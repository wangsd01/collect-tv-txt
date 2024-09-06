import os
import re
import urllib
import time
from datetime import datetime
from urllib.parse import urlparse

import eventlet
import requests
import threading
from queue import Queue
import concurrent.futures

from tqdm import tqdm

from my_tv_collect.m3u8_stream_choopy_test import is_m3u8_stream_choppy
from my_tv_collect.udp_stream_choppy_test import is_udp_stream_choppy


def get_url_file_extension(url):
    # 解析URL
    parsed_url = urlparse(url)
    # 获取路径部分
    path = parsed_url.path
    # 提取文件扩展名
    extension = os.path.splitext(path)[1]
    return extension


def convert_m3u_to_txt(m3u_content):
    # 分行处理
    lines = m3u_content.split('\n')

    # 用于存储结果的列表
    txt_lines = []

    # 临时变量用于存储频道名称
    channel_name = ""

    for line in lines:
        # 过滤掉 #EXTM3U 开头的行
        if line.startswith("#EXTM3U"):
            continue
        # 处理 #EXTINF 开头的行
        if line.startswith("#EXTINF"):
            # 获取频道名称（假设频道名称在引号后）
            channel_name = line.split(',')[-1].strip()
        # 处理 URL 行
        elif line.startswith("http"):
            if '$' in line:
                # remove comment after $
                line = line.split('$')[0]
            txt_lines.append(f"{channel_name},{line.strip()}")

    # 将结果合并成一个字符串，以换行符分隔
    return '\n'.join(txt_lines)


# 检测URL是否可访问并记录响应时间
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}


def check_url(url, timeout=1):
    try:
        if "://" in url:
            start_time = time.time()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
                if response.status == 200:
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


def filter_accessible_urls(urls):
    urls = set(urls)
    valid_urls = []
    max_works = min(len(urls), 10)
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
        results = executor.map(check_url, urls)

        for latency, valid, url in results:
            if valid:
                valid_urls.append((latency, url))
    valid_urls = sorted(valid_urls)
    valid_urls = [url for _, url in valid_urls]
    return valid_urls


def standardize_channel_name(name):
    name = name.upper()
    name = name.replace("1920", "")
    name = name.replace("1920", "")
    name = name.replace("1920", "")
    name = name.replace("CAVS", "")
    name = name.replace("cctv", "CCTV")
    name = name.replace("中央", "CCTV")
    name = name.replace("央视", "CCTV")
    name = name.replace("1080P", "")
    name = name.replace("576P", "")
    name = name.replace("576", "")
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
    name = name.replace("·正直播", "")
    name = name.replace("女性时�?", "女性时尚")
    name = name.replace("怀旧剧�?", "CCTV怀旧剧场")
    name = name.replace("CCTV0", "CCTV")
    name = re.sub(r"CCTV(\d+)台", r"CCTV\1", name)
    name = name.replace("「IPV6」", "")
    name = name.replace("CCTV1综合", "CCTV1")
    name = name.replace("CCTV综合", "CCTV1")
    name = name.replace("CCTV1B", "CCTV1")
    name = name.replace("CCTV2财经", "CCTV2")
    name = name.replace("CCTV2经济", "CCTV2")
    name = name.replace("CCTV财经", "CCTV2")
    name = name.replace("CCTV3综艺", "CCTV3")
    name = name.replace("CCTV综艺", "CCTV3")
    name = name.replace("CCTV4国际", "CCTV4")
    name = name.replace("CCTV国际", "CCTV4")
    name = name.replace("CCTV4中文国际", "CCTV4")
    name = name.replace("CCTV4中文", "CCTV4")
    name = name.replace("CCTV4欧洲", "CCTV4")
    name = name.replace("CCTV4美洲", "CCTV4")
    name = name.replace("CCTV4北美", "CCTV4")
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
    name = name.replace("CCTV10科教", "CCTV10")
    name = name.replace("CCTV科教", "CCTV10")
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
    l = len(name)
    if l%2 == 0 and name[0:l//2] == name[l//2:]:
        name = name[0:l//2]
    return name


def rank_channel_urls_by_speed(channels):
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


def check_url_by_choppy_and_speed(url):
    # if 'udp' in url or 'rtp' in url:
    #     is_choppy, speed = analyze_udp_stream(url)
    if 'm3u8' in url:
        is_choppy, speed = is_m3u8_stream_choppy(url)
    else:
        is_choppy, speed = is_udp_stream_choppy(url)
    return is_choppy, speed, url


def rank_channel_urls_by_choppy_and_speed(channel_urls):
    urls = set(channel_urls)
    valid_urls = []
    if len(channel_urls) == 0:
        return valid_urls
    max_works = min(len(urls), 10)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_works) as executor:
        urls = [url.strip() for url in urls]
        results = executor.map(check_url_by_choppy_and_speed, urls)

        results = sorted(results, key=lambda x: (x[0], -x[1]))
        print(results)
        for is_choppy, speed, url in results:
            if not is_choppy and speed > 100:
                valid_urls.append(url)
    return valid_urls


def sequential_rank_channel_urls_by_choppy_and_speed(channel_urls):
    urls = set(channel_urls)
    valid_urls = []
    if len(urls) == 0:
        return valid_urls
    results = []
    for url in tqdm(urls, desc="sequential ranking urls:"):
        result = check_url_by_choppy_and_speed(url)
        results.append(result)
    results = sorted(results, key=lambda x: (x[0], -x[1]))
    print(results)
    for is_choppy, speed, url in results:
        if not is_choppy and speed > 100:
            valid_urls.append(url)
    return valid_urls
