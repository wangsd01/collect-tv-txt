import os
import re
import urllib
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

import requests
import threading
from queue import Queue
import concurrent.futures

from tqdm import tqdm

from my_tv_collect.stream_check import check_stream_quality


def get_url_file_extension(url):
    # 解析URL
    parsed_url = urlparse(url)
    # 获取路径部分
    path = parsed_url.path
    # 提取文件扩展名
    extension = os.path.splitext(path)[1]
    return extension


def convert_m3u_to_txt(m3u_content):
    txt_lines = []
    channel_name = ""

    for raw_line in m3u_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            _, separator, channel_name = line.partition(",")
            if not separator:
                channel_name = ""
            channel_name = channel_name.strip()
            continue
        if line.startswith("#") or "://" not in line:
            continue

        stream_url = line.split("$", 1)[0].strip()
        if channel_name and stream_url:
            txt_lines.append(f"{channel_name},{stream_url}")

    return "\n".join(txt_lines)


# 检测URL是否可访问并记录响应时间
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}


def check_url(url, timeout=3, max_latency_ms=2000):
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return None, False, None

        start_time = time.time()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(1)
            elapsed_time = (time.time() - start_time) * 1000
            if 200 <= response.status < 400 and (
                    max_latency_ms is None or elapsed_time <= max_latency_ms):
                return elapsed_time, True, url
    except Exception as e:
        # print(f"Error checking {url}   : {e}")
        pass
    return None, False, None


def is_url_accessible(url):
    try:
        print(url)
        response = requests.get(url, timeout=1)
        if response.status_code == 200:
            return url
    except requests.exceptions.RequestException:
        pass
    return None


# def filter_accessible_urls(urls):
#     urls = set(urls)
#     valid_urls = []
#     max_works = min(len(urls), 100)
#     #   多线程获取可用url
#     # with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
#     #     futures = []
#     #     for url in urls:
#     #         url = url.strip()
#     #         futures.append(executor.submit(is_url_accessible, url))
#     #
#     #     for future in concurrent.futures.as_completed(futures):
#     #         result = future.result()
#     #         if result:
#     #             valid_urls.append(result)
#
#     with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
#         urls = [url.strip() for url in urls]
#         results = executor.map(is_url_accessible, urls)
#
#         for result in results:
#             if result:
#                 valid_urls.append(result)
#     return valid_urls

def filter_accessible_urls_sequential(urls):
    urls = set(urls)
    valid_urls = []
    for url in tqdm(urls):
        # if is_url_accessible(url):
        latency, valid, url = check_url(url, timeout=1)
        if valid:
            valid_urls.append(url)
    return valid_urls


def filter_accessible_urls(urls, timeout=3, max_latency_ms=2000, max_workers=10):
    urls = set(urls)
    if not urls:
        return []

    valid_urls = []
    max_works = min(len(urls), max_workers)
    #   多线程获取可用url
    # with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
    #     futures = []
    #     for url in urls:
    #         url = url.strip()
    #         futures.append(executor.submit(check_url, url))
    #
    #     for future in concurrent.futures.as_completed(futures):
    #         result = future.result()
    #         if result:
    #             valid_urls.append(result)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
        urls = [url.strip() for url in urls]
        results = executor.map(
            lambda url: check_url(url, timeout=timeout, max_latency_ms=max_latency_ms),
            urls,
        )

        for latency, valid, url in results:
            if valid:
                valid_urls.append((latency, url))
    valid_urls = sorted(valid_urls)
    valid_urls = [url for _, url in valid_urls]
    return valid_urls


def standardize_channel_name(name):
    try:
        import zhconv
    except ImportError:
        pass
    else:
        name = zhconv.convert(name, locale='zh-cn')
    # if 'CCTV' in name:
    #     print("Before", name)
    name = name.upper()
    name = name.replace("IPV6", "")
    name = name.replace("HEVC", "")
    name = name.replace("7.5M", "")
    name = name.replace("6.8M", "")
    name = name.replace("2.5M", "")
    name = name.replace("4M", "")
    name = name.replace("8M", "")
    name = name.replace("12M", "")
    name = name.replace("5.5M", "")
    name = name.replace("咪咕", "")
    # Resolution tags (e.g. "720P", "1080P") are stripped as a single unit so a
    # leftover "P" never lingers -- a bare "P" replace previously ate the letter
    # out of real words too (ESPN -> ESN, "Fox Sports" -> "FOXSORTS").
    for resolution in ("785", "540", "768", "1280", "720", "1920", "1080",
                       "2160", "480", "270", "144"):
        name = re.sub(resolution + r"P?", "", name)
    name = name.replace("DD5.1", "")
    name = name.replace(".", "")
    name = name.replace("CAVS", "")
    name = name.replace("AC3", "")
    name = name.replace("AAC", "")
    name = name.replace("cctv", "CCTV")
    name = name.replace("中央", "CCTV")
    name = name.replace("央视", "CCTV")
    name = name.replace("第2", "2")
    name = name.replace("劇場", "剧场")
    name = name.replace("BACKUP", "")
    name = name.replace("50FPS", "")
    name = name.replace("25P-HLG源", "")
    name = name.replace("H265", "")
    name = name.replace("2060P", "")
    name = name.replace("1080P", "")
    name = name.replace("576P", "")
    for resolution in ("576", "75", "68", "25", "55"):
        name = re.sub(resolution + r"P?", "", name)
    name = name.replace("*", "")
    name = name.replace("中国", "")
    name = name.replace("IPTV", "")
    name = name.replace("國際", "")
    name = name.replace("电视台", "")
    name = name.replace("高清", "")
    name = name.replace("高请", "")
    name = name.replace("超清", "")
    name = name.replace("超高", "")
    name = name.replace("HD", "")
    name = name.replace("标清", "")
    name = name.replace("频道", "")
    name = name.replace("测试", "")
    name = name.replace("系列", "")
    name = name.replace("备用V6", "")
    name = name.replace("备用V4", "")
    name = name.replace("-", "")
    name = name.replace("_", "")
    name = name.replace(" ", "")
    name = name.replace("PLUS", "+")
    name = name.replace("＋", "+")
    name = name.replace("(", "")
    name = name.replace(")", "")
    name = name.replace("（", "")
    name = name.replace("）", "")
    name = name.replace("[", "")
    name = name.replace("]", "")
    name = name.replace("“", "")
    name = name.replace("”", "")
    name = name.replace("•", "")
    name = name.replace("ITV", "")
    name = name.replace("·正直播", "")
    name = name.replace("女性时�?", "女性时尚")
    name = name.replace("怀旧剧�?", "CCTV怀旧剧场")
    name = name.replace("CCTV0", "CCTV")
    name = re.sub(r"CCTV(\d+)台", r"CCTV\1", name)
    name = name.replace("「IPV6」", "")
    name = name.replace("電視台", "")
    if "台球" not in name:
        name = name.replace("台", "")
    name = name.replace("頻道", "")
    name = name.replace("套", "")
    name = name.replace("十一", "11")
    name = name.replace("十二", "12")
    name = name.replace("十三", "13")
    name = name.replace("十四", "14")
    name = name.replace("十五", "15")
    name = name.replace("十六", "16")
    name = name.replace("十七", "17")
    name = name.replace("一", "1")
    name = name.replace("二", "2")
    name = name.replace("三", "3")
    name = name.replace("四", "4")
    name = name.replace("五", "5")
    name = name.replace("六", "6")
    name = name.replace("七", "7")
    name = name.replace("八", "8")
    name = name.replace("九", "9")
    name = name.replace("十", "10")

    name = name.replace("CCTV1综合", "CCTV1")
    name = name.replace("CCTV1綜合", "CCTV1")
    name = name.replace("CCTV综合", "CCTV1")
    name = name.replace("CCTV綜合", "CCTV1")
    name = name.replace("CCTV1B", "CCTV1")
    name = name.replace("CCTV2财经", "CCTV2")
    name = name.replace("CCTV2经济", "CCTV2")
    name = name.replace("CCTV财经", "CCTV2")
    name = name.replace("CCTV2经", "CCTV2")
    name = name.replace("CCTV2财", "CCTV2")
    name = name.replace("CCTV3综艺", "CCTV3")
    name = name.replace("CCTV综艺", "CCTV3")
    name = name.replace("CCTV4国际", "CCTV4")
    name = name.replace("CCTV国际", "CCTV4")
    name = name.replace("CCTV4中文国际", "CCTV4")
    name = name.replace("CCTV4中文", "CCTV4")
    name = name.replace("CCTV4欧洲", "CCTV4")
    name = name.replace("CCTV4美洲", "CCTV4")
    name = name.replace("CCTV4亚洲", "CCTV4")
    name = name.replace("CCTV4ASIA", "CCTV4")
    name = name.replace("CCTV4北美", "CCTV4")
    name = name.replace("CCTV4美", "CCTV4")
    name = name.replace("CCTV4欧", "CCTV4")
    name = name.replace("CCTV5体育", "CCTV5")
    name = name.replace("CCTV体育", "CCTV5")
    name = name.replace("CCTV5综合体育", "CCTV5")
    name = name.replace("CCTV5测试", "CCTV5")
    name = name.replace("CCTV05", "CCTV5")
    name = name.replace("CCTV6电影", "CCTV6")
    name = name.replace("CCTV电影", "CCTV6")
    name = name.replace("CCTV6影院代", "CCTV6")
    name = name.replace("CCTV7军事", "CCTV7")
    name = name.replace("CCTV军事", "CCTV7")
    name = name.replace("CCTV7军农", "CCTV7")
    name = name.replace("CCTV7农业", "CCTV7")
    name = name.replace("CCTV7国防军事", "CCTV7")
    name = name.replace("CCTV7国防", "CCTV7")
    name = name.replace("CCTV8电视剧", "CCTV8")
    name = name.replace("CCTV电视剧", "CCTV8")
    name = name.replace("CCTV8电视", "CCTV8")
    name = name.replace("CCTV9记录", "CCTV9")
    name = name.replace("CCTV纪录片", "CCTV9")
    name = name.replace("CCTV9纪录", "CCTV9")
    name = name.replace("CCTV纪录9", "CCTV9")
    name = name.replace("CCTV10科教", "CCTV10")
    name = name.replace("CCTV科教", "CCTV10")
    name = name.replace("CCTV11戏剧", "CCTV11")
    name = name.replace("CCTV11戏曲", "CCTV11")
    name = name.replace("CCTV戏曲", "CCTV11")
    name = name.replace("CCTV12社会与法", "CCTV12")
    name = name.replace("CCTV社会与法", "CCTV12")
    name = name.replace("CCTV12社会", "CCTV12")
    name = name.replace("CCTV12法制", "CCTV12")
    name = name.replace("CCTV13新闻", "CCTV13")
    name = name.replace("CCTV新闻", "CCTV13")
    name = name.replace("CCTV14少儿", "CCTV14")
    name = name.replace("CCTV少儿", "CCTV14")
    name = name.replace("CCTV15音乐", "CCTV15")
    name = name.replace("CCTV音乐", "CCTV15")
    name = name.replace("CCTV16奥林匹克", "CCTV16")
    name = name.replace("CCTV奥林匹克", "CCTV16")
    name = name.replace("CCTV奥运体育", "CCTV16")
    name = name.replace("CCTV16奥林", "CCTV16")
    name = name.replace("CCTV16HR", "CCTV16")
    name = name.replace("CCTV16[R]", "CCTV16")
    name = name.replace("CCTV17农业农村", "CCTV17")
    name = name.replace("CCTV17农村农业", "CCTV17")
    name = name.replace("CCTV农业农村", "CCTV17")
    name = name.replace("CCTV17农业", "CCTV17")
    name = name.replace("CCTV5+体育赛视", "CCTV5+")
    name = name.replace("CCTV5+体育赛事", "CCTV5+")
    name = name.replace("CCTV体育赛事", "CCTV5+")
    name = name.replace("CCTV5+体育", "CCTV5+")
    name = name.replace("CCTV+5+", "CCTV5+")
    name = name.replace("CCTV5+赛事", "CCTV5+")
    name = name.replace("CCTV5赛事", "CCTV5+")
    name = name.replace("CCTV4K超", "CCTV4K")
    name = name.replace("CCTVCCTV", "CCTV")
    name = name.replace("CCTV高尔夫.网球", "CCTV高尔夫网球")
    name = name.replace("CCTV高尔夫·网球", "CCTV高尔夫网球")
    name = name.replace("CCTV高网", "CCTV高尔夫网球")
    name = name.replace("CCTV高尔网球", "CCTV高尔夫网球")
    name = name.replace("CCTV网球", "CCTV高尔夫网球")
    name = name.replace("CCTV高尔夫球", "CCTV高尔夫网球")
    if name == "CCTV高尔夫":
        name = "CCTV高尔夫网球"
    name = name.replace("TVGUIDE", "电视指南")
    name = name.replace("CHC电影B", "CHC电影")
    name = name.replace("CHC电影", "CHC影迷电影")
    name = name.replace("CHC家庭影院B", "CHC家庭")
    name = name.replace("CHC动作电影B", "CHC动作")
    name = name.replace("CHC家庭影院", "CHC家庭")
    name = name.replace("CHC动作电影", "CHC动作")
    name = name.replace("CHC影迷电影", "CHC影迷")
    if not name.startswith("CCTV"):
        name = name.replace("4K", "")

    l = len(name)
    if l%2 == 0 and name[0:l//2] == name[l//2:]:
        name = name[0:l//2]
    # if 'CCTV' in name:
    #     print("After", name)
    return name


def rank_channel_urls_by_speed(channels):
    import eventlet

    # 线程安全的队列，用于存储下载任务
    task_queue = Queue()

    # 线程安全的列表，用于存储结果
    results = []

    error_channels = []

    def worker():
        while True:
            # 从队列中获取一个任务
            channel_url = task_queue.get()
            try:
                channel_url_t = channel_url.rstrip(channel_url.split('/')[-1])  # m3u8链接前缀
                lines = requests.get(channel_url, timeout=1).text.strip().split('\n')  # 获取m3u8文件内容
                ts_lists = [line.split('/')[-1] for line in lines if line.startswith('#') == False]  # 获取m3u8文件下视频流后缀
                ts_lists_0 = ts_lists[0].rstrip(ts_lists[0].split('.ts')[-1])  # m3u8链接前缀
                ts_url = channel_url_t + ts_lists[0]  # 拼接单个视频片段下载链接

                # 多获取的视频数据进行5秒钟限制
                with eventlet.Timeout(5, False):
                    start_time = time.time()
                    content = requests.get(ts_url, timeout=1.).content
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1

                if content:
                    with open(ts_lists_0, 'ab') as f:
                        f.write(content)  # 写入文件
                    file_size = len(content)
                    # print(f"文件大小：{file_size} 字节")
                    download_speed = file_size / response_time / 1024
                    # print(f"下载速度：{download_speed:.3f} kB/s")
                    normalized_speed = min(max(download_speed / 1024, 0.001), 100)  # 将速率从kB/s转换为MB/s并限制在1~100之间
                    # print(f"标准化后的速率：{normalized_speed:.3f} MB/s")

                    # 删除下载的文件
                    os.remove(ts_lists_0)
                    result = channel_url, f"{normalized_speed:.3f} MB/s"
                    results.append(result)
                    numberx = (len(results) + len(error_channels)) / len(channels) * 100
                    print(
                        f"可用频道：{len(results)} 个 , 不可用频道：{len(error_channels)} 个 , 总频道：{len(channels)} 个 ,总进度：{numberx:.2f} %。")
            except:
                error_channel = channel_url
                error_channels.append(error_channel)
                numberx = (len(results) + len(error_channels)) / len(channels) * 100
                print(
                    f"可用频道：{len(results)} 个 , 不可用频道：{len(error_channels)} 个 , 总频道：{len(channels)} 个 ,总进度：{numberx:.2f} %。")

            # 标记任务完成
            task_queue.task_done()

    # 创建多个工作线程
    num_threads = 10
    for _ in range(num_threads):
        t = threading.Thread(target=worker, daemon=True)  # 将工作线程设置为守护线程
        t.start()

    # 添加下载任务到队列
    for channel in channels:
        task_queue.put(channel)

    # 等待所有任务完成
    task_queue.join()

    results.sort(key=lambda x: -float(x[1].split()[0]))
    print(results)
    sorted_urls = [url for url, speed in results]
    return sorted_urls


def channel_key(channel_name):
    match = re.search(r'\d+', channel_name)
    if match:
        return int(match.group())
    else:
        return float('inf')  # 返回一个无穷大的数字作为关键字


def measure_segment_size(segment_url):
    try:
        response = requests.get(segment_url, stream=True)
        response.raise_for_status()
        size = 0
        for chunk in response.iter_content(chunk_size=1024):
            size += len(chunk)
        return size
    except requests.RequestException as e:
        print(f"Failed "
              f"to download segment {segment_url}: {e}")
        return 0


def check_url_by_choppy_and_speed(url, decode_seconds=5, retries=1):
    try:
        is_choppy, speed, error_code = check_stream_quality(
            url, decode_seconds=decode_seconds, retries=retries,
        )
        return is_choppy, speed, url
    except RuntimeError:
        # Environment problem (e.g. ffmpeg missing from PATH) -- don't hide
        # it by silently reporting every stream as choppy.
        raise
    except Exception:
        return True, 0, url


def rank_channels_by_choppy_and_speed(channel_url_map, max_workers=30, decode_seconds=5, retries=1):
    """Rank every channel's URLs for choppiness/speed with a single shared thread pool.

    Checking each channel with its own pool means total wall time is the *sum* of every
    channel's slowest URL. Flattening all (channel, url) pairs into one pool means it's
    closer to the slowest single check overall.
    """
    pairs = [
        (channel_name, url)
        for channel_name, urls in channel_url_map.items()
        for url in {u.strip() for u in urls}
    ]

    ranked = {channel_name: [] for channel_name in channel_url_map}
    if not pairs:
        return ranked

    results_by_channel = defaultdict(list)
    max_works = min(len(pairs), max_workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
        future_to_channel = {
            executor.submit(check_url_by_choppy_and_speed, url, decode_seconds, retries): channel_name
            for channel_name, url in pairs
        }
        for future in tqdm(concurrent.futures.as_completed(future_to_channel),
                            total=len(future_to_channel), desc="ranking channel urls"):
            channel_name = future_to_channel[future]
            is_choppy, speed, url = future.result()
            results_by_channel[channel_name].append((is_choppy, speed, url))

    for channel_name, results in results_by_channel.items():
        results.sort(key=lambda x: (x[0], -x[1]))
        ranked[channel_name] = [url for is_choppy, speed, url in results if not is_choppy]
    return ranked
