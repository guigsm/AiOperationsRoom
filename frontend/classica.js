'use strict';

/* Botão "Clássica" no cabeçalho: abre a InToca Sala (a lista simples de Tocas). A porta vem de /api/classica
   (que lê ~/.intoca/sala.json); sem Clássica registrada, nenhum botão aparece. */

function urlClassica(porta, local) {
  if (!Number.isInteger(porta) || porta < 1 || porta > 65535) return null;
  const host = (local && local.hostname) || '127.0.0.1';
  return `http://${host}${porta === 80 ? '' : ':' + porta}/?sala=classica`;
}

function montarBotaoClassica(doc, url) {
  const existente = doc.getElementById('botao-classica');
  if (existente) existente.remove();
  if (!url) return null;
  const link = doc.createElement('a');
  link.id = 'botao-classica';
  link.className = 'botao-classica';
  link.href = url;
  link.textContent = 'Clássica';
  link.title = 'Abrir a InToca Sala, a versão simples';
  const barra = doc.querySelector('.topbar');
  if (!barra) return null;
  const aviso = doc.getElementById('connection');
  barra.insertBefore(link, aviso && aviso.parentNode === barra ? aviso : null);
  return link;
}

/* Link no menu lateral (o visível: a barra superior fica escondida). Último item, só visita, mesma aba. */
const ICONE_CLASSICA = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg>';

function montarLinkClassica(doc, url) {
  const existente = doc.getElementById('link-classica');
  if (existente) existente.remove();
  if (!url) return null;
  const menu = doc.querySelector('.trilho-principal .trilho-nav');
  if (!menu) return null;
  const link = doc.createElement('a');
  link.id = 'link-classica';
  link.className = 'nav nav-classica';
  link.href = url;
  link.setAttribute('aria-label', 'Sala Clássica');
  link.title = 'Abrir a Sala Clássica (visita, não muda seu padrão)';
  link.innerHTML = ICONE_CLASSICA;
  menu.appendChild(link);
  return link;
}

async function iniciarBotaoClassica() {
  try {
    const resposta = await fetch('/api/classica');
    if (!resposta.ok) return;
    const dados = await resposta.json();
    const url = urlClassica(dados.porta, window.location);
    montarBotaoClassica(document, url);
    montarLinkClassica(document, url);
  } catch (_erro) { /* sem Clássica: nada a mostrar */ }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciarBotaoClassica);
  else iniciarBotaoClassica();
}
if (typeof module !== 'undefined') module.exports = { urlClassica, montarBotaoClassica, montarLinkClassica };
