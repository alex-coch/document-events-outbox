import json
import os
import socket
import sys
import time

import pika
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import apply_event, engine

QUEUE = "document.submitted.v1"


def log(action, **fields):
    print(json.dumps({"action": action, "pod": socket.gethostname(), **fields}), flush=True)


def relay(channel):
    channel.confirm_delivery()
    while True:
        with engine.begin() as db:
            event = db.execute(text("""
                SELECT event_id, document_id, event_type FROM outbox_events WHERE published_at IS NULL
                ORDER BY created_at, event_id LIMIT 1 FOR UPDATE SKIP LOCKED
            """)).mappings().first()
            if event:
                payload = {key: str(value) for key, value in event.items()}
                channel.basic_publish(exchange="", routing_key=QUEUE, mandatory=True,
                                      body=json.dumps(payload).encode(), properties=pika.BasicProperties(
                                          content_type="application/json", delivery_mode=2,
                                          message_id=payload["event_id"]))
                db.execute(text("UPDATE outbox_events SET published_at=now() WHERE event_id=:event_id"), payload)
        if event:
            log("published", event_id=payload["event_id"])
        else:
            channel.connection.sleep(0.25)


def consume(channel):
    channel.basic_qos(prefetch_count=1)

    def handle(ch, delivery, properties, body):
        event = json.loads(body)
        applied = apply_event(event)
        fields = {"event_id": event["event_id"], "redelivered": delivery.redelivered}
        if applied and event["event_id"] == os.getenv("PAUSE_BEFORE_ACK"):
            log("committed_before_ack", **fields)
            while True:
                ch.connection.sleep(1)
        ch.basic_ack(delivery_tag=delivery.delivery_tag)
        log("applied" if applied else "duplicate_skipped", **fields)

    channel.basic_consume(QUEUE, handle, auto_ack=False)
    channel.start_consuming()


def run(role):
    params = pika.ConnectionParameters(
        host=os.getenv("BROKER_HOST", "rabbitmq"), credentials=pika.PlainCredentials("outbox", os.environ["DEMO_PASSWORD"]),
        heartbeat=30, blocked_connection_timeout=10, socket_timeout=3, stack_timeout=8,
    )
    while True:
        try:
            with pika.BlockingConnection(params) as connection:
                channel = connection.channel()
                channel.queue_declare(queue=QUEUE, durable=True)
                role(channel)
        except (pika.exceptions.AMQPError, OperationalError, OSError) as exc:
            log("reconnecting", reason=type(exc).__name__)
            time.sleep(1)


if __name__ == "__main__":
    run({"relay": relay, "consumer": consume}[sys.argv[1]])
