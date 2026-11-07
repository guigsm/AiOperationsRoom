"""Optional InToca manifest (sede.yaml): one room per active project."""

from __future__ import annotations

import os
import re
from pathlib import Path

from backend.config import ROOT
from backend.projects import path_key

SEDE_ENV = "INTOCA_SEDE"
MANIFEST_NAME = "sede.yaml"
_cache: dict = {"path": None, "mtime": None, "value": None}


def _candidate(base: str | Path) -> Path | None:
    path = Path(str(base)).expanduser()
    path = path if path.name.lower() == MANIFEST_NAME else path / MANIFEST_NAME
    return path if path.is_file() else None


def find(start: Path = ROOT, environ=os.environ, home: Path | None = None) -> tuple[Path, str] | None:
    """Return (sede.yaml, how it was found): INTOCA_SEDE, ~/.intoca/sede pointer, then walking up."""
    if environ.get(SEDE_ENV):
        found = _candidate(environ[SEDE_ENV])
        if found:
            return found, "variavel"
    pointer = (home or Path.home()) / ".intoca" / "sede"
    try:
        found = _candidate(pointer.read_text(encoding="utf-8").strip()) if pointer.is_file() else None
    except OSError:
        found = None
    if found:
        return found, "ponteiro"
    for folder in [start, *start.parents]:
        found = _candidate(folder)
        if found:
            return found, "subida"
    return None


def _read(path: Path) -> dict | None:
    try:
        import yaml  # optional dependency: without it the room falls back to cwd mapping
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse(data: dict, root: Path) -> dict | None:
    """Rooms from a loaded manifest: the sede itself plus every project with status ativo."""
    fronts: dict[str, dict] = {}
    suite = data.get("suite")
    raw_fronts = suite.get("frentes") if isinstance(suite, dict) else None
    for key, front in (raw_fronts.items() if isinstance(raw_fronts, dict) else []):
        if isinstance(front, dict):
            fronts[str(key)] = {"chave": str(key), "nome": _text(front.get("nome")) or str(key),
                                "descricao": _text(front.get("descricao")),
                                "membros": [str(m) for m in front.get("membros") or []]}
    front_of = {member.casefold(): front for front in fronts.values() for member in front["membros"]}
    rooms = [{"id": "sede", "nome": "Sede", "sigla": "DIR", "caminho_local": str(root)}]
    for item in data.get("projetos") or []:
        if not isinstance(item, dict) or _text(item.get("status")) != "ativo":
            continue
        name, folder = _text(item.get("nome")), _text(item.get("pasta_atual"))
        if name and folder:
            rooms.append({"id": name, "nome": name, "sigla": _text(item.get("sigla")), "caminho_local": folder,
                          "suite": _text(item.get("suite"))})
    result = []
    for room in rooms:
        try:
            key = path_key(room["caminho_local"])
        except ValueError:
            continue
        front = front_of.get(room["id"].casefold())
        result.append({**room, "caminho_key": key, "arquivado": 0, "criado_em": "", "atualizado_em": "",
                       "frente": front["chave"] if front else None,
                       "frente_nome": front["nome"] if front else None,
                       "frente_descricao": front["descricao"] if front else None})
    if len(result) < 2:
        return None
    return {"salas": result, "frentes": list(fronts.values()), "raiz": str(root)}


def load() -> dict | None:
    """Rooms of this machine: from the InToca Sala (Classica) API when it is up (INT-07), else the manifest (see load_from)."""
    from backend import fonte

    if fonte.classica_porta() is not None:
        proprio = load_from()  # sede e siglas: a API diz quais sao as Tocas, nao onde fica a sede nem as siglas de OS
        located = find()
        siglas = {room["nome"]: room["sigla"] for room in (proprio or {}).get("salas", []) if room.get("sigla")}
        vindo = fonte.tocas(str(located[0].parent) if located else None, siglas)
        if vindo:
            return vindo
        return proprio
    return load_from()


def load_from(start: Path = ROOT, environ=os.environ, home: Path | None = None) -> dict | None:
    """Manifest rooms or None (no sede found, unreadable, no PyYAML): callers fall back to cwd mapping."""
    located = find(start, environ, home)
    if located is None:
        return None
    path, how = located
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["value"]
    data = _read(path)
    value = parse(data, path.parent) if data else None
    if value:
        value = {**value, "origem": how, "arquivo": str(path)}
    _cache.update(path=path, mtime=mtime, value=value)
    return value


def worktree_repo(cwd: str, root: Path) -> str | None:
    """Repository folder behind cwd when cwd is inside <sede>/_worktrees/<name>; None otherwise."""
    base = root / "_worktrees"
    try:
        target = Path(cwd)
        relative = target.relative_to(base)
    except (ValueError, OSError):
        return None
    if not relative.parts:
        return None
    marker = base / relative.parts[0] / ".git"
    try:
        text = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    except OSError:
        return None
    found = re.match(r"gitdir:\s*(.+?)[/\\]\.git[/\\]worktrees[/\\]", text.strip())
    return found.group(1) if found else None


def resolve(cwd: str, manifest: dict) -> dict | None:
    """Room for cwd: worktrees resolve to the owner project, otherwise the most specific folder wins."""
    from backend import projects
    owner = worktree_repo(cwd, Path(manifest["raiz"]))
    return projects.resolve(owner or cwd, manifest["salas"])
