import re
import argparse
import sys
import os

# --- 辅助函数：解析单个 M3U 内容 (返回 order_list, channels_map, header) ---
def parse_single_m3u(m3u_content):
    if not m3u_content:
        return [], {}, ""
        
    # 严格去除空行，保证后续解析的连续性
    lines = [line.strip() for line in m3u_content.strip().split('\n') if line.strip()]
    
    channels_map = {}
    order_list = []
    header = ""
    
    current_info_line = None
    current_channel_name = None
    
    for line in lines:
        if line.startswith('#EXTM3U'):
            if not header: # 只记录第一个遇到的 M3U 头部
                header = line
            continue

        if line.startswith('#EXTINF:'):
            current_info_line = line
            match = re.search(r',(.+)$', line)
            if match:
                current_channel_name = match.group(1).strip()
            else:
                current_channel_name = None 
            
            if current_channel_name:
                if current_channel_name not in channels_map:
                    channels_map[current_channel_name] = {"info": current_info_line, "urls": set()}
                    order_list.append(current_channel_name)
                else:
                    # 总是更新为最新的属性行
                    channels_map[current_channel_name]["info"] = current_info_line
            
        elif (line.startswith('http://') or line.startswith('https://')):
            if current_channel_name and current_channel_name in channels_map:
                channels_map[current_channel_name]["urls"].add(line)
        
        else:
             current_channel_name = None # 遇到非M3U行则重置状态

    return order_list, channels_map, header # <-- 返回头部信息

# --- 主函数：处理文件 I/O 和高级合并逻辑 ---
def main():
    parser = argparse.ArgumentParser(
        description="合并多个M3U文件的内容，对同名频道下的所有URL进行去重和分组，并按频道首次出现的相对顺序排序。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # ... (参数解析部分不变) ...
    parser.add_argument('-i', '--input', type=str, nargs='+', required=True, help="一个或多个输入M3U文件的路径")
    parser.add_argument('-o', '--output', type=str, required=True, help="输出M3U文件的路径")
    args = parser.parse_args()
    
    if not args.input:
        print("错误: 请提供至少一个输入文件。", file=sys.stderr)
        sys.exit(1)
        
    final_channels_map = {}
    final_order_list = []
    final_header = ""
    
    # 1. 处理第一个文件 (作为基础顺序)
    try:
        input_file_1 = args.input[0]
        if not os.path.exists(input_file_1):
            raise FileNotFoundError(f"文件不存在: {input_file_1}")
            
        with open(input_file_1, 'r', encoding='utf-8') as f:
            content_1 = f.read()
            
        temp_order_list, temp_map, header = parse_single_m3u(content_1)
        
        final_header = header # 记录第一个文件的头部
        final_order_list.extend(temp_order_list)
        final_channels_map.update(temp_map)
        
    except Exception as e:
        print(f"处理第一个文件 '{input_file_1}' 时发生错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 依次处理后续文件 (进行高级合并)
    for input_file in args.input[1:]:
        if not os.path.exists(input_file):
            print(f"警告: 输入文件 '{input_file}' 不存在。跳过。", file=sys.stderr)
            continue
            
        if input_file == args.output:
            print(f"警告: 输入文件 '{input_file}' 和输出文件不能是同一个文件。跳过。", file=sys.stderr)
            continue

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content_n = f.read()
                
            current_order_list, current_map, _ = parse_single_m3u(content_n) # 忽略后续文件的 header
            
            last_known_channel_index = -1
            
            # 找到文件 2 中已存在频道在最终列表中的最新位置
            for i, channel in enumerate(final_order_list):
                if channel in current_map:
                    last_known_channel_index = i

            # 遍历当前文件的频道顺序，执行插入
            for channel_name in current_order_list:
                
                if channel_name in final_channels_map:
                    # A. 频道已存在: 合并 URL 和更新属性
                    
                    # 1. 更新属性 (保留最新的)
                    final_channels_map[channel_name]["info"] = current_map[channel_name]["info"]
                    
                    # 2. 合并 URL
                    final_channels_map[channel_name]["urls"].update(current_map[channel_name]["urls"])
                    
                    # 3. 更新 last_known_channel_index
                    last_known_channel_index = final_order_list.index(channel_name)
                    
                else:
                    # B. 频道是新的: 插入到已知频道之后
                    
                    # 1. 将新频道添加到最终 map
                    final_channels_map[channel_name] = current_map[channel_name]
                    
                    # 2. 插入到 order_list 中，位置是 last_known_channel_index + 1
                    insert_index = last_known_channel_index + 1
                    final_order_list.insert(insert_index, channel_name)
                    
                    # 3. 更新 last_known_channel_index 到新插入频道的位置
                    last_known_channel_index = insert_index 

        except Exception as e:
            print(f"处理文件 '{input_file}' 时发生错误: {e}", file=sys.stderr)
            sys.exit(1)

    # 3. 写入最终结果
    output_lines = [final_header] if final_header else []
    
    for name in final_order_list:
        if name in final_channels_map:
            data = final_channels_map[name]
            output_lines.append(data["info"])
            for url in sorted(list(data["urls"])):
                output_lines.append(url)
                
    modified_m3u = '\n'.join(output_lines)

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(modified_m3u)
            
        print(f"成功: {len(args.input)} 个 M3U 文件已合并，并写入到 '{args.output}'")
        
    except Exception as e:
        print(f"写入文件时发生错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
