# Notion Daily Digest

> **A single-script Notion → Gemini → Slack daily digest**
>
> Collects recent updates from selected Notion pages each morning, summarizes them
> per-project with Google Gemini, and posts one digest to Slack via Incoming Webhook.
> No cron, no Lambda, no server — just macOS `launchd`.

<sub>KR: 여러 Notion 페이지의 매일 변경사항을 모아 Gemini로 친근한 한국어 요약을 만들어 Slack에 단일 알림으로 보내는 단일 Python 스크립트. macOS launchd로 로컬 실행.</sub>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

---

## Features

- 📅 **Runs daily, hands-off** — macOS `launchd` fires it at 09:00 local time (configurable). Background job; you forget about it
- 🗂 **Per-project grouping** — `projects.json` lists which Notion pages to watch. Only **child pages** of those parents (i.e. individual notes / paper write-ups) are tracked for changes
- ✏️ **Friendly LLM summary** — One short paragraph per project from Gemini, in a consistent conversational tone (no repetitive greetings)
- 🛡 **Graceful RPD fallback** — When Gemini's free-tier daily quota is hit, the summary line is replaced with a fallback message and the page list is still delivered. Alerts never go silent
- 🪶 **Serverless** — Runs on your own Mac via launchd. No AWS, no external cron, no bot tokens
- 🔇 **Noise filter** — Sends nothing when there are zero changes. The state file auto-updates the cutoff each run

---

## Quick start

For a brand-new install:

| # | Step | Time |
|---|---|---|
| 1 | Install deps: `pip install requests python-dotenv google-genai` | 1 min |
| 2 | Create a Notion integration → put the token (`ntn_...`) in `.env`. Connect the integration to each Notion page you want to watch (page menu → Connections) | 5 min |
| 3 | Get a Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → `.env` | 1 min |
| 4 | Create a Slack Incoming Webhook URL at [api.slack.com/apps](https://api.slack.com/apps) → `.env` | 3 min |
| 5 | `cp .env.example .env` and fill in the four keys | 1 min |
| 6 | `cp projects.json.example projects.json` and fill in your Notion page IDs | 2 min |
| 7 | Smoke-test without calling LLM or Slack: `python3 daily_notion_digest.py --no-llm --dry-run --hours 72` | 1 min |
| 8 | Copy `com.example.notion-digest.plist`, edit paths/username, install to `~/Library/LaunchAgents/`, and `launchctl load` it | 5 min |

Full launchd commands are in [Operations — launchd setup](#operations--launchd-setup).

---

## Run modes

| Goal | Command | API calls |
|---|---|---|
| Real run (post to Slack) | `python3 daily_notion_digest.py` | Notion + Gemini + Slack |
| Preview tone/format (no Slack) | `--dry-run` | Notion + Gemini |
| LLM off — page list only, still posts to Slack | `--no-llm` | Notion + Slack |
| Console only, no LLM (saves Gemini RPD) | `--no-llm --dry-run` | Notion |
| Force a fixed lookback, ignoring state | `--hours 48` | (combine with the above) |

> 💡 `--dry-run` skips Slack but still calls the LLM. To avoid burning Gemini RPD while iterating, add `--no-llm`.

---

## Layout

```
.
├── README.md
├── LICENSE                              # MIT
├── daily_notion_digest.py               # Main script: Notion fetch → LLM summary → Slack post
├── run_notion_digest.sh                 # launchd wrapper: cd + per-day log file + invoke python
├── com.example.notion-digest.plist      # launchd schedule template (edit time / username, then install)
├── projects.json.example                # Template for Notion pages to monitor
├── .env.example                         # Template for the four API keys
└── .gitignore
```

Created at runtime (all gitignored):
- `.env` — your real keys
- `projects.json` — your real project list
- `com.<your_user>.notion-digest.plist` — your real launchd plist
- `notion_digest_state.json` — last-run timestamp

---

## Operations — launchd setup

```bash
# 1. Copy the template and edit Label / paths
cp com.example.notion-digest.plist com.YOUR_USERNAME.notion-digest.plist
# Replace YOUR_USERNAME in: Label, ProgramArguments, WorkingDirectory,
# StandardOutPath, StandardErrorPath

# 2. Install and load
cp com.YOUR_USERNAME.notion-digest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.YOUR_USERNAME.notion-digest.plist

# 3. Verify registration
launchctl list | grep notion-digest
#   -    0   com.YOUR_USERNAME.notion-digest

# 4. After the next scheduled run, inspect the daily log
tail -50 ~/Library/Logs/notion-digest/digest-$(date +%Y-%m-%d).log
```

> ⚠️ **macOS TCC**: `launchd` cannot execute scripts inside `~/Downloads`, `~/Documents`, `~/Desktop`, or iCloud-synced folders. Keep the code somewhere else (e.g. `~/Notion_Daily_Digest`, `~/Projects/...`). Also enable **automatic login** so the LaunchAgent reloads after reboot on an unattended Mac.

---

## Output language

By default, the LLM prompt, the Slack header / notification text, and the fallback summary line are **in Korean** — this codebase originated in a Korean-speaking lab and was generalized from there.

To switch the digest to another language, edit:
- `SYSTEM_INSTRUCTION` in `daily_notion_digest.py`
- The prompt template inside `llm_summarize()`
- The `header` / `sub` strings inside `build_slack_blocks()`
- The fallback `text` field inside `post_to_slack()`

All four are clearly marked with comments.

---

## Design decisions

| Aspect | Choice | Why |
|---|---|---|
| Scheduler | macOS `launchd` | Native to macOS, handles sleep/wake. Zero servers compared to Lambda |
| LLM | Google Gemini 2.5 Flash Lite | Free-tier RPD is enough for daily runs; good Korean/English quality; no billing required to start |
| Slack auth | Incoming Webhook URL | Simpler than a Bot Token. One-way post to one channel = minimal permission |
| Change detection | State file (`last_run` timestamp) | Cutoff advances automatically. Missed days auto-catch-up on next run |
| Project list | Separate `projects.json` (not hardcoded) | Keeps lab-specific IDs out of the repo. The repo ships only `projects.json.example` |
| RPD-exhausted handling | Fallback line + page list | Notifications never go silent. Recovers on next free-tier reset |
| Rate limiting | 15s sleep between calls + backoff `[10, 30, 60, 120]s` | Keeps each run far under RPM/TPM ceilings. Production runs once a day, so the added wall-clock is harmless |

---

## Troubleshooting

| Symptom | Likely cause / what to check |
|---|---|
| No alert at 9 AM | `launchctl list \| grep notion-digest` — is it registered? Then check the last log under `~/Library/Logs/notion-digest/` |
| Log says `Operation not permitted` | Code is in a TCC-protected folder (`~/Downloads` etc.). Move it elsewhere |
| Log says `No new updates — skipping Slack` | Working as intended. Nothing changed in Notion that day |
| Log says `429 RESOURCE_EXHAUSTED` | Gemini RPD hit. Fallback still posts the page list. Recovers on next reset |
| Slack message arrives but pages look missing | Make sure the Notion integration is connected to those pages (page menu → Connections) |
| LaunchAgent disappears after reboot | Auto-login is off. macOS System Settings → Users & Groups → Automatic login |

Manual trigger (sends to Slack — careful):
```bash
launchctl start com.YOUR_USERNAME.notion-digest
# Or safely:
python3 daily_notion_digest.py --dry-run --hours 24
```

---

## License

[MIT](./LICENSE) — use, modify, and distribute freely.

---

## Credits

Originally built for and operated by **Joon An Lab (Korea University)**. This repo is a generalized version of our internal daily-digest routine.
