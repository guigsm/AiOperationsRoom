"""SAL-09: evento novo tira a sessão de 'orfa' (comunicação perdida) e ingestão sem bloqueio quando não há novidade."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import events
from backend.api import app
from backend.config import events_path
from backend.db import connect


def iso(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="seconds")


def put(*items):
    with events_path().open("a", encoding="utf-8") as stream:
        for item in items:
            stream.write(json.dumps(item) + "\n")


def ev(sid, name, when, **extra):
    return {"id": f"{sid}-{name}-{when}", "session_id": sid, "evento": name, "cwd": "/w", "t": when, **extra}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_OPERATIONS_ROOM_SESSIONS_DIR", str(tmp_path / "sessions"))
    with TestClient(app) as test_client:
        yield test_client


def estado(client, sid="o"):
    return next(a["estado"] for a in client.get(f"/api/sessoes/{sid}/agentes").json()["agentes"] if a["pai_chave"] is None)


def virar_orfa(client):
    put(ev("o", "SessionStart", iso(hours=26)))
    client.get("/api/painel")
    assert estado(client) == "orfa"


@pytest.mark.parametrize("nome", ["UserPromptSubmit", "Stop", "SessionStart", "PostToolUse", "Notification"])
def test_qualquer_evento_novo_tira_a_sessao_de_orfa(client, nome):
    virar_orfa(client)
    put(ev("o", nome, iso(seconds=-2)))  # depois da detecção, que carimba "agora"
    client.get("/api/painel")  # ingere e reconcilia
    assert estado(client) != "orfa"
    assert client.get("/api/painel").json()["resumo"]["orfa"] == 0


def test_evento_antigo_ingerido_tarde_nao_retoma(client):
    virar_orfa(client)
    put(ev("o", "UserPromptSubmit", iso(hours=30)))
    client.get("/api/painel")
    assert estado(client) == "orfa"


def test_session_end_nao_retoma(client):
    virar_orfa(client)
    put(ev("o", "SessionEnd", iso(seconds=-2)))
    client.get("/api/painel")
    assert estado(client) == "concluida"


def test_ingestao_sem_novidade_nao_pega_o_bloqueio_de_escrita(client, monkeypatch):
    put(ev("a", "SessionStart", iso(minutes=1)))
    client.get("/api/painel")
    with connect() as con:
        assert events._sem_novidade(con, events_path())
        comandos = []
        con.set_trace_callback(comandos.append)
        assert events.ingest(con) == 0
    assert not any("BEGIN" in c.upper() for c in comandos)


def test_ingestao_volta_a_ler_quando_o_arquivo_cresce(client):
    put(ev("a", "SessionStart", iso(minutes=1)))
    client.get("/api/painel")
    put(ev("b", "SessionStart", iso(seconds=5)))
    with connect() as con:
        assert not events._sem_novidade(con, events_path())
        assert events.ingest(con) == 1
        con.commit()
        assert events._sem_novidade(con, events_path())
