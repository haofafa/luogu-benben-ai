#!/bin/bash
# stop.sh - 停止洛谷犇犇AI服务

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 方法2：通过进程名停止
PROCESS_COUNT=$(ps aux | grep -v grep | grep -c "python.*luogu_ai")
if [ $PROCESS_COUNT -gt 0 ]; then
    echo "📌 找到 $PROCESS_COUNT 个相关进程，正在停止..."
    
    # 停止所有相关进程
    pids=$(ps aux | grep -v grep | grep "python.*luogu_ai" | awk '{print $2}')
    for pid in $pids; do
        echo "  停止进程 $pid..."
        kill $pid 2>/dev/null
        sleep 1
        if ps -p $pid > /dev/null 2>&1; then
            kill -9 $pid 2>/dev/null
            echo "  ✅ 强制停止进程 $pid"
        fi
    done
    
    echo "✅ 所有相关进程已停止"
else
    echo "✅ 未找到运行中的服务进程"
fi

# 清理临时文件
rm -f server.pid stop.pid 2>/dev/null

echo "🎉 服务停止完成！"