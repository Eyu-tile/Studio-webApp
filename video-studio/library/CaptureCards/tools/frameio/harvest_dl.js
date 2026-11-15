const { chromium } = require('playwright');const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const A={};
function ing(o){if(!o||typeof o!=='object')return;if(Array.isArray(o)){o.forEach(ing);return;}
  if(o.id&&o.__typename&&/Asset$/.test(o.__typename)){const a=A[o.id]||{id:o.id};a.type=o.__typename;
    if(o.name)a.name=o.name;
    if(o.media&&o.media.original&&o.media.original.downloadUrl)a.dl=o.media.original.downloadUrl.replace(/\\u0026/g,'&');
    if(o.thumbnailImageUrl&&o.thumbnailImageUrl.url)a.thumb=o.thumbnailImageUrl.url;
    A[o.id]=a;}
  for(const k in o)ing(o[k]);}
(async()=>{const b=await chromium.launch({args:['--no-sandbox']});
 const p=await(await b.newContext({viewport:{width:1440,height:1600}})).newPage();
 p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){try{ing(JSON.parse(await r.text()));}catch(e){}}});
 await p.goto(SHARE,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 await p.evaluate(()=>{let best=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;best=e;}});if(best)best.setAttribute('data-h','1');});
 let last=0,st=0;
 for(let i=0;i<400;i++){await p.evaluate(()=>{const e=document.querySelector('[data-h="1"]')||document.scrollingElement;e.scrollTop+=1000;});
   await p.waitForTimeout(450);const n=Object.values(A).filter(a=>a.dl).length;if(n===last)st++;else{st=0;last=n;}
   if(i%20===0)console.log('pass',i,'with_dl',n);if(st>=25)break;}
 fs.writeFileSync('dl/manifest_dl.json',JSON.stringify(Object.values(A),null,2));
 console.log('FINAL with_dl:',Object.values(A).filter(a=>a.dl).length,'/',Object.keys(A).length);
 await b.close();})();
