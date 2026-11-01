"""SAL-02: chat title as character name, rooms from the sede manifest."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import manifest, titulo
from backend.api import app
from backend.config import events_path
from backend.db import init_db

SEDE_YAML = r"""
versao: 1
projetos:
  - {nome: localhost, sigla: LOC, status: ativo, pasta_atual: 'C:\intoca\_infra\painel'}
  - {nome: sala-de-operacoes, sigla: SAL, status: ativo, pasta_atual: 'C:\intoca\sala'}
  - {nome: antigo, sigla: OLD, status: encerrado, pasta_atual: 'C:\intoca\antigo'}
  - {nome: Escola da Nuvem, sigla: GPA, status: ativo, pasta_atual: 'C:\Users\E470\repos\gpa'}
suite:
  frentes:
    operacao: {nome: 'Operação', membros: [localhost, sala-de-operacoes]}
"""


def test_title_patterns():
    siglas = {"SAL": "sala-de-operacoes"}
    assert titulo.parse("Gerente · Localhost") == {
        "cargo": "Gerente", "projeto": "Localhost", "os_id": None, "rotulo": "Gerente · Localhost"}
    assert titulo.parse("Diretoria · Sede")["rotulo"] == "Diretoria · Sede"
    assert titulo.parse("Plantão · Deploy · VA")["projeto"] == "VA"
    executor = titulo.parse("Executor · SAL-02 nome pelo título", siglas)
    assert (executor["cargo"], executor["os_id"], executor["projeto"]) == ("Executor", "SAL-02", "sala-de-operacoes")
    assert executor["rotulo"] == "Executor · SAL-02"
    assert titulo.parse("Executor · SAL-02")["projeto"] is None


@pytest.mark.parametrize("raw", [None, "", "Conversa qualquer", "Gerente", "Gerente · ", "Executor · sem id", "Chefe · X", 12])
def test_title_off_pattern_is_neutral(raw):
    assert titulo.parse(raw) == {"cargo": None, "projeto": None, "os_id": None, "rotulo": None}


def test_hook_keeps_session_title_without_prompt(tmp_path):
    hook = Path(__file__).resolve().parent.parent / "hooks" / "capture.py"
    env = {"AI_OPERATIONS_ROOM_DATA_DIR": str(tmp_path), "PATH": ""}
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "C:\\x", "prompt": "segredo",
               "session_title": "Gerente · Localhost"}
    without = {key: value for key, value in payload.items() if key != "session_title"}
    for body in (payload, {**without, "session_id": "s2"}):
        done = subprocess.run([sys.executable, str(hook)], input=json.dumps(body), text=True, env=env)
        assert done.returncode == 0
    lines = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines[0]["session_title"] == "Gerente · Localhost" and "prompt" not in lines[0]
    assert "session_title" not in lines[1]


def make_sede(tmp_path: Path) -> Path:
    sede = tmp_path / "sede"
    sede.mkdir()
    (sede / "sede.yaml").write_text(SEDE_YAML, encoding="utf-8")
    return sede


def test_manifest_rooms_and_fronts(tmp_path):
    sede = make_sede(tmp_path)
    found = manifest.load_from(start=tmp_path / "fora", environ={"INTOCA_SEDE": str(sede)}, home=tmp_path / "h")
    assert [room["nome"] for room in found["salas"]] == ["Sede", "localhost", "sala-de-operacoes", "Escola da Nuvem"]
    assert found["origem"] == "variavel"
    room = {r["nome"]: r for r in found["salas"]}
    assert room["localhost"]["frente"] == "operacao" and room["Escola da Nuvem"]["frente"] is None


def test_manifest_lookup_order(tmp_path):
    sede = make_sede(tmp_path)
    home = tmp_path / "home"
    (home / ".intoca").mkdir(parents=True)
    (home / ".intoca" / "sede").write_text(str(sede), encoding="utf-8")
    assert manifest.find(tmp_path / "x", {}, home)[1] == "ponteiro"
    assert manifest.find(sede / "sala" / "app", {}, tmp_path / "nada")[1] == "subida"
    assert manifest.find(Path(tmp_path.anchor), {"INTOCA_SEDE": str(tmp_path / "invalida")}, tmp_path / "nada") is None


def test_no_manifest_or_broken_manifest_is_soft(tmp_path):
    assert manifest.load_from(start=Path(tmp_path.anchor), environ={}, home=tmp_path) is None
    broken = tmp_path / "b"
    broken.mkdir()
    (broken / "sede.yaml").write_text("projetos: [: :", encoding="utf-8")
    assert manifest.load_from(start=tmp_path, environ={"INTOCA_SEDE": str(broken)}, home=tmp_path) is None


def test_resolve_most_specific_and_worktrees(tmp_path):
    sede = tmp_path / "sede"
    (sede / "_worktrees" / "wt1").mkdir(parents=True)
    (sede / "plugin").mkdir()
    (sede / "_worktrees" / "wt1" / ".git").write_text(
        f"gitdir: {sede / 'plugin'}/.git/worktrees/wt1\n", encoding="utf-8")
    data = {"projetos": [{"nome": "plugin-intoca", "status": "ativo", "pasta_atual": str(sede / "plugin")},
                         {"nome": "sub", "status": "ativo", "pasta_atual": str(sede / "plugin" / "sub")}]}
    found = manifest.parse(data, sede)

    def pick(cwd):
        return (manifest.resolve(str(cwd), found) or {}).get("nome")

    assert pick(sede / "plugin" / "x") == "plugin-intoca"
    assert pick(sede / "plugin" / "sub" / "y") == "sub"
    assert pick(sede / "plugin" / ".claude" / "worktrees" / "a") == "plugin-intoca"
    assert pick(sede / "_worktrees" / "wt1" / "pasta") == "plugin-intoca"
    assert pick(sede / "outra") == "Sede"
    assert pick(tmp_path / "fora") is None


def event(sid, name, cwd, minute, title=None):
    body = {"session_id": sid, "cwd": cwd, "evento": name, "id": f"{sid}-{name}-{minute}",
            "t": (datetime.now(timezone.utc) - timedelta(minutes=30 - minute)).isoformat(timespec="seconds")}
    if title is not None:
        body["session_title"] = title
    return body


def write_events(*items):
    with events_path().open("a", encoding="utf-8") as stream:
        for item in items:
            stream.write(json.dumps(item) + "\n")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    with TestClient(app) as test_client:
        yield test_client


def runs_of(client):
    return {r["session_id"]: r for r in client.get("/api/painel?horas=24&convivencia=24").json()["historico"]}


def test_title_persisted_updated_and_exposed(client):
    write_events(event("a", "SessionStart", "C:\\x", 1, "Gerente · Localhost"),
                 event("a", "UserPromptSubmit", "C:\\x", 2, "Gerente · Sala"),
                 event("a", "Stop", "C:\\x", 3))
    session = client.get("/api/sessoes").json()["sessoes"][0]
    assert session["titulo"] == "Gerente · Sala" and session["cargo"] == "Gerente"
    run = runs_of(client)["a"]
    assert (run["cargo"], run["projeto"], run["rotulo"]) == ("Gerente", "Sala", "Gerente · Sala")


def test_old_database_gets_title_column(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    con = sqlite3.connect(tmp_path / "operations-room.db")
    con.execute("CREATE TABLE sessao (session_id TEXT PRIMARY KEY, cwd TEXT NOT NULL, "
                "ultimo_evento TEXT NOT NULL, ultima_atualizacao TEXT NOT NULL)")
    con.commit()
    con.close()
    init_db()
    con = sqlite3.connect(tmp_path / "operations-room.db")
    assert "titulo" in {row[1] for row in con.execute("PRAGMA table_info(sessao)")}
    con.close()


def test_title_absent_keeps_current_name(client):
    write_events(event("b", "SessionStart", "C:\\y", 1))
    run = runs_of(client)["b"]
    assert run["rotulo"] is None and run["tipo"] == "principal"


def test_api_with_manifest_closes_manual_registration(client, monkeypatch, tmp_path):
    found = manifest.parse(yaml.safe_load(SEDE_YAML), Path("C:/intoca"))
    monkeypatch.setattr("backend.api.manifesto.load", lambda *a, **k: found)
    write_events(event("c", "SessionStart", "C:\\intoca\\sala\\app", 1, "Executor · SAL-02 tema"),
                 event("d", "SessionStart", "C:\\intoca\\_infra\\painel", 2, "Gerente · Localhost"))
    assert client.get("/api/manifesto").json()["ativo"] is True
    assert [p["nome"] for p in client.get("/api/projetos").json()][:3] == ["Sede", "localhost", "sala-de-operacoes"]
    assert client.post("/api/projetos", json={"nome": "x", "caminho_local": "C:\\x"}).status_code == 409
    assert client.delete("/api/projetos/1").status_code == 409
    runs = runs_of(client)
    assert runs["c"]["projeto_nome"] == "sala-de-operacoes" and runs["c"]["projeto"] == "sala-de-operacoes"
    assert runs["c"]["rotulo"] == "Executor · SAL-02" and runs["c"]["frente"] == "operacao"
    assert runs["d"]["projeto_nome"] == "localhost"


def test_api_without_manifest_keeps_manual_mapping(client):
    assert client.get("/api/manifesto").json() == {"ativo": False}
    assert client.post("/api/projetos", json={"nome": "Sede", "caminho_local": "C:\\intoca"}).status_code == 201


# --- SAL-05: título em UTF-8 ------------------------------------------------

def test_repair_mojibake_titles():
    assert titulo.repair("Gerente Â· Sala") == "Gerente · Sala"
    assert titulo.repair("Executor Â· LOC-10 cwd") == "Executor · LOC-10 cwd"
    assert titulo.repair("AudiÃ§Ã£o") == "Audição"
    assert titulo.repair("Gerente · Sala") == "Gerente · Sala"
    assert titulo.repair("Audição Paulista") == "Audição Paulista"
    assert titulo.repair("AÇÃO") == "AÇÃO"
    assert titulo.parse("Gerente Â· Sala")["rotulo"] == "Gerente · Sala"
    assert titulo.parse("Executor Â· SAL-05 titulo", {"SAL": "sala"})["os_id"] == "SAL-05"


def test_hook_reads_stdin_as_utf8_bytes(tmp_path):
    hook = Path(__file__).resolve().parent.parent / "hooks" / "capture.py"
    env = {"AI_OPERATIONS_ROOM_DATA_DIR": str(tmp_path), "SYSTEMROOT": "C:\\Windows"}
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s9", "cwd": "C:\\x",
               "session_title": "Executor · SAL-05 audição"}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    done = subprocess.run([sys.executable, str(hook)], input=raw, capture_output=True, env=env, timeout=30)
    assert done.returncode == 0 and done.stdout == b"" and done.stderr == b""
    line = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["session_title"] == "Executor · SAL-05 audição"
