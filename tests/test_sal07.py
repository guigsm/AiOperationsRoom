"""SAL-07: pendências por sala (card e sino): agrupamento por projeto e agentes com projeto_id."""
from __future__ import annotations

from test_lot5 import client, ev, iso, put, sede  # noqa: F401  (fixtures reaproveitadas)


def test_group_by_project_gives_each_room_its_own_rows(client, sede):
    body = client.get("/api/pendencias").json()["pendencias"]
    por_projeto = {g["projeto_id"]: g for g in body["por_projeto"]}
    assert len(por_projeto) == 2 and {g["projeto"] for g in por_projeto.values()} == {"Sede", "sala"}
    assert sum(len(g["itens"]) for g in por_projeto.values()) == body["total"] == 5
    sala = next(g for g in body["por_projeto"] if g["projeto"] == "sala")
    assert {i["projeto_id"] for i in sala["itens"]} == {sala["projeto_id"]}
    assert {"tipo", "pedido", "onde", "desde"} <= set(sala["itens"][0])


def test_agents_carry_the_room_id_that_matches_the_queue_project(client, sede):
    put(ev("p", "SessionStart", iso(seconds=9), cwd=str(sede / "sala"), session_title="Gerente · sala"),
        ev("p", "PermissionRequest", iso(seconds=7), cwd=str(sede / "sala"), tool_name="Write"),
        ev("o", "SessionStart", iso(seconds=9), cwd="/fora", session_title="Gerente · outro"))
    body = client.get("/api/pendencias").json()
    sala_id = next(g["projeto_id"] for g in body["pendencias"]["por_projeto"] if g["projeto"] == "sala")
    esperando = next(a for a in body["agentes"] if a["sessao"] == "p")
    assert esperando["esperando_permissao"] is True and esperando["projeto_id"] == sala_id
    assert next(a for a in body["agentes"] if a["sessao"] == "o")["projeto_id"] is None


def test_painel_runs_expose_the_same_project_id(client, sede):
    put(ev("p", "SessionStart", iso(seconds=9), cwd=str(sede / "sala"), session_title="Gerente · sala"))
    body = client.get("/api/pendencias").json()
    sala_id = next(g["projeto_id"] for g in body["pendencias"]["por_projeto"] if g["projeto"] == "sala")
    run = next(r for r in client.get("/api/painel").json()["execucoes"] if r["session_id"] == "p")
    assert run["projeto_id"] == sala_id
