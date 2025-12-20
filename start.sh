#!/bin/bash

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 虚拟环境路径
VENV_DIR="$SCRIPT_DIR/venv"

# 检查虚拟环境是否存在
if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 虚拟环境不存在: $VENV_DIR"
    echo "请先创建虚拟环境: python -m venv venv"
    exit 1
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

LOG_FILE="bot.log"
MAX_LINES=1000
CHECK_INTERVAL=3600  # 每小时检查一次（秒）

# 清理函数（保持 inode 不变，让 tail -f 继续工作）
cleanup_log() {
    if [ -f "$LOG_FILE" ]; then
        LINE_COUNT=$(wc -l < "$LOG_FILE")
        if [ "$LINE_COUNT" -gt "$MAX_LINES" ]; then
            tail -n "$MAX_LINES" "$LOG_FILE" > "$LOG_FILE.tmp"
            cat "$LOG_FILE.tmp" > "$LOG_FILE"
            rm -f "$LOG_FILE.tmp"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 日志已清理，保留 $MAX_LINES 行（原 $LINE_COUNT 行）"
        fi
    fi
}

# 信号处理 - 优雅退出
cleanup_on_exit() {
    echo ""
    echo "收到停止信号，正在关闭..."
    if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
        kill "$BOT_PID"
        echo "机器人已停止"
    fi
    exit 0
}

trap cleanup_on_exit SIGINT SIGTERM

# 启动前清理
if [ -f "$LOG_FILE" ]; then
    LINE_COUNT=$(wc -l < "$LOG_FILE")
    if [ "$LINE_COUNT" -gt "$MAX_LINES" ]; then
        echo "日志文件有 $LINE_COUNT 行，清理中..."
        tail -n "$MAX_LINES" "$LOG_FILE" > "$LOG_FILE.tmp"
        cat "$LOG_FILE.tmp" > "$LOG_FILE"
        rm -f "$LOG_FILE.tmp"
        echo "日志已清理，保留最近 $MAX_LINES 行"
    else
        echo "日志文件有 $LINE_COUNT 行，无需清理"
    fi
fi

# 检查是否已有进程在运行
if pgrep -f "python.*main.py" > /dev/null; then
    echo "警告: 机器人已在运行中"
    echo "现有进程:"
    ps aux | grep "python.*main.py" | grep -v grep
    read -p "是否停止现有进程并重新启动? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "停止现有进程..."
        pkill -f "python.*main.py"
        sleep 2
    else
        echo "取消启动"
        exit 0
    fi
fi

# 启动机器人（后台运行，使用虚拟环境的 Python）
"$VENV_DIR/bin/python" main.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!

echo "=================================="
echo "机器人已启动"
echo "机器人 PID: $BOT_PID"
echo "日志文件: $LOG_FILE"
echo "自动清理: 每 $CHECK_INTERVAL 秒检查，保留最近 $MAX_LINES 行"
echo "=================================="
echo ""
echo "按 Ctrl+C 停止机器人"
echo ""

# 主循环 - 定期清理日志并监控进程
LAST_CLEAN_TIME=$(date +%s)

while true; do
    # 检查机器人进程是否还在运行
    if ! kill -0 "$BOT_PID" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 机器人进程已退出"
        exit 1
    fi

    # 检查是否需要清理日志
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - LAST_CLEAN_TIME))

    if [ "$TIME_DIFF" -ge "$CHECK_INTERVAL" ]; then
        cleanup_log
        LAST_CLEAN_TIME=$CURRENT_TIME
    fi

    # 短暂休眠，避免占用太多 CPU
    sleep 10
done
