from __future__ import annotations

import json
from pathlib import Path

import click

from data_ingestion.config.settings import get_settings
from data_ingestion.database.db import init_db, session_scope
from data_ingestion.database.repositories import DispatchRepository, IngestionRepository
from data_ingestion.dispatcher import SequentialDispatcher
from data_ingestion.ingestion_service import IngestionService
from data_ingestion.logging_config import configure_logging


@click.group()
def cli() -> None:
    """FTTH Data Ingestion CLI."""
    settings = get_settings()
    configure_logging(settings.log_level)


@cli.command("init-db")
def init_db_command() -> None:
    """Initialize PostgreSQL/PostGIS schema."""
    init_db()
    click.echo("Database schema initialized.")


@cli.command("ingest")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--customer-id", default=None, help="Customer/account identifier for lineage.")
@click.option("--init/--no-init", "auto_init", default=True, help="Create DB schema before ingesting.")
def ingest_command(file_path: Path, customer_id: str | None, auto_init: bool) -> None:
    """Ingest a CSV, Excel, KML, or KMZ file."""
    settings = get_settings()
    if auto_init:
        init_db()

    effective_customer_id = customer_id or settings.default_customer_id
    with session_scope() as session:
        repo = IngestionRepository(session)
        service = IngestionService(repo)
        result = service.ingest_file(file_path, customer_id=effective_customer_id)

    click.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


@cli.command("dispatch")
@click.option("--limit", default=None, type=int, help="Maximum pending records to dispatch.")
def dispatch_command(limit: int | None) -> None:
    """Sequentially dispatch pending records to downstream agents."""
    settings = get_settings()
    effective_limit = limit or settings.dispatch_batch_size
    init_db()

    with session_scope() as session:
        repo = DispatchRepository(session)
        dispatcher = SequentialDispatcher(repo)
        processed = dispatcher.dispatch_pending(limit=effective_limit)

    click.echo(f"Dispatched {processed} record(s).")


if __name__ == "__main__":
    cli()
