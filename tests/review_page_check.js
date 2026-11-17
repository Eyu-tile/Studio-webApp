// Browser check of the review page (local.html): no script errors, comment pinned to the paused frame, a range,
// a reply, resolve, persistence across reload, Copy-notes output, no sideways scroll at phone width.
// Usage: node tests/review_page_check.js <review dir>   (prints JSON; exit 1 on any failure)
const { chromium } = require('playwright');

(async () => {
  const dir = process.argv[2];
  const fails = [];
  const errs = [];
  const ok = (cond, msg) => { if (!cond) fails.push(msg); };
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1360, height: 820 } });
  p.on('pageerror', (e) => errs.push(e.message));
  await p.goto('file://' + dir + '/local.html');
  await p.waitForFunction(() => document.querySelector('video').readyState >= 1, null, { timeout: 15000 });
  const seek = (t) => p.evaluate((x) => { document.querySelector('video').currentTime = x; }, t);

  await seek(2.5); await p.waitForTimeout(300);
  await p.fill('#nameInput', 'Tester');
  await p.click('#text'); await p.keyboard.type('First note'); await p.keyboard.press('Enter');
  await seek(8.0); await p.waitForTimeout(300); await p.click('#outBtn');
  await seek(6.0); await p.waitForTimeout(300);
  await p.click('#text'); await p.keyboard.type('Range note'); await p.keyboard.press('Enter');
  await p.locator('.list > .c').first().locator('text=Reply').click();
  await p.keyboard.type('A reply'); await p.keyboard.press('Enter');
  await p.waitForTimeout(200);
  ok((await p.$$('.pin')).length === 2, 'two pins on the timeline');
  ok(await p.isHidden('#replying'), 'reply bar closes after sending');

  await p.evaluate(() => { navigator.clipboard.writeText = (t) => { window.__c = t; return Promise.resolve(); }; });
  await p.click('#copyNotes'); await p.waitForTimeout(100);
  const notes = await p.evaluate(() => window.__c);
  ok(notes === '0:02.50 First note [replies: A reply]\n0:06.00-0:08.00 Range note', 'notes text: ' + JSON.stringify(notes));

  await p.locator('.list > .c').first().locator('text=Resolve').click();
  ok((await p.textContent('#counts')) === '1 open · 1 resolved', 'resolve updates counts');
  await p.reload(); await p.waitForTimeout(600);
  ok((await p.textContent('#counts')) === '1 open · 1 resolved', 'comments persist across reload');

  await seek(6.0); await p.waitForTimeout(300);
  ok((await p.textContent('#cur')).startsWith('00:00:06:'), 'timecode follows real seconds');
  await p.setViewportSize({ width: 400, height: 860 }); await p.waitForTimeout(200);
  ok((await p.evaluate(() => document.documentElement.scrollWidth)) <= 400, 'no sideways scroll at 400 px');
  ok(errs.length === 0, 'script errors: ' + errs.join('; '));
  await b.close();
  console.log(JSON.stringify({ fails }));
  process.exit(fails.length ? 1 : 0);
})();
