"""
聊天记录查询路由
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from config import config
from ..auth import verify_token
from ..models import (
    ChatlogDecryptRequest, ChatlogGroupResponse, ChatlogMessageResponse,
    ChatSummaryRequest, ChatSummaryResponse
)
from src.utils.wechat_chatlog import WeChatDBDecryptor, WeChatDBReader, HAS_CRYPTO
from src.utils.summary_service import start_chat_summary_async, SummaryConfig, SummaryGroup, SummaryResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chatlog", tags=["chatlog"])


def create_routes():
    """创建路由"""

    @router.post("/decrypt", dependencies=[Depends(verify_token)])
    async def decrypt_database(request: ChatlogDecryptRequest):
        """解密微信数据库"""
        if not HAS_CRYPTO:
            raise HTTPException(status_code=500, detail="服务器缺少 pycryptodome 依赖")

        if not os.path.isdir(request.input_path):
            raise HTTPException(status_code=400, detail=f"输入目录不存在: {request.input_path}")

        try:
            decryptor = WeChatDBDecryptor(request.key)
            count = decryptor.decrypt_directory(request.input_path, request.output_path)
            logger.info(f"[HTTP API] 解密完成: {count} 个文件")
            return {
                "success": True,
                "message": f"成功解密 {count} 个文件",
                "count": count,
                "output_path": request.output_path
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"[HTTP API] 解密失败: {e}")
            raise HTTPException(status_code=500, detail=f"解密失败: {str(e)}")

    @router.get("/groups", response_model=List[ChatlogGroupResponse], dependencies=[Depends(verify_token)])
    async def list_chat_groups(
        db_path: str = Query(..., description="解密后的数据库目录"),
        limit: int = Query(0, description="限制返回数量，0 表示不限制")
    ):
        """列出所有群聊"""
        if not os.path.isdir(db_path):
            raise HTTPException(status_code=400, detail=f"目录不存在: {db_path}")

        reader = WeChatDBReader(db_path)
        try:
            groups = reader.list_groups(limit=limit)
            return [
                ChatlogGroupResponse(
                    username=g.username,
                    owner=g.owner,
                    remark=g.remark,
                    nick_name=g.nick_name,
                    display_name=g.display_name()
                )
                for g in groups
            ]
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"[HTTP API] 列出群聊失败: {e}")
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
        finally:
            reader.close()

    @router.get("/messages", response_model=List[ChatlogMessageResponse], dependencies=[Depends(verify_token)])
    async def query_messages(
        db_path: str = Query(..., description="解密后的数据库目录"),
        group: str = Query(..., description="群聊ID 或个人微信ID"),
        start: Optional[str] = Query(None, description="开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
        end: Optional[str] = Query(None, description="结束时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
        limit: int = Query(100, description="限制返回数量")
    ):
        """查询聊天记录"""
        if not os.path.isdir(db_path):
            raise HTTPException(status_code=400, detail=f"目录不存在: {db_path}")

        start_time = end_time = None
        try:
            if start:
                fmt = "%Y-%m-%d %H:%M:%S" if " " in start else "%Y-%m-%d"
                start_time = datetime.strptime(start, fmt)
            if end:
                fmt = "%Y-%m-%d %H:%M:%S" if " " in end else "%Y-%m-%d"
                end_time = datetime.strptime(end, fmt)
                if " " not in end:
                    end_time = end_time.replace(hour=23, minute=59, second=59)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效的时间格式: {e}")

        reader = WeChatDBReader(db_path)
        try:
            messages = reader.get_messages(
                talker=group,
                start_time=start_time,
                end_time=end_time,
                text_only=True,
                limit=limit
            )
            return [
                ChatlogMessageResponse(
                    seq=m.seq,
                    time=m.time.isoformat(),
                    talker=m.talker,
                    sender=m.sender,
                    sender_name=m.sender_name,
                    msg_type=m.msg_type,
                    content=m.content,
                    is_self=m.is_self
                )
                for m in messages
            ]
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"[HTTP API] 查询消息失败: {e}")
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
        finally:
            reader.close()

    @router.post("/summary", response_model=ChatSummaryResponse, dependencies=[Depends(verify_token)])
    async def send_chat_summary(request: ChatSummaryRequest):
        """
        发送群聊总结

        异步启动解密和总结任务。同一时间只允许一个总结任务运行。
        """
        # 构建配置
        summary_config = SummaryConfig(
            input_path=request.input_path,
            key=request.key,
            output_path=request.output_path,
            api_base=request.api_base,
            groups=[SummaryGroup(group_id=g.group_id, group_name=g.group_name) for g in request.groups],
            token=config.HTTP_API_TOKEN or None
        )

        group_names = [g.group_name for g in request.groups]

        # 完成回调
        def on_complete(result: SummaryResult):
            if result.success:
                logger.info(f"[HTTP API] 群聊总结任务完成: {result.message}")
            else:
                logger.error(f"[HTTP API] 群聊总结任务失败: {result.message}")

        # 异步启动任务（内部已处理锁和线程）
        result = start_chat_summary_async(summary_config, on_complete)

        if not result.success:
            return ChatSummaryResponse(
                success=False,
                message=result.message
            )

        logger.info(f"[HTTP API] 已启动群聊总结任务: {group_names}")
        return ChatSummaryResponse(
            success=True,
            message=f"已启动群聊总结任务，目标群聊: {', '.join(group_names)}"
        )

    return router
