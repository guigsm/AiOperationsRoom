/* Estado do bloco "Depende de você" do topo: começa recolhido; a escolha fica no localStorage
   (com try/catch: sem armazenamento a tela funciona e o estado vale só nesta visita). */
(function (raiz) {
  const CHAVE = 'sala.depende.aberto';
  function lerAberto(armazem) {
    try { return Boolean(armazem) && armazem.getItem(CHAVE) === '1'; } catch (erro) { return false; }
  }
  function gravarAberto(aberto, armazem) {
    try {
      if (!armazem) return;
      if (aberto) armazem.setItem(CHAVE, '1');
      else armazem.removeItem(CHAVE);
    } catch (erro) { /* sem armazenamento: vale só nesta visita */ }
  }
  const api = { CHAVE, lerAberto, gravarAberto };
  raiz.DependeEstado = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
