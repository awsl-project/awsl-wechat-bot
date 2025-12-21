import time
import subprocess
import re
import os
import logging
import Quartz
from src.adapters.base import BaseWeChatAdapter
from config import config
from src.utils.accessibility import get_messages_via_accessibility

logger = logging.getLogger(__name__)


class MacOSWindow:
    """macOS 单群模式的虚拟窗口对象"""

    def __init__(self, adapter, group_name: str):
        self.adapter = adapter
        self.group_name = group_name

    def Exists(self, timeout: float = 0.5) -> bool:
        """检查窗口是否存在（macOS 单群模式始终返回 True）"""
        return True


class MacOSWeChatAdapter(BaseWeChatAdapter):
    def __init__(self):
        self.process_name = self._detect_wechat_process()
        if not self.process_name:
            raise RuntimeError("微信未运行，请先启动微信")
        logger.info(f"检测到微信进程: {self.process_name}")

    def _detect_wechat_process(self) -> str:
        """检测微信进程名称"""
        result = subprocess.run(['pgrep', 'WeChat'], capture_output=True)
        if result.returncode == 0:
            return "WeChat"
        result = subprocess.run(['pgrep', '微信'], capture_output=True)
        if result.returncode == 0:
            return "微信"
        return None

    def _run_applescript(self, script: str) -> str:
        """执行 AppleScript"""
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=config.APPLESCRIPT_TIMEOUT_LONG
        )
        if result.returncode != 0:
            logger.debug(f"AppleScript 错误: {result.stderr}")
            return None
        return result.stdout.strip()

    def activate_window(self):
        """激活微信窗口"""
        subprocess.run(['open', '-a', self.process_name], check=True)
        time.sleep(0.3)

    def find_all_wechat_windows(self) -> list[dict]:
        """查找所有微信窗口（macOS 单群模式）

        Returns:
            list[dict]: 包含单个群聊窗口的列表
        """
        group_name = config.GROUP_NAME
        if not group_name:
            logger.error("macOS 需要在 .env 中配置 GROUP_NAME")
            return []

        # 切换到目标群聊
        self.find_chat(group_name)

        # 返回虚拟窗口对象
        window = MacOSWindow(self, group_name)
        logger.info(f"macOS 单群模式: 监听 [{group_name}]")
        return [{"title": group_name, "window": window}]

    def get_messages_from_window(self, window: MacOSWindow) -> list:
        """从指定窗口获取消息（macOS 单群模式）"""
        return self.get_messages()

    def send_text_to_window(self, window: MacOSWindow, text: str) -> bool:
        """向指定窗口发送消息（macOS 单群模式）"""
        return self.send_text(text)

    def send_image_to_window(self, window: MacOSWindow, image_base64: str) -> bool:
        """向指定窗口发送图片（base64编码）

        Args:
            window: 窗口对象
            image_base64: base64 编码的图片数据

        Returns:
            bool: 是否发送成功
        """
        import base64
        import tempfile
        import os

        try:
            # 解码 base64 数据
            image_data = base64.b64decode(image_base64)

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_file.write(image_data)
                tmp_path = tmp_file.name

            # 使用现有的 send_image 方法发送
            success = self.send_image(tmp_path)

            # 删除临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass

            return success
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False

    def click_input_box(self):
        """点击输入框以获得焦点"""
        script = f'''
        tell application "System Events"
            tell process "{self.process_name}"
                set wechatWindow to window 1
                set {{wx, wy}} to position of wechatWindow
                set {{ww, wh}} to size of wechatWindow
                return (wx as text) & "," & (wy as text) & "," & (ww as text) & "," & (wh as text)
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                  capture_output=True, text=True, timeout=config.APPLESCRIPT_TIMEOUT_SHORT)
        except subprocess.TimeoutExpired:
            logger.warning(f"获取窗口位置超时（{config.APPLESCRIPT_TIMEOUT_SHORT}秒）")
            return False

        if result.returncode != 0:
            logger.warning(f"获取窗口位置失败: {result.stderr}")
            return False

        try:
            wx, wy, ww, wh = map(float, result.stdout.strip().split(','))
        except Exception as e:
            logger.warning(f"解析窗口坐标失败: {e}")
            return False

        click_x = wx + ww * 0.6
        click_y = wy + wh * 0.92

        move_event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)
        time.sleep(0.05)

        mouse_down = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_down)
        time.sleep(0.05)

        mouse_up = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp, (click_x, click_y), 0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, mouse_up)
        return True

    def find_chat(self, chat_name: str) -> bool:
        """查找并切换到指定聊天窗口"""
        self.activate_window()
        time.sleep(0.2)

        script = f'''
        set the clipboard to "{chat_name}"
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "f" using command down
                delay 0.3
                keystroke "v" using command down
                delay 1.0
                key code 36
                delay 0.5
                key code 53
                delay 0.3
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(0.5)
        self.click_input_box()
        logger.info(f"已切换到聊天: {chat_name}")
        return True

    def get_messages(self) -> list:
        """获取当前聊天窗口的消息"""
        self.activate_window()
        time.sleep(0.2)
        all_messages = get_messages_via_accessibility(self.process_name)
        messages = []
        for text in all_messages:
            if len(text) < 2:
                continue
            if re.match(r'^[\d:]+$', text):
                continue
            if text in ['<', '>', 'S', '...', 'Image', 'Animated Stickers']:
                continue
            messages.append(text)
        return messages

    def send_text(self, text: str) -> bool:
        """发送文本消息"""
        self.activate_window()
        time.sleep(0.2)
        script = f'''
        set the clipboard to "{text}"
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "v" using command down
                delay 0.3
                key code 36
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(0.5)
        return True

    def send_image(self, image_path: str) -> bool:
        """发送图片"""
        script = f'''
        set theFile to POSIX file "{image_path}"
        try
            set the clipboard to (read theFile as JPEG picture)
        on error
            set the clipboard to (read theFile as «class PNGf»)
        end try
        '''
        try:
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=config.APPLESCRIPT_TIMEOUT_SHORT)
        except subprocess.TimeoutExpired:
            logger.error(f"复制图片到剪贴板超时")
            return False

        if result.returncode != 0:
            logger.error(f"复制图片失败: {result.stderr}")
            return False

        time.sleep(0.3)
        self.activate_window()
        time.sleep(0.2)
        script = f'''
        tell application "System Events"
            tell process "{self.process_name}"
                keystroke "v" using command down
                delay 0.5
                key code 36
            end tell
        end tell
        '''
        self._run_applescript(script)
        time.sleep(1.0)
        return True
