"""Reconcile open executions against Claude Code's local process registry."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import data_dir


def sessions_dir() -> Path:
    return Path(os.environ.get("AI_OPERATIONS_ROOM_SESSIONS_DIR") or Path.home() / ".claude" / "sessions")


def process_alive(pid: object) -> bool:
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    if number <= 0:
        return False
    if sys.platform != "win32":
        return Path(f"/proc/{number}").exists()

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, number)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            return False
        name = ctypes.create_unicode_buffer(1024)
        length = wintypes.DWORD(1024)
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
            return True
        return Path(name.value).name.casefold().startswith(("claude", "node"))
    finally:
        kernel.CloseHandle(handle)


def living_sessions() -> dict[str, bool]:
    found: dict[str, bool] = {}
    folder = sessions_dir()
    if not folder.is_dir():
        return found
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("sessionId"), str):
            continue
        sid = data["sessionId"]
        found[sid] = found.get(sid, False) or process_alive(data.get("pid"))
    return found


SILENCIO_ORFA_HORAS = 24  # além disso, sem sinal, a sessão deixa de ser "ociosa" e vira órfã
SILENCIO_ORFA_ENV = "AI_OPERATIONS_ROOM_ORPHAN_HOURS"
EVENTO_RECENTE = timedelta(seconds=60)  # evento tão novo que o registro do processo ainda não é confiável
SESSAO_DESCONHECIDA = timedelta(minutes=10)  # sem registro local do processo: espera antes de dar por parada
ATIVOS = ("trabalhando", "delegando", "aguardando")


def silencio_orfa() -> timedelta:
    """Silêncio que faz uma sessão parada virar órfã: 24 h, ou o valor (em horas) da variável de ambiente."""
    try:
        horas = float(os.environ.get(SILENCIO_ORFA_ENV, ""))
    except ValueError:
        horas = SILENCIO_ORFA_HORAS
    return timedelta(hours=horas if horas > 0 else SILENCIO_ORFA_HORAS)


def classificar(vivo: bool | None, ultimo_evento: datetime, session_end_sem_par: bool,
                agora: datetime, silencio: timedelta | None = None) -> str:
    """'ativo', 'ocioso' ou 'orfa' para uma sessão com execução aberta.

    vivo: processo do chat vivo (True), sumido (False) ou sem registro local (None).
    Órfã só com SessionEnd sem par ou com silêncio maior que o limite; o app do Claude
    encerra o processo de um chat parado e o religa ao abri-lo, então processo sumido
    sozinho é ocioso. Processo vivo é sempre ativo.
    """
    if vivo:
        return "ativo"
    parado = agora - ultimo_evento
    if session_end_sem_par or parado > (silencio or silencio_orfa()):
        return "orfa"
    if parado < EVENTO_RECENTE:
        return "ativo"
    if vivo is False or parado > SESSAO_DESCONHECIDA:
        return "ocioso"
    return "ativo"


def _session_end_sem_par(con: sqlite3.Connection, session_id: str, ultimo: str) -> bool:
    """SessionEnd sem o resto do ciclo (sem SessionStart) ou que não fechou a execução ainda aberta."""
    return con.execute(
        "SELECT 1 FROM evento e WHERE e.session_id = ? AND e.nome = 'SessionEnd' AND ("
        "NOT EXISTS (SELECT 1 FROM evento s WHERE s.session_id = e.session_id AND s.nome = 'SessionStart') "
        "OR julianday(e.ocorrido_em) >= julianday(?)) LIMIT 1", (session_id, ultimo)
    ).fetchone() is not None


def reconcile(con: sqlite3.Connection, *, living: dict[str, bool] | None = None,
              now: datetime | None = None) -> int:
    """Marca como ociosa (ou órfã, pelas regras de `classificar`) a sessão cujo processo sumiu."""
    living = living_sessions() if living is None else living
    now = now or datetime.now(timezone.utc)
    demo_mode = (data_dir() / ".demo-mode").exists()
    rows = con.execute(
        "SELECT session_id, MAX(atualizado_em) AS ultimo FROM execucao "
        "WHERE estado IN ('trabalhando', 'delegando', 'aguardando', 'ocioso') GROUP BY session_id"
    ).fetchall()
    idle, orphan = [], []
    for row in rows:
        if demo_mode and row["session_id"].startswith("demo-"):
            continue
        last = row["ultimo"]
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except (AttributeError, ValueError):
            continue
        verdict = classificar(living.get(row["session_id"]), last_dt,
                              _session_end_sem_par(con, row["session_id"], last), now)
        if verdict == "orfa":
            orphan.append(row["session_id"])
        elif verdict == "ocioso":
            idle.append(row["session_id"])
    count = 0
    stamp = now.isoformat(timespec="seconds")
    for sid in orphan:
        count += con.execute(
            "UPDATE execucao SET estado = 'orfa', origem_encerramento = 'pid_morto', atualizado_em = ? "
            "WHERE session_id = ? AND estado IN ('trabalhando', 'delegando', 'aguardando', 'ocioso')",
            (stamp, sid),
        ).rowcount
    for sid in idle:
        # atualizado_em fica no último evento: é dele que se conta o "ocioso há X".
        count += con.execute(
            "UPDATE execucao SET estado = 'ocioso' WHERE session_id = ? AND pai_chave IS NULL "
            "AND estado IN ('trabalhando', 'delegando', 'aguardando')", (sid,)
        ).rowcount
        # sem processo não há subagente em curso: o que ficou aberto foi interrompido.
        count += con.execute(
            "UPDATE execucao SET estado = 'concluida', origem_encerramento = 'interrompida' "
            "WHERE session_id = ? AND pai_chave IS NOT NULL "
            "AND estado IN ('trabalhando', 'delegando', 'aguardando')", (sid,)
        ).rowcount
    return count
