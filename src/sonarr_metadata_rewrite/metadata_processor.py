"""Complete metadata file processing unit."""

import logging
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xml.etree.ElementTree import ElementTree  # noqa: F401

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import (
    MetadataInfo,
    ProcessResult,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
)
from sonarr_metadata_rewrite.retry_utils import retry
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Complete processing unit for .nfo metadata files."""

    def __init__(self, settings: Settings, translator: Translator):
        self.settings = settings
        self.translator = translator

    def _parse_nfo_with_retry(self, nfo_path: Path) -> "ElementTree[ET.Element]":
        """Parse NFO file with retry logic for incomplete/corrupt files.

        Args:
            nfo_path: Path to .nfo file to parse

        Returns:
            Parsed XML tree

        Raises:
            ET.ParseError: If file remains corrupt after retries
            OSError: If file cannot be accessed after retries
        """

        @retry(
            timeout=10.0,
            interval=0.5,
            log_interval=3.0,
            exceptions=(ET.ParseError, OSError),
        )
        def parse_file() -> "ElementTree[ET.Element]":
            try:
                return ET.parse(nfo_path)
            except ET.ParseError:
                # Try to handle multi-episode files without relying on error message
                if self._is_multi_episode_file(nfo_path):
                    return self._parse_multi_episode_file(nfo_path)
                raise

        return parse_file()

    def _is_multi_episode_file(self, nfo_path: Path) -> bool:
        """Check if NFO file contains multiple episodedetails root elements.

        Args:
            nfo_path: Path to .nfo file to check

        Returns:
            True if file has multiple episodedetails root elements, False otherwise
        """
        try:
            with open(nfo_path, encoding="utf-8") as f:
                content = f.read().strip()

            # Count occurrences of <episodedetails> opening tags
            episode_tags = re.findall(r"<episodedetails\b", content)
            return len(episode_tags) > 1

        except Exception:
            return False

    def _parse_multi_episode_file(self, nfo_path: Path) -> "ElementTree[ET.Element]":
        """Parse NFO file with multiple <episodedetails> root elements.

        This method preserves the entire multi-episode structure by wrapping
        all episodes in a container, allowing the metadata writing process to
        update title and plot fields while keeping everything else intact.

        Args:
            nfo_path: Path to .nfo file to parse

        Returns:
            Parsed XML tree with all episodes preserved under a wrapper element

        Raises:
            ET.ParseError: If file cannot be parsed even with multi-episode handling
        """
        try:
            # Read the file content
            with open(nfo_path, encoding="utf-8") as f:
                content = f.read()

            # Wrap multiple root elements in a container for parsing
            wrapped_content = f"<multiepisode>{content}</multiepisode>"

            # Parse the wrapped content
            root = ET.fromstring(wrapped_content)
            if root is None:
                raise ET.ParseError("Failed to parse wrapped multi-episode content")

            # Find all episodedetails elements
            episode_elements = root.findall("episodedetails")

            if not episode_elements:
                raise ET.ParseError(
                    "No episodedetails elements found in multi-episode file"
                )

            # Create a new tree with the wrapper as root to preserve all episodes
            tree: ElementTree[ET.Element] = ET.ElementTree(root)

            return tree

        except Exception as e:
            # If multi-episode parsing fails, re-raise as ParseError with context
            raise ET.ParseError(f"Failed to parse multi-episode file: {e}") from e

    def process_file(self, nfo_path: Path) -> ProcessResult:
        """Process a single .nfo file with complete translation workflow.

        Args:
            nfo_path: Path to .nfo file to process

        Returns:
            ProcessResult with success status and details
        """
        # Check if this is a multi-episode file
        if self._is_multi_episode_file(nfo_path):
            return self._process_multi_episode_file(nfo_path)
        else:
            return self._process_single_episode_file(nfo_path)

    def _process_single_episode_file(self, nfo_path: Path) -> ProcessResult:
        """Process a single-episode NFO file."""
        tmdb_ids = None
        metadata_info = None
        try:
            # Extract all metadata in single parse (including content for comparison)
            metadata_info = self._extract_metadata_info(nfo_path)

            # Build TMDB IDs from parsed metadata using hierarchical resolution
            tmdb_ids = self._build_tmdb_ids_from_metadata(metadata_info, nfo_path)
            if not tmdb_ids:
                return ProcessResult(
                    success=False,
                    file_path=nfo_path,
                    message="No TMDB ID found in .nfo file",
                    file_modified=False,
                    translated_content=None,
                )

            # Get translations from TMDB API
            all_translations = self.translator.get_translations(tmdb_ids)

            # Apply language preferences to find best translation
            selected_translation = self._select_preferred_translation(all_translations)
            if selected_translation:
                # Check if content matches selected translation (use cached)
                current_title, current_description = (
                    metadata_info.title,
                    metadata_info.description,
                )

                if (
                    current_title == selected_translation.title.content
                    and current_description == selected_translation.description.content
                ):
                    return ProcessResult(
                        success=True,
                        file_path=nfo_path,
                        message="Content already matches preferred translation",
                        tmdb_ids=tmdb_ids,
                        file_modified=False,
                        translated_content=selected_translation,
                    )

            if not selected_translation:
                # No preferred translation found - try to revert to original backup
                original_metadata = self._get_backup_metadata_info(nfo_path)
                if original_metadata:
                    original_title, original_description = (
                        original_metadata.title,
                        original_metadata.description,
                    )
                    current_title, current_description = (
                        metadata_info.title,
                        metadata_info.description,
                    )

                    # Only revert if current content is different from original
                    if (
                        current_title != original_title
                        or current_description != original_description
                    ):
                        selected_translation = TranslatedContent(
                            title=TranslatedString(
                                content=original_title, language="original"
                            ),
                            description=TranslatedString(
                                content=original_description, language="original"
                            ),
                        )
                        # Continue to write original content back
                    else:
                        # Already showing original content
                        preferred_langs = ", ".join(self.settings.preferred_languages)
                        available_langs = (
                            ", ".join(sorted(all_translations.keys()))
                            if all_translations
                            else "none"
                        )
                        return ProcessResult(
                            success=False,
                            file_path=nfo_path,
                            message=(
                                f"File unchanged - content already matches original "
                                f"and "
                                f"no translation available in preferred languages "
                                f"[{preferred_langs}]. "
                                f"Available: [{available_langs}]"
                            ),
                            tmdb_ids=tmdb_ids,
                            file_modified=False,
                            translated_content=None,
                        )
                else:
                    # No backup available - return existing failure result
                    preferred_langs = ", ".join(self.settings.preferred_languages)
                    available_langs = (
                        ", ".join(sorted(all_translations.keys()))
                        if all_translations
                        else "none"
                    )
                    return ProcessResult(
                        success=False,
                        file_path=nfo_path,
                        message=(
                            f"File unchanged - no translation available in preferred "
                            f"languages [{preferred_langs}]. "
                            f"Available: [{available_langs}]"
                        ),
                        tmdb_ids=tmdb_ids,
                        file_modified=False,
                        translated_content=None,
                    )

            # Apply fallback logic for empty translation fields
            selected_translation = self._apply_fallback_to_translation(
                metadata_info, selected_translation
            )

            # Create backup if enabled
            backup_created = self._backup_original(nfo_path)

            # Write translated metadata using cached XML tree
            self._write_translated_metadata_with_tree(
                metadata_info.xml_tree, nfo_path, selected_translation
            )

            return ProcessResult(
                success=True,
                file_path=nfo_path,
                message=self._build_success_message(selected_translation),
                tmdb_ids=tmdb_ids,
                backup_created=backup_created,
                file_modified=True,
                translated_content=selected_translation,
            )

        except Exception as e:
            return ProcessResult(
                success=False,
                file_path=nfo_path,
                message=f"Processing error: {e}",
                tmdb_ids=tmdb_ids,
                file_modified=False,
                translated_content=None,
            )

    def _process_multi_episode_file(self, nfo_path: Path) -> ProcessResult:
        """Process a multi-episode NFO file with individual episode translations."""
        try:
            # Extract metadata from all episodes
            all_metadata = self._extract_all_metadata_info(nfo_path)

            if not all_metadata:
                return ProcessResult(
                    success=False,
                    file_path=nfo_path,
                    message="No episodes found in multi-episode file",
                    file_modified=False,
                    translated_content=None,
                )

            # Process each episode to get its translation
            episode_translations: list[TranslatedContent | None] = []
            translated_episodes = 0

            for metadata_info in all_metadata:
                # Build TMDB IDs for this specific episode
                tmdb_ids = self._build_tmdb_ids_from_metadata(metadata_info, nfo_path)
                if not tmdb_ids:
                    # Skip episodes without TMDB ID
                    episode_translations.append(None)
                    continue

                # Get translations for this specific episode
                all_translations = self.translator.get_translations(tmdb_ids)
                selected_translation = self._select_preferred_translation(
                    all_translations
                )

                if selected_translation:
                    # Apply fallback logic for empty translation fields
                    selected_translation = self._apply_fallback_to_translation(
                        metadata_info, selected_translation
                    )
                    translated_episodes += 1

                episode_translations.append(selected_translation)

            if translated_episodes == 0:
                return ProcessResult(
                    success=False,
                    file_path=nfo_path,
                    message="No translations found for any episode in file",
                    file_modified=False,
                    translated_content=None,
                )

            # Create backup if enabled
            backup_created = self._backup_original(nfo_path)

            # Write translated metadata for all episodes
            self._write_multi_episode_metadata(
                all_metadata[0].xml_tree, nfo_path, episode_translations
            )

            # Return result with first episode's translation for compatibility
            first_translation = next((t for t in episode_translations if t), None)
            episode_count = len(all_metadata)
            message = (
                f"Successfully translated {translated_episodes}/{episode_count} eps"
            )
            return ProcessResult(
                success=True,
                file_path=nfo_path,
                message=message,
                tmdb_ids=self._build_tmdb_ids_from_metadata(all_metadata[0], nfo_path),
                backup_created=backup_created,
                file_modified=True,
                translated_content=first_translation,
            )

        except Exception as e:
            return ProcessResult(
                success=False,
                file_path=nfo_path,
                message=f"Processing error: {e}",
                file_modified=False,
                translated_content=None,
            )

    def _extract_metadata_info(self, nfo_path: Path) -> MetadataInfo:
        """Extract all metadata information from NFO file in single parse.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            MetadataInfo object with all extracted data (first episode for multi-ep)
        """
        metadata_list = self._extract_all_metadata_info(nfo_path)
        return metadata_list[0]  # Return first episode for compatibility

    def _extract_all_metadata_info(self, nfo_path: Path) -> list[MetadataInfo]:
        """Extract metadata information from all episodes in NFO file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            List of MetadataInfo objects (one per episode, or single for non-multi-ep)
        """
        tree = self._parse_nfo_with_retry(nfo_path)
        root = tree.getroot()

        if root.tag == "multiepisode":
            # Multi-episode file - extract from all episodes
            metadata_list = []
            episodes = root.findall("episodedetails")

            for episode_elem in episodes:
                info = self._extract_metadata_from_element(
                    episode_elem, "episodedetails", tree
                )
                metadata_list.append(info)

            return metadata_list

        elif root.tag in ("tvshow", "episodedetails"):
            # Single episode or show file
            info = self._extract_metadata_from_element(root, root.tag, tree)
            return [info]

        else:
            # Unknown file type
            info = self._extract_metadata_from_element(root, "unknown", tree)
            return [info]

    def _extract_metadata_from_element(
        self,
        element: ET.Element,
        file_type: str,
        xml_tree: "ElementTree[ET.Element]",
    ) -> MetadataInfo:
        """Extract metadata from a single XML element.

        Args:
            element: XML element to extract from
            file_type: Type of file ("tvshow", "episodedetails", "unknown")
            xml_tree: Complete XML tree for writing back

        Returns:
            MetadataInfo object with extracted data
        """
        info = MetadataInfo(file_type=file_type, xml_tree=xml_tree)  # type: ignore[arg-type]

        # Extract all uniqueid elements
        for uniqueid in element.findall(".//uniqueid"):
            id_type = uniqueid.get("type", "").lower()
            id_value = uniqueid.text

            if not id_value or not id_value.strip():
                continue

            if id_type == "tmdb":
                info.tmdb_id = int(id_value.strip())
            elif id_type == "tvdb":
                info.tvdb_id = int(id_value.strip())
            elif id_type == "imdb":
                info.imdb_id = id_value.strip()

        # Extract title
        title_element = element.find("title")
        if title_element is not None and title_element.text:
            info.title = title_element.text.strip()

        # Extract plot/description
        plot_element = element.find("plot")
        if plot_element is not None and plot_element.text:
            info.description = plot_element.text.strip()

        # For episode files, extract season/episode numbers
        if file_type == "episodedetails":
            season_element = element.find("season")
            episode_element = element.find("episode")

            if season_element is not None and season_element.text:
                info.season = int(season_element.text.strip())
            if episode_element is not None and episode_element.text:
                info.episode = int(episode_element.text.strip())

        return info

    def _resolve_tmdb_id_with_metadata(
        self, metadata_info: MetadataInfo, nfo_path: Path
    ) -> int | None:
        """Resolve TMDB ID using hierarchical strategy with pre-parsed metadata.

        Args:
            metadata_info: Already-parsed metadata information
            nfo_path: Path to .nfo file (for hierarchical resolution if needed)

        Returns:
            TMDB series ID if found, None otherwise
        """
        # Tier 1: Direct TMDB ID (already checked in metadata_info)
        if metadata_info.tmdb_id:
            return metadata_info.tmdb_id

        # Tier 2: For episode files, try parent recursively
        parent_info = None
        if metadata_info.file_type == "episodedetails":
            parent_info = self._find_parent_metadata_info(nfo_path)
            if parent_info and parent_info.tmdb_id:
                return parent_info.tmdb_id

        # Tier 3: External APIs
        return self._resolve_via_external_apis(metadata_info, parent_info)

    def _find_parent_metadata_info(self, episode_nfo_path: Path) -> MetadataInfo | None:
        """Find and parse parent tvshow.nfo file for episode.

        Args:
            episode_nfo_path: Path to episode .nfo file

        Returns:
            MetadataInfo of parent tvshow.nfo if found, None otherwise
        """
        current_dir = episode_nfo_path.parent

        # Check up to 3 levels up to find tvshow.nfo
        for _ in range(3):
            tvshow_path = current_dir / "tvshow.nfo"
            if tvshow_path.exists() and tvshow_path.is_file():
                try:
                    # Parse and extract metadata info
                    metadata_info = self._extract_metadata_info(tvshow_path)
                    if metadata_info.file_type == "tvshow":
                        return metadata_info
                except (ET.ParseError, ValueError, AttributeError):
                    # Failed to parse, continue searching
                    pass

            # Move up one directory level
            parent_dir = current_dir.parent
            if parent_dir == current_dir:  # Reached filesystem root
                break
            current_dir = parent_dir

        return None

    def _resolve_via_external_apis(
        self,
        current_info: MetadataInfo,
        parent_info: MetadataInfo | None,
    ) -> int | None:
        """Try to resolve TMDB ID using external APIs.

        Args:
            current_info: Metadata from current NFO file
            parent_info: Metadata from parent NFO file (if applicable)

        Returns:
            TMDB series ID if found, None otherwise
        """
        # Try current file's external IDs first
        tmdb_id = self._try_external_id_lookup(current_info)
        if tmdb_id:
            return tmdb_id

        # For episode files, also try parent's external IDs
        if parent_info:
            tmdb_id = self._try_external_id_lookup(parent_info)
            if tmdb_id:
                # Don't write to current file since the ID belongs to parent
                return tmdb_id

        return None

    def _try_external_id_lookup(self, info: MetadataInfo) -> int | None:
        """Try to find TMDB ID using external IDs from metadata info.

        Args:
            info: MetadataInfo containing external IDs

        Returns:
            TMDB series ID if found, None otherwise
        """
        # Try TVDB ID first
        if info.tvdb_id:
            tmdb_id = self.translator.find_tmdb_id_by_external_id(
                str(info.tvdb_id), "tvdb_id"
            )
            if tmdb_id:
                return tmdb_id

        # Try IMDB ID
        if info.imdb_id:
            tmdb_id = self.translator.find_tmdb_id_by_external_id(
                info.imdb_id, "imdb_id"
            )
            if tmdb_id:
                return tmdb_id

        return None

    def _build_tmdb_ids_from_metadata(
        self, metadata_info: MetadataInfo, nfo_path: Path
    ) -> TmdbIds | None:
        """Build TmdbIds object from parsed metadata using hierarchical resolution.

        Args:
            metadata_info: Already-parsed metadata information
            nfo_path: Path to the NFO file (for hierarchical resolution if needed)

        Returns:
            TmdbIds object if found, None otherwise
        """
        # Use hierarchical resolution (returns immediately if tmdb_id exists)
        tmdb_series_id = self._resolve_tmdb_id_with_metadata(metadata_info, nfo_path)
        if tmdb_series_id is None:
            return None

        # Build TmdbIds based on file type
        if metadata_info.file_type == "tvshow":
            return TmdbIds(series_id=tmdb_series_id)
        elif metadata_info.file_type == "episodedetails":
            if metadata_info.season is None or metadata_info.episode is None:
                # Missing season/episode information
                return None
            return TmdbIds(
                series_id=tmdb_series_id,
                season=metadata_info.season,
                episode=metadata_info.episode,
            )

        # Unknown file type
        return None

    def _apply_fallback_to_translation(
        self, metadata_info: MetadataInfo, translation: TranslatedContent
    ) -> TranslatedContent:
        """Apply fallback logic to translation with empty fields.

        Args:
            metadata_info: Cached metadata information from NFO file
            translation: Selected translation that may have empty fields

        Returns:
            TranslatedContent with empty fields replaced by original content
        """
        # If both title and description are present, no fallback needed
        if translation.title.content and translation.description.content:
            return translation

        # If title is empty, try original language title if language family matches
        if not translation.title.content:
            # Get the language from either field (prefer title, fallback to description)
            preferred_language = (
                translation.title.language
                if translation.title.language != "unknown"
                else translation.description.language
            )
            original_title = self._get_original_title_if_language_matches(
                metadata_info, preferred_language
            )
            if original_title:
                # Use original title but keep the preferred language for reporting
                return TranslatedContent(
                    title=TranslatedString(
                        content=original_title, language=preferred_language
                    ),
                    description=(
                        translation.description
                        if translation.description.content
                        else TranslatedString(
                            content=metadata_info.description, language="original"
                        )
                    ),
                )

        # Apply fallback using cached original content
        final_title = (
            translation.title
            if translation.title.content
            else TranslatedString(content=metadata_info.title, language="original")
        )
        final_description = (
            translation.description
            if translation.description.content
            else TranslatedString(
                content=metadata_info.description, language="original"
            )
        )

        # Return new TranslatedContent with fallback applied
        return TranslatedContent(
            title=final_title,
            description=final_description,
        )

    def _get_original_title_if_language_matches(
        self, metadata_info: MetadataInfo, preferred_language: str
    ) -> str | None:
        """Get original title if original language matches preferred language family.

        Args:
            metadata_info: Cached metadata information containing TMDB IDs
            preferred_language: The preferred language code (e.g., "zh-CN")

        Returns:
            Original title if language families match, None otherwise
        """
        try:
            # Need TMDB ID for API call
            if not metadata_info.tmdb_id:
                return None

            # Build TmdbIds object for API call
            tmdb_ids = TmdbIds(
                series_id=metadata_info.tmdb_id,
                season=metadata_info.season,
                episode=metadata_info.episode,
            )

            # Get original language and title from TMDB Details API
            original_details = self.translator.get_original_details(tmdb_ids)
            if not original_details:
                return None

            original_language, original_title = original_details

            # Check if language families match
            preferred_base = preferred_language.split("-")[0]
            original_base = original_language.split("-")[0]

            if preferred_base == original_base:
                return original_title

        except Exception:
            # If anything fails, return None to use standard fallback
            pass

        return None

    def _backup_original(self, nfo_path: Path) -> bool:
        """Create backup of original .nfo file.

        Args:
            nfo_path: Path to original .nfo file

        Returns:
            True if backup was created successfully, False otherwise
        """
        if not self.settings.original_files_backup_dir:
            return False

        # Create backup directory structure mirroring original
        relative_path = nfo_path.relative_to(self.settings.rewrite_root_dir)
        backup_path = self.settings.original_files_backup_dir / relative_path

        # Check if backup already exists - don't overwrite it
        if backup_path.exists():
            return True  # Backup already exists, so we consider this successful

        # Ensure backup directory exists
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy original file to backup location
        shutil.copy2(nfo_path, backup_path)
        return True

    def _write_translated_metadata_with_tree(
        self,
        xml_tree: ET.ElementTree | None,
        nfo_path: Path,
        translation: TranslatedContent,
    ) -> None:
        """Write translated metadata using cached XML tree.

        Args:
            xml_tree: Cached XML tree from metadata extraction
            nfo_path: Path to .nfo file to update
            translation: Translated content

        Raises:
            Exception: If write operation fails
        """
        if xml_tree is None:
            raise ValueError("XML tree cannot be None")

        root = xml_tree.getroot()
        if root is None:
            raise ValueError("XML tree root cannot be None")

        # Update title and plot elements (for single episode or show files only)
        title_element = root.find("title")
        if title_element is not None:
            title_element.text = translation.title.content

        plot_element = root.find("plot")
        if plot_element is not None:
            plot_element.text = translation.description.content

        # Write the updated XML back to file atomically
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            # Standard XML writing (no XML declaration since original files lack it)
            ET.indent(xml_tree, space="  ", level=0)
            xml_tree.write(
                temp_path, encoding="utf-8", xml_declaration=False, method="xml"
            )

            # Atomic replacement
            temp_path.replace(nfo_path)

        except Exception:
            # Clean up temporary file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _write_multi_episode_metadata(
        self,
        xml_tree: ET.ElementTree | None,
        nfo_path: Path,
        episode_translations: list[TranslatedContent | None],
    ) -> None:
        """Write translated metadata for multi-episode files.

        Args:
            xml_tree: Cached XML tree from metadata extraction
            nfo_path: Path to .nfo file to update
            episode_translations: List of translations for each episode (None if none)

        Raises:
            Exception: If write operation fails
        """
        if xml_tree is None:
            raise ValueError("XML tree cannot be None")

        root = xml_tree.getroot()
        if root is None:
            raise ValueError("XML tree root cannot be None")

        if root.tag != "multiepisode":
            raise ValueError("Expected multiepisode root for multi-episode writing")

        episodes = root.findall("episodedetails")
        if len(episodes) != len(episode_translations):
            raise ValueError("Number of episodes and translations must match")

        # Update each episode with its specific translation
        for episode, translation in zip(episodes, episode_translations, strict=False):
            if translation is not None:
                title_element = episode.find("title")
                if title_element is not None:
                    title_element.text = translation.title.content

                plot_element = episode.find("plot")
                if plot_element is not None:
                    plot_element.text = translation.description.content

        # Write back the original structure without wrapper
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            content_lines = []
            for episode in episodes:
                # Format each episode properly
                ET.indent(episode, space="  ", level=0)
                episode_str = ET.tostring(episode, encoding="unicode", method="xml")
                content_lines.append(episode_str)

            # Write without XML declaration for multi-episode files
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(content_lines))

            # Atomic replacement
            temp_path.replace(nfo_path)

        except Exception:
            # Clean up temporary file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _select_preferred_translation(
        self, all_translations: dict[str, TranslatedContent]
    ) -> TranslatedContent | None:
        """Select best translation based on language preferences with smart merging.

        Args:
            all_translations: Dictionary of all available translations

        Returns:
            Merged translation from preferred languages or None if no match found
        """
        title_string = None
        description_string = None

        # Find best title and description from preferred languages
        for preferred_lang in self.settings.preferred_languages:
            if preferred_lang in all_translations:
                translation = all_translations[preferred_lang]

                # Take title if we don't have one yet and this translation has content
                if not title_string and translation.title.content:
                    title_string = translation.title

                # Take description if missing and this translation has content
                if not description_string and translation.description.content:
                    description_string = translation.description

                # Stop if we have both title and description
                if title_string and description_string:
                    break

        # Return merged translation if we found at least one field
        if title_string or description_string:
            # Use empty TranslatedString with "unknown" language for missing fields
            return TranslatedContent(
                title=title_string or TranslatedString(content="", language="unknown"),
                description=description_string
                or TranslatedString(content="", language="unknown"),
            )

        return None

    def _build_success_message(self, translation: TranslatedContent) -> str:
        """Build success message showing language sources for title and description.

        Args:
            translation: The selected translation content

        Returns:
            Formatted success message
        """
        if translation.title.language == translation.description.language:
            return f"Successfully translated to {translation.title.language}"
        else:
            parts = []
            if translation.title.content:
                parts.append(f"title: {translation.title.language}")
            if translation.description.content:
                parts.append(f"description: {translation.description.language}")
            return f"Successfully translated ({', '.join(parts)})"

    def _get_backup_metadata_info(self, nfo_path: Path) -> MetadataInfo | None:
        """Get original metadata from backup file if available.

        Args:
            nfo_path: Path to current .nfo file

        Returns:
            MetadataInfo object if backup exists, None otherwise
        """
        if not self.settings.original_files_backup_dir:
            return None

        # Calculate backup path using same logic as _backup_original()
        relative_path = nfo_path.relative_to(self.settings.rewrite_root_dir)
        backup_path = self.settings.original_files_backup_dir / relative_path

        if backup_path.exists():
            try:
                return self._extract_metadata_info(backup_path)
            except Exception as e:
                logger.warning(f"Failed to read backup file {backup_path}: {e}")
                return None
        return None
