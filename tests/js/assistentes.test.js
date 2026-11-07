'use strict';

/* INT-07: dicionário único dos assistentes e varredura das palavras da página.
   Rodar: node --test tests/js/assistentes.test.js */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const A = require('../../frontend/assistentes.js');
const px = require('../../frontend/pixel.js');

const ROTULOS = {
  revisor: 'Assistente · revisor', auditor: 'Assistente · auditor', pesquisador: 'Assistente · pesquisador',
  vigia: 'Assistente · vigia', 'claude-code-guide': 'Assistente · guia', 'general-purpose': 'Assistente · geral',
  Explore: 'Explorador', Plan: 'Planejador',
};

test('cada tipo da lista tem o seu rótulo', () => {
  Object.entries(ROTULOS).forEach(([tipo, esperado]) => assert.equal(A.rotulo(tipo), esperado, tipo));
});

test('intoca:revisor e revisor dão o mesmo rótulo e a mesma família (e o mesmo boneco)', () => {
  ['revisor', 'auditor', 'pesquisador', 'vigia'].forEach((t) => {
    assert.equal(A.rotulo(`intoca:${t}`), A.rotulo(t));
    assert.equal(A.familia(`intoca:${t}`), A.familia(t));
    assert.equal(px.familiaDe(`intoca:${t}`), px.familiaDe(t));
  });
  assert.equal(A.rotulo('intoca:revisor'), 'Assistente · revisor');
  assert.equal(px.rotulo('intoca:revisor', null), 'Assistente · revisor');
});

test('tipo desconhecido vira apenas Assistente, sem o nome interno', () => {
  ['xyz-interno', 'subagente', 'desconhecido', '', null, undefined, 'plugin:coisa-nova'].forEach((t) => {
    assert.equal(A.rotulo(t), 'Assistente', String(t));
    assert.equal(px.rotulo(t, null), 'Assistente');
  });
  assert.equal(px.rotulo('x', { rotulo: 'Executor · INT-07' }), 'Executor · INT-07'); // título do chat vence
});

test('principal é chat; só o assistente de leitura é pequeno', () => {
  assert.equal(A.rotulo('principal'), 'Chat');
  assert.equal(A.familia('principal'), 'principal');
  assert.deepEqual(['Explore', 'pesquisador', 'intoca:pesquisador', 'claude-code-guide'].map(A.leitura), [true, true, true, true]);
  assert.deepEqual(['revisor', 'general-purpose', 'Plan', 'principal', 'xyz'].map(A.leitura), [false, false, false, false, false]);
});

test('as famílias de glifo que existiam continuam reconhecidas', () => {
  assert.equal(A.familia('Explore'), 'pesquisa');
  assert.equal(A.familia('Plan'), 'plano');
  assert.equal(A.familia('code-review'), 'revisao');
  assert.equal(A.familia('verificador-x'), 'qa');
  assert.equal(A.familia('analista-bi'), 'dados');
  assert.equal(A.familia('curador'), 'conhecimento');
  assert.equal(A.familia('qualquer'), 'outro');
});

// Varredura do que a página mostra. Exceções de integração (lista curta e comentada):
//  - comunicacao.js: `claude --resume` é o comando real do Claude Code e "app do Claude" é o app concreto onde se retoma o chat.
//  - assistentes.js: 'claude-code-guide' é o nome interno que o Claude Code dá ao assistente; só a chave, o rótulo é "Assistente · guia".
const EXCECOES_CLAUDE = new Set(['comunicacao.js', 'assistentes.js']);
const pasta = path.join(__dirname, '..', '..', 'frontend');
const arquivos = fs.readdirSync(pasta).filter((f) => /\.(html|js)$/.test(f));

test('"Claude principal", "subagente" e "sessões e subagentes" não aparecem na página', () => {
  arquivos.forEach((f) => {
    const texto = fs.readFileSync(path.join(pasta, f), 'utf8');
    assert.doesNotMatch(texto, /Claude principal/i, f);
    assert.doesNotMatch(texto, /sess(ões|oes) e subagentes/i, f);
    assert.doesNotMatch(texto, /subagent/i, f);
  });
});

test('"Claude" só aparece onde é a integração concreta', () => {
  arquivos.forEach((f) => {
    const texto = fs.readFileSync(path.join(pasta, f), 'utf8');
    if (EXCECOES_CLAUDE.has(f)) return;
    assert.doesNotMatch(texto, /claude/i, `${f} cita Claude fora da lista de exceções`);
  });
});

test('a legenda explica o boneco pequeno e o texto usa "chats e assistentes"', () => {
  const index = fs.readFileSync(path.join(pasta, 'index.html'), 'utf8');
  assert.match(index, /boneco pequeno = assistente de leitura/);
  assert.match(index, /chats e assistentes/);
  assert.match(index, /assistentes\.js/);
});
