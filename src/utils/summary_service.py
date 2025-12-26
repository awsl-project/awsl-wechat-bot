"""
群聊总结服务 - 统一的总结调用入口

提供带锁的总结功能，确保同一时间只有一个总结任务运行。
供 API 和定时任务统一调用。
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SummaryGroup:
    """群聊配置"""
    group_id: str
    group_name: str


@dataclass
class SummaryConfig:
    """总结配置"""
    input_path: str
    key: str
    output_path: str
    api_base: str
    groups: List[SummaryGroup]
    date: Optional[str] = None  # YYYY-MM-DD，默认为今天
    token: Optional[str] = None


@dataclass
class SummaryResult:
    """总结结果"""
    success: bool
    message: str
    details: Optional[dict] = None


class SummaryService:
    """群聊总结服务（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._running_lock = threading.Lock()
        self._is_running = False
        self._initialized = True

    @property
    def is_running(self) -> bool:
        """检查是否有总结正在运行"""
        return self._is_running

    def run_summary(self, config: SummaryConfig) -> SummaryResult:
        """
        执行群聊总结（同步阻塞）

        Args:
            config: 总结配置

        Returns:
            SummaryResult: 执行结果
        """
        # 尝试获取锁
        if not self._running_lock.acquire(blocking=False):
            return SummaryResult(
                success=False,
                message="已有总结任务正在运行，请稍后再试"
            )

        self._is_running = True

        try:
            return self._execute_summary(config)
        except Exception as e:
            logger.exception("[Summary] 总结执行失败")
            return SummaryResult(
                success=False,
                message=f"总结执行失败: {str(e)}"
            )
        finally:
            self._is_running = False
            self._running_lock.release()

    def start_summary_async(
        self,
        config: SummaryConfig,
        on_complete: Optional[callable] = None
    ) -> SummaryResult:
        """
        异步启动总结任务（非阻塞）

        Args:
            config: 总结配置
            on_complete: 完成回调函数，接收 SummaryResult 参数

        Returns:
            SummaryResult: 启动结果（success=True 表示已启动，False 表示已有任务运行）
        """
        import threading

        # 尝试获取锁
        if not self._running_lock.acquire(blocking=False):
            return SummaryResult(
                success=False,
                message="已有总结任务正在运行，请稍后再试"
            )

        self._is_running = True

        def run_and_release():
            try:
                result = self._execute_summary(config)
                if on_complete:
                    on_complete(result)
            except Exception as e:
                logger.exception("[Summary] 总结执行失败")
                if on_complete:
                    on_complete(SummaryResult(
                        success=False,
                        message=f"总结执行失败: {str(e)}"
                    ))
            finally:
                self._is_running = False
                self._running_lock.release()

        thread = threading.Thread(target=run_and_release, daemon=True)
        thread.start()

        return SummaryResult(
            success=True,
            message="总结任务已启动"
        )

    def _execute_summary(self, config: SummaryConfig) -> SummaryResult:
        """执行总结的内部逻辑"""
        import sys
        import os

        # 添加项目根目录到路径
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from tools.chat_summary import (
            decrypt_database,
            fetch_messages,
            format_messages_for_llm,
            generate_ranking,
            summarize_with_llm,
            render_to_image,
            send_image_to_group
        )
        from config import config as app_config

        results = {
            "decrypt": None,
            "groups": {}
        }

        # 1. 解密数据库
        logger.info(f"[Summary] 开始解密数据库: {config.input_path} -> {config.output_path}")
        try:
            decrypt_result = decrypt_database(
                api_base=config.api_base,
                input_path=config.input_path,
                key=config.key,
                output_path=config.output_path,
                token=config.token
            )
            results["decrypt"] = decrypt_result
            logger.info(f"[Summary] 数据库解密完成: {decrypt_result}")
        except Exception as e:
            logger.error(f"[Summary] 数据库解密失败: {e}")
            return SummaryResult(
                success=False,
                message=f"数据库解密失败: {str(e)}",
                details=results
            )

        # 2. 确定日期范围
        if config.date:
            try:
                target_date = datetime.strptime(config.date, "%Y-%m-%d")
            except ValueError:
                return SummaryResult(
                    success=False,
                    message=f"无效的日期格式: {config.date}"
                )
        else:
            target_date = datetime.now()

        date_str = target_date.strftime("%Y-%m-%d")
        next_date_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
        start_time = f"{date_str} 05:00:00"
        end_time = f"{next_date_str} 05:00:00"

        # 3. 为每个群生成总结
        success_count = 0
        fail_count = 0

        for group in config.groups:
            group_result = {
                "success": False,
                "message": "",
                "msg_count": 0
            }

            try:
                logger.info(f"[Summary] 处理群聊: {group.group_name} ({group.group_id})")

                # 获取聊天记录
                messages = fetch_messages(
                    api_base=config.api_base,
                    db_path=config.output_path,
                    group=group.group_id,
                    start=start_time,
                    end=end_time,
                    limit=2000,
                    token=config.token
                )

                logger.info(f"[Summary] 获取到 {len(messages)} 条消息")

                if not messages:
                    group_result["message"] = "没有消息记录"
                    results["groups"][group.group_id] = group_result
                    continue

                messages_text, valid_count, sender_counts = format_messages_for_llm(messages)
                group_result["msg_count"] = valid_count

                if valid_count == 0:
                    group_result["message"] = "没有有效消息"
                    results["groups"][group.group_id] = group_result
                    continue

                # 生成排行榜
                ranking = generate_ranking(sender_counts)

                # 生成总结
                logger.info("[Summary] 调用 LLM 生成总结...")
                summary = summarize_with_llm(
                    messages_text=messages_text,
                    group_name=group.group_name,
                    date_str=date_str,
                    api_url=app_config.OPENAI_BASE_URL,
                    api_key=app_config.OPENAI_API_KEY,
                    model=app_config.OPENAI_MODEL
                )

                # 合并总结和排行榜
                summary = summary + "\n\n" + ranking
                gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 渲染图片
                output_image = os.path.join(config.output_path, f"summary_{group.group_id}_{date_str}.png")
                logger.info(f"[Summary] 渲染图片: {output_image}")

                if not render_to_image(summary, date_str, valid_count, gen_time, output_image):
                    group_result["message"] = "图片渲染失败"
                    results["groups"][group.group_id] = group_result
                    fail_count += 1
                    continue

                # 发送图片
                logger.info(f"[Summary] 发送图片到群聊: {group.group_name}")
                send_image_to_group(
                    api_base=config.api_base,
                    group_name=group.group_name,
                    image_path=output_image,
                    token=config.token
                )

                group_result["success"] = True
                group_result["message"] = "成功"
                results["groups"][group.group_id] = group_result
                success_count += 1
                logger.info(f"[Summary] 群聊 {group.group_name} 总结完成")

            except Exception as e:
                logger.exception(f"[Summary] 处理群聊 {group.group_name} 失败")
                group_result["message"] = str(e)
                results["groups"][group.group_id] = group_result
                fail_count += 1

        # 汇总结果
        total = len(config.groups)
        if fail_count == 0:
            return SummaryResult(
                success=True,
                message=f"全部完成: {success_count}/{total} 个群聊",
                details=results
            )
        elif success_count > 0:
            return SummaryResult(
                success=True,
                message=f"部分完成: {success_count}/{total} 成功, {fail_count}/{total} 失败",
                details=results
            )
        else:
            return SummaryResult(
                success=False,
                message=f"全部失败: {fail_count}/{total} 个群聊",
                details=results
            )


# 全局实例
_summary_service = SummaryService()


def run_chat_summary(config: SummaryConfig) -> SummaryResult:
    """
    执行群聊总结（同步阻塞）

    Args:
        config: 总结配置

    Returns:
        SummaryResult: 执行结果
    """
    return _summary_service.run_summary(config)


def start_chat_summary_async(
    config: SummaryConfig,
    on_complete: callable = None
) -> SummaryResult:
    """
    异步启动总结任务（非阻塞）

    Args:
        config: 总结配置
        on_complete: 完成回调函数，接收 SummaryResult 参数

    Returns:
        SummaryResult: 启动结果（success=True 表示已启动，False 表示已有任务运行）
    """
    return _summary_service.start_summary_async(config, on_complete)


def is_summary_running() -> bool:
    """检查是否有总结正在运行"""
    return _summary_service.is_running
