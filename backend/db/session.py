from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from core.config import DatabaseConfigs, DatabasePoolConfigs


engine = create_engine(
    DatabaseConfigs.DATABASE_URL,
    pool_size=DatabasePoolConfigs.POOL_SIZE,
    max_overflow=DatabasePoolConfigs.MAX_OVERFLOW,
    pool_timeout=DatabasePoolConfigs.POOL_TIMEOUT,
    pool_recycle=DatabasePoolConfigs.POOL_RECYCLE,
    pool_pre_ping=DatabasePoolConfigs.POOL_PRE_PING,
    echo=DatabasePoolConfigs.ECHO,
    connect_args={"sslmode": "require"} if "sslmode=require" in DatabaseConfigs.DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


