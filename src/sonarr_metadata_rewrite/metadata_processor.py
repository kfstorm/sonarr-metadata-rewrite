"""Complete metadata file processing unit."""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from sonarr_metadata_rewrite.config import Settings
from sonarr_metadata_rewrite.models import (
    ProcessResult,
    TmdbIds,
    TranslatedContent,
)
from sonarr_metadata_rewrite.translator import Translator


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
            if not selected_translation:
                preferred_langs = ", ".join(self.settings.preferred_languages)
                available_langs = (
                    ", ".join(sorted(all_translations.keys()))
                    if all_translations
                    else "none"
                )
                return ProcessResult(
                    success=False,  # No work was accomplished
                    file_path=nfo_path,
                    message=(
                        f"File unchanged - no translation available in preferred "
                        f"languages [{preferred_langs}]. Available: [{available_langs}]"
                    ),
                    tmdb_ids=tmdb_ids,
                    translations_found=bool(all_translations),
                    file_modified=False,
                    selected_language=None,
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

        if tmdb_id is None:
            return None

        # Determine if this is a series or episode file
        if root.tag == "tvshow":
            # Series file
            return TmdbIds(series_id=tmdb_id)
        elif root.tag == "episodedetails":
            # Episode file - extract season and episode numbers
            season_element = root.find("season")
            episode_element = root.find("episode")

            if season_element is not None and episode_element is not None:
                season_text = season_element.text
                episode_text = episode_element.text
                if season_text is not None and episode_text is not None:
                    season = int(season_text.strip())
                    episode = int(episode_text.strip())
                    return TmdbIds(series_id=tmdb_id, season=season, episode=episode)
                else:
                    return None
            else:
                # Missing season/episode information
                return None
        else:
            # Unknown file type
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
