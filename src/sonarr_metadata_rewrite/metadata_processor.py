"""Complete metadata file processing unit."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.etree.ElementTree import ElementTree  # noqa: F401

from sonarr_metadata_rewrite.backup_utils import create_backup, get_backup_path
from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.file_utils import extract_metadata_info, is_nfo_file
from sonarr_metadata_rewrite.models import (
    EpisodeMetadataInfo,
    MetadataInfo,
    MetadataProcessResult,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
)
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Complete processing unit for .nfo metadata files."""

    def __init__(self, settings: Settings, translator: Translator):
        self.settings = settings
        self.translator = translator

    def process_file(self, nfo_path: Path) -> MetadataProcessResult:
        """Process a single .nfo file with complete translation workflow.

        Args:
            nfo_path: Path to .nfo file to process

        Returns:
            MetadataProcessResult with success status and details
        """
        tmdb_ids = None
        metadata_info = None
        try:
            metadata_info = extract_metadata_info(nfo_path)

            if metadata_info.file_type == "episodedetails":
                return self._process_episode_file(nfo_path, metadata_info)

            return self._process_single_metadata_file(nfo_path, metadata_info)

        except Exception as e:
            return MetadataProcessResult(
                success=False,
                file_path=nfo_path,
                message=f"Processing error: {e}",
                exception=e,
                tmdb_ids=tmdb_ids,
                file_modified=False,
                translated_content=None,
            )

    def _process_single_metadata_file(
        self, nfo_path: Path, metadata_info: MetadataInfo
    ) -> MetadataProcessResult:
        """Process a single-document metadata file."""
        tmdb_ids = None

        # Extract all metadata in single parse (including content for comparison)
        tmdb_ids = self._build_tmdb_ids_from_metadata(metadata_info, nfo_path)
        if not tmdb_ids:
            return MetadataProcessResult(
                success=False,
                file_path=nfo_path,
                message="No TMDB ID found in .nfo file",
                file_modified=False,
                translated_content=None,
            )

        all_translations = self.translator.get_translations(tmdb_ids)
        selected_translation = self._select_preferred_translation(all_translations)

        if not selected_translation:
            original_metadata = self._get_backup_metadata_info(nfo_path)
            if original_metadata:
                if (
                    metadata_info.title != original_metadata.title
                    or metadata_info.description != original_metadata.description
                ):
                    selected_translation = TranslatedContent(
                        title=TranslatedString(
                            content=original_metadata.title, language="original"
                        ),
                        description=TranslatedString(
                            content=original_metadata.description,
                            language="original",
                        ),
                    )
                else:
                    preferred_langs = ", ".join(self.settings.preferred_languages)
                    available_langs = (
                        ", ".join(sorted(all_translations.keys()))
                        if all_translations
                        else "none"
                    )
                    return MetadataProcessResult(
                        success=False,
                        file_path=nfo_path,
                        message=(
                            f"File unchanged - content already matches original and "
                            f"no translation available in preferred languages "
                            f"[{preferred_langs}]. "
                            f"Available: [{available_langs}]"
                        ),
                        tmdb_ids=tmdb_ids,
                        file_modified=False,
                        translated_content=None,
                    )
            else:
                preferred_langs = ", ".join(self.settings.preferred_languages)
                available_langs = (
                    ", ".join(sorted(all_translations.keys()))
                    if all_translations
                    else "none"
                )
                return MetadataProcessResult(
                    success=False,
                    file_path=nfo_path,
                    message=(
                        f"File unchanged - no translation available in preferred "
                        f"languages [{preferred_langs}]. Available: [{available_langs}]"
                    ),
                    tmdb_ids=tmdb_ids,
                    file_modified=False,
                    translated_content=None,
                )

        selected_translation = self._apply_fallback_to_translation(
            metadata_info, selected_translation
        )

        if (
            metadata_info.title == selected_translation.title.content
            and metadata_info.description == selected_translation.description.content
        ):
            return MetadataProcessResult(
                success=True,
                file_path=nfo_path,
                message="Content already matches preferred translation",
                tmdb_ids=tmdb_ids,
                file_modified=False,
                translated_content=selected_translation,
            )

        backup_created = create_backup(
            nfo_path,
            self.settings.original_files_backup_dir,
            self.settings.rewrite_root_dirs,
        )

        self._write_translated_metadata_with_tree(
            metadata_info.xml_tree, nfo_path, selected_translation
        )

        return MetadataProcessResult(
            success=True,
            file_path=nfo_path,
            message=self._build_success_message(selected_translation),
            tmdb_ids=tmdb_ids,
            backup_created=backup_created,
            file_modified=True,
            translated_content=selected_translation,
        )

    def _process_episode_file(
        self, nfo_path: Path, metadata_info: MetadataInfo
    ) -> MetadataProcessResult:
        """Process one or more episode documents from a single NFO file."""
        episode_entries = metadata_info.episode_entries or []
        series_tmdb_id = self._resolve_tmdb_id_with_metadata(metadata_info, nfo_path)
        if series_tmdb_id is None:
            return MetadataProcessResult(
                success=False,
                file_path=nfo_path,
                message="No TMDB ID found in .nfo file",
                file_modified=False,
                translated_content=None,
            )

        selected_translation: TranslatedContent | None = None
        updated_translations: dict[int, TranslatedContent] = {}
        translated_count = 0
        unchanged_count = 0
        unavailable_count = 0
        first_tmdb_ids: TmdbIds | None = None

        backup_metadata = self._get_backup_metadata_info(nfo_path)

        for index, entry in enumerate(episode_entries):
            if entry.season is None or entry.episode is None:
                unavailable_count += 1
                continue

            entry_tmdb_ids = TmdbIds(
                tmdb_id=series_tmdb_id,
                season=entry.season,
                episode=entry.episode,
            )
            if first_tmdb_ids is None:
                first_tmdb_ids = entry_tmdb_ids

            all_translations = self.translator.get_translations(entry_tmdb_ids)
            entry_translation = self._select_preferred_translation(all_translations)

            entry_metadata = self._build_episode_metadata_info(entry, series_tmdb_id)
            if not entry_translation:
                backup_entry = self._find_matching_backup_episode(
                    backup_metadata, entry
                )
                if backup_entry and (
                    entry.title != backup_entry.title
                    or entry.description != backup_entry.description
                ):
                    entry_translation = TranslatedContent(
                        title=TranslatedString(
                            content=backup_entry.title, language="original"
                        ),
                        description=TranslatedString(
                            content=backup_entry.description,
                            language="original",
                        ),
                    )
                else:
                    unavailable_count += 1
                    continue

            entry_translation = self._apply_fallback_to_translation(
                entry_metadata, entry_translation
            )
            if selected_translation is None:
                selected_translation = entry_translation

            if (
                entry.title == entry_translation.title.content
                and entry.description == entry_translation.description.content
            ):
                unchanged_count += 1
                translated_count += 1
                continue

            updated_translations[index] = entry_translation
            translated_count += 1

        if not updated_translations and translated_count == 0:
            preferred_langs = ", ".join(self.settings.preferred_languages)
            return MetadataProcessResult(
                success=False,
                file_path=nfo_path,
                message=(
                    "File unchanged - no episode translation available in preferred "
                    f"languages [{preferred_langs}]"
                ),
                tmdb_ids=first_tmdb_ids,
                file_modified=False,
                translated_content=None,
            )

        if not updated_translations:
            message = self._build_multi_episode_message(
                updated_count=0,
                translated_count=translated_count,
                unchanged_count=unchanged_count,
                unavailable_count=unavailable_count,
                episode_count=len(episode_entries),
            )
            return MetadataProcessResult(
                success=True,
                file_path=nfo_path,
                message=message,
                tmdb_ids=first_tmdb_ids,
                file_modified=False,
                translated_content=selected_translation,
            )

        backup_created = create_backup(
            nfo_path,
            self.settings.original_files_backup_dir,
            self.settings.rewrite_root_dirs,
        )
        self._write_translated_episode_entries(
            episode_entries, nfo_path, updated_translations
        )

        message = self._build_multi_episode_message(
            updated_count=len(updated_translations),
            translated_count=translated_count,
            unchanged_count=unchanged_count,
            unavailable_count=unavailable_count,
            episode_count=len(episode_entries),
        )
        return MetadataProcessResult(
            success=True,
            file_path=nfo_path,
            message=message,
            tmdb_ids=first_tmdb_ids,
            backup_created=backup_created,
            file_modified=True,
            translated_content=selected_translation,
        )

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
        # Movies must have a direct TMDB ID; TV external-ID resolution does not
        # identify movie resources safely.
        if metadata_info.file_type == "movie":
            return metadata_info.tmdb_id

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
        """Find a unique parent TV show NFO for an episode.

        Args:
            episode_nfo_path: Path to episode .nfo file

        Returns:
            MetadataInfo of parent tvshow.nfo if found, None otherwise
        """
        current_dir = episode_nfo_path.parent

        # Check up to 3 levels up. A series root can use a nonstandard NFO name.
        for _ in range(3):
            candidates: list[MetadataInfo] = []
            for nfo_path in current_dir.iterdir():
                if not nfo_path.is_file() or not is_nfo_file(nfo_path):
                    continue
                try:
                    metadata_info = extract_metadata_info(nfo_path)
                    if metadata_info.file_type == "tvshow":
                        candidates.append(metadata_info)
                except (ET.ParseError, ValueError, AttributeError):
                    continue

            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                return None

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
            return TmdbIds(tmdb_id=tmdb_series_id)
        elif metadata_info.file_type == "movie":
            return TmdbIds(tmdb_id=tmdb_series_id, media_type="movie")
        elif metadata_info.file_type == "episodedetails":
            if metadata_info.season is None or metadata_info.episode is None:
                # Missing season/episode information
                return None
            return TmdbIds(
                tmdb_id=tmdb_series_id,
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
                tmdb_id=metadata_info.tmdb_id,
                media_type="movie" if metadata_info.file_type == "movie" else "tv",
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

    def _build_episode_metadata_info(
        self, entry: EpisodeMetadataInfo, series_tmdb_id: int
    ) -> MetadataInfo:
        """Convert an episode entry into MetadataInfo for shared helpers."""
        return MetadataInfo(
            tmdb_id=series_tmdb_id,
            tvdb_id=entry.tvdb_id,
            imdb_id=entry.imdb_id,
            file_type="episodedetails",
            season=entry.season,
            episode=entry.episode,
            title=entry.title,
            description=entry.description,
            xml_tree=entry.xml_tree,
        )

    def _find_matching_backup_episode(
        self, backup_metadata: MetadataInfo | None, entry: EpisodeMetadataInfo
    ) -> EpisodeMetadataInfo | None:
        """Find the matching backup episode by season and episode number."""
        if backup_metadata is None or not backup_metadata.episode_entries:
            return None

        for backup_entry in backup_metadata.episode_entries:
            if (
                backup_entry.season == entry.season
                and backup_entry.episode == entry.episode
            ):
                return backup_entry

        return None

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

        # Update title element
        title_element = root.find("title")  # type: ignore[union-attr]
        if title_element is not None:
            title_element.text = translation.title.content

        # Update plot/description element
        plot_element = root.find("plot")  # type: ignore[union-attr]
        if plot_element is not None:
            plot_element.text = translation.description.content

        # Write the updated XML back to file atomically
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            # Configure XML formatting
            ET.indent(xml_tree, space="  ", level=0)
            xml_tree.write(
                temp_path, encoding="utf-8", xml_declaration=True, method="xml"
            )

            # Atomic replacement
            temp_path.replace(nfo_path)

        except Exception:
            # Clean up temporary file if something went wrong
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _write_translated_episode_entries(
        self,
        episode_entries: list[EpisodeMetadataInfo],
        nfo_path: Path,
        updated_translations: dict[int, TranslatedContent],
    ) -> None:
        """Write translated content for one or more episode XML documents."""
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            serialized_documents: list[str] = []
            for index, entry in enumerate(episode_entries):
                xml_tree = entry.xml_tree
                if xml_tree is None:
                    raise ValueError("Episode XML tree cannot be None")
                root = xml_tree.getroot()
                if root is None:
                    raise ValueError("Episode XML root cannot be None")

                translation = updated_translations.get(index)
                if translation:
                    title_element = root.find("title")
                    if title_element is not None:
                        title_element.text = translation.title.content
                    plot_element = root.find("plot")
                    if plot_element is not None:
                        plot_element.text = translation.description.content

                ET.indent(xml_tree, space="  ", level=0)
                serialized_documents.append(ET.tostring(root, encoding="unicode"))

            content = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                + "\n".join(serialized_documents)
                + "\n"
            )
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(nfo_path)
        except Exception:
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

    def _build_multi_episode_message(
        self,
        updated_count: int,
        translated_count: int,
        unchanged_count: int,
        unavailable_count: int,
        episode_count: int,
    ) -> str:
        """Build a status message for multi-episode files."""
        if episode_count == 1:
            if updated_count == 1:
                return "Successfully translated 1 episode"
            return "Content already matches preferred translation"

        parts = [f"{updated_count} of {episode_count} episodes updated"]
        if unchanged_count:
            parts.append(f"{unchanged_count} already matched")
        skipped_count = episode_count - translated_count
        if unavailable_count or skipped_count:
            parts.append(f"{max(unavailable_count, skipped_count)} left unchanged")
        return "; ".join(parts)

    def _get_backup_metadata_info(self, nfo_path: Path) -> MetadataInfo | None:
        """Get original metadata from backup NFO file if available.

        Args:
            nfo_path: Path to current .nfo file

        Returns:
            MetadataInfo object if backup exists, None otherwise
        """
        backup_path = get_backup_path(
            nfo_path,
            self.settings.original_files_backup_dir,
            self.settings.rewrite_root_dirs,
        )
        if not backup_path:
            return None

        try:
            return extract_metadata_info(backup_path)
        except Exception as e:
            logger.warning(
                f"Failed to read backup file {backup_path}: {e}", exc_info=True
            )
            return None
