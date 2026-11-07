"""INT-07: faxina não vira boneco, nome do chat sem título, registro mesclado e hook enxuto."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend import registro
from backend import titulo as titulos
from backend.api import app
from backend.config import events_path
from backend.db import connect

RAIZ = Path(__file__).resolve().parents[1]


def at(minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def gravar(*eventos: dict) -> None:
    with events_path().open("a", encoding="utf-8") as stream:
        for evento in eventos:
            stream.write(json.dumps(evento) + "\n")


def base(sid="s"):
    return [
        {"id": f"{sid}-1", "evento": "SessionStart", "session_id": sid, "cwd": "C:/work/proj/app", "t": at(-5)},
        {"id": f"{sid}-2", "evento": "UserPromptSubmit", "session_id": sid, "cwd": "C:/work/proj/app", "t": at(-4)},
    ]


def chaves(client) -> set[str]:
    return {item["chave"] for item in client.get("/api/painel").json()["execucoes"]}


def test_faxina_sem_inicio_e_sem_tipo_nao_vira_boneco(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    gravar(*base(), {"id": "f1", "evento": "SubagentStop", "session_id": "s", "agent_id": "lixo", "cwd": "C:/work/proj/app", "t": at(-3)},
           {"id": "f2", "evento": "SubagentStop", "session_id": "s", "cwd": "C:/work/proj/app", "t": at(-2)})
    with TestClient(app) as client:
        assert chaves(client) == {"session:s"}
        with connect() as con:  # o registro continua inteiro: o filtro não apaga dado
            assert con.execute("SELECT COUNT(*) FROM evento WHERE nome = 'SubagentStop'").fetchone()[0] == 2
        assert client.get("/api/sessoes/s/agentes").json()["agentes"][0]["chave"] == "session:s"


def test_fim_com_tipo_ou_com_inicio_anterior_continua_boneco(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    gravar(*base(),
           {"id": "t1", "evento": "SubagentStop", "session_id": "s", "agent_id": "com-tipo", "agent_type": "intoca:revisor", "cwd": "C:/work/proj/app", "t": at(-3)},
           {"id": "i1", "evento": "SubagentStart", "session_id": "s", "agent_id": "com-inicio", "cwd": "C:/work/proj/app", "t": at(-3)},
           {"id": "i2", "evento": "SubagentStop", "session_id": "s", "agent_id": "com-inicio", "cwd": "C:/work/proj/app", "t": at(-2)})
    with TestClient(app) as client:
        assert chaves(client) == {"session:s", "agent:com-tipo", "agent:com-inicio"}


def test_faxina_ja_gravada_no_banco_some_na_leitura(monkeypatch, tmp_path):
    """Linha criada antes da INT-07 (fim sem início e sem tipo) não aparece, e o chat dela não ganha 'filhos'."""
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    gravar(*base())
    with TestClient(app) as client:
        client.get("/api/painel")
        with connect() as con:
            con.execute("INSERT INTO evento (id, session_id, nome, ocorrido_em, dados) VALUES ('old', 's', 'SubagentStop', ?, ?)",
                        (at(-3), json.dumps({"agent_id": "velho", "evento": "SubagentStop"})))
            con.execute("INSERT INTO execucao (chave, session_id, agent_id, pai_chave, tipo, cwd, estado, origem_encerramento, criado_em, atualizado_em) "
                        "VALUES ('agent:velho', 's', 'velho', 'session:s', 'subagente', 'C:/work/proj/app', 'concluida', 'SubagentStop', ?, ?)",
                        (at(-3), at(-3)))
        painel = client.get("/api/painel").json()
        assert {item["chave"] for item in painel["execucoes"]} == {"session:s"}
        assert all(item["chave"] != "agent:velho" for item in painel["historico"])


def test_nome_do_chat_sem_titulo(monkeypatch, tmp_path):
    assert titulos.parse_chat("Diretoria · InToca", "C:/x")["rotulo"] == "Diretoria · InToca"
    assert titulos.parse_chat("Corrigir o login", "C:/x")["rotulo"] == "Corrigir o login"
    assert titulos.parse_chat("", r"C:\Users\fulano\meu projeto\app")["rotulo"] == "Chat sem título · meu projeto/app"
    assert titulos.parse_chat(None, "/home/x/api")["rotulo"] == "Chat sem título · x/api"
    assert titulos.parse_chat(None, "C:\\")["rotulo"] == "Chat sem título"
    assert len(titulos.parse_chat("x" * 200, "C:/a")["rotulo"]) <= titulos.ROTULO_MAX
    assert "Claude" not in titulos.parse_chat(None, "")["rotulo"]
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path))
    gravar(*base("a"), {"id": "b1", "evento": "SessionStart", "session_id": "b", "cwd": "C:/work/proj/app", "session_title": "Revisar contrato", "t": at(-5)})
    with TestClient(app) as client:
        por_chat = {item["session_id"]: item["rotulo"] for item in client.get("/api/painel").json()["execucoes"]}
        assert por_chat == {"a": "Chat sem título · proj/app", "b": "Revisar contrato"}


def test_registrar_mescla_a_chave_animada(monkeypatch, tmp_path):
    caminho = tmp_path / "sala.json"
    monkeypatch.setenv(registro.REGISTRO_ENV, str(caminho))
    caminho.write_text(json.dumps({"classica": {"porta": 80}, "animada": {"porta": 1, "pid": 2, "extra": "fica", "auto": True}}), encoding="utf-8")
    registro.registrar(8766)
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["classica"] == {"porta": 80}
    assert dados["animada"]["porta"] == 8766 and dados["animada"]["extra"] == "fica" and dados["animada"]["auto"] is True
    assert set(dados["animada"]) >= {"porta", "pid", "iniciou_em", "versao"}
    registro.remover()  # tira só o que é nosso
    assert json.loads(caminho.read_text(encoding="utf-8"))["animada"] == {"extra": "fica", "auto": True}


def test_hook_nao_importa_modulos_pesados_e_sai_sem_saida(tmp_path):
    """O SessionEnd tem de responder em menos de 1 s: o hook só usa sys, os, json e time, e roda isolado (-I -S)."""
    codigo = ("import runpy,sys;sys.argv=['capture.py'];"
              "g=runpy.run_path(sys.argv[0] if False else r'%s',run_name='x');"
              "print(sorted(m for m in ('uuid','datetime','pathlib','tempfile','subprocess') if m in sys.modules))") % (RAIZ / "hooks" / "capture.py")
    saida = subprocess.run([sys.executable, "-I", "-S", "-c", codigo], capture_output=True, text=True, timeout=60)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]"
    payload = json.dumps({"hook_event_name": "SessionEnd", "session_id": "z", "cwd": "C:/w", "reason": "other"})
    env = {"AI_OPERATIONS_ROOM_DATA_DIR": str(tmp_path), "SystemRoot": r"C:\Windows"}
    feito = subprocess.run([sys.executable, "-I", "-S", str(RAIZ / "hooks" / "capture.py")], input=payload, text=True,
                           capture_output=True, env=env, timeout=60)
    assert feito.returncode == 0 and feito.stdout == "" and feito.stderr == ""
    gravado = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert gravado["evento"] == "SessionEnd" and gravado["reason"] == "other" and len(gravado["id"]) == 36


# ---------------------------------------------------------------- entrega 1: fonte única (Clássica no ar ou não)
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend import fonte, manifest


class _Classica(BaseHTTPRequestHandler):
    respostas: dict = {}

    def do_GET(self):  # noqa: N802
        corpo = self.respostas.get(self.path)
        if corpo is None:
            self.send_response(404)
            self.end_headers()
            return
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args):
        pass


@pytest.fixture
def classica(tmp_path, monkeypatch):
    sede, toca = tmp_path / "sede", tmp_path / "ouro"
    sede.mkdir(); toca.mkdir()
    (sede / "sede.yaml").write_text("projetos: []\n", encoding="utf-8")
    _Classica.respostas = {
        "/api/tocas": {"sede": True, "suite": None, "ordem": [], "lista": [
            {"kind": "site", "name": "ouro", "dir": str(toca), "suite": "operacao"},
            {"kind": "tool", "name": "ferramenta", "dir": str(tmp_path)}],
            "grupos": [{"id": "operacao", "titulo": "Operação", "descricao": "d", "tipo": "frente",
                        "itens": [{"toca": {"name": "ouro"}, "anexas": []}]}]},
        "/api/pendencias": {"sede": True, "total": 2, "ausentes": [], "fontes": [
            {"origem": "sede", "arquivo": "diretoria/fila.md", "lida": True,
             "abertas": [{"numero": "3", "tipo": "Pode", "pedido": "Publicar X", "onde": "chat", "desde": "2026-11-07", "estado": "aberto"}]},
            {"origem": "ouro", "arquivo": "ops/fila.md", "lida": True,
             "abertas": [{"numero": "", "tipo": "esquisito", "pedido": "Ver Y", "onde": "", "desde": "", "estado": "aberto"}]}]},
    }
    servidor = HTTPServer(("127.0.0.1", 0), _Classica)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    monkeypatch.setattr(manifest, "load", manifest.load_real)
    monkeypatch.setattr(manifest, "find", lambda *a, **k: (sede / "sede.yaml", "ponteiro"))
    monkeypatch.setattr(manifest, "load_from", lambda *a, **k: None)
    monkeypatch.setattr(fonte, "classica_porta", lambda: servidor.server_address[1])
    fonte._cache.clear()
    yield {"sede": sede, "toca": toca, "servidor": servidor}
    servidor.shutdown()
    servidor.server_close()


def test_com_a_classica_no_ar_tocas_e_pendencias_vem_da_api(classica, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    with TestClient(app) as client:
        assert client.get("/api/manifesto").json()["ativo"] is True
        salas = {p["nome"]: p for p in client.get("/api/projetos").json()}
        assert set(salas) == {"Sede", "ouro"}  # a ferramenta (kind tool) não é sala
        assert salas["ouro"]["frente"] == "operacao" and salas["ouro"]["frente_nome"] == "Operação"
        pend = client.get("/api/pendencias").json()
        assert pend["fonte"] == "classica"
        assert pend["pendencias"]["total"] == 2
        por_projeto = {g["projeto"]: g["itens"] for g in pend["pendencias"]["por_projeto"]}
        assert por_projeto["Sede"][0]["tipo"] == "pode" and por_projeto["Sede"][0]["numero"] == 3
        assert por_projeto["ouro"][0]["tipo"] == "outro"
        gravar(*base("c"))
        # o chat que está na pasta da Toca cai na sala dela
        gravar({"id": "k1", "evento": "SessionStart", "session_id": "k", "cwd": str(classica["toca"] / "src"), "t": at(-1)})
        sala_do_chat = {i["session_id"]: i["projeto_nome"] for i in client.get("/api/painel").json()["execucoes"]}
        assert sala_do_chat["k"] == "ouro"


def test_com_a_classica_fora_do_ar_a_leitura_propria_assume(classica, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    classica["servidor"].shutdown()
    classica["servidor"].server_close()
    fonte._cache.clear()
    proprio = {"salas": [{"id": "sede", "nome": "Sede", "sigla": "DIR", "caminho_local": str(classica["sede"]), "caminho_key": "k1",
                          "arquivado": 0, "frente": None, "frente_nome": None, "frente_descricao": None}],
               "frentes": [], "raiz": str(classica["sede"]), "origem": "ponteiro"}
    monkeypatch.setattr(manifest, "load_from", lambda *a, **k: proprio)
    with TestClient(app) as client:
        assert [p["nome"] for p in client.get("/api/projetos").json()] == ["Sede"]
        assert client.get("/api/pendencias").json()["fonte"] == "propria"


def test_sem_classica_registrada_nem_pergunta(monkeypatch):
    monkeypatch.setattr(fonte, "classica_porta", lambda: None)
    chamadas = []
    monkeypatch.setattr(fonte, "_buscar", lambda *a: chamadas.append(a))
    assert fonte.tocas() is None and fonte.pendencias() is None and chamadas == []


def test_resposta_invalida_da_classica_cai_na_reserva(classica, monkeypatch):
    _Classica.respostas["/api/tocas"] = {"sede": False, "lista": []}
    _Classica.respostas["/api/pendencias"] = ["nao", "e", "objeto"]
    fonte._cache.clear()
    assert fonte.tocas(str(classica["sede"])) is None
    assert fonte.pendencias() is None
