'use strict';

/* Testes de frontend/depende.js (estado do bloco "Depende de você" do topo).
   Rodar: node --test tests/js/depende.test.js */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { CHAVE, lerAberto, gravarAberto } = require(path.join(__dirname, '..', '..', 'frontend', 'depende.js'));

const memoria = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };

test('o padrão é recolhido, com ou sem armazenamento', () => {
  assert.equal(lerAberto(memoria()), false);
  assert.equal(lerAberto(null), false);
  assert.equal(lerAberto(undefined), false);
});

test('exibir fica lembrado e ocultar volta ao padrão', () => {
  const a = memoria();
  gravarAberto(true, a);
  assert.equal(a.getItem(CHAVE), '1');
  assert.equal(lerAberto(a), true);
  gravarAberto(false, a);
  assert.equal(lerAberto(a), false);
  assert.equal(a.getItem(CHAVE), null);
});

test('armazenamento que lança não quebra: recolhido e sem erro', () => {
  const ruim = { getItem() { throw new Error('bloqueado'); }, setItem() { throw new Error('bloqueado'); }, removeItem() { throw new Error('bloqueado'); } };
  assert.equal(lerAberto(ruim), false);
  assert.doesNotThrow(() => gravarAberto(true, ruim));
  assert.doesNotThrow(() => gravarAberto(false, ruim));
  assert.doesNotThrow(() => gravarAberto(true, null));
});
