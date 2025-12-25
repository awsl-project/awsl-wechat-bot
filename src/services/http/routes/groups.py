"""
群组路由
"""

import logging

from fastapi import APIRouter, Depends

from ..auth import verify_token
from ..models import GroupInfo

logger = logging.getLogger(__name__)
router = APIRouter()


def create_routes(bot_instance):
    """创建路由"""

    @router.get("/api/groups", response_model=list[GroupInfo], dependencies=[Depends(verify_token)])
    async def list_groups():
        """列出所有聊天窗口"""
        groups = []
        for group in bot_instance.groups:
            try:
                is_active = group["window"].Exists(0.5)
                groups.append(GroupInfo(name=group["name"], active=is_active))
            except Exception as e:
                logger.error(f"检查群组 {group['name']} 状态失败: {e}")
                groups.append(GroupInfo(name=group["name"], active=False))
        return groups

    return router
