# ==================== 直接部署脚本 ====================
"""
直接部署脚本 - 使用主文件夹，排除用户数据文件
适用于Render部署，因为Render版本使用Firebase存储
"""

import os
import subprocess
import datetime
from pathlib import Path

# GitHub仓库信息
GITHUB_REPO_URL = "https://github.com/laowangbot/-3.0-.git"

def get_script_dir():
    """获取脚本所在目录"""
    return Path(__file__).parent

def update_gitignore():
    """更新.gitignore文件，确保用户数据不被上传"""
    gitignore_path = get_script_dir() / ".gitignore"
    
    # 需要排除的用户数据文件模式
    exclude_patterns = [
        "# 用户数据文件 - 不上传到GitHub",
        "data/",
        "sessions/",
        "*.session",
        "*.session-journal",
        "*.log",
        "bot.log",
        "channel_data.json",
        "user_data.json",
        "user_config.json",
        "cache/",
        "temp/",
        "logs/",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".Python",
        "env/",
        "venv/",
        ".env.local",
        ".env.production",
        "test_*.py",
        "debug_*.py",
        "*_test.py",
        "*_debug.py",
        "backup_*.py",
        "*.backup",
        "*.bak",
        "*.tmp",
        "*.temp",
        "firebase_credentials.json",
        "firebase_config.json",
        "firebase_credentials_template.txt",
        "local_config.json",
        "user_sessions/",
        "user_data/",
        "local_data/",
        "temp_data/",
        "debug_data/",
        "test_data/",
        "backup_data/",
        "*.analysis",
        "*.report",
        "*.summary",
        "*.log.*",
        "monitoring_*.log",
        "cloning_*.log",
        "user_*.log",
        "debug_*.log",
        "test_*.log",
        "error_*.log",
        "performance_*.log",
        "firebase_*.log",
        "render_*.log",
        "deployment_*.log",
        "*.session.backup",
        "*.session.old",
        "*.session.temp",
        "*.session.test",
        "*.session.debug",
        "user_*.session",
        "test_*.session",
        "debug_*.session",
        "temp_*.session",
        "backup_*.session",
        "firebase_*.session",
        "render_*.session",
        "deployment_*.session",
        "local_*.session",
        "production_*.session",
        "development_*.session",
        "staging_*.session",
        "*.session.*",
        "*.log.*",
        "*.json.backup",
        "*.json.old",
        "*.json.temp",
        "*.json.test",
        "*.json.debug",
        "user_*.json",
        "test_*.json",
        "debug_*.json",
        "temp_*.json",
        "backup_*.json",
        "firebase_*.json",
        "render_*.json",
        "deployment_*.json",
        "local_*.json",
        "production_*.json",
        "development_*.json",
        "staging_*.json",
        "*.json.*",
        "*.analysis.*",
        "*.report.*",
        "*.summary.*",
        "*.log.*",
        "*.session.*",
        "*.json.*",
        "*.backup.*",
        "*.old.*",
        "*.temp.*",
        "*.test.*",
        "*.debug.*",
        "*.production.*",
        "*.development.*",
        "*.staging.*",
        "*.local.*",
        "*.render.*",
        "*.firebase.*",
        "*.deployment.*",
        "*.monitoring.*",
        "*.cloning.*",
        "*.user.*",
        "*.bot.*",
        "*.api.*"
    ]
    
    # 读取现有的.gitignore内容
    existing_content = ""
    if gitignore_path.exists():
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        except UnicodeDecodeError:
            # 如果编码有问题，重新创建文件
            gitignore_path.unlink()
            existing_content = ""
    
    # 检查是否需要添加新的排除模式
    new_patterns = []
    for pattern in exclude_patterns:
        if pattern not in existing_content:
            new_patterns.append(pattern)
    
    # 如果有新模式，添加到.gitignore
    if new_patterns:
        with open(gitignore_path, 'a', encoding='utf-8') as f:
            f.write('\n' + '\n'.join(new_patterns))
        print(f"✅ 更新.gitignore文件，添加了 {len(new_patterns)} 个排除模式")
    else:
        print("✅ .gitignore文件已是最新")

def run_git_command(command, check=True):
    """运行Git命令"""
    try:
        result = subprocess.run(command, shell=True, check=check, 
                              capture_output=True, text=True, encoding='utf-8')
        if result.stdout:
            print(f"📤 {command}: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Git命令失败: {command}")
        print(f"错误: {e.stderr}")
        if check:
            raise
        return None

def main():
    print("🚀 开始直接部署到GitHub...")
    print("==================================================")
    print("📋 部署策略:")
    print("   - 使用主文件夹直接部署")
    print("   - 排除所有用户数据文件")
    print("   - Render版本使用Firebase存储")
    print("   - 不创建clan_bot子文件夹")
    
    # 1. 更新.gitignore文件
    print("\n🔧 更新.gitignore文件...")
    update_gitignore()
    
    # 2. 检查Git状态
    print("\n📊 检查Git状态...")
    run_git_command("git status --porcelain")
    
    # 3. 添加所有文件（.gitignore会排除用户数据）
    print("\n📤 添加文件到Git...")
    run_git_command("git add .")
    
    # 4. 检查将要提交的文件
    print("\n📋 检查将要提交的文件...")
    result = run_git_command("git status --porcelain")
    if result and result.stdout:
        print("将要提交的文件:")
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                print(f"   {line}")
    
    # 5. 提交更改
    print("\n💾 提交更改...")
    commit_message = f"🚀 直接部署更新 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run_git_command(f'git commit -m "{commit_message}"')
    
    # 6. 推送到GitHub
    print("\n🌐 推送到GitHub...")
    run_git_command("git push origin main")
    
    print("\n🎉 直接部署完成!")
    print("==================================================")
    print("📊 部署信息:")
    print(f"   - 仓库: {GITHUB_REPO_URL}")
    print(f"   - 策略: 直接部署主文件夹")
    print(f"   - 排除: 用户数据文件")
    print(f"   - 存储: Render使用Firebase")
    print("==================================================")
    print("🔧 Render部署配置:")
    print("   - Root Directory: 留空（使用根目录）")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Start Command: python lsjmain.py")
    print("   - 环境变量: 使用firebase_credentials_template.txt中的配置")

if __name__ == "__main__":
    main()
