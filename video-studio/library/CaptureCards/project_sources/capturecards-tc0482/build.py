import json, subprocess, os, sys
sys.path.insert(0, '/tmp/claude-0/-home-user-video-studio-claude-plugin/c77d22ec-6b89-5b09-a2c3-205b160242d8/scratchpad')
from ass451 import A, tw, ts
os.chdir('/home/user/video-studio-claude-plugin/video-studio/projects/capturecards-tc0482')
S = json.load(open('work/script.json')); M = json.load(open('raw/map.json'))
H = sys.argv[1]
def dur(p): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',p],capture_output=True,text=True).stdout.strip())
BODY = [f'B{i:02d}' for i in range(1,9)]; ORDER = [H] + BODY
V2 = os.environ.get('VOV') == 'v2'; V3 = os.environ.get('VOV') in ('v3','v4'); VS = os.environ.get('VOV','')
J = json.load(open(f'work/vo/{H}_{VS}_align.json' if V3 else (f'work/vo/{H}_v2_align.json' if V2 else f'work/vo/{H}_t_align.json'))); al = J['al']
ch, cs, ce = al['characters'], al['character_start_times_seconds'], al['character_end_times_seconds']
toks = []; i = 0
while i < len(ch):
    if ch[i] == ' ': i += 1; continue
    j = i
    while j < len(ch) and ch[j] != ' ': j += 1
    toks.append((''.join(ch[i:j]), cs[i], ce[j-1])); i = j
per = [len(S[k].split()) for k in ORDER]
assert sum(per) == len(toks), (sum(per), len(toks))
LW = {}; p = 0
for k, n in zip(ORDER, per): LW[k] = toks[p:p+n]; p += n
TOTAL = dur(f'work/vo/{H}_{VS}.mp3' if V3 else (f'work/vo/{H}_v2.mp3' if V2 else f'work/vo/{H}_t.mp3')) + 0.8
def T(line, wi): return LW[line][wi][1]

HOOK = {'H1': [('H1',0,'PHOOK',0)], 'H2': [('H2',0,'PHOOK',1)], 'H3': [('H3',0,'PHOOK',2)]}   # option C: presenter says the hook
body = [tuple(x) for x in json.load(open('work/shots.json')) if x[0] != 'H2']
SHOTS = HOOK[H] + body
# TC0128-style presenter inserts (Higgsfield Seedance 2.5 lip-sync clip), keyed by (line, word) -> presenter line index
PRES = {('B02',0):2, ('B03',19):3, ('B06',0):4, ('B08',0):5}
PSEG = json.load(open('work/vo/presenter_lines.json')); PSRC = os.path.abspath('raw/higgsfield/presenter_talk.mp4')
if os.path.exists(PSRC):
    M['PRESENTER'] = PSRC
    PMAP = json.load(open('work/vo/presenter_map.json')); HMAP = json.load(open('work/vo/presenter_hooks_map.json')); M['PHOOK'] = os.path.abspath('raw/higgsfield/presenter_hooks.mp4')
    SHOTS = [(l,w,'PRESENTER',PRES[(l,w)]) if (l,w) in PRES else (l,w,n,i) for l,w,n,i in SHOTS]
if V2:   # presenter v2: realistic woman, her own voice, keyed lines
    M['PRESENTER'] = M['PHOOK'] = os.path.abspath('raw/higgsfield/presenter2_talk.mp4')
    PMAP = HMAP = json.load(open('work/vo/presenter2_map.json'))
    K2 = {('B02',0):'P_wash', ('B03',19):'P_clean', ('B06',0):'P_card', ('B08',0):'P_homes'}
    SHOTS = [(l,w,'PHOOK',H) if (l,w)==(H,0) else ((l,w,'PRESENTER',K2[(l,w)]) if (l,w) in K2 else (l,w,n,i)) for l,w,n,i in SHOTS]
SHOTS.insert([k for k,s in enumerate(SHOTS) if s[0]=='B06'][0], ('B05',4,'hf_20260820_184313',2.4))   # 'the card gets heavier'
if V3:   # TC0128-style opening (VO over matching B-roll), presenter only in the body, every shot matched to its words
    SV = json.load(open('work/shots_v3.json'))
    SHOTS = [tuple(x) for x in SV['hooks'][H] + SV['body']]
    PN = '4' if VS == 'v4' else '3'
    M['PRESENTER'] = os.path.abspath(f'raw/higgsfield/presenter{PN}_talk.mp4')
    PMAP = json.load(open(f'work/vo/presenter{PN}_map.json'))
TRANS = {}   # TC0128 reference: hard cuts only
if V3:   # transitions at section changes; no SFX on transitions (SFX only on the X signs)
    TRANS = {('B01',0):('zoomin',0.3), ('B03',0):('fadeblack',0.35), ('B04',0):('slideleft',0.25),
             ('B05',0):('fade',0.4), ('B07',0):('slideleft',0.25), ('B08',7):('fadewhite',0.3)}
SFX = []
def sfx(n,t,g): SFX.append([n, round(max(0,t),3), g])
TS = {'slideleft':('whoosh_fast',-14), 'zoomin':('whoosh_zoom',-14), 'fadewhite':('glare',-16), 'fadeblack':('soft_swell',-17)}

def build():
    cuts = [0.0 if k == 0 else max(0, T(l,w) - 0.04) for k,(l,w,_,_) in enumerate(SHOTS)] + [TOTAL]
    segs = []; plan = []; zd = [(1.0,1.08),(1.08,1.0),(1.0,1.07),(1.07,1.0)]
    for k,(l,w,n,inp) in enumerate(SHOTS):
        L = cuts[k+1] - cuts[k]; src = M[n]; D = dur(src)
        tr = TRANS.get((l,w)); extra = tr[1] if tr else 0
        need = L + extra; avail = D - 0.05 - (inp if isinstance(inp,(int,float)) and n not in ('PRESENTER','PHOOK') else 0)
        if n in ('PRESENTER','PHOOK'):
            pm = (PMAP if n=='PRESENTER' else HMAP)[inp]; sp = pm['speed']; st = max(0, pm['src_start'] - 0.04*sp)
            en = min(D-0.05, st+L*sp); segs.append({'src':src,'start':round(st,3),'end':round(en,3),'speed':round((en-st)/L,4),'mute':True,'fit':'cover'})
            plan.append((round(cuts[k],2), round(L,2), l, ' '.join(t[0] for t in LW[l][w:])[:46], n)); continue
        seg = {'src':src, 'start':inp, 'mute':True, 'fit':'cover'}
        if n not in ('SCALE','PRESENTER','PHOOK'): seg.update(zoom=zd[k%4][0], zoom_to=zd[k%4][1])
        if V3 and H == 'H1' and k == 0: seg.update(zoom=1.0, zoom_to=1.22)
        if avail >= need: seg['end'] = round(inp+need, 3)
        else:
            seg['end'] = round(inp+avail, 3); seg['speed'] = round(avail/need, 4)
            assert seg['speed'] >= 0.7, (n, seg['speed'])
        if tr:
            seg['transition_in'] = {'type':tr[0], 'dur':tr[1]}
            if not V3: nm,g = TS[tr[0]]; sfx(nm, cuts[k]-tr[1]-0.1, g)
        segs.append(seg); plan.append((round(cuts[k],2), round(L,2), l, ' '.join(t[0] for t in LW[l][w:])[:46], n))
    return split_long(segs, plan, cuts)

MAXSHOT = 3.0
def split_long(segs, plan, cuts):
    """Split any shot longer than MAXSHOT at word starts; later parts are punch-ins of the same take (keeps lip sync)."""
    starts = [t[1]-0.04 for t in toks]
    S2, P2 = [], []
    for k,(seg,pl) in enumerate(zip(segs, plan)):
        a, b = cuts[k], cuts[k+1]; L = b - a
        if L <= MAXSHOT: S2.append(seg); P2.append(pl); continue
        n = int(L // MAXSHOT) + 1; pts = [a]
        for q in range(1, n):
            target = a + L*q/n; cand = [x for x in starts if pts[-1]+0.9 < x < b-0.9]
            pts.append(min(cand, key=lambda x: abs(x-target)) if cand else target)
        pts.append(b)
        sp = seg.get('speed', 1.0) if 'zoom' not in seg else (seg['end']-seg['start'])/L
        for q in range(len(pts)-1):
            p = dict(seg); p.pop('transition_in', None) if q else None
            p['start'] = round(seg['start'] + (pts[q]-a)*sp, 3); p['end'] = round(seg['start'] + (pts[q+1]-a)*sp, 3)
            zq = 1.0 if q % 2 == 0 else 1.16
            p['zoom'] = zq; p['zoom_to'] = zq + (0.02 if 'zoom' in seg else 0.0)
            if 'zoom' not in seg: p['zoom_to'] = zq
            S2.append(p); P2.append((round(pts[q],2), round(pts[q+1]-pts[q],2), pl[2], pl[3] if q == 0 else '  (punch-in)', pl[4]))
    return S2, P2

DISP = {('eight',):'8', ('nine','point','seven.'):'9.7.', ('thirty','thousand'):'30,000', ('ninety-day',):'90-day',
        ('Capture','Cards'):'CaptureCards'}
def captions(a):
    for l in ORDER:
        tk = LW[l]; disp = []; k = 0
        while k < len(tk):
            for key,val in sorted(DISP.items(), key=lambda x:-len(x[0])):
                if tuple(t[0] for t in tk[k:k+len(key)]) == key:
                    disp.append((val, tk[k][1], tk[k+len(key)-1][2])); k += len(key); break
            else: disp.append(tk[k]); k += 1
        ch3 = [disp[i:i+3] for i in range(0, len(disp), 3)]
        if len(ch3) > 1 and len(ch3[-1]) == 1: last = ch3.pop(); ch3[-1] = ch3[-1] + last
        nxt = ORDER.index(l) + 1
        lend = LW[ORDER[nxt]][0][1] if nxt < len(ORDER) else TOTAL - 0.2
        for j,c in enumerate(ch3):
            t0 = c[0][1] - 0.03; t1 = (ch3[j+1][0][1] - 0.03) if j+1 < len(ch3) else lend - 0.03
            a.box(t0, t1, 540, 1250, ' '.join(x[0] for x in c), 70, fade=(25,25))

import re
def captions128(a):
    for l in ORDER:
        tk = LW[l]; disp = []; k = 0
        while k < len(tk):
            for key,val in sorted(DISP.items(), key=lambda x:-len(x[0])):
                if tuple(t[0] for t in tk[k:k+len(key)]) == key:
                    disp.append((val, tk[k][1], tk[k+len(key)-1][2])); k += len(key); break
            else: disp.append(tk[k]); k += 1
        def clean(w):
            w = re.sub(r'[.,?!;:]+$', '', w)
            return w if w in ('I','CaptureCards') or w[:1].isdigit() else w.lower()
        chunks = []; cur = []
        for d in disp:
            txt = ' '.join(clean(x[0]) for x in cur + [d])
            if cur and (len(cur) >= 3 or len(txt) > 17): chunks.append(cur); cur = []
            cur.append(d)
            if re.search(r'[.?!]$', d[0]): chunks.append(cur); cur = []
        if cur: chunks.append(cur)
        nxt = ORDER.index(l) + 1
        lend = LW[ORDER[nxt]][0][1] if nxt < len(ORDER) else TOTAL - 0.2
        for j,c in enumerate(chunks):
            t0 = c[0][1] - 0.03; t1 = (chunks[j+1][0][1] - 0.03) if j+1 < len(chunks) else min(lend - 0.03, c[-1][2] + 0.6)
            a.ev.append(f"Dialogue: 2,{ts(t0)},{ts(t1)},C,,0,0,0,,{{\\an5\\pos(540,1300)}}" + ' '.join(clean(x[0]) for x in c))

def signs128(a):
    if V3 and H == 'H1':   # hookier H1 open: curiosity headline + weights popping in as they're said
        hend = LW['B01'][0][1] - 0.05
        a.box(0.0, hend, 540, 300, 'WHY DID THIS CARD', 64, fg='&HFFFFFF&', bg='&H2A2AE8&', padx=30, pady=12, r=22, layer=3, fade=(0,60))
        a.box(0.0, hend, 540, 392, 'GET HEAVIER?', 78, fg='&HFFFFFF&', bg='&H2A2AE8&', padx=34, pady=12, r=22, layer=3, fade=(0,60))
        t = T('H1',3); sfx('pop', t-0.03, -13)
        a.box(t, T('H1',14)-0.04, 540, 1060, '8 g', 130, fg='&H000000&', bg='&HFFFFFF&', padx=40, pady=14, r=30, layer=4)
        t = T('H1',16); sfx('pop', t-0.03, -12)
        a.box(t, hend, 540, 1060, '9.7 g', 140, fg='&HFFFFFF&', bg='&H2A2AE8&', padx=44, pady=16, r=30, layer=4)
    if V3:
        for wi,end in ((11,13),(13,17)):
            a.xstamp(T('B07',wi), T('B07',end)-0.04, 540, 820, size=240); sfx('stamp', T('B07',wi)-0.03, -12)
    t = T('B08',7)
    a.box(t, TOTAL, 540, 560, '90-DAY MONEY-BACK GUARANTEE', 56, fg='&H1E3A5A&', bg='&H5CC6F2&', padx=30, pady=18, r=40, layer=3)
    t = T('B08',14)
    a.box(t, TOTAL, 540, 1520, 'TAP THE LINK BELOW', 62, fg='&HFFFFFF&', bg='&H6E6B0C&', padx=40, pady=22, r=48, layer=3)
    for k in range(2):
        a.ev.append(f"Dialogue: 9,{ts(t)},{ts(TOTAL)},T,,0,0,0,,{{\\an5\\move(540,{1630+k*55},540,{1645+k*55},0,450)\\fs60\\bord4\\3c&H000000&\\1c&HFFFFFF&\\fad(150,0)}}▼")

def signs(a):
    line_end = lambda l: (LW[ORDER[ORDER.index(l)+1]][0][1] if ORDER.index(l)+1 < len(ORDER) else TOTAL) - 0.03
    RED, TEAL = '&H2A2AE8&', '&H3F5A1E&'
    t = T('B02',6); sfx('pop', t-0.03, -15)
    a.box(t, T('B02',12)-0.04, 540, 340, 'NEVER WASHED', 80, fg='&HFFFFFF&', bg=RED, padx=32, pady=16, r=26, layer=3)
    t = T('B02',30); sfx('pop', t-0.03, -15)
    a.box(t, line_end('B02'), 540, 340, '100,000s', 84, fg='&HFFFFFF&', bg=TEAL, padx=34, pady=16, r=26, layer=3)
    for i,(wi,lab) in enumerate([(8,'Plant-derived lure'),(20,'Sticky card traps them')]):
        t = T('B04',wi); sfx('tick', t-0.02, -15); fs = 58; w = tw(lab,fs)+52; y = 430 + i*112
        a.box(t, line_end('B04'), int(150+w/2), y, lab, fs, padx=26, pady=14, r=20, layer=3); a.check(t, line_end('B04'), 92, y, size=72)
    for wi,end in ((11,13),(13,17)):
        t = T('B07',wi); sfx('stamp', t-0.03, -12); a.xstamp(t, T('B07',end)-0.04, 540, 820, size=240)
    t = T('B07',17); sfx('pop', t-0.03, -15)
    a.box(t, line_end('B07'), 540, 340, '≈ 3 MONTHS PER CARD', 72, fg='&HFFFFFF&', bg=TEAL, padx=30, pady=16, r=26, layer=3)
    t = T('B08',0); sfx('pop', t+0.05, -15); sfx('sparkle', t+0.3, -18)
    a.box(t+0.05, T('B08',7)-0.04, 540, 300, '30,000+ HOMES', 80, fg='&HFFFFFF&', bg=TEAL, padx=34, pady=16, r=26, layer=3)
    a.box(t+0.3, T('B08',7)-0.04, 540, 410, '★★★★★', 64, fg='&H00C8FF&', bg='&HFFFFFF&', padx=24, pady=10, r=22, layer=3)
    t = T('B08',11); sfx('ding', t-0.02, -15)
    a.box(t, TOTAL, 540, 640, '90-DAY MONEY-BACK GUARANTEE', 58, fg='&H000000&', bg='&H00C8FF&', padx=30, pady=18, r=26, layer=3)
    for k in range(2):
        a.ev.append(f"Dialogue: 9,{ts(T('B08',14))},{ts(TOTAL)},T,,0,0,0,,{{\\an5\\move(540,{1330+k*55},540,{1345+k*55},0,450)\\fs60\\bord4\\3c&H000000&\\1c&H00C8FF&\\fad(150,0)}}▼")

if __name__ == '__main__':
    segs, plan = build()
    json.dump({'source':segs[0]['src'], 'segments':segs, 'reframe':0.5, 'grade':'natural', 'texts':[]}, open(f'work/{H}.edl.json','w'), indent=1)
    a = A(); captions128(a); signs128(a); a.write(f'work/{H}.ass')
    t=open(f'work/{H}.ass').read().replace('[Events]','').replace('Style: T,','Style: C,Inter SemiBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,-1,0,1,3.5,1.5,5,0,0,0,1\nStyle: T,',1)
    open(f'work/{H}.ass','w').write(t.replace('Format: Layer, Start','[Events]\nFormat: Layer, Start',1))
    json.dump(SFX, open(f'work/{H}_sfx.json','w')); json.dump({'total':TOTAL, 'plan':plan}, open(f'work/{H}_plan.json','w'), indent=1)
    for r in plan: print(f"{r[0]:6.2f} {r[1]:4.2f}s {r[2]:4} | {r[3]:46} | {r[4][:34]}")
    print('shots', len(plan), 'max %.2f' % max(r[1] for r in plan if r[4] != 'SCALE'), 'total %.1f' % TOTAL)
