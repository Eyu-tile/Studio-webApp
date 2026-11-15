import json,base64,subprocess,sys,time,urllib.request,numpy as np,soundfile as sf
S=json.load(open('work/script.json')); O=S['order']
parts=[O[:7],O[7:18],O[18:]]
SR=44100; audio=[]; CH=[];CS=[];CE=[]; t=0.0
for pi,keys in enumerate(parts):
    text=' '.join(S[k] for k in keys)
    body=json.dumps({"text":text,"model_id":"eleven_v3","voice_settings":{"stability":0.5,"similarity_boost":0.8}}).encode()
    for attempt in range(4):
        try:
            req=urllib.request.Request("https://api.elevenlabs.io/v1/text-to-speech/cgSgspJ2msm6clMCkdW9/with-timestamps?output_format=mp3_44100_128",data=body,headers={"xi-api-key":"proxy-injected","Content-Type":"application/json"})
            r=json.load(urllib.request.urlopen(req,timeout=300)); break
        except Exception as e: print('retry',pi,e); time.sleep(5)
    open(f'work/vo/p{pi}.mp3','wb').write(base64.b64decode(r['audio_base64']))
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',f'work/vo/p{pi}.mp3','-ac','1','-ar',str(SR),f'work/vo/p{pi}.wav'],check=True)
    a,_=sf.read(f'work/vo/p{pi}.wav',dtype='float32'); al=r['alignment']
    if CH: CH.append(' '); CS.append(t-0.01); CE.append(t)
    CH+=al['characters']; CS+=[x+t for x in al['character_start_times_seconds']]; CE+=[x+t for x in al['character_end_times_seconds']]
    gap=np.zeros(int(0.35*SR),np.float32); audio+=[a,gap]; t+=len(a)/SR+0.35
    print(pi, round(len(a)/SR,2),'s')
x=np.concatenate(audio); sf.write('work/vo/H_raw.wav',x,SR)
json.dump({'text':''.join(CH),'al':{'characters':CH,'character_start_times_seconds':CS,'character_end_times_seconds':CE}},open('work/vo/H_raw_align.json','w'))
