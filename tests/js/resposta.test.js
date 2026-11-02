'use strict';

/* Testes de frontend/resposta.js (leitura da resposta de /api) e da abreviação das legendas.
   Rodar: node --test tests/js/resposta.test.js */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { lerResposta } = require(path.join(__dirname, '..', '..', 'frontend', 'resposta.js'));
const { abreviarRotulo } = require(path.join(__dirname, '..', '..', 'frontend', 'pixel.js'));

const resposta = (status, corpo, tipo) => new Response(corpo, { status, headers: { 'content-type': tipo } });

test('JSON com status ok devolve os dados', async () => {
  const dados = await lerResposta(resposta(200, '{"ok":true}', 'application/json'), '/api/health');
  assert.deepEqual(dados, { ok: true });
});

test('500 em texto puro vira erro legível com status e caminho, sem quebrar o parse', async () => {
  await assert.rejects(lerResposta(resposta(500, 'Internal Server Error', 'text/plain'), '/api/painel'),
    (erro) => erro.message === '500 /api/painel');
});

test('erro em JSON acrescenta o detalhe', async () => {
  await assert.rejects(lerResposta(resposta(503, '{"detail":"Banco ocupado."}', 'application/json'), '/api/sessoes'),
    (erro) => erro.message === '503 /api/sessoes: Banco ocupado.');
});

test('200 que não é JSON também é erro com status e caminho', async () => {
  await assert.rejects(lerResposta(resposta(200, '<html></html>', 'text/html'), '/api/painel'),
    (erro) => /^200 \/api\/painel/.test(erro.message));
});

test('legendas: cargo em três letras, espaço e projeto/OS, sem o ponto médio', () => {
  assert.equal(abreviarRotulo('Gerente · Audição'), 'Ger. Audição');
  assert.equal(abreviarRotulo('Gerente · Sala'), 'Ger. Sala');
  assert.equal(abreviarRotulo('Executor · SAL-06'), 'Exe. SAL-06');
  assert.equal(abreviarRotulo('Diretoria · Sede'), 'Dir. Sede');
  assert.equal(abreviarRotulo('Secretaria · Sede'), 'Sec. Sede');
  assert.equal(abreviarRotulo('Plantão · Deploy'), 'Pla. Deploy');
  assert.equal(abreviarRotulo('Plantao · Deploy'), 'Pla. Deploy');
  assert.equal(abreviarRotulo('Assistente · Sala'), 'Ass. Sala');
  assert.equal(abreviarRotulo('Claude principal'), 'Claude principal');
  assert.equal(abreviarRotulo('Explore'), 'Explore');
  assert.equal(abreviarRotulo('Faxineiro · Sala'), 'Faxineiro · Sala');
  assert.equal(abreviarRotulo(null), '');
});
