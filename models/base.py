from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in `models/` -- currently
    just `TriageRun`, but centralizing this now avoids each new model
    picking its own base."""
