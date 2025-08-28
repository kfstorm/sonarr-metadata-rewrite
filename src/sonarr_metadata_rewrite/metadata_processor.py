"""Complete metadata file processing unit."""

import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import (
    ExternalIds,
    ProcessResult,
    TmdbIds,
    TranslatedContent,
)
from sonarr_metadata_rewrite.translator import Translator

logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Complete processing unit for .nfo metadata files."""

    def __init__(self, settings: Settings, translator: Translator):
        self.settings = settings
        self.translator = translator

    def process_file(self, nfo_path: Path) -> ProcessResult:
        """Process a single .nfo file with complete translation workflow.

        Args:
            nfo_path: Path to .nfo file to process

        Returns:
            ProcessResult with success status and details
        """
        tmdb_ids = None
        try:
            # Extract TMDB IDs from .nfo file
            tmdb_ids = self._extract_tmdb_ids(nfo_path)
            if not tmdb_ids:
                return ProcessResult(
                    success=False,
                    file_path=nfo_path,
                    message="No TMDB ID found in .nfo file",
                    file_modified=False,
                    selected_language=None,
                )

            # Get translations from TMDB API
            all_translations = self.translator.get_translations(tmdb_ids)

            # Apply language preferences to find best translation
            selected_translation = self._select_preferred_translation(all_translations)
            if selected_translation:
                # Check if content already matches the selected translation
                current_title, current_description = self._extract_original_content(
                    nfo_path
                )

                if (
                    current_title == selected_translation.title
                    and current_description == selected_translation.description
                ):
                    return ProcessResult(
                        success=True,
                        file_path=nfo_path,
                        message=(
                            f"Content already matches preferred translation "
                            f"({selected_translation.language})"
                        ),
                        tmdb_ids=tmdb_ids,
                        translations_found=True,
                        file_modified=False,
                        selected_language=selected_translation.language,
                    )

            if not selected_translation:
                # No preferred translation found - try to revert to original backup
                original_content = self._get_original_content_from_backup(nfo_path)
                if original_content:
                    original_title, original_description = original_content
                    current_title, current_description = self._extract_original_content(
                        nfo_path
                    )

                    # Only revert if current content is different from original
                    if (
                        current_title != original_title
                        or current_description != original_description
                    ):
                        selected_translation = TranslatedContent(
                            title=original_title,
                            description=original_description,
                            language="original",
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
                            translations_found=bool(all_translations),
                            file_modified=False,
                            selected_language=None,
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
                        translations_found=bool(all_translations),
                        file_modified=False,
                        selected_language=None,
                    )

            # Apply fallback logic for empty translation fields
            selected_translation = self._apply_fallback_to_translation(
                nfo_path, selected_translation
            )

            # Create backup if enabled
            backup_created = self._backup_original(nfo_path)

            # Write translated metadata
            self._write_translated_metadata(nfo_path, selected_translation)

            return ProcessResult(
                success=True,
                file_path=nfo_path,
                message=f"Successfully translated to {selected_translation.language}",
                tmdb_ids=tmdb_ids,
                translations_found=True,
                backup_created=backup_created,
                file_modified=True,
                selected_language=selected_translation.language,
            )

        except Exception as e:
            return ProcessResult(
                success=False,
                file_path=nfo_path,
                message=f"Processing error: {e}",
                tmdb_ids=tmdb_ids,
                file_modified=False,
                selected_language=None,
            )

    def _extract_tmdb_ids(self, nfo_path: Path) -> TmdbIds | None:
        """Extract TMDB IDs from .nfo XML file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            TmdbIds object if found, None otherwise
        """
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Find TMDB uniqueid
        tmdb_id = None
        uniqueid_elements = root.findall('.//uniqueid[@type="tmdb"]')
        if uniqueid_elements:
            tmdb_id_text = uniqueid_elements[0].text
            if tmdb_id_text and tmdb_id_text.strip():
                tmdb_id = int(tmdb_id_text.strip())

        # Determine if this is a series or episode file
        if root.tag == "tvshow":
            # Series file
            if tmdb_id is None:
<<<<<<< HEAD
                # Try to find TMDB ID using external IDs
                external_ids = self._extract_external_ids(root)
                if external_ids and (external_ids.tvdb_id or external_ids.imdb_id):
                    tmdb_id = self.translator.find_tmdb_id_by_external_id(external_ids)
                    if tmdb_id is None:
                        return None
                else:
                    return None
=======
                return None
>>>>>>> 7da425d15b5924ced21191626590a54dfbd0587f
            return TmdbIds(series_id=tmdb_id)
        elif root.tag == "episodedetails":
            # Episode file - extract season and episode numbers first
            season_element = root.find("season")
            episode_element = root.find("episode")

            if season_element is None or episode_element is None:
                # Missing season/episode information
                return None

            season_text = season_element.text
            episode_text = episode_element.text
            if season_text is None or episode_text is None:
                return None

            season = int(season_text.strip())
            episode = int(episode_text.strip())

            # If no TMDB ID in episode file, try to find it from parent tvshow.nfo
            if tmdb_id is None:
                tmdb_id = self._find_series_tmdb_id_from_parent(nfo_path)
                if tmdb_id is None:
                    return None

            return TmdbIds(series_id=tmdb_id, season=season, episode=episode)
        else:
            # Unknown file type
            return None

    def _extract_external_ids(self, root: ET.Element) -> ExternalIds:
        """Extract external IDs from .nfo XML root element.

        Args:
            root: XML root element from .nfo file

        Returns:
            ExternalIds object with available external IDs
        """
        external_ids = ExternalIds()

        # Check for TVDB ID in uniqueid elements
        tvdb_elements = root.findall('.//uniqueid[@type="tvdb"]')
        if tvdb_elements:
            tvdb_id_text = tvdb_elements[0].text
            if tvdb_id_text and tvdb_id_text.strip().isdigit():
                external_ids.tvdb_id = int(tvdb_id_text.strip())

        # Check for IMDB ID in uniqueid elements
        imdb_elements = root.findall('.//uniqueid[@type="imdb"]')
        if imdb_elements:
            imdb_id_text = imdb_elements[0].text
            if imdb_id_text and imdb_id_text.strip():
                external_ids.imdb_id = imdb_id_text.strip()

        return external_ids

    def _find_series_tmdb_id_from_parent(self, episode_nfo_path: Path) -> int | None:
        """Find TMDB series ID from parent directory's tvshow.nfo file.

        Args:
            episode_nfo_path: Path to episode .nfo file

        Returns:
            TMDB series ID if found, None otherwise
        """
        # Start from the episode file's directory and walk up to find tvshow.nfo
        current_dir = episode_nfo_path.parent

        # Check up to 3 levels up to find tvshow.nfo (handles Season subdirectories)
        for _ in range(3):
            tvshow_path = current_dir / "tvshow.nfo"
            if tvshow_path.exists() and tvshow_path.is_file():
                try:
                    tree = ET.parse(tvshow_path)
                    root = tree.getroot()

                    # Only process if it's actually a tvshow file
                    if root.tag == "tvshow":
                        uniqueid_elements = root.findall('.//uniqueid[@type="tmdb"]')
                        if uniqueid_elements:
                            tmdb_id_text = uniqueid_elements[0].text
                            if tmdb_id_text and tmdb_id_text.strip():
                                return int(tmdb_id_text.strip())
                        
                        # If no TMDB ID found, try external ID lookup
                        external_ids = self._extract_external_ids(root)
                        if external_ids and (external_ids.tvdb_id or external_ids.imdb_id):
                            tmdb_id = self.translator.find_tmdb_id_by_external_id(external_ids)
                            if tmdb_id:
                                return tmdb_id
                except (ET.ParseError, ValueError, AttributeError):
                    # Failed to parse or extract TMDB ID, continue searching
                    pass

            # Move up one directory level
            parent_dir = current_dir.parent
            if parent_dir == current_dir:  # Reached filesystem root
                break
            current_dir = parent_dir

        return None

    def _extract_original_content(self, nfo_path: Path) -> tuple[str, str]:
        """Extract original title and description from .nfo file.

        Args:
            nfo_path: Path to .nfo file

        Returns:
            Tuple of (original_title, original_description)
        """
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Extract title
        original_title = ""
        title_element = root.find("title")
        if title_element is not None and title_element.text:
            original_title = title_element.text.strip()

        # Extract plot/description
        original_description = ""
        plot_element = root.find("plot")
        if plot_element is not None and plot_element.text:
            original_description = plot_element.text.strip()

        return original_title, original_description

    def _apply_fallback_to_translation(
        self, nfo_path: Path, translation: TranslatedContent
    ) -> TranslatedContent:
        """Apply fallback logic to translation with empty fields.

        Args:
            nfo_path: Path to .nfo file to get original content from
            translation: Selected translation that may have empty fields

        Returns:
            TranslatedContent with empty fields replaced by original content
        """
        # If both title and description are present, no fallback needed
        if translation.title and translation.description:
            return translation

        # If title is empty, try to use original language title if language family
        # matches
        if not translation.title:
            original_title = self._get_original_title_if_language_matches(
                nfo_path, translation.language
            )
            if original_title:
                # Use original title but keep the preferred language for reporting
                final_title = original_title
                final_description = (
                    translation.description
                    if translation.description
                    else self._extract_original_content(nfo_path)[1]
                )
                return TranslatedContent(
                    title=final_title,
                    description=final_description,
                    language=translation.language,
                )

        # Extract original content for standard fallback
        original_title, original_description = self._extract_original_content(nfo_path)

        # Apply fallback for empty fields
        final_title = translation.title if translation.title else original_title
        final_description = (
            translation.description if translation.description else original_description
        )

        # Return new TranslatedContent with fallback applied
        return TranslatedContent(
            title=final_title,
            description=final_description,
            language=translation.language,
        )

    def _get_original_title_if_language_matches(
        self, nfo_path: Path, preferred_language: str
    ) -> str | None:
        """Get original title if original language matches preferred language family.

        Args:
            nfo_path: Path to .nfo file to extract TMDB IDs from
            preferred_language: The preferred language code (e.g., "zh-CN")

        Returns:
            Original title if language families match, None otherwise
        """
        try:
            # Extract TMDB IDs to call the details API
            tmdb_ids = self._extract_tmdb_ids(nfo_path)
            if not tmdb_ids:
                return None

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

    def _write_translated_metadata(
        self, nfo_path: Path, translation: TranslatedContent
    ) -> None:
        """Write translated metadata to .nfo file.

        Args:
            nfo_path: Path to .nfo file to update
            translation: Translated content

        Raises:
            Exception: If write operation fails
        """
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Update title element
        title_element = root.find("title")
        if title_element is not None:
            title_element.text = translation.title

        # Update plot/description element
        plot_element = root.find("plot")
        if plot_element is not None:
            plot_element.text = translation.description

        # Write the updated XML back to file atomically
        # Use a temporary file to ensure atomic writes
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        try:
            # Configure XML formatting
            ET.indent(tree, space="  ", level=0)
            tree.write(temp_path, encoding="utf-8", xml_declaration=True, method="xml")

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
        """Select best translation based on language preferences.

        Args:
            all_translations: Dictionary of all available translations

        Returns:
            Selected metadata object or None if no preferred language found
        """
        for preferred_lang in self.settings.preferred_languages:
            if preferred_lang in all_translations:
                return all_translations[preferred_lang]
        return None

    def _get_original_content_from_backup(
        self, nfo_path: Path
    ) -> tuple[str, str] | None:
        """Get original content from backup file if available.

        Args:
            nfo_path: Path to current .nfo file

        Returns:
            Tuple of (original_title, original_description) if backup exists,
            None otherwise
        """
        if not self.settings.original_files_backup_dir:
            return None

        # Calculate backup path using same logic as _backup_original()
        relative_path = nfo_path.relative_to(self.settings.rewrite_root_dir)
        backup_path = self.settings.original_files_backup_dir / relative_path

        if backup_path.exists():
            try:
                return self._extract_original_content(backup_path)
            except Exception as e:
                logger.warning(f"Failed to read backup file {backup_path}: {e}")
                return None
        return None
