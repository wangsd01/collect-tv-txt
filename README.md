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

