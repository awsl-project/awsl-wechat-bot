"""
截图工具
"""

import subprocess
import time
from config import Config


def get_window_info(process_name: str = "WeChat") -> dict:
    """获取微信窗口位置和大小"""
    script = f'''
    tell application "System Events"
        tell process "{process_name}"
            set win to window 1
            set winPos to position of win
            set winSize to size of win
            return (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
        end tell
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=Config.APPLESCRIPT_TIMEOUT_SHORT)
    except subprocess.TimeoutExpired:
        print(f"获取窗口信息超时（{Config.APPLESCRIPT_TIMEOUT_SHORT}秒）")
        return None

    if result.returncode == 0:
        parts = result.stdout.strip().split(',')
        return {
            'x': int(parts[0]),
            'y': int(parts[1]),
            'w': int(parts[2]),
            'h': int(parts[3])
        }
    return None


def capture_screen_region(x: int, y: int, w: int, h: int, output_path: str):
    """截取屏幕区域"""
    subprocess.run(['screencapture', '-R', f'{x},{y},{w},{h}', '-x', output_path], check=True)


def calc_screenshot_region(win: dict) -> tuple:
    """根据窗口信息计算截图区域"""
    x = win['x'] + int(win['w'] * Config.SCREENSHOT_LEFT_RATIO)
    y = win['y'] + int(win['h'] * Config.SCREENSHOT_TOP_RATIO)
    w = int(win['w'] * Config.SCREENSHOT_WIDTH_RATIO)
    h = int(win['h'] * Config.SCREENSHOT_HEIGHT_RATIO)
    return x, y, w, h


if __name__ == "__main__":
    print("截图区域测试")
    print("=" * 40)

    subprocess.run(['open', '-a', 'WeChat'])
    time.sleep(1)

    win = get_window_info()
    if not win:
        print("错误: 无法获取微信窗口")
        exit(1)

    print(f"窗口: ({win['x']}, {win['y']}) {win['w']}x{win['h']}")

    x, y, w, h = calc_screenshot_region(win)
    print(f"截图: ({x}, {y}) {w}x{h}")

    output = "/tmp/wechat_screenshot.png"
    capture_screen_region(x, y, w, h, output)

    print(f"已保存: {output}")
    subprocess.run(['open', output])
