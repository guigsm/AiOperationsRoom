"""SAL-04: pendências do proprietário, OS por agente e permissão ao vivo."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import manifest
from backend import pendencias as pend
from backend.api import app
from backend.config import events_path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "hooks" / "capture.py"

FILA = """# Fila

## Ordens de serviço

| OS | Tema | Estado |
| --- | --- | --- |
| SAL-04 | depende de voce | em execução (noite) |
| SAL-05 | outra | escrita; aguarda "vai" |
| SAL-05 | repetida | concluída |

## Esperando o proprietário

| # | Tipo | Pedido | Onde responder | Desde | Estado |
| --- | --- | --- | --- | --- | --- |
| 1 | vai | "vai SAL-05" | chat Gerente | 2026-10-31 | aberto |
| 2 | conferir | olhar a tela | app | 2026-10-30 | feito 2026-10-31 |
| 3 | cartao | cartão do executor da SAL-04 | painel | 2026-10-31 | aberto |
| 4 | coisa-estranha | tipo desconhecido | app | 2026-10-31 | aberto |
| 5 | pode |
| 6 | decisao | sem estado ok | app | 2026-10-31 | Aberto |
"""


# --- leitor -------------------------------------------------------------------

def test_reads_only_open_rows_and_normalizes_type():
    lida = pend.ler_fila(FILA)
    assert [(x["numero"], x["tipo"]) for x in lida["esperando"]] == [(1, "vai"), (3, "cartao"), (4, "outro"), (6, "decisao")]
    assert lida["esperando"][0]["onde"] == "chat Gerente" and lida["esperando"][0]["estado"] == "aberto"


def test_missing_malformed_or_empty_sections_do_not_break():
    assert pend.ler_fila("") == {"esperando": [], "os": {}}
    assert pend.ler_fila("## Esperando o proprietário\n\nsem tabela\n")["esperando"] == []
    torta = "## Esperando o proprietário\n\n| # | Tipo |\n| - | - |\n| 1 | vai |\n"
    assert pend.ler_fila(torta)["esperando"] == []  # sem colunas Pedido e Estado
    assert pend.ler_arquivo(Path("Z:/nao/existe/fila.md")) is None


def test_os_table_first_row_wins_and_has_label():
    os_ = pend.ler_fila(FILA)["os"]
    assert os_["SAL-04"]["situacao"] == "andamento" and os_["SAL-04"]["estado"] == "em execução"
    assert os_["SAL-05"]["situacao"] == "aguarda-vai" and os_["SAL-05"]["estado"] == "aguarda o vai"


@pytest.mark.parametrize("texto,esperado", [
    ("concluída e aceita em 2026-10-13", "concluida"),
    ('escrita; aguarda "vai"', "aguarda-vai"),
    ("aguarda o “vai” do proprietário", "aguarda-vai"),
    ("espera o vai", "aguarda-vai"),
    ("aguarda integração", "aguarda-integracao"),
    ("entregue em 2026-10-26; falta integrar", "aguarda-integracao"),
    ("entregue em 2026-10-21, integrada na main", "concluida"),
    ('OS escrita; "vai" dado em 2026-10-25; cartão por spawn_task', "andamento"),
    ("em execução", "andamento"),
    ("a escrever", "a-escrever"),
    ("executada em 2026-10-17; relatório relatorios/X.md; aguarda aceite da Diretoria", "aguarda-integracao"),
    ("Aberta em 2026-10-19. Executada em 2026-10-19: relatório gravado", "concluida"),
    ('"Vai" do proprietário em 2026-10-19: ops/os/X.md. Executor por cartão.', "andamento"),
    ("executor aberto em 2026-10-27; R2 espera o e-mail", "andamento"),
    ("decidida em 2026-10-25; nada a executar agora", "outro"),
    ('em curso (noite): ALF contratado; ALF-02 escrita, espera "vai"; faltam outros', "andamento"),
    ("", "outro"),
    # fila da sala (SAL-03 e SAL-04 de ops/fila.md)
    ("**liberada em 2026-10-31**, **concluída com pendências, aceita pelo gerente em 2026-10-31**", "concluida"),
    ('OS escrita em os/X.md; **liberada** com o "vai" do proprietário; aguardando o proprietário abrir o chat', "a-escrever"),
])
def test_state_classification_matches_fila_ts(texto, esperado):
    assert pend.situacao_do_estado(texto) == esperado


def test_real_sala_queue_is_readable():
    fila = Path(r"C:\intoca\sala\ops\fila.md")
    if not fila.is_file():
        pytest.skip("fila da sala ausente")
    lida = pend.ler_fila(fila.read_text(encoding="utf-8"))
    assert {"SAL-01", "SAL-04"} <= set(lida["os"])


# --- hook ---------------------------------------------------------------------

def run_hook(tmp_path, payload) -> list[dict]:
    env = {"AI_OPERATIONS_ROOM_DATA_DIR": str(tmp_path / "hook"), "SYSTEMROOT": "C:\\Windows"}
    done = subprocess.run([sys.executable, str(CAPTURE)], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=30)
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""
    path = tmp_path / "hook" / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_hook_records_permission_request_with_minimal_fields(tmp_path):
    saved = run_hook(tmp_path, {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": "C:\\w",
                                "tool_name": "Write", "tool_input": {"file_path": "C:\\segredo.txt", "content": "x"},
                                "permission_suggestions": [{"type": "addRules"}], "transcript_path": "C:\\t.jsonl"})
    assert len(saved) == 1
    event = saved[0]
    assert event["evento"] == "PermissionRequest" and event["tool_name"] == "Write" and event["session_id"] == "s1"
    assert set(event) <= {"evento", "session_id", "cwd", "tool_name", "id", "t"}
    assert "segredo" not in json.dumps(event)


def test_hook_permission_without_extra_fields_and_notification_variant(tmp_path):
    saved = run_hook(tmp_path, {"hook_event_name": "PermissionRequest", "session_id": "s1"})
    assert saved[0]["evento"] == "PermissionRequest" and "tool_name" not in saved[0]
    saved = run_hook(tmp_path, {"hook_event_name": "Notification", "notification_type": "permission_prompt",
                                "session_id": "s1", "message": "Claude precisa de permissão para ler /x"})
    assert saved[1]["notification_type"] == "permission_prompt" and "message" not in saved[1]
    # outra notificação não é gravada
    saved = run_hook(tmp_path, {"hook_event_name": "Notification", "notification_type": "idle_prompt", "session_id": "s1"})
    assert len(saved) == 2


def test_hook_does_not_leak_tool_name_on_other_events(tmp_path):
    saved = run_hook(tmp_path, {"hook_event_name": "Stop", "session_id": "s2", "tool_name": "Bash", "prompt": "oi"})
    assert "tool_name" not in saved[0] and "prompt" not in saved[0]


# --- API ----------------------------------------------------------------------

def iso(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat(timespec="seconds")


def put(*items):
    with events_path().open("a", encoding="utf-8") as stream:
        for item in items:
            stream.write(json.dumps(item) + "\n")


def ev(sid, name, when, cwd="/w", **extra):
    return {"id": f"{sid}-{name}-{when}", "session_id": sid, "evento": name, "cwd": cwd, "t": when, **extra}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("AI_OPERATIONS_ROOM_SESSIONS_DIR", str(tmp_path / "vazio"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sede(tmp_path, monkeypatch):
    """Sede de teste com uma fila de projeto (sala) e uma da sede; filas copiadas, nunca as reais."""
    (tmp_path / "sede" / "diretoria").mkdir(parents=True)
    (tmp_path / "sala" / "ops").mkdir(parents=True)
    (tmp_path / "sala" / "ops" / "fila.md").write_text(FILA, encoding="utf-8")
    (tmp_path / "sede" / "diretoria" / "fila.md").write_text(
        "## Esperando o proprietário\n\n| # | Tipo | Pedido | Onde responder | Desde | Estado |\n| --- | --- | --- | --- | --- | --- |\n"
        "| 1 | pode | publicar X | chat da Diretoria | 2026-10-31 | aberto |\n", encoding="utf-8")
    found = manifest.parse({"projetos": [{"nome": "sala", "sigla": "SAL", "status": "ativo",
                                          "pasta_atual": str(tmp_path / "sala")}]}, tmp_path / "sede")
    monkeypatch.setattr("backend.api.manifesto.load", lambda *a, **k: found)
    return tmp_path


def test_api_without_manifest_is_empty_and_valid(client):
    body = client.get("/api/pendencias").json()
    assert body["pendencias"] == {"total": 0, "por_tipo": [], "por_projeto": []}
    assert body["agentes"] == [] and body["lido_em"]


def test_api_lists_open_rows_by_type_and_project(client, sede):
    body = client.get("/api/pendencias").json()["pendencias"]
    assert [g["tipo"] for g in body["por_tipo"]] == ["pode", "vai", "cartao", "decisao", "outro"]
    assert {g["projeto"] for g in body["por_projeto"]} == {"Sede", "sala"}
    vai = body["por_tipo"][1]["itens"][0]
    assert vai["projeto"] == "sala" and vai["numero"] == 1 and vai["onde"] == "chat Gerente"
    assert body["total"] == 5


def test_api_never_writes_queues(client, sede):
    antes = {p: p.read_bytes() for p in sede.rglob("fila.md")}
    client.get("/api/pendencias")
    client.get("/api/painel")
    assert {p: p.read_bytes() for p in sede.rglob("fila.md")} == antes


def test_card_row_disappears_when_executor_session_is_born(client, sede):
    def cartoes():
        itens = client.get("/api/pendencias").json()["pendencias"]["por_tipo"]
        return [i for g in itens if g["tipo"] == "cartao" for i in g["itens"]]
    assert len(cartoes()) == 1
    put(ev("e1", "SessionStart", iso(seconds=3), cwd=str(sede / "sala"), session_title="Executor · SAL-09 outro"))
    assert len(cartoes()) == 1  # outro ID não esconde
    put(ev("e2", "SessionStart", iso(seconds=2), cwd=str(sede / "sala"), session_title="Executor · SAL-04 depende"))
    assert cartoes() == []


def test_agent_gets_os_and_state_from_its_project_queue(client, sede):
    put(ev("e2", "SessionStart", iso(seconds=3), cwd=str(sede / "sala"), session_title="Executor · SAL-04 depende"),
        ev("g", "SessionStart", iso(seconds=3), cwd=str(sede / "sala"), session_title="Gerente · sala"))
    body = client.get("/api/pendencias").json()
    agents = {a["sessao"]: a for a in body["agentes"]}
    assert agents["e2"]["os_id"] == "SAL-04" and agents["e2"]["os_estado"] == "em execução"
    assert agents["g"]["os_id"] is None and agents["g"]["os_estado"] is None
    painel = client.get("/api/painel").json()
    item = next(r for r in painel["execucoes"] if r["session_id"] == "e2")
    assert item["os_id"] == "SAL-04" and item["os_estado"] == "em execução" and item["esperando_permissao"] is False
    sess = next(s for s in client.get("/api/sessoes").json()["sessoes"] if s["session_id"] == "e2")
    assert sess["os_estado"] == "em execução"


def test_waiting_permission_until_next_event(client):
    put(ev("p", "SessionStart", iso(seconds=9)), ev("p", "UserPromptSubmit", iso(seconds=8)),
        ev("p", "PermissionRequest", iso(seconds=7), tool_name="Write"))
    def waiting():
        run = next(r for r in client.get("/api/painel").json()["execucoes"] if r["session_id"] == "p")
        agent = next(a for a in client.get("/api/pendencias").json()["agentes"] if a["sessao"] == "p")
        assert run["esperando_permissao"] == agent["esperando_permissao"]
        return run["esperando_permissao"]
    assert waiting() is True
    put(ev("p", "Stop", iso(seconds=2)))
    assert waiting() is False


def test_waiting_permission_via_notification_and_ended_session(client):
    put(ev("n", "SessionStart", iso(seconds=9)),
        ev("n", "Notification", iso(seconds=7), notification_type="permission_prompt"))
    assert client.get("/api/pendencias").json()["agentes"][0]["esperando_permissao"] is True
    put(ev("n", "SessionEnd", iso(seconds=3)))
    assert client.get("/api/pendencias").json()["agentes"] == []
    assert client.get("/api/sessoes").json()["sessoes"][0]["esperando_permissao"] is False
