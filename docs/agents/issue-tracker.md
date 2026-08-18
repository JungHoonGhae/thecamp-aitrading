# Issue tracker: Linear

Issues and specs for this lecture live in Linear. Do not create GitHub issues, GitLab issues, or `.scratch/` tickets unless the user explicitly asks.

| | |
| --- | --- |
| Workspace | [Remodule](https://linear.app/remodule) |
| Team | ReModule (`REMOD`) |
| Project | [EDU-Fastcampus-AI-Trading](https://linear.app/remodule/project/edu-fastcampus-ai-trading-f504f6889edf) |
| Identifiers | `REMOD-123` |
| MCP | Cursor server `user-linear` (`https://mcp.linear.app/mcp`) |

This repo is the student lab (`edu-fastcampus-thecamp-aitrading`). Lecture ops live in `ops/` (private nested git). Both use this same Linear project.

## Status workflow

Use these **exact** ReModule status names:

| Linear status | Type | Meaning |
| ------------- | ---- | ------- |
| `Backlog` | backlog | Captured, not scheduled |
| `Todo` | unstarted | Ready to start |
| `🚀 In Progress` | started | Someone (or an agent) is working it |
| `🎉 Done` | completed | Complete |

The team also has QA/review statuses (`🔍 PR Review Requested`, `🛠 Staging QA Testing`, …). Do not use those for lecture-prep tickets unless the user asks.

Triage *roles* are **labels**, not statuses. See `docs/agents/triage-labels.md`. A ticket can be `Todo` and `ready-for-agent` at the same time.

## How to talk to Linear

Use the Linear MCP (`user-linear`). If it reports `needsAuth`, call `mcp_auth` then retry. If MCP is unavailable, draft the issue in chat and ask the user to create it — do not fall back to GitHub.

Discover tool schemas with `GetMcpTools` before calling.

## Conventions

- **Create an issue**: `save_issue` with `team` = `ReModule`, `project` = `EDU-Fastcampus-AI-Trading`, `title`, `description`, `state` = `Backlog` unless the skill says otherwise, and triage `labels` from `docs/agents/triage-labels.md`.
- **Read an issue**: `get_issue` with `id` = `REMOD-123` and `includeRelations` = true. Also `list_comments` for the thread.
- **List issues**: `list_issues` filtered by `team` = `ReModule` and `project` = `EDU-Fastcampus-AI-Trading`, plus `state` / `label` as needed. Ask for `title`, `description`, `labels`, `status`, `url`, `assignee`, `parentId`.
- **Comment**: `save_comment` with `issueId` and `body`. Do not overwrite the description unless the skill is updating the spec itself.
- **Apply / remove labels**: `save_issue` `labels` **replaces the full set** — read current labels first, then send the new complete list.
- **Close**: `save_issue` with `state` = `🎉 Done` and a comment explaining why.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## When a skill says "publish to the issue tracker"

Create a Linear issue on team ReModule in project EDU-Fastcampus-AI-Trading (`save_issue`).

## When a skill says "fetch the relevant ticket"

`get_issue` by identifier (`REMOD-123` or a Linear URL) plus `list_comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single Linear issue whose **child** issues are tickets.

- **Map**: one issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. Status `🚀 In Progress` while the effort is live. `save_issue` with `labels` including `wayfinder:map`, `project` = `EDU-Fastcampus-AI-Trading`.
- **Child ticket**: a Linear sub-issue of the map (`parentId` = map identifier). Put the question in the description. Labels: `wayfinder:<type>` (`research` / `prototype` / `grilling` / `task`). Once claimed, assign the ticket to the driving person (`assignee`).
- **Blocking**: Linear `blockedBy` / `blocks` on `save_issue`. A ticket is unblocked when every blocker is `🎉 Done`.
- **Frontier query**: `list_issues` with `parentId` = map, drop status `🎉 Done`, drop any with an open blocker or an assignee; first in map order wins.
- **Claim**: `save_issue` with `assignee` = `me` and `state` = `🚀 In Progress` — the session's first write.
- **Resolve**: `save_comment` with the answer, `save_issue` `state` = `🎉 Done`, then append a context pointer (gist + link) to the map's Decisions-so-far.
