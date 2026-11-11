// 用 CDP 驱动无头 Edge：支持注入主题、切换视口
// 用法: node scripts/shoot.mjs <url> <out.png> [width] [height] [theme] [mobile]
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const [url, out, w = '1440', h = '900', theme = 'light', mobile = '0', scroll = '0'] = process.argv.slice(2);
const port = 9300 + Math.floor(Math.random() * 400);
const profile = mkdtempSync(join(tmpdir(), 'edge-'));

const proc = spawn(EDGE, [
  '--headless=new',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  '--no-proxy-server',
  '--disable-gpu',
  '--hide-scrollbars',
  '--no-first-run',
  '--disable-features=Translate',
  'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitPort() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (r.ok) return;
    } catch {}
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
      if (m.id === msgId) {
        ws.removeEventListener('message', onMsg);
        m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result);
      }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}

function once(ws, event) {
  return new Promise((resolve) => {
    const onMsg = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.method === event) { ws.removeEventListener('message', onMsg); resolve(m.params); }
    };
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
  await rpc(ws, 'Emulation.setDeviceMetricsOverride', {
    width: +w, height: +h, deviceScaleFactor: mobile === '1' ? 2 : 1, mobile: mobile === '1',
  });

  let loaded = once(ws, 'Page.loadEventFired');
  await rpc(ws, 'Page.navigate', { url });
  await loaded;

  if (theme !== 'default') {
    await rpc(ws, 'Runtime.evaluate', { expression: `localStorage.setItem('theme','${theme}')` });
    loaded = once(ws, 'Page.loadEventFired');
    await rpc(ws, 'Page.reload');
    await loaded;
  }

  await sleep(1500);
  if (+scroll) {
    await rpc(ws, 'Runtime.evaluate', { expression: `window.scrollTo(0, ${+scroll})` });
    await sleep(900);
  }
  await sleep(700);
  const shot = await rpc(ws, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(out, Buffer.from(shot.data, 'base64'));
  console.log('saved', out);
  ws.close();
} finally {
  proc.kill();
  await sleep(400);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
