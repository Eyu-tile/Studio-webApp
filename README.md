# video-studio marketplace

A Claude Code plugin marketplace with one plugin: **[`video-studio`](plugins/video-studio)**, an
agentic video editor for talking heads, shorts, YouTube, podcasts and multicam, montages, music videos,
screen recordings, ads and slideshows.

## Install
In Claude Code:
```
/plugin marketplace add Eyu-tile/video-studio-claude-plugin
/plugin install video-studio@video-studio-marketplace
```
From a terminal:
```bash
claude plugin marketplace add Eyu-tile/video-studio-claude-plugin
claude plugin install video-studio@video-studio-marketplace
```
No GitHub? Point at the unzipped folder instead: `claude plugin marketplace add ~/path/to/video-studio-marketplace`.
Try without installing: `claude --plugin-dir ./plugins/video-studio`.

Then once per machine, in Claude Code: "set up video editing".

## Share with a team
Add to a project's `.claude/settings.json` so everyone who opens the repo is offered the plugin:
```json
{
  "extraKnownMarketplaces": {
    "video-studio-marketplace": { "source": { "source": "github", "repo": "Eyu-tile/video-studio-claude-plugin" } }
  },
  "enabledPlugins": { "video-studio@video-studio-marketplace": true }
}
```

## Develop
```bash
claude plugin validate plugins/video-studio
claude plugin validate .
claude --plugin-dir ./plugins/video-studio plugin details video-studio
```
Bump `version` in both `plugins/video-studio/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
when you release; users get it with `/plugin update video-studio`.

## Repository layout
- `plugins/video-studio/`: the plugin (install it with the commands above)
- `examples/nexa-workspace/`: a ready-made brand / moves / notes set to copy into a project
- `legacy/in-repo-v1/`: the first, in-repo version of the toolkit, kept for reference
