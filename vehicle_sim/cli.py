"""CLI entry point for the vehicle simulator."""

from __future__ import annotations

import asyncio

import click

from .geo import CITIES
from .simulator import simulate
from .writers.api_writer import ApiWriter
from .writers.file_writer import FileWriter

CITY_NAMES = list(CITIES.keys())


@click.group()
def cli() -> None:
    """Pulse vehicle simulation toolkit."""


@cli.command()
@click.option("-n", "--vehicles", required=True, type=int, help="Number of vehicles to simulate.")
@click.option(
    "--city",
    type=click.Choice(CITY_NAMES, case_sensitive=False),
    default=None,
    help="Restrict vehicles to a specific city. Default: random across all cities.",
)
@click.option("--ping-min", default=1.0, type=float, help="Minimum ping interval in seconds.")
@click.option("--ping-max", default=5.0, type=float, help="Maximum ping interval in seconds.")
@click.option("--drop-rate", default=0.05, type=float, help="Probability of a dropped ping (0.0-1.0).")
@click.option(
    "--writer",
    "writer_type",
    type=click.Choice(["file", "api"], case_sensitive=False),
    default="file",
    help="Position writer backend.",
)
@click.option("--log-dir", default="logs", help="Directory for log files (file writer).")
@click.option("--max-file-mb", default=10, type=int, help="Max log file size in MB before rotation.")
@click.option("--api-endpoint", default="http://localhost:8888/api/position", help="API endpoint (api writer).")
@click.option("--api-batch-size", default=50, type=int, help="Batch size for API writes.")
@click.option("--radius", default=None, type=float, help="Radius in km from city center to distribute vehicles. Default: use full city bounding box.")
def run(
    vehicles: int,
    city: str | None,
    ping_min: float,
    ping_max: float,
    drop_rate: float,
    writer_type: str,
    log_dir: str,
    max_file_mb: int,
    api_endpoint: str,
    api_batch_size: int,
    radius: float | None,
) -> None:
    """Simulate N vehicles moving along real roads in US cities."""
    if writer_type == "file":
        writer = FileWriter(log_dir=log_dir, max_file_bytes=max_file_mb * 1024 * 1024)
        click.echo(f"[config] Writer: file -> {log_dir}/ (rotate at {max_file_mb} MB)")
    else:
        writer = ApiWriter(endpoint=api_endpoint, batch_size=api_batch_size)
        click.echo(f"[config] Writer: api -> {api_endpoint} (batch={api_batch_size})")

    city_label = city or "all cities"
    radius_label = f", Radius: {radius} km" if radius else ""
    click.echo(
        f"[config] Vehicles: {vehicles}, City: {city_label}{radius_label}, "
        f"Ping: {ping_min}-{ping_max}s, Drop: {drop_rate:.0%}"
    )

    asyncio.run(simulate(vehicles, writer, ping_min, ping_max, drop_rate, city, radius))


@cli.command()
@click.option("--port", default=8888, type=int, help="Server port.")
def serve(port: int) -> None:
    """Start the WebSocket relay server for the dashboard UI."""
    from .server import run_server
    run_server(port=port)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
