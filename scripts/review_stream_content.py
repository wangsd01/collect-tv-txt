#!/usr/bin/env python3
"""Reconnect to live streams across real-time rounds and save evidence."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


@dataclass
class ReviewItem:
    channel: str
    url: str
    frames: list[str] = field(default_factory=list)
    logo_crops: dict[str, list[str]] = field(default_factory=dict)
    captured_at: list[str] = field(default_factory=list)
    error: str = ""
    decision: str = ""
    reason: str = ""
    logo_result: str = ""


def read_entries(path):
    found, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        channel, separator, url = line.partition(",")
        entry = channel.strip(), url.strip()
        if separator and entry[1].startswith(("http://", "https://")) and entry not in seen:
            found.append(entry); seen.add(entry)
    return found


def read_overrides(path):
    if not path.exists(): return {}
    return {(e["channel"], e["url"]): e for e in json.loads(path.read_text(encoding="utf-8"))}


def valid_image(path):
    try:
        with Image.open(path) as image: image.verify()
        return True
    except (OSError, ValueError): return False


def logo_crop_boxes(size):
    """Return generously sized crops for the four usual on-screen logo areas."""
    width, height = size
    crop_width, crop_height = max(1, round(width * .36)), max(1, round(height * .32))
    return {
        "左上": (0, 0, crop_width, crop_height),
        "右上": (width - crop_width, 0, width, crop_height),
        "左下": (0, height - crop_height, crop_width, height),
        "右下": (width - crop_width, height - crop_height, width, height),
    }


def extract_logo_crops(source, destination_dir):
    """Save visual evidence; this does not make an automatic identity claim."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    result = []
    with Image.open(source) as image:
        image = image.convert("RGB")
        for label, box in logo_crop_boxes(image.size).items():
            filename = f"{source.stem}-{label}.jpg"
            image.crop(box).save(destination_dir / filename, quality=90)
            result.append(filename)
    return result


def capture_round(entry, frames, logo_crops, number, timeout):
    channel, url = entry
    token = hashlib.sha256(f"{channel}\0{url}".encode()).hexdigest()[:12]
    filename = f"{channel}-{token}-round-{number}.jpg".replace("/", "_")
    destination = frames / filename
    if destination.exists(): raise RuntimeError(f"evidence file exists: {destination}")
    at = datetime.now(timezone.utc).isoformat()
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if urlparse(url).scheme in {"http", "https"}: command.extend(("-user_agent", "collect-tv-txt/1.0"))
    command.extend(("-i", url, "-map", "0:v:0", "-frames:v", "1", "-q:v", "4", "-y", str(destination)))
    try: result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired: return None, [], at, "截图超时"
    if result.returncode or not valid_image(destination):
        if destination.exists(): destination.unlink()
        return None, [], at, result.stderr.decode("utf-8", errors="replace").strip()[-250:] or "无法取得可用视频帧"
    try:
        crops = extract_logo_crops(destination, logo_crops)
    except OSError as exc:
        return filename, [], at, f"台标区域裁剪失败：{exc}"
    return filename, crops, at, ""


def card(item):
    images = "".join(f'<a href="frames/{html.escape(frame)}"><img loading="lazy" src="frames/{html.escape(frame)}"></a>' for frame in item.frames) or '<span class="missing">没有取得截图</span>'
    logo_evidence = "".join(
        '<details class="logos"><summary>台标区域（四角）</summary><div class="crops">' +
        ''.join(f'<a href="logo-crops/{html.escape(crop)}"><img loading="lazy" src="logo-crops/{html.escape(crop)}"></a>' for crop in item.logo_crops.get(frame, [])) +
        '</div></details>' for frame in item.frames if item.logo_crops.get(frame)
    )
    timestamps = "<br>".join(html.escape(value) for value in item.captured_at)
    prior = f'<p class="manual">已有人工规则：<strong>{html.escape(item.decision)}</strong> — {html.escape(item.reason)}</p>' if item.decision else ""
    error = f'<p class="error">{html.escape(item.error)}</p>' if item.error else ""
    logo_result = f'<p class="logo-result">{html.escape(item.logo_result)}</p>' if item.logo_result else ""
    return f'<section class="card"><h2>{html.escape(item.channel)}</h2><code>{html.escape(item.url)}</code><p><small>UTC：{timestamps}</small></p>{prior}{logo_result}{error}<div class="frames">{images}</div>{logo_evidence}</section>'


def page(title, intro, items):
    ui = Path(__file__).with_name("review_ui.html").read_text(encoding="utf-8")
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{html.escape(title)}</title><style>body{{font:15px/1.5 system-ui,sans-serif;margin:24px;color:#222}}code{{word-break:break-all}}.card{{border:1px solid #ccc;border-radius:8px;padding:12px;margin:16px 0}}h2{{margin:0}}.frames,.crops{{display:flex;gap:8px;overflow:auto}}.frames img{{width:320px;height:180px;object-fit:contain;background:#111}}.logos{{margin-top:8px}}.crops img{{width:180px;height:100px;object-fit:contain;background:#111}}.logo-result,.manual{{color:#075b24}}.error{{color:#a11}}.missing{{color:#777}}</style><body><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p>{''.join(card(item) for item in items)}{ui}</body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playlist", type=Path); parser.add_argument("output_dir", type=Path)
    parser.add_argument("--overrides", type=Path, default=Path("config/stream_overrides.json")); parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--channel", action="append", help="capture only this exact channel; repeatable")
    parser.add_argument("--round-delays", default="0,60,180"); parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(); delays = [int(value) for value in args.round_delays.split(",")]
    if delays != sorted(set(delays)) or not delays or delays[0] != 0: raise ValueError("round delays must be unique, ascending, and start with 0")
    if args.output_dir.exists(): raise ValueError(f"output directory exists: {args.output_dir}")
    frames = args.output_dir / "frames"; frames.mkdir(parents=True); logo_crops = args.output_dir / "logo-crops"; entries = read_entries(args.playlist); overrides = read_overrides(args.overrides)
    if args.channel:
        entries = [entry for entry in entries if entry[0] in set(args.channel)]
    if not entries:
        raise ValueError("playlist has no matching stream entries")
    items = {entry: ReviewItem(*entry, decision=overrides.get(entry,{}).get("decision",""), reason=overrides.get(entry,{}).get("reason","")) for entry in entries}
    started = time.monotonic()
    for number, delay in enumerate(delays, 1):
        wait = delay - (time.monotonic() - started)
        if wait > 0: time.sleep(wait)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(capture_round, entry, frames, logo_crops, number, args.timeout): entry for entry in entries}
            for future in concurrent.futures.as_completed(futures):
                entry = futures[future]; frame, crops, at, error = future.result(); item = items[entry]; item.captured_at.append(at)
                if frame:
                    item.frames.append(frame)
                    item.logo_crops[frame] = crops
                if error: item.error = "; ".join(filter(None, [item.error, f"round {number}: {error}"]))
    ordered = sorted(items.values(), key=lambda item: (item.channel, item.url))
    (args.output_dir / "manifest.json").write_text(json.dumps({"schema_version":2,"round_delays_seconds":delays,"items":[asdict(item) for item in ordered]},ensure_ascii=False,indent=2),encoding="utf-8")
    intro = "每轮均重新连接，记录实际 UTC 采样时间。展开“台标区域”可检查四角；台标证据仍由人工判断。已有规则只是历史信息，新画面仍可重新审核。"
    (args.output_dir / "gallery.html").write_text(page("直播源真实时间截图",intro,ordered),encoding="utf-8")
    (args.output_dir / "needs-review.html").write_text(page("待人工确认","本页只列无法完整取证的源。内容证据由分析报告提供。",[item for item in ordered if item.error]),encoding="utf-8")
    print(args.output_dir / "gallery.html")


if __name__ == "__main__": main()
