"""SAL-03: ocioso em vez de órfã e blocos por frente da Suíte."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import manifest
from backend.api import app
from backend.config import events_path
from backend.db import connect
from backend.reconcile import SILENCIO_ORFA_ENV, classificar, reconcile, silencio_orfa

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


# --- regra pura -------------------------------------------------------------

def test_process_gone_five_minutes_without_session_end_is_idle():
    assert classificar(False, ago(minutes=5), False, NOW) == "ocioso"


def test_fresh_event_is_active_even_if_process_record_is_stale():
    assert classificar(False, ago(seconds=10), False, NOW) == "ativo"
    assert classificar(False, ago(minutes=2), False, NOW) == "ocioso"


def test_silence_over_24h_is_orphan():
    assert classificar(False, ago(hours=25), False, NOW) == "orfa"
    assert classificar(False, ago(hours=23), False, NOW) == "ocioso"


def test_session_end_without_pair_is_orphan():
    assert classificar(False, ago(minutes=5), True, NOW) == "orfa"


def test_live_process_is_active_even_after_long_silence():
    assert classificar(True, ago(hours=30), False, NOW) == "ativo"


def test_unknown_process_waits_ten_minutes_then_idle():
    assert classificar(None, ago(minutes=3), False, NOW) == "ativo"
    assert classificar(None, ago(minutes=11), False, NOW) == "ocioso"


def test_silence_limit_from_environment(monkeypatch):
    assert silencio_orfa() == timedelta(hours=24)
    monkeypatch.setenv(SILENCIO_ORFA_ENV, "2")
    assert classificar(False, ago(hours=3), False, NOW) == "orfa"
    monkeypatch.setenv(SILENCIO_ORFA_ENV, "lixo")
    assert silencio_orfa() == timedelta(hours=24)


# --- reconcile + API ----------------------------------------------------------

def iso(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="seconds")


def put(*items):
    with events_path().open("a", encoding="utf-8") as stream:
        for item in items:
            stream.write(json.dumps(item) + "\n")


def ev(sid, name, when, cwd="/w", **extra):
    return {"id": f"{sid}-{name}-{when}-{extra.get('agent_id', '')}", "session_id": sid, "evento": name,
            "cwd": cwd, "t": when, **extra}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("AI_OPERATIONS_ROOM_SESSIONS_DIR", str(tmp_path / "vazio"))
    with TestClient(app) as test_client:
        yield test_client


def by_session(client):
    return {r["session_id"]: r for r in client.get("/api/painel?horas=24&convivencia=24").json()["historico"]
            if r["pai_chave"] is None}


def test_idle_keeps_last_event_instant_and_returns_to_active_on_new_event(client):
    when = iso(minutes=40)
    put(ev("a", "SessionStart", when), ev("a", "Stop", when))
    run = by_session(client)["a"]
    assert run["estado"] == "ocioso" and run["atualizado_em"] == when
    assert 39 * 60 <= run["ocioso_segundos"] <= 41 * 60
    put(ev("a", "UserPromptSubmit", iso(seconds=5)))
    run = by_session(client)["a"]
    assert run["estado"] == "trabalhando" and run["ocioso_segundos"] is None


def test_silent_over_24h_becomes_orphan_and_idle_subagent_is_closed(client):
    put(ev("old", "SessionStart", iso(hours=26)),
        ev("busy", "SessionStart", iso(minutes=30)),
        ev("busy", "SubagentStart", iso(minutes=30), agent_id="x"))
    client.get("/api/painel")
    assert client.get("/api/sessoes/old/agentes").json()["agentes"][0]["estado"] == "orfa"
    states = {a["pai_chave"] is None: a["estado"] for a in client.get("/api/sessoes/busy/agentes").json()["agentes"]}
    assert states == {True: "ocioso", False: "concluida"}


def test_session_end_without_session_start_is_orphan(client):
    put(ev("z", "SubagentStart", iso(minutes=2), agent_id="s"), ev("z", "SessionEnd", iso(minutes=2)))
    client.get("/api/sessoes")
    with connect() as con:
        con.execute("UPDATE execucao SET estado = 'trabalhando' WHERE session_id = 'z'")
        assert reconcile(con, living={"z": False}) > 0
    assert {a["estado"] for a in client.get("/api/sessoes/z/agentes").json()["agentes"]} == {"orfa"}


def test_summary_counts_idle(client):
    put(ev("a", "SessionStart", iso(minutes=40)))
    resumo = client.get("/api/painel").json()["resumo"]
    assert resumo["ocioso"] == 1 and resumo["orfa"] == 0 and resumo["sessoes_ativas"] == 0


# --- blocos por frente --------------------------------------------------------

SEDE = r"""
versao: 1
projetos:
  - {nome: estudio, sigla: EST, status: ativo, pasta_atual: 'C:\intoca\estudio'}
  - {nome: localhost, sigla: LOC, status: ativo, pasta_atual: 'C:\intoca\_infra\painel'}
  - {nome: coreograf, sigla: COR, status: ativo, pasta_atual: 'C:\intoca\coreograf'}
suite:
  frentes:
    producao: {nome: 'Estúdio', descricao: 'imagem, vídeo e 3D', membros: [estudio]}
    operacao: {nome: 'Operação', descricao: 'camada Claude e painel', membros: [localhost]}
"""


def test_manifest_fronts_carry_description_and_order():
    found = manifest.parse(yaml.safe_load(SEDE), Path("C:/intoca"))
    assert [f["chave"] for f in found["frentes"]] == ["producao", "operacao"]
    assert found["frentes"][0]["descricao"] == "imagem, vídeo e 3D"
    room = {r["nome"]: r for r in found["salas"]}
    assert room["estudio"]["frente_nome"] == "Estúdio" and room["coreograf"]["frente"] is None


def test_panel_exposes_fronts_only_with_manifest(client, monkeypatch):
    put(ev("a", "SessionStart", iso(seconds=3), cwd="C:\\intoca\\estudio"))
    assert client.get("/api/painel").json()["frentes"] == []
    found = manifest.parse(yaml.safe_load(SEDE), Path("C:/intoca"))
    monkeypatch.setattr("backend.api.manifesto.load", lambda *a, **k: found)
    painel = client.get("/api/painel").json()
    assert [f["chave"] for f in painel["frentes"]] == ["producao", "operacao"]
    run = painel["execucoes"][0]
    assert run["frente"] == "producao" and run["frente_nome"] == "Estúdio"
