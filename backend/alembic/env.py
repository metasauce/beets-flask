"""Alembic environment configuration for beets-flask database migrations.

This module configures Alembic to use the beets-flask database configuration
for both autogenerate support and runtime migrations.
"""

from alembic import context

# Import beets_flask database components
from beets_flask.config.flask_config import get_flask_config
from beets_flask.database.models.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# add your model's MetaData object here
# for 'autogenerate' support
# This is crucial for autogenerate to detect model changes
target_metadata = Base.metadata


def get_url() -> str:
    """Get the database URL from beets-flask configuration.

    Returns
    -------
        str: The database connection URI.

    """
    flask_config = get_flask_config()
    return flask_config["DATABASE_URI"]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    from sqlalchemy import engine_from_config, pool

    # Get the database URL from beets-flask config
    url = get_url()

    # Create engine configuration with our URL
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
