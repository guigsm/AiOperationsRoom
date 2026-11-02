"""Local API and static frontend for AI Operations Room."""

from __future__ import annotations

import functools
import logging
import sqlite3
from contextlib import asynccontextmanager
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import FRONTEND
from backend.db import connect, init_db
from backend.events import ingest as _ingest
from backend import manifest as manifesto
from backend import pendencias as filas_mod
from backend import projects
from backend import runs
from backend import titulo as titulos
from backend.reconcile import reconcile


class ProjectInput(BaseModel):
    nome: str
    caminho_local: str


def database() -> Iterator[sqlite3.Connection]:
    with connect() as con:
        yield con


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Operations Room", lifespan=lifespan)
log = logging.getLogger("uvicorn.error")


def ingest(con: sqlite3.Connection) -> int:
    """Ingestão em melhor esforço: banco travado por outro processo não derruba a rota, que serve o já gravado."""
    try:
        return _ingest(con)
    except sqlite3.OperationalError as exc:
        con.rollback()
        log.warning("ingest adiada: %s", exc)
        return 0


@app.exception_handler(sqlite3.OperationalError)
async def _banco_ocupado(_request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    log.warning("banco indisponível: %s", exc)
    return JSONResponse({"detail": "Banco ocupado; tente de novo em instantes."}, status_code=503)


@app.exception_handler(Exception)
async def _erro_interno(request: Request, exc: Exception) -> JSONResponse:
    log.error("erro em %s", request.url.path, exc_info=exc)
    return JSONResponse({"detail": "Erro interno do servidor."}, status_code=500)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


def _scope(con: sqlite3.Connection):
    """Rooms and the cwd resolver: from the manifest when there is one, else the manual mapping."""
    found = manifesto.load()
    if found:
        return found, found["salas"], lambda cwd: manifesto.resolve(cwd, found)
    mapped = projects.list_all(con)
    return None, mapped, lambda cwd: projects.resolve(cwd, mapped)


def _manual_only(deliver):
    """Manual registration is disabled while a manifest drives the rooms."""
    def guard(*args, **kwargs):
        if manifesto.load():
            raise HTTPException(status_code=409, detail="As salas vêm do manifesto da sede; o cadastro manual está desativado.")
        return deliver(*args, **kwargs)
    return functools.wraps(deliver)(guard)


@app.get("/api/manifesto")
def manifest_info() -> dict:
    found = manifesto.load()
    if not found:
        return {"ativo": False}
    return {"ativo": True, "origem": found.get("origem"), "frentes": found["frentes"]}


@app.get("/api/projetos")
def list_projects(con: sqlite3.Connection = Depends(database)) -> list[dict]:
    found, mapped, _ = _scope(con)
    if found:
        return [{key: room.get(key) for key in ("id", "nome", "sigla", "caminho_local", "arquivado", "frente", "frente_nome")}
                for room in mapped]
    return [projects.public(p) for p in mapped]


def _save(con: sqlite3.Connection, data: ProjectInput, project_id: int | None = None) -> dict:
    try:
        return projects.save(con, nome=data.nome, caminho_local=data.caminho_local,
                             project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Nome ou pasta já cadastrados.") from exc


@app.post("/api/projetos", status_code=201)
@_manual_only
def create_project(data: ProjectInput, con: sqlite3.Connection = Depends(database)) -> dict:
    return _save(con, data)


@app.put("/api/projetos/{project_id}")
@_manual_only
def update_project(project_id: int, data: ProjectInput,
                   con: sqlite3.Connection = Depends(database)) -> dict:
    if projects.get(con, project_id) is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return _save(con, data, project_id)


@app.post("/api/projetos/{project_id}/arquivar")
@_manual_only
def archive_project(project_id: int, con: sqlite3.Connection = Depends(database)) -> dict:
    return _set_archive(con, project_id, True)


@app.post("/api/projetos/{project_id}/desarquivar")
@_manual_only
def unarchive_project(project_id: int, con: sqlite3.Connection = Depends(database)) -> dict:
    return _set_archive(con, project_id, False)


def _set_archive(con: sqlite3.Connection, project_id: int, archived: bool) -> dict:
    if projects.get(con, project_id) is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    con.execute(
        "UPDATE projeto SET arquivado = ?, atualizado_em = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
        "WHERE id = ?", (int(archived), project_id),
    )
    return projects.public(projects.get(con, project_id))


@app.delete("/api/projetos/{project_id}")
@_manual_only
def delete_project(project_id: int, con: sqlite3.Connection = Depends(database)) -> dict:
    cursor = con.execute("DELETE FROM projeto WHERE id = ?", (project_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"removido": True}


@app.get("/api/sessoes")
def list_sessions(con: sqlite3.Connection = Depends(database)) -> dict:
    ingest(con)
    found, _mapped, resolve = _scope(con)
    siglas = _siglas(found)
    contexto = _contexto_os(con, found)
    rows = con.execute(
        "SELECT session_id, cwd, ultimo_evento, ultima_atualizacao, titulo "
        "FROM sessao WHERE cwd <> '' ORDER BY ultima_atualizacao DESC LIMIT 200"
    ).fetchall()
    sessions = []
    for row in rows:
        session = dict(row)
        session.update({key: value for key, value in titulos.parse(session["titulo"], siglas).items() if key != "projeto"})
        match = resolve(session["cwd"])
        session["projeto_id"] = match["id"] if match else None
        session["projeto_nome"] = match["nome"] if match else None
        _anotar(session, contexto, match)
        sessions.append(session)
    return {"sessoes": sessions}


def _contexto_os(con: sqlite3.Connection, found: dict | None) -> dict:
    """Filas lidas (só leitura), sessões esperando permissão e IDs de OS que já têm executor com título."""
    executores = {titulos.parse(row["titulo"]).get("os_id") for row in con.execute("SELECT titulo FROM sessao WHERE titulo <> ''")}
    return {"filas": filas_mod.ler_filas(found), "esperando": runs.waiting_permission(con),
            "executores": {item for item in executores if item},
            "sala_por_nome": {room["nome"]: room["id"] for room in (found["salas"] if found else [])}}


def _anotar(item: dict, contexto: dict, match: dict | None) -> None:
    """os_estado, os_situacao e esperando_permissao no item de uma sessão ou execução principal."""
    principal = item.get("pai_chave") is None
    sala = contexto["sala_por_nome"].get(item.get("projeto") or "") or (match["id"] if match else None)
    linha = filas_mod.os_da_sala(contexto["filas"], sala, item.get("os_id")) if principal else None
    item["os_estado"] = linha["estado"] if linha else None
    item["os_situacao"] = linha["situacao"] if linha else None
    item["esperando_permissao"] = bool(principal and item.get("session_id") in contexto["esperando"])


def _siglas(found: dict | None) -> dict[str, str]:
    return {room["sigla"]: room["nome"] for room in (found["salas"] if found else []) if room.get("sigla")}


@app.get("/api/painel")
def dashboard(horas: int = Query(6, ge=1, le=24),
              convivencia: int = Query(12, ge=0, le=24),
              con: sqlite3.Connection = Depends(database)) -> dict:
    ingest(con)
    reconcile(con)
    found, _mapped, resolve = _scope(con)
    siglas = _siglas(found)
    chat_titles = {row["session_id"]: row["titulo"] for row in con.execute("SELECT session_id, titulo FROM sessao WHERE titulo <> ''")}
    now = datetime.now(timezone.utc)
    window = (now - timedelta(hours=horas)).isoformat(timespec="seconds")
    visible = (now - timedelta(hours=convivencia)).isoformat(timespec="seconds")
    rows = con.execute(
        "SELECT * FROM execucao WHERE estado IN ('trabalhando', 'delegando', 'aguardando', 'ocioso') "
        "OR julianday(criado_em) >= julianday(?) OR julianday(atualizado_em) >= julianday(?) "
        "ORDER BY atualizado_em DESC", (window, visible)
    ).fetchall()
    contexto = _contexto_os(con, found)
    items = []
    for row in rows:
        match = resolve(row["cwd"])
        item = runs.public(row, match)
        # Only the main chat carries the title; subagents keep the type the room already shows.
        if item["pai_chave"] is None:
            item["titulo"] = chat_titles.get(item["session_id"], "")
            item.update(titulos.parse(item["titulo"], siglas))
        _anotar(item, contexto, match)
        items.append(item)
    active = runs.ACTIVE
    summary_items = [item for item in items if item["estado"] in active or
                     _in_window(item["criado_em"], window) or _in_window(item["atualizado_em"], window)]
    principals_with_children = {row["pai_chave"] for row in con.execute(
        "SELECT DISTINCT pai_chave FROM execucao WHERE pai_chave IS NOT NULL"
    )}
    room_items = [item for item in items if item["estado"] in active or item["estado"] == runs.IDLE or
                  (convivencia and _in_window(item["atualizado_em"], visible) and
                   (item["pai_chave"] is not None or item["chave"] in principals_with_children or
                    _duration(item) >= 30))]
    history: dict[str, list[dict]] = {}
    for item in sorted(summary_items, key=lambda x: x["criado_em"], reverse=True):
        history.setdefault(item["tipo"], []).append(item)
    history = {kind: entries[:50] for kind, entries in history.items()}
    return {
        "horas": horas,
        "convivencia": convivencia,
        "frentes": [{key: front.get(key) for key in ("chave", "nome", "descricao")}
                    for front in (found["frentes"] if found else [])],
        "execucoes": room_items,
        "historico": summary_items,
        "historico_tipos": history,
        "sessoes": [item for item in summary_items if item["pai_chave"] is None],
        "resumo": {
            **{state: sum(item["estado"] == state for item in summary_items)
               for state in ("trabalhando", "delegando", "aguardando", "ocioso", "concluida", "orfa")},
            "sessoes_ativas": len({item["session_id"] for item in summary_items if item["estado"] in active}),
            "execucoes_na_janela": len(summary_items),
        },
    }


def _in_window(value: str, cutoff: str) -> bool:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) >= datetime.fromisoformat(cutoff)
    except (AttributeError, ValueError, TypeError):
        return False


def _duration(item: dict) -> float:
    try:
        start = datetime.fromisoformat(item["criado_em"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["atualizado_em"].replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except (AttributeError, ValueError, TypeError):
        return 0


@app.get("/api/pendencias")
def pending(con: sqlite3.Connection = Depends(database)) -> dict:
    """O que depende do proprietário (seções das filas) e o que cada agente faz. Só lê as filas."""
    ingest(con)
    reconcile(con)
    found, _mapped, resolve = _scope(con)
    siglas = _siglas(found)
    contexto = _contexto_os(con, found)
    titles = {row["session_id"]: row["titulo"] for row in con.execute("SELECT session_id, titulo FROM sessao")}
    agents = []
    for row in con.execute(
        "SELECT * FROM execucao WHERE pai_chave IS NULL AND estado IN ('trabalhando', 'delegando', 'aguardando', 'ocioso') "
        "ORDER BY atualizado_em DESC"
    ):
        match = resolve(row["cwd"])
        item = runs.public(row, match)
        item["titulo"] = titles.get(row["session_id"], "")
        item.update(titulos.parse(item["titulo"], siglas))
        _anotar(item, contexto, match)
        agents.append({"sessao": item["session_id"], "personagem": item["rotulo"], "projeto": item["projeto_nome"],
                       "os_id": item["os_id"], "os_estado": item["os_estado"], "os_situacao": item["os_situacao"],
                       "estado": item["estado"], "esperando_permissao": item["esperando_permissao"]})
    return {"pendencias": filas_mod.pendencias(found, contexto["filas"], contexto["executores"]),
            "agentes": agents, "lido_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@app.get("/api/sessoes/{session_id}/historico")
def session_history(session_id: str, con: sqlite3.Connection = Depends(database)) -> dict:
    ingest(con)
    rows = con.execute(
        "SELECT id, nome, ocorrido_em, dados FROM evento WHERE session_id = ? "
        "ORDER BY ocorrido_em DESC, id DESC LIMIT 100", (session_id,)
    ).fetchall()
    return {"eventos": [dict(row) for row in rows]}


@app.get("/api/sessoes/{session_id}/agentes")
def session_agents(session_id: str, con: sqlite3.Connection = Depends(database)) -> dict:
    ingest(con)
    rows = con.execute(
        "SELECT * FROM execucao WHERE session_id = ? ORDER BY pai_chave, criado_em", (session_id,)
    ).fetchall()
    return {"agentes": [dict(row) for row in rows]}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/projetos")
def projects_page() -> FileResponse:
    return FileResponse(FRONTEND / "projects.html")


@app.get("/como-utilizar")
def how_to_page() -> FileResponse:
    return FileResponse(FRONTEND / "how-to.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="127.0.0.1", port=8765)
