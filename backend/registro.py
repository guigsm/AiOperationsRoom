"""Registro da sala animada em ~/.intoca/sala.json (estado da máquina, compartilhado com a InToca Sala)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REGISTRO_ENV = "INTOCA_SALA_JSON"
PORT_ENV = "AI_OPERATIONS_ROOM_PORT"
PADRAO = 8765
VERSAO = "0.2.0"


def registro_path() -> Path:
    return Path(os.environ.get(REGISTRO_ENV) or Path.home() / ".intoca" / "sala.json").expanduser()


def porta_configurada(flag: int | None = None) -> int:
    """Flag --port vence a variável AI_OPERATIONS_ROOM_PORT, que vence o padrão 8765."""
    if flag is not None:
        return flag
    bruto = os.environ.get(PORT_ENV, "").strip()
    if bruto:
        try:
            valor = int(bruto)
        except ValueError:
            raise SystemExit(f"{PORT_ENV} precisa ser um número de porta; recebi {bruto!r}.")
        if not 1 <= valor <= 65535:
            raise SystemExit(f"{PORT_ENV} fora do intervalo 1-65535: {valor}.")
        return valor
    return PADRAO


def _ler(path: Path) -> dict:
    try:
        dados = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(path: Path, dados: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def registrar(porta: int) -> None:
    """Grava animada={porta,pid,iniciou_em,versao}; preserva o resto do arquivo. Nunca derruba a sala."""
    try:
        path = registro_path()
        dados = _ler(path)
        dados["animada"] = {
            "porta": porta,
            "pid": os.getpid(),
            "iniciou_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "versao": VERSAO,
        }
        _gravar(path, dados)
    except OSError:
        pass


def remover() -> None:
    """Tira a entrada da animada, só se for deste processo (outra sala pode ter assumido a chave)."""
    try:
        path = registro_path()
        dados = _ler(path)
        atual = dados.get("animada")
        if isinstance(atual, dict) and atual.get("pid") == os.getpid():
            dados.pop("animada")
            _gravar(path, dados)
    except OSError:
        pass


def classica_porta() -> int | None:
    """Porta da InToca Sala (Clássica) registrada em sala.json, ou None."""
    dados = _ler(registro_path())
    for chave in ("classica", "sala"):
        item = dados.get(chave)
        if isinstance(item, dict):
            item = item.get("porta")
        if isinstance(item, int) and not isinstance(item, bool) and 0 < item < 65536:
            return item
    porta = dados.get("porta")
    if isinstance(porta, int) and not isinstance(porta, bool) and 0 < porta < 65536:
        return porta
    return None
