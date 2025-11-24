#!/bin/bash
# AWS Lightsail 一键部署脚本
# 用于简化机器人在AWS Lightsail上的部署流程

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ==================== 配置区域 ====================

# 项目目录
PROJECT_DIR=~/telegram_bots/bybot3.0
# Python版本
PYTHON_VERSION=3.11

# ==================== 函数定义 ====================

print_header() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_step() {
    echo ""
    echo -e "${PURPLE}>>> $1${NC}"
    echo ""
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 询问用户确认
confirm() {
    read -p "$(echo -e ${YELLOW}$1 [y/N]: ${NC})" -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# ==================== 欢迎信息 ====================

clear
print_header "AWS Lightsail 机器人一键部署脚本"

echo "此脚本将帮助您："
echo "  1. 安装系统依赖"
echo "  2. 配置Python环境"
echo "  3. 安装项目依赖"
echo "  4. 配置机器人环境变量"
echo "  5. 设置Supervisor自动重启"
echo "  6. 启动所有机器人"
echo ""

if ! confirm "是否继续？"; then
    echo "部署已取消"
    exit 0
fi

# ==================== 检查系统环境 ====================

print_step "步骤 1/8: 检查系统环境"

# 检查是否为root用户
if [ "$EUID" -eq 0 ]; then
    print_warning "不建议使用root用户运行此脚本"
    if ! confirm "是否继续？"; then
        exit 1
    fi
fi

# 检查系统类型
if ! command_exists apt; then
    print_error "此脚本仅支持Ubuntu/Debian系统"
    exit 1
fi

print_success "系统检查通过"

# ==================== 更新系统 ====================

print_step "步骤 2/8: 更新系统软件包"

print_info "更新软件包列表..."
sudo apt update

if confirm "是否升级系统软件包？（推荐）"; then
    print_info "升级系统软件包..."
    sudo apt upgrade -y
fi

print_success "系统更新完成"

# ==================== 安装依赖 ====================

print_step "步骤 3/8: 安装系统依赖"

print_info "安装Python ${PYTHON_VERSION}..."

# 检查Python是否已安装
if command_exists python${PYTHON_VERSION}; then
    print_success "Python ${PYTHON_VERSION} 已安装"
else
    print_info "正在安装Python ${PYTHON_VERSION}..."
    sudo apt install software-properties-common -y
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev -y
fi

# 安装其他工具
print_info "安装其他必要工具..."
sudo apt install -y \
    python3-pip \
    git \
    supervisor \
    zip \
    unzip \
    htop \
    curl \
    wget

print_success "依赖安装完成"

# ==================== 创建项目目录 ====================

print_step "步骤 4/8: 准备项目目录"

# 如果项目目录不存在，创建并询问如何获取代码
if [ ! -d "$PROJECT_DIR" ]; then
    print_info "项目目录不存在，创建: $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
    
    echo ""
    echo "请选择代码部署方式："
    echo "  1) 使用Git克隆（需要Git仓库地址）"
    echo "  2) 手动上传（稍后自行上传代码）"
    echo "  3) 跳过（代码已存在）"
    read -p "请选择 [1-3]: " deploy_method
    
    case $deploy_method in
        1)
            read -p "请输入Git仓库地址: " git_repo
            if [ -n "$git_repo" ]; then
                print_info "克隆代码..."
                git clone "$git_repo" "$PROJECT_DIR"
            fi
            ;;
        2)
            print_warning "请使用SCP或其他方式上传代码到: $PROJECT_DIR"
            print_info "上传完成后，重新运行此脚本"
            exit 0
            ;;
        3)
            print_info "跳过代码部署"
            ;;
    esac
else
    print_success "项目目录已存在: $PROJECT_DIR"
fi

# 进入项目目录
cd "$PROJECT_DIR" || {
    print_error "无法进入项目目录: $PROJECT_DIR"
    exit 1
}

print_success "项目目录准备完成"

# ==================== 配置Python环境 ====================

print_step "步骤 5/8: 配置Python虚拟环境"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    print_info "创建Python虚拟环境..."
    python${PYTHON_VERSION} -m venv venv
    print_success "虚拟环境创建完成"
else
    print_success "虚拟环境已存在"
fi

# 激活虚拟环境
print_info "激活虚拟环境..."
source venv/bin/activate

# 升级pip
print_info "升级pip..."
pip install --upgrade pip setuptools wheel

# 安装项目依赖
if [ -f "requirements.txt" ]; then
    print_info "安装项目依赖..."
    pip install -r requirements.txt
    print_success "依赖安装完成"
else
    print_warning "未找到requirements.txt文件"
fi

print_success "Python环境配置完成"

# ==================== 配置机器人 ====================

print_step "步骤 6/8: 配置机器人环境变量"

# 检查是否有环境变量模板
if [ ! -f "env.aws.template" ]; then
    print_warning "未找到环境变量模板文件: env.aws.template"
    print_info "请手动创建.env配置文件"
else
    echo ""
    echo "请输入您要部署的机器人数量:"
    read -p "搬运机器人数量 [5]: " transfer_count
    transfer_count=${transfer_count:-5}
    
    read -p "会员机器人数量 [3]: " member_count
    member_count=${member_count:-3}
    
    echo ""
    print_info "将创建 $transfer_count 个搬运机器人和 $member_count 个会员机器人的配置文件"
    
    if confirm "是否现在创建配置文件？"; then
        # 创建搬运机器人配置
        for i in $(seq 1 $transfer_count); do
            config_file=".env.transfer_bot${i}"
            if [ ! -f "$config_file" ]; then
                cp env.aws.template "$config_file"
                print_success "创建配置文件: $config_file"
            else
                print_info "配置文件已存在: $config_file"
            fi
        done
        
        # 创建会员机器人配置
        for i in $(seq 1 $member_count); do
            config_file=".env.member_bot${i}"
            if [ ! -f "$config_file" ]; then
                cp env.aws.template "$config_file"
                print_success "创建配置文件: $config_file"
            else
                print_info "配置文件已存在: $config_file"
            fi
        done
        
        echo ""
        print_warning "请编辑各个.env文件，填入正确的配置信息："
        print_info "  nano .env.transfer_bot1"
        print_info "  nano .env.member_bot1"
        print_info "  ..."
        echo ""
        
        if ! confirm "配置文件是否已填写完成？"; then
            print_warning "请完成配置后重新运行脚本"
            exit 0
        fi
    fi
fi

# 设置配置文件权限
print_info "设置配置文件权限..."
chmod 600 .env.* 2>/dev/null || true
print_success "配置文件权限设置完成"

# ==================== 配置Supervisor ====================

print_step "步骤 7/8: 配置Supervisor自动重启"

if [ -d "supervisor_templates" ]; then
    if [ -f "supervisor_templates/create_all_configs.sh" ]; then
        print_info "使用自动配置脚本..."
        bash supervisor_templates/create_all_configs.sh
    else
        print_info "手动复制Supervisor配置..."
        for conf_file in supervisor_templates/*.conf; do
            if [ -f "$conf_file" ] && [[ "$conf_file" != *"template"* ]]; then
                sudo cp "$conf_file" /etc/supervisor/conf.d/
                print_success "复制配置: $(basename $conf_file)"
            fi
        done
    fi
    
    # 重新加载Supervisor配置
    print_info "重新加载Supervisor配置..."
    sudo supervisorctl reread
    sudo supervisorctl update
    
    print_success "Supervisor配置完成"
else
    print_warning "未找到supervisor_templates目录"
    print_info "请手动配置Supervisor"
fi

# ==================== 启动机器人 ====================

print_step "步骤 8/8: 启动机器人"

if confirm "是否现在启动所有机器人？"; then
    print_info "启动所有机器人..."
    sudo supervisorctl start all
    
    echo ""
    sleep 2
    
    print_info "检查机器人状态..."
    sudo supervisorctl status
    
    echo ""
    print_success "机器人已启动"
else
    print_info "跳过启动，稍后可手动执行："
    print_info "  sudo supervisorctl start all"
fi

# ==================== 部署完成 ====================

print_header "部署完成！"

echo -e "${GREEN}🎉 恭喜！机器人部署成功！${NC}"
echo ""
echo "接下来的步骤："
echo ""
echo "1. 验证机器人运行状态："
echo "   ${CYAN}sudo supervisorctl status${NC}"
echo ""
echo "2. 查看机器人日志："
echo "   ${CYAN}sudo tail -f /var/log/transfer_bot1.out.log${NC}"
echo ""
echo "3. 测试机器人："
echo "   在Telegram中向机器人发送 /start"
echo ""
echo "4. 监控系统："
echo "   ${CYAN}bash monitor_bots.sh${NC}"
echo ""
echo "5. 设置自动备份："
echo "   ${CYAN}crontab -e${NC}"
echo "   添加：${CYAN}0 2 * * * ~/telegram_bots/bybot3.0/backup_bots.sh >> ~/backup.log 2>&1${NC}"
echo ""
echo "常用命令："
echo "  ${CYAN}sudo supervisorctl restart all${NC}     # 重启所有机器人"
echo "  ${CYAN}sudo supervisorctl stop all${NC}        # 停止所有机器人"
echo "  ${CYAN}free -h${NC}                            # 查看内存"
echo "  ${CYAN}df -h${NC}                              # 查看磁盘"
echo "  ${CYAN}htop${NC}                               # 查看进程"
echo ""
echo "文档："
echo "  完整部署指南: ${CYAN}AWS_DEPLOYMENT_GUIDE.md${NC}"
echo "  故障排查:     ${CYAN}AWS_TROUBLESHOOTING.md${NC}"
echo ""
echo -e "${YELLOW}⚠️  重要提醒：${NC}"
echo "  1. 定期备份配置和数据"
echo "  2. 监控服务器资源使用"
echo "  3. 设置AWS账单告警"
echo "  4. 妥善保管SSH密钥和配置文件"
echo ""

print_success "感谢使用AWS Lightsail部署脚本！"
echo ""








