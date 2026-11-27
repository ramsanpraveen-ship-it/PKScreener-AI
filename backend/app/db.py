import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://localhost/pkscreener_ai",
)


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database():
    from . import models  # ensure model metadata is registered
    Base.metadata.create_all(bind=engine)


def get_db():
    from fastapi import HTTPException
    from sqlalchemy.exc import SQLAlchemyError

    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("select 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Local PostgreSQL is unavailable") from error
    try:
        yield db
    finally:
        db.close()
