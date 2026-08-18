"""002 - add title to conversation sessions.

Task #4 adds the optional ``title`` column to ``conversation_sessions`` so
existing databases can match ``core.models.ConversationSessionRecord``.

Revision ID: 002_add_title
Revises: 001_initial_schema
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_title"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_sessions",
        sa.Column("title", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_sessions", "title")
