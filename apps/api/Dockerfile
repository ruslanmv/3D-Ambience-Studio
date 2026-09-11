FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY apps/api /app/apps/api
COPY schemas /app/schemas
RUN pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/apps/api
CMD ["uvicorn", "ambience.main:app", "--host", "0.0.0.0", "--port", "8000"]
