"""Integration test configuration and fixtures."""

import os
import socket
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.integration.fixtures.container_manager import ContainerManager
from tests.integration.fixtures.sonarr_client import SonarrClient
from tests.integration.test_helpers import setup_series_with_nfos

# Test API key used for integration tests
TEST_API_KEY = "testkey12345678901234567890"


@pytest.fixture(scope="session")
def temp_media_root() -> Generator[Path, None, None]:
    """Create session-wide temporary media directory for Sonarr container and tests."""
    with tempfile.TemporaryDirectory(prefix="sonarr_media_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(scope="session")
def temp_config_dir() -> Generator[Path, None, None]:
    """Create temporary config directory for Sonarr container."""
    with tempfile.TemporaryDirectory(prefix="sonarr_config_") as temp_dir:
        temp_path = Path(temp_dir)

        # Create config.xml inside the directory
        config_file = temp_path / "config.xml"
        config_file.write_text(
            f"""<?xml version="1.0" encoding="utf-8"?>
<Config>
  <Port>8989</Port>
  <SslPort>9898</SslPort>
  <EnableSsl>False</EnableSsl>
  <LaunchBrowser>False</LaunchBrowser>
  <AuthenticationMethod>None</AuthenticationMethod>
  <AuthenticationRequired>DisabledForLocalAddresses</AuthenticationRequired>
  <Branch>main</Branch>
  <ApiKey>{TEST_API_KEY}</ApiKey>
  <SslCertPath></SslCertPath>
  <SslCertPassword></SslCertPassword>
  <UrlBase></UrlBase>
  <UpdateMechanism>Docker</UpdateMechanism>
  <InstanceName>Sonarr (Test)</InstanceName>
</Config>"""
        )
        yield temp_path


@pytest.fixture(scope="session")
def container_manager() -> Generator[ContainerManager, None, None]:
    """Create container manager with automatic cleanup."""
    with ContainerManager() as manager:
        yield manager


@pytest.fixture(scope="session")
def sonarr_container(
    container_manager: ContainerManager,
    temp_media_root: Path,
    temp_config_dir: Path,
) -> Generator[SonarrClient, None, None]:
    """Start Sonarr container and return configured client."""
    # Find a free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        free_port = s.getsockname()[1]

    # Always set PUID/PGID for LinuxServer images

    env = {
        "TZ": "UTC",
        "PUID": str(os.getuid()),
        "PGID": str(os.getgid()),
    }

    # Set container runtime-specific arguments
    extra_args = []
    if container_manager.runtime == "podman":
        # Use keep-id to maintain consistent UID mapping with PUID/PGID
        extra_args.append("--userns=keep-id")

    # Start Sonarr container (runs in foreground with output streaming)
    container_name = f"sonarr-test-{free_port}"
    container_manager.run_container(
        image="docker.io/linuxserver/sonarr:latest",
        name=container_name,
        ports={8989: free_port},
        volumes={
            str(temp_media_root): "/tv",
            str(temp_config_dir): "/config",
        },
        environment=env,
        extra_args=extra_args,
    )

    # Create and configure client with the API key from our config
    base_url = f"http://localhost:{free_port}"
    client = SonarrClient(base_url, api_key=TEST_API_KEY)

    # Wait for Sonarr to be ready (Sonarr takes longer to start up)
    print("Waiting for Sonarr API to be ready...")
    if not client.wait_for_ready(max_attempts=30, delay=1.0):
        raise RuntimeError("Sonarr failed to become ready within 30 seconds")

    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def unconfigured_sonarr_container(sonarr_container: SonarrClient) -> SonarrClient:
    """Sonarr container with no metadata providers enabled by default."""
    print("Configuring Sonarr to disable all metadata providers by default...")
    metadata_config_success = sonarr_container.configure_metadata_settings()
    if not metadata_config_success:
        raise RuntimeError("Failed to configure metadata settings")
    print("All metadata providers disabled by default")
    return sonarr_container


@pytest.fixture
def metadata_provider_names(unconfigured_sonarr_container: SonarrClient) -> list[str]:
    """Get list of available metadata provider names from Sonarr API."""
    providers = unconfigured_sonarr_container.get_metadata_providers()
    return [provider["name"] for provider in providers]


@pytest.fixture
def prepared_series_with_nfos(
    unconfigured_sonarr_container: SonarrClient,
    temp_media_root: Path,
) -> Generator[tuple[Path, list[Path], dict[Path, Path], int], None, None]:
    """Prepare series structure without initial .nfo files.

    Note: This fixture does not enable any metadata providers and does not 
    generate .nfo files initially. Tests must explicitly enable the provider 
    they want to test and generate .nfo files as needed.

    Returns:
        Tuple of (series_path, empty_nfo_list, empty_backup_mapping, series_id)
    """
    series, nfo_files, original_backups = setup_series_with_nfos(
        unconfigured_sonarr_container, temp_media_root
    )

    try:
        series_path = temp_media_root / series.slug
        yield series_path, nfo_files, original_backups, series.id
    finally:
        series.__exit__(None, None, None)
