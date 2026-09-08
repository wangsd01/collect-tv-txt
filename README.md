# collect-tv-txt

自动收集整理直播源

收集器会先用 FFmpeg 验证直播流能否正常解码，再抽样检查长时间黑屏和
画面定格；检测到异常的地址会被隔离，不写入发布列表。内容检查默认采样
8 秒，可用 `--content-check-seconds` 调整，设为 `0` 可关闭：

```bash
python main.py --content-check-seconds 12
```

该检查用于发现无信号画面和停止更新的视频，不能可靠区分电视台正常广告，
也不能单独确认台标与频道名称是否一致。

## 人工内容审核

真实时间取样、截图及 OCR 仅产生候选，最后由 HTML 页面人工判断。首次使用可建立
独立环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-audit.txt
.venv/bin/python scripts/review_stream_content.py merged_output.txt audits/$(date +%F)-realtime
```

调试某个频道时可加 `--channel CCTV10`；批量央视频道可加 `--channel-prefix CCTV`。

为台标参考库选择可信样本：

```bash
.venv/bin/python scripts/logo_template_review.py audits/日期-realtime
# 在生成页面中框出台标并导出 JSON 后：
.venv/bin/python scripts/apply_logo_review.py /path/to/logo-reference-review.json audits/日期-realtime
```

审核页会先对同步转播和近似画面去重；不同节目时段应分别采集、分别审核，逐步补充模板。

在生成的 `gallery.html` 中选择结论并导出 `stream-review.json` 后，应用结论：

```bash
.venv/bin/python scripts/apply_stream_review.py /path/to/stream-review.json
python main.py
```

每张截图都附有四角台标裁剪图；有目标台标的正常节目内广告可在页面标为“频道正确／正常广告”。
已确认台标模板保存在 `config/logo_templates.json`；图形匹配只提供候选。匹配到其他台标时，
提示“频道标签分错或内容切换”并交人工确认，不会自动剔除。
错台、只有声音、以及“同一 URL 会插播诈骗医疗广告”的 `mixed_content` 都会剔除；
信号失效隔离；确认正确但停播的测试卡可发布。OCR 识别到“抢购热线”等只会提示人工
审核，不会因为频道的正常广告自动删除。

| 类别  | 文件名  | 更新频率                                       | 备注   |
|-------|-------|------------------------------------------------|------------|
|直播源| （merged_output.txt） |  每日自动更新 | http://gg.gg/tv-live-txt   |
|直播源| （merged_output.m3u） |  每日自动更新 | http://gg.gg/tv-live-m3u   |
|黑名单| （blacklist_auto.txt） |  不定时更新 | 无效直播源会从直播源过滤掉   |
|白名单| （whitelist_auto.txt） |  不定时更新 | 高响应源汇总到直播源   |

### **直播源（txt）：**
```
https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt
```
直播源（txt）短链：
```
http://gg.gg/tv-live-txt
```
镜像源（txt）：
```
https://ghproxy.net/https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt
```
镜像源（txt）短链：
```
http://gg.gg/tv-live-txt-mirr
```
### **直播源（m3u）：**
```
https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.m3u
```
直播源（m3u）短链：
```
http://gg.gg/tv-live-m3u
```


| 类 别  | 直播源                                       | ShortLink   |
|-------|------------------------------------------------|------------|
| （txt） |  https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt | http://gg.gg/tv-live-txt   |
| （m3u） |  https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.m3u | http://gg.gg/tv-live-m3u   |


如果有其他定期更新稳定的源也可以留言，有时间一起加在收集列表里。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=kimwang1978/collect-tv-txt&type=Date)](https://star-history.com/#kimwang1978/collect-tv-txt&Date)
