from enum import Enum

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit names so alembic autogenerate diffs stay stable (AGENTS.md §10).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_values(enum_class: type[Enum]) -> list[str]:
    # SQLAlchemy's default is enum .name; persisting .value keeps DB rows equal
    # to the API's wire values ("idle", not "IDLE") — AGENTS.md §2.
    return [str(member.value) for member in enum_class]
