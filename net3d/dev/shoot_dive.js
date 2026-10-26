// Renders the dive frames and lays them out as a filmstrip.
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const frames = JSON.parse(fs.readFileSync('dive.json'));
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  page.on('pageerror', e => console.log('pageerror:', e.message));
  await page.goto('http://127.0.0.1:8765/index.html');
  await page.waitForFunction('window.ready === true');
  const imgs = [];
  for (const f of frames) {
    await page.evaluate(([s, p, l]) => window.render(s, p, l), [f.scene, f.pos, f.look]);
    imgs.push((await page.screenshot({ type: 'jpeg', quality: 88 })).toString('base64'));
  }
  const strip = await browser.newPage({ viewport: { width: 1640, height: 100 } });
  const cells = frames.map((f, i) => `<figure><img src="data:image/jpeg;base64,${imgs[i]}"><figcaption>${i + 1}. ${f.label}</figcaption></figure>`).join('');
  await strip.setContent(`<html><body style="margin:0;background:#1b1b1b;font:16px sans-serif;color:#ddd">
    <div style="display:grid;grid-template-columns:repeat(2,800px);gap:14px 20px;padding:14px">${cells}</div>
    <style>figure{margin:0}img{width:800px;height:450px;display:block}figcaption{padding:6px 2px}</style></body></html>`);
  await strip.screenshot({ path: 'net3d_dive_filmstrip.png', fullPage: true });
  await browser.close();
  console.log('ok');
})();
