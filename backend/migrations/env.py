from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import get_settings
from backend.app.db import models as db_models
from backend.app.db.base import Base

_ = db_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A caller that already chose a database wins. Alembic's own API lets a caller pass the
# target with `config.set_main_option("sqlalchemy.url", ...)`, and this module used to
# overwrite that with the configured DATABASE_URL unconditionally. Test fixtures that set
# the URL that way therefore ran their migrations against whatever the environment's
# settings pointed at -- in practice, staging -- with nothing in the output to say so.
# Falling back to settings keeps the ordinary `alembic upgrade head` behaviour intact.
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    config.set_main_option(
        "sqlalchemy.url",
        settings.database_url.get_secret_value().replace("%", "%%"),
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
