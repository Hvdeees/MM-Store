"""Alembic runs this file for every migration command (upgrade, downgrade, revision --autogenerate)."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

# Autogenerate compares the database against these table definitions to write new migrations.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection") or create_engine(settings.database_url)
    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:
    # render_as_batch lets SQLite (which can't ALTER most columns) handle future migrations too.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
