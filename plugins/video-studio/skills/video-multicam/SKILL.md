---
name: video-multicam
description: Multi-camera and multi-recorder edits - video podcasts, interviews, panels, webinars with separate cameras, a camera plus a separate audio recorder or lav mics. Syncs everything by audio, auto-switches angles to whoever is talking, keeps one continuous audio mix. Use when there are 2+ angles or separately recorded audio of the same moment.
---

# Multicam

## 1. Sync
```bash
vs ingest $P/raw -o $P/work/media
vs sync $P/raw/<best-audio> $P/raw/camA.mp4 $P/raw/camB.mp4 $P/raw/wide.mp4 -o $P/work/sync.json
```
- Use the cleanest audio (mixer/recorder) as the reference (first file).
- Confidence < 8 → check: look at waveforms or listen around a clap; cameras with no usable audio
  must be synced by eye (`vs filmstrip` around a clap/flash) and the offset written into `sync.json` by hand.
- Recordings that stop/start (camera 30-min clip limits) → sync each file separately.

## 2. Switch
```bash
vs multicam --sync $P/work/sync.json \
  --angle $P/raw/camA.mp4=$P/raw/micA.wav --angle $P/raw/camB.mp4=$P/raw/micB.wav \
  --wide $P/raw/wide.mp4 --mix $P/raw/<best-audio> \
  --start <ref-time of first word> --end <ref-time of last word> -o $P/work/edl.json
```
- `VIDEO=MIC`: the mic that hears that person best (their lav, or the camera's own audio if each camera is close to its speaker).
- Tune: `--min-shot` 2–3 s (podcast), 1.2 s (energetic); `--max-shot` 8–15 s to cut to wide for variety;
  `--margin-db` higher = fewer switches.
- Result: segments switch picture; `audio_track` (with `follow`) keeps the sound from the mix, cut for cut.

## 3. Tighten the conversation
1. Transcribe the mix: `vs transcribe $P/raw/<best-audio> -o $P/work/mix.transcript` and read it.
   Its times are reference times when the mix is the sync reference (otherwise add its offset).
2. Choose what to keep (drop dead air, tangents, false starts, off-topic chat) as reference-time ranges
   on word boundaries. Present them as a cut list → **approval gate**.
3. Re-run `vs multicam ... --keep 12.4-95.2 --keep 101.0-240.7 ...`. Each kept range is switched by speaker, and
   the audio follows the cuts from the mix.
4. Punch-ins on single-speaker shots (`zoom` 1.1) for emphasis, lower-third names (`texts`) at first appearance,
   `dip-black` between topics if wanted.
5. Captions: `vs captions $P/work/mix.transcript.json $P/work/edl.json -o $P/work/captions ...` maps the mix
   transcript through every shot automatically (the mix must be the EDL's `audio_track`).

## 4. Deliver
Full episode `--preset youtube` (or `podcast` −16 LUFS), audio-only via `vs convert out/final.mp4 -o out/ep.mp3`,
clips via `/video-repurpose` (vertical crops: `focus` per speaker).
