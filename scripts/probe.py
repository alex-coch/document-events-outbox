"""Run inside the API container against the live HTTP API and PostgreSQL."""
import json
import sys
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.db import engine


def http(path, data=None):
    request = Request("http://localhost:8000" + path, data=data,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=4) as result:
        assert result.status == (201 if data else 200)
        return json.load(result)


def verify(event_id, delivered):
    with engine.connect() as db:
        row = db.execute(text("""
            SELECT document_id, published_at,
              (SELECT count(*) FROM processed_events WHERE event_id=:id) AS processed
            FROM outbox_events WHERE event_id=:id
        """), {"id": event_id}).one()
    assert http(f"/documents/{row.document_id}")["id"] == str(row.document_id)
    history = http(f"/documents/{row.document_id}/history")
    assert (row.published_at is not None) == delivered, row
    assert row.processed == int(delivered), row
    assert history == ([{"event_id": event_id, "status": "submitted"}] if delivered else []), history
    print(f"event_id={event_id} published={delivered} processed={row.processed} history_count={len(history)}")


if __name__ == "__main__":
    if sys.argv[1] == "create":
        print(http("/documents", b'{"title":"Delivery experiment"}')["event_id"])
    else:
        verify(sys.argv[2], sys.argv[1] == "delivered")
