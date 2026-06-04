# Notion Daily Digest

매일 정해진 시각에 Notion 페이지의 최근 변경사항을 모아 LLM으로 요약해 Slack에 전송하는 단일 파이썬 스크립트.

연구실, 스터디 모임, 사이드 프로젝트 등에서 "여러 Notion 페이지를 매일 한 알림으로 받고 싶다"는 케이스에 적합합니다.

## 동작 방식

1. 매일 정해진 시각(예: 09:00 KST)에 macOS `launchd`가 스크립트를 실행
2. `projects.json`에 등록된 각 페이지의 **자식 페이지** 중 직전 실행 이후 추가/수정된 것을 수집
3. 프로젝트별로 Google Gemini가 친근한 톤의 한 단락 요약 생성 (RPD 한도 초과 시 페이지 목록만 fallback)
4. Slack Incoming Webhook으로 한 메시지 전송 (헤더 + 프로젝트별 섹션)
5. 새 변경이 없으면 Slack 전송 생략

## 필요한 것

- macOS (launchd 사용) — Linux/Windows는 cron/Task Scheduler로 동등하게 가능
- Python 3.9+
- Notion API integration (`ntn_` 토큰)
- Google Gemini API key ([free tier OK](https://aistudio.google.com/apikey))
- Slack Incoming Webhook URL (채널 1개 전용)

## 설치

```bash
git clone https://github.com/<your-id>/Notion_Daily_Digest.git
cd Notion_Daily_Digest
pip install requests python-dotenv google-genai
```

### 1. `.env` 작성

```bash
cp .env.example .env
# .env 열어서 키 4개 채우기
```

### 2. `projects.json` 작성

모니터링할 Notion 페이지 ID를 채웁니다. 각 페이지는 **자식 페이지를 가진 부모 페이지**여야 하고, 자식 페이지의 추가/수정이 알림 대상이 됩니다.

```bash
cp projects.json.example projects.json
# 본인 페이지 ID로 수정
```

> ⚠️ Notion API integration이 각 페이지에 **Connections**로 추가되어 있어야 봇이 읽을 수 있습니다. Notion에서 페이지 우상단 `···` → `Connections` → 본인 integration 추가.

페이지 ID는 Notion 페이지 URL의 마지막 32자 (또는 하이픈 포함 36자):
```
https://www.notion.so/My-Page-344302d9c598818888888888d5041134fb3d
                              └─────────── page_id ───────────┘
```

### 3. 테스트

```bash
# LLM 호출 없이 어떤 페이지가 잡히는지 콘솔 출력만
python3 daily_notion_digest.py --no-llm --dry-run --hours 72

# LLM 요약까지 (Slack 전송 X)
python3 daily_notion_digest.py --dry-run --hours 72

# 실제 전송
python3 daily_notion_digest.py --hours 24
```

### 4. launchd 등록 (매일 자동 실행)

```bash
# 1. example을 본인용 plist로 복사하고 경로/Label 수정
cp com.example.notion-digest.plist com.YOUR_USERNAME.notion-digest.plist
# Label, ProgramArguments, WorkingDirectory, StandardOut/ErrorPath의
# YOUR_USERNAME을 본인 macOS username으로 치환

# 2. LaunchAgents에 설치 + 로드
cp com.YOUR_USERNAME.notion-digest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.YOUR_USERNAME.notion-digest.plist

# 3. 등록 확인
launchctl list | grep notion-digest

# 4. 즉시 1회 테스트 (학생/팀원들에게 알림 갈 수 있으니 신중히)
launchctl start com.YOUR_USERNAME.notion-digest
```

로그 확인:
```bash
tail -50 ~/Library/Logs/notion-digest/digest-$(date +%Y-%m-%d).log
```

## 옵션

```bash
python3 daily_notion_digest.py                  # 기본: state 파일 기반 cutoff, Slack 전송
python3 daily_notion_digest.py --dry-run        # Slack 전송 없이 콘솔 출력
python3 daily_notion_digest.py --no-llm         # LLM 요약 생략 (페이지 목록만 Slack 전송)
python3 daily_notion_digest.py --no-llm --dry-run  # 둘 다 (수집 결과만 콘솔 확인)
python3 daily_notion_digest.py --hours 48       # state 무시하고 직전 48시간 윈도우
```

## 운영 메모

- **state 파일** (`notion_digest_state.json`) — 직전 실행 시각 저장. 다음 실행은 그 이후 변경분만 처리해서 호출량 자동 절약
- **RPD 한도** — Gemini free tier가 초과되면 자동으로 fallback 메시지 + 페이지 목록만 전송 (알림 자체는 빠지지 않음)
- **자동 로그인** — macOS LaunchAgent는 사용자 세션에서 동작하므로, 무인 운영 시 자동 로그인이 켜져 있어야 재부팅 후 자동 복구

## 라이선스

MIT
