import json,re,os
C=json.load(open('dl/catalogue_raw.json'))
idxmap=json.load(open('allthumbs/map.json'))      # "000"->name  (root indices I reviewed)
name2idx={v:k for k,v in idxmap.items()}
# ---- UGC content by reviewed ROOT index (from visual sheet review) ----
IDX={
 'NASAL_SPRAY_USE':[0,3,4,5,6],'NASAL_SPRAY_PRODUCT':[2],
 'SINUS_ANATOMY':[7,10,232],
 'SYMPTOM_CONGESTION':[180,188,199,209,220,221,269,276,277,281,284,286,290,331,337,336-1],
 'SYMPTOM_EYES':[18,27,32,172,179],
 'SYMPTOM_TIRED':[55,103,145,146,168,217,226,272,275,291,338,298],
 'GROGGY_WAKING':[13,66,72,109,150,157,218,233,234,305,339,80],
 'PILLS':[215,238],
 'DOCTOR_PAPERWORK':[214,216,230],
 'PRODUCTS_SHELF':[175,183,189,195,208,210],
 'MULTI_SPRAYS':[175],
 'SPRAY_CONTRAST':[46,68,78,80,83,116,117,118,125,127,191],
 'CLEAN_WASH':[171,185,193,194,196,201,206,278],
 'MAKE_BED_SHEETS':[57,58,59,82,84,86,90,102,129,143,155,171,190,192,200,204,205,211,225,288],
 'CLEAN_VACUUM':[158,159,182,186,212,213],
 'CLEAN_SPRAY':[149,162,165],
 'MATTRESS_REVEAL':[266,294,299,307,308,319,320,324,325,332],
 'MITE_COLONY':[35,167,237,239,240,244,246,247,248,249,250,252,253,254,255,256,258,261,264,265,267,268,270,273,274,280,282,287,289,292,293,296,297,303,309,311,312,314],
 'MECHANISM_LURE':[11,12,21,22,24,25,37,40,229,259,263,283,313,315],
 'MECHANISM_DISCARD':[300],
 'PRODUCT_PLACEMENT':[43,64,67,75,76,77,81,85,92,98,104,110,117,126,128,130,138,160,222,224],
 'PRODUCT_BOX':[16,29,30,38,42,53,60,74,89,95,100,101,114,132],
 'PRODUCT_CARD':[18,19,20,27,28,34,47,48,56,91,93,99,111,121,122,123,124,133,134,136,251,327,334],
 'PRODUCT_HERO':[241,327],
 'TESTIMONIAL':[48,65,69,135,227,228,52,54,140,141,177,178],
 'LAB':[15,257],
 'CTA_SCREEN':[36,106,119,120,236,304,306],
 'GUARANTEE':[328],
 'REMINDER':[105,137],
 'BEDROOM_EST':[8,144,152,156,174,181,223,235,287,326,329,335],
 'AVOID_BEFORE_AFTER':[31],
 'AVOID_CUT_OPEN_CATCH':[17,49,50,51,63,231,243,316,317,321],
 'AVOID_PHONE_LIGHT':[23,131,318],
 'TITLE_CARD':[1],
}
idx2themes={}
for theme,ids in IDX.items():
    for i in ids: idx2themes.setdefault(f"{i:03d}",[]).append(theme)
# ---- filename-based tagging (AI/descriptive names) ----
def fname_themes(n):
    t=[]; s=n.lower()
    def has(*p): return any(re.search(x,s) for x in p)
    if has(r'sneez'): t.append('SYMPTOM_SNEEZE')
    if has(r'cough'): t.append('SYMPTOM_COUGH')
    if has(r'struggl|can.?t breathe|blocked|congest|stuffy|obstru'): t.append('SYMPTOM_CONGESTION')
    if has(r'nasal.?cav|sinus|nose.?blocked|nasal congestion|septoplasty'): t.append('SINUS_ANATOMY')
    if has(r'nasal spr|nasal sprey|otrivine|decongest'): t.append('NASAL_SPRAY_USE')
    if has(r'taking.?pill|antihist|pill.?drink'): t.append('PILLS')
    if has(r'waking.?up.?well|well.?rested|refreshed'): t.append('RELIEF_RESTED')
    if has(r'sleep|sleeps|sleeping|woman sleeps'): t.append('SLEEPING')
    if has(r'feeding on skin|leaving dropping|absorbing moisture|dead skin|proteins'): t.append('MITE_FEEDING')
    if has(r'inside_?mattress|inside.?pillow|moving_?inside|crawling_?inside|emerging_?from|in_?pillow_?mattress|colony|microscopic_?dust|dust.?mites.?(crawl|inside|moving|in )'): t.append('MITE_COLONY')
    if has(r'\bmite\b.*(macro|single|closeup)|a dust mite in the mattress|3d-microscopic|dust mite animation|dust mites animation'): t.append('MITE_MACRO')
    if has(r'attract|lure|capture_card_attract'): t.append('MECHANISM_LURE')
    if has(r'trapped_in_adhesive|mites_on_card|crawling_to_card|illuminating_dust_mites_on_card|adhesive'): t.append('MECHANISM_TRAP')
    if has(r'card (operation|composition)|trueclean card|mite-?capture|capturecard|product_showcase'): t.append('PRODUCT_CARD')
    if has(r'before ?- ?after|before-after'): t.append('AVOID_BEFORE_AFTER')
    if has(r'bait doesn|dust-?mite cover'): t.append('AVOID_PROBLEM')
    if has(r'b-roll'): t.append('UGC_PEOPLE')
    if has(r'tiktokdownload'): t.append('UGC_SOCIAL')
    if has(r'reference\.jpg|box_reference|card_reference|pad_reference|cut_open_reference'): t.append('PRODUCT_REFERENCE_IMG')
    return t
out={}
for n,c in C.items():
    idx=name2idx.get(n)
    themes=set(fname_themes(n))
    if idx and idx in idx2themes: themes.update(idx2themes[idx])
    # curation
    cur=[]
    if 'ProblemClips' in c['folders']: cur.append('AVOID(ProblemClips)')
    if 'RealProductRefs' in c['folders']: cur.append('APPROVED_PRODUCT')
    if 'CTA' in c['folders']: cur.append('APPROVED_CTA')
    # compliance
    comp=[]
    if any(x.startswith('AVOID') for x in themes) or 'AVOID(ProblemClips)' in cur: comp.append('AVOID')
    out[n]={'folders':c['folders'],'curation':cur,'themes':sorted(themes) or ['UNTAGGED'],
            'compliance':comp,'root_index':idx,'is_image':n.lower().endswith(('.jpg','.jpeg','.png','.webp')),
            'thumb':c.get('thumb')}
json.dump(out,open('dl/catalogue.json','w'),indent=2)
# stats
from collections import Counter
tc=Counter(t for v in out.values() for t in v['themes'])
print("catalogued",len(out),"files")
print("UNTAGGED:",sum(1 for v in out.values() if v['themes']==['UNTAGGED']))
print("\nthemes:")
for t,n in tc.most_common(): print(f"  {t:24} {n}")
