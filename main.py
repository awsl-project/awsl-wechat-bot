#!/usr/bin/env python3
"""
AWSL 微信机器人 - 使用 Accessibility API
监控指定群聊，检测到 "awsl" 消息时自动发送随机图片或AI回复
"""

import os
import sys
import time
import logging
import subprocess
import tempfile
import re
import sqlite3
import requests
import queue
import threading
import Quartz

from config import config
from utils_accessibility_api import get_messages_via_accessibility
from ai_service import AIService
from command_service import CommandService

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WeChatOCR:
    """使用 OCR 读取微信消息"""

    def __init__(self):
        self.process_name = self._detect_wechat_process()
        if not self.process_name:
            raise RuntimeError("微信未运行，请先启动微信")
        logger.info(f"检测到微信进程: {self.process_name}")

    def _detect_wechat_process(self) -> str:
        """检测微信进程名称"""
        result = subprocess.run(['pgrep', 'WeChat'], capture_output=True)
        if result.returncode == 0:
            return "WeChat"
        result = subprocess.run(['pgrep', '微信'], capture_output=True)
        if result.returncode == 0:
            return "微信"
        return None

    def _run_applescript(self, script: str) -> str:
        """执行 AppleScript"""
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.debug(f"AppleScript 错误: {result.stderr}")
            return None
        return result.stdout.strip()

    def activate_window(self):
        """激活微信窗口"""
        subprocess.run(['open', '-a', self.process_name], check=True)
        time.sleep(0.3)

    def click_input_box(self):
        """点击输入框以获得焦点"""
        # 使用 AppleScript 获取窗口位置和大小
        script = f'''
        tell application "System Events"
            tell process "{self.process_name}"
                set wechatWindow to window 1
                set {{wx, wy}} to position of wechatWindow
                set {{ww, wh}} to size of wechatWindow
                return (wx as text) & "," & (wy as text) & "," & (ww as text) & "," & (wh as text)
            end tell
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script],
                              capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.warning(f"获取窗口位置失败: {result.stderr}")
            return False

        # 解析窗口位置和大小
        try:
            wx, wy, ww, wh = map(float, result.stdout.strip().split(','))
        except Exception as e:
            logger.warning(f"解析窗口坐标失败: {e}")
            return False

        # 计算点击位置（窗口底部中间偏右）
        click_x = wx + ww * 0.6
        click_y = wy + wh * 0.92

        # 使用 Quartz 执行系统级鼠标点击
        # 移动鼠标到目标位置
        move_event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)
        time.sleep(0.05)

        # 鼠标按下
        mouse_down = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_down)
        time.sleep(0.05)

        # 鼠标抬起
        mouse_up = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_up)

        logger.debug(f"已点击输入框位置: ({click_x:.0f}, {click_y:.0f})")
        return True

    def find_chat(self, chat_name: str) -> bool:
        """查找并切换到指定聊天窗口"""
        self.activate_window()
        time.sleep(0.2)

        script = f'''
        set the clipboard to "{chat_name}"
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "f" using command down
                delay 0.3
                keystroke "v" using command down
                delay 1.0
                key code 36
                delay 0.5
                key code 53
                delay 0.3
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(0.5)

        # 点击输入框获得焦点
        self.click_input_box()

        logger.info(f"已切换到聊天: {chat_name}")
        return True

    def get_messages(self) -> list:
        """获取当前聊天窗口的消息"""
        self.activate_window()
        time.sleep(0.2)

        # 使用 Accessibility API 获取消息
        all_messages = get_messages_via_accessibility(self.process_name)

        # 过滤噪音
        messages = []
        for text in all_messages:
            if len(text) < 2:
                continue
            if re.match(r'^[\d:]+$', text):  # 纯时间戳
                continue
            # UI 元素和特殊标记
            if text in ['<', '>', 'S', '...', 'Image', 'Animated Stickers']:
                continue
            messages.append(text)

        return messages

    def send_text(self, text: str) -> bool:
        """发送文本消息"""
        self.activate_window()
        time.sleep(0.2)

        script = f'''
        set the clipboard to "{text}"
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "v" using command down
                delay 0.3
                key code 36
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(0.5)
        return True

    def send_image(self, image_path: str) -> bool:
        """发送图片"""
        # 复制图片到剪贴板
        script = f'''
        set theFile to POSIX file "{image_path}"
        try
            set the clipboard to (read theFile as JPEG picture)
        on error
            set the clipboard to (read theFile as «class PNGf»)
        end try
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"复制图片失败: {result.stderr}")
            return False

        time.sleep(0.3)
        self.activate_window()
        time.sleep(0.2)

        # 粘贴并发送
        script = f'''
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "v" using command down
                delay 0.5
                key code 36
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(1.0)
        logger.info("图片已发送")
        return True


class AWSlBot:
    """AWSL 机器人 - 使用消息队列分离检测和处理"""

    def __init__(self, group_name: str):
        self.group_name = group_name
        self.wechat = WeChatOCR()
        self.max_cache = 200

        # 消息队列（最多10个待处理消息）
        self.message_queue = queue.Queue(maxsize=10)

        # 冷却控制
        self.last_trigger_time = 0
        self.cooldown_lock = threading.Lock()

        # 数据库锁（保护数据库操作）
        self.db_lock = threading.Lock()

        # 运行控制
        self.running = False
        self.detector_thread = None
        self.processor_thread = None

        self._init_db()

        # 初始化 AI 服务
        try:
            self.ai_service = AIService()
        except Exception as e:
            logger.warning(f"AI 服务初始化失败，AI 功能将不可用: {e}")
            self.ai_service = None

        # 初始化命令服务
        try:
            self.command_service = CommandService()
            if self.command_service.load_commands():
                logger.info(f"命令服务初始化成功，已加载 {len(self.command_service.commands)} 个命令")
            else:
                logger.warning("命令列表加载失败")
        except Exception as e:
            logger.warning(f"命令服务初始化失败: {e}")
            self.command_service = None

        logger.info(f"AWSL Bot 初始化完成，监控群聊: {group_name}")

    def _init_db(self):
        """初始化 SQLite 数据库"""
        db_path = os.path.join(os.path.dirname(__file__), 'messages.db')
        # 允许跨线程使用（因为我们使用队列模式）
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS message_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
        logger.info(f"数据库初始化完成: {db_path}")

    def _is_processed(self, msg_hash: str) -> bool:
        """检查消息是否已处理"""
        with self.db_lock:
            cursor = self.conn.execute(
                'SELECT 1 FROM message_hashes WHERE hash = ?', (msg_hash,)
            )
            return cursor.fetchone() is not None

    def _mark_processed(self, msg_hash: str):
        """标记消息为已处理"""
        with self.db_lock:
            try:
                self.conn.execute(
                    'INSERT OR IGNORE INTO message_hashes (hash) VALUES (?)', (msg_hash,)
                )
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"数据库写入失败: {e}")

    def _cleanup_old_hashes(self):
        """清理旧记录，保留最近的记录"""
        with self.db_lock:
            cursor = self.conn.execute('SELECT COUNT(*) FROM message_hashes')
            count = cursor.fetchone()[0]
            if count > self.max_cache:
                self.conn.execute('''
                    DELETE FROM message_hashes WHERE id IN (
                        SELECT id FROM message_hashes ORDER BY id ASC LIMIT ?
                    )
                ''', (count - self.max_cache // 2,))
                self.conn.commit()
                logger.info(f"清理旧记录，剩余 {self.max_cache // 2} 条")

    def fetch_awsl_image(self) -> str:
        """从 API 获取随机图片 URL"""
        try:
            response = requests.get(
                config.API_URL,
                headers={'accept': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            pic_info = data.get('pic_info', {})
            url = pic_info.get('large', pic_info.get('original', {})).get('url')
            if url:
                logger.info(f"获取到图片: {url[:50]}...")
                return url
            return None

        except Exception as e:
            logger.error(f"获取图片失败: {e}")
            return None

    def download_image(self, url: str) -> str:
        """下载图片到临时文件"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            suffix = '.png' if 'png' in url.lower() else '.jpg'
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, 'wb') as f:
                f.write(response.content)

            logger.info(f"图片已下载: {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None

    def send_awsl_image(self) -> bool:
        """获取并发送 AWSL 图片"""
        image_url = self.fetch_awsl_image()
        if not image_url:
            return False

        image_path = self.download_image(image_url)
        if not image_path:
            return False

        try:
            return self.wechat.send_image(image_path)
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass

    def is_trigger(self, text: str) -> tuple:
        """
        检查是否包含触发词

        Returns:
            tuple: (trigger_type, content)
                trigger_type: "ai" - AI回复, "command" - 远程命令, "command_refresh" - 刷新命令列表, None - 不触发
                content:
                    - AI模式时为问题内容
                    - command模式时为(command_key, params)元组
                    - 其他为空字符串
        """
        # 过滤包含 Animated Stickers 的消息（不区分大小写）
        if "animated stickers" in text.lower():
            return (None, "")

        # 消息内容
        content = text.strip()
        content_lower = content.lower()

        # 检查是否为 awsl 触发词
        keyword_lower = config.TRIGGER_KEYWORD.lower()

        # 特殊处理：awsl hp - 刷新命令列表
        if content_lower == f"{keyword_lower} hp":
            logger.info("匹配到 awsl hp - 刷新命令列表")
            return ("command_refresh", ("hp", ""))

        # 如果以 awsl 开头
        if content_lower.startswith(keyword_lower):
            # 提取 awsl 后面的部分
            after_keyword = content[len(config.TRIGGER_KEYWORD):].strip()

            # 如果 awsl 后面有内容，作为 AI 问题
            if after_keyword:
                return ("ai", after_keyword)

            # 纯 awsl，不触发任何动作
            return (None, "")

        # 检查是否为远程命令（直接执行，不需要 awsl 前缀）
        if self.command_service:
            cmd_match = self.command_service.match_command(content)
            if cmd_match:
                logger.info(f"匹配到远程命令: {cmd_match[0]} with params: {cmd_match[1]}")
                return ("command", cmd_match)

        # 不触发
        return (None, "")


    def message_detector_loop(self):
        """消息检测循环 - 持续检测新消息并加入队列"""
        logger.info("消息检测线程启动")

        # 初始化：记录当前所有消息避免重复触发
        initial_messages = self.wechat.get_messages()
        for msg in initial_messages:
            msg_hash = str(hash(msg))
            self._mark_processed(msg_hash)
        logger.info(f"已记录历史消息: {len(initial_messages)} 条")

        while self.running:
            try:
                messages = self.wechat.get_messages()

                logger.info("-" * 40)
                logger.info(f"检测到 {len(messages)} 条消息")

                # 处理所有消息，找出未处理过的
                new_messages = []
                for msg in messages:
                    msg_hash = str(hash(msg))
                    if not self._is_processed(msg_hash):
                        new_messages.append(msg)
                        self._mark_processed(msg_hash)

                # 处理所有新消息
                if new_messages:
                    logger.info(f"发现 {len(new_messages)} 条新消息")
                    for msg in new_messages:
                        logger.info(f"新消息: {msg}")

                        trigger_type, content = self.is_trigger(msg)

                        if trigger_type:
                            # 将触发消息加入队列
                            try:
                                self.message_queue.put_nowait({
                                    'type': trigger_type,
                                    'content': content,
                                    'timestamp': time.time()
                                })
                                logger.info(f"✓ 消息已加入队列 (队列大小: {self.message_queue.qsize()})")
                            except queue.Full:
                                logger.warning("⚠ 队列已满，丢弃消息")

                # 清理旧记录
                self._cleanup_old_hashes()

                # 短暂延迟避免 CPU 占用过高，但保持快速响应
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"消息检测出错: {e}")
                time.sleep(1)  # 出错时等待更长时间

        logger.info("消息检测线程退出")

    def message_processor_loop(self):
        """消息处理循环 - 从队列取消息并处理（带冷却）"""
        logger.info("消息处理线程启动")

        while self.running:
            try:
                # 从队列获取消息（最多等待1秒）
                try:
                    task = self.message_queue.get(timeout=1)
                except queue.Empty:
                    continue

                trigger_type = task['type']
                content = task['content']

                # 检查冷却时间
                with self.cooldown_lock:
                    now = time.time()
                    remaining = config.TRIGGER_COOLDOWN - (now - self.last_trigger_time)

                    if remaining > 0:
                        logger.info(f"⏳ 冷却中，还需 {remaining:.1f} 秒，消息将稍后处理")
                        # 等待冷却时间
                        time.sleep(remaining)
                        now = time.time()

                    # 处理消息
                    if trigger_type == "command" and self.command_service:
                        # 执行命令
                        command_key, params = content
                        logger.info(f">>> 触发命令: {command_key} with params: {params}")
                        result = self.command_service.execute_command(command_key, params)

                        if result:
                            # 直接发送文本结果
                            self.wechat.send_text(result)
                        else:
                            logger.error(f"命令执行失败: {command_key}")
                            self.wechat.send_text(f"命令执行失败: {command_key}")

                    elif trigger_type == "command_refresh" and self.command_service:
                        logger.info(">>> 触发命令刷新")
                        # 刷新命令列表
                        success = self.command_service.load_commands()
                        if success:
                            self.wechat.send_text("已经成功了")

                    elif trigger_type == "ai" and self.ai_service:
                        logger.info(f">>> 触发 AI 回复! 问题: {content}")
                        answer = self.ai_service.ask(content)
                        if answer:
                            self.wechat.send_text(answer)
                        else:
                            logger.error("AI 回复失败")
                            self.wechat.send_text("抱歉，我现在无法回答这个问题 😅")
                    elif trigger_type == "ai" and not self.ai_service:
                        logger.warning("AI 服务未初始化，无法回复")

                    # 更新最后触发时间
                    self.last_trigger_time = now

                # 标记任务完成
                self.message_queue.task_done()

            except Exception as e:
                logger.error(f"消息处理出错: {e}")
                import traceback
                traceback.print_exc()

        logger.info("消息处理线程退出")

    def run(self):
        """运行机器人主循环"""
        logger.info("=" * 50)
        logger.info("AWSL Bot 启动 (Accessibility API + 队列模式)")
        logger.info(f"监控群聊: {self.group_name}")
        logger.info(f"触发关键词: {config.TRIGGER_KEYWORD}")
        logger.info(f"检测间隔: 0.5 秒 (快速响应)")
        logger.info(f"响应冷却: {config.TRIGGER_COOLDOWN} 秒")
        logger.info(f"队列大小: 最多 10 条")
        logger.info("=" * 50)

        # 切换到目标群聊
        self.wechat.find_chat(self.group_name)

        # 设置运行标志
        self.running = True

        # 启动检测线程
        self.detector_thread = threading.Thread(
            target=self.message_detector_loop,
            name="MessageDetector",
            daemon=True
        )
        self.detector_thread.start()

        # 启动处理线程
        self.processor_thread = threading.Thread(
            target=self.message_processor_loop,
            name="MessageProcessor",
            daemon=True
        )
        self.processor_thread.start()

        logger.info("两个线程已启动:")
        logger.info("  - 检测线程: 持续检测新消息")
        logger.info("  - 处理线程: 处理消息并发送回复（带冷却）")
        logger.info("")
        logger.info("开始监控...")

        try:
            # 主线程等待
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("收到停止信号，正在关闭...")
            self.running = False

            # 等待线程结束
            if self.detector_thread:
                self.detector_thread.join(timeout=5)
            if self.processor_thread:
                self.processor_thread.join(timeout=5)

            # 关闭数据库连接
            with self.db_lock:
                self.conn.close()

            logger.info("机器人已停止")


def main():
    try:
        bot = AWSlBot(config.GROUP_NAME)
        bot.run()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
