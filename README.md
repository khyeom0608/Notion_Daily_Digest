# Notion Daily Digest

> **Notion → Gemini → Slack 일일 다이제스트 — 단일 Python 스크립트**
>
> 매일 정해진 시각에 여러 Notion 페이지의 최근 변경사항을 모아 Gemini로 친근한 요약을 만들어
> Slack에 단일 알림으로 보냅니다. cron / Lambda / 서버 없이 macOS launchd만으로 돌아갑니다.

<sub>EN: A standalone Python script that collects recent updates from selected Notion pages, summarizes them per-project with Google Gemini, and posts one digest to Slack via Incoming Webhook. Scheduled locally via macOS launchd — no external infrastructure.</sub>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

---

## 주요 기능

- 📅 **매일 자동 실행** — macOS launchd 기준 09:00 KST (시간/요일 조정 가능). 백그라운드 잡이라 사용자가 신경 쓸 일 없음
- 🗂 **프로젝트별 그룹핑** — `projects.json`에 등록한 Notion 페이지들의 **자식 페이지**(논문/아이디어 단위) 변경만 감지
- ✏️ **친근한 LLM 요약** — Gemini가 프로젝트마다 한 단락 요약 (한국어 톤 일관, 인사말 반복 X)
- 🛡 **RPD 한도 fallback** — Gemini 무료 tier 초과 시에도 알림 누락 없음. 요약 자리 대신 페이지 목록만 정상 전송
- 🪶 **무서버** — 본인 맥에서 launchd만 사용. AWS / 외부 cron / Bot Token 모두 불필요
- 🔇 **노이즈 컷** — 새 변경 0건이면 Slack 전송 자동 생략. state 파일로 매일 cutoff 자동 갱신

---

## Quick start

신규 사용자 기준:

| 단계 | 액션 | 소요 |
|---|---|---|
| 1 | **의존성 설치**: `pip install requests python-dotenv google-genai` | 1분 |
| 2 | **Notion integration 발급** → `.env`에 `NOTION_API_KEY`. 모니터링할 페이지마다 Connections 추가 | 5분 |
| 3 | **Gemini API key 발급** → [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → `.env`에 `GEMINI_API_KEY` | 1분 |
| 4 | **Slack Incoming Webhook URL 발급** → [api.slack.com/apps](https://api.slack.com/apps) → `.env`에 `SLACK_WEBHOOK_URL` | 3분 |
| 5 | `cp .env.example .env` 후 키 4개 채우기 | 1분 |
| 6 | `cp projects.json.example projects.json` 후 모니터링할 페이지 ID 채우기 | 2분 |
| 7 | `python3 daily_notion_digest.py --no-llm --dry-run --hours 72`로 수집 확인 | 1분 |
| 8 | `cp com.example.notion-digest.plist com.YOUR_USERNAME.notion-digest.plist` → 경로 수정 → `~/Library/LaunchAgents/`로 복사 → `launchctl load` | 5분 |

자세한 launchd 등록 명령어는 [#운영-launchd-등록](#운영--launchd-등록) 참조.

---

## 실행 모드

| 시나리오 | 명령어 | API 호출 |
|---|---|---|
| 본격 운영 (Slack 전송) | `python3 daily_notion_digest.py` | Notion + Gemini + Slack |
| 톤/형식 미리 확인 (Slack X) | `--dry-run` | Notion + Gemini |
| 본문 LLM 없이 페이지 목록만 전송 | `--no-llm` | Notion + Slack |
| 콘솔에만 출력 (Gemini RPD 절약) | `--no-llm --dry-run` | Notion |
| state 무시하고 직전 N시간 강제 | `--hours 48` | (조합 가능) |

> 💡 `--dry-run`은 Slack 전송만 생략하고 LLM은 호출합니다. Gemini RPD 한도가 걱정될 땐 `--no-llm`을 같이 줘서 LLM도 끄세요.

---

## 폴더 구조

```
.
├── README.md
├── LICENSE                              # MIT
├── daily_notion_digest.py               # 메인 (Notion 수집 → LLM 요약 → Slack 전송)
├── run_notion_digest.sh                 # launchd wrapper (작업 디렉토리 + 일자별 로그)
├── com.example.notion-digest.plist      # launchd 스케줄 템플릿 (시간/사용자명 수정 후 사용)
├── projects.json.example                # 모니터링 대상 Notion 페이지 템플릿
├── .env.example                         # API 키 템플릿 (4종)
└── .gitignore
```

런타임에 추가되는 (gitignored) 파일:
- `.env` — 본인 API 키
- `projects.json` — 본인 운영 프로젝트
- `com.<your_user>.notion-digest.plist` — 본인 launchd plist
- `notion_digest_state.json` — 직전 실행 시각

---

## 운영 — launchd 등록

```bash
# 1. example을 본인 환경으로 복사 + Label/경로 치환
cp com.example.notion-digest.plist com.YOUR_USERNAME.notion-digest.plist
# Label, ProgramArguments, WorkingDirectory, StandardOut/ErrorPath의
# YOUR_USERNAME / 경로를 본인 환경에 맞게 수정

# 2. LaunchAgents에 설치 + 로드
cp com.YOUR_USERNAME.notion-digest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.YOUR_USERNAME.notion-digest.plist

# 3. 등록 확인
launchctl list | grep notion-digest
#  - 0  com.YOUR_USERNAME.notion-digest

# 4. 일자별 로그 확인 (다음 9시 이후)
tail -50 ~/Library/Logs/notion-digest/digest-$(date +%Y-%m-%d).log
```

> ⚠️ **macOS TCC 주의**: `~/Downloads`, `~/Documents`, `~/Desktop`, iCloud 폴더는 launchd가 실행 못 합니다. 코드를 그 외 위치(예: `~/Hedwig`, `~/Projects/...`)에 두세요. 자동 로그인이 켜져 있어야 재부팅 후 LaunchAgent가 자동 복구됩니다.

---

## 핵심 설계 결정

| 항목 | 선택 | 이유 |
|---|---|---|
| 자동화 방식 | macOS launchd | cron보다 macOS-native, sleep wake 대응. AWS Lambda 대비 서버 0개 |
| LLM provider | Google Gemini 2.5 Flash Lite | free tier RPD 충분, 한국어 품질 양호, OpenAI 결제 없이 시작 |
| Slack 인증 | Incoming Webhook URL | Bot Token보다 단순. 채널 1개 단방향 전송이라 최소 권한 |
| 변경 감지 | state 파일 (last_run timestamp) | 매일 cutoff 자동 갱신. 놓친 날도 다음 실행에서 자동 캐치업 |
| 프로젝트 목록 | `projects.json`으로 분리 | 코드에 박지 않음. 공개 repo엔 example만, 실제 데이터는 `.gitignore` |
| RPD 초과 처리 | fallback 메시지 + 페이지 목록 | 알림 자체는 빠지지 않게. 익일 자동 회복 |
| Rate limit | 호출 사이 15s sleep + 백오프 [10,30,60,120]s | RPM/TPM 여유 확보. production은 하루 1회라 영향 미미 |

---

## Troubleshooting

| 증상 | 원인 / 점검 |
|---|---|
| 9시에 알림이 안 옴 | `launchctl list \| grep notion-digest` → 등록 상태 확인. 로그(`~/Library/Logs/notion-digest/`) 마지막 줄 확인 |
| 로그에 `Operation not permitted` | TCC 보호 폴더 안에 코드가 있음. `~/Downloads` 등에서 빼서 다른 위치로 |
| 로그에 `새 업데이트 없음 — Slack 전송 생략` | 정상. 그 날 노션에 새 변경 없었음 |
| 로그에 `429 RESOURCE_EXHAUSTED` | Gemini RPD 한도. fallback로 페이지 목록은 정상 발송됨. 익일 자동 회복 |
| Slack에 알림은 오는데 페이지가 안 보임 | Notion integration이 해당 페이지에 Connections로 연결됐는지 확인 |
| 재부팅 후 LaunchAgent가 사라짐 | 자동 로그인 OFF 상태. macOS 시스템 설정 → 사용자 및 그룹 → 자동 로그인 켜기 |

수동 트리거 (학생들/팀에 알림 갈 수 있음 — 신중히):
```bash
launchctl start com.YOUR_USERNAME.notion-digest
# 또는 dry-run으로 안전하게
python3 daily_notion_digest.py --dry-run --hours 24
```

---

## 라이센스

[MIT](./LICENSE) — 자유롭게 사용/수정/배포 가능.

---

## Credits

원본 운영: Joon An Lab (Korea University). 본 repo는 lab에서 운영 중인 routine을 일반화한 것입니다.
