import json,sys,os,io,urllib.request
from PIL import Image,ImageDraw
H="https://buildyourads.com"; K=os.environ.get("BYA_KEY","bya_live_injected_by_proxy"); out=sys.argv[1]; ids=sys.argv[2:]
W=300; cols=5; rows=(len(ids)+cols-1)//cols; sheet=Image.new('RGB',(W*cols,W*rows),'gray'); d=ImageDraw.Draw(sheet)
for i,cid in enumerate(ids):
    req=urllib.request.Request(f"{H}/api/v1/clips/{cid}",headers={"Authorization":"Bearer "+K,"User-Agent":"video-studio/1.0"})
    c=json.load(urllib.request.urlopen(req,timeout=30)); c=c.get('clip',c)
    try:
        im=Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(c['thumbUrl'],headers={'User-Agent':'video-studio/1.0'}),timeout=30).read())).convert('RGB'); im.thumbnail((W,W-16)); sheet.paste(im,((i%cols)*W,(i//cols)*W+16))
    except Exception as e: print('err',cid,e)
    d.text(((i%cols)*W+3,(i//cols)*W+2),f"{i} {c['filename'][:36]}",fill='yellow')
sheet.save(out)
