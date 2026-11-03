// Prova de subida: sobe a sala do mesmo jeito que o painel das Tocas (Node `spawn`, shell:true, stdio em pipe),
// mede o tempo até /api/health responder e até `pronta: true`, confere o registro em sala.json e encerra a árvore.
// Uso: node scripts/prova-subida.mjs [--porta 8766] [--lancador venv|uv|python] [--stdio pipe|ignore] [--limite 180]
// Sempre em dados e sala.json temporários: não toca na sala real nem em ~/.intoca.
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';

const arg = (nome, padrao) => { const i = process.argv.indexOf(`--${nome}`); return i > 0 ? process.argv[i + 1] : padrao; };
const APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const porta = arg('porta', '8766');
const lancador = arg('lancador', 'venv');
const stdio = arg('stdio', 'pipe');
const limite = Number(arg('limite', '180')) * 1000;
const dados = mkdtempSync(join(tmpdir(), 'sala-prova-'));
const salaJson = join(dados, 'sala.json');
const py = join(APP, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const comandos = {
  venv: [`"${py}"`, '-m', 'backend.cli', 'serve'],
  uv: ['uv', 'run', '--directory', `"${APP}"`, 'python', '-m', 'backend.cli', 'serve'],
  python: ['python', '-m', 'backend.cli', 'serve'],
};
const [cmd, ...args] = comandos[lancador];
const t0 = Date.now();
const filho = spawn(cmd, [...args, '--port', porta], {
  cwd: APP, shell: true, windowsHide: true, stdio: stdio === 'ignore' ? 'ignore' : 'pipe',
  env: { ...process.env, NO_COLOR: '1', AI_OPERATIONS_ROOM_DATA_DIR: dados, INTOCA_SALA_JSON: salaJson },
});
const saida = [];
filho.stdout?.on('data', (d) => saida.push(d.toString()));
filho.stderr?.on('data', (d) => saida.push(d.toString()));
const marcas = {};
const segs = () => ((Date.now() - t0) / 1000).toFixed(1);
let terminou = false;

function encerrar(codigo) {
  if (terminou) return; terminou = true;
  if (process.platform === 'win32') spawnSync('taskkill', ['/T', '/F', '/PID', String(filho.pid)], { stdio: 'ignore' });
  else try { process.kill(-filho.pid); } catch { filho.kill('SIGKILL'); }
  console.log(JSON.stringify({ lancador, stdio, porta, ...marcas }));
  if (codigo) console.log(saida.join('').slice(-800));
  rmSync(dados, { recursive: true, force: true });
  process.exit(codigo);
}
filho.on('exit', (c) => { if (!terminou) { marcas.saiu_com = c; encerrar(1); } });
setTimeout(() => { marcas.sem_resposta_s = segs(); encerrar(1); }, limite);

const sondar = () => {
  const r = http.get({ host: '127.0.0.1', port: porta, path: '/api/health', timeout: 2000 }, (res) => {
    let corpo = ''; res.on('data', (d) => (corpo += d));
    res.on('end', () => {
      try {
        const saude = JSON.parse(corpo);
        marcas.escuta_s ??= segs();
        if (saude.pronta) {
          marcas.pronta_s = segs();
          marcas.saude = saude;
          marcas.sala_json = existsSync(salaJson) ? JSON.parse(readFileSync(salaJson, 'utf8')).animada : null;
          encerrar(0);
        }
      } catch { /* resposta ainda não é a da sala */ }
    });
  });
  r.on('error', () => {}); r.on('timeout', () => r.destroy());
};
setInterval(sondar, 1000);
