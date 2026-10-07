from fastapi import FastAPI


app = FastAPI(title="FastAPI Hello World", version="1.0.0")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello World from india karnataka ind"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
