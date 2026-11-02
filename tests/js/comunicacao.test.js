'use strict';

/* Testes de frontend/comunicacao.js (aviso do "!" de comunicação perdida).
   Rodar: node --test tests/js/comunicacao.test.js */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const C = require(path.join(__dirname, '..', '..', 'frontend', 'comunicacao.js'));

test('comando de retomada usa só cwd e session_id', () => {
  const comando = C.comandoRetomar({
    session_id: 'abc-123', cwd: 'C:\intoca\sala', prompt: 'segredo do prompt', titulo: 'Gerente · Sala', rotulo: 'x',
  });
  assert.equal(comando, 'cd "C:\intoca\sala" && claude --resume abc-123');
  assert.ok(!/segredo|Gerente/.test(comando));
});

test('sem cwd conhecido, só o resume', () => {
  assert.equal(C.comandoRetomar({ session_id: 'abc', cwd: '' }), 'claude --resume abc');
});

test('session_id fora do padrão ou pasta com aspas não gera comando perigoso', () => {
  assert.equal(C.comandoRetomar({ session_id: 'a; rm -rf /', cwd: 'C:\\x' }), null);
  assert.equal(C.comandoRetomar({ session_id: '', cwd: 'C:\\x' }), null);
  assert.equal(C.comandoRetomar(null), null);
  assert.equal(C.comandoRetomar({ session_id: 'abc', cwd: 'C:\\x" & calc & "' }), 'claude --resume abc');
});

test('textos usam o termo novo e não falam em órfã', () => {
  const tudo = [C.TITULO, C.PORQUE, C.RETOMAR_APP, C.RETOMAR_TERMINAL, C.NOTA].join(' ');
  assert.equal(C.TITULO, 'Comunicação perdida');
  assert.ok(!/órf/i.test(tudo));
  assert.match(C.RETOMAR_APP, /mande uma mensagem/);
});
