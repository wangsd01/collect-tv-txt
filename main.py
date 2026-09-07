"""Safe CCTV stream collector entry point.

The legacy script performed network work at import time, swallowed every
download error, and overwrote playlists even when no source succeeded.  The
implementation below keeps the pipeline bounded and publishes atomically.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import tempfile
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from my_tv_collect.stream_check import OK, check_stream_quality
from my_tv_collect.utils import convert_m3u_to_txt, standardize_channel_name

SOURCE_URLS = [
    "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt",
    "https://m3u.ibert.me/txt/fmml_ipv6.txt",
    "https://m3u.ibert.me/txt/ycl_iptv.txt",
    "https://m3u.ibert.me/txt/y_g.txt",
    "https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt",
    "https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt",
    "https://gitlab.com/p2v5/wangtv/-/raw/main/lunbo.txt",
    "https://gitlab.com/p2v5/wangtv/-/raw/main/wang-tvlive.txt",
    "https://raw.githubusercontent.com/iptv-org/iptv/refs/heads/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8",
    "https://raw.githubusercontent.com/zuomy2021/tv/refs/heads/main/iptv.txt",
    "https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8",
    "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/tv-ipv4-cmcc.m3u",
    # 山东省级及济南频道专项源（最近核验更新于 2026-07）
    "https://raw.githubusercontent.com/sggc/SDU-IPTV-PRO/main/SDM-Unicast.m3u",
    # 港澳台频道清单（公开 GitHub 源，内容为 M3U）
    "https://raw.githubusercontent.com/whherui/IPTV/main/%E5%8F%B0%E6%B9%BE%E9%A6%99%E6%B8%AF%E6%BE%B3%E9%97%A8.txt",
    "https://raw.githubusercontent.com/s14685/tv/main/iptvhk.txt",
]

HKTW_CHANNELS = {"凤凰香港", "凤凰香港台", "凤凰中文", "凤凰资讯", "凤凰资讯台", "翡翠台", "TVB翡翠台", "无线新闻台", "TVB新闻", "TVB News"}

SATELLITE_CHANNELS = {
    "浙江卫视", "北京卫视", "东方卫视",
    "江苏卫视", "湖南卫视", "山东卫视",
}

# Keep common current and legacy source names: public playlists are not
# consistent about including the province/city prefix or the latest callsign.
SHANDONG_CHANNELS = {
    "山东齐鲁", "齐鲁", "齐鲁频道",
    "山东新闻", "山东文旅", "山东影视",
    "山东综艺", "山东生活", "山东体育休闲", "山东体育",
    "山东农科", "山东少儿", "山东公共", "山东教育",
    "山东国际", "山东读书",
}
JINAN_CHANNELS = {
    "济南新闻综合", "济南综合",
    "济南都市", "济南经济生活", "济南生活",
    "济南影视", "济南文化娱乐", "济南娱乐",
    "济南文旅体育", "济南体育休闲",
    "济南公共", "济南移动", "济南科教", "济南图文",
}
SELECTED_LOCAL_CHANNELS = SHANDONG_CHANNELS | JINAN_CHANNELS

def fetch_source(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "collect-tv-txt/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")

def source_lines(text):
    if "#EXTINF" in text:
        text = convert_m3u_to_txt(text)
    return [line.strip() for line in text.splitlines() if line.strip()]

def parse_channels(texts, satellite_channels=SATELLITE_CHANNELS,
                   local_channels=SELECTED_LOCAL_CHANNELS):
    channels, seen = defaultdict(list), defaultdict(set)
    for text in texts:
        for line in source_lines(text):
            if "#genre#" in line or "," not in line or "://" not in line:
                continue
            raw_name, url = (part.strip() for part in line.split(",", 1))
            name, url = standardize_channel_name(raw_name), url.split("$", 1)[0].strip()
            if (name.startswith("CCTV") or name in HKTW_CHANNELS or
                    name in satellite_channels or name in local_channels) and url and url not in seen[name]:
                seen[name].add(url); channels[name].append(url)
    return dict(channels)


def parse_cctv_channels(texts):
    """Backward-compatible name for consumers of the original parser."""
    return parse_channels(texts, satellite_channels=set(), local_channels=set())

def validate_stream(url, decode_seconds, connect_grace):
    choppy, speed, error = check_stream_quality(url, decode_seconds=decode_seconds,
                                                  connect_grace=connect_grace, retries=0)
    return url, not choppy and error == OK, speed

def stable_channels(channels, max_candidates=30, max_streams=10, workers=24,
                    decode_seconds=3, connect_grace=3):
    candidates = [(name, url) for name, urls in channels.items()
                  for url in urls[:max_candidates]]
    stable = defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(candidates)) or 1) as pool:
        futures = {pool.submit(validate_stream, url, decode_seconds, connect_grace): name
                   for name, url in candidates}
        for future in concurrent.futures.as_completed(futures):
            try:
                url, valid, speed = future.result()
            except Exception as exc:
                print(f"stream check failed: {exc}"); continue
            if valid: stable[futures[future]].append((speed, url))
    return {name: [url for _, url in sorted(items, reverse=True)[:max_streams]]
            for name, items in stable.items() if items}

def render_outputs(channels, timestamp=None):
    timestamp = timestamp or datetime.now()
    txt = ["更新时间,#genre#", f"{timestamp:%Y%m%d-%H-%M-%S},url"]
    m3u = ["#EXTM3U"]
    def key(name):
        suffix = name[4:]
        return (int(suffix) if suffix.isdigit() else (6 if suffix == "5+" else 10000), name)
    cctv = sorted((name for name in channels if name.startswith("CCTV")), key=key)
    hktw = sorted((name for name in channels if name in HKTW_CHANNELS), key=key)
    satellite = sorted(name for name in channels if name in SATELLITE_CHANNELS)
    shandong = sorted(name for name in channels if name in SHANDONG_CHANNELS)
    jinan = sorted(name for name in channels if name in JINAN_CHANNELS)
    grouped_names = [
        ("央视频道", cctv), ("卫视频道", satellite),
        ("山东频道", shandong), ("济南频道", jinan), ("港澳台", hktw),
    ]
    for group, names in grouped_names:
        if not names:
            continue
        txt.append(""); txt.append(f"{group},#genre#")
        for name in names:
            for url in channels[name]:
                txt.append(f"{name},{url}")
                m3u.extend((f'#EXTINF:-1 group-title="{group}",{name}', url))
    return "\n".join(txt) + "\n", "\n".join(m3u) + "\n"

def atomic_write(path, content):
    path = Path(path).resolve(); fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise

def collect(args):
    texts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.source_workers, len(SOURCE_URLS))) as pool:
        futures = {pool.submit(fetch_source, url, args.source_timeout): url for url in SOURCE_URLS}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                text = future.result()
                if text.strip(): texts.append(text); print(f"fetched {url}")
                else: print(f"ignored empty source: {url}")
            except Exception as exc: print(f"source failed: {url}: {exc}")
    if not texts: raise RuntimeError("all source downloads failed; existing output was preserved")
    channels = parse_channels(texts)
    if not channels: raise RuntimeError("sources contained no selected streams; existing output was preserved")
    result = stable_channels(channels, args.max_candidates, args.max_streams, args.stream_workers,
                             args.decode_seconds, args.connect_grace)
    if not result: raise RuntimeError("no stable selected streams found; existing output was preserved")
    return result

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-timeout", type=float, default=10); parser.add_argument("--source-workers", type=int, default=12)
    parser.add_argument("--stream-workers", type=int, default=24); parser.add_argument("--decode-seconds", type=float, default=3)
    parser.add_argument("--connect-grace", type=float, default=3); parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--max-streams", type=int, default=10); parser.add_argument("--output-txt", type=Path, default=Path("merged_output.txt"))
    parser.add_argument("--output-m3u", type=Path, default=Path("merged_output.m3u")); args = parser.parse_args(argv)
    try:
        channels = collect(args); txt, m3u = render_outputs(channels)
        atomic_write(args.output_txt, txt)
        atomic_write(args.output_m3u, m3u)
        # Keep the historical consumer path in sync with the published result.
        atomic_write(Path("my_tv_collect") / "my_itvlist.m3u", m3u)
        # Keep the dated collector playlist in sync for consumers of the
        # my_tv_collect directory.  This path is intentionally the spelling
        # requested by the project output contract.
        atomic_write(Path("my_tv_collect") / "my_itelist.m3u", m3u)
    except (RuntimeError, ValueError) as exc:
        print(f"Collection failed: {exc}"); return 1
    print(f"Published {sum(map(len, channels.values()))} stable streams across {len(channels)} channels"); return 0

if __name__ == "__main__":
    raise SystemExit(main())
