from abc import ABC, abstractmethod

class BaseWeChatAdapter(ABC):
    """微信操作适配器基类"""
    
    @abstractmethod
    def find_chat(self, chat_name: str) -> bool:
        """查找并进入指定聊天窗口"""
        pass

    @abstractmethod
    def get_messages(self) -> list[str]:
        """获取当前聊天窗口的消息列表"""
        pass

    @abstractmethod
    def send_text(self, text: str) -> bool:
        """发送文本消息"""
        pass

    @abstractmethod
    def send_image(self, image_path: str) -> bool:
        """发送图片消息"""
        pass

    @abstractmethod
    def activate_window(self):
        """激活微信窗口"""
        pass

    @abstractmethod
    def find_all_wechat_windows(self) -> list[dict]:
        """查找所有微信窗口（用于多群监听）

        Returns:
            list[dict]: 窗口信息列表，每个字典包含：
                - title: 窗口标题（群名）
                - window: 窗口控制对象
        """
        pass
