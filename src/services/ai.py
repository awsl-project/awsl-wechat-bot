#!/usr/bin/env python3
"""
AI 服务模块 - 使用 OpenAI API 回复问题
"""

import logging
import requests
from config import config

logger = logging.getLogger(__name__)


class AIService:
    """AI 服务类，使用 HTTPS 请求与 OpenAI API 交互"""

    def __init__(self):
        """初始化 AI 服务"""
        self.api_url = f"{config.OPENAI_BASE_URL}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        logger.info(f"AI 服务初始化完成，API: {config.OPENAI_BASE_URL}")

    def ask(self, question: str, system_prompt: str = None) -> str:
        """
        向 AI 提问并获取回复

        Args:
            question: 用户问题
            system_prompt: 系统提示词（可选）

        Returns:
            AI 的回复文本，如果失败则返回 None
        """
        try:
            messages = []

            # 添加系统提示词
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": "你是一个友好、有趣的 AI 助手，用简洁、幽默的方式回答问题。"
                })

            # 添加用户问题
            messages.append({"role": "user", "content": question})

            logger.info(f"正在向 AI 提问: {question}")

            # 构建请求数据
            payload = {
                "model": config.OPENAI_MODEL,
                "messages": messages,
                "max_tokens": config.OPENAI_MAX_TOKENS,
                "temperature": config.OPENAI_TEMPERATURE,
            }

            # 发送 HTTPS 请求
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            # 解析响应
            data = response.json()
            answer = data['choices'][0]['message']['content'].strip()
            logger.info(f"AI 回复: {answer[:100]}...")
            return answer

        except requests.exceptions.RequestException as e:
            logger.error(f"AI 请求失败: {e}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"AI 响应解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"AI 请求异常: {e}")
            return None
