import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project's root directory to the Python path
# This allows Alembic to find your 'models' package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import your Base and models here so Alembic's autogenerate can see them
from models.base import Base
from models.user.user import User
from models.usecase.usecase import UsecaseMetadata
from models.file_processing.file_metadata import FileMetadata
from models.file_processing.ocr_records import OCRInfo, OCROutputs
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
from models.generator.test_script import TestScript
from models.user.api_key import UserAPIKey

from core.config import DatabaseConfigs

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Overwrite the sqlalchemy.url in the alembic.ini with the one from our config
config.set_main_option("sqlalchemy.url", DatabaseConfigs.DATABASE_URL)

# Set the metadata for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()