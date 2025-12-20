"""
AWSL 微信机器人配置 - 使用 Pydantic Settings
支持从环境变量读取配置
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """配置类 - 自动从环境变量读取"""

    # 触发关键词
    TRIGGER_KEYWORD: str = "awsl"

    # OCR 自定义词汇表
    OCR_CUSTOM_WORDS: list[str] = ["awsl"]

    # API 地址
    API_URL: str = "https://awsl.api.awsl.icu/v2/random_json"

    # 命令 API 地址
    COMMAND_API_BASE_URL: str = "https://bhwa233-api.vercel.app"

    # 检查消息间隔（秒）
    CHECK_INTERVAL: int = 3

    # 触发冷却时间（秒）
    TRIGGER_COOLDOWN: int = 10

    # 调试模式（输出每次检测到的所有消息）
    DEBUG: bool = False

    # AppleScript 超时配置（秒）
    APPLESCRIPT_TIMEOUT_SHORT: int = 10   # 简单操作: 窗口位置、图片复制
    APPLESCRIPT_TIMEOUT_MEDIUM: int = 20  # 中等操作: 消息获取
    APPLESCRIPT_TIMEOUT_LONG: int = 30    # 复杂操作: 深度UI遍历、窗口激活

    # 截图区域参数（暂时不使用，Accessibility API 不需要）
    SCREENSHOT_LEFT_RATIO: float = 0.30
    SCREENSHOT_TOP_RATIO: float = 0.06
    SCREENSHOT_WIDTH_RATIO: float = 0.65
    SCREENSHOT_HEIGHT_RATIO: float = 0.75

    # OpenAI 配置（从环境变量读取）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_TOKENS: int = 500
    OPENAI_TEMPERATURE: float = 0.7

    # 定时任务配置
    # 示例:
    # [
    #     {"type": "daily", "time": "09:00", "content": "早安！"},
    #     {"type": "interval", "seconds": 3600, "command": "ss", "params": ""}
    # ]
    SCHEDULED_TASKS: list[dict] = [
        {"type": "interval", "seconds": 3600, "command": "ss"}
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# 创建全局配置实例
config = Config()
