import json,numpy as np,soundfile as sf,sys
def ptrim(name, maxgap=0.22, thr=-38, lead=0.04, tail=0.12):
    a,sr=sf.read(f'work/vo/{name}.wav',dtype='float32'); J=json.load(open(f'work/vo/{name}_align.json')); al=J['al']
    hop=int(0.01*sr); e=np.array([20*np.log10(np.sqrt(np.mean(a[i:i+hop]**2))+1e-9) for i in range(0,len(a)-hop,hop)])
    sil=e<thr; segs=[]; i=0
    while i<len(sil):
        if sil[i]:
            j=i
            while j<len(sil) and sil[j]: j+=1
            segs.append((i*0.01,j*0.01)); i=j
        else: i+=1
    first=min(np.argmax(~sil)*0.01, al['character_start_times_seconds'][0]); last=len(a)/sr
    cuts=[]
    for s0,s1 in segs:
        if s1-s0>maxgap and s0>first+0.05 and s1<last-0.05:
            k=maxgap/2; cuts.append((s0+k,s1-k))
    start=max(0,first-lead); end=len(a)/sr
    for s0,s1 in reversed(segs):
        if s1>=len(a)/sr-0.02: end=min(end,s0+tail); break
    keep=[];t=start
    for c0,c1 in cuts: keep.append((t,c0)); t=c1
    keep.append((t,end)); f=int(0.004*sr); out=[]
    for t0,t1 in keep:
        s=a[int(t0*sr):int(t1*sr)].copy()
        if len(s)>2*f: s[:f]*=np.linspace(0,1,f); s[-f:]*=np.linspace(1,0,f)
        out.append(s)
    def rm(t):
        off=start
        for c0,c1 in cuts:
            if t>=c1: off+=c1-c0
            elif t>c0: return c0-off
        return t-off
    al2=dict(al); al2['character_start_times_seconds']=[round(rm(x),4) for x in al['character_start_times_seconds']]; al2['character_end_times_seconds']=[round(rm(x),4) for x in al['character_end_times_seconds']]
    x=np.concatenate(out); return x,sr,{'text':J['text'],'al':al2}
