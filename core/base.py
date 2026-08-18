"""AETHERIS base Pydantic model — all schemas inherit from this.

Per ADR-001: extra="ignore" by default. Critical contracts opt into
extra="forbid" explicitly.
"""

from pydantic import BaseModel, ConfigDict


class AetherisBaseModel(BaseModel):
    """All AETHERIS schemas inherit from this.

    Critical contracts (RFC-001 §4) opt into ``extra="forbid"`` via
    ``model_config = ConfigDict(extra="forbid")``.
    """

    model_config = ConfigDict(extra="ignore")
