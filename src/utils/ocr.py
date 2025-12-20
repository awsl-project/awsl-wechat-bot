"""
OCR 工具
"""

import subprocess
import time
import os
import tempfile
from Foundation import NSURL
import Vision

from config import Config
from utils_screenshot import get_window_info, capture_screen_region, calc_screenshot_region


def ocr_image(image_path: str) -> list:
    """
    使用 macOS Vision 框架进行 OCR

    Returns:
        list: [{'text': str, 'confidence': float, 'x': float, 'y': float, 'width': float}, ...]
              x, y, width 为 0-1 的比例值
              x < 0.5 表示左侧（他人消息），x >= 0.5 表示右侧（自己消息）
    """
    image_url = NSURL.fileURLWithPath_(image_path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(image_url, None)

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(['zh-Hans', 'zh-Hant', 'en'])
    request.setAutomaticallyDetectsLanguage_(True)
    request.setMinimumTextHeight_(0.01)
    request.setCustomWords_(Config.OCR_CUSTOM_WORDS)

    success, error = handler.performRequests_error_([request], None)
    if not success:
        print(f"OCR 错误: {error}")
        return []

    results = []
    for obs in request.results():
        text = obs.topCandidates_(1)[0].string()
        conf = obs.confidence()
        bbox = obs.boundingBox()
        results.append({
            'text': text,
            'confidence': conf,
            'x': bbox.origin.x,
            'y': bbox.origin.y,
            'width': bbox.size.width,
        })

    # 按 y 坐标排序（从上到下）
    results.sort(key=lambda r: -r['y'])
    return results


def get_others_messages(ocr_results: list, confidence_threshold: float = 0.4) -> list:
    """
    从 OCR 结果中提取他人消息（左侧消息）

    内部进行位置过滤（x < 0.2）、置信度过滤、长度过滤

    Args:
        ocr_results: ocr_image 返回的结果列表
        confidence_threshold: 置信度阈值（默认 0.4）

    Returns:
        list: 消息文本列表 ['消息1', '消息2', ...]
    """
    messages = []
    for r in ocr_results:
        # 左侧消息 (x < 0.2)
        if r['x'] >= 0.2:
            continue
        # 置信度过滤
        if r['confidence'] < confidence_threshold:
            continue
        # 文本清理和长度过滤
        text = r['text'].strip()
        if len(text) >= 2:
            messages.append(text)
    return messages


def screenshot_and_ocr(process_name: str = "WeChat") -> list:
    """截图并 OCR 识别"""
    win = get_window_info(process_name)
    if not win:
        return []

    x, y, w, h = calc_screenshot_region(win)

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        screenshot_path = f.name

    try:
        capture_screen_region(x, y, w, h, screenshot_path)
        return ocr_image(screenshot_path)
    finally:
        try:
            os.remove(screenshot_path)
        except OSError:
            pass


if __name__ == "__main__":
    print("OCR 识别测试")
    print("=" * 40)

    subprocess.run(['open', '-a', 'WeChat'])
    time.sleep(1)

    win = get_window_info()
    if not win:
        print("错误: 无法获取微信窗口")
        exit(1)

    x, y, w, h = calc_screenshot_region(win)

    screenshot = "/tmp/wechat_ocr_test.png"
    capture_screen_region(x, y, w, h, screenshot)

    print(f"\n全部识别结果:")
    print("-" * 50)

    results = ocr_image(screenshot)
    for i, r in enumerate(results, 1):
        conf = f"{r['confidence']:.0%}"
        side = "左" if r['x'] < 0.2 else "右"
        print(f"[{i:2d}] [{side}] ({conf}) x={r['x']:.2f} | {r['text']}")

    print(f"\n共识别 {len(results)} 行")

    print(f"\n他人消息 (x < 0.2, 置信度 >= 40%):")
    print("-" * 50)
    others = get_others_messages(results)
    for i, msg in enumerate(others, 1):
        print(f"[{i:2d}] {msg}")
    print(f"\n共 {len(others)} 条他人消息")

    # os.remove(screenshot)
