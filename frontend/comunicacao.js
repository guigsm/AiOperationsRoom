/* Aviso do "!" (comunicação perdida): o que aconteceu e como retomar. Só orienta, não executa nada.
   O comando usa apenas `cwd` e `session_id` da execução, nunca texto de prompt. */
(function (raiz) {
  const ID_SEGURO = /^[A-Za-z0-9_-]{1,100}$/;

  function comandoRetomar(execucao) {
    const sessao = execucao && execucao.session_id;
    const pasta = execucao && execucao.cwd;
    if (typeof sessao !== 'string' || !ID_SEGURO.test(sessao)) return null;
    const retomar = `claude --resume ${sessao}`;
    if (typeof pasta !== 'string' || !pasta.trim() || /["\r\n\0]/.test(pasta)) return retomar;
    return `cd "${pasta.trim()}" && ${retomar}`;
  }

  const TITULO = 'Comunicação perdida';
  const PORQUE = 'A sala parou de receber sinais deste chat, por isso ele aparece com “!”.';
  const RETOMAR_APP = 'Para retomar: abra o chat no app do Claude e mande uma mensagem. Qualquer evento novo do chat o traz de volta.';
  const RETOMAR_TERMINAL = 'Chat de terminal: rode, na pasta do chat:';
  const NOTA = 'A sala só recebe os sinais dos hooks e não consegue reconectar sozinha.';

  const api = { comandoRetomar, TITULO, PORQUE, RETOMAR_APP, RETOMAR_TERMINAL, NOTA };
  raiz.Comunicacao = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
