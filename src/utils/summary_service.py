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
            extract_overview,
            build_summary_text,
            summarize_with_llm,
            render_to_image,
            send_image_to_group,
            send_text_to_group
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
            # 指定日期：使用该日期的 05:00 到次日 05:00
            try:
                target_date = datetime.strptime(config.date, "%Y-%m-%d")
            except ValueError:
                return SummaryResult(
                    success=False,
                    message=f"无效的日期格式: {config.date}"
                )
            date_str = target_date.strftime("%Y-%m-%d")
            file_date_str = date_str  # 用于文件名
            next_date_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
            start_time = f"{date_str} 05:00:00"
            end_time = f"{next_date_str} 05:00:00"
        else:
            # 未指定日期：从最近的凌晨5点到当前时间
            now = datetime.now()
            today_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now >= today_5am:
                start_datetime = today_5am
            else:
                start_datetime = today_5am - timedelta(days=1)
            date_str = f"{start_datetime.strftime('%Y-%m-%d %H:%M')} ~ {now.strftime('%Y-%m-%d %H:%M')}"
            file_date_str = now.strftime("%Y-%m-%d_%H%M")  # 用于文件名
            start_time = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")

        # 3. 读取群名称
        name_reader = None
        try:
            from src.utils.wechat_chatlog import WeChatDBReader
            name_reader = WeChatDBReader(config.output_path)
        except Exception:
            name_reader = None

        # 4. 为每个群生成总结
        success_count = 0
        fail_count = 0

        for group in config.groups:
            display_group_name = group.group_name
            if name_reader:
                try:
                    display_group_name = name_reader.get_group_display_name(group.group_id)
                except Exception:
                    display_group_name = group.group_name
            group_result = {
                "success": False,
                "message": "",
                "msg_count": 0
            }

            try:
                logger.info(f"[Summary] 处理群聊: {display_group_name} ({group.group_id})")

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

                messages_text, valid_count, sender_stats = format_messages_for_llm(messages)
                group_result["msg_count"] = valid_count

                if valid_count == 0:
                    group_result["message"] = "没有有效消息"
                    results["groups"][group.group_id] = group_result
                    continue

                # 生成排行榜
                ranking = generate_ranking(sender_stats)

                # 生成总结
                logger.info("[Summary] 调用 LLM 生成总结...")
                try:
                    summary = summarize_with_llm(
                        messages_text=messages_text,
                        group_name=display_group_name,
                        date_str=date_str,
                        api_url=app_config.OPENAI_BASE_URL,
                        api_key=app_config.OPENAI_API_KEY,
                        model=app_config.OPENAI_MODEL
                    )
                except Exception as e:
                    logger.error(f"[Summary] LLM 总结失败: {e}")
                    group_result["message"] = f"LLM 总结失败: {str(e)}"
                    results["groups"][group.group_id] = group_result
                    fail_count += 1
                    continue

                # 验证 LLM 返回结果
                if not summary or len(summary.strip()) < 50:
                    logger.error(f"[Summary] LLM 返回内容无效或过短")
                    group_result["message"] = "LLM 返回内容无效"
                    results["groups"][group.group_id] = group_result
                    fail_count += 1
                    continue

                logger.info(f"[Summary] LLM 总结成功，长度: {len(summary)}")

                # 合并总结和排行榜
                overview = extract_overview(summary)
                summary = summary + "\n\n" + ranking
                text_message = build_summary_text(overview, ranking, display_group_name)
                gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 渲染图片（使用绝对路径）
                output_dir = os.path.abspath(config.output_path)
                os.makedirs(output_dir, exist_ok=True)
                output_image = os.path.join(output_dir, f"summary_{group.group_id}_{file_date_str}.png")
                logger.info(f"[Summary] 渲染图片: {output_image}")

                if not render_to_image(summary, date_str, valid_count, gen_time, output_image, display_group_name):
                    group_result["message"] = "图片渲染失败"
                    results["groups"][group.group_id] = group_result
                    fail_count += 1
                    continue

                # 验证图片文件存在
                if not os.path.exists(output_image):
                    logger.error(f"[Summary] 图片文件不存在: {output_image}")
                    group_result["message"] = "图片文件不存在"
                    results["groups"][group.group_id] = group_result
                    fail_count += 1
                    continue

                logger.info(f"[Summary] 图片渲染成功: {output_image}")

                # 发送图片
                logger.info(f"[Summary] 发送图片到群聊: {group.group_name}")
                send_image_to_group(
                    api_base=config.api_base,
                    group_name=group.group_name,
                    image_path=output_image,
                    token=config.token
                )
                try:
                    send_text_to_group(
                        api_base=config.api_base,
                        group_name=group.group_name,
                        message=text_message,
                        token=config.token
                    )
                except Exception as e:
                    logger.warning(f"[Summary] 文本消息发送失败 [{group.group_name}]: {e}")

                group_result["success"] = True
                group_result["message"] = "成功"
                results["groups"][group.group_id] = group_result
                success_count += 1
                logger.info(f"[Summary] 群聊 {display_group_name} 总结完成")

            except Exception as e:
                logger.exception(f"[Summary] 处理群聊 {display_group_name} 失败")
                group_result["message"] = str(e)
                results["groups"][group.group_id] = group_result
                fail_count += 1

        # 汇总结果
        if name_reader:
            try:
                name_reader.close()
            except Exception:
                pass
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
