"""Offline, advisory-only OCR and visual evidence for captured streams."""
import argparse
import json
import subprocess
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from my_tv_collect.logo_match import load_logo_library, match_logo_candidates, summarize_logo_matches
try:  # Supports both `python -m scripts...` and direct script execution.
    from scripts.review_stream_content import ReviewItem, card, page, read_overrides
except ModuleNotFoundError:
    from review_stream_content import ReviewItem, card, page, read_overrides

LOCAL_TESSDATA = PROJECT_ROOT / "tools" / "tessdata"


def fingerprint(path):
    with Image.open(path) as image:
        thumbnail = image.convert('RGB').resize((9, 8))
        pixels = list(thumbnail.convert('L').get_flattened_data())
        colours = list(thumbnail.get_flattened_data())
    return {
        "dhash": sum((pixels[y*9+x] > pixels[y*9+x+1]) << (y*8+x)
                     for y in range(8) for x in range(8)),
        "mean_rgb": [round(sum(pixel[index] for pixel in colours) / len(colours), 1)
                     for index in range(3)],
    }


def frame_round(frame):
    return frame.rsplit("-round-", 1)[-1].split(".", 1)[0]


def visually_similar(first, second):
    """Conservative candidate match; still not a content identity claim."""
    return ((first["hash"]["dhash"] ^ second["hash"]["dhash"]).bit_count() <= 5
            and sum(abs(a - b) for a, b in zip(first["hash"]["mean_rgb"], second["hash"]["mean_rgb"])) <= 24)
def text_flags(text):
    compact = re.sub(r'\s+', '', text).lower()
    lost = [word for word in ('nosignal', 'signalwas', '信号中断', '訊號', '信号失效') if word in compact]
    ads = [word for word in ('抢购', '订购', '訂購', '热线', '熱線', '名额有限', '名額有限') if word in compact]
    return lost, ads


def available_ocr_languages():
    system = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                            text=True, check=True).stdout.splitlines()
    local = [language for language in ("chi_sim", "chi_tra")
             if (LOCAL_TESSDATA / f"{language}.traineddata").exists()]
    return (["eng"] if "eng" in system else []) + local


def ocr_image(path, languages):
    texts = []
    if "eng" in languages:
        result = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng", "--psm", "11"],
                                capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            texts.append(result.stdout)
    chinese = [language for language in languages if language.startswith("chi_")]
    if chinese:
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "--tessdata-dir", str(LOCAL_TESSDATA),
             "-l", "+".join(chinese), "--psm", "11"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            texts.append(result.stdout)
    return "\n".join(texts), bool(texts)


def analyze(source, output):
    output.mkdir(parents=True, exist_ok=False)
    import shutil
    shutil.copytree(source/'frames', output/'frames')
    if (source / 'logo-crops').exists():
        shutil.copytree(source / 'logo-crops', output / 'logo-crops')
    manifest = json.loads((source/'manifest.json').read_text())
    languages = available_ocr_languages()
    if not languages:
        raise RuntimeError('No supported Tesseract language installed')
    overrides = read_overrides(PROJECT_ROOT / 'config' / 'stream_overrides.json')
    logo_library = load_logo_library(PROJECT_ROOT / 'config' / 'logo_templates.json')
    items, records = [], []
    for entry in manifest['items']:
        item = ReviewItem(**entry)
        override = overrides.get((item.channel,item.url),{})
        item.decision, item.reason = override.get('decision',''), override.get('reason','')
        evidence = []
        frame_logo_matches = []
        for frame in item.frames:
            path = output/'frames'/frame
            try:
                text, ocr_ok = ocr_image(path, languages)
                lost, ads = text_flags(text) if ocr_ok else ([], [])
                logo_matches = match_logo_candidates(path, logo_library)
                frame_logo_matches.append(logo_matches)
                evidence.append(dict(frame=frame, hash=fingerprint(path), text=text, lost=lost,
                                     ads=ads, ocr_ok=ocr_ok, logo_matches=logo_matches))
            except (OSError, subprocess.TimeoutExpired) as exc:
                evidence.append(dict(frame=frame,error=str(exc)))
                frame_logo_matches.append([])
        item.logo_result, logo_warning = summarize_logo_matches(item.channel, frame_logo_matches)
        if logo_warning:
            item.error = '; '.join(filter(None, [item.error, logo_warning]))
        items.append(item);records.append(evidence)
        print(f'{len(items)}/{len(manifest["items"])} {item.channel}',flush=True)
    for i,item in enumerate(items):
        frames = records[i]
        reasons = []
        if sum(bool(f.get('lost')) for f in frames)>=2:
            reasons.append('多个画面出现信号提示文字，需区分失效页和节目字幕')
        if sum(bool(f.get('ads')) for f in frames)>=2:
            reasons.append('多个画面出现推销文字（也可能是频道正常广告）')
        peers=[]
        for j,other in enumerate(items):
            if i==j or item.channel==other.channel or item.url==other.url:
                continue
            matched_rounds = [
                frame_round(a["frame"]) for a in frames if "hash" in a and any(
                    frame_round(a["frame"]) == frame_round(b["frame"]) and visually_similar(a, b)
                    for b in records[j] if "hash" in b
                )
            ]
            if len(matched_rounds) >= 2:
                peers.append(other.channel + " " + other.url + "（轮次 " + ", ".join(matched_rounds) + "）")
        if peers:
            reasons.append('至少两轮与其他频道同轮画面近似；可能是共用/错配内容，需人工核对：'+'；'.join(peers))
        if any(not f.get('ocr_ok',False) for f in frames):
            reasons.append('部分 OCR 未完成')
        if reasons:
            item.error='；'.join(filter(None,[item.error,*reasons]))
    intro='仅为人工审核候选，不自动更改发布。OCR语言：'+'+'.join(languages)+'。近似阈值为试验值；未识别台标，未证明来源独立。'
    (output/'gallery.html').write_text(page('内容证据画廊',intro,items), encoding="utf-8")
    pending=[i for i in items if i.error]
    (output/'needs-review.html').write_text(page('待人工确认',intro,pending), encoding="utf-8")
    (output/'evidence.json').write_text(json.dumps({'source':str(source),'ocr_languages':languages,'items':[{'channel':i.channel,'url':i.url,'reason':i.error,'frames':r} for i,r in zip(items,records)]},ensure_ascii=False,indent=2))
    print(f'Review: {output}/needs-review.html ({len(pending)})')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();analyze(args.source,args.output)
