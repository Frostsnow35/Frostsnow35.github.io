// 验证：播放器跨页面持久、音量可调、导航后脚本仍工作
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const BASE = process.argv[2] || 'http://localhost:4323';
const port = 9600 + Math.floor(Math.random() * 300);
const profile = mkdtempSync(join(tmpdir(), 'edge-t-'));

const proc = spawn(EDGE, [
  '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--no-proxy-server', '--disable-gpu', '--no-first-run', '--autoplay-policy=no-user-gesture-required', 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let id = 0;
const rpc = (ws, method, params = {}) => new Promise((resolve, reject) => {
  const mid = ++id;
  const on = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id === mid) { ws.removeEventListener('message', on); m.error ? reject(new Error(m.error.message)) : resolve(m.result); }
  };
  ws.addEventListener('message', on);
  ws.send(JSON.stringify({ id: mid, method, params }));
});
const evaluate = async (ws, expr) => {
  const r = await rpc(ws, 'Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  return r.result.value;
};

try {
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break; } catch {}
    await sleep(200);
  }
  const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  await rpc(ws, 'Page.enable');
  await rpc(ws, 'Runtime.enable');

  await rpc(ws, 'Page.navigate', { url: BASE + '/' });
  await sleep(2500);

  // 打标记 + 设音量 0.7
  console.log('volume set:', await evaluate(ws, `(function(){var r=document.getElementById('vol');r.value=70;r.dispatchEvent(new Event('input',{bubbles:true}));var a=document.getElementById('bgm');a.dataset.mark='keep';return [r.value,a.volume,a.paused];})()`));
  await sleep(800);
  const before = await evaluate(ws, `(function(){var a=document.getElementById('bgm');return {t:a.currentTime,paused:a.paused,vol:a.volume,muted:a.muted};})()`);
  console.log('before nav:', JSON.stringify(before));

  // 点导航去 /posts/
  await evaluate(ws, `document.querySelector('a[href="/posts/"]').click()`);
  await sleep(2500);

  const after = await evaluate(ws, `(function(){
    var a=document.getElementById('bgm');
    var p=document.querySelector('[data-astro-transition-persist="player"]');
    return {
      url: location.pathname,
      sameNode: !!(a && a.dataset.mark === 'keep'),
      currentTime: a ? a.currentTime : null,
      paused: a ? a.paused : null,
      vol: a ? a.volume : null,
      rail: document.getElementById('vol') ? document.getElementById('vol').value : null,
      playerCount: document.querySelectorAll('#player').length,
      persisted: !!p
    };
  })()`);
  console.log('after nav:', JSON.stringify(after));

  // 导航后主题切换是否还能用（事件委托验证）
  await evaluate(ws, `document.getElementById('theme-toggle').click()`);
  await sleep(300);
  console.log('theme after click:', await evaluate(ws, `document.documentElement.dataset.theme`));
  await evaluate(ws, `document.getElementById('theme-toggle').click()`);

  // 返回首页，确认播放器依然只有一个且未重播
  await evaluate(ws, `document.querySelector('a[href="/"]').click()`);
  await sleep(2200);
  console.log('back home:', JSON.stringify(await evaluate(ws, `(function(){var a=document.getElementById('bgm');return {url:location.pathname,count:document.querySelectorAll('#player').length,same:!!(a&&a.dataset.mark==='keep'),t:a?a.currentTime:null,paused:a?a.paused:null,title:document.querySelector('.hero-title')?document.querySelector('.hero-title').textContent:null};})()`)));

  ws.close();
} finally {
  proc.kill();
  await sleep(400);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
