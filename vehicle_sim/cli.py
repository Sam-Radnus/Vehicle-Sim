"""CLI entry point for the vehicle simulator."""

from __future__ import annotations

import asyncio

import click

from .simulator import simulate
from .writers.api_writer import ApiWriter
from .writers.file_writer import FileWriter


@click.command()
@click.option("-n", "--vehicles", required=True, type=int, help="Number of vehicles to simulate.")
@click.option("--min-dist", default=50.0, type=float, help="Minimum src-dst distance in km.")
@click.option("--max-dist", default=150.0, type=float, help="Maximum src-dst distance in km.")
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
@click.option("--api-endpoint", default="http://localhost:8080/api/position", help="API endpoint (api writer).")
@click.option("--api-batch-size", default=50, type=int, help="Batch size for API writes.")
def main(
    vehicles: int,
    min_dist: float,
    max_dist: float,
    ping_min: float,
    ping_max: float,
    drop_rate: float,
    writer_type: str,
    log_dir: str,
    max_file_mb: int,
    api_endpoint: str,
    api_batch_size: int,
) -> None:
    """Simulate N vehicles moving from random source to destination."""
    if writer_type == "file":
        writer = FileWriter(log_dir=log_dir, max_file_bytes=max_file_mb * 1024 * 1024)
        click.echo(f"[config] Writer: file -> {log_dir}/ (rotate at {max_file_mb} MB)")
    else:
        writer = ApiWriter(endpoint=api_endpoint, batch_size=api_batch_size)
        click.echo(f"[config] Writer: api -> {api_endpoint} (batch={api_batch_size})")

    click.echo(
        f"[config] Vehicles: {vehicles}, Distance: {min_dist}-{max_dist} km, "
        f"Ping: {ping_min}-{ping_max}s, Drop: {drop_rate:.0%}"
    )

    asyncio.run(simulate(vehicles, writer, min_dist, max_dist, ping_min, ping_max, drop_rate))


if __name__ == "__main__":
    main()
