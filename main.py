#!/usr/bin/env python3
"""
AWSL 微信机器人 - 支持多平台
监控指定群聊，检测到 "awsl" 消息时自动发送随机图片或AI回复
"""

import os
import sys
import time
import datetime
import logging
import subprocess
import tempfile
import re
import sqlite3
import requests
import queue
import threading

from config import config
from adapters import get_wechat_adapter
from ai_service import AIService
from command_service import CommandService

# 根据配置设置日志级别
log_level = logging.DEBUG if config.DEBUG else logging.INFO

# 日志配置
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AWSlBot:
    """AWSL 机器人 - 使用消息队列分离检测和处理"""

    def __init__(self, group_name: str):
        self.group_name = group_name
        self.wechat = get_wechat_adapter()
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
        self.scheduler_thread = None

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
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS message_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def _hash_message_with_context(self, messages: list, index: int) -> str:
        """结合前向上下文计算消息的唯一哈希值"""
        current = messages[index]
        context_size = 2
        context_parts = []
        for i in range(max(0, index - context_size), index):
            context_parts.append(messages[i])
        context_parts.append(current)
        context = "|".join(context_parts)
        return str(hash(context))

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
        """清理旧记录"""
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

    def fetch_awsl_image(self) -> str:
        """从 API 获取随机图片 URL"""
        try:
            response = requests.get(config.API_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            pic_info = data.get('pic_info', {})
            url = pic_info.get('large', pic_info.get('original', {})).get('url')
            return url
        except Exception as e:
            logger.error(f"获取图片失败: {e}")
            return None

    def download_image(self, url: str) -> str:
        """下载图片到临时文件"""
        try:
            response = requests.get(url, timeout=30)
            suffix = '.png' if 'png' in url.lower() else '.jpg'
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, 'wb') as f:
                f.write(response.content)
            return temp_path
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None

    def is_trigger(self, text: str) -> tuple:
        """检查是否包含触发词"""
        if "animated stickers" in text.lower():
            return (None, "")
        content = text.strip()
        content_lower = content.lower()
        keyword_lower = config.TRIGGER_KEYWORD.lower()
        if content_lower == f"{keyword_lower} hp":
            return ("command_refresh", ("hp", ""))
        if content_lower.startswith(keyword_lower):
            after_keyword = content[len(config.TRIGGER_KEYWORD):].strip()
            if after_keyword:
                return ("ai", after_keyword)
            return (None, "")
        if self.command_service:
            cmd_match = self.command_service.match_command(content)
            if cmd_match:
                return ("command", cmd_match)
        return (None, "")

    def scheduler_loop(self):
        """定时任务调度循环"""
        logger.info("定时任务调度线程启动")
        tasks = config.SCHEDULED_TASKS
        if not tasks:
            while self.running:
                time.sleep(60)
            return
        task_states = {}
        for i, task in enumerate(tasks):
            if task.get('type') == 'interval':
                task_states[i] = time.time()
            else:
                task_states[i] = ""
        while self.running:
            try:
                now = time.time()
                current_dt = datetime.datetime.now()
                current_time_str = current_dt.strftime("%H:%M")
                current_date_str = current_dt.strftime("%Y-%m-%d")
                for i, task in enumerate(tasks):
                    task_type = task.get('type')
                    content = task.get('content')
                    command_name = task.get('command')
                    if not content and not command_name:
                        continue
                    if task_type == 'interval':
                        if now - task_states.get(i, 0) >= task.get('seconds', 3600):
                            self._queue_task(task, now, i)
                            task_states[i] = now
                    elif task_type == 'daily':
                        if current_time_str == task.get('time') and task_states.get(i, "") != current_date_str:
                            self._queue_task(task, now, i)
                            task_states[i] = current_date_str
                time.sleep(1)
            except Exception as e:
                logger.error(f"调度线程出错: {e}")
                time.sleep(5)

    def _queue_task(self, task, now, i):
        content = task.get('content')
        command_name = task.get('command')
        try:
            if command_name:
                logger.info(f"⏰ 触发定时命令[{i}]: {command_name}")
                self.message_queue.put_nowait({
                    'type': 'command',
                    'content': (command_name, task.get('params', '')),
                    'timestamp': now
                })
            else:
                logger.info(f"⏰ 触发定时消息[{i}]: {content}")
                self.message_queue.put_nowait({
                    'type': 'text',
                    'content': content,
                    'timestamp': now
                })
        except queue.Full:
            logger.warning("⚠ 队列已满，跳过任务")

    def message_detector_loop(self):
        """消息检测循环"""
        logger.info("消息检测线程启动")
        initial_messages = self.wechat.get_messages()
        for i, msg in enumerate(initial_messages):
            self._mark_processed(self._hash_message_with_context(initial_messages, i))
        while self.running:
            try:
                messages = self.wechat.get_messages()
                messages_to_check = messages[-3:] if len(messages) > 3 else messages
                start_index = len(messages) - len(messages_to_check)
                new_messages = []
                for i, msg in enumerate(messages_to_check):
                    msg_hash = self._hash_message_with_context(messages, start_index + i)
                    if not self._is_processed(msg_hash):
                        new_messages.append((msg, msg_hash))
                for msg, msg_hash in new_messages:
                    self._mark_processed(msg_hash)
                    trigger_type, content = self.is_trigger(msg)
                    if trigger_type:
                        try:
                            self.message_queue.put_nowait({
                                'type': trigger_type,
                                'content': content,
                                'timestamp': time.time()
                            })
                        except queue.Full:
                            pass
                self._cleanup_old_hashes()
                time.sleep(config.CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"检测出错: {e}")
                time.sleep(1)

    def message_processor_loop(self):
        """消息处理循环"""
        logger.info("消息处理线程启动")
        while self.running:
            try:
                task = self.message_queue.get(timeout=1)
                trigger_type = task['type']
                content = task['content']
                if trigger_type == "text":
                    with self.cooldown_lock:
                        self.wechat.send_text(content)
                        self.last_trigger_time = time.time()
                    self.message_queue.task_done()
                    continue
                with self.cooldown_lock:
                    remaining = config.TRIGGER_COOLDOWN - (time.time() - self.last_trigger_time)
                    if remaining > 0:
                        time.sleep(remaining)
                    if trigger_type == "command" and self.command_service:
                        res = self.command_service.execute_command(content[0], content[1])
                        self.wechat.send_text(res if res else "执行失败")
                    elif trigger_type == "command_refresh":
                        if self.command_service.load_commands():
                            self.wechat.send_text("已经成功了")
                    elif trigger_type == "ai" and self.ai_service:
                        ans = self.ai_service.ask(content)
                        self.wechat.send_text(ans if ans else "抱歉，我现在无法回答这个问题 😅")
                    self.last_trigger_time = time.time()
                self.message_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"处理出错: {e}")

    def run(self):
        """运行机器人"""
        # 激活微信窗口
        self.wechat.activate_window()
        
        # 默认启动消息
        time.sleep(1) # 等待窗口稳定
        self.wechat.send_text("机器人已启动")
            
        self.running = True
        self.detector_thread = threading.Thread(target=self.message_detector_loop, daemon=True)
        self.processor_thread = threading.Thread(target=self.message_processor_loop, daemon=True)
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.detector_thread.start()
        self.processor_thread.start()
        self.scheduler_thread.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False

def main():
    try:
        bot = AWSlBot(config.GROUP_NAME)
        bot.run()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()