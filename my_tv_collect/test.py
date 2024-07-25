from my_tv_collect.utils import check_url, is_url_accessible

# url = "http://58.19.38.162:9901/tsfile/live/1000_1.m3u8?key=txiptv&playlive=1&authid=0$湖北联通 酒店"
url = "http://58.19.38.162:9901/tsfile/live/1000_1.m3u8?key=txiptv&playlive=1&authid=0"
url = "http://38.64.72.148/hls/modn/list/4005/chunklist1.m3u8?"
url = "http://n1.dddmmh.space:8088/udp/225.0.4.74:7980"
print(check_url(url))
print(is_url_accessible(url))