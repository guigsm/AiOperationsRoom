"""Character name from the chat title: "Cargo · Projeto" or "Executor · ID tema"."""

from __future__ import annotations

import re

CARGOS = {"diretoria": "Diretoria", "gerente": "Gerente", "plantão": "Plantão", "plantao": "Plantão",
          "assistente": "Assistente", "secretaria": "Secretaria", "executor": "Executor"}
OS_ID = re.compile(r"^([A-Za-z]{2,8}-\d+[A-Za-z]?)(?:\s+(.*))?$")


def repair(title: str) -> str:
    """Undo UTF-8 text decoded as cp1252 (hook bug before SAL-05); correct titles come back unchanged."""
    if "Â" not in title and "Ã" not in title:
        return title
    try:
        return title.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return title


def parse(title: str | None, siglas: dict[str, str] | None = None) -> dict:
    """Return cargo, projeto, os_id and rotulo; every value is None when the title is absent or off-pattern.

    siglas maps an OS prefix (SAL) to a project name, used for Executor titles that carry only the ID.
    """
    empty = {"cargo": None, "projeto": None, "os_id": None, "rotulo": None}
    if not isinstance(title, str):
        return empty
    parts = [part.strip() for part in repair(title).split("·")]
    cargo = CARGOS.get(parts[0].casefold()) if len(parts) > 1 else None
    if cargo is None or not parts[1]:
        return empty
    if cargo == "Executor":
        found = OS_ID.match(parts[1])
        if not found:
            return empty
        os_id = found.group(1).upper()
        projeto = (siglas or {}).get(os_id.split("-")[0])
        return {"cargo": cargo, "projeto": projeto, "os_id": os_id, "rotulo": f"{cargo} · {os_id}"}
    projeto = parts[-1]
    return {"cargo": cargo, "projeto": projeto, "os_id": None, "rotulo": f"{cargo} · {projeto}"}


ROTULO_MAX = 44


def nome_do_chat(title: str | None, cwd: str | None) -> str:
    """Rótulo de um chat cujo título não segue `Cargo · Projeto` (INT-07).

    O título do chat, se houver; senão `Chat sem título · <últimas duas pastas do cwd>`.
    """
    texto = " ".join(repair(title).split()) if isinstance(title, str) else ""
    if texto:
        return texto if len(texto) <= ROTULO_MAX else texto[: ROTULO_MAX - 1].rstrip() + "…"
    partes = [parte for parte in re.split(r"[\\/]+", cwd or "") if parte and not re.fullmatch(r"[A-Za-z]:", parte)]
    return "Chat sem título · " + "/".join(partes[-2:]) if partes else "Chat sem título"


def parse_chat(title: str | None, cwd: str | None, siglas: dict[str, str] | None = None) -> dict:
    """`parse` com o rótulo preenchido para o chat fora do padrão."""
    dados = parse(title, siglas)
    if dados["rotulo"] is None:
        dados["rotulo"] = nome_do_chat(title, cwd)
    return dados
