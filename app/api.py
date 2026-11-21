from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine, submit

api = FastAPI(title="Document events outbox")


class Document(BaseModel):
    title: str = Field(min_length=1, max_length=250)


@api.get("/live")
def live():
    return {"status": "up"}


@api.get("/ready")
def ready():
    with engine.connect() as db:
        db.execute(text("SELECT 1 FROM documents LIMIT 1"))
    return {"status": "ready"}


@api.post("/documents", status_code=201)
def create(document: Document):
    return submit(document.title)


@api.get("/documents/{document_id}")
def document(document_id: UUID):
    with engine.connect() as db:
        row = db.execute(text("SELECT id, title FROM documents WHERE id=:id"), {"id": document_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Unknown document")
    return dict(row)


@api.get("/documents/{document_id}/history")
def history(document_id: UUID):
    with engine.connect() as db:
        rows = db.execute(text("""
            SELECT event_id, status FROM document_history WHERE document_id=:id ORDER BY id
        """), {"id": document_id}).mappings()
        return [dict(row) for row in rows]
