from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db


def test_outbox_failure_rolls_back_document(monkeypatch):
    existing = db.submit("first")
    new_document_id = uuid4()
    ids = iter((new_document_id, existing["event_id"]))
    monkeypatch.setattr(db, "uuid4", lambda: next(ids))
    with pytest.raises(IntegrityError):
        db.submit("must roll back")
    with db.engine.connect() as conn:
        assert not conn.execute(text("SELECT 1 FROM documents WHERE id=:id"), {"id": new_document_id}).first()


def test_redelivery_has_one_business_effect():
    event = {**db.submit("repeat delivery"), "event_type": "document.submitted.v1"}
    # Use a distinct event ID to exercise the handler independently of the running relay.
    event["event_id"] = uuid4()
    assert db.apply_event(event)
    assert not db.apply_event(event)
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM document_history WHERE event_id=:event_id"), event).scalar_one() == 1


def test_failed_effect_rolls_back_deduplication():
    event = {"event_id": uuid4(), "document_id": uuid4(), "event_type": "document.submitted.v1"}
    with pytest.raises(IntegrityError):
        db.apply_event(event)
    with db.engine.connect() as conn:
        assert not conn.execute(text("SELECT 1 FROM processed_events WHERE event_id=:event_id"), event).first()
