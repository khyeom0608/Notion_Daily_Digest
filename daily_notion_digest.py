"""
매일 아침 9시(KST)에 실행되어
연구실 프로젝트들의 '참고 논문 및 아이디어' 페이지에서 최근 추가/수정된
자식 페이지(논문/아이디어 정리)를 수집하고,
Gemini로 친근한 요약을 만들어 Slack #test_claude 채널에 보낸다.

사용법:
    python3 daily_notion_digest.py             # 정상 실행 (Slack 전송)
    python3 daily_notion_digest.py --dry-run   # Slack 전송 없이 콘솔 출력만
    python3 daily_notion_digest.py --hours 48  # 룩백 윈도우 변경 (기본 24h)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
KST = timezone(timedelta(hours=9))

GEMINI_MODEL = "gemini-2.5-flash-lite"
STATE_FILE = Path(__file__).parent / "notion_digest_state.json"
PROJECTS_FILE = Path(__file__).parent / "projects.json"
DEFAULT_LOOKBACK_HOURS = 24


def load_projects() -> list[tuple[str, str, str]]:
    """projects.json에서 (emoji, name, page_id) 튜플 리스트 로드."""
    if not PROJECTS_FILE.exists():
        sys.exit(f"{PROJECTS_FILE.name}이 없습니다. projects.json.example을 참고해 만드세요.")
    data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return [(p["emoji"], p["name"], p["page_id"]) for p in data]


PROJECTS: list[tuple[str, str, str]] = load_projects()


# ---------- Notion ----------

def notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def list_child_pages(parent_id: str, h: dict) -> list[dict]:
    """부모 페이지의 직계 child_page 블록만 페이지네이션으로 모두 가져온다."""
    out: list[dict] = []
    url = f"{NOTION_API}/blocks/{parent_id}/children?page_size=100"
    while True:
        r = requests.get(url, headers=h, timeout=30)
        r.raise_for_status()
        data = r.json()
        for b in data.get("results", []):
            if b.get("type") == "child_page":
                out.append(b)
        if not data.get("has_more"):
            break
        url = f"{NOTION_API}/blocks/{parent_id}/children?page_size=100&start_cursor={data['next_cursor']}"
    return out


def get_page_meta(page_id: str, h: dict) -> Optional[dict]:
    r = requests.get(f"{NOTION_API}/pages/{page_id}", headers=h, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def get_user_name(user_id: str, h: dict, cache: dict) -> str:
    if user_id in cache:
        return cache[user_id]
    r = requests.get(f"{NOTION_API}/users/{user_id}", headers=h, timeout=30)
    name = r.json().get("name", "?") if r.status_code == 200 else "?"
    cache[user_id] = name
    return name


def page_text_preview(page_id: str, h: dict, max_chars: int = 800) -> str:
    """페이지 본문 일부를 텍스트로 추출 (LLM 컨텍스트용)."""
    r = requests.get(
        f"{NOTION_API}/blocks/{page_id}/children?page_size=20",
        headers=h, timeout=30,
    )
    if r.status_code != 200:
        return ""
    parts: list[str] = []
    for b in r.json().get("results", []):
        t = b.get("type")
        if t in {"paragraph", "heading_1", "heading_2", "heading_3",
                 "bulleted_list_item", "numbered_list_item", "quote", "callout", "toggle"}:
            rich = b.get(t, {}).get("rich_text", [])
            text = "".join(x.get("plain_text", "") for x in rich)
            if text.strip():
                parts.append(text)
        elif t == "code":
            rich = b.get("code", {}).get("rich_text", [])
            parts.append("[code] " + "".join(x.get("plain_text", "") for x in rich)[:200])
        elif t == "child_page":
            parts.append(f"  · 하위 페이지: {b.get('child_page', {}).get('title', '')}")
        if sum(len(p) for p in parts) > max_chars:
            break
    return "\n".join(parts)[:max_chars]


# ---------- 수집 ----------

def collect_updates(cutoff: datetime, h: dict) -> dict[str, list[dict]]:
    """프로젝트별로 cutoff 이후 수정된 자식 페이지 목록을 모은다."""
    user_cache: dict[str, str] = {}
    by_project: dict[str, list[dict]] = {}

    for emoji, name, ref_id in PROJECTS:
        children = list_child_pages(ref_id, h)
        recent: list[dict] = []
        for c in children:
            child_id = c["id"]
            last_edited = c.get("last_edited_time")
            if not last_edited:
                continue
            edited_dt = datetime.fromisoformat(last_edited.replace("Z", "+00:00"))
            if edited_dt < cutoff:
                continue

            meta = get_page_meta(child_id, h)
            if meta is None:
                continue

            title = c.get("child_page", {}).get("title", "(제목 없음)")
            created = meta.get("created_time", "")
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
            is_new = created_dt is not None and created_dt >= cutoff

            editor_id = meta.get("last_edited_by", {}).get("id", "")
            creator_id = meta.get("created_by", {}).get("id", "")
            editor = get_user_name(editor_id, h, user_cache) if editor_id else ""
            creator = get_user_name(creator_id, h, user_cache) if creator_id else ""

            preview = page_text_preview(child_id, h)

            recent.append({
                "id": child_id,
                "title": title,
                "url": meta.get("url", ""),
                "is_new": is_new,
                "edited_at": edited_dt,
                "editor": editor,
                "creator": creator,
                "preview": preview,
            })
        if recent:
            recent.sort(key=lambda x: x["edited_at"], reverse=True)
            by_project[f"{emoji} {name}"] = recent
    return by_project


# ---------- LLM ----------

def _gemini_call_with_retry(client: genai.Client, prompt: str,
                            cfg: "genai_types.GenerateContentConfig") -> str:
    """503/429 일시 오류는 백오프하며 최대 4회 재시도. 그래도 실패하면 빈 문자열."""
    delays = [10, 30, 60, 120]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=cfg)
            return (resp.text or "").strip()
        except Exception as e:
            msg = str(e)
            transient = any(code in msg for code in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
            if attempt == len(delays) or not transient:
                print(f"  Gemini 호출 실패 (시도 {attempt}/{len(delays)}): {msg[:160]}")
                return ""
            print(f"  Gemini 일시 오류 (시도 {attempt}), {delay}s 대기 후 재시도")
            time.sleep(delay)
    return ""


SYSTEM_INSTRUCTION = """\
너는 우리 연구실의 각 프로젝트 노션 페이지에 있는 '참고 논문 및 아이디어'에
매일 추가·수정되는 내용을 정리해서 학생들에게 알려주는 비서야.

[말투 규칙 — 반드시 지킬 것]
- 항상 친근한 존댓말('~해요', '~네요', '~인 것 같아요')로 일관되게 답해.
- "얘들아", "안녕하세요!", "여러분!" 같은 인사말로 시작하지 마. 곧바로 본문으로 들어가.
- 이모지는 쓰지 마.
- 본인을 지칭하지 마 ("정리해 드릴게요" 같은 표현 금지). 사실만 담담히 짚어.

[내용 규칙]
- 어떤 내용이 추가/수정됐는지 핵심을 짚고, 학생들이 어떻게 활용할 수 있을지 함께 설명해.
- 페이지가 1~2편이면 자연스러운 산문 2~3문장으로 정리.
- 페이지가 3편 이상이면 항목별로 한 줄씩 정리하되, 각 줄에 (a) 핵심 내용, (b) 활용 포인트 모두 포함.
- 항목별 정리 시 형식: `- 저자/연도 — 한 줄 핵심. 활용 포인트.`
- 모든 추가된 페이지를 빠짐없이 다뤄 (중간에 끊지 마).

[Slack 형식 규칙 — 매우 중요]
- 굵은 글씨는 별표 한 개 (`*텍스트*`) — 두 개 별표(`**텍스트**`)는 절대 쓰지 마. Slack에서 굵게 표시되지 않아.
- 굵은 글씨는 핵심 키워드 1~3개에만 절제해서 사용.
- 마크다운 헤더(`#`)나 코드블록(```) 쓰지 마.
"""


def llm_summarize(updates: dict[str, list[dict]], client: genai.Client) -> dict[str, str]:
    """프로젝트별로 한 단락 친근한 요약을 만든다 (Gemini)."""
    summaries: dict[str, str] = {}
    cfg = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
        max_output_tokens=800,
    )
    for idx, (project, items) in enumerate(updates.items()):
        if idx > 0:
            # 무료 tier RPM/TPM 여유 확보용 — 호출 사이 15초 간격 (분당 4회 미만)
            time.sleep(15)
        bullet_lines = []
        for it in items:
            tag = "신규" if it["is_new"] else "수정"
            bullet_lines.append(
                f"- [{tag}] {it['title']}\n"
                f"  작성/수정: {it['editor'] or it['creator']}\n"
                f"  본문 미리보기:\n{it['preview'] or '(본문 미리보기 없음)'}"
            )
        prompt = (
            f"프로젝트: {project}\n\n"
            f"이 프로젝트의 '참고 논문 및 아이디어' 노션에 새로 추가되거나 수정된 페이지 목록:\n\n"
            f"{chr(10).join(bullet_lines)}\n\n"
            "위 지침대로 정리해줘."
        )
        text = _gemini_call_with_retry(client, prompt, cfg)
        summaries[project] = text or "_(요약 생성 실패 — 아래 페이지 목록을 직접 확인해주세요)_"
    return summaries


# ---------- Slack ----------

def build_slack_blocks(updates: dict[str, list[dict]],
                       summaries: dict[str, str],
                       window_start: datetime,
                       window_end: datetime) -> list[dict]:
    total = sum(len(v) for v in updates.values())
    header = (
        f"📚 오늘의 참고 논문 & 아이디어 업데이트 "
        f"({window_end.astimezone(KST).strftime('%Y-%m-%d (%a) %H:%M KST')})"
    )
    sub = (
        f"_{window_start.astimezone(KST).strftime('%m/%d %H:%M')} 부터 "
        f"{window_end.astimezone(KST).strftime('%m/%d %H:%M')} 까지 · 총 {total}건_"
    )

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": sub}]},
        {"type": "divider"},
    ]

    for project, items in updates.items():
        summary = summaries.get(project, "").strip()
        body_lines = [f"*{project}*"]
        if summary:
            body_lines.append(summary)
        for it in items:
            tag = "🆕" if it["is_new"] else "✏️"
            who = it["editor"] or it["creator"] or "?"
            link_title = it["title"].replace("|", "│")[:140]
            body_lines.append(f"  {tag} <{it['url']}|{link_title}> · _{who}_")
        text = "\n".join(body_lines)
        # Slack section text 한도 3000자
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}})
        blocks.append({"type": "divider"})

    return blocks


def post_to_slack(webhook_url: str, blocks: list[dict]) -> None:
    payload = {"blocks": blocks, "text": "오늘의 참고 논문 & 아이디어 업데이트"}
    r = requests.post(webhook_url, json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Slack webhook 실패 {r.status_code}: {r.text[:300]}")


# ---------- 상태 ----------

def load_last_run() -> Optional[datetime]:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return datetime.fromisoformat(data["last_run"])
    except Exception:
        return None


def save_last_run(when: datetime) -> None:
    STATE_FILE.write_text(json.dumps({"last_run": when.isoformat()}))


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Slack에 전송하지 않고 콘솔에만 출력")
    ap.add_argument("--hours", type=int, default=None, help=f"룩백 윈도우 (기본: state 파일, 없으면 {DEFAULT_LOOKBACK_HOURS}h)")
    ap.add_argument("--no-llm", action="store_true", help="LLM 요약 생략 (페이지 목록만). --dry-run 같이 주면 Slack 전송도 안 함")
    args = ap.parse_args()

    load_dotenv(Path(__file__).parent / ".env")
    notion_token = os.environ.get("NOTION_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not notion_token or not gemini_key or not webhook:
        sys.exit(".env에 NOTION_API_KEY / GEMINI_API_KEY / SLACK_WEBHOOK_URL 모두 필요합니다.")

    now = datetime.now(timezone.utc)
    if args.hours is not None:
        cutoff = now - timedelta(hours=args.hours)
    else:
        last = load_last_run()
        cutoff = last if last else (now - timedelta(hours=DEFAULT_LOOKBACK_HOURS))

    print(f"[{now.astimezone(KST):%Y-%m-%d %H:%M KST}] cutoff={cutoff.astimezone(KST):%Y-%m-%d %H:%M KST}")

    h = notion_headers(notion_token)
    t0 = time.time()
    updates = collect_updates(cutoff, h)
    n = sum(len(v) for v in updates.values())
    print(f"수집 완료: {n}건 / {len(updates)}개 프로젝트 ({time.time()-t0:.1f}s)")

    if n == 0:
        print("새 업데이트 없음 — Slack 전송 생략")
        if not args.dry_run:
            save_last_run(now)
        return 0

    if args.no_llm:
        summaries = {p: "" for p in updates}
    else:
        print("LLM 요약 생성 중...")
        client = genai.Client(api_key=gemini_key)
        summaries = llm_summarize(updates, client)

    blocks = build_slack_blocks(updates, summaries, cutoff, now)

    if args.dry_run:
        print("\n=== DRY RUN — Slack에 전송 안 함 ===\n")
        for project, items in updates.items():
            print(f"\n## {project}  ({len(items)}건)")
            summary = summaries.get(project, "").strip()
            if summary:
                print(summary)
            for it in items:
                tag = "🆕" if it["is_new"] else "✏️"
                print(f"  {tag} {it['title']}  · {it['editor'] or it['creator']}")
                print(f"     {it['url']}")
        return 0

    print(f"Slack 전송 중... (블록 {len(blocks)}개)")
    post_to_slack(webhook, blocks)
    save_last_run(now)
    print("완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
