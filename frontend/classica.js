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

async function iniciarBotaoClassica() {
  try {
    const resposta = await fetch('/api/classica');
    if (!resposta.ok) return;
    const dados = await resposta.json();
    montarBotaoClassica(document, urlClassica(dados.porta, window.location));
  } catch (_erro) { /* sem Clássica: nada a mostrar */ }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciarBotaoClassica);
  else iniciarBotaoClassica();
}
if (typeof module !== 'undefined') module.exports = { urlClassica, montarBotaoClassica };
