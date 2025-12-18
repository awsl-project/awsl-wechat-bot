"""
AWSL 微信机器人配置 - 使用 Pydantic Settings
支持从环境变量读取配置
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """配置类 - 自动从环境变量读取"""

    # 群聊名称
    GROUP_NAME: str = "PY 交易群·小米红米·安卓机"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# 创建全局配置实例
config = Config()
