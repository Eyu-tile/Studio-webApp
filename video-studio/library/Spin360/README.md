# Spin360 library

Luxury pedestal fan brand. **Luxury. Quiet. Refreshing.** Read before any Spin360 edit:

0. `CAST_AND_SETS.md`: who, where, which unit, product details, audio notes. `CLAIMS.md`: every claim in the footage + risk.
1. `BRAND_GUIDE.md`: palette, Inter, logo versions, required photography look, product details, video defaults.
2. `DO_NOT_USE.md`: banned/caution rules (includes a third-party logo hidden in the guide's Soft Wave sample).
3. `resources/ATLAS.md`: the footage atlas (built with `vs learn`, once sources are added).
4. `WINNING_ADS.md` + `ads/AD_PLAYBOOK.md`: what has worked and how past ads were built (from 272 briefs).
5. `USAGE_LOG.md`: what has already been used where.

## Layout
| path | what |
|---|---|
| `brand/Spin360_Style_Guide_v1.pdf` | the client's style guide (v1, Aug 2025) |
| `brand/logo/` | 4 approved logo versions, transparent PNG (4167 px) |
| `brand/images/` | product renders (black pearl, white pearl), mood/inspiration and room references from the guide |
| `resources/` | inventory, atlas (`ATLAS.md`, `atlas_full.json` with transcripts), sources, usage |
| `tools/` | `bya_pull.py` (re-scan the BuildYourAds library), `bya_thumbs.py` (thumbnail contact sheet for clip ids) |

## Sources
| added | source | provider | files | sampled | described |
|---|---|---|---|---|---|
| 2026-11-14 | Spin360 Style Guide v1 (uploaded PDF) | local | 1 PDF, 4 logos, 11 images | - | yes (this README + BRAND_GUIDE) |
| 2026-11-14 | BuildYourAds workspace `acme` (API, `https://buildyourads.com`) | buildyourads | 779 clips, 323 min, 23 folders | 633 unique live clips: frame at every cut + every 1 s (b-roll) / ~1-6 s (talking heads), from the originals | **all 633 described by eye** (shot lists, beats, takes); 82 duplicates + 64 archived inherit / keep BYA |

## Open questions for the client
- Rights to the inspiration/room photos in the guide: OK to use in ads, or reference only?
- Clean Soft Wave pattern file (without the Waterman logo)? Vector logo files (SVG/AI)?
- Scent names, key specs/claims we may say (noise level, speeds, oscillation), price and offer, target audience.

## BuildYourAds access
- API docs: https://buildyourads.com/api/v1/docs. Auth: `Authorization: Bearer <brand key>`, saved as a network secret on the cloud
  environment (injected by the proxy), never in this repo. Read endpoints used: `/api/v1/folders`, `/api/v1/clips`,
  `/api/v1/clips/<id>`, `/api/v1/clips/<id>/media`. `/status/pipeline` needs a browser login.
- The key is a brand key with write access too: I only call GET endpoints unless asked.
- Re-scan: `python3 tools/bya_pull.py <outdir>` then rebuild the atlas.
- Footage is creator UGC (Vicky, Lauren, Avery, Kylie, Michael, Sean), talking-head scripts, b-roll, 44 Higgsfield AI
  clips and a few Artlist stock clips. BuildYourAds already labels script lines (Hook, Product benefit, Mechanism explainer,
  Room transformation, Failed alternative, Dead silent, Scent rotation, Offer CTA ...).

## Using the map
- `resources/ATLAS.md`: every clip (status, product, fit/hook/quality, best seconds, summary). `atlas_full.json` `eye`: full shot list.
- `resources/BROLL_INDEX.md` (by beat), `SCRIPT_TAKES.md` (every line + best takes), `HOOKS.md`, `PRODUCT_SHOTS.md` (by colourway), `PEOPLE.md`.
- Search: `python3 tools/find.py "paper towel bottom intake" --colour white --ok`, `--beat airflow_demo_hand --min-fit 2`, `--room bedroom`.
- Rebuild after re-describing: `python3 tools/merge_desc.py`. New footage: `tools/bya_pull.py` → `tools/bya_sample.py` → `tools/make_batches.py` → describe with `resources/DESCRIBE_BRIEF.md`.
- Contact sheets live in `resources/sheets/` (not committed; regenerate with `tools/bya_sample.py`).

## Past ads (`ads/`)
- `AD_PLAYBOOK.md`: audience, formats, hooks, structure, tone, offers over time, claim rules, winners, a recipe for new ads.
- `CATALOGUE.md` (272 briefs, 1,183 ads), `HOOK_BANK.md` (824 hooks), `briefs_index.json` (per-brief data), `briefs/` (brief texts),
  `roadmap_rows.json` + `creative_roadmap_2026-11-14.xlsx` (the sheet with every link). Exported videos: Drive links are private; share them to watch.
