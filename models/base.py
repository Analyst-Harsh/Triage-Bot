from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in `models/` -- currently
    just `TriageRun`, but centralizing this now avoids each new model
    picking its own base.

    Maps `Mapped[datetime]` to a timezone-aware Postgres column by default:
    every write in this codebase uses `datetime.now(UTC)` (aware), and
    without this the default `DateTime()` type silently drops the tzinfo on
    write, so reads come back naive and break arithmetic against other aware
    datetimes."""

    type_annotation_map: ClassVar[dict[type, DateTime]] = {datetime: DateTime(timezone=True)}
