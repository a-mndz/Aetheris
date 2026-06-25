"""
SQLAlchemy database models for AMMRO.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class User(Base):
    """
    User database model.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
