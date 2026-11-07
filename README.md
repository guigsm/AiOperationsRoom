# AI Operations Room · InToca

> **Origem e crédito.** Este repositório é um fork de [`mewsdev/AiOperationsRoom`](https://github.com/mewsdev/AiOperationsRoom),
> projeto de **Maria Eduarda Watanabe** (@mewsdev) sob licença MIT. Todo o mérito da ideia, da sala em pixel art e da
> base de código é dela; o aviso de copyright e a [licença](LICENSE) originais foram mantidos. A versão InToca é a sala animada
> da suíte InToca.

## O que a versão InToca muda

Mudanças pequenas e separáveis sobre o original, para a sala conviver com a InToca Sala (a versão simples, "Clássica"):

- **Porta escolhida por você:** `serve --port N` ou a variável `AI_OPERATIONS_ROOM_PORT` (a flag vence a variável; padrão 8765).
- **Registro da sala em `~/.intoca/sala.json`:** ao subir, mescla `porta, pid, iniciou_em, versao` na chave `animada` sem apagar o resto da chave nem do arquivo
  (gravação atômica) e remove a própria entrada ao encerrar normalmente (Ctrl+C). Sala encerrada à força deixa a entrada; quem lê confere
  o `pid` e `/api/health`.
- **Saúde por HTTP:** `GET /api/health` devolve `{ok, versao, pronta}`. A porta abre primeiro; `pronta` vira `true` depois do banco aberto
  e da primeira leitura da fila de eventos, que roda em segundo plano para uma fila grande não atrasar a abertura da porta.
- **Botão "Clássica"** no cabeçalho, que abre a InToca Sala na porta registrada em `sala.json`. Sem Clássica registrada, o botão não aparece.
- **Nome na tela:** "AI Operations Room · InToca".
- **Fonte única (INT-07):** com a InToca Sala (Clássica) no ar, a Animada consome `/api/tocas` e `/api/pendencias` dela em vez de ler manifesto e filas por conta própria; sem ela, mantém a leitura de antes como reserva (`backend/fonte.py`). Só HTTP em loopback, sem código compartilhado.
- **Faxina não vira boneco:** o fim de assistente (`SubagentStop`) sem início anterior e sem tipo é a faxina interna do Claude Code depois de cada resposta; não cria personagem, e os que já estão no banco deixam de aparecer na leitura, sem apagar dado.
- **Vocabulário na placa:** `Assistente · revisor`, `Explorador` etc. vêm de um dicionário único (`frontend/assistentes.js`); chat sem título mostra o título do chat ou `Chat sem título · <pastas>`.
- Sala de escritório ligada a um manifesto de projetos opcional (`INTOCA_SEDE`), fila de pendências do proprietário e comunicação por
  agente.

O remoto `upstream` aponta para o repositório original. Se ele evoluir, cada mudança é avaliada e trazida à mão (`git fetch upstream`).
A história deste fork não é reescrita.

## Subida confiável no Windows

Prefira o Python do ambiente virtual **direto**, sem `uv run`, com o diretório de trabalho na pasta do repositório:

```powershell
.venv\Scripts\python.exe -m backend.cli serve --port 8765
```

O `uv run` confere o ambiente a cada chamada e, numa máquina saturada (antivírus, indexador, sincronizador de nuvem logo após ligar),
levou minutos para a porta abrir; o `.venv` direto abriu em 6 a 15 s nas mesmas condições. Não relance o comando enquanto a porta não
abre: o processo está importando e abrindo o banco, e um segundo só atrasa o primeiro. O log mostra `[sala] iniciando…` assim que o
processo vive e `sala pronta` ao final. `scripts/start-room.ps1` já usa o `.venv` e espera `/api/health`.

Para conferir a subida do jeito que um painel faria (Node `spawn` com `shell:true`), rode
`node scripts/prova-subida.mjs --porta 8766`: mede o tempo até a porta responder e até `pronta`, confere o `sala.json` e encerra tudo.
Use sempre outra porta e dados temporários (o script já faz isso) para não tocar na sala em uso.


Uma sala local para acompanhar sessões e subagentes do Claude Code. O aplicativo recebe somente metadados de hooks, mantém os dados em SQLite local e serve a interface em `127.0.0.1`.

## Requisitos

- Python 3.12 ou superior
- [`uv` instalado](https://docs.astral.sh/uv/getting-started/installation/) e disponível no terminal
- Claude Code, somente para acompanhar sessões reais

## Início rápido

```powershell
uv sync --extra dev
uv run python -m backend.cli hooks-install
uv run python -m backend.cli serve
```

Execute os comandos na pasta deste repositório. Abra [http://127.0.0.1:8765](http://127.0.0.1:8765) e **deixe o terminal do servidor aberto** enquanto usa a sala; `Ctrl+C` encerra o servidor. O hook continua instalado depois que o servidor para e registra eventos para a próxima abertura. A tela Projetos associa um diretório local a cada nome exibido na sala. O caminho mais específico vence. Uma sala aparece quando há uma sessão capturada nesse diretório; cadastrar um projeto sozinho não cria uma sala vazia.

Mantenha a pasta do repositório no mesmo lugar após instalar os hooks: o comando registrado no Claude Code aponta para o caminho local deste checkout. Se precisar movê-la, execute `hooks-remove` antes da mudança e `hooks-install` na nova localização.

### Abrir automaticamente ao entrar no Windows

Depois de executar `uv sync --extra dev` e `hooks-install` uma vez, você pode iniciar o servidor em segundo plano e abrir o navegador com:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-room.ps1
```

O script usa a porta 8765, espera a API responder e abre a sala. Se a porta já estiver ocupada, ele encerra com erro em vez de abrir outra aplicação. Para usar outra porta, acrescente `-Port 8898` ao comando. Se o atalho não abrir a sala, execute o comando manualmente em um terminal para ver o erro; erros de um atalho oculto não aparecem na tela.

Para executar esse script em cada **login** do Windows:

1. Pressione `Win+R`, digite `shell:startup` e pressione Enter.
2. Na pasta aberta, crie um atalho. Como destino, use `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\caminho\para\AiOperationsRoom\scripts\start-room.ps1"`, trocando o caminho pelo local real do repositório.
3. Faça logout e login para testar. Para desativar a abertura automática, remova esse atalho da pasta Inicializar.

O script inicia apenas o servidor real. A demonstração abaixo usa dados separados e deve ser aberta com `demo --serve`. [A Microsoft documenta a pasta `shell:startup` para aplicativos iniciados no login](https://support.microsoft.com/en-gb/windows/experience/startup-boot/configure-startup-applications-in-windows).

## Demonstração

O modo demo cria uma fila e um banco separados em `~/.ai-operations-room-demo`, sem acessar dados reais ou precisar do Claude Code. Projetos cadastrados na demo não aparecem no servidor real, e vice-versa.

```powershell
uv run python -m backend.cli demo --serve
```

Abra `http://127.0.0.1:8765` e interrompa o processo quando terminar. Para apenas gerar os dados fictícios, omita `--serve`. Ao executar `demo` novamente, os eventos e horários fictícios são renovados; sessões da demo não são classificadas como órfãs por falta de PID.

Use `--port 8876` em qualquer comando de servidor quando a porta padrão já estiver ocupada.

## Hooks do Claude Code

O registro altera `~/.claude/settings.json`: adiciona um command hook para `SessionStart`, `UserPromptSubmit`, `Stop`, `SubagentStart`, `SubagentStop` e `SessionEnd`. Antes de alterar o arquivo, revise seu conteúdo.

```powershell
uv run python -m backend.cli hooks-install
uv run python -m backend.cli hooks-remove
```

`hooks-remove` remove somente entradas cujo comando aponta para `hooks/capture.py` deste checkout, mesmo se o executável Python tiver mudado. Ele preserva os demais hooks e configurações.

O comando registrado é o interpretador base direto, isolado e sem `site` (`"<python>" -I -S "<checkout>/hooks/capture.py"`), sem PowerShell e sem o lançador do venv: a partida rápida mantém o hook de `SessionEnd` abaixo de 1 s (antes o Claude Code o cancelava, "Hook cancelled"). `hooks-install` também migra a entrada antiga deste checkout (PowerShell, com o campo `shell`) para o comando novo. O hook só usa a biblioteca padrão e só grava uma linha em `events.jsonl`.

O hook registra identificadores, tipo de agente, diretório de trabalho, razão de encerramento e a hora do evento. Ele não salva prompts, respostas nem transcrições. Para detectar sessões interrompidas sem hook de encerramento, o servidor consulta o identificador da sessão e o PID em `~/.claude/sessions`; não copia o conteúdo desses arquivos para o banco. Os dados ficam por padrão em `~/.ai-operations-room`; defina `AI_OPERATIONS_ROOM_DATA_DIR` para usar outra pasta.

O Painel usa um período selecionável de 6, 12 ou 24 horas. O Escritório mostra execuções ativas e as encerradas nas últimas 12 horas; apenas sessões principais sem subagentes encerradas em menos de 30 segundos são ocultadas da sala.

## Sugestões de agentes

Estou compartilhando também 2 agentes que eu utilizo nos meus projetos de trabalho e pessoais[SUGESTAO_DE_AGENTES.md](SUGESTAO_DE_AGENTES.md): um revisor de código e um pesquisador de contexto.

## Desenvolvimento

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.test-temp
node --check frontend/app.js
node --test tests/js/*.test.js
```

Consulte [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md) e [HANDOFF.md](HANDOFF.md) para decisões e pontos de extensão.

## Limites atuais

- A interface consulta a API a cada quatro segundos.
- Esta versão é destinada somente ao Windows. macOS e Linux não foram validados; no macOS, a detecção de sessões órfãs ainda não funciona. Em 08/10/2026, uma sessão real do Claude Code com subagente Explore foi capturada no Windows, e a API exibiu a filha concluída e o principal trabalhando novamente.
- O suporte de hooks foi validado com o formato documentado do Claude Code. O registro assistido usa o arquivo global de configurações do usuário; configurações gerenciadas pela organização podem impedir hooks locais.
- O serviço é local e não fornece autenticação ou acesso remoto.

## Inspiração visual

A sala pixel foi inspirada pelo [Pixel Agents](https://github.com/pixel-agents-hq/pixel-agents), da equipe Pixel Agents. Os personagens e móveis foram criados para este projeto; nenhum asset do Pixel Agents é usado.

## Licença

Distribuído sob a [licença MIT](LICENSE).
