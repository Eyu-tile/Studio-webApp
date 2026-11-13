const { chromium } = require('playwright');const fs=require('fs');
const REAL='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const A={};
function ing(o){if(!o||typeof o!=='object')return;if(Array.isArray(o)){o.forEach(ing);return;}
  if(o.id&&o.__typename&&/Asset$/.test(o.__typename)){const a=A[o.id]||{id:o.id};a.type=o.__typename;
    if(o.name)a.name=o.name;
    if(o.media&&o.media.original&&o.media.original.downloadUrl)a.dl=o.media.original.downloadUrl.replace(/\\u0026/g,'&');
    if(o.thumbnailImageUrl&&o.thumbnailImageUrl.url)a.thumb=o.thumbnailImageUrl.url;A[o.id]=a;}
  for(const k in o)ing(o[k]);}
async function dbl(p,t){try{await p.locator(`text="${t}"`).first().dblclick({timeout:8000});return true}catch(e){try{await p.locator(`text="${t}"`).first().click({timeout:4000});return true}catch(e2){return false}}}
(async()=>{const b=await chromium.launch({args:['--no-sandbox']});
 const p=await(await b.newContext({viewport:{width:1280,height:1200}})).newPage();
 p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){try{ing(JSON.parse(await r.text()));}catch(e){}}});
 await p.goto(REAL,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 await dbl(p,'TRUECLEAN'); await p.waitForTimeout(3500);
 for(const sub of ['Dust mites','Dust Mites','dustmites']){
   Object.keys(A).forEach(k=>delete A[k]);
   const ok=await dbl(p,sub); await p.waitForTimeout(4000);
   await p.evaluate(()=>{let x=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;x=e;}});if(x){for(let i=0;i<8;i++)x.scrollTop+=500;}});
   await p.waitForTimeout(3000);
   const items=Object.values(A).filter(a=>a.name);
   fs.writeFileSync(`dl/sub_${sub.replace(/[^A-Za-z]/g,'_')}.json`,JSON.stringify(items,null,2));
   console.log(`\n[${sub}] ${ok?'':'(no-open) '}${items.length} items`);
   items.forEach(a=>console.log('   ',a.name));
   await p.goBack().catch(()=>{}); await p.waitForTimeout(3000); await dbl(p,'TRUECLEAN'); await p.waitForTimeout(2500);
 }
 await b.close();})();
