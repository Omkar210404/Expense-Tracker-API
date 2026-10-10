"""The Alembic migration and the models must describe the same schema."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.database import Base, make_engine

ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def describe(engine) -> dict:
    """Everything the inspector can tell about each table, in a comparable form."""
    inspector = inspect(engine)
    schema = {}
    for table in sorted(inspector.get_table_names()):
        if table == "alembic_version":
            continue
        schema[table] = {
            "columns": sorted(
                (column["name"], str(column["type"]), column["nullable"], column["primary_key"])
                for column in inspector.get_columns(table)
            ),
            "foreign_keys": sorted(
                (
                    key["name"],
                    tuple(key["constrained_columns"]),
                    key["referred_table"],
                    tuple(key["referred_columns"]),
                    key.get("options", {}).get("ondelete"),
                )
                for key in inspector.get_foreign_keys(table)
            ),
            "unique": sorted(
                (constraint["name"], tuple(constraint["column_names"]))
                for constraint in inspector.get_unique_constraints(table)
            ),
            "checks": sorted(
                (constraint["name"], constraint["sqltext"])
                for constraint in inspector.get_check_constraints(table)
            ),
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table)
            ),
        }
    return schema


@pytest.fixture
def migrated_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    return url


def test_migration_creates_the_same_schema_as_the_models(tmp_path, migrated_url):
    migrated = make_engine(migrated_url)
    from_models = make_engine(f"sqlite:///{(tmp_path / 'models.db').as_posix()}")
    Base.metadata.create_all(from_models)
    try:
        expected = describe(from_models)
        assert set(expected) == {"users", "categories", "expenses", "budgets"}
        assert describe(migrated) == expected
    finally:
        migrated.dispose()
        from_models.dispose()


def test_autogenerate_finds_nothing_left_to_migrate(migrated_url):
    engine = make_engine(migrated_url)
    try:
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert differences == []
    finally:
        engine.dispose()


def test_downgrade_removes_every_table(migrated_url):
    command.downgrade(alembic_config(migrated_url), "base")

    engine = make_engine(migrated_url)
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()
