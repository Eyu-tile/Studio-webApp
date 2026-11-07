---
name: video-nle-handoff
description: Hand an agent-made rough cut to a traditional editor (Premiere Pro, DaVinci Resolve, Final Cut Pro, Avid) for colour, multicam or final polish - export CMX3600 EDL / FCPXML timelines from the EDL, or drive Resolve/Final Cut directly through an MCP server. Use when someone wants to "finish in Premiere/Resolve/FCP", export an XML/EDL, or connect Claude to their NLE.
---

# NLE handoff

## Export a timeline (works everywhere)
```bash
video-studio/vs export video-studio/projects/<name>/work/edl.json -o video-studio/projects/<name>/out/rough_cut --fps 30
```
- `rough_cut.edl` (CMX3600): Premiere (File › Import), Resolve (File › Import › Timeline), Avid. Relink media to the original files on import.
- `rough_cut.fcpxml`: Final Cut Pro and Resolve. Media is referenced by absolute path, so import on the machine with the footage.
- Hand over captions as `work/captions.srt` (import as a caption track) and graphics as the rendered overlay files.
- Frame rate must match the footage; pass `--fps` for 23.976/29.97 projects (CMX3600 here is non-drop).

## Drive the NLE (MCP, local only)
These need the NLE running on the person's own machine, so set them up there, not in a cloud session.
Verify the repo is maintained and read its README before installing.
- **DaVinci Resolve** (Studio; Preferences › General › External scripting = Local):
  `Tooflex/davinci-resolve-mcp`, or `lordhoell/davinci-resolve-mcp` (ships its own Claude Code skill;
  `claude mcp add davinci-resolve -- davinci-resolve-mcp` after installing it per its README).
- **Final Cut Pro** (macOS): `dreliq9/fcp-mcp`, `claude mcp add --transport stdio fcp -- uvx fcp-mcp`.
- **Premiere Pro**: no mature MCP yet. Import the `.edl` (Premiere doesn't read FCPXML natively).

With an MCP connected: build the timeline from `edl.json` (one clip per segment, in order), add
markers for every graphic/caption note, and leave colour and audio mix to the editor unless asked.
