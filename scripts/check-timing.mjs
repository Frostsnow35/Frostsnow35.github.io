// 采样打字机时间线，确认节奏（名字/签名的出现、停留、退格）
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const url = process.argv[2] || 'http://localhost:4321/';
const port = 9600 + Math.floor(Math.random() * 300);
const profile = mkdtempSync(join(tmpdir(), 'edge-'));

const proc = spawn(EDGE, [
  '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--no-proxy-server', '--disable-gpu', '--no-first-run', '--disable-features=Translate', 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitPort() {
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) return; } catch {}
    await sleep(200);
  }
  throw new Error('devtools not ready');
}

let id = 0;
function rpc(ws, method, params = {}) {
  const msgId = ++id;
  return new Promise((resolve, reject) => {
    const onMsg = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id === msgId) { ws.removeEventListener('message', onMsg); m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result); }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
function once(ws, event) {
  return new Promise((resolve) => {
    const onMsg = (ev) => { const m = JSON.parse(ev.data); if (m.method === event) { ws.removeEventListener('message', onMsg); resolve(m.params); } };
    ws.addEventListener('message', onMsg);
  });
}

try {
  await waitPort();
  const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  await rpc(ws, 'Page.enable');
  await rpc(ws, 'Runtime.enable');
  const loaded = once(ws, 'Page.loadEventFired');
  await rpc(ws, 'Page.navigate', { url });
  await loaded;

  const start = Date.now();
  const rows = [];
  for (let i = 0; i < 130; i++) {
    const r = await rpc(ws, 'Runtime.evaluate', {
      expression: `(() => {
        const n = document.querySelector('.hero-title .typed-txt');
        const g = document.querySelector('.hero-tag .typed-txt');
        return (n ? n.textContent : '') + ' | ' + (g ? g.textContent : '');
      })()`,
      returnByValue: true,
    });
    rows.push([Date.now() - start, r.result.value]);
    await sleep(100);
  }

  // 压缩连续相同状态，输出关键时刻
  let prev = null;
  for (const [t, v] of rows) {
    const kind = v.includes('|') ? v.split(' | ') : [''];
    const state = `${kind[0].length}/${kind[1] ? kind[1].length : 0}`;
    if (state !== prev) { console.log(String(t).padStart(6), state.padEnd(8), v.slice(0, 60)); prev = state; }
  }
  ws.close();
} finally {
  proc.kill();
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
