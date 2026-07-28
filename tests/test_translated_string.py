"""Legacy test-data construction for provenance-aware strings."""

from sonarr_metadata_rewrite.models import TranslatedString as ModelTranslatedString


class TranslatedString(ModelTranslatedString):
    """Build Translation Record test data from the former concise arguments."""

    def __init__(self, content: str, language: str) -> None:
        """Create translation test data with a source tag."""
        super().__init__(
            content=content,
            source="translation" if language not in {"unknown", "original"} else None,
            source_tag=None if language in {"unknown", "original"} else language,
        )

    @property
    def language(self) -> str:
        """Expose the old test assertion name while tests are migrated."""
        if self.source_tag is None:
            return "original"
        return self.source_tag
