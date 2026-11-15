# CaptureCards Library (TrueClean)

This folder holds everything known about CaptureCards. Read it before any CaptureCards ad. Each product gets its own folder (`library/<Product>/`). Shared, product-neutral assets such as sound-effect packs stay in `library/assets/`.

## Read in this order
1. `04_do_not_use/DO_NOT_USE.md`: the client's hard rules (product look, claims, mite visuals, skin). These rules override everything else.
2. `AD_STYLE_GUIDE.md`: the house style, learned from all sources (pacing, hooks, captions, checklist).
3. `03_winning_ads/WINNERS_PLAYBOOK.md`: what the 22 winning videos and 8 winning statics have in common, with measured numbers.
4. `01_resources_frameio/ATLAS.md`: every Frame.io footage file, beat by beat, with its compliance status. Use it to choose clips.
5. `05_sfx/SFX_GUIDE.md`: the client's SFX pack, with which sound goes on which kind of moment and at what level.

## Contents
| Folder | Source | What's inside |
|---|---|---|
| `01_resources_frameio/` | Frame.io resource share (footage library) | `ATLAS.md` / `ATLAS.json` (429 files, per-second beats, BANNED/CAUTION/OK, best in-points), `GALLERY_CATALOGUE.md`, `catalogue.json` |
| `02_previous_ads/` | Previous-ads shares: f.io/yIqZh79i (344 ads) and f.io/nW9g_P5a + f.io/OJBuHtBv (56 files, 14 concepts) | `AD_BEATS_PREVIOUS_ADS_2.md`, `BEAT_NOTES_shares2_3.md`, per-ad data (`data_share1_344ads/`, `data_shares2_3/`), contact sheets |
| `03_winning_ads/` | Winner Room (capturecards-winner-room…/#tc0165) | `WINNERS_PLAYBOOK.md`, `WINNERS_BEATS.md` (every shot with its VO), `WINNERS.json`, `WINNERS_SCRIPTS_AND_NOTES.md`, `WINNERS_STRATEGY_ANALYSIS.txt`, `winner_room_library.json`, contact sheets |
| `05_sfx/` | Client SFX pack (sfx.zip, TC0481) | `SFX_GUIDE.md`, `originals/` (10 files as received), `ready/` (trimmed and level-matched cuts) |
| `04_do_not_use/` | Client Drive guideline folder | `DO_NOT_USE.md`, both guideline-video transcripts, reference frames (`card.jpg` shows the real card) |

## Footage uniqueness rule
Each new project uses library clips that no earlier project has used. Before picking footage, check `FOOTAGE_USAGE.json`, which lists each clip and the projects that used it. After finishing a project, add that project's code to every clip it used. If no unused clip fits a line, generate the shot in Higgsfield instead of reusing an old one.

## Standing rules for every new ad (from the client, TC0488)
1. **Pick a winner at random as the reference.** Before planning the edit, choose one video at random from `03_winning_ads/WINNERS.json`. Study its beats (`WINNERS_BEATS.md`), contact sheets and notes, and carry its working edit choices into the new ad. Do not copy its script or any banned visuals, such as the teal card or the phone-light reveal. Record which winner was picked, and what was taken from it, in the project notes.
2. **Use real people from the resources**, not only AI people. Prefer one real creator who recurs through the ad as the "she" (several clips of the same person), then add other real UGC people for "most people" moments. Use AI for mites, cutaways, mechanism shots and any gaps the real footage can't cover. The card itself always comes from real footage.

## Caption style (from TC0481 v4)
Inter SemiBold 80, lowercase, black text on a white rounded box (corner radius 30, box height 112, about 32 px padding each side), centred at y = 1300 on 9x16. Two or three words per caption, or up to 17 characters. Strip punctuation. This replaced the white-with-black-outline style.

## Product facts (current)
- **What it is:** a dark-green fabric card with a plant-derived pheromone lure and an adhesive layer. Mites are drawn to the lure, stick to the card, and leave the bed when the card is thrown away.
- **Usage:** four cards per bed, kept sealed, moved monthly, replaced within 3 months.
- **Offer:** a 90-day money-back guarantee (no return needed). Check the current discount and the "30,000+ homes" figure before each ad.
- **Landing pages seen:** `mites-capturecards`, `capturecards-not-a-cold`, `capturecards-proof`, `capturecards-cant-stop-itching` (itch), `capturecards-menovsmite`, `capturecards-not-just-tired`, `capturecards-derp1`, `capturecards-tried-everything`.

## Projects built so far
These are in `video-studio/projects/`:
- `capturecards-tc0418`: Cleaning the Wrong Place.
- `capturecards-tc0421`: What Nobody's Checking.
- `capturecards-tc0451`: Three Dust Mite Myths.
- `capturecards-tc0481`: Itch Without Bites (3 hooks, 9x16).
- `capturecards-tc0482`: Weight Test (presenter plus VO, 9x16).
- `capturecards-tc0488`: Scale & Awareness 1 (unaware-allergy explainer, 9x16, 120 s).
