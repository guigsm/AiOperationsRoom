"""Fonte única de Tocas e pendências (INT-07): com a InToca Sala (Clássica) no ar, a Animada consome a API dela.

A Clássica registra a porta em ~/.intoca/sala.json. Estando no ar, `/api/tocas` e `/api/pendencias` dela dizem quais são as
Tocas e o que espera o proprietário, e a Animada deixa de ler manifesto e filas por conta própria nesses dois pontos. Sem a
Clássica (não registrada, fora do ar, resposta inválida), `tocas()` e `pendencias()` devolvem None e quem chama usa a leitura
própria de antes, como reserva. Só HTTP em loopback com tempo curto; nenhum código é compartilhado entre as duas.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from backend import registro

TEMPO_LIMITE = 0.8  # segundos por chamada: a Clássica é local, quem não responde nisso está fora do ar
VALIDADE = 3.0  # a tela pergunta a cada 4 s; dentro desta janela a resposta é reaproveitada
VALIDADE_FALHA = 10.0  # Clássica fora do ar: não insiste a cada ciclo
log = logging.getLogger("uvicorn.error")
_cache: dict[tuple[int, str], tuple[float, object]] = {}


def _agora() -> float:
    return time.monotonic()


def _buscar(porta: int, caminho: str) -> object | None:
    """GET JSON de http://127.0.0.1:<porta><caminho>, ou None. Reaproveita a resposta (ou a falha) por alguns segundos."""
    chave = (porta, caminho)
    guardado = _cache.get(chave)
    if guardado and _agora() < guardado[0]:
        return guardado[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=TEMPO_LIMITE) as resposta:
            if resposta.status != 200:
                raise ValueError(f"status {resposta.status}")
            dados = json.loads(resposta.read(2_000_000).decode("utf-8-sig"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        log.info("fonte: a Clássica na porta %s não respondeu a %s (%s); leitura própria como reserva", porta, caminho, exc)
        _cache[chave] = (_agora() + VALIDADE_FALHA, None)
        return None
    _cache[chave] = (_agora() + VALIDADE, dados)
    return dados


def classica_porta() -> int | None:
    return registro.classica_porta()


def _api(caminho: str) -> dict | None:
    porta = classica_porta()
    if porta is None:
        return None
    dados = _buscar(porta, caminho)
    return dados if isinstance(dados, dict) else None


def tocas(sede_raiz: str | None = None, siglas: dict[str, str] | None = None) -> dict | None:
    """As salas no formato do manifesto (salas, frentes, raiz) a partir de `/api/tocas`, ou None sem Clássica.

    `sede_raiz`: pasta da sede (o `/api/tocas` diz que há sede, não onde ela está); sem ela não há sala "Sede".
    `siglas`: nome da Toca -> sigla de OS, quando a Animada souber de outra fonte (a API não traz sigla).
    """
    dados = _api("/api/tocas")
    if not dados or dados.get("sede") is not True or not isinstance(dados.get("lista"), list):
        return None
    from backend.projects import path_key

    frente_de: dict[str, dict] = {}
    frentes = []
    for grupo in dados.get("grupos") or []:
        if isinstance(grupo, dict) and grupo.get("tipo") == "frente":
            frente = {"chave": str(grupo.get("id")), "nome": str(grupo.get("titulo") or grupo.get("id")),
                      "descricao": str(grupo.get("descricao") or ""), "membros": []}
            frentes.append(frente)
            for item in grupo.get("itens") or []:
                toca = item.get("toca") if isinstance(item, dict) else None
                if isinstance(toca, dict) and toca.get("name"):
                    frente["membros"].append(str(toca["name"]))
                    frente_de[str(toca["name"]).casefold()] = frente
    pares = [{"id": "sede", "nome": "Sede", "sigla": "DIR", "caminho_local": sede_raiz}] if sede_raiz else []
    for toca in dados["lista"]:
        if isinstance(toca, dict) and toca.get("kind") == "site" and toca.get("name") and toca.get("dir"):
            nome = str(toca["name"])
            pares.append({"id": nome, "nome": nome, "sigla": (siglas or {}).get(nome, ""), "caminho_local": str(toca["dir"]),
                          "suite": str(toca.get("suite") or "")})
    salas = []
    for sala in pares:
        try:
            chave = path_key(sala["caminho_local"])
        except ValueError:
            continue
        frente = frente_de.get(sala["nome"].casefold())
        salas.append({**sala, "caminho_key": chave, "arquivado": 0, "criado_em": "", "atualizado_em": "",
                      "frente": frente["chave"] if frente else None, "frente_nome": frente["nome"] if frente else None,
                      "frente_descricao": frente["descricao"] if frente else None})
    if len(salas) < 2:
        return None
    return {"salas": salas, "frentes": frentes, "raiz": sede_raiz or salas[0]["caminho_local"], "origem": "classica"}


def pendencias() -> list[dict] | None:
    """Linhas abertas de `/api/pendencias` (origem, tipo, pedido, onde, desde, numero), ou None sem Clássica."""
    dados = _api("/api/pendencias")
    if not dados or not isinstance(dados.get("fontes"), list):
        return None
    linhas = []
    for fonte in dados["fontes"]:
        if not isinstance(fonte, dict):
            continue
        for aberta in fonte.get("abertas") or []:
            if isinstance(aberta, dict) and aberta.get("pedido"):
                linhas.append({"origem": str(fonte.get("origem") or ""), **aberta})
    return linhas
