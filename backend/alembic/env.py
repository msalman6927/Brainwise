from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, make_url, pool
from sqlalchemy.engine import Connection

from backend.core.config import settings
from backend.db.base import Base
from backend.models import *  # noqa: F403 — registers every table for autogenerate

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _dsn() -> str:
    # Same provider-agnostic rewrite as db/session.py; alembic.ini keeps only a
    # placeholder url so no credential is ever committed. Migrations use the
    # *sync* psycopg engine: psycopg cannot run async on Windows' default
    # ProactorEventLoop, and DDL does not need async.
    return (
        make_url(settings.database_url)
        .set(drivername="postgresql+psycopg")
        .render_as_string(hide_password=False)
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _dsn()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
