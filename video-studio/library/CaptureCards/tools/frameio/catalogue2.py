import json,re,os
cat=json.load(open('dl/catalogue.json'))
pplmap=json.load(open('ppl_thumbs/index_map.json'))   # "000"->name (Product&people index)
# people-folder content by reviewed ppl index (from 3 sheets)
PPL={
 'PRODUCT_PLACEMENT':[0,1,4,6,11,12,19,37,39,40,43,56,62,64,67,75,76,77,81,85,92,98,110,112,114,116,117,126?0 if False else 126,128,130,138,160,222,224],
 'PRODUCT_BOX':[16,30,31,38,42,53,60,74,89,95,100,101,132],
 'TESTIMONIAL':[7,8,18,25,26,27,28,32,33,34,35,48,52,65,69,96,97,106,108,119],
 'GROGGY_WAKING':[9,13,66,72,87,104,109],
 'NIGHTSTAND_PILLS':[5,10,71,73,88,94,113],
 'MAKE_BED_SHEETS':[14,15,20,29,57,58,59,82,84,90,102,115],
 'BEDROOM_EST':[21,22],
 'CTA_SCREEN':[36,105,120],
 'PRODUCT_CARD':[17,24,44,45,47,51,91,93,99,111,121,122,123,124],
 'SPRAY_CONTRAST':[46,68,78,80,83,125],
 'CLEAN_WASH':[79],
 'SYMPTOM_TIRED':[55,103],
 'MATTRESS_SLEEP':[107,118],
 'AVOID_PHONE_LIGHT':[23],
 'AVOID_CUT_OPEN_CATCH':[49,50,63],
}
ppl_idx2themes={}
for th,ids in PPL.items():
    for i in ids:
        if isinstance(i,int): ppl_idx2themes.setdefault(f"{i:03d}",[]).append(th)
name2ppl={v:k for k,v in pplmap.items()}
for n,v in cat.items():
    pi=name2ppl.get(n)
    if pi and pi in ppl_idx2themes:
        th=set(v['themes'])-{'UNTAGGED','UGC_PEOPLE'}
        th.update(ppl_idx2themes[pi])
        v['themes']=sorted(th)
    # mark remaining pure UGC_PEOPLE / UNTAGGED as real UGC B-roll (people+bedroom)
    if v['themes'] in (['UGC_PEOPLE'],['UNTAGGED']):
        v['themes']=['UGC_REALPERSON_BROLL']; v['low_confidence']=True
json.dump(cat,open('dl/catalogue.json','w'),indent=2)
from collections import Counter
tc=Counter(t for v in cat.values() for t in v['themes'])
print("UNTAGGED/generic now:",sum(1 for v in cat.values() if v['themes']==['UGC_REALPERSON_BROLL']))
print("distinct themes:",len(tc))
