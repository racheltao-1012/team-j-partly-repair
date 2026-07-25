FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN mkdir -p /app/storage

ENV PARTLY_API_URL=http://host.docker.internal:8420
ENV DATABASE_PATH=/app/storage/inspection.db
ENV PHOTO_STORAGE_PATH=/app/storage/photo-assessments

EXPOSE 8501

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8501"]
