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
                line = line.split('$')[0]
            txt_lines.append(f"{channel_name},{line.strip()}")

    # 将结果合并成一个字符串，以换行符分隔
    return '\n'.join(txt_lines)

# def process_url(url):
#     try:
#         # 打开URL并读取内容
#         with urllib.request.urlopen(url) as response:
#             # 以二进制方式读取数据
#             data = response.read()
#             # 将二进制数据解码为字符串
#             text = data.decode('utf-8')
#             channel_name=""
#             channel_address=""
#
#             #处理m3u和m3u8，提取channel_name和channel_address
#             if get_url_file_extension(url)==".m3u" or get_url_file_extension(url)==".m3u8":
#                 text=convert_m3u_to_txt(text)
#
#             # 逐行处理内容
#             lines = text.split('\n')
#             for line in lines:
#                 process_channel_line(line) # 每行按照规则进行分发
#
#     except Exception as e:
#         print(f"处理URL时发生错误：{e}")