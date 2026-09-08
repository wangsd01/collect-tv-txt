#!/usr/bin/env python3
"""Audit a published playlist and render failed stream evidence as HTML."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from my_tv_collect.stream_check import OK, check_stream_content, check_stream_quality, check_stream_tracks


REASON_LABELS = {
    "TIMEOUT": "连接或读取超时",
    "UNREACHABLE": "服务器拒绝连接",
    "DNS_ERROR": "域名解析失败",
    "FORBIDDEN": "服务器拒绝访问（HTTP 403）",
    "NOT_FOUND": "地址不存在（HTTP 404）",
    "CLIENT_ERROR": "HTTP 客户端错误",
    "SERVER_ERROR": "源服务器错误",
    "DECODE_ERROR": "视频无法解码",
    "UNKNOWN_ERROR": "未知连接或解码错误",
    "BLACK_SCREEN": "采样画面长时间黑屏",
    "FROZEN_VIDEO": "采样画面长时间定格",
    "CHOPPY": "解码速度过慢，可能卡顿",
    "NO_VIDEO_TRACK": "只有声音或数据轨，没有视频画面",
}


@dataclass
class AuditResult:
    channel: str
    url: str
    passed: bool
    reason: str
    speed: float
    screenshot: str | None = None


def read_entries(path: Path):
    entries = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        channel, separator, url = raw_line.partition(",")
        if separator and url.strip().startswith(("http://", "https://")):
            entries.append((channel.strip(), url.strip()))
    return entries


def audit_entry(entry, decode_seconds, content_seconds, connect_grace):
    channel, url = entry
    has_video, _has_audio, track_error = check_stream_tracks(
        url, connect_grace=connect_grace,
    )
    if not has_video:
        return AuditResult(channel, url, False, track_error, 0.0)
    choppy, speed, error = check_stream_quality(
        url, decode_seconds=decode_seconds, connect_grace=connect_grace, retries=0,
    )
    if error != OK:
        return AuditResult(channel, url, False, error, speed)
    if choppy:
        return AuditResult(channel, url, False, "CHOPPY", speed)
    acceptable, reason = check_stream_content(
        url, sample_seconds=content_seconds, connect_grace=connect_grace,
    )
    return AuditResult(channel, url, acceptable, reason, speed)


def capture_failure(result: AuditResult, screenshot_dir: Path, timeout):
    digest = hashlib.sha256(result.url.encode()).hexdigest()[:12]
    filename = f"{result.channel}-{digest}.jpg".replace("/", "_")
    destination = screenshot_dir / filename
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-user_agent", "collect-tv-txt/1.0", "-i", result.url,
        "-frames:v", "1", "-q:v", "3", "-y", str(destination),
    ]
    try:
        completed = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return result
    if completed.returncode == 0 and destination.exists():
        result.screenshot = f"screenshots/{filename}"
    return result


def render_report(path, source, results, started_at):
    failures = [result for result in results if not result.passed]
    rows = []
    for result in failures:
        if result.screenshot:
            evidence = (
                f'<a href="{html.escape(result.screenshot)}">'
                f'<img loading="lazy" src="{html.escape(result.screenshot)}"></a>'
            )
        else:
            evidence = '<span class="none">无法从该源取得画面</span>'
        reason = REASON_LABELS.get(result.reason, result.reason)
        if result.reason == "DECODE_ERROR" and result.screenshot:
            reason = "连续解码失败，但复查可提取单帧（疑似间歇性码流错误）"
        elif result.reason in {"NOT_FOUND", "UNREACHABLE", "TIMEOUT"} and result.screenshot:
            reason = f"{reason}；复查时可提取单帧，源状态不稳定"
        rows.append(
            "<tr>"
            f"<td>{html.escape(result.channel)}</td>"
            f"<td><code>{html.escape(result.url)}</code></td>"
            f"<td><strong>{html.escape(reason)}</strong><br><small>{html.escape(result.reason)}</small></td>"
            f"<td>{evidence}</td>"
            "</tr>"
        )
    body = "\n".join(rows) or '<tr><td colspan="4">本次没有检测失败的源。</td></tr>'
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>直播源审计报告</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;margin:24px;color:#222}} table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}} th{{background:#f3f3f3;position:sticky;top:0}}
img{{width:360px;max-width:100%;height:auto}} code{{word-break:break-all}} .none{{color:#777}}
</style></head><body>
<h1>直播源审计报告</h1>
<p>源文件：{html.escape(str(source))}<br>开始时间：{started_at:%Y-%m-%d %H:%M:%S}<br>
总计：{len(results)}，通过：{len(results)-len(failures)}，失败：{len(failures)}</p>
<p>注意：本报告自动判断连通性、解码速度、黑屏和定格；截图用于人工检查串台、错误画面和广告。</p>
<table><thead><tr><th>频道</th><th>URL</th><th>失败原因</th><th>截图</th></tr></thead><tbody>{body}</tbody></table>
</body></html>"""
    path.write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playlist", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--decode-seconds", type=float, default=4)
    parser.add_argument("--content-seconds", type=float, default=8)
    parser.add_argument("--connect-grace", type=float, default=5)
    args = parser.parse_args()

    started_at = datetime.now()
    entries = read_entries(args.playlist)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = args.output_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                audit_entry, entry, args.decode_seconds,
                args.content_seconds, args.connect_grace,
            )
            for entry in entries
        ]
        results = []
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(f"[{index}/{len(futures)}] {result.channel}: "
                  f"{'OK' if result.passed else result.reason}", flush=True)

    failures = [result for result in results if not result.passed]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, args.workers)) as pool:
        failures = list(pool.map(
            lambda result: capture_failure(
                result, screenshot_dir, args.content_seconds + args.connect_grace,
            ),
            failures,
        ))
    failure_by_url = {result.url: result for result in failures}
    results = [failure_by_url.get(result.url, result) for result in results]
    results.sort(key=lambda result: (result.passed, result.channel, result.url))
    render_report(args.output_dir / "report.html", args.playlist, results, started_at)
    print(f"Report: {args.output_dir / 'report.html'}")


if __name__ == "__main__":
    main()
