"""Build VO v2: narrator (Jessica) + presenter's own voice, never overlapping.
Presenter lines come from the Seedance clip audio (her own voice, perfect lip sync).
Writes work/vo/{H}_v2.wav/.mp3 and work/vo/{H}_v2_align.json (ElevenLabs-style char alignment),
plus work/vo/presenter2_map.json {key: clip_start} used by build.py."""
import json, re, subprocess, sys, numpy as np, soundfile as sf
import os; os.chdir('/home/user/video-studio-claude-plugin/video-studio/projects/capturecards-tc0482')
S = json.load(open('work/script.json'))
CLIP = 'raw/higgsfield/presenter2_talk.mp4'
SR = 44100
LINES = {'H1': S['H1'], 'H2': S['H2'], 'H3': S['H3'], 'P_wash': "You wash your sheets every week.",
         'P_clean': "That's why your bed looks clean.", 'P_card': "And everything on that card used to be in your bed.",
         'P_homes': "Over thirty thousand homes already use them."}
ORDER = ['H1','H2','H3','P_wash','P_clean','P_card','P_homes']
norm = lambda x: re.sub(r'[^a-z0-9]', '', x.lower())

def locate():
    from faster_whisper import WhisperModel
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',CLIP,'-ac','1','-ar',str(SR),'work/vo/p2clip.wav'], check=True)
    a16 = 'work/vo/p2clip16.wav'; subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',CLIP,'-ac','1','-ar','16000',a16], check=True)
    a,_ = sf.read(a16, dtype='float32'); m = WhisperModel('small', device='cpu', compute_type='int8')
    W = []
    for s in m.transcribe(a, language='en', word_timestamps=True)[0]: W += [(w.word.strip(), w.start, w.end) for w in s.words]
    print(' '.join(f'{w}@{s:.2f}' for w,s,e in W))
    out = {}; starts = []; i = 0
    for k in ORDER:
        f = re.sub(r'[^A-Za-z]','',LINES[k].split()[0])
        while re.sub(r'[^A-Za-z]','',W[i][0]) != f: i += 1
        starts.append(i); i += 1
    for n,k in enumerate(ORDER):
        i = starts[n]; j = starts[n+1] if n+1 < len(starts) else len(W)
        out[k] = {'s': W[i][1], 'e': W[j-1][2], 'words': W[i:j]}
        print(k, round(out[k]['s'],2), round(out[k]['e'],2), ' '.join(x[0] for x in out[k]['words']))
    # refine starts/ends with energy (whisper boundaries can sit in silence)
    a,_ = sf.read('work/vo/p2clip.wav', dtype='float32')
    db = lambda t: 20*np.log10(np.sqrt(np.mean(a[int(t*SR):int((t+0.03)*SR)]**2))+1e-9)
    for k,v in out.items():
        t = v['s']
        while t < v['s']+1.2 and db(t) < -35: t += 0.01
        # skip a silence gap (>0.3 s) inside the first 0.9 s (whisper put the start too early)
        u = t
        while u < v['s']+0.9:
            if db(u) < -35:
                g = u
                while g < u+1.0 and db(g) < -35: g += 0.01
                if g-u > 0.3: t = g; break
                u = g
            u += 0.01
        if t > v['s']+0.05:
            d = t-0.03-v['s']; v['s'] += d; v['words'] = [(w, max(s0+d if n==0 else s0, v['s']), e) for n,(w,s0,e) in enumerate(v['words'])]
        t = v['e']
        while t > v['s'] and db(t-0.03) < -35: t -= 0.01
        v['e'] = min(v['e'], t+0.02)
        print('refined', k, round(v['s'],2), round(v['e'],2))
    json.dump({k:{'s':v['s'],'e':v['e'],'words':v['words']} for k,v in out.items()}, open('work/vo/presenter2_words.json','w'), indent=1)
    return out

def chars_for(text, t0, t1, wtimes=None):
    """char-level timing for text spanning t0..t1; uses per-word times when counts match."""
    words = text.split(); ch=[]; cs=[]; ce=[]
    if wtimes and len(wtimes) == len(words): spans = [(s,e) for s,e in wtimes]
    else:
        L = sum(len(w) for w in words); t = t0; spans = []
        for w in words: d = (t1-t0)*len(w)/L; spans.append((t, t+d)); t += d
    for wi,(w,(s,e)) in enumerate(zip(words, spans)):
        if wi: ch.append(' '); cs.append(s-0.01); ce.append(s)
        for c in w: ch.append(c); cs.append(s); ce.append(e)
    return ch, cs, ce

def build(H, P):
    clip,_ = sf.read('work/vo/p2clip.wav', dtype='float32')
    J = json.load(open('work/vo/'+os.environ.get('NARR','H3_t')+'_align.json')); al = J['al']; txt = ''.join(al['characters'])
    jess,_ = sf.read('work/vo/'+os.environ.get('NARR','H3_t')+'.wav', dtype='float32')
    cs0, ce0 = al['character_start_times_seconds'], al['character_end_times_seconds']
    b01 = txt.index(S['B01'])
    pieces = []; CH=[]; CS=[]; CE=[]; t = 0.0
    def add_pres(k, pad_in=0.12, pad_out=0.14):
        nonlocal t
        p = P[k]; s0 = max(0, p['s']-pad_in); s1 = p['e']+pad_out
        a = clip[int(s0*SR):int(s1*SR)]; pieces.append(a)
        wt = [(w[1]-s0+t, w[2]-s0+t) for w in p['words']]
        c,s,e = chars_for(LINES[k], p['s']-s0+t, p['e']-s0+t, wt)
        if CH: CH.append(' '); CS.append(c and s[0]-0.01); CE.append(s[0])
        CH.extend(c); CS.extend(s); CE.extend(e); t += len(a)/SR
    def add_jess(i0, i1):  # narrator chars i0..i1 (exclusive), cut at word boundaries
        nonlocal t
        a0 = max(0, cs0[i0]-0.045); a1 = ce0[i1-1]+0.06
        a = jess[int(a0*SR):int(a1*SR)]; pieces.append(a)
        if CH: CH.append(' '); CS.append(cs0[i0]-a0+t-0.01); CE.append(cs0[i0]-a0+t)
        for i in range(i0, i1): CH.append(al['characters'][i]); CS.append(cs0[i]-a0+t); CE.append(ce0[i]-a0+t)
        t += len(a)/SR
    add_pres(H, pad_in=0.05, pad_out=0.12)
    # walk body, swapping presenter sentences
    marks = sorted((txt.index(LINES[k], b01), k) for k in ('P_wash','P_clean','P_card','P_homes'))
    i = b01
    for pos,k in marks:
        if pos > i: add_jess(i, pos-1)          # up to the space before the sentence
        add_pres(k); i = pos + len(LINES[k]) + 1   # skip sentence + following space
    add_jess(i, len(txt))
    x = np.concatenate(pieces); sf.write(f'work/vo/{H}_v2.wav', x, SR)
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',f'work/vo/{H}_v2.wav','-b:a','192k',f'work/vo/{H}_v2.mp3'], check=True)
    json.dump({'text':''.join(CH), 'al':{'characters':CH,'character_start_times_seconds':CS,'character_end_times_seconds':CE}}, open(f'work/vo/{H}_v2_align.json','w'))
    print(H, round(len(x)/SR,2), 's')

if __name__ == '__main__':
    P = locate()
    json.dump({k:{'src_start':round(v['s'],3),'speed':1.0} for k,v in P.items()}, open('work/vo/presenter2_map.json','w'), indent=1)
    for H in ('H1','H2','H3'): build(H, P)
