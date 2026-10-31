"""Claude Code hook: append metadata only, never conversation content."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("hook_event_name", "session_id", "cwd", "agent_id", "agent_type", "reason", "session_title")
BACKGROUND_FIELDS = ("id", "type", "status", "agent_type")
PERMISSION_FIELDS = ("notification_type", "tool_name")  # só nomes: nunca tool_input nem a mensagem
PERMISSION_TYPE = "permission_prompt"


def data_dir() -> Path:
    return Path(os.environ.get("AI_OPERATIONS_ROOM_DATA_DIR")
                or Path.home() / ".ai-operations-room").expanduser()


def is_permission(payload: dict) -> bool:
    """PermissionRequest (provado com chat real) ou Notification do tipo permission_prompt."""
    name = payload.get("hook_event_name")
    return name == "PermissionRequest" or (name == "Notification" and payload.get("notification_type") == PERMISSION_TYPE)


def normalize(payload: dict) -> dict:
    event = {key: payload[key] for key in FIELDS if key in payload}
    if is_permission(payload):
        for key in PERMISSION_FIELDS:
            value = payload.get(key)
            if isinstance(value, str) and value:
                event[key] = value[:120]
    event["evento"] = event.pop("hook_event_name", "desconhecido")
    event["id"] = str(uuid.uuid4())
    event["t"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tasks = payload.get("background_tasks")
    if isinstance(tasks, list):
        event["background_tasks"] = [
            {key: task[key] for key in BACKGROUND_FIELDS if key in task}
            for task in tasks if isinstance(task, dict)
        ]
    return event


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or not payload.get("session_id"):
            return 0
        if payload.get("hook_event_name") == "Notification" and not is_permission(payload):
            return 0  # outras notificações não interessam à sala
        path = data_dir()
        path.mkdir(parents=True, exist_ok=True)
        with (path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(normalize(payload), ensure_ascii=False) + "\n")
    except Exception:
        pass  # A hook must never interrupt Claude Code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
