"""
Accessibility API 工具 - 使用 macOS Accessibility API 获取微信消息
比 OCR 更准确、更快速
"""

import subprocess
import os
import logging
from config import config

logger = logging.getLogger(__name__)


def get_messages_via_accessibility(process_name: str = "WeChat") -> list:
    """
    通过 Accessibility API 获取微信消息

    Args:
        process_name: 微信进程名称

    Returns:
        list: 消息文本列表 ['消息1', '消息2', ...]
    """
    script_path = os.path.join(
        os.path.dirname(__file__),
        'get_messages.applescript'
    )

    if not os.path.exists(script_path):
        logger.error(f"找不到 AppleScript 文件: {script_path}")
        return []

    try:
        result = subprocess.run(
            ['osascript', script_path],
            capture_output=True,
            text=True,
            timeout=config.APPLESCRIPT_TIMEOUT_MEDIUM  # 消息获取使用中等超时
        )

        if result.returncode != 0:
            logger.error(f"AppleScript 执行失败: {result.stderr}")
            return []

        output = result.stdout.strip()

        if output.startswith("ERROR:"):
            logger.error(f"获取消息失败: {output[6:]}")
            return []

        if output.startswith("SUCCESS:"):
            messages_str = output[8:]
            if messages_str == "NO_MESSAGES":
                return []

            # 解析消息
            messages = messages_str.split("|||")

            # 返回非空消息
            return [msg.strip() for msg in messages if msg.strip()]

        logger.error(f"未知响应格式: {output}")
        return []

    except subprocess.TimeoutExpired:
        logger.error(f"AppleScript 执行超时（{config.APPLESCRIPT_TIMEOUT_MEDIUM}秒），可能原因：")
        logger.error("  1. 微信无响应或卡顿")
        logger.error("  2. 系统负载过高")
        logger.error("  3. UI结构复杂，遍历时间过长")
        return []
    except Exception as e:
        logger.error(f"获取消息异常: {e}")
        return []


def main():
    """测试 Accessibility API 消息提取"""
    print("=" * 60)
    print("Accessibility API 消息提取测试")
    print("=" * 60)
    print()

    # 配置日志
    logging.basicConfig(level=logging.INFO)

    print("正在获取微信消息...")
    results = get_messages_via_accessibility("WeChat")

    if not results:
        print("✗ 未能获取消息")
        print()
        print("可能的原因:")
        print("1. 微信未运行")
        print("2. 没有打开聊天窗口")
        print("3. 辅助功能权限未授予")
        return

    print(f"✓ 成功获取 {len(results)} 条消息")
    print()

    print("消息内容:")
    print("-" * 60)
    for i, msg in enumerate(results, 1):
        print(f"{i:2d}. {msg}")

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
