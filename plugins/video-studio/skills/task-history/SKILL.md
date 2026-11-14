---
name: task-history
description: Client task history by code (e.g. TC0488) - start a task, record each delivered version, log client feedback, and resume exactly where it was left, even in a new session or on another machine. Use when the person names a task code, says "continue", "back to", "the client replied", "client feedback on", "what did we deliver", "revision", or when an ad or edit is delivered to a client.
---

# Task history

`vs task` keeps one history per client task in `<workspace>/history/<CODE>.json` and `<CODE>.md`. These are
small text files committed with the workspace, so they survive new sessions and other machines. Each delivery
snapshots the edit's inputs (script, shot list, EDLs, builder, project.md) into `history/<CODE>/vN/`.

## Starting work
- New client task: `vs task new <CODE> --project <folder> --client "<Client>" --title "<title>" --brief <file|text>`.
  Use the client's own code when they have one (TC0488); otherwise make one up and tell the person.
- The person names a code, or says "continue", "back to it", or "the client replied": run `vs task resume <CODE>`
  **before anything else**. Then read the files it lists (`history/<CODE>.md`, the project's `project.md` and
  `NOTES.md`). Say in two or three lines where things stand (last version, open feedback, next step), then continue.
- No code given: `vs task list --open`, and ask which one if several fit.
- Project folder missing on this machine (fresh cloud session): `vs task restore <CODE>` brings back the edit
  files of the last version. Footage and renders are re-fetched from the sources those files list.

## Delivering
After sending a version to the client, always run
`vs task deliver <CODE> --file <final file> [--file ...] [--link <where they got it>] --note "<what changed>"`.
Write the note for someone who wasn't here: what this version changed and why.

## Client feedback
- Log it as soon as it arrives: `vs task feedback <CODE> "<their words>" [--who <name>] [--on v2]`. Use `--split`
  for one item per line, or `--file comments.txt`. Keep their wording; don't paraphrase it away.
- Timestamped comments ("0:12 cut later"): also run `vs notes add` as printed, to map them onto shots in the EDL of
  the version they reviewed. Do that before changing the edit.
- Work through the open items. When one is handled, run `vs task done <CODE> <#> --how "<what you did>"`. If you
  won't do one, run `vs task done <CODE> <#> --skip "<why>"` and tell the person.
- Decisions and context worth keeping (client preferences, things to avoid, approvals):
  `vs task note <CODE> "<text>"`.
- Deliver the revision with `vs task deliver` as above. `vs task close <CODE>` once the client approves.

Never invent feedback or mark an item done that wasn't done. `resume` shows only what was recorded.
