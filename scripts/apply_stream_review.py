#!/usr/bin/env python3
"""Apply exported HTML stream-review.json decisions to manual overrides.

This changes only config/stream_overrides.json.  Run the normal collection
afterward to regenerate published playlists from the new rules.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


VERDICT_TO_DECISION = {
    "wrong_channel": "reject",
    "mixed_content": "reject",
    "audio_only": "reject",
    "signal_lost": "quarantine",
    "off_air": "allow_if_frame",
}

DEFAULT_REASONS = {
    "wrong_channel": "人工 HTML 审核：错台／冒充频道的广告",
    "mixed_content": "人工 HTML 审核：多次取样发现内容会切换；不可靠源",
    "audio_only": "人工 HTML 审核：只有声音、没有视频画面",
    "signal_lost": "人工 HTML 审核：信号失效，暂时隔离",
    "off_air": "人工 HTML 审核：频道正确但停播测试卡，可发布",
}


def load_entries(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def apply_reviews(existing: list[dict], reviews: list[dict], review_source: str) -> tuple[list[dict], int]:
    """Return overrides with actionable human verdicts merged by channel + URL."""
    by_key = {(entry["channel"], entry["url"]): entry for entry in existing}
    applied = 0
    for review in reviews:
        verdict = review.get("verdict")
        decision = VERDICT_TO_DECISION.get(verdict)
        if not decision:
            continue
        channel, url = review.get("channel", "").strip(), review.get("url", "").strip()
        if not channel or not url.startswith(("http://", "https://")):
            raise ValueError("review has an invalid channel or URL")
        note = review.get("note", "").strip()
        by_key[(channel, url)] = {
            "channel": channel,
            "url": url,
            "decision": decision,
            "reason": note or DEFAULT_REASONS[verdict],
            "reviewed_at": review.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
            "review_source": review_source,
        }
        applied += 1
    return sorted(by_key.values(), key=lambda entry: (entry["channel"], entry["url"])), applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="JSON exported from review_ui.html")
    parser.add_argument("--overrides", type=Path, default=Path("config/stream_overrides.json"))
    args = parser.parse_args()
    payload = json.loads(args.review.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("reviews"), list):
        raise ValueError("not a schema_version 1 stream review export")
    updated, applied = apply_reviews(load_entries(args.overrides), payload["reviews"], str(args.review))
    args.overrides.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Applied {applied} actionable reviews to {args.overrides}. Run main.py to regenerate playlists.")


if __name__ == "__main__":
    main()
