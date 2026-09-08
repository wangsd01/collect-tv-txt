#!/usr/bin/env python3
"""Create verified logo templates from a logo-reference-review.json export."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image


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
    by_file = {entry["file"]: entry for entry in existing}
    created = 0
    for review in payload["reviews"]:
        if review.get("verdict") != "correct_logo":
            continue
        channel, frame = review.get("channel", "").strip(), review.get("frame", "").strip()
        source = (frames_dir / frame).resolve()
        if source.parent != frames_dir or not source.is_file():
            raise ValueError("review frame is outside the capture directory or missing")
        token = hashlib.sha256(json.dumps([channel, frame, review["box"]]).encode()).hexdigest()[:12]
        relative = Path("logo_templates") / safe_channel_name(channel) / f"human-{token}.png"
        destination = config_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            crop_box = normalized_crop_box(review["box"], image.size)
            image.convert("RGB").crop(crop_box).save(destination)
        by_file[relative.as_posix()] = {
            "channel": channel, "file": relative.as_posix(),
            "source": f"人工框选自 {capture_dir / 'frames' / frame}", "verified": True,
        }
        created += 1
    return sorted(by_file.values(), key=lambda entry: (entry["channel"], entry["file"])), created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config/logo_templates.json"))
    args = parser.parse_args()
    payload = json.loads(args.review.read_text(encoding="utf-8"))
    updated, created = apply_logo_reviews(payload, args.capture_dir, args.config)
    args.config.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {created} verified logo templates in {args.config.parent / 'logo_templates'}")


if __name__ == "__main__":
    main()
