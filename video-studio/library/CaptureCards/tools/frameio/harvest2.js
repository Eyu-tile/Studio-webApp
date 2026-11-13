const { chromium } = require('playwright');const fs=require('fs');
const SHARE='https://next.frame.io/share/b60a2849-ccfb-489d-8390-6d7f736e5677/839d9983-9579-4204-98c6-009c87b4e98e';
const assets={};
function ingest(obj){
  if(!obj||typeof obj!=='object')return;
  if(Array.isArray(obj)){obj.forEach(ingest);return;}
  if(obj.id && obj.__typename && /Asset$/.test(obj.__typename)){
    const a=assets[obj.id]||{id:obj.id};a.type=obj.__typename;
    if(obj.name)a.name=obj.name;
    if('duration'in obj&&obj.duration!=null)a.duration=obj.duration;
    if(obj.media){a.mime=obj.media.mimeType;if(obj.media.filesize)a.filesize=obj.media.filesize;}
    if(obj.filesize)a.filesize=obj.filesize;
    if(obj.thumbnailImageUrl&&obj.thumbnailImageUrl.url)a.thumb=obj.thumbnailImageUrl.url;
    assets[obj.id]=a;
  }
  for(const k in obj)ingest(obj[k]);
}
(async()=>{
  const b=await chromium.launch({args:['--no-sandbox']});
  const p=await(await b.newContext({viewport:{width:1440,height:1600}})).newPage();
  p.on('response',async r=>{if(r.url().includes('/graphql')&&r.request().method()==='POST'){
    try{ingest(JSON.parse(await r.text()));}catch(e){}}});
  await p.goto(SHARE,{waitUntil:'networkidle',timeout:60000}).catch(()=>{});
  await p.waitForTimeout(4000);
  // find the scrollable grid container (max scrollHeight-clientHeight)
  const pickSel = await p.evaluate(()=>{
    let best=null,bestGap=0;
    document.querySelectorAll('*').forEach(el=>{
      const gap=el.scrollHeight-el.clientHeight;
      if(gap>bestGap && el.clientHeight>300){bestGap=gap;best=el;}
    });
    if(best){best.setAttribute('data-harvest','1');return bestGap;}
    return 0;
  });
  console.log('scroll container gap:',pickSel);
  let last=0,stable=0;
  for(let i=0;i<400;i++){
    await p.evaluate(()=>{const e=document.querySelector('[data-harvest="1"]')||document.scrollingElement;e.scrollTop+=1200;});
    await p.waitForTimeout(450);
    const n=Object.values(assets).filter(a=>a.name).length;
    if(n===last)stable++;else{stable=0;last=n;}
    if(i%15===0)console.log('pass',i,'named',n);
    if(stable>=20)break;
  }
  fs.writeFileSync('dl/manifest.json',JSON.stringify(Object.values(assets),null,2));
  console.log('FINAL ids:',Object.keys(assets).length,'named:',Object.values(assets).filter(a=>a.name).length);
  await b.close();
})();
