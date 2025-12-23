"""
定时任务服务
支持基于 cron 表达式的定时任务管理
"""

import logging
import sqlite3
import threading
from datetime import datetime
from typing import Optional, List, Dict
from croniter import croniter

logger = logging.getLogger(__name__)


class ScheduledTask:
    """定时任务模型"""

    def __init__(
        self,
        id: Optional[int] = None,
        name: str = "",
        cron_expression: str = "",
        message: str = "",
        message_type: str = "text",  # "text" or "image"
        image_base64: str = "",  # base64 encoded image for message_type="image"
        target_groups: str = "",  # JSON string of group names, empty = all groups
        enabled: bool = True,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        last_run: Optional[str] = None
    ):
        self.id = id
        self.name = name
        self.cron_expression = cron_expression
        self.message = message
        self.message_type = message_type
        self.image_base64 = image_base64
        self.target_groups = target_groups
        self.enabled = enabled
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_run = last_run

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "cron_expression": self.cron_expression,
            "message": self.message,
            "message_type": self.message_type,
            "image_base64": self.image_base64,
            "target_groups": self.target_groups,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run": self.last_run
        }


class ScheduledTaskService:
    """定时任务服务"""

    def __init__(self, db_path: str):
        """
        初始化定时任务服务

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)

        # 启用 WAL 模式以支持并发读写
        self.conn.execute('PRAGMA journal_mode=WAL')
        # 设置更短的超时时间
        self.conn.execute('PRAGMA busy_timeout=5000')

        self.db_lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with self.db_lock:
            # 检查表是否存在
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_tasks'"
            )
            table_exists = cursor.fetchone() is not None

            if table_exists:
                # 检查是否需要添加新字段
                cursor = self.conn.execute("PRAGMA table_info(scheduled_tasks)")
                columns = [row[1] for row in cursor.fetchall()]

                # 添加 message_type 字段
                if 'message_type' not in columns:
                    logger.info("添加 message_type 字段到数据库...")
                    self.conn.execute("ALTER TABLE scheduled_tasks ADD COLUMN message_type TEXT DEFAULT 'text'")

                # 添加 image_base64 字段
                if 'image_base64' not in columns:
                    logger.info("添加 image_base64 字段到数据库...")
                    self.conn.execute("ALTER TABLE scheduled_tasks ADD COLUMN image_base64 TEXT DEFAULT ''")

                self.conn.commit()
            else:
                # 创建新表（使用本地时间而不是 UTC）
                self.conn.execute('''
                    CREATE TABLE scheduled_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        cron_expression TEXT NOT NULL,
                        message TEXT NOT NULL,
                        message_type TEXT DEFAULT 'text',
                        image_base64 TEXT DEFAULT '',
                        target_groups TEXT DEFAULT '',
                        enabled INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                        updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                        last_run TIMESTAMP
                    )
                ''')
                self.conn.commit()

            logger.info("定时任务数据库初始化完成")

    def validate_cron_expression(self, cron_expr: str) -> bool:
        """
        验证 cron 表达式是否有效

        Args:
            cron_expr: cron 表达式

        Returns:
            是否有效
        """
        try:
            croniter(cron_expr)
            return True
        except Exception as e:
            logger.debug(f"无效的 cron 表达式 '{cron_expr}': {e}")
            return False

    def create_task(
        self,
        name: str,
        cron_expression: str,
        message: str = "",
        message_type: str = "text",
        image_base64: str = "",
        target_groups: str = "",
        enabled: bool = True
    ) -> Optional[ScheduledTask]:
        """
        创建定时任务

        Args:
            name: 任务名称
            cron_expression: cron 表达式
            message: 要发送的消息（message_type为text时）
            message_type: 消息类型，"text" 或 "image"
            image_base64: base64编码的图片（message_type为image时）
            target_groups: 目标群组（JSON字符串），空字符串表示所有群
            enabled: 是否启用

        Returns:
            创建的任务对象，失败返回 None
        """
        if not self.validate_cron_expression(cron_expression):
            logger.error(f"创建任务失败：无效的 cron 表达式 '{cron_expression}'")
            return None

        with self.db_lock:
            try:
                cursor = self.conn.execute(
                    '''INSERT INTO scheduled_tasks
                       (name, cron_expression, message, message_type, image_base64, target_groups, enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (name, cron_expression, message, message_type, image_base64, target_groups, 1 if enabled else 0)
                )
                self.conn.commit()
                task_id = cursor.lastrowid

                # 返回创建的任务
                return self.get_task(task_id)
            except sqlite3.Error as e:
                logger.error(f"创建定时任务失败: {e}")
                return None

    def get_task(self, task_id: int) -> Optional[ScheduledTask]:
        """
        获取指定 ID 的任务

        Args:
            task_id: 任务 ID

        Returns:
            任务对象，不存在返回 None
        """
        # 读操作不需要锁，WAL 模式支持并发读
        cursor = self.conn.execute(
            'SELECT * FROM scheduled_tasks WHERE id = ?',
            (task_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_task(row)
        return None

    def get_all_tasks(self) -> List[ScheduledTask]:
        """
        获取所有任务

        Returns:
            任务列表
        """
        # 读操作不需要锁，WAL 模式支持并发读
        cursor = self.conn.execute('SELECT * FROM scheduled_tasks ORDER BY id DESC')
        rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def get_enabled_tasks(self) -> List[ScheduledTask]:
        """
        获取所有已启用的任务

        Returns:
            已启用的任务列表
        """
        # 读操作不需要锁，WAL 模式支持并发读
        cursor = self.conn.execute(
            'SELECT * FROM scheduled_tasks WHERE enabled = 1 ORDER BY id'
        )
        rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_task(
        self,
        task_id: int,
        name: Optional[str] = None,
        cron_expression: Optional[str] = None,
        message: Optional[str] = None,
        message_type: Optional[str] = None,
        image_base64: Optional[str] = None,
        target_groups: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """
        更新定时任务

        Args:
            task_id: 任务 ID
            name: 任务名称
            cron_expression: cron 表达式
            message: 消息内容
            message_type: 消息类型
            image_base64: 图片base64
            target_groups: 目标群组
            enabled: 是否启用

        Returns:
            是否成功
        """
        # 验证 cron 表达式
        if cron_expression is not None and not self.validate_cron_expression(cron_expression):
            logger.error(f"更新任务失败：无效的 cron 表达式 '{cron_expression}'")
            return False

        with self.db_lock:
            try:
                # 构建更新语句
                updates = []
                params = []

                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                if cron_expression is not None:
                    updates.append("cron_expression = ?")
                    params.append(cron_expression)
                if message is not None:
                    updates.append("message = ?")
                    params.append(message)
                if message_type is not None:
                    updates.append("message_type = ?")
                    params.append(message_type)
                if image_base64 is not None:
                    updates.append("image_base64 = ?")
                    params.append(image_base64)
                if target_groups is not None:
                    updates.append("target_groups = ?")
                    params.append(target_groups)
                if enabled is not None:
                    updates.append("enabled = ?")
                    params.append(1 if enabled else 0)

                if not updates:
                    return True

                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(task_id)

                query = f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE id = ?"
                self.conn.execute(query, params)
                self.conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"更新定时任务失败: {e}")
                return False

    def delete_task(self, task_id: int) -> bool:
        """
        删除定时任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        with self.db_lock:
            try:
                self.conn.execute('DELETE FROM scheduled_tasks WHERE id = ?', (task_id,))
                self.conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"删除定时任务失败: {e}")
                return False

    def update_last_run(self, task_id: int):
        """
        更新任务的最后运行时间

        Args:
            task_id: 任务 ID
        """
        with self.db_lock:
            try:
                # 使用 UTC 时间（CURRENT_TIMESTAMP），与 should_run 中的 UTC 比较保持一致
                self.conn.execute(
                    'UPDATE scheduled_tasks SET last_run = CURRENT_TIMESTAMP WHERE id = ?',
                    (task_id,)
                )
                self.conn.commit()
            except sqlite3.Error as e:
                logger.error(f"更新任务运行时间失败: {e}")

    def should_run(self, task: ScheduledTask, current_time: datetime) -> bool:
        """
        检查任务是否应该运行

        Args:
            task: 任务对象
            current_time: 当前本地时间（用于 cron 计算）

        Returns:
            是否应该运行
        """
        if not task.enabled:
            return False

        try:
            # 使用 croniter 检查是否到了执行时间（基于本地时间）
            cron = croniter(task.cron_expression, current_time)
            # 获取上次应该运行的时间（本地时间）
            prev_run_local = cron.get_prev(datetime)

            # 获取下次应该运行的时间
            next_run = cron.get_next(datetime)

            # 计算当前时间距离上次应该执行的时间差（秒）
            time_since_prev = (current_time - prev_run_local).total_seconds()

            # 如果距离上次执行时间在30秒内，认为当前在执行窗口内
            # 窗口设置为30秒，容忍调度器5秒检查间隔的延迟（最多6次检查机会）
            in_execution_window = 0 <= time_since_prev <= 30

            # 如果从未运行过，只有在执行窗口内才运行
            if task.last_run is None or not task.last_run.strip():
                return in_execution_window

            # 解析最后运行时间（数据库存储的是 UTC 时间）
            try:
                # 尝试多种时间格式
                last_run_str = task.last_run.replace('Z', '+00:00')
                # SQLite CURRENT_TIMESTAMP 格式: YYYY-MM-DD HH:MM:SS (UTC)
                if ' ' in last_run_str and '+' not in last_run_str:
                    last_run_utc = datetime.strptime(last_run_str, '%Y-%m-%d %H:%M:%S')
                else:
                    last_run_utc = datetime.fromisoformat(last_run_str)
            except (ValueError, AttributeError) as e:
                logger.warning(f"无法解析任务 {task.id} 的 last_run 时间 '{task.last_run}': {e}，视为从未运行")
                return in_execution_window

            # 将本地时间的 prev_run 转换为 UTC 进行比较
            # 计算本地时间与 UTC 的时差
            utc_offset = datetime.now() - datetime.utcnow()
            prev_run_utc = prev_run_local - utc_offset

            # 比较两个 UTC 时间：如果上次应该运行的时间在最后运行时间之后，且当前在执行窗口内，说明需要运行
            return prev_run_utc > last_run_utc and in_execution_window
        except Exception as e:
            logger.error(f"检查任务 {task.id} 运行时间失败: {e}")
            return False

    def _row_to_task(self, row: tuple) -> ScheduledTask:
        """
        将数据库行转换为任务对象

        Args:
            row: 数据库行

        Returns:
            任务对象
        """
        return ScheduledTask(
            id=row[0],
            name=row[1],
            cron_expression=row[2],
            message=row[3],
            message_type=row[4] if len(row) > 10 else "text",  # 新增字段，兼容旧数据
            image_base64=row[5] if len(row) > 10 else "",  # 新增字段，兼容旧数据
            target_groups=row[6] if len(row) > 10 else row[4],  # 兼容旧数据
            enabled=bool(row[7] if len(row) > 10 else row[5]),  # 兼容旧数据
            created_at=row[8] if len(row) > 10 else row[6],  # 兼容旧数据
            updated_at=row[9] if len(row) > 10 else row[7],  # 兼容旧数据
            last_run=row[10] if len(row) > 10 else row[8]  # 兼容旧数据
        )

    def close(self):
        """关闭数据库连接"""
        with self.db_lock:
            self.conn.close()
