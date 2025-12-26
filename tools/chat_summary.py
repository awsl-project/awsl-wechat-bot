#!/usr/bin/env python3
"""
群聊工具 - 微信聊天记录解密与总结

子命令:
    decrypt  - 解密微信数据库
    summary  - 生成群聊总结

使用方法:
    python chat_summary.py decrypt --input <输入路径> --key <密钥> --output <输出路径>
    python chat_summary.py summary --group <群ID> --db-path <数据库路径> [--date <日期>] [--image]

示例:
    # 解密数据库
    python chat_summary.py decrypt \\
        --input "C:\\Users\\xxx\\Documents\\xwechat_files\\wxid_xxx" \\
        --key "9d0391daa25847..." \\
        --output "C:\\decrypted"

    # 生成总结
    python chat_summary.py summary --group 49100408389@chatroom --db-path "C:\\decrypted"
    python chat_summary.py summary --group 49100408389@chatroom --db-path "C:\\decrypted" --image
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import requests

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config

# HTML 模板，用于渲染 Markdown 成图片（使用 $var 占位符避免与 CSS 花括号冲突）
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px;
            min-height: 100vh;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 30px 40px;
        }
        .header h1 { font-size: 28px; margin-bottom: 15px; text-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .header .meta { font-size: 14px; opacity: 0.9; }
        .header .meta span { margin-right: 20px; }
        .content { padding: 40px; color: #333; line-height: 1.8; }
        .content h1 { display: none; }
        .content h2 {
            color: #4facfe;
            font-size: 20px;
            margin: 25px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid #e0e0e0;
        }
        .content h3 { color: #555; font-size: 16px; margin: 20px 0 10px 0; }
        .content p { margin: 10px 0; text-align: justify; }
        .content ul, .content ol { margin: 10px 0 10px 25px; }
        .content li { margin: 8px 0; }
        .content strong { color: #4facfe; }
        .content hr { display: none; }
        .footer {
            background: #f8f9fa;
            padding: 20px 40px;
            text-align: center;
            color: #888;
            font-size: 12px;
            border-top: 1px solid #e0e0e0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 群聊总结</h1>
            <div class="meta">
                <span>📅 $date</span>
                <span>💬 $msg_count 条消息</span>
                <span>🕐 $gen_time</span>
            </div>
        </div>
        <div class="content">
            $content
        </div>
        <div class="footer">
            由 AI 自动生成 · AWSL WeChat Bot
        </div>
    </div>
</body>
</html>"""


def fetch_messages(
    api_base: str,
    db_path: str,
    group: str,
    start: str,
    end: str,
    limit: int = 1000,
    token: Optional[str] = None
) -> list[dict]:
    """从 API 获取聊天记录"""
    url = f"{api_base}/api/chatlog/messages"
    params = {
        "db_path": db_path,
        "group": group,
        "start": start,
        "end": end,
        "limit": limit
    }
    headers = {"accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def decrypt_database(
    api_base: str,
    input_path: str,
    key: str,
    output_path: str,
    token: Optional[str] = None
) -> dict:
    """调用 API 解密微信数据库"""
    url = f"{api_base}/api/chatlog/decrypt"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "input_path": input_path,
        "key": key,
        "output_path": output_path
    }

    response = requests.post(url, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()


def format_messages_for_llm(messages: list[dict]) -> tuple[str, int, dict[str, int]]:
    """将消息格式化为 LLM 可读的文本，并统计发送者消息数量"""
    if not messages:
        return "（无消息记录）", 0, {}

    lines = []
    sender_counts: dict[str, int] = {}

    for msg in messages:
        if msg.get("is_self"):
            continue
        time_str = msg.get("time", "")[11:19]
        sender = msg.get("sender_name") or "未知"
        content = msg.get("content", "")
        lines.append(f"[{time_str}] {sender}: {content}")

        # 统计消息数量
        sender_counts[sender] = sender_counts.get(sender, 0) + 1

    return "\n".join(lines), len(lines), sender_counts


def generate_ranking(sender_counts: dict[str, int], top_n: int = 10) -> str:
    """生成消息排行榜 Markdown"""
    if not sender_counts:
        return ""

    # 按消息数量排序
    sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    # 排名标识
    rank_icons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    lines = ["## 📊 发言排行榜", ""]
    for i, (sender, count) in enumerate(sorted_senders):
        icon = rank_icons[i] if i < len(rank_icons) else f"#{i + 1}"
        lines.append(f"- {icon} **{sender}** - {count} 条消息")

    return "\n".join(lines)


def summarize_with_llm(
    messages_text: str,
    group_name: str,
    date_str: str,
    api_url: str,
    api_key: str,
    model: str = "gpt-4o-mini"
) -> str:
    """使用 LLM 生成聊天记录总结"""
    system_prompt = """你是一个专业的群聊记录分析助手。请分析提供的聊天记录，生成结构化的 Markdown 格式总结。

总结应包含以下部分：

## 概览
简要描述今日群聊的整体氛围和活跃度（1-2句话）

## 话题分析
识别出所有讨论话题，对于每个话题提供：
- **主题** - 话题的简短标题
- **时间**: 起止时间（如 09:30-10:15）
- **参与者**: 主要参与讨论的成员
- **内容**: 详细描述讨论过程，包括各方观点、提出的问题、给出的解答或建议、达成的共识等（3-5句话）

格式示例：
### 话题一：[主题名称]
- **时间**: 09:30 - 10:15
- **参与者**: 张三、李四、王五
- **内容**: 张三提出了xxx问题，李四建议使用xxx方案，王五补充了xxx细节。经过讨论，大家认为xxx是最佳选择，并计划xxx。

## 重要信息
提取值得关注的信息、决定或结论（如无则写"无"）

注意：
- 使用中文输出
- 话题按时间顺序排列
- 合并相似或连续的讨论
- 内容描述要具体，体现讨论的来龙去脉
- 忽略表情包、无意义的水群内容
- 如果聊天内容较少或无实质内容，如实说明
- 不要生成活跃成员/发言排行相关内容，这部分由程序自动统计"""

    user_prompt = f"""请总结以下群聊记录：

群聊: {group_name}
日期: {date_str}

聊天记录:
---
{messages_text}
---

请生成 Markdown 格式的总结。"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.3
    }

    response = requests.post(
        f"{api_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def markdown_to_html(md_text: str) -> str:
    """将 Markdown 转换为 HTML"""
    try:
        import markdown
        return markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
    except ImportError:
        # 简单的 Markdown 转换
        import re
        lines = md_text.split('\n')
        html_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()

            # 标题
            if stripped.startswith('### '):
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<h3>{stripped[4:]}</h3>')
            elif stripped.startswith('## '):
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<h2>{stripped[3:]}</h2>')
            elif stripped.startswith('# '):
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<h1>{stripped[2:]}</h1>')
            # 列表项
            elif stripped.startswith('- '):
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                content = stripped[2:]
                content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
                html_lines.append(f'<li>{content}</li>')
            # 空行
            elif not stripped:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
            # 普通段落
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
                html_lines.append(f'<p>{content}</p>')

        if in_list:
            html_lines.append('</ul>')

        return '\n'.join(html_lines)


def render_to_image(summary: str, date_str: str, msg_count: int, gen_time: str, output_path: str) -> bool:
    """使用 html2image 将总结渲染为图片，自动裁剪空白"""
    try:
        from html2image import Html2Image
    except ImportError:
        print("错误: 需要安装 html2image: pip install html2image")
        return False

    try:
        from PIL import Image
    except ImportError:
        print("错误: 需要安装 Pillow: pip install Pillow")
        return False

    from string import Template

    # 将 markdown 转为 HTML
    html_content = markdown_to_html(summary)

    # 根据内容估算高度（每个字符约 0.5-1px，加上基础高度）
    base_height = 300  # header + footer + padding
    content_height = len(summary) * 0.8 + summary.count('\n') * 25
    estimated_height = int(base_height + content_height)
    # 设置一个足够大的高度，确保不截断
    render_height = max(estimated_height, 1000) + 500

    # 生成完整 HTML（使用 Template 避免花括号冲突）
    template = Template(HTML_TEMPLATE)
    full_html = template.substitute(
        date=date_str,
        msg_count=msg_count,
        gen_time=gen_time,
        content=html_content
    )

    try:
        hti = Html2Image(size=(900, render_height))
        output_dir = os.path.dirname(output_path) or '.'
        output_name = os.path.basename(output_path)
        if not output_name.endswith('.png'):
            output_name += '.png'

        hti.output_path = output_dir
        temp_name = f"_temp_{output_name}"
        hti.screenshot(html_str=full_html, save_as=temp_name)

        # 裁剪空白部分
        temp_path = os.path.join(output_dir, temp_name)
        final_path = os.path.join(output_dir, output_name)

        img = Image.open(temp_path)
        pixels = img.load()
        width, height = img.size

        # 从底部向上扫描，找到白色容器（footer）的底部
        # footer 背景是 #f8f9fa (248, 249, 250)，容器底部有圆角
        bottom = height
        center_x = width // 2  # 检测中心位置

        for y in range(height - 1, 100, -1):
            r, g, b = pixels[center_x, y][:3]
            # 检测到浅灰色 footer 或白色内容区域
            if r > 240 and g > 240 and b > 240:
                bottom = y + 50  # 留 50px 底部边距
                break

        # 裁剪图片
        bottom = min(bottom, height)
        if bottom < height:
            img = img.crop((0, 0, width, bottom))

        img.save(final_path)
        img.close()

        # 删除临时文件
        if os.path.exists(temp_path) and temp_path != final_path:
            os.remove(temp_path)

        return True
    except Exception as e:
        print(f"渲染图片失败: {e}")
        return False


def send_image_to_group(
    api_base: str,
    group_name: str,
    image_path: str,
    token: Optional[str] = None
) -> bool:
    """发送图片到群聊"""
    import base64

    # 读取图片并转为 base64
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    url = f"{api_base}/api/send"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "group_name": group_name,
        "image_base64": image_base64
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return True


def cmd_decrypt(args) -> int:
    """解密子命令"""
    print(f"输入路径: {args.input}")
    print(f"输出路径: {args.output}")
    print(f"API: {args.api_base}")
    print("-" * 40)

    print("正在解密数据库...")
    try:
        result = decrypt_database(
            api_base=args.api_base,
            input_path=args.input,
            key=args.key,
            output_path=args.output,
            token=args.token
        )
        print(f"解密完成: {result}")
        return 0
    except requests.exceptions.RequestException as e:
        print(f"错误: 解密失败: {e}")
        return 1


def cmd_summary(args) -> int:
    """总结子命令"""
    # 确定日期范围
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"错误: 无效的日期格式: {args.date}")
            return 1
    else:
        target_date = datetime.now()

    date_str = target_date.strftime("%Y-%m-%d")
    next_date_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
    start_time = f"{date_str} 05:00:00"
    end_time = f"{next_date_str} 05:00:00"

    if not args.db_path:
        print("错误: 请提供 --db-path 参数")
        return 1

    if not config.OPENAI_API_KEY:
        print("错误: 未配置 OPENAI_API_KEY")
        return 1

    print(f"群聊ID: {args.group}")
    print(f"日期: {date_str}")
    print(f"数据库: {args.db_path}")
    print(f"API: {args.api_base}")
    if args.send:
        print(f"发送到: {args.send}")
    print("-" * 40)

    # 获取聊天记录
    print("正在获取聊天记录...")
    try:
        messages = fetch_messages(
            api_base=args.api_base,
            db_path=args.db_path,
            group=args.group,
            start=start_time,
            end=end_time,
            limit=args.limit,
            token=args.token
        )
    except requests.exceptions.RequestException as e:
        print(f"错误: 获取聊天记录失败: {e}")
        return 1

    print(f"获取到 {len(messages)} 条消息")

    if not messages:
        print("没有消息记录，无需总结")
        return 0

    messages_text, valid_count, sender_counts = format_messages_for_llm(messages)
    print(f"有效消息: {valid_count} 条（已过滤自己发送的消息）")

    if valid_count == 0:
        print("没有有效消息，无需总结")
        return 0

    # 生成排行榜
    ranking = generate_ranking(sender_counts)

    # 生成总结
    print("正在生成总结...")
    try:
        summary = summarize_with_llm(
            messages_text=messages_text,
            group_name=args.group,
            date_str=date_str,
            api_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
            model=config.OPENAI_MODEL
        )
    except requests.exceptions.RequestException as e:
        print(f"错误: LLM 请求失败: {e}")
        return 1

    # 合并总结和排行榜
    summary = summary + "\n\n" + ranking

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 如果需要发送，强制生成图片
    if args.send:
        print("正在渲染图片...")
        output_path = args.output or f"/tmp/summary_{date_str}.png"
        if not output_path.endswith('.png'):
            output_path += '.png'

        if not render_to_image(summary, date_str, valid_count, gen_time, output_path):
            return 1

        print(f"图片已保存到: {output_path}")

        # 发送图片
        print(f"正在发送图片到群聊: {args.send}")
        try:
            send_image_to_group(
                api_base=args.api_base,
                group_name=args.send,
                image_path=output_path,
                token=args.token
            )
            print("图片发送成功!")
        except requests.exceptions.RequestException as e:
            print(f"错误: 发送图片失败: {e}")
            return 1
    elif args.image:
        # 仅生成图片不发送
        print("正在渲染图片...")
        output_path = args.output or f"summary_{date_str}.png"
        if not output_path.endswith('.png'):
            output_path += '.png'

        if render_to_image(summary, date_str, valid_count, gen_time, output_path):
            print(f"\n图片已保存到: {output_path}")
        else:
            return 1
    else:
        # 输出 Markdown
        header = f"""# 群聊总结

- **日期**: {date_str}
- **消息数**: {valid_count}
- **生成时间**: {gen_time}

---

"""
        full_summary = header + summary

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(full_summary)
            print(f"\n总结已保存到: {args.output}")
        else:
            print("\n" + "=" * 40)
            print(full_summary)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="群聊工具 - 微信聊天记录解密与总结",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # decrypt 子命令
    decrypt_parser = subparsers.add_parser("decrypt", help="解密微信数据库")
    decrypt_parser.add_argument("--input", "-i", required=True, help="输入路径（微信数据目录）")
    decrypt_parser.add_argument("--key", "-k", required=True, help="解密密钥")
    decrypt_parser.add_argument("--output", "-o", required=True, help="输出路径")
    decrypt_parser.add_argument("--api-base", default="http://localhost:8000", help="API 基础地址")
    decrypt_parser.add_argument("--token", help="API Bearer Token")

    # summary 子命令
    summary_parser = subparsers.add_parser("summary", help="生成群聊总结")
    summary_parser.add_argument("--group", "-g", required=True, help="群聊ID")
    summary_parser.add_argument("--date", "-d", help="日期 (YYYY-MM-DD)，默认为今天")
    summary_parser.add_argument("--db-path", required=True, help="解密后的数据库目录")
    summary_parser.add_argument("--api-base", default="http://localhost:8000", help="API 基础地址")
    summary_parser.add_argument("--token", help="API Bearer Token")
    summary_parser.add_argument("--output", "-o", help="输出文件路径")
    summary_parser.add_argument("--limit", "-n", type=int, default=2000, help="消息数量限制 (默认: 2000)")
    summary_parser.add_argument("--image", action="store_true", help="输出为图片")
    summary_parser.add_argument("--send", "-s", metavar="GROUP_NAME", help="生成后发送图片到指定群聊名称")

    args = parser.parse_args()

    if args.command == "decrypt":
        return cmd_decrypt(args)
    elif args.command == "summary":
        return cmd_summary(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
