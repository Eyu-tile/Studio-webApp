const { chromium } = require('playwright');const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e678e'.replace('678e','009e');
const REAL='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
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
 await p.goto(REAL,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});await p.waitForTimeout(4000);
 for(const folder of ['TRUECLEAN','Dust mites']){
   Object.keys(A).forEach(k=>delete A[k]);
   try{ await p.locator(`text="${folder}"`).first().dblclick({timeout:8000}); }
   catch(e){ try{await p.locator(`text="${folder}"`).first().click({timeout:5000});}catch(e2){console.log('no click',folder,e2.message);} }
   await p.waitForTimeout(4000);
   // scroll a bit to hydrate
   await p.evaluate(()=>{let best=null,g=0;document.querySelectorAll('*').forEach(e=>{const d=e.scrollHeight-e.clientHeight;if(d>g&&e.clientHeight>300){g=d;best=e;}});if(best){for(let i=0;i<6;i++)best.scrollTop+=600;}});
   await p.waitForTimeout(3000);
   const items=Object.values(A).filter(a=>a.name);
   fs.writeFileSync(`dl/folder_${folder.replace(/ /g,'_')}.json`,JSON.stringify(items,null,2));
   console.log(folder,'->',items.length,'items:',items.map(a=>a.name).join(' | ').slice(0,200));
   // go back
   await p.goBack().catch(()=>{}); await p.waitForTimeout(3000);
 }
 await b.close();})();
