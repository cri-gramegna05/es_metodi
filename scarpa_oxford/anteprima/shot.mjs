// Anteprime PNG della scarpa con three.js in Chromium headless.
// Uso (da scarpa_oxford/anteprima):  npm install && node shot.mjs
import {chromium} from 'playwright-core';
import http from 'http'; import fs from 'fs'; import path from 'path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const GLB = '../output/oxford_42_dx.glb';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const VISTE = [
  {q: 'az=-90&el=5&title=Esterno', out: 'v_esterno.png'},
  {q: 'az=90&el=5&title=Interno', out: 'v_interno.png'},
  {q: 'az=-38&el=24&title=Tre%20quarti', out: 'v_trequarti.png'},
  {q: 'az=200&el=18&title=Retro', out: 'v_retro.png'},
  {q: 'az=-62&el=28&esploso=tomaia&labels=1&title=Tomaia%20-%20pezzi%20esterni', out: 'esploso_tomaia.png'},
  {q: 'az=-62&el=28&esploso=interno&labels=1&title=Fodere%2C%20rinforzi%2C%20sottopiede', out: 'esploso_interno.png'},
];
const tipi = {'.js': 'text/javascript', '.html': 'text/html', '.mjs': 'text/javascript'};
const srv = http.createServer((req, res) => {
  const p = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
  fs.readFile(p, (e, d) => {
    if (e) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, {'Content-Type': tipi[path.extname(p)] || 'application/octet-stream'}); res.end(d);
  });
}).listen(8765);
const b = await chromium.launch({executablePath: CHROME,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
fs.mkdirSync(path.join(ROOT, 'anteprima', 'png'), {recursive: true});
for (const v of VISTE) {
  const pg = await b.newPage({viewport: {width: 1200, height: 700}});
  pg.on('pageerror', e => console.log('errore pagina:', e.message));
  await pg.goto(`http://localhost:8765/anteprima/render.html?glb=${GLB}&w=1200&h=700&${v.q}`);
  await pg.waitForFunction('window.PRONTO === true', {timeout: 180000});
  await pg.screenshot({path: path.join(ROOT, 'anteprima', 'png', v.out)});
  await pg.close(); console.log('ok', v.out);
}
await b.close(); srv.close();
