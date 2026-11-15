import json, re, subprocess, numpy as np, soundfile as sf, os
os.chdir('/home/user/video-studio-claude-plugin/video-studio/projects/capturecards-tc0482')
from faster_whisper import WhisperModel
SR = 44100
L = {'P_wash':"You wash your sheets every week.", 'P_clean':"That's why your bed looks clean.",
     'P_card':"And everything on that card used to be in your bed.", 'P_homes':"Over thirty thousand homes already use them."}
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i','raw/higgsfield/presenter3_talk.mp4','-ac','1','-ar',str(SR),'work/vo/p3_44.wav'], check=True)
clip,_ = sf.read('work/vo/p3_44.wav', dtype='float32'); a16,_ = sf.read('work/vo/p3.wav', dtype='float32')
W = []
for s in WhisperModel('small', device='cpu', compute_type='int8').transcribe(a16, language='en', word_timestamps=True)[0]:
    W += [(w.word.strip(), w.start, w.end) for w in s.words]
db = lambda t: 20*np.log10(np.sqrt(np.mean(clip[int(t*SR):int((t+0.02)*SR)]**2))+1e-9)
firsts = ['You',"That's",'And','Over']; idx=[]; i=0
for f in firsts:
    while re.sub(r"[^A-Za-z']",'',W[i][0]) != f: i += 1
    idx.append(i); i += 1
P = {}
for n,k in enumerate(L):
    ws = W[idx[n]:(idx[n+1] if n < 3 else len(W))]
    s = ws[0][1]; e = ws[-1][2]
    while s > 0 and db(s-0.02) > -40: s -= 0.01          # back up to true onset
    while db(s) < -40 and s < ws[0][2]: s += 0.01
    while e > s and db(e-0.02) < -40: e -= 0.01
    P[k] = {'s':round(s,3), 'e':round(e+0.03,3), 'words':ws}; print(k, P[k]['s'], P[k]['e'], ' '.join(w[0] for w in ws))
json.dump({k:{'src_start':v['s'],'speed':1.0} for k,v in P.items()}, open('work/vo/presenter3_map.json','w'), indent=1)

def chars_for(text, t0, t1, ws):
    words = text.split(); ch=[];cs=[];ce=[]
    if len(ws) == len(words): spans = [(max(t0,w[1]-ws[0][1]+t0), w[2]-ws[0][1]+t0) for w in ws]
    else:
        Ltot = sum(len(w) for w in words); t=t0; spans=[]
        for w in words: d=(t1-t0)*len(w)/Ltot; spans.append((t,t+d)); t+=d
    for wi,(w,(s,e)) in enumerate(zip(words,spans)):
        if wi: ch.append(' '); cs.append(s-0.01); ce.append(s)
        for c in w: ch.append(c); cs.append(s); ce.append(e)
    return ch,cs,ce

B = json.load(open('work/vo/v3/body_t_align.json')); bal = B['al']; btxt=''.join(bal['characters'])
body,_ = sf.read('work/vo/v3/body_t.wav', dtype='float32'); bcs, bce = bal['character_start_times_seconds'], bal['character_end_times_seconds']
for H in ('H1','H2','H3'):
    Hj = json.load(open(f'work/vo/v3/{H}_t_align.json')); hk,_ = sf.read(f'work/vo/v3/{H}_t.wav', dtype='float32')
    pieces=[hk, np.zeros(int(0.25*SR))]; t=len(hk)/SR+0.25
    CH=list(Hj['al']['characters']); CS=list(Hj['al']['character_start_times_seconds']); CE=list(Hj['al']['character_end_times_seconds'])
    def add_body(i0, i1):
        global t
        a0 = max(0, bcs[i0]-0.04); a1 = bce[i1-1]+0.08; seg = body[int(a0*SR):int(a1*SR)]; pieces.append(seg)
        CH.append(' '); CS.append(bcs[i0]-a0+t-0.01); CE.append(bcs[i0]-a0+t)
        for i in range(i0,i1): CH.append(bal['characters'][i]); CS.append(bcs[i]-a0+t); CE.append(bce[i]-a0+t)
        t += len(seg)/SR
    def add_pres(k):
        global t
        p = P[k]; s0 = p['s']-0.03; seg = clip[int(s0*SR):int((p['e']+0.06)*SR)]; pieces.append(seg)
        c,s,e = chars_for(L[k], p['s']-s0+t, p['e']-s0+t, p['words'])
        CH.append(' '); CS.append(s[0]-0.01); CE.append(s[0]); CH.extend(c); CS.extend(s); CE.extend(e); t += len(seg)/SR
    marks = sorted((btxt.index(L[k]), k) for k in L); i = 0
    for pos,k in marks:
        if pos > i: add_body(i, pos-1)
        add_pres(k); i = pos + len(L[k]) + 1
    add_body(i, len(btxt))
    x = np.concatenate(pieces); sf.write(f'work/vo/{H}_v3.wav', x, SR)
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',f'work/vo/{H}_v3.wav','-b:a','192k',f'work/vo/{H}_v3.mp3'], check=True)
    json.dump({'text':''.join(CH),'al':{'characters':CH,'character_start_times_seconds':CS,'character_end_times_seconds':CE}}, open(f'work/vo/{H}_v3_align.json','w'))
    print(H, round(len(x)/SR,2))
