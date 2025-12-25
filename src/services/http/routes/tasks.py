"""
定时任务路由
"""

import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from ..auth import verify_token
from ..models import ScheduledTaskCreate, ScheduledTaskUpdate, ScheduledTaskResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _task_to_response(task) -> ScheduledTaskResponse:
    """将任务对象转换为响应模型"""
    try:
        target_groups = json.loads(task.target_groups) if task.target_groups else []
    except json.JSONDecodeError:
        target_groups = []

    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        cron_expression=task.cron_expression,
        message=task.message,
        message_type=task.message_type,
        image_base64=task.image_base64 if task.message_type == "image" else "",
        target_groups=target_groups,
        enabled=task.enabled,
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_run=task.last_run
    )


def create_routes(task_service):
    """创建路由"""

    @router.get("/api/tasks", response_model=List[ScheduledTaskResponse], dependencies=[Depends(verify_token)])
    async def list_scheduled_tasks():
        """获取所有定时任务"""
        tasks = task_service.get_all_tasks()
        return [_task_to_response(task) for task in tasks]

    @router.post("/api/tasks", response_model=ScheduledTaskResponse, dependencies=[Depends(verify_token)])
    async def create_scheduled_task(request: ScheduledTaskCreate):
        """创建定时任务"""
        target_groups_json = json.dumps(request.target_groups, ensure_ascii=False)
        task = task_service.create_task(
            name=request.name,
            cron_expression=request.cron_expression,
            message=request.message or "",
            message_type=request.message_type,
            image_base64=request.image_base64 or "",
            target_groups=target_groups_json,
            enabled=True
        )

        if not task:
            raise HTTPException(status_code=400, detail="创建任务失败，请检查 cron 表达式是否正确")

        logger.info(f"[HTTP API] 创建定时任务: {task.name}")
        return _task_to_response(task)

    @router.get("/api/tasks/{task_id}", response_model=ScheduledTaskResponse, dependencies=[Depends(verify_token)])
    async def get_scheduled_task(task_id: int):
        """获取指定定时任务"""
        task = task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
        return _task_to_response(task)

    @router.put("/api/tasks/{task_id}", response_model=ScheduledTaskResponse, dependencies=[Depends(verify_token)])
    async def update_scheduled_task(task_id: int, request: ScheduledTaskUpdate):
        """更新定时任务"""
        task = task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")

        update_params = {}
        if request.name is not None:
            update_params['name'] = request.name
        if request.cron_expression is not None:
            update_params['cron_expression'] = request.cron_expression
        if request.message is not None:
            update_params['message'] = request.message
        if request.message_type is not None:
            update_params['message_type'] = request.message_type
        if request.image_base64 is not None:
            update_params['image_base64'] = request.image_base64
        if request.target_groups is not None:
            update_params['target_groups'] = json.dumps(request.target_groups, ensure_ascii=False)
        if request.enabled is not None:
            update_params['enabled'] = request.enabled

        success = task_service.update_task(task_id, **update_params)
        if not success:
            raise HTTPException(status_code=400, detail="更新任务失败")

        logger.info(f"[HTTP API] 更新定时任务: {task_id}")
        updated_task = task_service.get_task(task_id)
        return _task_to_response(updated_task)

    @router.delete("/api/tasks/{task_id}", dependencies=[Depends(verify_token)])
    async def delete_scheduled_task(task_id: int):
        """删除定时任务"""
        task = task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")

        success = task_service.delete_task(task_id)
        if not success:
            raise HTTPException(status_code=500, detail="删除任务失败")

        logger.info(f"[HTTP API] 删除定时任务: {task_id}")
        return {"success": True, "message": "任务已删除"}

    return router
