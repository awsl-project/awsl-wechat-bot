#!/usr/bin/env python3
"""
Windows 窗口诊断工具
用于检查所有微信相关窗口的详细信息
"""

import uiautomation as auto

def find_all_windows():
    """查找所有顶层窗口"""
    print("=" * 60)
    print("正在扫描所有顶层窗口...")
    print("=" * 60)

    root = auto.GetRootControl()
    all_windows = []

    # 获取所有顶层窗口
    for window in root.GetChildren():
        try:
            if not window.Exists(0):
                continue

            class_name = window.ClassName
            title = window.Name

            # 只关注微信相关窗口
            is_wechat = False
            if "wechat" in class_name.lower() or "微信" in title or "WeChat" in title:
                is_wechat = True
            elif "mmui" in class_name.lower():
                is_wechat = True

            if is_wechat:
                all_windows.append({
                    "class": class_name,
                    "title": title,
                    "window": window
                })
        except Exception as e:
            continue

    return all_windows

def main():
    windows = find_all_windows()

    if not windows:
        print("\n❌ 未找到任何微信相关窗口！")
        print("\n建议：")
        print("1. 确认微信已经启动")
        print("2. 双击弹出一些群聊窗口")
        print("3. 重新运行此工具")
        return

    print(f"\n找到 {len(windows)} 个微信相关窗口：\n")

    for i, w in enumerate(windows, 1):
        print(f"窗口 {i}:")
        print(f"  类名: {w['class']}")
        print(f"  标题: {w['title']}")
        print(f"  是否存在: {w['window'].Exists(0)}")

        # 判断窗口类型
        if w['title'] in ['微信', 'WeChat']:
            print(f"  类型: 主窗口 ⭐")
        else:
            print(f"  类型: 可能是群聊窗口 ✓")

        print()

    # 统计
    main_windows = [w for w in windows if w['title'] in ['微信', 'WeChat']]
    popup_windows = [w for w in windows if w['title'] not in ['微信', 'WeChat']]

    print("=" * 60)
    print(f"统计：")
    print(f"  主窗口: {len(main_windows)} 个")
    print(f"  弹出窗口: {len(popup_windows)} 个")
    print("=" * 60)

    if not popup_windows:
        print("\n提示：")
        print("没有找到弹出的群聊窗口！")
        print("请按以下步骤操作：")
        print("1. 打开微信主窗口")
        print("2. 找到要监听的群聊")
        print("3. 双击群聊，将其弹出为独立窗口")
        print("4. 重新运行此诊断工具检查")
    else:
        print("\n✓ 找到弹出窗口，可以启动 main.py 了！")

if __name__ == "__main__":
    main()
