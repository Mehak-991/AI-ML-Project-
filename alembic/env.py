"""Alembic migration environment wired to the application's settings and metadata."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.database.models import Base

config = context.config

if config.config_file_name is not None:
    # Keep loggers created before migrations (e.g. app.*) working when run in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
if settings.DATABASE_URL is None:
    raise RuntimeError("DATABASE_URL must be set to run migrations (see .env.example).")
# Escape '%' so configparser interpolation does not mangle URL-encoded passwords.
config.set_main_option(
    "sqlalchemy.url", settings.DATABASE_URL.get_secret_value().replace("%", "%%")
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
