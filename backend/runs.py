"""Projection of hook metadata into session and agent states."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


ACTIVE = {"trabalhando", "delegando", "aguardando"}
IDLE = "ocioso"  # processo do chat sumiu sem SessionEnd e o último evento é recente


# INT-07: depois de cada resposta o Claude Code faz uma faxina interna (título, memória, sugestões) que chega como
# SubagentStop sem SubagentStart e sem agent_type. Não é alguém contratado, então não vira boneco. O filtro vale na criação
# (apply) e na leitura (FAXINA_SQL, para o que já está no banco); events.jsonl e o banco nunca são reescritos.
FAXINA_SQL = (
    "(execucao.pai_chave IS NOT NULL AND execucao.tipo = 'subagente' AND NOT EXISTS ("
    "SELECT 1 FROM evento s WHERE s.session_id = execucao.session_id AND s.nome = 'SubagentStart' "
    "AND json_extract(s.dados, '$.agent_id') = execucao.agent_id))"
)


def key_for(event: dict) -> str:
    agent_id = event.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        return f"agent:{agent_id}"
    return f"session:{event['session_id']}"


def main_key(session_id: str) -> str:
    return f"session:{session_id}"


def _value(event: dict, name: str) -> str:
    value = event.get(name)
    return value if isinstance(value, str) else ""


def _upsert(con: sqlite3.Connection, event: dict, *, state: str,
            parent: str | None = None, ended_by: str | None = None) -> None:
    key = key_for(event)
    when = _value(event, "t")
    existing = con.execute("SELECT atualizado_em FROM execucao WHERE chave = ?", (key,)).fetchone()
    if existing and existing["atualizado_em"] > when:
        return
    kind = _value(event, "agent_type") or ("principal" if key.startswith("session:") else "subagente")
    con.execute(
        "INSERT INTO execucao (chave, session_id, agent_id, pai_chave, tipo, cwd, estado, "
        "origem_encerramento, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET cwd = CASE WHEN excluded.cwd <> '' THEN excluded.cwd ELSE execucao.cwd END, "
        "estado = excluded.estado, origem_encerramento = excluded.origem_encerramento, "
        "atualizado_em = excluded.atualizado_em",
        (key, event["session_id"], _value(event, "agent_id") or None, parent, kind,
         _value(event, "cwd"), state, ended_by, when, when),
    )


def _set_main(con: sqlite3.Connection, event: dict, state: str, ended_by: str | None = None) -> None:
    main = dict(event)
    main.pop("agent_id", None)
    main.pop("agent_type", None)
    _upsert(con, main, state=state, ended_by=ended_by)


def _active_children(con: sqlite3.Connection, session_id: str) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM execucao WHERE session_id = ? AND pai_chave IS NOT NULL "
        "AND estado IN ('trabalhando', 'delegando', 'aguardando')", (session_id,)
    ).fetchone()[0]


def _retomar_orfa(con: sqlite3.Connection, event: dict) -> None:
    """Qualquer evento novo do chat tira a execução principal de 'orfa' (comunicação perdida).

    Volta como 'aguardando'; a reconciliação reclassifica em seguida (ativo ou ocioso). Evento mais antigo que a
    detecção (ingestão atrasada) não retoma nada.
    """
    when = _value(event, "t")
    con.execute(
        "UPDATE execucao SET estado = 'aguardando', origem_encerramento = NULL, atualizado_em = ? "
        "WHERE chave = ? AND estado = 'orfa' AND atualizado_em <= ?",
        (when, main_key(event["session_id"]), when),
    )


def apply(con: sqlite3.Connection, event: dict) -> None:
    name = event["evento"]
    if name != "SessionEnd":
        _retomar_orfa(con, event)
    if name == "SessionStart":
        _set_main(con, event, "aguardando")
    elif name == "UserPromptSubmit":
        _set_main(con, event, "trabalhando")
    elif name == "SubagentStart":
        _set_main(con, event, "delegando")
        _upsert(con, event, state="trabalhando", parent=main_key(event["session_id"]))
    elif name == "SubagentStop":
        if not _value(event, "agent_type") and (not _value(event, "agent_id") or not con.execute(
            "SELECT 1 FROM execucao WHERE chave = ?", (key_for(event),)
        ).fetchone()):
            return  # faxina interna: fim sem início anterior e sem tipo
        if not con.execute("SELECT 1 FROM execucao WHERE chave = ?", (main_key(event["session_id"]),)).fetchone():
            _set_main(con, event, "aguardando")
        _upsert(con, event, state="concluida", parent=main_key(event["session_id"]), ended_by="SubagentStop")
        main = con.execute("SELECT estado FROM execucao WHERE chave = ?", (main_key(event["session_id"]),)).fetchone()
        if main and main["estado"] == "delegando" and not _active_children(con, event["session_id"]):
            _set_main(con, event, "trabalhando")
    elif name == "Stop":
        tasks = event.get("background_tasks")
        if isinstance(tasks, list):
            listed = {str(task["id"]) for task in tasks if isinstance(task, dict) and task.get("id")}
            for child in con.execute(
                "SELECT chave, agent_id FROM execucao WHERE session_id = ? AND pai_chave IS NOT NULL "
                "AND estado IN ('trabalhando', 'delegando', 'aguardando')", (event["session_id"],)
            ).fetchall():
                if child["agent_id"] not in listed:
                    con.execute(
                        "UPDATE execucao SET estado = 'concluida', origem_encerramento = 'interrompida', "
                        "atualizado_em = ? WHERE chave = ? AND atualizado_em <= ?",
                        (_value(event, "t"), child["chave"], _value(event, "t")),
                    )
        _set_main(con, event, "delegando" if _active_children(con, event["session_id"]) else "aguardando")
    elif name == "SessionEnd":
        _set_main(con, event, "concluida", _value(event, "reason") or "SessionEnd")
        con.execute(
            "UPDATE execucao SET estado = 'concluida', origem_encerramento = 'SessionEnd', atualizado_em = ? "
            "WHERE session_id = ? AND pai_chave IS NOT NULL AND estado IN ('trabalhando', 'delegando', 'aguardando') "
            "AND atualizado_em <= ?",
            (_value(event, "t"), event["session_id"], _value(event, "t")),
        )


def waiting_permission(con: sqlite3.Connection) -> set[str]:
    """Sessões cujo último evento é um pedido de permissão e cujo chat principal segue com processo.

    Dura até o próximo evento da própria sessão (qualquer um); não há estado novo na execução.
    """
    rows = con.execute(
        "SELECT e.session_id FROM evento e WHERE (e.nome = 'PermissionRequest' OR (e.nome = 'Notification' "
        "AND json_extract(e.dados, '$.notification_type') = 'permission_prompt')) "
        "AND NOT EXISTS (SELECT 1 FROM evento n WHERE n.session_id = e.session_id AND "
        "(n.ocorrido_em > e.ocorrido_em OR (n.ocorrido_em = e.ocorrido_em AND n.rowid > e.rowid))) "
        "AND EXISTS (SELECT 1 FROM execucao x WHERE x.session_id = e.session_id AND x.pai_chave IS NULL "
        "AND x.estado IN ('trabalhando', 'delegando', 'aguardando'))"
    ).fetchall()
    return {row["session_id"] for row in rows}


def event_data(event: dict) -> str:
    safe = {key: value for key, value in event.items() if key not in {"prompt", "last_assistant_message"}}
    return json.dumps(safe, ensure_ascii=False, sort_keys=True)


def public(row: sqlite3.Row, project: dict | None) -> dict:
    item = dict(row)
    item["projeto_id"] = project["id"] if project else None
    item["projeto_nome"] = project["nome"] if project else None
    item["frente"] = project.get("frente") if project else None
    item["frente_nome"] = project.get("frente_nome") if project else None
    item["frente_descricao"] = project.get("frente_descricao") if project else None
    item["ocioso_segundos"] = idle_seconds(item["atualizado_em"]) if item["estado"] == IDLE else None
    return item


def idle_seconds(last_event: str, now: datetime | None = None) -> int | None:
    """Segundos desde o último evento (número; a formatação é do frontend)."""
    try:
        last = datetime.fromisoformat(last_event.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return max(0, int(((now or datetime.now(timezone.utc)) - last).total_seconds()))
