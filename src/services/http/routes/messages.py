"""
消息发送路由
"""

import logging
import queue
import time

from fastapi import APIRouter, HTTPException, Depends

from ..auth import verify_token
from ..models import SendMessageRequest, SendMessageResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def create_routes(bot_instance):
    """创建路由"""

    @router.post("/api/send", response_model=SendMessageResponse, dependencies=[Depends(verify_token)])
    async def send_message(request: SendMessageRequest):
        """向指定聊天窗口发送消息或图片"""
        if not request.message and not request.image_base64:
            raise HTTPException(status_code=400, detail="必须提供 message 或 image_base64 参数")

        target_group = None
        for group in bot_instance.groups:
            if group["name"] == request.group_name:
                target_group = group
                break

        if not target_group:
            raise HTTPException(status_code=404, detail=f"未找到群组: {request.group_name}")

        if not target_group["window"].Exists(0.5):
            raise HTTPException(status_code=400, detail=f"群组窗口已关闭: {request.group_name}")

        try:
            task_data = {
                'group_name': request.group_name,
                'window': target_group["window"],
                'timestamp': time.time()
            }

            if request.image_base64:
                task_data['type'] = 'image'
                task_data['content'] = request.image_base64
                message_type = "图片"
            elif request.message:
                task_data['type'] = 'text'
                task_data['content'] = request.message
                message_type = "文本消息"

            try:
                bot_instance.message_queue.put_nowait(task_data)
                logger.info(f"[HTTP API] {message_type}已加入队列，目标: [{request.group_name}]")
                return SendMessageResponse(success=True, message=f"{message_type}已加入发送队列")
            except queue.Full:
                raise HTTPException(status_code=503, detail="消息队列已满，请稍后重试")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[HTTP API] 加入队列失败: {e}")
            raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")

    return router
