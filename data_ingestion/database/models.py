from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[object] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="INGESTED", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="job")


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        UniqueConstraint("job_id", "normalized_key", name="uq_addresses_job_normalized_key"),
        Index("ix_addresses_job_id", "job_id"),
        Index("ix_addresses_address_id", "address_id"),
        Index("ix_addresses_terminal_id", "terminal_id"),
        Index("ix_addresses_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_uuid: Mapped[object] = mapped_column(UUID(as_uuid=True), default=uuid4, nullable=False)
    job_id: Mapped[object] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    raw_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    network_node: Mapped[str | None] = mapped_column(String(255), nullable=True)
    terminal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_layer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    validation_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_warnings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    job: Mapped[IngestionJob] = relationship(back_populates="addresses")


class NetworkAsset(Base):
    __tablename__ = "network_assets"
    __table_args__ = (Index("ix_network_assets_geometry", "geometry", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    asset_type: Mapped[str] = mapped_column(String(255), nullable=False)
    geometry: Mapped[object | None] = mapped_column(Geometry(srid=4326), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"))
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_valid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class DispatchQueue(Base):
    __tablename__ = "dispatch_queue"
    __table_args__ = (
        Index("ix_dispatch_status_created_at", "status", "created_at"),
        UniqueConstraint("address_id", name="uq_dispatch_address_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[object] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AgentTable(Base):
    """Registry of agent teams and their per-field color rules for map visualisation."""

    __tablename__ = "agent_tables"
    __table_args__ = (UniqueConstraint("agent_name", name="uq_agent_tables_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # color_rules: [{"field":"status","value":"qualified","color":"#22c55e","label":"Qualified"}, ...]
    color_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    results: Mapped[list["AgentResult"]] = relationship(
        back_populates="agent_table", cascade="all, delete-orphan"
    )


class AgentResult(Base):
    """Stores one agent team's processed output per address record."""

    __tablename__ = "agent_results"
    __table_args__ = (
        UniqueConstraint("agent_name", "address_id", name="uq_agent_results_agent_address"),
        Index("ix_agent_results_agent_name", "agent_name"),
        Index("ix_agent_results_job_id", "job_id"),
        Index("ix_agent_results_address_id", "address_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(
        String(100), ForeignKey("agent_tables.agent_name", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[object] = mapped_column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id"), nullable=False)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    agent_table: Mapped["AgentTable"] = relationship(back_populates="results")
