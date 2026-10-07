# FastAPI Hello World

A minimal FastAPI application with a health check.

## Run locally

Install the dependencies and start the development server:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Build the Docker image

```bash
docker build -t fastapi-hello-world .
```

## Run the Docker container

```bash
docker run -p 8000:8000 fastapi-hello-world
```

## Test

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
```

Swagger documentation is available at:

http://localhost:8000/docs

Use this website to preview .yaml files

https://todiagram.com/editor
