const { chromium } = require('playwright');
const fs = require('fs');
const SHARE = 'https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: {width:1440,height:900} });
  const page = await ctx.newPage();
  const reqs = [];
  const gql = [];
  page.on('request', r => {
    const u = r.url();
    if (/frame\.io|frameusercontent|cloudfront|amazonaws|adobe/.test(u))
      reqs.push({m:r.method(), u});
  });
  page.on('response', async resp => {
    const u = resp.url();
    if (u.includes('/graphql') && resp.request().method()==='POST') {
      try {
        const pd = resp.request().postData();
        const op = pd ? (JSON.parse(pd).operationName || (Array.isArray(JSON.parse(pd))?JSON.parse(pd).map(x=>x.operationName).join(','):'?')) : '?';
        const body = await resp.text();
        gql.push({op, status:resp.status(), len:body.length, sample: body.slice(0,4000)});
      } catch(e){ gql.push({err:String(e)}); }
    }
  });
  await page.goto(SHARE, {waitUntil:'networkidle', timeout:60000}).catch(e=>console.log('goto:',e.message));
  await page.waitForTimeout(5000);
  await page.screenshot({path:'dl/share.png', fullPage:false});
  // try to read visible asset names
  const texts = await page.evaluate(() => {
    const out=[];
    document.querySelectorAll('[data-testid], [class*="asset"], [class*="card"], [aria-label]').forEach(el=>{
      const t=(el.getAttribute('aria-label')||el.textContent||'').trim();
      if(t && t.length<120) out.push(t);
    });
    return [...new Set(out)].slice(0,200);
  });
  fs.writeFileSync('dl/requests.json', JSON.stringify(reqs,null,2));
  fs.writeFileSync('dl/gql.json', JSON.stringify(gql,null,2));
  fs.writeFileSync('dl/texts.json', JSON.stringify(texts,null,2));
  console.log('REQS hosts:', [...new Set(reqs.map(r=>r.u.split("/")[2]))].join(', '));
  console.log('GQL ops:', gql.map(g=>g.op+':'+g.status).join(' | '));
  console.log('TEXTS count:', texts.length);
  await browser.close();
})();
