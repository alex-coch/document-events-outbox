FROM python:3.11-slim-bookworm AS dependencies
WORKDIR /service
RUN pip install --no-cache-dir poetry==2.1.3
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
COPY pyproject.toml poetry.lock ./
RUN poetry sync --with test --no-root --no-interaction

FROM python:3.11-slim-bookworm
WORKDIR /service
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/service/.venv/bin:$PATH"
COPY --from=dependencies /service/.venv /service/.venv
COPY . .
USER 65534
CMD ["uvicorn", "app.api:api", "--host", "0.0.0.0", "--port", "8000"]
