const { chromium } = require('playwright');const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const A={};
function ing(o){if(!o||typeof o!=='object')return;if(Array.isArray(o)){o.forEach(ing);return;}
  if(o.id&&o.__typename&&/Asset$/.test(o.__typename)){const a=A[o.id]||{id:o.id};a.type=o.__typename;
    if(o.name)a.name=o.name;
    if(o.media&&o.media.original&&o.media.original.downloadUrl)a.dl=o.media.original.downloadUrl.replace(/\\u0026/g,'&');
    if(o.thumbnailImageUrl&&o.thumbnailImageUrl.url)a.thumb=o.thumbnailImageUrl.url;A[o.id]=a;}
  for(const k in o)ing(o[k]);}
(async()=>{const b=await chromium.launch({args:['--no-sandbox']});
 const p=await(await b.newContext({viewport:{width:1280,height:1200}})).newPage();
 p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){try{ing(JSON.parse(await r.text()));}catch(e){}}});
 await p.goto(SHARE,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 await p.evaluate(()=>{let best=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;best=e;}});if(best)best.setAttribute('data-h','1');});
 let prevTop=-1,sameTop=0;
 for(let i=0;i<200;i++){
   const top=await p.evaluate(()=>{const e=document.querySelector('[data-h="1"]')||document.scrollingElement;e.scrollTop+=700;return e.scrollTop;});
   await p.waitForTimeout(1300); // let settle-hydration fire
   if(top===prevTop)sameTop++;else{sameTop=0;prevTop=top;}
   if(i%10===0)console.log('pass',i,'top',top,'with_dl',Object.values(A).filter(a=>a.dl).length);
   if(sameTop>=4)break; // reached bottom
 }
 // one more settle at bottom
 await p.waitForTimeout(2000);
 fs.writeFileSync('dl/manifest_dl.json',JSON.stringify(Object.values(A),null,2));
 console.log('FINAL with_dl:',Object.values(A).filter(a=>a.dl).length,'/',Object.keys(A).length);
 await b.close();})();
