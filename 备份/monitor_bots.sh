#!/bin/bash
# 机器人监控脚本
# 用于检查所有机器人的运行状态和系统资源

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印标题
print_header() {
    echo ""
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

# 打印分隔线
print_separator() {
    echo ""
    echo "--------------------------------"
    echo ""
}

# 清屏（可选）
# clear

# 显示当前时间
print_header "Telegram机器人监控面板"
echo -e "${GREEN}当前时间：${NC}$(date '+%Y-%m-%d %H:%M:%S')"
echo -e "${GREEN}服务器：${NC}$(hostname)"
echo -e "${GREEN}运行时间：${NC}$(uptime -p)"

# ==================== 机器人状态 ====================
print_separator
print_header "机器人运行状态"

# 检查Supervisor是否运行
if ! systemctl is-active --quiet supervisor; then
    echo -e "${RED}❌ Supervisor服务未运行！${NC}"
    echo "请执行：sudo systemctl start supervisor"
    exit 1
fi

# 获取所有机器人状态
BOT_STATUS=$(sudo supervisorctl status 2>&1)

if [ $? -eq 0 ]; then
    # 统计运行中的机器人
    RUNNING_COUNT=$(echo "$BOT_STATUS" | grep -c "RUNNING")
    TOTAL_COUNT=$(echo "$BOT_STATUS" | wc -l)
    
    echo -e "${GREEN}运行中：${NC}$RUNNING_COUNT / $TOTAL_COUNT"
    echo ""
    
    # 显示详细状态，根据状态着色
    while IFS= read -r line; do
        if echo "$line" | grep -q "RUNNING"; then
            echo -e "${GREEN}✓${NC} $line"
        elif echo "$line" | grep -q "STOPPED"; then
            echo -e "${RED}✗${NC} $line"
        elif echo "$line" | grep -q "FATAL"; then
            echo -e "${RED}⚠${NC} $line"
        elif echo "$line" | grep -q "STARTING"; then
            echo -e "${YELLOW}⟳${NC} $line"
        else
            echo -e "  $line"
        fi
    done <<< "$BOT_STATUS"
    
    # 检查是否有非RUNNING状态的机器人
    PROBLEM_BOTS=$(echo "$BOT_STATUS" | grep -v "RUNNING")
    if [ -n "$PROBLEM_BOTS" ] && [ "$RUNNING_COUNT" -lt "$TOTAL_COUNT" ]; then
        echo ""
        echo -e "${RED}⚠️  警告：有机器人未正常运行！${NC}"
        echo ""
        echo "查看日志命令："
        echo "$PROBLEM_BOTS" | awk '{print "  sudo tail -50 /var/log/" $1 ".err.log"}'
    fi
else
    echo -e "${RED}❌ 无法获取机器人状态${NC}"
    echo "$BOT_STATUS"
fi

# ==================== 系统资源 ====================
print_separator
print_header "系统资源使用情况"

# 内存使用
echo -e "${YELLOW}📊 内存使用：${NC}"
free -h | awk '
NR==1 {print "  " $0}
NR==2 {
    total=$2; used=$3; free=$4; available=$7
    printf "  %-10s %-10s %-10s %-10s\n", total, used, free, available
    
    # 计算使用百分比
    gsub(/[^0-9.]/, "", used)
    gsub(/[^0-9.]/, "", total)
    if (total > 0) {
        percent = (used / total) * 100
        if (percent > 80) color = "\033[0;31m"  # 红色
        else if (percent > 60) color = "\033[1;33m"  # 黄色
        else color = "\033[0;32m"  # 绿色
        printf "  " color "使用率: %.1f%%\033[0m\n", percent
    }
}'

echo ""

# 磁盘使用
echo -e "${YELLOW}💾 磁盘使用：${NC}"
df -h / | awk '
NR==1 {print "  " $0}
NR==2 {
    print "  " $0
    gsub(/%/, "", $5)
    percent = $5
    if (percent > 80) color = "\033[0;31m"
    else if (percent > 60) color = "\033[1;33m"
    else color = "\033[0;32m"
    printf "  " color "使用率: %s%%\033[0m\n", percent
}'

echo ""

# CPU负载
echo -e "${YELLOW}💻 CPU负载：${NC}"
LOAD=$(uptime | awk -F'load average:' '{print $2}')
echo "  1分钟, 5分钟, 15分钟:$LOAD"

# CPU核心数
CPU_CORES=$(nproc)
echo "  CPU核心数: $CPU_CORES"

# 计算CPU使用率
LOAD_1MIN=$(uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | xargs)
LOAD_PERCENT=$(echo "scale=1; ($LOAD_1MIN / $CPU_CORES) * 100" | bc 2>/dev/null || echo "N/A")
if [ "$LOAD_PERCENT" != "N/A" ]; then
    echo "  负载率: ${LOAD_PERCENT}%"
fi

# ==================== 网络状态 ====================
print_separator
print_header "网络连接状态"

# 测试Telegram API连接
echo -e "${YELLOW}🌐 Telegram API连接测试：${NC}"
if timeout 5 curl -s -I https://api.telegram.org >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓ api.telegram.org 连接正常${NC}"
    
    # 测试延迟
    PING_RESULT=$(ping -c 3 api.telegram.org 2>&1 | tail -1)
    if echo "$PING_RESULT" | grep -q "avg"; then
        AVG_PING=$(echo "$PING_RESULT" | awk -F'/' '{print $5}')
        echo "  平均延迟: ${AVG_PING}ms"
    fi
else
    echo -e "  ${RED}✗ api.telegram.org 连接失败${NC}"
    echo "  请检查网络设置和防火墙"
fi

# ==================== 机器人进程信息 ====================
print_separator
print_header "机器人进程资源占用"

# 查找Python进程
PYTHON_PROCS=$(ps aux | grep "[p]ython.*lsjmain.py" | wc -l)

if [ $PYTHON_PROCS -gt 0 ]; then
    echo -e "${GREEN}发现 $PYTHON_PROCS 个机器人进程${NC}"
    echo ""
    echo "进程详情："
    ps aux | grep "[p]ython.*lsjmain.py" | awk '
    BEGIN {
        printf "  %-8s %-6s %-6s %-10s %s\n", "USER", "PID", "CPU%", "MEM%", "TIME"
        printf "  %-8s %-6s %-6s %-10s %s\n", "--------", "------", "------", "----------", "--------"
    }
    {
        printf "  %-8s %-6s %-6s %-10s %s\n", $1, $2, $3, $4, $10
    }'
    
    # 计算总内存使用
    TOTAL_MEM=$(ps aux | grep "[p]ython.*lsjmain.py" | awk '{sum+=$4} END {print sum}')
    echo ""
    echo -e "  总内存占用: ${YELLOW}${TOTAL_MEM}%${NC}"
else
    echo -e "${RED}⚠️  未发现运行中的机器人进程${NC}"
fi

# ==================== 最近日志错误 ====================
print_separator
print_header "最近日志错误（最近10条）"

# 检查所有错误日志
ERROR_FOUND=false
for log_file in /var/log/*bot*.err.log; do
    if [ -f "$log_file" ]; then
        # 获取最近的错误（排除空行）
        RECENT_ERRORS=$(sudo tail -10 "$log_file" 2>/dev/null | grep -v "^$" | tail -5)
        
        if [ -n "$RECENT_ERRORS" ]; then
            ERROR_FOUND=true
            echo ""
            echo -e "${YELLOW}📄 $(basename $log_file)${NC}"
            echo "$RECENT_ERRORS" | while IFS= read -r line; do
                if echo "$line" | grep -qi "error\|exception\|failed\|fatal"; then
                    echo -e "  ${RED}$line${NC}"
                else
                    echo "  $line"
                fi
            done
        fi
    fi
done

if [ "$ERROR_FOUND" = false ]; then
    echo -e "${GREEN}✓ 没有发现最近的错误日志${NC}"
fi

# ==================== 磁盘空间警告 ====================
print_separator

# 检查磁盘使用是否超过80%
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "${RED}⚠️  警告：磁盘使用率超过80%！${NC}"
    echo "请清理不需要的文件或日志"
    echo ""
    echo "建议清理命令："
    echo "  # 清理旧日志（7天前）"
    echo "  sudo find /var/log -name '*.log' -mtime +7 -delete"
    echo "  # 清理旧备份"
    echo "  find ~/backups -name '*.tar.gz' -mtime +7 -delete"
fi

# 检查内存使用是否超过80%
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", ($3/$2) * 100}')
if [ "$MEM_USAGE" -gt 80 ]; then
    echo -e "${RED}⚠️  警告：内存使用率超过80%！${NC}"
    echo "可能需要优化机器人配置或升级服务器"
    echo ""
fi

# ==================== 快速操作提示 ====================
print_separator
print_header "常用操作命令"

echo "机器人管理："
echo "  sudo supervisorctl status              # 查看状态"
echo "  sudo supervisorctl restart all         # 重启所有机器人"
echo "  sudo supervisorctl restart bot名称     # 重启特定机器人"
echo ""
echo "日志查看："
echo "  sudo tail -f /var/log/bot名称.out.log  # 实时查看输出日志"
echo "  sudo tail -f /var/log/bot名称.err.log  # 实时查看错误日志"
echo ""
echo "系统监控："
echo "  htop                                   # 进程监控"
echo "  df -h                                  # 磁盘使用"
echo "  free -h                                # 内存使用"

print_separator

echo -e "${GREEN}✅ 监控检查完成${NC}"
echo ""








