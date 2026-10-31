# Handoff

## Onde mudar cada parte

- Hooks e filtro de campos: `hooks/capture.py`
- Registro e remoção de hooks, demo e servidor: `backend/cli.py`
- Leitura da fila e deduplicação: `backend/events.py`
- Filas da sede (pendências do proprietário, OS por agente; só leitura): `backend/pendencias.py`
- Regras de estados: `backend/runs.py`
- Detecção de sessões órfãs pelo registro local do Claude Code: `backend/reconcile.py`
- Esquema local: `backend/db.py`
- API: `backend/api.py`
- Mapeamento por diretório: `backend/projects.py`
- Sala, painel e detalhes: `frontend/app.js`, `frontend/pixel.js`, `frontend/office.css` e `frontend/styles.css`

## Decisão visual F2

Os personagens em pixel art são definidos em código em `frontend/pixel.js`, por mapas de caracteres convertidos em SVG com um `<path>` por cor e `crispEdges`. Pele, cabelo e roupa variam por cores; o agente principal usa fone roxo. Os personagens e móveis foram criados para este projeto; nenhum asset do Pixel Agents é usado. Antes de publicar, confirmar a autoria dos elementos visuais e a ausência de recursos copiados na revisão final.

## Extensões previstas

Para múltiplas pastas por projeto, substitua `caminho_local` por uma tabela de mapeamentos e mantenha a regra do caminho mais específico. Para uma nova origem de eventos, escreva um adaptador que produza o mesmo contrato de evento, sem acoplar a API ao aplicativo de origem.

Antes de publicar, revise o histórico Git, exemplos, imagens e arquivos versionados em busca de dados pessoais, caminhos privados, logs, credenciais e licenças de recursos visuais.
