"""Main CLI entry point for sonarr-metadata-rewrite."""

import click

from sonarr_metadata import __version__
from sonarr_metadata.config import get_tmdb_api_key


@click.command()
@click.version_option(version=__version__)
def cli() -> None:
    """Sonarr Metadata Translation Layer.

    A long-running service that monitors Sonarr-generated .nfo files and
    overwrites them with TMDB translations in your desired language.
    """
    # Verify TMDB API key is available
    try:
        api_key = get_tmdb_api_key()
        click.echo("🚀 Starting Sonarr Metadata Translation Layer...")
        click.echo(f"✅ TMDB API key loaded (ending in ...{api_key[-4:]})")
        click.echo("Service functionality not yet implemented")
    except ValueError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        raise click.Abort() from e


if __name__ == "__main__":
    cli()
