/* Lê a resposta de /api: JSON em caso de sucesso; em erro, uma mensagem legível com status e caminho
   (ex.: "500 /api/painel"), mesmo quando o servidor devolve texto puro em vez de JSON. */
(function (raiz) {
  async function lerResposta(response, caminho) {
    const local = `${response.status} ${caminho}`;
    const tipo = (response.headers && response.headers.get && response.headers.get('content-type')) || '';
    const texto = await response.text();
    let dados = null;
    if (/json/i.test(tipo) || /^\s*[{[]/.test(texto)) {
      try { dados = JSON.parse(texto); } catch (erro) { dados = null; }
    }
    if (!response.ok) {
      const detalhe = dados && typeof dados.detail === 'string' ? dados.detail : '';
      throw new Error(detalhe ? `${local}: ${detalhe}` : local);
    }
    if (dados === null) throw new Error(`${local}: resposta fora do formato esperado`);
    return dados;
  }
  const api = { lerResposta };
  raiz.RespostaApi = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
