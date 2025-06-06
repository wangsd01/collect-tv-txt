from collections import defaultdict

from tqdm import tqdm

from my_tv_collect.main import CollectTV
from my_tv_collect.utils import check_url, is_url_accessible

# url = "http://58.19.38.162:9901/tsfile/live/1000_1.m3u8?key=txiptv&playlive=1&authid=0$湖北联通 酒店"
# url = "http://58.19.38.162:9901/tsfile/live/1000_1.m3u8?key=txiptv&playlive=1&authid=0"
# url = "http://38.64.72.148/hls/modn/list/4005/chunklist1.m3u8?"
# url = "http://n1.dddmmh.space:8088/udp/225.0.4.74:7980"
# print(check_url(url))
# print(is_url_accessible(url))

# url = "http://112.46.85.60:8009/hls/503/index.m3u8"
# url = "http://1.30.18.218:20080/hls/5/index.m3u8"
url = "https://yunmei.tv/cctv"
channel_dict = defaultdict(list)
# for i in tqdm(range(0, 100)):
for i in list(range(1, 15)) + ['5+']:
    # test_url = "http://112.46.85.60:8009/hls/" + str(i) + "/index.m3u8"
    # test_url = "http://1.30.18.218:20080/hls/" + str(i) + "/index.m3u8"
    # test_url = "http://116.162.6.192/zycfcdn.gdwlcloud.com/PLTV/88888888/224/3221225" + f"{i:03d}"+"/index.m3u8"
    # test_url = f"http://59.44.102.18:8888/newlive/live/hls/{i}/live.m3u8"
    # test_url = f"http://124.205.11.242:91/live/CCTV{i}hd-8M/live.m3u8"
    # test_url = f"http://111.61.236.247:9081/hls/{i}/index.m3u8"
    # test_url = f"http://110.52.8.141:808/hls/{i}/index.m3u8"
    # test_url = f"http://123.52.87.69:52200/hls/{i}/index.m3u8"
    # test_url = f"http://175.31.21.146:4480/hls/{i}/index.m3u8"
    test_url = f"{url}/cctv-{i}.m3u8"
    if check_url(test_url)[2]:
        print(test_url)
        channel_dict['CCTV'+str(i)].append(test_url)
        # break

ctv = CollectTV()
ctv.live_channel_source_dict = channel_dict
ctv.write_to_m3u('new_iptv_1004')

