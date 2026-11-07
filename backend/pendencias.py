"""Filas do manifesto (só leitura): "Esperando o proprietário" e o estado das OS de cada agente.

Leitor puro e tolerante: arquivo faltando, tabela ausente ou linha malformada nunca derrubam a resposta.
A classificação do estado por texto é o porte de `situacaoDoEstado` (plugin intoca-sala, hooks/fila.ts).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

TIPOS = ("pode", "vai", "cartao", "abrir-chat", "arquivar", "permissao", "decisao", "conferir")
SECAO = "esperando o proprietario"
ID_DE_OS = re.compile(r"^([A-Za-z][A-Za-z0-9]*-\d+[A-Za-z]?)(?![A-Za-z0-9])")
ID_NO_TEXTO = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,8}-\d+[A-Za-z]?)(?![A-Za-z0-9])")
SEPARADOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
LIMITE_LINHAS = 4000

ROTULOS = {"andamento": "em execução", "aguarda-vai": "aguarda o vai", "aguarda-integracao": "aguarda integração",
           "concluida": "concluída", "a-escrever": "a escrever", "outro": None}


def limpar(celula: str) -> str:
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", celula)
    texto = re.sub(r"\*\*|__", "", texto).replace("`", "").replace("\\|", "|")
    texto = re.sub(r"[\x00-\x1f\x7f]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto)
    base = re.sub("[̀-ͯ]", "", base)
    return re.sub("[“”‘’\"']", "", base).lower()


def _celulas(linha: str) -> list[str]:
    texto = re.sub(r"^\|", "", linha.strip())
    fim = texto[:-1] if texto.endswith("|") and not texto.endswith("\\|") else texto
    saida, atual, crase = [], "", False
    for i, c in enumerate(fim):
        if c == "`":
            crase = not crase
        if c == "|" and not crase and (i == 0 or fim[i - 1] != "\\"):
            saida.append(atual)
            atual = ""
            continue
        atual += c
    saida.append(atual)
    return [limpar(item) for item in saida]


def ler_tabelas(texto: str) -> list[dict]:
    """Todas as tabelas: {secao, cabecalho, linhas}. Linha curta é completada; a longa junta o excesso no fim."""
    linhas = texto.lstrip("﻿").splitlines()[:LIMITE_LINHAS]
    tabelas, secao, i = [], "", 0
    while i < len(linhas):
        linha = linhas[i]
        titulo = re.match(r"^#{1,6}\s+(.*)$", linha)
        if titulo:
            secao = limpar(titulo.group(1))
        elif linha.lstrip().startswith("|") and i + 1 < len(linhas) and SEPARADOR.match(linhas[i + 1].strip()):
            cabecalho = _celulas(linha)
            corpo, j = [], i + 2
            while j < len(linhas) and linhas[j].lstrip().startswith("|"):
                c = _celulas(linhas[j])
                if len(c) > len(cabecalho):
                    sobra = c[len(cabecalho) - 1:]
                    c = c[:len(cabecalho) - 1] + [" | ".join(sobra)]
                c += [""] * (len(cabecalho) - len(c))
                corpo.append(c)
                j += 1
            tabelas.append({"secao": secao, "cabecalho": cabecalho, "linhas": corpo})
            i = j - 1
        i += 1
    return tabelas


def coluna(cabecalho: list[str], trecho: str) -> int:
    for i, nome in enumerate(cabecalho):
        if trecho in sem_acento(nome):
            return i
    return -1


def situacao_do_estado(estado: str) -> str:
    """Porte de `situacaoDoEstado` (fila.ts): andamento, aguarda-vai, aguarda-integracao, concluida, a-escrever, outro."""
    t = sem_acento(estado or "")
    f = re.ASCII
    if re.search(r"^\s*(?:\*\*)?(?:em curso|em execu)", t, f):
        return "andamento"
    if re.search(r"aguarda\w*\s+(?:o\s+|a\s+)?vai\b", t, f) or re.search(r"espera\w*\s+(?:o\s+)?vai\b", t, f):
        return "aguarda-vai"
    if re.search(r"aguarda\w*\s+(?:a\s+|o\s+)?(?:integra[cç]|aceite)|pronta?\s+para\s+integrar|aguarda\w*\s+merge", t, f):
        return "aguarda-integracao"
    if re.search(r"(?:^|[^a-z])(?:concluid|integrad|cumprid|fechad|arquivad|executad|aceit[ao])", t, f):
        return "concluida"
    if re.search(r"(?:^|[^a-z])entregue", t, f):
        return "aguarda-integracao"
    if re.search(r"em execu|em curso|executand|vai dado|cartao por|em andamento|executor (?:aberto|por cartao)"
                 r"|vai (?:do proprietario )?em \d", t, f):
        return "andamento"
    if re.search(r"a escrever|escrit[ao]|a abrir|a contratar", t, f):
        return "a-escrever"
    return "outro"


def _esperando(tabela: dict) -> list[dict]:
    cab = tabela["cabecalho"]
    i = {nome: coluna(cab, nome) for nome in ("tipo", "pedido", "onde", "desde", "estado")}
    if i["tipo"] < 0 or i["pedido"] < 0 or i["estado"] < 0:
        return []
    saida = []
    for c in tabela["linhas"]:
        if not sem_acento(c[i["estado"]]).startswith("aberto") or not c[i["pedido"]]:
            continue
        tipo = sem_acento(c[i["tipo"]]).strip()
        numero = c[0].strip() if c and i["tipo"] != 0 else ""
        saida.append({
            "numero": int(numero) if numero.isdigit() else (numero or None),
            "tipo": tipo if tipo in TIPOS else "outro",
            "pedido": c[i["pedido"]],
            "onde": c[i["onde"]] if i["onde"] >= 0 else "",
            "desde": c[i["desde"]] if i["desde"] >= 0 else "",
            "estado": "aberto",
        })
    return saida


def _os(tabela: dict) -> dict[str, dict]:
    cab = tabela["cabecalho"]
    if sem_acento(cab[0] if cab else "") != "os" or coluna(cab, "estado") < 0:
        return {}
    i_estado, i_tema = coluna(cab, "estado"), coluna(cab, "tema")
    saida: dict[str, dict] = {}
    for c in tabela["linhas"]:
        achado = ID_DE_OS.match(c[0] if c else "")
        if not achado:
            continue
        chave = achado.group(1).upper()
        if chave in saida:  # a primeira linha de um ID vale; repetição é histórico
            continue
        estado = c[i_estado]
        situacao = situacao_do_estado(estado)
        saida[chave] = {"id": achado.group(1), "tema": c[i_tema] if i_tema >= 0 else "", "estado_texto": estado,
                        "situacao": situacao, "estado": ROTULOS[situacao]}
    return saida


def ler_fila(texto: str) -> dict:
    """Texto de uma fila → {'esperando': [...], 'os': {ID: linha}}. Nunca lança."""
    esperando, os_ = [], {}
    try:
        for tabela in ler_tabelas(texto):
            if sem_acento(tabela["secao"]).strip() == SECAO:
                esperando += _esperando(tabela)
            else:
                for chave, linha in _os(tabela).items():
                    os_.setdefault(chave, linha)
    except Exception:
        return {"esperando": [], "os": {}}
    return {"esperando": esperando, "os": os_}


_cache: dict[Path, tuple[tuple, dict]] = {}


def ler_arquivo(caminho: Path) -> dict | None:
    """Fila em disco (leitura com cache por mtime e tamanho); None se o arquivo não existe ou não abre."""
    try:
        info = caminho.stat()
        marca = (info.st_mtime_ns, info.st_size)
        if caminho in _cache and _cache[caminho][0] == marca:
            return _cache[caminho][1]
        valor = ler_fila(caminho.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return None
    _cache[caminho] = (marca, valor)
    return valor


def caminho_da_fila(sala: dict) -> Path:
    base = Path(sala["caminho_local"])
    return base / "diretoria" / "fila.md" if sala.get("id") == "sede" else base / "ops" / "fila.md"


def ler_filas(manifesto: dict | None) -> dict[str, dict]:
    """{id da sala: fila lida} para as salas do manifesto cuja fila existe. Sem manifesto, vazio."""
    filas = {}
    for sala in (manifesto or {}).get("salas", []):
        lida = ler_arquivo(caminho_da_fila(sala))
        if lida is not None:
            filas[sala["id"]] = lida
    return filas


def os_da_sala(filas: dict[str, dict], sala_id: str | None, os_id: str | None) -> dict | None:
    if not sala_id or not os_id:
        return None
    return filas.get(sala_id, {}).get("os", {}).get(os_id.upper())


def _linhas_da_api(manifesto: dict | None, externas: list[dict]) -> dict[str, list[dict]]:
    """Linhas de `/api/pendencias` da Clássica por id de sala (origem `sede` é a sala `sede`; as demais, pelo nome)."""
    por_nome = {sala["nome"].casefold(): sala["id"] for sala in (manifesto or {}).get("salas", [])}
    saida: dict[str, list[dict]] = {}
    for linha in externas:
        origem = str(linha.get("origem") or "")
        sala_id = "sede" if origem == "sede" else por_nome.get(origem.casefold())
        if sala_id is None:
            continue
        tipo = sem_acento(str(linha.get("tipo") or "")).strip()
        numero = str(linha.get("numero") or "").strip()
        saida.setdefault(sala_id, []).append({
            "numero": int(numero) if numero.isdigit() else (numero or None),
            "tipo": tipo if tipo in TIPOS else "outro", "pedido": str(linha.get("pedido") or ""),
            "onde": str(linha.get("onde") or ""), "desde": str(linha.get("desde") or ""), "estado": "aberto",
        })
    return saida


def pendencias(manifesto: dict | None, filas: dict[str, dict], titulos_de_executor: set[str],
               externas: list[dict] | None = None) -> dict:
    """Pendências abertas por tipo e por projeto. Linha `cartao` some se já nasceu o executor da OS citada.

    `externas`: linhas já lidas pela InToca Sala (INT-07); com elas, as filas locais não são consultadas para as pendências.
    """
    itens = []
    da_api = _linhas_da_api(manifesto, externas) if externas is not None else None
    for sala in (manifesto or {}).get("salas", []):
        for linha in (da_api.get(sala["id"], []) if da_api is not None else filas.get(sala["id"], {}).get("esperando", [])):
            if linha["tipo"] == "cartao" and {m.upper() for m in ID_NO_TEXTO.findall(linha["pedido"])} & titulos_de_executor:
                continue
            itens.append({"projeto": sala["nome"], "projeto_id": sala["id"], **linha})
    por_tipo = [{"tipo": tipo, "itens": [x for x in itens if x["tipo"] == tipo]} for tipo in (*TIPOS, "outro")]
    projetos = list(dict.fromkeys(x["projeto_id"] for x in itens))
    return {
        "total": len(itens),
        "por_tipo": [grupo for grupo in por_tipo if grupo["itens"]],
        "por_projeto": [{"projeto": next(x["projeto"] for x in itens if x["projeto_id"] == pid), "projeto_id": pid,
                         "itens": [x for x in itens if x["projeto_id"] == pid]} for pid in projetos],
    }
