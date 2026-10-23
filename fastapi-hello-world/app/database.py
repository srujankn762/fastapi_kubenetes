
import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Read the MySQL connection URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = URL.create(
        "mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        host=os.environ.get("DB_HOST", "mysql_database"),
        port=int(os.environ.get("DB_PORT", "3306")),
        database=os.environ["MYSQL_DATABASE"],
    ).render_as_string(hide_password=False)


# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)


# Create database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# Base class for SQLAlchemy models
Base = declarative_base()


# Database dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
