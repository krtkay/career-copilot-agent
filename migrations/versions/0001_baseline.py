"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-01-15 00:00:00

This baseline creates the extensions and the full schema from the SQLModel metadata,
guaranteeing the migration never drifts from the ORM models. Subsequent, incremental
changes should use ``alembic revision --autogenerate`` which will diff against this
baseline.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlmodel import SQLModel

# Register models on the metadata.
import app.models  # noqa: F401

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    SQLModel.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind)
