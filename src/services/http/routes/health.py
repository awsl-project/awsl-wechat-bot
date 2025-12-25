"""
健康检查和首页路由
"""

import os
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from config import config

router = APIRouter()


def create_routes(bot_instance):
    """创建路由"""

    @router.get("/", response_class=HTMLResponse)
    async def root():
        """Web UI 首页"""
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'templates',
            'index.html'
        )
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "<h1>模板文件未找到</h1>"

    @router.get("/api/health")
    async def health():
        """健康检查"""
        return {
            "status": "healthy",
            "groups_count": len(bot_instance.groups),
            "server_time": datetime.now().isoformat(),
            "timezone": time.strftime("%Z"),
            "timezone_offset": time.strftime("%z"),
            "auth_enabled": bool(config.HTTP_API_TOKEN)
        }

    return router
