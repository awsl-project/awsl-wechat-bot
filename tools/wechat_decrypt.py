#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeChat Database Key Dumper

根据 wx_key.dll 提取微信数据库密钥。
需要以管理员身份运行。

依赖:
    pip install psutil

使用方法:
    python wechat_decrypt.py
"""

import ctypes
import os
import sys
import time
from ctypes import c_bool, c_char_p, c_int, c_uint32, create_string_buffer, POINTER
from pathlib import Path
from typing import Optional, Tuple, List

try:
    import psutil
except ImportError:
    print("请安装 psutil: pip install psutil")
    sys.exit(1)


class WeChatKeyDumper:
    """微信密钥提取器，封装 wx_key.dll 的调用"""

    def __init__(self, dll_path: str):
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"找不到 DLL 文件: {dll_path}")

        self.dll = ctypes.CDLL(dll_path)
        self._setup_functions()
        self._initialized = False

    def _setup_functions(self):
        """设置 DLL 函数的参数和返回类型"""
        self.dll.InitializeHook.argtypes = [c_uint32]
        self.dll.InitializeHook.restype = c_bool

        self.dll.PollKeyData.argtypes = [c_char_p, c_int]
        self.dll.PollKeyData.restype = c_bool

        self.dll.GetStatusMessage.argtypes = [c_char_p, c_int, POINTER(c_int)]
        self.dll.GetStatusMessage.restype = c_bool

        self.dll.CleanupHook.argtypes = []
        self.dll.CleanupHook.restype = c_bool

        self.dll.GetLastErrorMsg.argtypes = []
        self.dll.GetLastErrorMsg.restype = c_char_p

    def initialize(self, pid: int) -> bool:
        result = self.dll.InitializeHook(c_uint32(pid))
        if result:
            self._initialized = True
        return result

    def poll_key(self) -> Optional[str]:
        key_buffer = create_string_buffer(128)
        if self.dll.PollKeyData(key_buffer, 128):
            return key_buffer.value.decode('utf-8')
        return None

    def get_status_messages(self) -> List[Tuple[int, str]]:
        messages = []
        msg_buffer = create_string_buffer(512)
        level = c_int()
        while self.dll.GetStatusMessage(msg_buffer, 512, ctypes.byref(level)):
            messages.append((level.value, msg_buffer.value.decode('utf-8')))
        return messages

    def get_last_error(self) -> str:
        error = self.dll.GetLastErrorMsg()
        return error.decode('utf-8') if error else "未知错误"

    def cleanup(self):
        if self._initialized:
            self.dll.CleanupHook()
            self._initialized = False
            print("[INFO] Hook 已卸载")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def find_wechat_process() -> Optional[int]:
    """查找微信主进程 PID（选择内存占用最大的）"""
    candidates = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in ('wechat.exe', 'weixin.exe'):
                mem = proc.info['memory_info'].rss if proc.info['memory_info'] else 0
                candidates.append((proc.info['pid'], mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not candidates:
        return None

    # 选择内存占用最大的进程（通常是主进程）
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def kill_wechat() -> bool:
    """关闭所有微信进程"""
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in ('wechat.exe', 'weixin.exe'):
                proc.kill()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def find_wechat_exe() -> Optional[str]:
    """查找微信安装路径"""
    import winreg

    # 尝试从注册表读取
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Tencent\WeChat", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Tencent\WeChat", "InstallPath"),
    ]

    for root, key_path, value_name in reg_paths:
        try:
            with winreg.OpenKey(root, key_path) as key:
                install_path, _ = winreg.QueryValueEx(key, value_name)
                exe_path = Path(install_path) / "WeChat.exe"
                if exe_path.exists():
                    return str(exe_path)
                exe_path = Path(install_path) / "Weixin.exe"
                if exe_path.exists():
                    return str(exe_path)
        except:
            pass

    # 尝试常见路径
    common_paths = [
        r"C:\Program Files\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files\Tencent\Weixin\Weixin.exe",
        r"D:\Program Files\Tencent\WeChat\WeChat.exe",
        r"D:\Program Files\Tencent\Weixin\Weixin.exe",
    ]

    for path in common_paths:
        if Path(path).exists():
            return path

    return None


def launch_wechat(exe_path: str) -> bool:
    """启动微信"""
    import subprocess
    try:
        subprocess.Popen([exe_path], creationflags=subprocess.DETACHED_PROCESS)
        return True
    except:
        return False


def wait_for_wechat_ready(timeout: int = 30) -> Optional[int]:
    """等待微信进程启动并加载 Weixin.dll"""
    start = time.time()
    while time.time() - start < timeout:
        pid = find_wechat_process()
        if pid:
            try:
                proc = psutil.Process(pid)
                for mmap in proc.memory_maps():
                    if 'weixin.dll' in mmap.path.lower():
                        return pid
            except:
                pass
        time.sleep(0.5)
    return find_wechat_process()  # 超时后返回当前 PID（如果有）


def main():
    print("WeChat Key Dumper")
    print("=" * 40)

    if sys.platform != 'win32':
        print("[ERROR] 仅支持 Windows")
        sys.exit(1)

    # 检查管理员权限
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False

    if not is_admin:
        print("[WARNING] 建议以管理员身份运行")

    # 定位 DLL
    script_dir = Path(__file__).parent
    dll_path = script_dir / "assets" / "dll" / "wx_key.dll"
    if not dll_path.exists():
        dll_path = script_dir / "wx_key.dll"
    if not dll_path.exists():
        print(f"[ERROR] 找不到 wx_key.dll")
        sys.exit(1)

    # 查找微信安装路径
    wechat_exe = find_wechat_exe()
    if not wechat_exe:
        print("[ERROR] 未找到微信安装路径")
        sys.exit(1)
    print(f"[INFO] 微信路径: {wechat_exe}")

    # 检查微信是否正在运行
    existing_pid = find_wechat_process()
    if existing_pid:
        print(f"[INFO] 检测到微信正在运行 (PID: {existing_pid})")
        print("[INFO] 需要重启微信才能捕获密钥")
        response = input("[?] 是否关闭微信并重启? (Y/n): ").strip().lower()
        if response == 'n':
            print("[INFO] 已取消")
            sys.exit(0)

        print("[INFO] 正在关闭微信...")
        kill_wechat()
        time.sleep(2)

    # 启动微信
    print("[INFO] 正在启动微信...")
    if not launch_wechat(wechat_exe):
        print("[ERROR] 启动微信失败")
        sys.exit(1)

    # 等待微信启动
    print("[INFO] 等待微信加载...")
    pid = wait_for_wechat_ready(timeout=30)
    if not pid:
        print("[ERROR] 等待微信启动超时")
        sys.exit(1)
    print(f"[INFO] 微信 PID: {pid}")

    # 安装 Hook
    try:
        with WeChatKeyDumper(str(dll_path)) as dumper:
            if not dumper.initialize(pid):
                print(f"[ERROR] 初始化失败: {dumper.get_last_error()}")
                sys.exit(1)

            print("\n[SUCCESS] Hook 安装成功!")
            print("[INFO] 请在微信中登录，密钥将自动捕获...")
            print("-" * 40)

            for _ in range(1200):  # 最多等待 120 秒
                for level, msg in dumper.get_status_messages():
                    prefix = ["INFO", "SUCCESS", "ERROR"][level] if level < 3 else "INFO"
                    print(f"[{prefix}] {msg}")

                key = dumper.poll_key()
                if key:
                    print("\n" + "=" * 40)
                    print(f"[KEY] {key}")
                    print("=" * 40)
                    return

                time.sleep(0.1)

            print("[ERROR] 超时，未能获取密钥")

    except KeyboardInterrupt:
        print("\n[INFO] 已取消")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
