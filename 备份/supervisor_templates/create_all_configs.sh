#!/bin/bash
# 一键创建所有Supervisor配置文件脚本

echo "🚀 创建Supervisor配置文件..."

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 配置文件列表
BOT_NAMES=(
    "transfer_bot1"
    "transfer_bot2"
    "transfer_bot3"
    "transfer_bot4"
    "transfer_bot5"
    "member_bot1"
    "member_bot2"
    "member_bot3"
)

# 复制配置文件到supervisor目录
for bot_name in "${BOT_NAMES[@]}"; do
    if [ -f "$SCRIPT_DIR/${bot_name}.conf" ]; then
        echo "📝 创建配置: ${bot_name}.conf"
        sudo cp "$SCRIPT_DIR/${bot_name}.conf" "/etc/supervisor/conf.d/${bot_name}.conf"
    else
        echo "⚠️  警告: 找不到 ${bot_name}.conf"
    fi
done

echo ""
echo "✅ 配置文件创建完成！"
echo ""
echo "接下来执行以下命令："
echo "  sudo supervisorctl reread"
echo "  sudo supervisorctl update"
echo "  sudo supervisorctl start all"
echo ""








