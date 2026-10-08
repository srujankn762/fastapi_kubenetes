from fastapi import FastAPI
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine

app = FastAPI(title="FastAPI Hello World", version="1.0.0")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello World from india karnataka"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/db-health")
def database_health():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.scalar_one()

        return {
            "status": "healthy",
            "database": "mysql",
            "connection": "successful",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )