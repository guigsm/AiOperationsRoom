"""Small SQLite store for project mappings and session discovery."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import database_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(database_path(), timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with connect() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS projeto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL COLLATE NOCASE UNIQUE,
                caminho_local TEXT NOT NULL,
                caminho_key TEXT NOT NULL UNIQUE,
                arquivado INTEGER NOT NULL DEFAULT 0 CHECK (arquivado IN (0, 1)),
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessao (
                session_id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                ultimo_evento TEXT NOT NULL,
                ultima_atualizacao TEXT NOT NULL,
                titulo TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS ingestao (
                chave TEXT PRIMARY KEY,
                valor INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evento (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                nome TEXT NOT NULL,
                ocorrido_em TEXT NOT NULL,
                dados TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execucao (
                chave TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT,
                pai_chave TEXT,
                tipo TEXT NOT NULL,
                cwd TEXT NOT NULL,
                estado TEXT NOT NULL,
                origem_encerramento TEXT,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_execucao_session ON execucao(session_id);
            CREATE INDEX IF NOT EXISTS idx_evento_session ON evento(session_id);
        """)
        # Light migration: databases created before the chat title was captured.
        if "titulo" not in {row["name"] for row in con.execute("PRAGMA table_info(sessao)")}:
            con.execute("ALTER TABLE sessao ADD COLUMN titulo TEXT NOT NULL DEFAULT ''")
