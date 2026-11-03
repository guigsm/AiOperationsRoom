"""INT-04: porta por flag ou variável, registro em sala.json, saúde com `pronta` e porta da Clássica."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from backend import registro
from backend.api import app
from backend.cli import main


@pytest.fixture
def sala_json(tmp_path, monkeypatch):
    path = tmp_path / "intoca" / "sala.json"
    monkeypatch.setenv(registro.REGISTRO_ENV, str(path))
    monkeypatch.delenv(registro.PORT_ENV, raising=False)
    return path


def test_porta_padrao_variavel_e_flag(monkeypatch):
    monkeypatch.delenv(registro.PORT_ENV, raising=False)
    assert registro.porta_configurada(None) == 8765
    monkeypatch.setenv(registro.PORT_ENV, "8766")
    assert registro.porta_configurada(None) == 8766
    assert registro.porta_configurada(9000) == 9000  # a flag vence a variável


@pytest.mark.parametrize("valor", ["abc", "0", "70000"])
def test_variavel_de_porta_invalida_para_com_mensagem(monkeypatch, valor):
    monkeypatch.setenv(registro.PORT_ENV, valor)
    with pytest.raises(SystemExit) as erro:
        registro.porta_configurada(None)
    assert registro.PORT_ENV in str(erro.value)


def test_serve_usa_a_flag_e_publica_a_porta_no_ambiente(monkeypatch, tmp_path, sala_json):
    chamadas = []
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: chamadas.append((a, k)))
    monkeypatch.setattr("sys.argv", ["x", "serve", "--port", "8766", "--data-dir", str(tmp_path)])
    try:
        assert main() == 0
        assert chamadas[0][1]["port"] == 8766
        assert chamadas[0][1]["host"] == "127.0.0.1"
        assert os.environ[registro.PORT_ENV] == "8766"
    finally:
        os.environ.pop(registro.PORT_ENV, None)
        os.environ.pop("AI_OPERATIONS_ROOM_DATA_DIR", None)


def test_registra_preserva_o_resto_e_remove_so_a_propria_entrada(sala_json):
    sala_json.parent.mkdir(parents=True)
    sala_json.write_text(json.dumps({"classica": {"porta": 80}, "controle": False}), encoding="utf-8")
    registro.registrar(8766)
    dados = json.loads(sala_json.read_text(encoding="utf-8"))
    assert dados["classica"] == {"porta": 80} and dados["controle"] is False
    assert dados["animada"]["porta"] == 8766 and dados["animada"]["pid"] == os.getpid()
    assert {"iniciou_em", "versao"} <= dados["animada"].keys()
    assert not list(sala_json.parent.glob("*.tmp"))  # gravação atômica não deixa temporário
    registro.remover()
    assert json.loads(sala_json.read_text(encoding="utf-8")) == {"classica": {"porta": 80}, "controle": False}


def test_registra_cria_o_arquivo_e_nao_remove_entrada_de_outro_processo(sala_json):
    registro.registrar(8766)
    assert sala_json.exists()
    dados = json.loads(sala_json.read_text(encoding="utf-8"))
    dados["animada"]["pid"] = os.getpid() + 1
    sala_json.write_text(json.dumps(dados), encoding="utf-8")
    registro.remover()
    assert "animada" in json.loads(sala_json.read_text(encoding="utf-8"))


def test_arquivo_corrompido_nao_derruba_o_registro(sala_json):
    sala_json.parent.mkdir(parents=True)
    sala_json.write_text("{não é json", encoding="utf-8")
    registro.registrar(8766)
    assert json.loads(sala_json.read_text(encoding="utf-8"))["animada"]["porta"] == 8766


def test_ciclo_de_vida_registra_ao_subir_e_remove_ao_sair(sala_json, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv(registro.PORT_ENV, "8766")
    with TestClient(app):
        assert json.loads(sala_json.read_text(encoding="utf-8"))["animada"]["porta"] == 8766
    assert "animada" not in json.loads(sala_json.read_text(encoding="utf-8"))


def test_sem_porta_no_ambiente_o_app_nao_toca_em_sala_json(sala_json, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    with TestClient(app):
        pass
    assert not sala_json.exists()


def test_saude_traz_versao_e_fica_pronta_depois_da_primeira_ingestao(sala_json, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OPERATIONS_ROOM_DATA_DIR", str(tmp_path / "dados"))
    with TestClient(app) as cliente:
        dados = cliente.get("/api/health").json()
        assert dados["ok"] is True and dados["versao"] == registro.VERSAO
        for _ in range(100):
            if cliente.get("/api/health").json()["pronta"]:
                break
            import time; time.sleep(0.05)
        assert cliente.get("/api/health").json()["pronta"] is True


def test_classica_le_a_porta_registrada_e_some_sem_registro(sala_json):
    with TestClient(app) as cliente:
        assert cliente.get("/api/classica").json() == {"porta": None}
        sala_json.parent.mkdir(parents=True, exist_ok=True)
        sala_json.write_text(json.dumps({"classica": {"porta": 8080, "pid": 1}}), encoding="utf-8")
        assert cliente.get("/api/classica").json() == {"porta": 8080}
        sala_json.write_text(json.dumps({"classica": {"porta": "x"}}), encoding="utf-8")
        assert cliente.get("/api/classica").json() == {"porta": None}


def test_titulo_da_tela_e_o_novo_nome():
    from backend.config import FRONTEND
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "<title>AI Operations Room · InToca</title>" in html
    assert "/static/classica.js" in html
