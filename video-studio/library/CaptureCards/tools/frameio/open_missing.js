const { chromium } = require('playwright');const fs=require('fs');
const REAL='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const want=JSON.parse(fs.readFileSync(process.argv[2]));const A={};
function ing(o){if(!o||typeof o!=='object')return;if(Array.isArray(o)){o.forEach(ing);return;}
  if(o.id&&o.__typename&&/Asset$/.test(o.__typename)){const a=A[o.id]||{id:o.id};a.type=o.__typename;if(o.name)a.name=o.name;
    if(o.media&&o.media.original&&o.media.original.downloadUrl)a.dl=o.media.original.downloadUrl.replace(/\\u0026/g,'&');A[o.id]=a;}
  for(const k in o)ing(o[k]);}
async function dbl(p,t){try{await p.locator(`text="${t}"`).first().dblclick({timeout:8000});return true}catch(e){return false}}
(async()=>{const b=await chromium.launch({args:['--no-sandbox']});
 const p=await(await b.newContext({viewport:{width:1280,height:1400}})).newPage();
 p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){try{ing(JSON.parse(await r.text()));}catch(e){}}});
 await p.goto(REAL,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 await dbl(p,'TRUECLEAN'); await p.waitForTimeout(3500); await dbl(p,'Product & people'); await p.waitForTimeout(4500);
 const folderUrl=p.url();
 for(const n of want){
   const have=()=>Object.values(A).find(a=>a.name===n&&a.dl); if(have())continue;
   let found=false;
   await p.evaluate(()=>{let x=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;x=e;}});if(x){x.setAttribute('data-h','1');x.scrollTop=0;}});
   for(let i=0;i<60&&!found;i++){
     if(await p.locator(`text="${n}"`).count()>0){found=true;break;}
     await p.evaluate(()=>{const e=document.querySelector('[data-h="1"]');if(e)e.scrollTop+=500;}); await p.waitForTimeout(500);}
   if(!found){console.log('notfound',n);continue;}
   await p.locator(`text="${n}"`).first().scrollIntoViewIfNeeded().catch(()=>{});
   await p.waitForTimeout(2500);
   if(!have()){await dbl(p,n); await p.waitForTimeout(5000); await p.goto(folderUrl,{waitUntil:'networkidle',timeout:60000}).catch(()=>{}); await p.waitForTimeout(3000);}
   console.log(n, have()?'OK':'nodl');
 }
 fs.writeFileSync('dl/missing_dl.json',JSON.stringify(Object.values(A).filter(a=>want.includes(a.name)&&a.dl),null,2));
 await b.close();})();
