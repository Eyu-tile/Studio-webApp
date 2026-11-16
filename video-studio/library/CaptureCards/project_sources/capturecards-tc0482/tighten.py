import json,subprocess,numpy as np,soundfile as sf,sys
def load(name):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',f'work/vo/{name}.mp3','-ac','1','-ar','44100',f'work/vo/{name}.wav'],check=True)
    a,sr=sf.read(f'work/vo/{name}.wav',dtype='float32'); J=json.load(open(f'work/vo/{name}_align.json')); return a,sr,J
def words(J):
    al=J['al']; ch,cs,ce=al['characters'],al['character_start_times_seconds'],al['character_end_times_seconds']; W=[];i=0
    while i<len(ch):
        if ch[i]==' ': i+=1; continue
        j=i
        while j<len(ch) and ch[j]!=' ': j+=1
        W.append([i,j,cs[i],ce[j-1]]); i=j
    return W
def tighten(a,sr,J,maxgap=0.12,keep=0.045,lead=0.05,tail=0.25):
    W=words(J); al=J['al']; cs=np.array(al['character_start_times_seconds']); ce=np.array(al['character_end_times_seconds'])
    # segments to keep: from first word start-lead to last word end+tail, removing gap middle where gap>maxgap
    cuts=[]  # (t0,t1) removed
    for w0,w1 in zip(W,W[1:]):
        g=w1[2]-w0[3]; last=J['text'][w0[1]-1]
        mg=0.30 if last in '.?!' else (0.16 if last in ',;:' else maxgap)
        if g>mg: k=mg/2; cuts.append((w0[3]+k,w1[2]-k))
    start=max(0,W[0][2]-lead); end=min(len(a)/sr,W[-1][3]+tail)
    keepsegs=[];t=start
    for c0,c1 in cuts: keepsegs.append((t,c0)); t=c1
    keepsegs.append((t,end))
    out=[];fade=int(0.004*sr)
    for t0,t1 in keepsegs:
        s=a[int(t0*sr):int(t1*sr)].copy()
        if len(s)>2*fade: s[:fade]*=np.linspace(0,1,fade); s[-fade:]*=np.linspace(1,0,fade)
        out.append(s)
    def remap(t):
        off=start;
        for c0,c1 in cuts:
            if t>=c1: off+=c1-c0
            elif t>c0: return c0-off
        return t-off
    al2=dict(al); al2['character_start_times_seconds']=[round(remap(x),4) for x in cs]; al2['character_end_times_seconds']=[round(remap(x),4) for x in ce]
    return np.concatenate(out),{'text':J['text'],'al':al2}
