# CaptureCards SFX pack

The client sent this pack (`sfx.zip`) for TC0481. Use these sounds in CaptureCards ads before any generic library SFX.

- `originals/`: the files exactly as received.
- `ready/`: trimmed and level-matched cuts, ready to drop into a mix. Copy them into the project's `work/sfx/`.

## The sounds and where they go

| Ready file | Source | Length | Peak at | Use it on | Gain in mix* |
|---|---|---|---|---|---|
| `whoosh.mp3` | freesound_community whosh-88720 (first 1.2 s) | 1.2 s | 0.95 s | Every transition (zoom, slide, fade, circle). Start it **0.9 s before the cut** so the peak lands on the cut. | −15 dB |
| `wrong.mp3` | freesound_community wrong-47985 (first 0.75 s) | 0.8 s | 0.10 s | ✕ stamps over failed fixes ("Hot washes", "Covers", "Anti-itch cream", "No spray", "nothing to plug in"). Replaces the old stamp hit. | −14 dB |
| `shutter.mp3` | kauasilbershlachparodes shutter-click-2 (+8 dB) | 0.5 s | 0.05 s | Cut into a microscope or macro mite view ("droppings", "Deep in the mattress", "They're microscopic"). Reads as "zooming in to look". | −8 dB |
| `scratch_a.mp3`, `scratch_b.mp3` | `scratch.MP3`, 1.4 s slices at 12 s and 20 s (+8 dB) | 1.4 s | — | Under a shot of the character scratching (hook "waking up scratching", "your body reacts", "that reaction is itching"). Alternate a and b so they don't sound looped. Keep it quiet: felt, not heard. | −12 dB |
| `sneeze.mp3` | mixkit young-woman-sneeze-2216 | 1.7 s | — | Only over a sneezing shot (allergy angle, e.g. "if you're sensitive to it"). Not for itch-only ads unless a sneeze is shown. | −18 dB |
| `riser_2s.mp3` | riser-7-130957, the first 2.0 s build | 2.0 s | 1.9 s (the end) | Into the product reveal ("That's exactly what CaptureCards do"). Start it **1.95 s before** the reveal word. One per ad. | −14 dB |
| `pop_a.mp3`, `pop_b.mp3` | universfield bubble-pop-04 / -06 | 1.1 s | 0.10 s | When an on-screen badge or pill pops in (90-day guarantee badge, "TAP THE LINK BELOW" pill, number chips). | −10 dB |
| `tap.mp3` | vadim_makes_sound soft-app-button-tap-2 | 1.0 s | 0.00 s | The CTA "Tap the link below", about 0.45 s after the pill pops in, as if the button is pressed. | −8 dB |
| `click.mp3` | universfield ui-button-click-147358 | 0.8 s | 0.10 s | Social-proof or number beats ("Over 30,000 homes"), or a UI or app moment. | −10 dB |

*Gain is the value passed to the project mixer, which adds +4 dB. The VO stays on top, music sits at −15 dB with sidechain ducking, and the master is normalized to −14 LUFS.

## Rules
- Use one sound per event. Never stack two hits on the same frame (a ✕ stamp gets `wrong` only, not a whoosh as well).
- Plain hard cuts get no SFX. Whooshes go only on real transitions; aim for about 8–12 per 90 s ad, so the edit doesn't turn into constant swishing.
- Pick sounds by what's on screen: shutter only on a cut into microscope or macro footage, scratch only under visible scratching, sneeze only under a visible sneeze.
- The winners use almost no transition SFX (see `03_winning_ads/WINNERS_PLAYBOOK.md`). This pack is the client's own request from TC0481 onward, so it takes priority, but keep the levels low.

## First used in
TC0481 (H1–H3, 9x16 v4). Placement code is `place_sfx()` and `signs()` in `projects/capturecards-tc0481/work/build.py`.

## Licensing
The client supplied these files. From their names, they appear to come from Pixabay (universfield, freesound_community, vadim_makes_sound, kauasilbershlachparodes, u_1pruylktlg; Pixabay Content License, no attribution needed) and Mixkit (sneeze; Mixkit Sound Effects Free License). `scratch.MP3` has no source name; confirm with the client where it came from before using it outside their ads.
