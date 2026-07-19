"""Unit tests for integration fixture lifecycle and readiness behavior."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.integration.fixtures.radarr_client import RadarrClient
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import MovieWithNfos, SeriesWithNfos


def immediate_retry(**_kwargs: Any) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Retry twice without sleeping for deterministic fixture tests."""

    def decorator(function: Callable[[], Any]) -> Callable[[], Any]:
        def wrapper() -> Any:
            try:
                return function()
            except AssertionError:
                return function()

        return wrapper

    return decorator


@pytest.mark.parametrize("client_class", [SonarrClient, RadarrClient])
def test_arr_command_failure_is_not_retried(
    client_class: type[SonarrClient] | type[RadarrClient],
) -> None:
    """Fail fast when either Arr platform reports a terminal command failure."""
    client = client_class("http://arr.invalid")
    try:
        with pytest.raises(RuntimeError, match="ended with status failed"):
            client._assert_command_completed(
                {"id": 12, "status": "failed", "message": "scan failed"}
            )
    finally:
        client.close()


@pytest.mark.parametrize(
    ("client_class", "provider", "is_radarr"),
    [
        (
            RadarrClient,
            {
                "id": 4,
                "name": "Kodi (XMBC) / Emby",
                "fields": [
                    {"name": "movieMetadata", "value": False},
                    {"name": "movieImages", "value": False},
                    {"name": "UseMovieNfo", "value": False},
                ],
            },
            True,
        ),
        (
            SonarrClient,
            {
                "id": 5,
                "name": "Kodi (XBMC)",
                "fields": [
                    {"name": "seriesMetadata", "value": False},
                    {"name": "episodeMetadata", "value": False},
                    {"name": "episodeImages", "value": False},
                    {"name": "seriesImages", "value": False},
                    {"name": "seasonImages", "value": False},
                ],
            },
            False,
        ),
    ],
)
def test_arr_metadata_configuration_waits_for_provider(
    client_class: type[RadarrClient] | type[SonarrClient],
    provider: dict[str, Any],
    is_radarr: bool,
) -> None:
    """Wait until either Arr platform finishes registering metadata providers."""
    client = client_class("http://arr.invalid")
    responses = [
        httpx.Response(200, json=[], request=httpx.Request("GET", "http://arr")),
        httpx.Response(
            200, json=[provider], request=httpx.Request("GET", "http://arr")
        ),
        httpx.Response(202, request=httpx.Request("PUT", "http://arr")),
    ]
    make_request = MagicMock(side_effect=responses)

    try:
        with (
            patch("tests.integration.fixtures.arr_client.retry", immediate_retry),
            patch.object(client, "_make_request", make_request),
        ):
            if is_radarr:
                assert isinstance(client, RadarrClient)
                assert client.configure_metadata_settings(use_movie_nfo=True)
            else:
                assert isinstance(client, SonarrClient)
                assert client.configure_metadata_settings()
    finally:
        client.close()

    update_payload = cast(dict[str, Any], make_request.call_args.kwargs["json"])
    assert update_payload["enable"] is True
    assert all(field["value"] is True for field in update_payload["fields"])


def test_series_setup_failure_removes_added_series(tmp_path: Path) -> None:
    """Clean up Sonarr resource when setup fails inside __enter__."""
    sonarr = MagicMock(spec=SonarrClient)
    manager = MagicMock()
    manager.__enter__.return_value = manager
    manager.slug = "series"
    manager.id = 7
    sonarr.trigger_disk_scan.return_value = False

    with (
        patch("tests.integration.test_helpers.SeriesManager", return_value=manager),
        pytest.raises(RuntimeError, match="Failed to trigger disk scan"),
    ):
        SeriesWithNfos(sonarr, tmp_path, 1, []).__enter__()

    manager.__exit__.assert_called_once()


def test_movie_setup_failure_removes_added_movie(tmp_path: Path) -> None:
    """Clean up Radarr resource when setup fails inside __enter__."""
    radarr = MagicMock(spec=RadarrClient)
    manager = MagicMock()
    manager.__enter__.return_value = manager
    manager.directory = tmp_path / "movie"
    manager.title = "Movie"
    manager.data = {"year": 2000}
    manager.id = 8
    radarr.trigger_disk_scan.return_value = False

    with (
        patch("tests.integration.test_helpers.MovieManager", return_value=manager),
        patch("tests.integration.test_helpers.create_fake_movie_file"),
        pytest.raises(RuntimeError, match="Failed to trigger Radarr disk scan"),
    ):
        MovieWithNfos(radarr, tmp_path, 1, use_movie_nfo=True).__enter__()

    manager.__exit__.assert_called_once()
