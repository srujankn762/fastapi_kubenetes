# Use the lightweight Python 3.12 image as the base image
FROM python:3.12-slim


# Prevent Python from creating .pyc compiled bytecode files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1


# Set /app as the working directory inside the container
WORKDIR /app


# Copy requirements.txt from the build context into the container
COPY requirements.txt .


# Install Python dependencies without storing pip's download cache
RUN pip install --no-cache-dir -r requirements.txt


# Copy our FastAPI application code into /app/app inside the container
COPY app ./app


# Document that the application listens on port 8000
EXPOSE 8000


# Start the FastAPI application using Uvicorn when the container starts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]