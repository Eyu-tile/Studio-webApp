const { chromium } = require('playwright');
const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
(async()=>{
  const b=await chromium.launch({args:['--no-sandbox']});
  const p=await (await b.newContext({viewport:{width:1440,height:900}})).newPage();
  const cmt=[];
  p.on('response',async r=>{
    if(r.url().includes('/graphql')&&r.request().method()==='POST'){
      try{const pd=r.request().postData();const op=pd?JSON.parse(pd).operationName:'';
        if(op&&/Comment/i.test(op)){const t=await r.text();cmt.push({op,status:r.status(),sample:t.slice(0,2500)});}
      }catch(e){}
    }
  });
  await p.goto(SHARE,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});
  await p.waitForTimeout(3000);
  // click first asset tile to open viewer (which loads comments)
  const tile=await p.$('[aria-label^="Select asset"]')||await p.$('[class*="asset"]');
  try{ await p.locator('text=Download Asset').first().scrollIntoViewIfNeeded(); }catch(e){}
  try{
    await p.locator('[aria-label^="tiktokdownload"], [aria-label*=".mp4"]').first().click({timeout:8000});
  }catch(e){ console.log('click1 fail',e.message);
    try{ await p.locator('img, [class*="thumb"], [class*="card"]').first().dblclick({timeout:8000}); }catch(e2){console.log('click2 fail',e2.message);} }
  await p.waitForTimeout(6000);
  await p.screenshot({path:'dl/viewer.png'});
  fs.writeFileSync('dl/comments.json',JSON.stringify(cmt,null,2));
  console.log('comment ops:',cmt.map(c=>c.op+':'+c.status).join(' | ')||'(none fired)');
  await b.close();
})();
