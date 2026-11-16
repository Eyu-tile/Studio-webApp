from PIL import ImageFont
import math
FONT='/usr/share/fonts/opentype/inter/Inter-Bold.otf'; K=0.822
def tw(text,fs): f=ImageFont.truetype(FONT,100); b=f.getbbox(text); return (b[2]-b[0])*fs/100*K
def ts(x): x=max(0,x); return f"{int(x//3600)}:{int(x%3600//60):02d}:{x%60:05.2f}"
def rrect(w,h,r):
    c=r*0.5523
    return (f"m {r:.0f} 0 l {w-r:.0f} 0 b {w-r+c:.0f} 0 {w:.0f} {r-c:.0f} {w:.0f} {r:.0f} l {w:.0f} {h-r:.0f} "
            f"b {w:.0f} {h-r+c:.0f} {w-r+c:.0f} {h:.0f} {w-r:.0f} {h:.0f} l {r:.0f} {h:.0f} b {r-c:.0f} {h:.0f} 0 {h-r+c:.0f} 0 {h-r:.0f} "
            f"l 0 {r:.0f} b 0 {r-c:.0f} {r-c:.0f} 0 {r:.0f} 0")
def xmark(s,t):
    # X shape centred in an s×s box, bar thickness t
    a=t/math.sqrt(2); pts=[(a,0),(s/2,s/2-a),(s-a,0),(s,a),(s/2+a,s/2),(s,s-a),(s-a,s),(s/2,s/2+a),(a,s),(0,s-a),(s/2-a,s/2),(0,a)]
    return 'm '+' l '.join(f'{x:.0f} {y:.0f}' for x,y in pts)
def circle(d):
    r=d/2;c=r*0.5523
    return f"m {r:.0f} 0 b {r+c:.0f} 0 {d:.0f} {r-c:.0f} {d:.0f} {r:.0f} b {d:.0f} {r+c:.0f} {r+c:.0f} {d:.0f} {r:.0f} {d:.0f} b {r-c:.0f} {d:.0f} 0 {r+c:.0f} 0 {r:.0f} b 0 {r-c:.0f} {r-c:.0f} 0 {r:.0f} 0"
POP="\\fscx80\\fscy80\\t(0,110,\\fscx106\\fscy106)\\t(110,180,\\fscx100\\fscy100)"
class A:
    def __init__(s): s.ev=[]
    def box(s,a,b,x,y,text,fs,fg='&H000000&',bg='&HFFFFFF&',padx=26,pady=16,r=22,layer=1,fade=(40,40),pop=True,alpha='&H00&'):
        w=tw(text,fs)+2*padx; h=fs*0.98+2*pady; p=POP if pop else ''
        s.ev.append(f"Dialogue: {layer},{ts(a)},{ts(b)},T,,0,0,0,,{{\\an5\\pos({x},{y})\\p1\\bord0\\shad0\\1c{bg}\\1a{alpha}\\fad{fade}{p}}}{rrect(w,h,r)}")
        s.ev.append(f"Dialogue: {layer+1},{ts(a)},{ts(b)},T,,0,0,0,,{{\\an5\\pos({x},{y+1})\\fs{fs}\\bord0\\shad0\\1c{fg}\\fad{fade}{p}}}{text}")
        return w,h
    def shape(s,a,b,x,y,path,col,layer=5,extra='',fade=(30,80)):
        s.ev.append(f"Dialogue: {layer},{ts(a)},{ts(b)},T,,0,0,0,,{{\\an5\\pos({x},{y})\\p1\\bord0\\shad0\\1c{col}\\fad{fade}{extra}}}{path}")
    def xstamp(s,a,b,x,y,size=300):
        s.shape(a,b,x,y,circle(size*1.25),'&HFFFFFF&',layer=5,extra=POP+'\\1a&H40&')
        s.shape(a,b,x,y,xmark(size*0.7,size*0.17),'&H2A2AE8&',layer=6,extra=POP)
    def check(s,a,b,x,y,size=70):
        s.shape(a,b,x,y,circle(size),'&H4AB82E&',layer=7,extra=POP)
        s.ev.append(f"Dialogue: 8,{ts(a)},{ts(b)},T,,0,0,0,,{{\\an5\\pos({x},{y+2})\\fs{int(size*0.7)}\\bord0\\shad0\\1c&HFFFFFF&\\fad(30,80){POP}}}✓")
    def write(s,path):
        hdr=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
             "Style: T,Inter,74,&H00000000,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        open(path,'w').write(hdr+"\n".join(s.ev)+"\n")
