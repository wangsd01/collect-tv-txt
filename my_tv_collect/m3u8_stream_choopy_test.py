import numpy as np
import requests
import m3u8
import time
from urllib.parse import urljoin


def is_m3u8_stream_choppy(m3u8_url, threshold=0.5):
    print(m3u8_url)
    try:
        response = requests.get(m3u8_url, timeout=1)
    except:
        print(m3u8_url, "time out")
        return True, 0
    base_uri = response.url  # This will be used as the base URI
    playlist = m3u8.loads(response.text, uri=base_uri)
    # print(playlist.segments)
    choppy_segments = 0
    total_segments = 0
    total_download_time = 0
    total_segment_size = 0
    segment_size_list = []
    packet_loss = 0
    for segment in playlist.segments:
        segment_url = urljoin(base_uri, segment.uri)  # Resolve the absolute URI
        segment_duration = segment.duration
        try:
            start_time = time.time()
            segment_response = requests.get(segment_url, timeout=1.)
            download_time = time.time() - start_time

            if download_time > segment_duration * (1 + threshold):
                choppy_segments += 1

            segment_size = 0.0
            n_chunk = 0
            for chunk in segment_response.iter_content(chunk_size=1024):
                segment_size += len(chunk)
                n_chunk += 1
            # bytes to Kb
            segment_size = segment_size / 1024.
            total_segments += 1
            total_download_time += download_time
            total_segment_size += segment_size
            segment_size_list.append(segment_size)
            if segment_size < 100:
                packet_loss += 1
            print(
                f"Segment {total_segments}: Duration={segment_duration}s, Download Time={download_time:.4f}s, Size={segment_size:.4f}Kb, Chunk Count={n_chunk}")
        except requests.RequestException as e:
            packet_loss += 1
            print(f"Segment {total_segments}: Failed to download (exception: {e})")
            continue

    if total_segments == 0:
        return True, 0

    choppy_ratio = choppy_segments / total_segments
    packet_loss_ratio = packet_loss / len(playlist.segments)

    seg_size_var_ratio = np.std(segment_size_list) / np.mean(segment_size_list)
    # is_choppy = choppy_ratio > 0.5 or seg_size_var_ratio > 0.1 or packet_loss_ratio > 0.2
    is_choppy = packet_loss_ratio > 0.5
    # is_choppy = choppy_ratio > 0.1 or packet_loss_ratio > 0.1
    speed = total_segment_size / total_download_time
    # print(segment_size_list)
    print(
        f"Choppy Ratio: {choppy_ratio:.2f}, seg size var ratio : {seg_size_var_ratio:.2f}, package loss ratio: {packet_loss_ratio:.2f}, is choppy: {is_choppy}, speed :{speed:.2f}kb/s")
    return is_choppy, speed  # You can adjust the threshold here


if __name__ == "__main__":
    # Example usage
    # m3u8_url = "http://123.146.162.24:8013/tslslive/noEX9SG/hls/live_sd.m3u8"
    # m3u8_url = "http://cdn.jdshipin.com:8880/ysp.php?id=cctv1"
    # m3u8_url = "http://n1.dddmmh.space:8088/udp/225.0.4.74:7980"
    # m3u8_url = "http://58.19.38.162:9901/tsfile/live/1001_1.m3u8?key=tvbox6_com&playlive=1&authid=0"
    # m3u8_url = "http://171.118.222.151:9999/tsfile/live/0001_1.m3u8"
    # m3u8_url = "http://111.197.224.161:4022/rtp/239.3.1.129:8008"
    # m3u8_url = "http://119.39.97.2:9002/tsfile/live/0005_1.m3u8?key=txiptv&playlive=1&authid=0"
    # m3u8_url = "http://36.32.174.67:60080/newlive/live/hls/1/live.m3u8"
    # m3u8_url = 'http://119.39.97.2:9002/tsfile/live/0005_1.m3u8?key=txiptv&playlive=1&authid=0'
    m3u8_url = "http://175.8.213.198:8081/tsfile/live/0005_1.m3u8?key=txiptv&playlive=1&authid=0"
    is_choppy, speed = is_m3u8_stream_choppy(m3u8_url)
    if is_choppy:
        print("The stream is choppy. speed is ", speed)
    else:
        print("The stream is smooth. speed is ", speed)
