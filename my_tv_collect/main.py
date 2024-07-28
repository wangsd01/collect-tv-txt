import collections
import datetime
import re
import urllib
from collections import defaultdict

from tqdm import tqdm

from my_tv_collect.utils import get_url_file_extension, convert_m3u_to_txt, filter_accessible_urls, \
    standardize_channel_name, rank_channel_urls_by_speed, channel_key, rank_channel_urls_by_choppy_and_speed, \
    sequential_rank_channel_urls_by_choppy_and_speed


class CollectTV:
    def __init__(self, live_tv_source_urls=[]):
        self.live_channel_source_dict = defaultdict(list)

        self.result_counter = 15  # 每个频道需要的个数
        for url in tqdm(live_tv_source_urls, desc="Downloading channels from files"):
            self.download_channel_list(url)
        self.filter_accessible_channels()
        # self.rank_channel_urls_by_speed()
        self.rank_channel_urls_by_choppy_and_speed()
        self.write_to_txt()
        self.write_to_m3u()

    def download_channel_list(self, url):
        try:
            # 打开URL并读取内容
            with urllib.request.urlopen(url) as response:
                # 以二进制方式读取数据
                data = response.read()
                # 将二进制数据解码为字符串
                text = data.decode('utf-8')

                # 处理m3u和m3u8，提取channel_name和channel_address
                if get_url_file_extension(url) == ".m3u" or get_url_file_extension(url) == ".m3u8":
                    text = convert_m3u_to_txt(text)

                # 逐行处理内容
                lines = text.split('\n')
                for line in lines:
                    self.process_channel_line(line)  # 每行按照规则进行分发

        except Exception as e:
            print(f"处理URL时发生错误：{e}, {url}")

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
        channel_name = line.split(',')[0].strip()
        channel_url = line.split(',')[1].strip()
        channel_name = standardize_channel_name(channel_name)
        if not channel_name.startswith('CCTV'):
            # only get source for cctv
            return
        # if 'IPV6' in channel_name:
        #     return
        if '4K' in channel_name:
            return
        if '8K' in channel_name:
            return
        if 'CCTV.COM' in channel_name:
            return

        self.live_channel_source_dict[channel_name].append(channel_url)

    def filter_accessible_channels(self):
        self.live_channel_source_dict = collections.OrderedDict(sorted(self.live_channel_source_dict.items(), key=lambda x: channel_key(x[0])))
        print("channels")
        print(list(self.live_channel_source_dict.keys()))
        for channel_name, channel_urls in tqdm(self.live_channel_source_dict.items(), desc="filtering accessible channel"):
            channel_urls = set(channel_urls)
            valid_urls = filter_accessible_urls(channel_urls)
            print("filtering ", channel_name, f", {len(channel_urls)} urls, {len(valid_urls)} accessible.")
            self.live_channel_source_dict[channel_name] = valid_urls

    def rank_channel_urls_by_speed(self):
        for channel_name, channel_urls in tqdm(self.live_channel_source_dict.items(), desc="ranking channels"):
            ranked_channel_urls = rank_channel_urls_by_speed(channel_urls)
            self.live_channel_source_dict[channel_name] = ranked_channel_urls

    def rank_channel_urls_by_choppy_and_speed(self):
        for channel_name, channel_urls in tqdm(self.live_channel_source_dict.items(), desc="ranking channels"):
            print(channel_name)
            ranked_channel_urls = rank_channel_urls_by_choppy_and_speed(channel_urls)
            # ranked_channel_urls = sequential_rank_channel_urls_by_choppy_and_speed(channel_urls)
            self.live_channel_source_dict[channel_name] = ranked_channel_urls

    def write_to_txt(self, file_name="my_itvlist"):
        file_name = file_name + "_" + datetime.datetime.now().strftime("%m-%d-%Y")
        file_name += ".txt"
        with open(file_name, 'w', encoding='utf-8') as file:
            channel_counters = {}
            file.write('央视频道,#genre#\n')
            for channel_name, channel_urls in self.live_channel_source_dict.items():
                if 'CCTV' in channel_name:
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
                if 'CCTV' in channel_name:
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
    urls = [
        'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u',
        'https://raw.githubusercontent.com/joevess/IPTV/main/iptv.m3u8',
        'https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt',
        'https://raw.githubusercontent.com/Guovin/TV/gd/result.txt',  # 每天自动更新1次
        'https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt',  # 每天自动更新1次
        'https://m3u.ibert.me/txt/fmml_ipv6.txt',
        'https://m3u.ibert.me/txt/ycl_iptv.txt',
        'https://m3u.ibert.me/txt/y_g.txt',
        'https://m3u.ibert.me/txt/j_home.txt',
        'https://raw.githubusercontent.com/gaotianliuyun/gao/master/list.txt',
        'https://gitee.com/xxy002/zhiboyuan/raw/master/zby.txt',
        'https://raw.githubusercontent.com/mlvjfchen/TV/main/iptv_list.txt',  # 每天早晚各自动更新1次 2024-06-03 17:50
        'https://raw.githubusercontent.com/fenxp/iptv/main/live/ipv6.txt',  # 1小时自动更新1次11:11 2024/05/13
        'https://raw.githubusercontent.com/fenxp/iptv/main/live/tvlive.txt',  # 1小时自动更新1次11:11 2024/05/13
        'https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt',  # 每天自动更新1次 2024-06-24 16:37
        'https://gitlab.com/p2v5/wangtv/-/raw/main/lunbo.txt',
        'https://raw.githubusercontent.com/PizazzGY/TVBox/main/live.txt',  # ADD 2024-07-22 13:50
        'https://raw.githubusercontent.com/kimwang1978/tvbox/main/%E5%A4%A9%E5%A4%A9%E5%BC%80%E5%BF%83/lives/%E2%91%AD%E5%BC%80%E5%BF%83%E7%BA%BF%E8%B7%AF.txt',
        'https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u',
        'https://gitlab.com/p2v5/wangtv/-/raw/main/wang-tvlive.txt',
        'https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8',
        "https://raw.githubusercontent.com/wangsd01/collect-tv-txt/main/my_tv_collect/my_itvlist.m3u",
        "https://raw.githubusercontent.com/wangsd01/collect-tv-txt/aa468c35f2e10b682f64d185533af6da8bf3d831/my_tv_collect/my_itvlist.m3u"
    ]
    ctv = CollectTV(urls)
