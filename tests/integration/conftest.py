"""Integration test configuration and fixtures."""

import os
import socket
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.integration.fixtures.container_manager import ContainerManager
from tests.integration.fixtures.radarr_client import RadarrClient
from tests.integration.fixtures.sonarr_client import SonarrClient

# Test API key used for integration tests
TEST_API_KEY = "testkey12345678901234567890"


def _write_arr_config(config_dir: Path, port: int, instance_name: str) -> None:
    """Write common LinuxServer Arr config."""
    (config_dir / "config.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<Config>
  <Port>{port}</Port>
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
  <InstanceName>{instance_name}</InstanceName>
</Config>""")


@contextmanager
def _temporary_arr_config(
    prefix: str, port: int, instance_name: str
) -> Generator[Path]:
    """Create temporary Arr config with common LinuxServer settings."""
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        config_dir = Path(temp_dir)
        _write_arr_config(config_dir, port, instance_name)
        yield config_dir


def _find_free_port() -> int:
    """Reserve an available local TCP port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_handle:
        socket_handle.bind(("", 0))
        return int(socket_handle.getsockname()[1])


def _arr_environment() -> dict[str, str]:
    """Return LinuxServer container user and timezone settings."""
    return {
        "TZ": "UTC",
        "PUID": str(os.getuid()),
        "PGID": str(os.getgid()),
    }


def _arr_extra_args(container_manager: ContainerManager) -> list[str]:
    """Return container runtime-specific arguments for Arr images."""
    return ["--userns=keep-id"] if container_manager.runtime == "podman" else []


def _start_arr_container(
    container_manager: ContainerManager,
    image: str,
    name_prefix: str,
    container_port: int,
    media_root: Path,
    media_path: str,
    config_dir: Path,
) -> int:
    """Start an Arr container and return its mapped local port."""
    free_port = _find_free_port()
    container_manager.run_container(
        image=image,
        name=f"{name_prefix}-{free_port}",
        ports={container_port: free_port},
        volumes={
            str(media_root): media_path,
            str(config_dir): "/config",
        },
        environment=_arr_environment(),
        extra_args=_arr_extra_args(container_manager),
    )
    return free_port


@pytest.fixture(scope="session")
def temp_sonarr_media_root() -> Generator[Path]:
    """Create session-wide temporary media directory for Sonarr tests."""
    with tempfile.TemporaryDirectory(prefix="sonarr_media_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(scope="session")
def temp_radarr_media_root() -> Generator[Path]:
    """Create session-wide temporary media directory for Radarr tests."""
    with tempfile.TemporaryDirectory(prefix="radarr_media_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(scope="session")
def temp_sonarr_config_dir() -> Generator[Path]:
    """Create temporary config directory for Sonarr container."""
    with _temporary_arr_config("sonarr_config_", 8989, "Sonarr (Test)") as config_dir:
        yield config_dir


@pytest.fixture(scope="session")
def container_manager() -> Generator[ContainerManager]:
    """Create container manager with automatic cleanup."""
    with ContainerManager() as manager:
        yield manager


@pytest.fixture(scope="session")
def sonarr_container(
    container_manager: ContainerManager,
    temp_sonarr_media_root: Path,
    temp_sonarr_config_dir: Path,
) -> Generator[SonarrClient]:
    """Start Sonarr container and return configured client."""
    free_port = _start_arr_container(
        container_manager,
        image="docker.io/linuxserver/sonarr:latest",
        name_prefix="sonarr-test",
        container_port=8989,
        media_root=temp_sonarr_media_root,
        media_path="/tv",
        config_dir=temp_sonarr_config_dir,
    )

    # Create and configure client with the API key from our config
    base_url = f"http://localhost:{free_port}"
    client = SonarrClient(base_url, api_key=TEST_API_KEY)

    # Wait for Sonarr to be ready (Sonarr takes longer to start up)
    print("Waiting for Sonarr API to be ready...")
    if not client.wait_for_ready(max_attempts=30, delay=1.0):
        raise RuntimeError("Sonarr failed to become ready within 30 seconds")

    # Only start streaming output after Sonarr is confirmed ready
    container_manager.start_streaming()

    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def configured_sonarr_container(sonarr_container: SonarrClient) -> SonarrClient:
    """Configure Sonarr metadata settings once per session."""
    print("Configuring Sonarr metadata settings for session...")
    metadata_config_success = sonarr_container.configure_metadata_settings()
    if not metadata_config_success:
        raise RuntimeError("Failed to configure metadata settings")
    print("Metadata settings configured successfully")
    return sonarr_container


@pytest.fixture(scope="session")
def temp_radarr_config_dir() -> Generator[Path]:
    """Create temporary config directory for Radarr container."""
    with _temporary_arr_config("radarr_config_", 7878, "Radarr (Test)") as config_dir:
        yield config_dir


@pytest.fixture(scope="session")
def radarr_container(
    temp_radarr_media_root: Path,
    temp_radarr_config_dir: Path,
) -> Generator[RadarrClient]:
    """Start Radarr container and return configured client."""
    with ContainerManager() as manager:
        free_port = _start_arr_container(
            manager,
            image="docker.io/linuxserver/radarr:latest",
            name_prefix="radarr-test",
            container_port=7878,
            media_root=temp_radarr_media_root,
            media_path="/movies",
            config_dir=temp_radarr_config_dir,
        )
        client = RadarrClient(f"http://localhost:{free_port}", api_key=TEST_API_KEY)
        if not client.wait_for_ready(max_attempts=30, delay=1.0):
            raise RuntimeError("Radarr failed to become ready within 30 seconds")
        manager.start_streaming()
        try:
            yield client
        finally:
            client.close()
