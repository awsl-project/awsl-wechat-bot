import time
import logging
import re
import uiautomation as auto
from adapters.base import BaseWeChatAdapter
from config import config

logger = logging.getLogger(__name__)

class WindowsWeChatAdapter(BaseWeChatAdapter):
    def __init__(self):
        self.window = None
        self._bind_window()

    def _bind_window(self):
        """绑定微信窗口"""
        # 支持的类名列表：新版微信使用 mmui::MainWindow
        class_names = ["mmui::MainWindow", "WeChatMainWndForPC"]
        # 支持的标题列表
        titles = ["微信", "WeChat"]
        
        for cls in class_names:
            for title in titles:
                logger.debug(f"尝试匹配: Title='{title}', Class='{cls}'")
                self.window = auto.WindowControl(searchDepth=1, Name=title, ClassName=cls)
                if self.window.Exists(0):
                    logger.info(f"成功匹配到微信窗口: {title} ({cls})")
                    return True
        
        logger.error("未发现运行中的微信窗口 (尝试了多种类名和标题)")
        return False

    def activate_window(self):
        """激活微信窗口"""
        logger.debug("正在激活微信窗口...")
        if not self.window or not self.window.Exists(0):
            if not self._bind_window():
                return
        
        try:
            # 尝试恢复最小化的窗口
            # 注意：不同版本的 uiautomation 属性可能不同
            # 使用 WindowPattern 来判断更稳妥
            if hasattr(self.window, "GetWindowPattern"):
                pattern = self.window.GetWindowPattern()
                if pattern and pattern.WindowPatternState == auto.WindowVisualState.Minimized:
                    self.window.Restore()
            elif hasattr(self.window, "IsMinimized") and self.window.IsMinimized():
                self.window.Restore()
            
            self.window.SetForeground()
            time.sleep(0.5)
            logger.debug("窗口已激活")
        except Exception as e:
            # 即使激活失败也不应该让程序崩溃，可能窗口已经被激活了
            pass

    def find_chat(self, chat_name: str) -> bool:
        """通过搜索进入聊天"""
        self.activate_window()
        
        # 快捷键 Ctrl+F 进入搜索框
        self.window.SendKeys('{Ctrl}f', waitTime=0.5)
        
        # 输入搜索内容
        search_edit = self.window.EditControl(Name="搜索")
        if search_edit.Exists(2):
            search_edit.SendKeys(chat_name)
            time.sleep(1)
            search_edit.SendKeys('{Enter}')
            logger.info(f"已尝试切换到聊天: {chat_name}")
            return True
        else:
            logger.error("未找到搜索框")
            return False

    def get_messages(self) -> list[str]:
        """获取当前聊天记录"""
        self.activate_window()
        
        logger.debug("正在查找消息列表...")
        # 方案1：通过名称查找
        msg_list = self.window.ListControl(Name="消息")
        if not msg_list.Exists(0.5):
            logger.debug("未找到名为'消息'的列表，尝试查找任意 ListControl...")
            # 方案2：查找第一个 ListControl
            msg_list = self.window.ListControl()

        if not msg_list.Exists(0):
            logger.warning("在当前窗口中未找到任何消息列表控件。")
            return []

        logger.debug("成功定位消息列表，正在提取消息...")
        messages = []
        try:
            # 遍历消息列表的子项
            for item in msg_list.GetChildren():
                # 新版微信的消息内容在子控件的 Name 属性里
                if item.ControlTypeName == 'ListItemControl':
                    text_control = item.TextControl()
                    # 有些消息是图片或表情，没有文本控件
                    if text_control.Exists(0):
                         messages.append(text_control.Name)
                    else: # 尝试直接获取 ListItemControl 的 Name
                        messages.append(item.Name)

            # 过滤噪音
            filtered_messages = []
            for text in messages:
                if not text or len(text) < 2:
                    continue
                if text in ['[图片]', '[表情]', '[视频]', '[文件]', 'Animated Stickers']:
                    continue
                if re.match(r'^[\d:]+$', text):  # 纯时间戳
                    continue
                filtered_messages.append(text)
                
            return filtered_messages
        except Exception as e:
            logger.error(f"提取消息时出错: {e}")
            return []

    def send_text(self, text: str) -> bool:
        """发送文本消息 (直接对当前焦点进行操作)"""
        # 步骤 0: 记录方法入口信息
        logger.debug(f"[send_text] 方法入口 - 文本内容: '{text}'")
        logger.debug(f"[send_text] 文本类型: {type(text)}, 长度: {len(text)}")

        # 步骤 1: 激活窗口
        logger.debug("[send_text] 步骤 1: 开始激活窗口")
        try:
            self.activate_window()
            logger.debug("[send_text] 步骤 1: 窗口激活成功")
        except Exception as e:
            logger.error(f"[send_text] 步骤 1: 窗口激活失败 - {type(e).__name__}: {e}")
            return False

        # 步骤 2: 清空可能存在的草稿
        logger.debug("[send_text] 步骤 2: 准备清空草稿")
        clear_keys = '{CTRL}a{DELETE}'
        logger.debug(f"[send_text] 步骤 2: 按键序列 - '{clear_keys}' (类型: {type(clear_keys)}, 长度: {len(clear_keys)})")
        try:
            self.window.SendKeys(clear_keys, waitTime=0.2)
            logger.debug("[send_text] 步骤 2: 清空草稿成功")
        except Exception as e:
            logger.error(f"[send_text] 步骤 2: 清空草稿失败 - {type(e).__name__}: {e}")
            logger.error(f"[send_text] 步骤 2: 异常详情", exc_info=True)
            return False

        # 步骤 3: 通过剪贴板设置文本
        logger.debug("[send_text] 步骤 3: 准备设置剪贴板")
        logger.debug(f"[send_text] 步骤 3: 剪贴板文本 - '{text}' (类型: {type(text)})")
        try:
            auto.SetClipboardText(text)
            logger.debug("[send_text] 步骤 3: 剪贴板设置成功")
            # 可选：验证剪贴板内容
            try:
                clipboard_content = auto.GetClipboardText()
                logger.debug(f"[send_text] 步骤 3: 验证剪贴板内容 - '{clipboard_content}'")
            except:
                pass
        except Exception as e:
            logger.error(f"[send_text] 步骤 3: 设置剪贴板失败 - {type(e).__name__}: {e}")
            logger.error(f"[send_text] 步骤 3: 异常详情", exc_info=True)
            return False

        # 步骤 4: 粘贴
        logger.debug("[send_text] 步骤 4: 准备粘贴")
        paste_keys = '{CTRL}v'
        logger.debug(f"[send_text] 步骤 4: 按键序列 - '{paste_keys}' (类型: {type(paste_keys)}, 长度: {len(paste_keys)})")
        try:
            self.window.SendKeys(paste_keys, waitTime=0.2)
            logger.debug("[send_text] 步骤 4: 粘贴成功")
        except Exception as e:
            logger.error(f"[send_text] 步骤 4: 粘贴失败 - {type(e).__name__}: {e}")
            logger.error(f"[send_text] 步骤 4: 异常详情", exc_info=True)
            return False

        # 步骤 5: 发送消息
        logger.debug("[send_text] 步骤 5: 准备发送消息")
        enter_keys = '{ENTER}'
        logger.debug(f"[send_text] 步骤 5: 按键序列 - '{enter_keys}' (类型: {type(enter_keys)}, 长度: {len(enter_keys)})")
        try:
            self.window.SendKeys(enter_keys, waitTime=0.2)
            logger.debug("[send_text] 步骤 5: 发送成功")
        except Exception as e:
            logger.error(f"[send_text] 步骤 5: 发送失败 - {type(e).__name__}: {e}")
            logger.error(f"[send_text] 步骤 5: 异常详情", exc_info=True)
            return False

        logger.info(f"✓ 发送成功 (直接焦点方式): {text[:20]}...")
        return True

    def send_image(self, image_path: str) -> bool:
        """发送图片 (通过复制文件到剪贴板)"""
        # 这里需要依赖 PIL 和一些 Windows API 来把图片存入剪贴板
        # 为了保持依赖精简，我们先实现一个基于文件路径复制的逻辑
        import ctypes
        from PIL import Image
        import io

        def send_to_clipboard(path):
            img = Image.open(path)
            output = io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]
            output.close()

            ctypes.windll.user32.OpenClipboard(None)
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.SetClipboardData(8, ctypes.windll.kernel32.GlobalAlloc(0x42, len(data)))
            # 简化的剪贴板操作，实际项目中可能需要更严谨的实现
            ctypes.windll.user32.CloseClipboard()

        try:
            # 这是一个复杂的 Win32 操作，暂时使用简单模拟
            # 实际最稳妥的方法是：选中文件 -> Ctrl+C -> 微信窗口 -> Ctrl+V
            self.activate_window()
            # 暂时提示：Windows 图片发送功能需要具体调试剪贴板格式
            logger.warning("Windows 图片发送功能暂未通过底层 API 完全验证，建议优先使用文本")
            return False
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False
