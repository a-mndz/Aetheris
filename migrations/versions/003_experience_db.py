"""003 — Experience DB tables (RFC-004 §7, ADR-008, DEC-013).

Creates the two-table Experience DB: ``experience_operational`` (high-write,
short retention) and ``experience_learning`` (read-heavy, long retention).
Additive-first per ADR-008 — this migration only creates new tables and their
indexes; it touches no existing table.

Revision ID: 003_experience_db
Revises: 002_add_title
Create Date: 2026-07-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_experience_db"
down_revision: Union[str, None] = "002_add_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experience_operational",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("task_profile", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "prediction_actual_deltas",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("failure_class", sa.String(length=64), nullable=True),
        sa.Column("recovery_action", sa.String(length=64), nullable=True),
        sa.Column("replay_trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_experience_operational_prompt_fingerprint",
        "experience_operational",
        ["prompt_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_experience_operational_replay_trace_id",
        "experience_operational",
        ["replay_trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_experience_operational_created",
        "experience_operational",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "experience_learning",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prompt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("task_profile", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("task_graph_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("planner_version", sa.String(length=64), nullable=True),
        sa.Column("consensus_quality", sa.Float(), nullable=True),
        sa.Column("routing_quality", sa.Float(), nullable=True),
        sa.Column("user_satisfaction", sa.Float(), nullable=True),
        sa.Column(
            "graph_mutation_audit",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("replay_trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_experience_learning_prompt_fingerprint",
        "experience_learning",
        ["prompt_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_experience_learning_task_graph_fingerprint",
        "experience_learning",
        ["task_graph_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_experience_learning_replay_trace_id",
        "experience_learning",
        ["replay_trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_experience_learning_created",
        "experience_learning",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_learning_created", table_name="experience_learning"
    )
    op.drop_index(
        "ix_experience_learning_replay_trace_id", table_name="experience_learning"
    )
    op.drop_index(
        "ix_experience_learning_task_graph_fingerprint",
        table_name="experience_learning",
    )
    op.drop_index(
        "ix_experience_learning_prompt_fingerprint",
        table_name="experience_learning",
    )
    op.drop_table("experience_learning")

    op.drop_index(
        "ix_experience_operational_created", table_name="experience_operational"
    )
    op.drop_index(
        "ix_experience_operational_replay_trace_id",
        table_name="experience_operational",
    )
    op.drop_index(
        "ix_experience_operational_prompt_fingerprint",
        table_name="experience_operational",
    )
    op.drop_table("experience_operational")
