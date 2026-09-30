# Local fake-provider service only. Production digest pinning is a later milestone.
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements-local.lock /app/requirements-local.lock
RUN pip install --no-cache-dir -r requirements-local.lock
COPY src/ /app/src/
COPY infra/postgres/ /app/infra/postgres/
RUN useradd --uid 10001 --create-home lab && mkdir /data && chown lab:lab /data
USER 10001:10001
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "llm_regression_lab.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
