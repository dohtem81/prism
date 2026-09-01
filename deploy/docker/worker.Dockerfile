FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Task routing sends translation jobs to translation.requested.q, so the worker must consume it explicitly.
CMD ["celery", "-A", "services.worker.app.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "celery,translation.requested.q"]
