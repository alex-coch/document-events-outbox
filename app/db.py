import os
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

engine = create_engine(URL.create(
    "postgresql+psycopg", username="outbox", password=os.environ["DEMO_PASSWORD"],
    host=os.getenv("DB_HOST", "postgres"), database="outbox",
), pool_pre_ping=True)


def submit(title):
    ids = {"document_id": uuid4(), "event_id": uuid4()}
    with engine.begin() as db:
        db.execute(text("INSERT INTO documents VALUES (:document_id, :title)"), {**ids, "title": title})
        db.execute(text("""
            INSERT INTO outbox_events (event_id, document_id, event_type)
            VALUES (:event_id, :document_id, 'document.submitted.v1')
        """), ids)
    return ids


def apply_event(event):
    if event["event_type"] != "document.submitted.v1":
        raise ValueError("Unsupported event type")
    with engine.begin() as db:
        inserted = db.execute(text("""
            INSERT INTO processed_events (consumer_name, event_id) VALUES ('history', :event_id)
            ON CONFLICT DO NOTHING RETURNING event_id
        """), event).scalar_one_or_none()
        if inserted is None:
            return False
        db.execute(text("""
            INSERT INTO document_history (document_id, event_id, status)
            VALUES (:document_id, :event_id, 'submitted')
        """), event)
    return True
