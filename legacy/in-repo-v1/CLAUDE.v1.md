# CLAUDE.md

This repo holds two things:

1. **Nexa landing page**: Vite + React 18 + TypeScript + Tailwind, three.js/GSAP/framer-motion.
   `npm run dev` · `npm run build` (tsc + vite) · `npm run lint`. Static assets in `public/`, code in `src/`.
2. **video-studio/**: an agentic video editing workspace (see `video-studio/README.md`).

## Video editing
- Any request to edit, cut, caption, reformat, QA or add graphics to a video: use the `video-edit` skill
  (it routes to `video-captions`, `video-qa`, `motion-graphics`, `video-style-guide`, `video-nle-handoff`, `video-setup`).
- Tools run from the repo root: `video-studio/vs <cmd>` (`vs help`). Check with `video-studio/vs doctor`.
- Before planning any edit, read `video-studio/style/notes.md`, `brand.md`, `moves.md` and the project's `project.md`.
- Gates: show the cut list before any full render; drafts render with `--preview`; run `vs qa` before showing a render.
- Raw footage in `video-studio/projects/*/raw/` is read-only; outputs go to `work/` and `out/`. Projects are git-ignored.
  Never commit media.
- Feedback that should apply to future edits → one line in `video-studio/style/notes.md`.
- Motion graphics are HyperFrames compositions (`/hyperframes`); vendored skills are pinned in `skills-lock.json`.
  Don't hand-edit vendored skill folders (`hyperframes*`, `media-use`); refresh with `bash video-studio/setup.sh --hf-update`.
