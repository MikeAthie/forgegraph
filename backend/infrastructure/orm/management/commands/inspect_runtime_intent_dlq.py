from __future__ import annotations

import json
from typing import Any, cast

from django.core.management.base import BaseCommand

from application.services.runtime_write_intents import (
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    build_runtime_intent_redis_client,
)


class Command(BaseCommand):
    help = "Inspect runtime intent dead-letter entries without reading raw Redis payloads."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Maximum number of dead-letter records to show.",
        )
        parser.add_argument(
            "--run-id",
            default="",
            help="Filter dead-letter records by run_id.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        count = max(int(options["count"]), 1)
        run_id_filter = str(options["run_id"] or "").strip()

        redis_client = build_runtime_intent_redis_client()
        records = cast(
            list[tuple[str, dict[str, Any]]],
            redis_client.xrevrange(
                RUNTIME_INTENT_DEAD_LETTER_STREAM,
                max="+",
                min="-",
                count=count,
            ),
        )

        shown = 0
        for message_id, fields in records:
            run_id = str(fields.get("run_id") or "").strip()
            if run_id_filter and run_id != run_id_filter:
                continue
            shown += 1
            self.stdout.write(
                json.dumps(
                    {
                        "dlq_message_id": message_id,
                        "run_id": run_id or None,
                        "intent_id": str(fields.get("intent_id") or "").strip() or None,
                        "attempt_id": str(fields.get("attempt_id") or "").strip() or None,
                        "intent_type": str(fields.get("intent_type") or "").strip() or None,
                        "delivery_count": _coerce_int(fields.get("delivery_count")),
                        "reason": str(fields.get("reason") or "").strip() or None,
                        "error_class": str(fields.get("error_class") or "").strip() or None,
                        "stream_message_id": str(
                            fields.get("stream_message_id")
                            or fields.get("original_message_id")
                            or ""
                        ).strip()
                        or None,
                        "timestamp": str(
                            fields.get("timestamp") or fields.get("dead_lettered_at") or ""
                        ).strip()
                        or None,
                    },
                    sort_keys=True,
                )
            )

        if shown == 0:
            self.stdout.write("No runtime intent dead-letter records matched.")


def _coerce_int(value: object) -> int | None:
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None
