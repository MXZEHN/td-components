// Renders each exported state from a few camera positions.
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const shots = JSON.parse(fs.readFileSync('scene.json'));
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('console', m => console.log('page:', m.text()));
  page.on('pageerror', e => console.log('pageerror:', e.message));
  await page.goto('http://127.0.0.1:8765/index.html');
  await page.waitForFunction('window.ready === true');
  const live = shots.live, fi = live.nodes.findIndex(n => n.name === 'feedback1');
  const fpos = [live.inst.tx[fi], live.inst.ty[fi], live.inst.fz[fi]];
  const views = [
    ['01_front', 'front', [5.0, -0.6, 11.2], [5.0, -0.6, 0]],
    ['02_layers', 'layers', [15.5, 6.5, 6.5], [5.0, -0.5, -3.5]],
    ['03_focus_level1', 'focus1', [15.5, 6.5, 6.5], [5.0, -0.5, -3.5]],
    ['04_reveal_explode', 'reveal', [17.5, 7.0, 7.5], [5.0, -0.5, -5.0]],
    ['06_reference_wires', 'layers', [14.5, 1.2, 3.2], [8.0, -1.2, -3.0]],
    ['05_live_follow', 'live', [fpos[0] + 0.6 - 1.2, fpos[1] - 0.4 + 0.3, fpos[2] + 3 + 1.2], fpos],
  ];
  for (const [name, key, pos, look] of views) {
    await page.evaluate(([s, p, l]) => window.render(s, p, l), [shots[key], pos, look]);
    await page.screenshot({ path: `net3d_${name}.png` });
    console.log('wrote', name);
  }
  await browser.close();
})();
