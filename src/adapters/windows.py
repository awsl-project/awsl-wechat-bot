import time
import logging
import re
import uiautomation as auto
from src.adapters.base import BaseWeChatAdapter
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
            # 尝试多种方法恢复最小化的窗口
            try:
                if hasattr(self.window, "ShowWindow"):
                    self.window.ShowWindow(1)  # SW_SHOWNORMAL
            except:
                pass

            try:
                if hasattr(self.window, "Restore"):
                    self.window.Restore()
            except:
                pass

            # 激活窗口
            self.window.SetForeground()
            time.sleep(0.5)
            logger.debug("窗口已激活")
        except Exception as e:
            # 即使激活失败也不应该让程序崩溃，可能窗口已经被激活了
            logger.debug(f"激活窗口时出现警告: {e}")

    def find_all_wechat_windows(self) -> list[dict]:
        """查找所有微信窗口（包括弹出的群聊窗口）

        Returns:
            list[dict]: 窗口信息列表，每个字典包含：
                - title: 窗口标题（群名）
                - window: WindowControl 对象
                - class: 窗口类名
        """
        logger.info("正在扫描所有微信窗口...")
        all_windows = []

        # 支持的类名列表
        # mmui::MainWindow - 主窗口
        # mmui::ChatSingleWindow - 弹出的群聊窗口
        # WeChatMainWndForPC - 旧版微信主窗口
        class_names = ["mmui::MainWindow", "mmui::ChatSingleWindow", "WeChatMainWndForPC"]
        main_titles = ["微信", "WeChat"]

        # 遍历所有可能的类名
        for cls in class_names:
            try:
                # 获取根控件并查找所有匹配的窗口
                root = auto.GetRootControl()
                controls = root.GetChildren()

                for ctrl in controls:
                    try:
                        if ctrl.ClassName == cls and ctrl.Exists(0):
                            title = ctrl.Name
                            # 跳过空标题
                            if not title:
                                continue

                            all_windows.append({
                                "title": title,
                                "window": ctrl,
                                "class": cls
                            })
                            logger.debug(f"发现窗口: {title} ({cls})")
                    except:
                        continue
            except Exception as e:
                logger.warning(f"扫描类名 {cls} 时出错: {e}")
                continue

        # 过滤掉主窗口（标题为"微信"或"WeChat"）
        popup_windows = [
            w for w in all_windows
            if w["title"] not in main_titles
        ]

        logger.info(f"找到 {len(popup_windows)} 个群聊窗口")
        return popup_windows

    def activate_specific_window(self, window):
        """激活指定的微信窗口

        Args:
            window: WindowControl 对象
        """
        logger.debug(f"正在激活窗口: {window.Name}")
        try:
            # 尝试多种方法恢复最小化的窗口
            try:
                # 方法1：使用 ShowWindow
                if hasattr(window, "ShowWindow"):
                    window.ShowWindow(1)  # SW_SHOWNORMAL
            except:
                pass

            try:
                # 方法2：使用 Restore
                if hasattr(window, "Restore"):
                    window.Restore()
            except:
                pass

            # 激活窗口
            window.SetForeground()
            time.sleep(0.5)
            logger.debug(f"窗口已激活: {window.Name}")
        except Exception as e:
            logger.debug(f"激活窗口时出现警告: {e}")

    def get_messages_from_window(self, window) -> list[str]:
        """从指定窗口获取消息

        Args:
            window: WindowControl 对象

        Returns:
            list[str]: 消息列表
        """
        self.activate_specific_window(window)

        logger.debug("正在查找消息列表...")
        # 方案1：通过名称查找
        msg_list = window.ListControl(Name="消息")
        if not msg_list.Exists(0.5):
            logger.debug("未找到名为'消息'的列表，尝试查找任意 ListControl...")
            # 方案2：查找第一个 ListControl
            msg_list = window.ListControl()

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

    def send_text_to_window(self, window, text: str) -> bool:
        """向指定窗口发送文本消息

        Args:
            window: WindowControl 对象
            text: 要发送的文本

        Returns:
            bool: 是否发送成功
        """
        logger.debug(f"[send_text_to_window] 向窗口 {window.Name} 发送: {text[:20]}...")

        # 激活窗口
        self.activate_specific_window(window)

        try:
            # 清空可能存在的草稿
            window.SendKeys('{CTRL}a{DELETE}', waitTime=0.2)

            # 通过剪贴板设置文本
            auto.SetClipboardText(text)

            # 验证剪贴板内容
            clipboard_content = auto.GetClipboardText()
            if clipboard_content != text:
                if config.DEBUG:
                    logger.debug(f"剪贴板截断！原始长度={len(text)} 剪贴板长度={len(clipboard_content)}")
                    logger.debug(f"原始内容: {repr(text)}")
                    logger.debug(f"剪贴板内容: {repr(clipboard_content)}")

                # 使用 Windows API 重新设置
                import win32clipboard
                import win32con
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                win32clipboard.CloseClipboard()

                if config.DEBUG:
                    logger.debug("已使用 win32clipboard 重新设置剪贴板")

            # 粘贴
            window.SendKeys('{CTRL}v', waitTime=0.2)

            # 发送消息
            window.SendKeys('{ENTER}', waitTime=0.2)

            logger.info(f"✓ 发送成功到 [{window.Name}]: {text[:20]}...")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    def send_image_to_window(self, window, image_base64: str) -> bool:
        """向指定窗口发送图片（base64编码）

        Args:
            window: WindowControl 对象
            image_base64: base64 编码的图片数据

        Returns:
            bool: 是否发送成功
        """
        import base64
        from PIL import Image
        import win32clipboard
        import io

        logger.debug(f"[send_image_to_window] 向窗口 {window.Name} 发送图片...")

        # 激活窗口
        self.activate_specific_window(window)

        try:
            # 解码 base64 数据
            image_data = base64.b64decode(image_base64)

            # 使用 PIL 读取图片
            img = Image.open(io.BytesIO(image_data))

            # 转换为 BMP 格式（Windows 剪贴板支持）
            output = io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            bmp_data = output.getvalue()[14:]  # 移除 BMP 文件头
            output.close()

            # 复制到剪贴板
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
            win32clipboard.CloseClipboard()

            time.sleep(0.3)

            # 粘贴图片
            window.SendKeys('{CTRL}v', waitTime=0.5)

            # 发送
            window.SendKeys('{ENTER}', waitTime=0.2)

            logger.info(f"✓ 图片发送成功到 [{window.Name}]")
            return True
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False

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

            # 验证剪贴板内容
            clipboard_content = auto.GetClipboardText()
            logger.debug(f"[send_text] 步骤 3: 验证剪贴板内容 - '{clipboard_content}'")

            if clipboard_content != text:
                logger.warning(f"[send_text] 剪贴板截断！原始长度={len(text)} 剪贴板长度={len(clipboard_content)}")

                # 使用 Windows API 重新设置
                import win32clipboard
                import win32con
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                win32clipboard.CloseClipboard()

                logger.debug("[send_text] 步骤 3: 已使用 win32clipboard 重新设置")

            logger.debug("[send_text] 步骤 3: 剪贴板设置成功")
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
        try:
            from PIL import Image
            import win32clipboard
            import io

            # 读取图片并转换为 BMP 格式（Windows 剪贴板支持）
            img = Image.open(image_path)
            output = io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]  # 移除 BMP 文件头
            output.close()

            # 复制到剪贴板
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

            # 激活窗口并粘贴
            self.activate_window()
            time.sleep(0.3)

            # 粘贴图片
            self.window.SendKeys('{CTRL}v', waitTime=0.5)

            # 发送
            self.window.SendKeys('{ENTER}', waitTime=0.2)

            logger.info("✓ 图片发送成功")
            return True
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False
