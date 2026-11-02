const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
let projects = [];
let sessions = [];
let editingId = null;
let manifest = { ativo: false };
let carregouProjetos = false;
let carregouSessoes = false;
let erroCarga = '';

async function request(method, path, body) {
  const response = await fetch('/api' + path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  return window.RespostaApi.lerResposta(response, '/api' + path);
}

function notice(message, error = false, ciclo = false) { const target = $('#notice'); target.dataset.ciclo = ciclo ? '1' : ''; target.textContent = message; target.classList.toggle('error', error); target.hidden = false; }
function openProject(project = null, path = '') { editingId = project?.id ?? null; $('#dialog-title').textContent = project ? 'Editar projeto' : 'Novo projeto'; $('#dialog-help').textContent = project ? 'A mudança da pasta atualiza as associações existentes.' : 'Escolha um nome curto para identificar a sala.'; $('#project-name').value = project?.nome ?? ''; $('#project-path').value = path || project?.caminho_local || ''; $('#project-dialog').showModal(); $('#project-name').focus(); }

function carregando(mensagem = 'Carregando…') { return `<p class="empty" role="status">${esc(mensagem)}</p>`; }
function falhou(texto) { return `<p class="empty erro" role="alert">Não foi possível carregar: ${esc(texto)}</p>`; }

function render() {
  const listaSem = $('#unmapped-list');
  const listaProj = $('#project-list');
  listaSem.setAttribute('aria-busy', String(!carregouSessoes && !erroCarga));
  listaProj.setAttribute('aria-busy', String(!carregouProjetos && !erroCarga));
  const unknown = new Map();
  for (const session of sessions) if (session.projeto_id === null) { const entry = unknown.get(session.cwd) || { cwd: session.cwd, count: 0 }; entry.count += 1; unknown.set(session.cwd, entry); }
  $('#new-project').hidden = manifest.ativo;
  $('#unmapped-count').textContent = unknown.size;
  if (!carregouSessoes) listaSem.innerHTML = erroCarga ? falhou(erroCarga) : carregando(); else $('#unmapped-list').innerHTML = unknown.size ? [...unknown.values()].map((entry) => `<div class="row"><div class="row-main"><strong class="path">${esc(entry.cwd)}</strong><small>${entry.count} sessão(ões)</small></div><div class="actions" ${manifest.ativo ? 'hidden' : ''}><button data-action="create" data-path="${esc(entry.cwd)}">Criar projeto</button><button data-action="map" data-path="${esc(entry.cwd)}">Mapear existente</button></div></div>`).join('') : '<p class="empty">Nenhum caminho sem projeto.</p>';
  if (!carregouProjetos) { listaProj.innerHTML = erroCarga ? falhou(erroCarga) : carregando(); return; }
  const visible = projects.filter((project) => !project.arquivado || $('#show-archived').checked);
  $('#project-count').textContent = projects.length;
  $('#project-list').innerHTML = visible.length ? visible.map((project) => `<div class="row ${project.arquivado ? 'archived' : ''}"><div class="row-main"><strong>${esc(project.nome)} ${project.arquivado ? '<span class="badge">Arquivado</span>' : ''}</strong><span class="path">${esc(project.caminho_local)}</span></div><div class="actions" ${manifest.ativo ? 'hidden' : ''}><button data-action="edit" data-id="${project.id}">Editar</button><button data-action="archive" data-id="${project.id}">${project.arquivado ? 'Desarquivar' : 'Arquivar'}</button><button class="danger" data-action="delete" data-id="${project.id}">Remover</button></div></div>`).join('') : '<p class="empty">Nenhum projeto nesta lista.</p>';
}

let atualizando = false;
let refazer = false;
let falhas = 0;
let relogio = null;
// Cada parte aparece assim que chega (a lista de projetos não espera a de sessões, que é a mais lenta);
// o próximo ciclo só começa depois deste terminar, e com falha o intervalo dobra até 30 s.
async function refresh() {
  if (atualizando) { refazer = true; return; }
  atualizando = true;
  clearTimeout(relogio);
  erroCarga = '';
  try {
    await Promise.all([
      request('GET', '/projetos').then((dados) => { projects = dados; carregouProjetos = true; render(); }),
      request('GET', '/sessoes').then((dados) => { sessions = dados.sessoes; carregouSessoes = true; render(); }),
      request('GET', '/manifesto').then((dados) => { manifest = dados; render(); }),
    ]);
    falhas = 0;
    if ($('#notice').dataset.ciclo) $('#notice').hidden = true;
  } catch (error) {
    falhas += 1;
    erroCarga = error.message;
    render();
    notice(error.message, true, true);
  } finally {
    atualizando = false;
    const deNovo = refazer;
    refazer = false;
    relogio = setTimeout(refresh, deNovo ? 0 : Math.min(30000, 4000 * 2 ** Math.min(falhas, 4)));
  }
}
$('#new-project').addEventListener('click', () => openProject());
$('#show-archived').addEventListener('change', render);
$('#cancel-dialog').addEventListener('click', () => $('#project-dialog').close());
$('#project-form').addEventListener('submit', async (event) => { event.preventDefault(); try { await request(editingId ? 'PUT' : 'POST', editingId ? `/projetos/${editingId}` : '/projetos', { nome: $('#project-name').value.trim(), caminho_local: $('#project-path').value.trim() }); $('#project-dialog').close(); await refresh(); notice('Projeto salvo.'); } catch (error) { notice(error.message, true); } });
document.addEventListener('click', async (event) => { const button = event.target.closest('button[data-action]'); if (!button) return; const action = button.dataset.action; const path = button.dataset.path; const project = projects.find((item) => String(item.id) === button.dataset.id); try { if (action === 'create') return openProject(null, path); if (action === 'edit') return openProject(project); if (action === 'map') { const options = projects.filter((item) => !item.arquivado); const choice = prompt(`Número do projeto:\n${options.map((item) => `${item.id} — ${item.nome}`).join('\n')}`); const target = options.find((item) => item.id === Number(choice)); if (!target || !confirm(`Substituir a pasta de "${target.nome}"?`)) return; await request('PUT', `/projetos/${target.id}`, { nome: target.nome, caminho_local: path }); } else if (action === 'archive' && project) await request('POST', `/projetos/${project.id}/${project.arquivado ? 'desarquivar' : 'arquivar'}`); else if (action === 'delete' && project && confirm(`Remover "${project.nome}"?`)) await request('DELETE', `/projetos/${project.id}`); await refresh(); } catch (error) { notice(error.message, true); } });
refresh();
