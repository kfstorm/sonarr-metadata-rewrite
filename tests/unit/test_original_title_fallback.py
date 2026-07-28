"""Original Title fallback behavior."""

from pathlib import Path
from unittest.mock import Mock

from sonarr_metadata_rewrite.metadata_processor import MetadataProcessor
from sonarr_metadata_rewrite.models import (
    OriginalTitleDetails,
    TmdbIds,
    TranslatedContent,
    TranslatedString,
)
from sonarr_metadata_rewrite.translator import Translator
from tests.conftest import create_test_settings


def translation(tag: str, title: str, overview: str = "") -> TranslatedContent:
    """Build one Translation Record with explicit provenance."""
    return TranslatedContent(
        title=TranslatedString(content=title, source="translation", source_tag=tag),
        description=TranslatedString(
            content=overview, source="translation", source_tag=tag
        ),
        tagline=TranslatedString(content="", source="translation", source_tag=tag),
    )


def test_parser_preserves_empty_translation_record(translator: Translator) -> None:
    """A returned empty Translation Record remains available for selection."""
    result = translator._parse_api_translations(
        {"translations": [{"iso_639_1": "zh", "iso_3166_1": "CN", "data": None}]},
        "movie",
    )

    assert result["zh-CN"].title.content == ""
    assert result["zh-CN"].title.source == "translation"
    assert result["zh-CN"].title.source_tag == "zh-CN"


def test_empty_matching_record_selects_original_title_before_later_title(
    test_data_dir: Path,
) -> None:
    """Original Title occupies the matching empty record's preference position."""
    settings = create_test_settings(test_data_dir, preferred_languages="zh-CN,zh-TW")
    translator = Mock(spec=Translator)
    translator.get_original_details.return_value = OriginalTitleDetails(
        "zh", "捕风追影"
    )
    processor = MetadataProcessor(settings, translator)

    result = processor._select_preferred_translation(
        {
            "zh-CN": translation("zh-CN", "", "简体简介"),
            "zh-TW": translation("zh-TW", "捕風追影", "繁體簡介"),
        },
        TmdbIds(tmdb_id=1, media_type="movie"),
    )

    assert result is not None
    assert result.title.content == "捕风追影"
    assert result.title.source == "original_title"
    assert result.title.source_tag == "zh"
    assert result.title.selection_tag == "zh-CN"
    assert result.description.content == "简体简介"
    assert result.description.selection_tag == "zh-CN"


def test_original_title_fallback_noop_message_includes_provenance(
    test_data_dir: Path,
) -> None:
    """An unchanged file still exposes Original Title fallback provenance."""
    processor = MetadataProcessor(
        create_test_settings(test_data_dir), Mock(spec=Translator)
    )
    message = processor._build_unchanged_message(
        TranslatedContent(
            title=TranslatedString(
                content="捕风追影",
                source="original_title",
                source_tag="zh",
                selection_tag="zh-CN",
            ),
            description=TranslatedString(content=""),
        )
    )

    assert message == (
        "Content already matches preferred translation "
        '(title: Original Title "捕风追影" [zh], fallback for zh-CN)'
    )
