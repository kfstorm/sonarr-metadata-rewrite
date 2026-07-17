"""Integration test configuration and fixtures."""

import os
import socket
import tempfile
from collections.abc import Generator
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

        _write_arr_config(
            temp_path,
            port=8989,
            instance_name="Sonarr (Test)",
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
def temp_radarr_config_dir() -> Generator[Path, None, None]:
    """Create temporary config directory for Radarr container."""
    with tempfile.TemporaryDirectory(prefix="radarr_config_") as temp_dir:
        temp_path = Path(temp_dir)
        _write_arr_config(temp_path, port=7878, instance_name="Radarr (Test)")
        yield temp_path


@pytest.fixture(scope="session")
def radarr_container(
    temp_media_root: Path,
    temp_radarr_config_dir: Path,
) -> Generator[RadarrClient, None, None]:
    """Start Radarr container and return configured client."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        free_port = sock.getsockname()[1]

    with ContainerManager() as manager:
        extra_args = ["--userns=keep-id"] if manager.runtime == "podman" else []
        manager.run_container(
            image="docker.io/linuxserver/radarr:latest",
            name=f"radarr-test-{free_port}",
            ports={7878: free_port},
            volumes={
                str(temp_media_root): "/movies",
                str(temp_radarr_config_dir): "/config",
            },
            environment={
                "TZ": "UTC",
                "PUID": str(os.getuid()),
                "PGID": str(os.getgid()),
            },
            extra_args=extra_args,
        )
        client = RadarrClient(f"http://localhost:{free_port}", api_key=TEST_API_KEY)
        if not client.wait_for_ready(max_attempts=30, delay=1.0):
            raise RuntimeError("Radarr failed to become ready within 30 seconds")
        manager.start_streaming()
        try:
            yield client
        finally:
            client.close()
