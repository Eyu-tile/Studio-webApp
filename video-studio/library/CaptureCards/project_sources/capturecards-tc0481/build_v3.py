"""TC0481 builder: phrase-matched shots, TC0128 captions, transitions at section changes, X stamps (only SFX)."""
import json, subprocess, os, sys, re
sys.path.insert(0, '/tmp/claude-0/-home-user-video-studio-claude-plugin/c77d22ec-6b89-5b09-a2c3-205b160242d8/scratchpad')
from ass451 import A, tw, ts
os.chdir('/home/user/video-studio-claude-plugin/video-studio/projects/capturecards-tc0481')
H = sys.argv[1]
S = json.load(open('work/script.json')); M = json.load(open('raw/map_pool.json')); M.update(json.load(open('raw/map_gen.json')))
SH = json.load(open('work/shots.json'))
def dur(p): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',p],capture_output=True,text=True).stdout.strip())
BODY = ['B01','B02','B03','B04','B05','B06','B07','B08','B09','B10','B11','B12']
ORDER = [H] + (['B02h2'] + BODY[2:] if H == 'H2' else BODY)
J = json.load(open(f'work/vo/{H}_vo_align.json')); al = J['al']
ch, cs, ce = al['characters'], al['character_start_times_seconds'], al['character_end_times_seconds']
toks = []; i = 0
while i < len(ch):
    if ch[i] == ' ': i += 1; continue
    j = i
    while j < len(ch) and ch[j] != ' ': j += 1
    toks.append((''.join(ch[i:j]), cs[i], ce[j-1])); i = j
per = [len(S[k].split()) for k in ORDER]; assert sum(per) == len(toks), (sum(per), len(toks))
LW = {}; p = 0
for k, n in zip(ORDER, per): LW[k] = toks[p:p+n]; p += n
TOTAL = dur(f'work/vo/{H}_vo.mp3') + 0.8
nz = lambda w: re.sub(r"[^a-z0-9']", '', w.lower())
def W(line, phrase):
    pw = [nz(x) for x in phrase.split()]; ws = [nz(t[0]) for t in LW[line]]
    for k in range(len(ws)):
        if ws[k:k+len(pw)] == pw: return k
    raise KeyError((line, phrase))
def T(line, phrase): return LW[line][W(line, phrase)][1]

def LS(l):
    v = SH[l]
    return v.get(H, v['default']) if isinstance(v, dict) else v
SHOTS = [(l, ph, clip, inp) for l in ORDER for ph, clip, inp in LS(l)]
_seen = {}
for l, ph, clip, _ in SHOTS: _seen.setdefault(clip, []).append(f'{l}:{ph}')
_dups = {c: v for c, v in _seen.items() if len(v) > 1}
assert not _dups, 'clip used twice in ' + H + ': ' + json.dumps(_dups, indent=1)
TRANS = {('B01',"Here's what's"):('zoomin',0.3), ('B04','Because that\'s where'):('fadeblack',0.35), ('B06','So the itch'):('slideleft',0.25),
         ('B08','You don\'t need'):('fade',0.4), ('B09','That\'s exactly'):('slideleft',0.25), ('B11','Just slide one'):('slideleft',0.25),
         ('B12','Try it with'):('fadewhite',0.3)}
SFX = []
def sfx(n, t, g): SFX.append([n, round(max(0, t), 3), g])

def build():
    cuts = [0.0 if k == 0 else max(0, T(l, ph) - 0.04) for k, (l, ph, _, _) in enumerate(SHOTS)] + [TOTAL]
    segs = []; plan = []; zd = [(1.0,1.08),(1.08,1.0),(1.0,1.07),(1.07,1.0)]
    for k, (l, ph, n, inp) in enumerate(SHOTS):
        L = cuts[k+1] - cuts[k]; src = M[n]; D = dur(src)
        tr = TRANS.get((l, ph)); extra = tr[1] if tr else 0
        need = L + extra; inp = min(inp, max(0, D - 0.05 - need*0.75)); avail = D - 0.05 - inp
        seg = {'src':src, 'start':round(inp,3), 'mute':True, 'fit':'cover', 'zoom':zd[k%4][0], 'zoom_to':zd[k%4][1]}
        if avail >= need: seg['end'] = round(inp + need, 3)
        else:
            seg['end'] = round(inp + avail, 3); seg['speed'] = round(avail / need, 4)
            assert seg['speed'] >= 0.7, (n, seg['speed'], L)
        if tr: seg['transition_in'] = {'type':tr[0], 'dur':tr[1]}
        segs.append(seg); plan.append((round(cuts[k],2), round(L,2), l, ph, n))
    return split_long(segs, plan, cuts)

def split_long(segs, plan, cuts, MAX=3.0):
    starts = [t[1]-0.04 for t in toks]; S2, P2 = [], []
    for k, (seg, pl) in enumerate(zip(segs, plan)):
        a, b = cuts[k], cuts[k+1]; L = b - a
        if L <= MAX: S2.append(seg); P2.append(pl); continue
        n = int(L // MAX) + 1; pts = [a]
        for q in range(1, n):
            target = a + L*q/n; cand = [x for x in starts if pts[-1]+0.9 < x < b-0.9]
            pts.append(min(cand, key=lambda x: abs(x-target)) if cand else target)
        pts.append(b); sp = (seg['end'] - seg['start']) / L
        for q in range(len(pts)-1):
            p = dict(seg)
            if q: p.pop('transition_in', None)
            p['start'] = round(seg['start'] + (pts[q]-a)*sp, 3); p['end'] = round(seg['start'] + (pts[q+1]-a)*sp, 3)
            z = 1.0 if q % 2 == 0 else 1.16; p['zoom'] = z; p['zoom_to'] = z + 0.02
            S2.append(p); P2.append((round(pts[q],2), round(pts[q+1]-pts[q],2), pl[2], pl[3] if q == 0 else '(punch-in)', pl[4]))
    return S2, P2

DISP = {('thirty','thousand'):'30,000', ('ninety-day',):'90-day', ('Capture','Cards'):'CaptureCards'}
def captions(a):
    for l in ORDER:
        tk = LW[l]; disp = []; k = 0
        while k < len(tk):
            for key, val in sorted(DISP.items(), key=lambda x: -len(x[0])):
                if tuple(re.sub(r'[.,?!]','',t[0]) for t in tk[k:k+len(key)]) == key:
                    disp.append((val + (tk[k+len(key)-1][0][-1] if tk[k+len(key)-1][0][-1] in '.,?!' else ''), tk[k][1], tk[k+len(key)-1][2])); k += len(key); break
            else: disp.append(tk[k]); k += 1
        def clean(w):
            w = re.sub(r'[.,?!;:]+$', '', w)
            return w if w in ('I', 'CaptureCards') or w[:1].isdigit() else w.lower()
        chunks = []; cur = []
        for d in disp:
            txt = ' '.join(clean(x[0]) for x in cur + [d])
            if cur and (len(cur) >= 3 or len(txt) > 17): chunks.append(cur); cur = []
            cur.append(d)
            if re.search(r'[.?!]$', d[0]): chunks.append(cur); cur = []
        if cur: chunks.append(cur)
        nxt = ORDER.index(l) + 1; lend = LW[ORDER[nxt]][0][1] if nxt < len(ORDER) else TOTAL - 0.2
        for j, c in enumerate(chunks):
            t0 = c[0][1] - 0.03; t1 = (chunks[j+1][0][1] - 0.03) if j+1 < len(chunks) else min(lend - 0.03, c[-1][2] + 0.6)
            a.ev.append(f"Dialogue: 2,{ts(t0)},{ts(t1)},C,,0,0,0,,{{\\an5\\pos(540,1300)}}" + ' '.join(clean(x[0]) for x in c))

def signs(a):
    for l, ph, nxt in (('B07','Hot washes','Covers'), ('B07','Covers','Anti-itch cream'), ('B07','Anti-itch cream','but the mites'),
                       ('B11','No spray','nothing to plug in'), ('B11','nothing to plug in','One card keeps')):
        t = T(l, ph); a.xstamp(t, T(l, nxt) - 0.04, 540, 820, size=240); sfx('stamp', t - 0.03, -12)
    t = T('B12','Try it with')
    a.box(t, TOTAL, 540, 560, '90-DAY MONEY-BACK GUARANTEE', 56, fg='&H1E3A5A&', bg='&H5CC6F2&', padx=30, pady=18, r=40, layer=3)
    t = T('B12','Tap the link')
    a.box(t, TOTAL, 540, 1520, 'TAP THE LINK BELOW', 62, fg='&HFFFFFF&', bg='&H6E6B0C&', padx=40, pady=22, r=48, layer=3)
    for k in range(2):
        a.ev.append(f"Dialogue: 9,{ts(t)},{ts(TOTAL)},T,,0,0,0,,{{\\an5\\move(540,{1630+k*55},540,{1645+k*55},0,450)\\fs60\\bord4\\3c&H000000&\\1c&HFFFFFF&\\fad(150,0)}}▼")

if __name__ == '__main__':
    segs, plan = build()
    json.dump({'source':segs[0]['src'], 'segments':segs, 'reframe':0.5, 'grade':'natural', 'texts':[]}, open(f'work/{H}.edl.json','w'), indent=1)
    a = A(); captions(a); signs(a); a.write(f'work/{H}.ass')
    t = open(f'work/{H}.ass').read().replace('[Events]','').replace('Style: T,','Style: C,Inter SemiBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,-1,0,1,3.5,1.5,5,0,0,0,1\nStyle: T,',1)
    open(f'work/{H}.ass','w').write(t.replace('Format: Layer, Start','[Events]\nFormat: Layer, Start',1))
    json.dump(SFX, open(f'work/{H}_sfx.json','w')); json.dump({'total':TOTAL, 'plan':plan}, open(f'work/{H}_plan.json','w'), indent=1)
    for r in plan: print(f"{r[0]:6.2f} {r[1]:4.2f}s {r[2]:5} | {r[3][:26]:26} | {r[4][:40]}")
    print('shots', len(plan), 'max %.2f' % max(r[1] for r in plan), 'total %.1f' % TOTAL)
