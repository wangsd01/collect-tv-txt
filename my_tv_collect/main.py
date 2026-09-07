import collections
import concurrent.futures
import datetime
import glob
import os
import re
import threading
import urllib
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from my_tv_collect.utils import get_url_file_extension, convert_m3u_to_txt, filter_accessible_urls, \
    standardize_channel_name, rank_channel_urls_by_speed, channel_key, rank_channels_by_choppy_and_speed


class CollectTV:
    def __init__(self, live_tv_source_urls=None, source_timeout=10,
                 max_latency_ms=2000, rank_streams=True,
                 max_source_workers=20, max_rank_workers=None,
                 decode_seconds=5, retries=1):
        self.live_channel_source_dict = defaultdict(list)
        self.source_timeout = source_timeout
        self.max_latency_ms = max_latency_ms
        # Each rank check spawns a real ffmpeg decode process (CPU-bound, not
        # just an idle socket), so default concurrency to the CPU count
        # rather than a large I/O-style thread count.
        self.max_rank_workers = max_rank_workers or (os.cpu_count() or 4) * 2
        self.decode_seconds = decode_seconds
        self.retries = retries
        self._dict_lock = threading.Lock()
        # self.load_from_folder()
        self.result_counter = 15  # 每个频道需要的个数
        live_tv_source_urls = live_tv_source_urls or []
        max_works = min(len(live_tv_source_urls), max_source_workers) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
            futures = [executor.submit(self.download_channel_list, url) for url in live_tv_source_urls]
            for _ in tqdm(concurrent.futures.as_completed(futures), total=len(futures),
                          desc="Downloading channels from sources"):
                pass
        self.filter_accessible_channels()
        if rank_streams:
            self.rank_channel_urls_by_choppy_and_speed()

    def download_channel_list(self, url):
        try:
            # 打开URL并读取内容
            with urllib.request.urlopen(url, timeout=self.source_timeout) as response:
                # 以二进制方式读取数据
                data = response.read()
                # 将二进制数据解码为字符串
                text = data.decode('utf-8', errors='replace')

                # 处理m3u和m3u8，提取channel_name和channel_address
                if get_url_file_extension(url) == ".m3u" or get_url_file_extension(url) == ".m3u8":
                    text = convert_m3u_to_txt(text)

                # 逐行处理内容
                lines = text.split('\n')
                for line in lines:
                    self.process_channel_line(line)  # 每行按照规则进行分发

        except Exception as e:
            print(f"处理URL时发生错误：{e}, {url}")

    def load_from_folder(self):
        folder = Path("/home/wang/github/collect-tv-txt/tuc-mywl")
        # get all txt file in the folder
        for txt_file in folder.glob("*.txt"):
            try:
                with open(txt_file, 'r', errors='ignore') as f:
                    lines = f.readlines()
                    for line in lines:
                        self.process_channel_line(line)  # 每行按照规则进行分发
            except Exception as e:
                try:
                    with open(txt_file, 'r', encoding='gb18030', errors='ignore') as f:
                        lines = f.readlines()
                        for line in lines:
                            self.process_channel_line(line)  # 每行按照规则进行分发
                except Exception as e:
                    print(txt_file, e)



    def process_channel_line(self, line):
        if '$' in line:
            # remove comment after $
            line = line.split('$')[0]
        line = line.strip()
        if len(line) == 0:
            return

        if "#genre#" not in line and "," in line and "://" in line:
            pass
        else:
            # print("Discard ", line)
            return
        channel_name, channel_url = (part.strip() for part in line.split(',', 1))
        channel_name = standardize_channel_name(channel_name)
        # if "CCTV5" != channel_name:
        #     return
        if (not channel_name.startswith('CCTV')) and (not channel_name.startswith('CHC')):
            # only get source for cctv
            return
        if 'IPV6' in channel_name:
            return
        if "法语" in channel_name:
            return
        if "电视塔" in channel_name:
            return
        if "购物" in channel_name:
            return
        if "NEWS" in channel_name:
            return
        if 'CCTV+' in channel_name:
            return
        if '4K' in channel_name:
            return
        if '8K' in channel_name:
            return
        if 'CCTV.COM' in channel_name:
            return
        if 'IPV6' in channel_name:
            return
        with self._dict_lock:
            self.live_channel_source_dict.setdefault(channel_name, []).append(channel_url)

    def filter_accessible_channels(self):
        self.live_channel_source_dict = collections.OrderedDict(
            sorted(self.live_channel_source_dict.items(), key=lambda x: channel_key(x[0])))
        print("channels")
        print(list(self.live_channel_source_dict.keys()))
        for channel_name, channel_urls in tqdm(self.live_channel_source_dict.items(),
                                               desc="filtering accessible channel"):
            channel_urls = set(channel_urls)
            valid_urls = filter_accessible_urls(
                channel_urls,
                timeout=min(self.source_timeout, 3),
                max_latency_ms=self.max_latency_ms,
            )
            print("filtering ", channel_name, f", {len(channel_urls)} urls, {len(valid_urls)} accessible.")
            self.live_channel_source_dict[channel_name] = valid_urls

    def rank_channel_urls_by_speed(self):
        for channel_name, channel_urls in tqdm(self.live_channel_source_dict.items(), desc="ranking channels"):
            ranked_channel_urls = rank_channel_urls_by_speed(channel_urls)
            self.live_channel_source_dict[channel_name] = ranked_channel_urls

    def rank_channel_urls_by_choppy_and_speed(self):
        ranked = rank_channels_by_choppy_and_speed(
            self.live_channel_source_dict,
            max_workers=self.max_rank_workers,
            decode_seconds=self.decode_seconds,
            retries=self.retries,
        )
        self.live_channel_source_dict.update(ranked)

    def write_to_txt(self, file_name="my_itvlist"):
        file_name = file_name + "_" + datetime.datetime.now().strftime("%m-%d-%Y")
        file_name += ".txt"
        with open(file_name, 'w', encoding='utf-8') as file:
            channel_counters = {}
            file.write('央视频道,#genre#\n')
            for channel_name, channel_urls in self.live_channel_source_dict.items():
                if 'CCTV' in channel_name or 'CHC' in channel_name:
                    channel_urls = channel_urls[:self.result_counter]
                    for channel_url in channel_urls:
                        file.write(f"{channel_name},{channel_url}\n")
            # channel_counters = {}
            # file.write('卫视频道,#genre#\n')
            # for result in self.results:
            #     channel_name, channel_url, speed = result
            #     if '卫视' in channel_name:
            #         if channel_name in channel_counters:
            #             if channel_counters[channel_name] >= result_counter:
            #                 continue
            #             else:
            #                 file.write(f"{channel_name},{channel_url}\n")
            #                 channel_counters[channel_name] += 1
            #         else:
            #             file.write(f"{channel_name},{channel_url}\n")
            #             channel_counters[channel_name] = 1
            # channel_counters = {}
            # file.write('其他频道,#genre#\n')
            # for result in self.results:
            #     channel_name, channel_url, speed = result
            #     if 'CCTV' not in channel_name and '卫视' not in channel_name and '测试' not in channel_name:
            #         if channel_name in channel_counters:
            #             if channel_counters[channel_name] >= result_counter:
            #                 continue
            #             else:
            #                 file.write(f"{channel_name},{channel_url}\n")
            #                 channel_counters[channel_name] += 1
            #         else:
            #             file.write(f"{channel_name},{channel_url}\n")
            #             channel_counters[channel_name] = 1

    def write_to_m3u(self, file_name="my_itvlist"):
        file_name = file_name + "_" + datetime.datetime.now().strftime("%m-%d-%Y")
        file_name += ".m3u"
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write('#EXTM3U\n')
            for channel_name, channel_urls in self.live_channel_source_dict.items():
                if 'CCTV' in channel_name or "CHC" in channel_name:
                    channel_urls = channel_urls[:self.result_counter]
                    for channel_url in channel_urls:
                        file.write(f"#EXTINF:-1 group-title=\"央视频道\",{channel_name}\n")
                        file.write(f"{channel_url}\n")
            # channel_counters = {}
            # # file.write('卫视频道,#genre#\n')
            # for result in results:
            #     channel_name, channel_url, speed = result
            #     if '卫视' in channel_name:
            #         if channel_name in channel_counters:
            #             if channel_counters[channel_name] >= result_counter:
            #                 continue
            #             else:
            #                 file.write(f"#EXTINF:-1 group-title=\"卫视频道\",{channel_name}\n")
            #                 file.write(f"{channel_url}\n")
            #                 channel_counters[channel_name] += 1
            #         else:
            #             file.write(f"#EXTINF:-1 group-title=\"卫视频道\",{channel_name}\n")
            #             file.write(f"{channel_url}\n")
            #             channel_counters[channel_name] = 1
            # channel_counters = {}
            # # file.write('其他频道,#genre#\n')
            # for result in results:
            #     channel_name, channel_url, speed = result
            #     if 'CCTV' not in channel_name and '卫视' not in channel_name and '测试' not in channel_name:
            #         if channel_name in channel_counters:
            #             if channel_counters[channel_name] >= result_counter:
            #                 continue
            #             else:
            #                 file.write(f"#EXTINF:-1 group-title=\"其他频道\",{channel_name}\n")
            #                 file.write(f"{channel_url}\n")
            #                 channel_counters[channel_name] += 1
            #         else:
            #             file.write(f"#EXTINF:-1 group-title=\"其他频道\",{channel_name}\n")
            #             file.write(f"{channel_url}\n")
            #             channel_counters[channel_name] = 1


if __name__ == "__main__":
    # 2026-09-07: 校验全部源地址可访问性，剔除已失效/空内容源，
    # 并将 github.com/.../blob/... 链接（返回 HTML 而非原始内容）替换为 raw.githubusercontent.com 等效地址
    urls = [
        'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u',
        'https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt',
        'https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u',  # 每天自动更新1次
        'https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt',  # 每天自动更新1次
        'https://m3u.ibert.me/txt/fmml_ipv6.txt',
        'https://m3u.ibert.me/txt/ycl_iptv.txt',
        'https://m3u.ibert.me/txt/y_g.txt',
        'https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt',
        'https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt',  # 每天自动更新1次 2024-06-24 16:37
        'https://gitlab.com/p2v5/wangtv/-/raw/main/lunbo.txt',
        'https://raw.githubusercontent.com/wwb521/live/main/tv.m3u',  # ADD 2024-08-05 每10天更新一次
        'https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt',  # ADD 2024-08-12 每天更新3次
        'https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u',
        'https://gitlab.com/p2v5/wangtv/-/raw/main/wang-tvlive.txt',
        'https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8',
        "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.m3u",
        "https://raw.githubusercontent.com/wangsd01/collect-tv-txt/main/my_tv_collect/test.m3u",
        "https://raw.githubusercontent.com/wangsd01/collect-tv-txt/main/my_tv_collect/my_itvlist.m3u",
        "https://raw.githubusercontent.com/zuomy2021/tv/refs/heads/main/iptv.txt",
        "https://raw.githubusercontent.com/ALIT8569/tuc-mywl/refs/heads/main/%E5%92%AA%E5%92%95%E5%A4%AE%E8%A7%86.txt",
        "https://raw.githubusercontent.com/ALIT8569/tuc-mywl/refs/heads/main/%E4%B8%AD%E5%9B%BD%E7%A7%BB%E5%8A%A8(ip%E7%89%88%E7%A7%BB%E5%8A%A8%E9%80%9A%E7%94%A8).txt",
    ]
    ctv = CollectTV(urls)
    ctv.write_to_txt()
    ctv.write_to_m3u()