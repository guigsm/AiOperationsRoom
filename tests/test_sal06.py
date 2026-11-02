"""SAL-06: erro de servidor sempre em JSON, ingestão tolerante a banco travado e legendas abreviadas."""
from __future__ import annotations

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.api import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_OPERATIONS_ROOM_SESSIONS_DIR", str(tmp_path / "sessions"))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _travado(_con):
    raise sqlite3.OperationalError("database is locked")


@pytest.mark.parametrize("caminho", ["/api/painel", "/api/sessoes", "/api/pendencias",
                                     "/api/sessoes/x/historico", "/api/sessoes/x/agentes"])
def test_ingestao_travada_serve_o_que_ja_esta_gravado(client, monkeypatch, caminho):
    monkeypatch.setattr(api, "_ingest", _travado)
    response = client.get(caminho)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_banco_travado_fora_da_ingestao_vira_503_em_json(client, monkeypatch):
    monkeypatch.setattr(api, "reconcile", _travado)
    response = client.get("/api/painel")
    assert response.status_code == 503
    assert "Banco ocupado" in response.json()["detail"]


def test_erro_inesperado_vira_500_em_json_nao_em_texto(client, monkeypatch):
    def quebra(_con):
        raise RuntimeError("falha qualquer")
    monkeypatch.setattr(api, "reconcile", quebra)
    response = client.get("/api/painel")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Erro interno do servidor."}


def test_ingestao_concorrente_com_escrita_nao_da_500(client, tmp_path):
    codigos = []

    def bater(caminho):
        for _ in range(15):
            codigos.append(client.get(caminho).status_code)

    eventos = tmp_path / "events.jsonl"
    with eventos.open("ab") as stream:
        for i in range(30):
            stream.write(('{"id":"e%d","session_id":"s%d","evento":"UserPromptSubmit","t":"2026-11-02T10:00:%02dZ","cwd":"C:\\x"}\n'
                          % (i, i % 3, i)).encode())
    threads = [threading.Thread(target=bater, args=(c,)) for c in ["/api/painel", "/api/sessoes", "/api/pendencias"] * 2]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codigos and set(codigos) == {200}
