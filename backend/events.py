"""Read the hook queue and keep the latest cwd for each session."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading

from backend.config import events_path
from backend import runs

_lock = threading.Lock()


def _sem_novidade(con: sqlite3.Connection, path) -> bool:
    """True quando o arquivo é o mesmo já lido até o fim: nada a gravar, então nem toma o bloqueio de escrita.

    Leitura pura (sem BEGIN IMMEDIATE): as rotas chamam ingest a cada ciclo da tela e quase sempre não há evento novo.
    """
    try:
        offset_row = con.execute("SELECT valor FROM ingestao WHERE chave = 'events_offset'").fetchone()
        prefix_row = con.execute("SELECT valor FROM ingestao WHERE chave = 'events_prefix'").fetchone()
        if not offset_row or not prefix_row:
            return False
        offset = int(offset_row["valor"])
        if not offset or path.stat().st_size != offset:
            return False
        with path.open("rb") as stream:
            return hashlib.sha256(stream.read(min(offset, 4096))).hexdigest() == prefix_row["valor"]
    except (OSError, sqlite3.Error):
        return False


def ingest(con: sqlite3.Connection) -> int:
    path = events_path()
    if not path.exists():
        return 0
    if _sem_novidade(con, path):
        return 0
    with _lock:
        # Serialize the cursor across server processes as well as threads.
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT valor FROM ingestao WHERE chave = 'events_offset'"
        ).fetchone()
        offset = int(row["valor"]) if row else 0
        previous = con.execute("SELECT valor FROM ingestao WHERE chave = 'events_prefix'").fetchone()
        processed = 0
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(0)
            prefix = hashlib.sha256(stream.read(min(offset, 4096))).hexdigest() if offset else ""
            if size < offset or (offset and previous and previous["valor"] != prefix):
                offset = 0
            stream.seek(offset)
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    stream.seek(start)
                    break
                try:
                    event = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                sid = event.get("session_id")
                name = event.get("evento")
                if not isinstance(sid, str) or not sid or not isinstance(name, str):
                    continue
                when = event.get("t")
                if not isinstance(when, str) or not when:
                    continue
                event_id = event.get("id")
                if not isinstance(event_id, str) or not event_id:
                    event_id = hashlib.sha256(
                        json.dumps(event, sort_keys=True, ensure_ascii=False).encode("utf-8")
                    ).hexdigest()
                cursor = con.execute(
                    "INSERT OR IGNORE INTO evento (id, session_id, nome, ocorrido_em, dados) VALUES (?, ?, ?, ?, ?)",
                    (event_id, sid, name, when, runs.event_data(event)),
                )
                inserted = cursor.rowcount > 0
                if inserted:
                    runs.apply(con, event)
                    cwd = event.get("cwd")
                    title = event.get("session_title")
                    con.execute(
                        "INSERT INTO sessao (session_id, cwd, ultimo_evento, ultima_atualizacao, titulo) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                        "titulo = CASE WHEN excluded.titulo <> '' AND excluded.ultima_atualizacao >= "
                        "sessao.ultima_atualizacao THEN excluded.titulo ELSE sessao.titulo END, "
                        "cwd = CASE WHEN excluded.ultima_atualizacao >= sessao.ultima_atualizacao "
                        "AND excluded.cwd <> '' THEN excluded.cwd ELSE sessao.cwd END, "
                        "ultimo_evento = CASE WHEN excluded.ultima_atualizacao >= sessao.ultima_atualizacao "
                        "THEN excluded.ultimo_evento ELSE sessao.ultimo_evento END, "
                        "ultima_atualizacao = MAX(sessao.ultima_atualizacao, excluded.ultima_atualizacao)",
                        (sid, cwd if isinstance(cwd, str) else "", name, when,
                         title.strip() if isinstance(title, str) else ""),
                    )
                processed += int(inserted)
            offset = stream.tell()
            stream.seek(0)
            prefix = hashlib.sha256(stream.read(min(offset, 4096))).hexdigest() if offset else ""
        con.execute(
            "INSERT INTO ingestao (chave, valor) VALUES ('events_offset', ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (offset,)
        )
        con.execute(
            "INSERT INTO ingestao (chave, valor) VALUES ('events_prefix', ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (prefix,)
        )
        return processed
