FROM python:3.11-slim-bookworm
WORKDIR /service
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 65534
CMD ["uvicorn", "app.api:api", "--host", "0.0.0.0", "--port", "8000"]
