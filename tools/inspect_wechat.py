import uiautomation as auto
import sys

def inspect_chat_content():
    """
    深入探测微信窗口内的 ListControl，寻找聊天记录
    """
    sys.stdout.reconfigure(encoding='utf-8')
    print("正在寻找微信窗口...")
    
    # 尝试绑定窗口
    wechat_window = None
    class_names = ["mmui::MainWindow", "WeChatMainWndForPC"]
    titles = ["微信", "WeChat"]
    
    for cls in class_names:
        for title in titles:
            win = auto.WindowControl(searchDepth=1, Name=title, ClassName=cls)
            if win.Exists(0):
                wechat_window = win
                print(f"找到窗口: {title} ({cls})")
                break
        if wechat_window: break
    
    if not wechat_window:
        print("未找到微信窗口！请确保微信已打开。")
        return

    print("\n正在扫描窗口内的所有列表控件 (ListControl)...")
    lists = wechat_window.GetChildren() # 这里可能只获取直系子节点，我们需要深度搜索吗？
    # 为了保险，我们用 WalkControl 遍历
    
    count = 0
    for control, depth in auto.WalkControl(wechat_window, maxDepth=5):
        if control.ControlTypeName == 'ListControl':
            count += 1
            print(f"\nFound ListControl #{count}: Name='{control.Name}', AutomationId='{control.AutomationId}'")
            print("-" * 30)
            
            # 打印前5个子项的内容
            children = control.GetChildren()
            if not children:
                print("  (空列表)")
                continue
                
            print(f"  包含 {len(children)} 个子项。前 5 项内容预览:")
            for i, child in enumerate(children[:5]):
                # 尝试获取文本
                content = child.Name
                print(f"    [{i}] Type={child.ControlTypeName}, Name='{content}'")
                
                # 如果 Name 为空，尝试找下级 TextControl
                if not content:
                    texts = child.GetChildren()
                    for t in texts:
                        print(f"       -> Sub: Type={t.ControlTypeName}, Name='{t.Name}'")
            print("-" * 30)

    if count == 0:
        print("\n[!] 竟然没有找到任何 ListControl？微信可能使用了非标准控件。")

if __name__ == "__main__":
    inspect_chat_content()