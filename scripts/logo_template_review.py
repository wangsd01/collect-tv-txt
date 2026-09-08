#!/usr/bin/env python3
"""Build an interactive page for selecting verified logo templates."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image


def frame_signature(path: Path):
    with Image.open(path) as image:
        thumbnail = image.convert("RGB").resize((9, 8))
        grey = list(thumbnail.convert("L").get_flattened_data())
        colours = list(thumbnail.get_flattened_data())
    return {
        "dhash": sum((grey[y * 9 + x] > grey[y * 9 + x + 1]) << (y * 8 + x)
                     for y in range(8) for x in range(8)),
        "mean_rgb": [sum(pixel[index] for pixel in colours) / len(colours) for index in range(3)],
    }


def similar_frames(first, second, hash_distance=8, colour_distance=30):
    return ((first["dhash"] ^ second["dhash"]).bit_count() <= hash_distance and
            sum(abs(a - b) for a, b in zip(first["mean_rgb"], second["mean_rgb"])) <= colour_distance)


def select_diverse_frames(manifest, capture_dir: Path):
    """Greedily keep one representative for synchronized/near-duplicate frames per channel."""
    representatives = []
    for item in manifest["items"]:
        captured = item.get("captured_at", [])
        for index, frame in enumerate(item.get("frames", [])):
            signature = frame_signature(capture_dir / "frames" / frame)
            duplicate = next((record for record in representatives
                              if record["channel"] == item["channel"] and
                              similar_frames(record["signature"], signature)), None)
            if duplicate:
                duplicate["duplicate_count"] += 1
                duplicate["duplicate_urls"].add(item["url"])
                continue
            representatives.append({
                "channel": item["channel"], "url": item["url"], "frame": frame,
                "captured_at": captured[index] if index < len(captured) else "",
                "signature": signature, "duplicate_count": 1, "duplicate_urls": {item["url"]},
            })
    return representatives


def build_page(capture_dir: Path) -> str:
    manifest = json.loads((capture_dir / "manifest.json").read_text(encoding="utf-8"))
    cards = []
    representatives = select_diverse_frames(manifest, capture_dir)
    total_frames = sum(len(item.get("frames", [])) for item in manifest["items"])
    for record in representatives:
        duplicate_note = (f' · 代表 {record["duplicate_count"]} 张近似截图／'
                          f'{len(record["duplicate_urls"])} 个 URL')
        cards.append(
            f'<section class="card" data-channel="{html.escape(record["channel"])}" '
            f'data-url="{html.escape(record["url"])}" data-frame="{html.escape(record["frame"])}">'
            f'<h2>{html.escape(record["channel"])}</h2><code>{html.escape(record["url"])}</code>'
            f'<p><small>UTC：{html.escape(record["captured_at"])} · {html.escape(record["frame"])}'
            f'{html.escape(duplicate_note)}</small></p>'
            f'<div class="image-wrap"><img draggable="false" src="frames/{html.escape(record["frame"])}">'
            '<div class="selection"></div></div><p class="coords">尚未框选台标</p>'
            '<label>结论：<select><option value="">待确认</option>'
            '<option value="correct_logo">台标正确，加入参考库</option>'
            '<option value="wrong_logo">台标不对</option>'
            '<option value="no_logo">无台标／看不清</option>'
            '<option value="uncertain">仍不确定</option></select></label></section>'
        )
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>台标模板审核</title><style>
body{{font:15px/1.5 system-ui,sans-serif;margin:24px;color:#222}}code{{word-break:break-all}}
.card{{border:1px solid #bbb;border-radius:8px;padding:12px;margin:16px 0}}.reviewed{{border-color:#267045}}
.image-wrap{{position:relative;display:inline-block;max-width:100%;cursor:crosshair;background:#111}}
.image-wrap img{{display:block;max-width:720px;width:100%;height:auto;user-select:none}}
.selection{{display:none;position:absolute;border:3px solid #ff3b30;background:#ff3b3022;pointer-events:none;box-sizing:border-box}}
select,button{{font:inherit;padding:8px}}.toolbar{{position:sticky;bottom:0;background:#fff;padding:14px;border:2px solid #267045}}
</style><body><h1>台标模板审核</h1>
<p>在完整画面上拖框，只圈住目标频道台标，再选择“台标正确”。不要把节目标题、字幕或背景一起圈入。</p>
<p>已将 {total_frames} 张截图按画面相似度去重为 {len(representatives)} 张代表图；同步转播不会重复贡献模板。</p>
{''.join(cards)}
<div class="toolbar"><button id="export">导出台标审核 JSON</button> <span id="progress"></span>
<br><small>这里只建立台标参考库，不修改播放列表。错台、无台标和不确定项不会成为模板。</small></div>
<script>(()=>{{
const key='collect-tv-logo-review-v1:'+location.pathname;let saved={{}};
try{{saved=JSON.parse(localStorage.getItem(key)||'{{}}')}}catch(_){{}}
const clamp=n=>Math.max(0,Math.min(1,n));
const cards=[...document.querySelectorAll('.card')].map(card=>{{
 const img=card.querySelector('img'),wrap=card.querySelector('.image-wrap'),box=card.querySelector('.selection');
 const select=card.querySelector('select'),coords=card.querySelector('.coords');
 const id=JSON.stringify([card.dataset.channel,card.dataset.url,card.dataset.frame]);let start=null;
 const draw=b=>{{if(!b)return;box.style.display='block';box.style.left=(b[0]*100)+'%';box.style.top=(b[1]*100)+'%';box.style.width=((b[2]-b[0])*100)+'%';box.style.height=((b[3]-b[1])*100)+'%';coords.textContent='框选：'+b.map(n=>n.toFixed(4)).join(', ')}};
 if(saved[id]){{select.value=saved[id].verdict;draw(saved[id].box)}}
 const point=e=>{{const r=img.getBoundingClientRect();return [clamp((e.clientX-r.left)/r.width),clamp((e.clientY-r.top)/r.height)]}};
 wrap.addEventListener('pointerdown',e=>{{start=point(e);wrap.setPointerCapture(e.pointerId)}});
 wrap.addEventListener('pointermove',e=>{{if(!start)return;const p=point(e),b=[Math.min(start[0],p[0]),Math.min(start[1],p[1]),Math.max(start[0],p[0]),Math.max(start[1],p[1])];draw(b)}});
 wrap.addEventListener('pointerup',e=>{{if(!start)return;const p=point(e),b=[Math.min(start[0],p[0]),Math.min(start[1],p[1]),Math.max(start[0],p[0]),Math.max(start[1],p[1])];start=null;saved[id]={{...(saved[id]||{{}}),channel:card.dataset.channel,url:card.dataset.url,frame:card.dataset.frame,box:b,reviewed_at:new Date().toISOString()}};localStorage.setItem(key,JSON.stringify(saved));draw(b);refresh()}});
 select.addEventListener('change',()=>{{saved[id]={{...(saved[id]||{{}}),channel:card.dataset.channel,url:card.dataset.url,frame:card.dataset.frame,verdict:select.value,reviewed_at:new Date().toISOString()}};localStorage.setItem(key,JSON.stringify(saved));refresh()}});
 return {{card,id,select}};
}});
function refresh(){{let done=0;cards.forEach(x=>{{const yes=Boolean(x.select.value);done+=yes;x.card.classList.toggle('reviewed',yes)}});document.getElementById('progress').textContent=`已审核 ${{done}} / ${{cards.length}}`}}
document.getElementById('export').addEventListener('click',()=>{{
 const reviews=cards.filter(x=>x.select.value).map(x=>saved[x.id]);
 const invalid=reviews.filter(x=>x.verdict==='correct_logo'&&(!x.box||x.box[2]-x.box[0]<.02||x.box[3]-x.box[1]<.02));
 if(invalid.length){{alert('标为正确台标的项目必须先拖框圈出台标。');return}}
 const blob=new Blob([JSON.stringify({{schema_version:1,report:location.pathname,exported_at:new Date().toISOString(),reviews}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='logo-reference-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)
}});refresh();
}})()</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.capture_dir / "logo-template-review.html"
    output.write_text(build_page(args.capture_dir), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
