// E2E check of the drawio-live stack: handshake, render, and live load of an
// external file edit. Requires playwright (see references/setup.md for the
// NODE_PATH hint if it is not resolvable).
//   BRIDGE_URL=http://100.x.y.z:8765 node e2e.cjs
// CommonJS on purpose: NODE_PATH resolution works with require but not ESM import.
const { chromium } = require('playwright');

(async () => {
const BRIDGE = process.env.BRIDGE_URL || 'http://127.0.0.1:8765';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(BRIDGE + '/', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() =>
  /loaded|saved/.test(document.getElementById('status').textContent), null, { timeout: 30000 });
console.log('handshake OK:', await page.textContent('#status'));
const frame = page.frames().find(f => f !== page.mainFrame());
await frame.waitForSelector('.geDiagramContainer', { timeout: 15000 });
console.log('editor UI rendered');

const orig = await (await fetch(BRIDGE + '/diagram')).text();
const marker = 'e2e-' + process.pid;
const edited = orig.replace('</root>',
  `<mxCell id="${marker}" parent="1" style="text;html=1;" value="${marker}" vertex="1">` +
  `<mxGeometry height="20" width="100" x="0" y="0" as="geometry"/></mxCell></root>`);
await fetch(BRIDGE + '/diagram', { method: 'POST', body: edited });
await page.waitForFunction(() =>
  document.getElementById('status').textContent.includes('agent edit'), null, { timeout: 15000 });
const seen = await frame.evaluate(m => document.body.innerHTML.includes(m), marker);
await fetch(BRIDGE + '/diagram', { method: 'POST', body: orig });   // restore
await browser.close();
if (!seen) { console.error('FAIL: external edit not visible in editor'); process.exit(1); }
console.log('E2E PASS — external edits load into the live editor');
})();
