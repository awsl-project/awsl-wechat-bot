"""
HTTP API 服务器
"""

import logging
import os

from fastapi import FastAPI
import uvicorn

from ..scheduled_task import ScheduledTaskService
from .scheduler import TaskScheduler
from .routes import health, groups, messages, tasks, chatlog

logger = logging.getLogger(__name__)


class HTTPServer:
    """HTTP API 服务器"""

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.app = FastAPI(
            title="AWSL WeChat Bot API",
            description="微信机器人 HTTP API 服务",
            version="1.0.0"
        )

        # 初始化定时任务服务
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            'scheduled_tasks.db'
        )
        self.task_service = ScheduledTaskService(db_path)

        # 初始化调度器
        self.scheduler = TaskScheduler(self.task_service, bot_instance)

        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""
        # 健康检查和首页
        self.app.include_router(health.create_routes(self.bot))

        # 群组路由
        self.app.include_router(groups.create_routes(self.bot))

        # 消息发送路由
        self.app.include_router(messages.create_routes(self.bot))

        # 定时任务路由
        self.app.include_router(tasks.create_routes(self.task_service))

        # 聊天记录路由
        self.app.include_router(chatlog.create_routes())

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """运行 HTTP 服务器"""
        self.scheduler.start()
        logger.info(f"启动 HTTP API 服务器: http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port, log_level="info")
