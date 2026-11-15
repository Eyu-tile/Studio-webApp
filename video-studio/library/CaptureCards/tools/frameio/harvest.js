const { chromium } = require('playwright');const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const assets={};
function ingest(obj){
  if(!obj||typeof obj!=='object')return;
  if(Array.isArray(obj)){obj.forEach(ingest);return;}
  if(obj.id && obj.__typename && /Asset$/.test(obj.__typename)){
    const a=assets[obj.id]||{id:obj.id};
    a.type=obj.__typename;
    if(obj.name)a.name=obj.name;
    if('duration'in obj)a.duration=obj.duration;
    if(obj.media){a.mime=obj.media.mimeType;if(obj.media.filesize)a.filesize=obj.media.filesize;}
    if(obj.filesize)a.filesize=obj.filesize;
    if(obj.thumbnailImageUrl&&obj.thumbnailImageUrl.url)a.thumb=obj.thumbnailImageUrl.url;
    if(obj.downloads&&Array.isArray(obj.downloads)){const o=obj.downloads.find(d=>d.key==='original');if(o)a.dl=o.downloadUrl;}
    if(obj.download&&obj.download.downloadUrl)a.dl=obj.download.downloadUrl;
    assets[obj.id]=a;
  }
  for(const k in obj)ingest(obj[k]);
}
(async()=>{
  const b=await chromium.launch({args:['--no-sandbox']});
  const p=await(await b.newContext({viewport:{width:1440,height:1600}})).newPage();
  p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){
    try{const j=JSON.parse(await r.text());ingest(j);}catch(e){}}});
  await p.goto(SHARE,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});
  await p.waitForTimeout(4000);
  // scroll the asset grid to lazy-load everything
  let last=0,stable=0;
  for(let i=0;i<300;i++){
    await p.mouse.wheel(0,3000);
    await p.waitForTimeout(500);
    const n=Object.values(assets).filter(a=>a.name).length;
    if(n===last){stable++;}else{stable=0;last=n;}
    if(i%10===0)console.log('pass',i,'assets',n);
    if(stable>=12)break;
  }
  fs.writeFileSync('dl/manifest.json',JSON.stringify(Object.values(assets),null,2));
  const withName=Object.values(assets).filter(a=>a.name);
  console.log('TOTAL assets captured:',Object.keys(assets).length,'| with name:',withName.length);
  await b.close();
})();
