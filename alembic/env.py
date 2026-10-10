"""Alembic environment. Run with `alembic upgrade head`."""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import DatabaseSettings
from app.database import Base, is_sqlite, make_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# A URL set on the config (the tests do this) wins over the environment.
database_url = config.get_main_option("sqlalchemy.url") or DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """Write the SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite(database_url),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot alter most things in place; batch mode rebuilds the table.
            render_as_batch=is_sqlite(database_url),
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
