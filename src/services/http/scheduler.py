"""
定时任务调度器
"""

import json
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self, task_service, bot_instance):
        self.task_service = task_service
        self.bot = bot_instance
        self.running = False
        self.thread = None
        self.execution_lock = threading.Lock()
        self.executing_tasks = set()

    def start(self):
        """启动调度器"""
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("定时任务调度器已启动")

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("定时任务调度器已停止")

    def _loop(self):
        """调度循环"""
        logger.info("定时任务调度线程启动")

        while self.running:
            try:
                current_time = datetime.now()
                tasks = self.task_service.get_enabled_tasks()

                for task in tasks:
                    if self.task_service.should_run(task, current_time):
                        self._execute_task(task)

                time.sleep(5)
            except Exception as e:
                logger.error(f"定时任务调度出错: {e}", exc_info=True)
                time.sleep(5)

        logger.info("定时任务调度线程退出")

    def _execute_task(self, task):
        """执行任务"""
        with self.execution_lock:
            if task.id in self.executing_tasks:
                logger.debug(f"任务 {task.name} 正在执行中，跳过")
                return
            self.executing_tasks.add(task.id)

        try:
            logger.info(f"⏰ 执行定时任务: {task.name} - {task.message_type}")
            self.task_service.update_last_run(task.id)

            try:
                target_groups = json.loads(task.target_groups) if task.target_groups else []
            except json.JSONDecodeError:
                target_groups = []

            if not target_groups:
                groups_to_send = self.bot.groups
            else:
                groups_to_send = [g for g in self.bot.groups if g["name"] in target_groups]

            for group in groups_to_send:
                if not group["window"].Exists(0.5):
                    logger.debug(f"群 [{group['name']}] 窗口已关闭，跳过")
                    continue

                try:
                    if task.message_type == "image":
                        self.bot.wechat.send_image_to_window(group["window"], task.image_base64)
                        logger.info(f"⏰ 定时任务图片已发送到 [{group['name']}]")
                    else:
                        self.bot.wechat.send_text_to_window(group["window"], task.message)
                        logger.info(f"⏰ 定时任务消息已发送到 [{group['name']}]")
                except Exception as e:
                    logger.error(f"⏰ 定时任务发送失败 [{group['name']}]: {e}")
        finally:
            with self.execution_lock:
                self.executing_tasks.discard(task.id)
