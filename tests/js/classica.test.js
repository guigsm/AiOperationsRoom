'use strict';

/* Testes de frontend/classica.js (botão "Clássica"). Rodar: node --test tests/js/classica.test.js */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { urlClassica, montarBotaoClassica } = require(path.join(__dirname, '..', '..', 'frontend', 'classica.js'));

test('porta válida vira endereço da Clássica no mesmo host; a 80 não leva porta', () => {
  assert.equal(urlClassica(8080, { hostname: 'localhost' }), 'http://localhost:8080/?sala=classica');
  assert.equal(urlClassica(80, { hostname: '127.0.0.1' }), 'http://127.0.0.1/?sala=classica');
  assert.equal(urlClassica(8080, null), 'http://127.0.0.1:8080/?sala=classica');
});

test('sem porta válida não há endereço, e o botão some', () => {
  for (const ruim of [null, undefined, 0, 70000, '80', 1.5]) assert.equal(urlClassica(ruim, null), null);
});

function docFalso() {
  const filhos = [];
  const barra = {
    insertBefore: (no) => filhos.push(no),
  };
  const doc = {
    getElementById: (id) => (id === 'botao-classica' ? filhos.find((f) => f.id === id) : null),
    createElement: () => ({ remove() { filhos.splice(filhos.indexOf(this), 1); } }),
    querySelector: () => barra,
  };
  return { doc, filhos };
}

test('monta um só botão, troca o anterior e remove quando a URL some', () => {
  const { doc, filhos } = docFalso();
  const a = montarBotaoClassica(doc, 'http://x/?sala=classica');
  assert.equal(a.textContent, 'Clássica');
  assert.equal(a.href, 'http://x/?sala=classica');
  montarBotaoClassica(doc, 'http://y/?sala=classica');
  assert.equal(filhos.length, 1);
  assert.equal(montarBotaoClassica(doc, null), null);
  assert.equal(filhos.length, 0);
});
