'use strict';

/* Dicionário único dos assistentes (INT-07): tipo interno -> rótulo da placa e família do glifo.
   O prefixo de plugin (`intoca:`) é tirado antes de consultar, então `intoca:revisor` e `revisor` dão o mesmo boneco.
   Tipo desconhecido vira apenas "Assistente", sem o nome interno. `leitura` marca o assistente que só lê e pesquisa:
   é o "boneco pequeno" da legenda. O `vigia` chega na PLG-31 e já tem entrada. */
(function (raiz) {
  const TIPOS = {
    revisor: { rotulo: 'Assistente · revisor', familia: 'revisao' },
    auditor: { rotulo: 'Assistente · auditor', familia: 'qa' },
    pesquisador: { rotulo: 'Assistente · pesquisador', familia: 'pesquisa', leitura: true },
    vigia: { rotulo: 'Assistente · vigia', familia: 'qa' },
    'claude-code-guide': { rotulo: 'Assistente · guia', familia: 'pesquisa', leitura: true }, // nome interno do Claude Code (integração)
    'general-purpose': { rotulo: 'Assistente · geral', familia: 'pesquisa' },
    explore: { rotulo: 'Explorador', familia: 'pesquisa', leitura: true },
    plan: { rotulo: 'Planejador', familia: 'plano' },
  };
  // Famílias de glifo para tipos sem rótulo próprio (continuam "Assistente"): o desenho segue reconhecendo o que já reconhecia.
  const FAMILIAS_EXTRA = [
    ['revisao', /^(code-review|simplify)/i], ['qa', /^(verificador|diagnostico|security)/i],
    ['dados', /^analista/i], ['conhecimento', /^(curador|radar|entrega)/i],
  ];

  const normalizar = (tipo) => String(tipo === null || tipo === undefined ? '' : tipo).trim().replace(/^[\w-]+:/, '').toLowerCase();
  const entrada = (tipo) => TIPOS[normalizar(tipo)] || null;

  function rotulo(tipo) {
    const chave = normalizar(tipo);
    if (chave === 'principal') return 'Chat';
    const item = TIPOS[chave];
    return item ? item.rotulo : 'Assistente';
  }

  function familia(tipo) {
    const chave = normalizar(tipo);
    if (chave === 'principal') return 'principal';
    const item = TIPOS[chave];
    if (item) return item.familia;
    const extra = FAMILIAS_EXTRA.find(([, padrao]) => padrao.test(chave));
    return extra ? extra[0] : 'outro';
  }

  const leitura = (tipo) => Boolean((entrada(tipo) || {}).leitura);

  const Assistentes = { TIPOS, normalizar, rotulo, familia, leitura };
  raiz.Assistentes = Assistentes;
  if (typeof module !== 'undefined' && module.exports) module.exports = Assistentes;
})(typeof window !== 'undefined' ? window : globalThis);
