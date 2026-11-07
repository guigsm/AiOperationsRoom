"""Hook de captura (Claude Code): grava só metadados, nunca o conteúdo da conversa.

INT-07: o hook de SessionEnd precisa responder em menos de 1 s, senão o Claude Code o cancela ("Hook cancelled") ao fechar.
Por isso este arquivo só usa `sys`, `os`, `json` e `time` (sem `uuid`, `datetime` nem `pathlib`, que pesam na partida do
interpretador), faz uma única gravação em modo append e sai. Nada lento acontece aqui: a leitura, a faxina e o banco são do servidor.
"""

import json
import os
import sys
import time

FIELDS = ("hook_event_name", "session_id", "cwd", "agent_id", "agent_type", "reason", "session_title")
BACKGROUND_FIELDS = ("id", "type", "status", "agent_type")
PERMISSION_FIELDS = ("notification_type", "tool_name")  # só nomes: nunca tool_input nem a mensagem
PERMISSION_TYPE = "permission_prompt"


def data_dir() -> str:
    return os.path.expanduser(os.environ.get("AI_OPERATIONS_ROOM_DATA_DIR")
                              or os.path.join(os.path.expanduser("~"), ".ai-operations-room"))


def is_permission(payload: dict) -> bool:
    """PermissionRequest (provado com chat real) ou Notification do tipo permission_prompt."""
    name = payload.get("hook_event_name")
    return name == "PermissionRequest" or (name == "Notification" and payload.get("notification_type") == PERMISSION_TYPE)


def _novo_id() -> str:
    raw = os.urandom(16).hex()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def normalize(payload: dict) -> dict:
    event = {key: payload[key] for key in FIELDS if key in payload}
    if is_permission(payload):
        for key in PERMISSION_FIELDS:
            value = payload.get(key)
            if isinstance(value, str) and value:
                event[key] = value[:120]
    event["evento"] = event.pop("hook_event_name", "desconhecido")
    event["id"] = _novo_id()
    event["t"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    tasks = payload.get("background_tasks")
    if isinstance(tasks, list):
        event["background_tasks"] = [
            {key: task[key] for key in BACKGROUND_FIELDS if key in task}
            for task in tasks if isinstance(task, dict)
        ]
    return event


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        if not isinstance(payload, dict) or not payload.get("session_id"):
            return 0
        if payload.get("hook_event_name") == "Notification" and not is_permission(payload):
            return 0  # outras notificações não interessam à sala
        path = data_dir()
        os.makedirs(path, exist_ok=True)
        linha = (json.dumps(normalize(payload), ensure_ascii=False) + "\n").encode("utf-8")
        with open(os.path.join(path, "events.jsonl"), "ab") as stream:
            stream.write(linha)
    except Exception:
        pass  # Um hook nunca pode interromper o Claude Code.
    return 0


if __name__ == "__main__":
    sys.exit(main())
