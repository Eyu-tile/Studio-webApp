#!/bin/bash
cd /home/user/video-studio-claude-plugin/video-studio/projects/capturecards-tc0488; h=$1
VS=/home/user/video-studio-claude-plugin/plugins/video-studio/bin/vs; export VS_WORKSPACE=/home/user/video-studio-claude-plugin/video-studio
$VS render work/${h}.edl.json -o out/_${h}.mp4 --preset reels --jobs 1 </dev/null > work/${h}_render.log 2>&1 || { tail -5 work/${h}_render.log; exit 1; }
python3 - "$h" <<'PY'
import json,subprocess,sys,re
h=sys.argv[1]
T=json.load(open(f'work/{h}_plan.json'))['total']; SFX=json.load(open(f'work/{h}_sfx.json'))
M='assets/music/incompetech_covert-affair_covert-affair-kevin-macleod.mp3'
import os
inp=['-i',f'work/vo/{h}_vo.mp3','-ss','2','-i',M]; fc=[]
for i,(n,t,g) in enumerate(SFX):
    inp+=['-i',f'work/sfx/{n}.mp3']; ms=int(t*1000)
    fc.append(f"[{i+2}:a]aresample=48000,aformat=channel_layouts=stereo,volume={g+4}dB,adelay={ms}|{ms}[s{i}]")
fc.append("[0:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur=2,asplit=2[v][vk]")
fc.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=-15dB,afade=t=in:d=0.4,afade=t=out:st={T-1.8:.2f}:d=1.8[m]")
fc.append("[m][vk]sidechaincompress=threshold=0.05:ratio=3:attack=15:release=250[md]")
if SFX:
    fc.append(''.join(f'[s{i}]' for i in range(len(SFX)))+f"amix=inputs={len(SFX)}:normalize=0[sx]")
    fc.append(f"[v][md][sx]amix=inputs=3:duration=first:normalize=0,atrim=0:{T}[a]")
else:
    fc.append(f"[v][md]amix=inputs=2:duration=first:normalize=0,atrim=0:{T}[a]")
subprocess.run(['ffmpeg','-nostdin','-y']+inp+['-filter_complex',';'.join(fc),'-map','[a]','-ar','48000','-ac','2',f'work/{h}_mix.wav'],check=True,capture_output=True)
r=subprocess.run(['ffmpeg','-nostdin','-i',f'work/{h}_mix.wav','-af','alimiter=limit=0.7:level=disabled,loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
j=json.loads(re.findall(r'\{[^{}]*"input_i"[^{}]*\}',r.stderr)[-1])
AF=f"alimiter=limit=0.7:level=disabled,loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true"
subprocess.run(['ffmpeg','-nostdin','-y','-i',f'out/_{h}.mp4','-i',f'work/{h}_mix.wav','-filter_complex',f"[0:v]ass=work/{h}.ass:fontsdir=/usr/share/fonts/opentype/inter[v];[1:a]{AF}[a]",'-map','[v]','-map','[a]','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-shortest','-movflags','+faststart',f'out/capturecards_tc0488_{h}_9x16.mp4'],check=True,capture_output=True)
PY
f=out/capturecards_tc0488_${h}_9x16.mp4
echo "$h $(ffprobe -v error -show_entries format=duration -of csv=p=0 $f) $(ffmpeg -nostdin -i $f -af ebur128=peak=true -f null - 2>&1 | grep -E '^\s+(I:|Peak:)' | tail -2 | tr -s ' ' | tr '\n' ' ')"
