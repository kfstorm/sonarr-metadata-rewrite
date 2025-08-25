"""Main CLI entry point for sonarr-metadata-rewrite."""

import logging
import signal
import sys
import time

import click

from sonarr_metadata_rewrite import __version__
from sonarr_metadata_rewrite.config import get_settings
from sonarr_metadata_rewrite.rewrite_service import RewriteService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


@click.command()
@click.version_option(version=__version__)
def cli() -> None:
    """Sonarr Metadata Translation Layer.

    A long-running service that monitors Sonarr-generated .nfo files and
    overwrites them with TMDB translations in your desired language.
    """
    # Load configuration
    try:
        settings = get_settings()
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)

    click.echo("🚀 Starting Sonarr Metadata Translation Layer...")
    click.echo(f"✅ TMDB API key loaded (ending in ...{settings.tmdb_api_key[-4:]})")
    click.echo(f"📁 Monitoring directory: {settings.rewrite_root_dir}")
    click.echo(f"🌍 Preferred languages: {settings.preferred_languages}")

    # Create and start service
    service = RewriteService(settings)

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum: int, frame: object) -> None:
        logger.info("Received shutdown signal")
        service.stop()
        click.echo("👋 Service stopped gracefully")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start the service
    service.start()
    click.echo("✅ Service started successfully")
    click.echo("Press Ctrl+C to stop the service")

    # Keep the main thread alive
    try:
        while service.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    cli()
