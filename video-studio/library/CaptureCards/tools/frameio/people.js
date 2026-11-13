const { chromium } = require('playwright');const fs=require('fs');
const REAL='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const A={};
function ing(o){if(!o||typeof o!=='object')return;if(Array.isArray(o)){o.forEach(ing);return;}
  if(o.id&&o.__typename&&/Asset$/.test(o.__typename)){const a=A[o.id]||{id:o.id};a.type=o.__typename;
    if(o.name)a.name=o.name;
    if(o.media&&o.media.original&&o.media.original.downloadUrl)a.dl=o.media.original.downloadUrl.replace(/\\u0026/g,'&');
    if(o.thumbnailImageUrl&&o.thumbnailImageUrl.url)a.thumb=o.thumbnailImageUrl.url;A[o.id]=a;}
  for(const k in o)ing(o[k]);}
async function dbl(p,t){try{await p.locator(`text="${t}"`).first().dblclick({timeout:9000});return true}catch(e){try{await p.locator(`text="${t}"`).first().click({timeout:4000});return true}catch(e2){return false}}}
(async()=>{const b=await chromium.launch({args:['--no-sandbox']});
 const p=await(await b.newContext({viewport:{width:1280,height:1400}})).newPage();
 p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){try{ing(JSON.parse(await r.text()));}catch(e){}}});
 await p.goto(REAL,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 await dbl(p,'TRUECLEAN'); await p.waitForTimeout(3500);
 Object.keys(A).forEach(k=>delete A[k]);
 await dbl(p,'Product & people'); await p.waitForTimeout(4500);
 // slow scroll to hydrate all
 await p.evaluate(()=>{let x=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;x=e;}});if(x)x.setAttribute('data-h','1');});
 let last=-1,st=0;
 for(let i=0;i<120;i++){await p.evaluate(()=>{const e=document.querySelector('[data-h="1"]')||document.scrollingElement;e.scrollTop+=700;});await p.waitForTimeout(900);
   const n=Object.values(A).filter(a=>a.thumb).length; if(n===last)st++;else{st=0;last=n;} if(st>=6)break;}
 const items=Object.values(A).filter(a=>a.name);
 fs.writeFileSync('dl/people.json',JSON.stringify(items,null,2));
 console.log('Product & people:',items.length,'items,',items.filter(a=>a.thumb).length,'w/thumb,',items.filter(a=>a.dl).length,'w/dl');
 items.forEach(a=>console.log('  ',a.name));
 await b.close();})();
