#!/bin/bash
# 机器人自动备份脚本
# 用于备份配置文件、Session文件和数据库

# ==================== 配置区域 ====================

# 备份目录
BACKUP_DIR=~/backups
# 项目目录
PROJECT_DIR=~/telegram_bots/bybot3.0
# 保留备份天数（超过此天数的备份将被自动删除）
RETENTION_DAYS=7

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==================== 函数定义 ====================

# 打印信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# 打印成功
print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 打印警告
print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 打印错误
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ==================== 备份流程 ====================

print_info "开始备份 Telegram 机器人..."
echo ""

# 创建备份目录
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    print_info "创建备份目录: $BACKUP_DIR"
fi

# 生成时间戳
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="bybot3.0_backup_${DATE}"
TEMP_BACKUP_DIR="${BACKUP_DIR}/${BACKUP_NAME}"

print_info "备份时间: $(date '+%Y-%m-%d %H:%M:%S')"
print_info "备份名称: ${BACKUP_NAME}"
echo ""

# 创建临时备份目录
mkdir -p "$TEMP_BACKUP_DIR"

# ==================== 备份项目文件 ====================

print_info "正在备份项目文件..."

# 检查项目目录是否存在
if [ ! -d "$PROJECT_DIR" ]; then
    print_error "项目目录不存在: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR" || exit 1

# 备份配置文件
print_info "  备份环境配置文件..."
mkdir -p "$TEMP_BACKUP_DIR/configs"
cp .env.* "$TEMP_BACKUP_DIR/configs/" 2>/dev/null || print_warning "  没有找到环境配置文件"

# 备份Session文件
print_info "  备份Session文件..."
if [ -d "sessions" ]; then
    mkdir -p "$TEMP_BACKUP_DIR/sessions"
    cp sessions/*.session "$TEMP_BACKUP_DIR/sessions/" 2>/dev/null || print_warning "  没有找到Session文件"
    cp sessions/*.session-journal "$TEMP_BACKUP_DIR/sessions/" 2>/dev/null || true
else
    print_warning "  Sessions目录不存在"
fi

# 备份本地数据库
print_info "  备份本地数据库..."
if [ -d "data" ]; then
    mkdir -p "$TEMP_BACKUP_DIR/data"
    cp -r data/* "$TEMP_BACKUP_DIR/data/" 2>/dev/null || print_warning "  没有找到数据文件"
else
    print_warning "  Data目录不存在"
fi

# 备份机器人配置
print_info "  备份机器人配置文件..."
if [ -d "bot_configs" ]; then
    mkdir -p "$TEMP_BACKUP_DIR/bot_configs"
    cp bot_configs/*.json "$TEMP_BACKUP_DIR/bot_configs/" 2>/dev/null || true
fi

# 备份频道数据
print_info "  备份频道数据..."
cp channel_data.json "$TEMP_BACKUP_DIR/" 2>/dev/null || true

# 备份Supervisor配置
print_info "  备份Supervisor配置..."
mkdir -p "$TEMP_BACKUP_DIR/supervisor"
sudo cp /etc/supervisor/conf.d/*bot*.conf "$TEMP_BACKUP_DIR/supervisor/" 2>/dev/null || print_warning "  没有找到Supervisor配置"

# 创建备份信息文件
print_info "  创建备份信息文件..."
cat > "$TEMP_BACKUP_DIR/backup_info.txt" << EOF
备份信息
========================================
备份时间: $(date '+%Y-%m-%d %H:%M:%S')
服务器: $(hostname)
系统: $(uname -a)
项目目录: $PROJECT_DIR
备份目录: $BACKUP_DIR

备份内容:
- 环境配置文件 (.env.*)
- Session文件 (sessions/*.session)
- 本地数据库 (data/*)
- 机器人配置 (bot_configs/*.json)
- 频道数据 (channel_data.json)
- Supervisor配置 (/etc/supervisor/conf.d/*bot*.conf)

机器人状态:
$(sudo supervisorctl status 2>&1)

系统资源:
内存: $(free -h | grep Mem | awk '{print $3 "/" $2}')
磁盘: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 " used)"}')

备份文件: ${BACKUP_NAME}.tar.gz
========================================
EOF

# ==================== 压缩备份 ====================

print_info "正在压缩备份..."
cd "$BACKUP_DIR" || exit 1

# 压缩备份目录
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME" 2>&1 | grep -v "Removing leading"

if [ $? -eq 0 ]; then
    # 删除临时目录
    rm -rf "$TEMP_BACKUP_DIR"
    
    # 获取备份文件大小
    BACKUP_SIZE=$(du -h "${BACKUP_NAME}.tar.gz" | cut -f1)
    
    print_success "备份完成！"
    echo ""
    print_info "备份文件: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    print_info "文件大小: ${BACKUP_SIZE}"
else
    print_error "备份压缩失败！"
    rm -rf "$TEMP_BACKUP_DIR"
    exit 1
fi

# ==================== 清理旧备份 ====================

print_info "正在清理旧备份（保留 ${RETENTION_DAYS} 天）..."

# 删除超过保留天数的备份
OLD_BACKUPS=$(find "$BACKUP_DIR" -name "bybot3.0_backup_*.tar.gz" -mtime +${RETENTION_DAYS})

if [ -n "$OLD_BACKUPS" ]; then
    echo "$OLD_BACKUPS" | while read -r old_backup; do
        rm -f "$old_backup"
        print_info "  删除旧备份: $(basename "$old_backup")"
    done
else
    print_info "  没有需要清理的旧备份"
fi

# ==================== 备份统计 ====================

echo ""
print_info "当前备份列表:"
ls -lh "$BACKUP_DIR"/bybot3.0_backup_*.tar.gz 2>/dev/null | tail -5 | awk '{print "  " $9 " (" $5 ", " $6 " " $7 ")"}'

TOTAL_BACKUPS=$(ls "$BACKUP_DIR"/bybot3.0_backup_*.tar.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

echo ""
print_info "备份统计:"
print_info "  总备份数: $TOTAL_BACKUPS"
print_info "  总大小: $TOTAL_SIZE"

# ==================== 备份建议 ====================

echo ""
print_info "备份建议:"
echo "  1. 定期下载备份到本地电脑"
echo "  2. 重要备份可上传到云存储（如AWS S3）"
echo "  3. 建议至少保留最近3次备份"
echo ""

# 提示下载命令
print_info "下载备份到本地（在本地电脑执行）:"
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "  scp -i ~/.ssh/your_key.pem ubuntu@${SERVER_IP}:${BACKUP_DIR}/${BACKUP_NAME}.tar.gz ~/Downloads/"

echo ""
print_success "✅ 备份脚本执行完成！"

# ==================== 恢复说明 ====================

# 创建恢复说明文件
cat > "$BACKUP_DIR/RESTORE_GUIDE.txt" << 'EOF'
备份恢复指南
========================================

如何恢复备份：

1. 解压备份文件
   tar -xzf bybot3.0_backup_YYYYMMDD_HHMMSS.tar.gz

2. 恢复环境配置
   cp bybot3.0_backup_*/configs/.env.* ~/telegram_bots/bybot3.0/

3. 恢复Session文件
   cp bybot3.0_backup_*/sessions/*.session ~/telegram_bots/bybot3.0/sessions/

4. 恢复数据库
   cp -r bybot3.0_backup_*/data/* ~/telegram_bots/bybot3.0/data/

5. 恢复Supervisor配置
   sudo cp bybot3.0_backup_*/supervisor/*.conf /etc/supervisor/conf.d/
   sudo supervisorctl reread
   sudo supervisorctl update

6. 重启所有机器人
   sudo supervisorctl restart all

7. 验证恢复
   sudo supervisorctl status

注意事项：
- 恢复前请先停止所有机器人
- 确保备份文件完整无损
- 恢复后检查配置文件权限（chmod 600）
- 重要操作前请先备份当前状态

========================================
EOF

exit 0








