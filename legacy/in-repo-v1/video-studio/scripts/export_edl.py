#!/usr/bin/env python3
"""Export an EDL json to formats an NLE can open, for finishing in
Premiere Pro, DaVinci Resolve or Final Cut Pro.

  .edl   CMX3600 (Premiere, Resolve, Avid; File > Import > EDL)
  .fcpxml  FCPXML 1.10 (Final Cut Pro, Resolve; File > Import > XML)

Usage:
  python3 video-studio/scripts/export_edl.py work/edl.json -o out/rough_cut --fps 30
"""
import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import edl_segments, load_json, probe  # noqa: E402


def tc(t, fps):
    f = int(round(t * fps))
    fr = int(round(fps))
    h, f = divmod(f, 3600 * fr)
    m, f = divmod(f, 60 * fr)
    s, f = divmod(f, fr)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("-o", "--out", required=True, help="output path without extension")
    ap.add_argument("--fps", type=float, help="timeline fps (default: first source)")
    ap.add_argument("--title", default="Claude rough cut")
    args = ap.parse_args()

    edl = load_json(args.edl)
    segs = list(edl_segments(edl))
    srcs = list(dict.fromkeys(s for s, *_ in segs))
    probes = {s: probe(s) for s in srcs}
    fps = args.fps or probes[srcs[0]]["fps"] or 30
    fr = int(round(fps))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # CMX3600
    lines = [f"TITLE: {args.title}", "FCM: NON-DROP FRAME", ""]
    rec = 0.0
    for i, (src, a, b, _) in enumerate(segs, 1):
        reel = f"AX{srcs.index(src) + 1:02d}"[:8]
        lines.append(f"{i:03d}  {reel:<8} AA/V  C        {tc(a, fps)} {tc(b, fps)} {tc(rec, fps)} {tc(rec + b - a, fps)}")
        lines.append(f"* FROM CLIP NAME: {Path(src).name}")
        lines.append("")
        rec += b - a
    out.with_suffix(".edl").write_text("\n".join(lines), encoding="utf-8")

    # FCPXML: rational times in frames/fps.
    def rt(t):
        return f"{int(round(t * fr)) * 100}/{fr * 100}s"

    p0 = probes[srcs[0]]
    res = [f'<format id="r0" name="FFVideoFormat{p0["height"]}p{fr}" frameDuration="100/{fr * 100}s" '
           f'width="{p0["width"]}" height="{p0["height"]}"/>']
    for k, s in enumerate(srcs, 1):
        uri = Path(s).resolve().as_uri()
        res.append(f'<asset id="a{k}" name={quoteattr(Path(s).name)} start="0s" duration="{rt(probes[s]["duration"])}" '
                   f'hasVideo="1" hasAudio="{1 if probes[s]["has_audio"] else 0}" format="r0">'
                   f'<media-rep kind="original-media" src={quoteattr(uri)}/></asset>')
    clips, rec = [], 0.0
    for src, a, b, seg in segs:
        name = quoteattr((seg.get("text") or Path(src).name)[:60])
        clips.append(f'<asset-clip ref="a{srcs.index(src) + 1}" name={name} offset="{rt(rec)}" '
                     f'start="{rt(a)}" duration="{rt(b - a)}" tcFormat="NDF"/>')
        rec += b - a
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
  <resources>
    {chr(10).join('    ' + r for r in res).strip()}
  </resources>
  <library>
    <event name={quoteattr(args.title)}>
      <project name={quoteattr(args.title)}>
        <sequence format="r0" duration="{rt(rec)}" tcStart="0s" tcFormat="NDF">
          <spine>
            {chr(10).join('            ' + c for c in clips).strip()}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""
    out.with_suffix(".fcpxml").write_text(xml, encoding="utf-8")
    print(f"{len(segs)} events -> {out.with_suffix('.edl')}, {out.with_suffix('.fcpxml')}")


if __name__ == "__main__":
    main()
