// 检查 View Transitions 下的两件事：giscus 是否在客户端导航后仍能挂载、首屏动效脚本是否重新生效
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = process.argv[2] || 'http://localhost:4400';
const port = 9800 + Math.floor(Math.random() * 150);
const profile = mkdtempSync(join(tmpdir(), 'edge-g-'));

const proc = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--no-proxy-server', '--disable-gpu', '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let id = 0;
const rpc = (ws, method, params = {}) => new Promise((resolve, reject) => {
  const mid = ++id;
  const on = (ev) => { const m = JSON.parse(ev.data); if (m.id === mid) { ws.removeEventListener('message', on); m.error ? reject(new Error(m.error.message)) : resolve(m.result); } };
  ws.addEventListener('message', on);
  ws.send(JSON.stringify({ id: mid, method, params }));
});
const ev = async (ws, e) => (await rpc(ws, 'Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result.value;

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break; } catch {} await sleep(200); }
  const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  await rpc(ws, 'Page.enable'); await rpc(ws, 'Runtime.enable');

  await rpc(ws, 'Page.navigate', { url: BASE + '/' });
  await sleep(2500);
  console.log('home magnet wired:', await ev(ws, `document.querySelector('.field')?.dataset.magnet`));

  // 客户端导航到留言页
  await ev(ws, `document.querySelector('a[href="/guestbook/"]').click()`);
  await sleep(3500);
  console.log('guestbook:', JSON.stringify(await ev(ws, `({path:location.pathname, iframes:document.querySelectorAll('iframe').length, giscusScript:document.querySelectorAll('script[src*="giscus.app"]').length, wrap:!!document.querySelector('.giscus-wrap')})`)));

  // 再回首页，检查磁吸脚本是否重新绑定到新的 .field
  await ev(ws, `document.querySelector('a[href="/"]').click()`);
  await sleep(2500);
  console.log('back home magnet:', JSON.stringify(await ev(ws, `({path:location.pathname, magnet:document.querySelector('.field')?.dataset.magnet, title:document.querySelector('.hero-title')?.textContent, eye:!!document.querySelector('.hero-eyebrow'), scrollText:document.querySelector('.scroll span')?.textContent || null})`)));

  // 检查 giscus 应用安装状态（网络请求层面）
  console.log('iframes after return:', await ev(ws, `document.querySelectorAll('iframe').length`));
  ws.close();
} finally {
  proc.kill();
  await sleep(400);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
