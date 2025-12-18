"""
远程命令服务
动态加载和管理来自 API 的命令
"""

import requests
import logging
from typing import Dict, List, Optional, Tuple
from config import config

logger = logging.getLogger(__name__)


class CommandService:
    """管理动态命令的服务类"""

    def __init__(self):
        self.api_base_url = config.COMMAND_API_BASE_URL
        self.commands: List[Dict] = []
        self.command_keys: List[str] = []

    def load_commands(self) -> bool:
        """
        从 API 加载命令列表

        Returns:
            bool: 是否成功加载
        """
        try:
            response = requests.get(
                f"{self.api_base_url}/api/command/hp",
                headers={'accept': 'application/json'},
                timeout=30
            )
            response.raise_for_status()

            # 加载命令列表并过滤掉 'hp' 命令
            all_commands = response.json()
            self.commands = [cmd for cmd in all_commands if cmd['key'].strip().lower() != 'hp']
            self.command_keys = [cmd['key'] for cmd in self.commands]

            logger.info(f"成功加载 {len(self.commands)} 个命令")
            logger.info(f"命令列表: {self.command_keys}")
            return True

        except Exception as e:
            logger.error(f"加载命令列表失败: {e}")
            return False

    def match_command(self, text: str) -> Optional[Tuple[str, str]]:
        """
        匹配命令

        Args:
            text: 用户输入的文本

        Returns:
            Tuple[command_key, params] 或 None
            - command_key: 命令的 key（不含空格）
            - params: 命令参数（如果有）
        """
        text_lower = text.lower().strip()
        logger.debug(f"尝试匹配命令: '{text_lower}'")

        # 按 key 长度从长到短排序，优先匹配长的命令（避免 "s" 匹配到 "ss"）
        sorted_keys = sorted(self.command_keys, key=len, reverse=True)

        for key in sorted_keys:
            key_lower = key.lower().strip()

            # 前缀匹配
            if text_lower.startswith(key_lower):
                # 提取参数（如果有）
                params = ""
                if len(text_lower) > len(key_lower):
                    params = text[len(key_lower):].strip()
                logger.debug(f"匹配成功: 命令='{key_lower}', 参数='{params}'")
                return (key_lower, params)

        logger.debug(f"未找到匹配的命令")
        return None

    def execute_command(self, command_key: str, params: str = "") -> Optional[str]:
        """
        执行命令并返回结果

        Args:
            command_key: 命令的 key（不含空格）
            params: 命令参数

        Returns:
            str: 命令执行结果文本，失败返回 None
        """
        try:
            # 构建 API URL
            url = f"{self.api_base_url}/api/command"

            # 构建完整的命令字符串（命令 + 参数）
            full_command = command_key
            if params:
                full_command = f"{command_key} {params}"

            # query string 只包含 command 参数
            query_params = {'command': full_command}

            logger.info(f"调用命令 API: {url} with params: {query_params}")

            response = requests.get(
                url,
                params=query_params,
                headers={'accept': 'application/json'},
                timeout=30
            )
            response.raise_for_status()

            # 解析响应 - API 返回格式 {"content": "...", "type": "text"}
            data = response.json()
            response_content = data.get('content', '')

            return response_content

        except Exception as e:
            logger.error(f"执行命令 {command_key} 失败: {e}")
            return None

    def _format_response(self, data) -> str:
        """格式化 API 响应为可读文本"""
        if isinstance(data, str):
            return data
        elif isinstance(data, list):
            # 数组类型，逐行显示
            return '\n'.join(str(item) for item in data)
        elif isinstance(data, dict):
            # 字典类型，格式化显示
            lines = []
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{key}: {str(value)}")
                else:
                    lines.append(f"{key}: {value}")
            return '\n'.join(lines)
        else:
            return str(data)

    def get_help_text(self) -> str:
        """获取命令帮助文本"""
        if not self.commands:
            return "命令列表为空，请检查网络连接"

        help_lines = ["可用命令："]
        for cmd in self.commands:
            help_lines.append(f"  {cmd['description']}")

        return '\n'.join(help_lines)
