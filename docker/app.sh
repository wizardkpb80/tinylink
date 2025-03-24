#!/bin/bash


alembic upgrade head

#cd src

gunicorn src.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind=fastapi_app:8000