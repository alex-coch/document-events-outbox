from alembic import op

revision = "001_documents"
down_revision = None


def upgrade():
    op.execute("""
        CREATE TABLE documents (id uuid PRIMARY KEY, title text NOT NULL);
        CREATE TABLE outbox_events (
            event_id uuid PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES documents,
            event_type text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz
        );
        CREATE INDEX outbox_pending ON outbox_events (created_at) WHERE published_at IS NULL;
        CREATE TABLE processed_events (
            consumer_name text NOT NULL,
            event_id uuid NOT NULL,
            PRIMARY KEY (consumer_name, event_id)
        );
        CREATE TABLE document_history (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES documents,
            event_id uuid NOT NULL,
            status text NOT NULL
        );
    """)


def downgrade():
    op.execute("DROP TABLE document_history, processed_events, outbox_events, documents")
