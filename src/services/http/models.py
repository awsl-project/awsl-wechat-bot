"""
HTTP API 数据模型
"""

from typing import Optional, List
from pydantic import BaseModel


# ============================================================
# 消息相关
# ============================================================

class SendMessageRequest(BaseModel):
    """发送消息请求"""
    group_name: str
    message: Optional[str] = None
    image_base64: Optional[str] = None


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    success: bool
    message: str


class GroupInfo(BaseModel):
    """群组信息"""
    name: str
    active: bool


# ============================================================
# 定时任务相关
# ============================================================

class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求"""
    name: str
    cron_expression: str
    message: Optional[str] = ""
    message_type: str = "text"
    image_base64: Optional[str] = ""
    target_groups: List[str] = []


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求"""
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    message: Optional[str] = None
    message_type: Optional[str] = None
    image_base64: Optional[str] = None
    target_groups: Optional[List[str]] = None
    enabled: Optional[bool] = None


class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""
    id: int
    name: str
    cron_expression: str
    message: str
    message_type: str
    image_base64: str
    target_groups: List[str]
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_run: Optional[str] = None


# ============================================================
# 聊天记录相关
# ============================================================

class ChatlogDecryptRequest(BaseModel):
    """解密数据库请求"""
    input_path: str
    key: str
    output_path: str


class ChatlogQueryRequest(BaseModel):
    """查询聊天记录请求"""
    db_path: str
    group: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int = 100


class ChatlogGroupResponse(BaseModel):
    """群聊信息响应"""
    username: str
    owner: str
    remark: str
    nick_name: str
    display_name: str


class ChatlogMessageResponse(BaseModel):
    """消息响应"""
    seq: int
    time: str
    talker: str
    sender: str
    sender_name: str
    msg_type: int
    content: str
    is_self: bool
