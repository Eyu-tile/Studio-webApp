#!/usr/bin/env python3
"""Transcribe a video/audio file to word-level timestamps.

Backends (first available wins unless --backend is given):
  faster-whisper  (pip install faster-whisper)       Linux/Windows/macOS, CPU or CUDA
  mlx-whisper     (pip install mlx-whisper)          Apple Silicon, fastest on Mac
  whisper         (pip install openai-whisper)       reference implementation

Output: <out>.json with {"words": [{"w","s","e","p"}], "segments": [...]} and
a packed, LLM-friendly <out>.md (see pack.py). Run pack.py again any time.

Usage:
  python3 video-studio/scripts/transcribe.py RAW.mp4 -o work/transcript
  python3 video-studio/scripts/transcribe.py RAW.mp4 -o work/transcript --model large-v3 --lang en
"""
import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, need, probe, run, save_json  # noqa: E402

BACKENDS = ["faster-whisper", "mlx-whisper", "whisper"]
MODULES = {"faster-whisper": "faster_whisper", "mlx-whisper": "mlx_whisper", "whisper": "whisper"}


def available(backend):
    return importlib.util.find_spec(MODULES[backend]) is not None


def extract_audio(src, dst):
    need("ffmpeg")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(dst)])


def via_faster_whisper(wav, model, lang, prompt):
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="auto", compute_type="auto")
    segs, info = m.transcribe(
        str(wav), language=lang, word_timestamps=True, vad_filter=False,
        initial_prompt=prompt, condition_on_previous_text=False,
    )
    words, segments = [], []
    for s in segs:
        segments.append({"s": round(s.start, 3), "e": round(s.end, 3), "text": s.text.strip()})
        for w in s.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3),
                          "p": round(w.probability, 3)})
    return words, segments, info.language


def via_openai_style(mod, wav, model, lang, prompt):
    kwargs = dict(word_timestamps=True, language=lang, initial_prompt=prompt,
                  condition_on_previous_text=False)
    if mod.__name__ == "mlx_whisper":
        repo = model if "/" in model else f"mlx-community/whisper-{model}-mlx"
        res = mod.transcribe(str(wav), path_or_hf_repo=repo, **kwargs)
    else:
        res = mod.load_model(model).transcribe(str(wav), **kwargs)
    words, segments = [], []
    for s in res["segments"]:
        segments.append({"s": round(s["start"], 3), "e": round(s["end"], 3), "text": s["text"].strip()})
        for w in s.get("words", []):
            words.append({"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3),
                          "p": round(w.get("probability", 1.0), 3)})
    return words, segments, res.get("language", lang)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True, help="output path without extension")
    ap.add_argument("--backend", choices=BACKENDS)
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3|turbo (default small; use large-v3 for finals)")
    ap.add_argument("--lang", default=None, help="language code, e.g. en (auto-detect if omitted)")
    ap.add_argument("--prompt", default=None,
                    help="vocabulary hint: brand names, jargon (e.g. 'Acme, Supabase, Kubernetes')")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        die(f"{src} not found")
    backend = args.backend or next((b for b in BACKENDS if available(b)), None)
    if backend is None or not available(backend):
        die("no transcription backend installed. Run: vs setup "
            "(or pip install faster-whisper)")

    info = probe(src)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "audio.wav"
        extract_audio(src, wav)
        print(f"transcribing {src.name} ({info['duration']:.1f}s) with {backend}/{args.model} ...",
              file=sys.stderr)
        try:
            if backend == "faster-whisper":
                words, segments, lang = via_faster_whisper(wav, args.model, args.lang, args.prompt)
            else:
                mod = __import__(MODULES[backend])
                words, segments, lang = via_openai_style(mod, wav, args.model, args.lang, args.prompt)
        except Exception as e:  # model download / load errors are the common case
            die(f"{backend} failed: {type(e).__name__}: {e}\n"
                "The first run downloads the model from Hugging Face: huggingface.co and *.hf.co "
                "must be reachable (cloud sessions: allow them in the environment's network settings).")

    out = Path(args.out)
    data = {
        "source": str(src), "duration": info["duration"], "language": lang,
        "backend": backend, "model": args.model, "words": words, "segments": segments,
    }
    save_json(out.with_suffix(".json"), data)
    subprocess.run([sys.executable, str(Path(__file__).parent / "pack.py"),
                    str(out.with_suffix(".json")), "-o", str(out.with_suffix(".md"))], check=True)
    print(f"wrote {out.with_suffix('.json')} ({len(words)} words) and {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
