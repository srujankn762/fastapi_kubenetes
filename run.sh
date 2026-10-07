#!/bin/bash

# Stop the script immediately if any command fails
set -e

# Stop containers created by this Docker Compose project
# --remove-orphans removes old containers that are no longer defined in docker-compose.yml
docker compose down --remove-orphans

# Build the FastAPI image and start all services
# This will start both FastAPI and MySQL
docker compose up --build