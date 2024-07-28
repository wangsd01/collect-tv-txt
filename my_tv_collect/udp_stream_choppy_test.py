import numpy as np
import requests
import time


def is_udp_stream_choppy(uri, duration=20):
    packet_intervals = []
    packet_loss = 0
    total_segments = 0
    total_download_time = 0
    total_segment_size = 0
    start_time = time.time()

    print(uri)
    while time.time() - start_time < duration:
        try:
            segment_start_time = time.time()
            response = requests.get(uri, stream=True, timeout=1.)
            size = 0
            n_chunk = 1000
            for chunk in response.iter_content(chunk_size=1024):
                size += len(chunk)
                # print(size)
                n_chunk -= 1
                if n_chunk < 0:
                    break
            segment_download_time = time.time() - segment_start_time
            segment_size = size / 1024
            total_download_time += segment_download_time
            total_segment_size += segment_size

            if segment_size < 100:
                packet_loss += 1

            if response.status_code == 200:
                packet_intervals.append(segment_download_time)
                print(
                    f"Segment {total_segments}: Download Time={segment_download_time:.4f}s, Segment size: {segment_size}")
            else:
                packet_loss += 1
                print(f"Segment {total_segments}: Failed to download (status code: {response.status_code})")



        except requests.RequestException as e:
            packet_loss += 1
            print(f"Segment {total_segments}: Failed to download (exception: {e})")
            continue
        total_segments += 1

    if not packet_intervals:
        print("No segments received.")
        return True, 0

    average_interval = np.mean(packet_intervals)
    jitter = np.std(packet_intervals) / np.mean(packet_intervals)
    packet_loss_ratio = packet_loss / total_segments

    # Determine if the stream is choppy
    jitter_threshold = 0.2
    packet_loss_ratio_threshold = 0.1
    # is_choppy = jitter > jitter_threshold or packet_loss_ratio > packet_loss_ratio_threshold
    packet_loss_ratio_threshold = 0.5
    is_choppy = packet_loss_ratio > packet_loss_ratio_threshold
    speed = total_segment_size / total_download_time

    print(f"Average Segment Download Time: {average_interval:.4f}s", f"Jitter ratio: {jitter:.4f}",
          f"Packet Loss Ratio: {packet_loss_ratio:.2%}, is choppy: {is_choppy}, speed: {speed:.2f}kb/s")
    return is_choppy, speed


if __name__ == "__main__":
    # Example usage
    # http_udp_uri = "http://n1.dddmmh.space:8088/udp/225.0.4.74:7980"
    # choppy_url = "http://36.32.174.67:60080/newlive/live/hls/1/live.m3u8"
    # http_udp_uri = "http://111.197.224.161:4022/rtp/239.3.1.129:8008"
    # http_udp_uri = "http://60.10.225.157:555/rtp/239.253.93.252:6430"
    http_udp_uri = "http://cdn.jdshipin.com:8880/ysp.php?id=cctv1"
    is_choppy, speed = is_udp_stream_choppy(http_udp_uri)
    if is_choppy:
        print("The stream is choppy. speed is ", speed)
    else:
        print("The stream is smooth. speed is ", speed)
