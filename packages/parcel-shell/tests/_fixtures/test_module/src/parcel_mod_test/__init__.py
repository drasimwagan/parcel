from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, Text

from parcel_sdk import Module, Permission

metadata = MetaData(schema="mod_test")

items = Table(
    "items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
)

module = Module(
    name="test",
    version="0.1.0",
    permissions=(Permission("test.read", "Read test items"),),
    capabilities=("http_egress",),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
)
