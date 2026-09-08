#!/usr/bin/env python3
"""Create verified logo templates from a logo-reference-review.json export."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

from my_tv_collect.utils import standardize_channel_name


def normalized_crop_box(box, size):
    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(value, (int, float)) for value in box):
        raise ValueError("logo review has an invalid crop box")
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1) or x2 - x1 < .02 or y2 - y1 < .02:
        raise ValueError("logo crop box is empty, too small, or outside the image")
    width, height = size
    return round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height)


def safe_channel_name(channel):
    value = re.sub(r"[^\w.-]+", "_", channel, flags=re.UNICODE).strip("._")
    if not value:
        raise ValueError("invalid channel name")
    return value


def apply_logo_reviews(payload, capture_dir: Path, config_path: Path) -> tuple[list[dict], int]:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("reviews"), list):
        raise ValueError("not a schema_version 1 logo review export")
    frames_dir = (capture_dir / "frames").resolve()
    config_dir = config_path.parent.resolve()
    existing = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else []
    for entry in existing:
        entry["channel"] = standardize_channel_name(entry["channel"])
    by_file = {entry["file"]: entry for entry in existing}
    created = 0
    for review in payload["reviews"]:
        if review.get("verdict") != "correct_logo":
            continue
        channel = standardize_channel_name(review.get("channel", "").strip())
        frame = review.get("frame", "").strip()
        source = (frames_dir / frame).resolve()
        if source.parent != frames_dir or not source.is_file():
            raise ValueError("review frame is outside the capture directory or missing")
        source_label = f"人工框选自 {capture_dir / 'frames' / frame}"
        prior = next((entry for entry in by_file.values() if entry.get("source") == source_label), None)
        if prior:
            prior["channel"] = channel
            continue
        token = hashlib.sha256(json.dumps([channel, frame, review["box"]]).encode()).hexdigest()[:12]
        relative = Path("logo_templates") / safe_channel_name(channel) / f"human-{token}.png"
        destination = config_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            crop_box = normalized_crop_box(review["box"], image.size)
            image.convert("RGB").crop(crop_box).save(destination)
        by_file[relative.as_posix()] = {
            "channel": channel, "file": relative.as_posix(),
            "source": source_label, "verified": True,
        }
        created += 1
    return sorted(by_file.values(), key=lambda entry: (entry["channel"], entry["file"])), created


def apply_wrong_logo_reviews(payload, existing: list[dict], review_source: str):
    """Turn explicit human wrong-logo verdicts into stream rejection rules."""
    by_key = {(entry["channel"], entry["url"]): entry for entry in existing}
    applied = 0
    for review in payload["reviews"]:
        if review.get("verdict") != "wrong_logo":
            continue
        channel = standardize_channel_name(review.get("channel", "").strip())
        url = review.get("url", "").strip()
        if not channel or not url.startswith(("http://", "https://")):
            raise ValueError("wrong-logo review has an invalid channel or URL")
        by_key[(channel, url)] = {
            "channel": channel, "url": url, "decision": "reject",
            "reason": "人工台标审核：画面台标与频道名称不符",
            "reviewed_at": review.get("reviewed_at"), "review_source": review_source,
        }
        applied += 1
    return sorted(by_key.values(), key=lambda entry: (entry["channel"], entry["url"])), applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/logo_templates.json"))
    parser.add_argument("--overrides", type=Path, default=Path("config/stream_overrides.json"))
    args = parser.parse_args()
    payload = json.loads(args.review.read_text(encoding="utf-8"))
    updated, created = apply_logo_reviews(payload, args.capture_dir, args.config)
    args.config.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides.exists() else []
    overrides, rejected = apply_wrong_logo_reviews(payload, overrides, str(args.review))
    args.overrides.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {created} verified logo templates; added {rejected} wrong-logo rejection rules")


if __name__ == "__main__":
    main()
