# ==================== 干净版本更新脚本 ====================
"""
自动备份干净版本到clan_bot文件夹并上传到GitHub
使用方法: python update_clean_version.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def get_script_dir():
    """获取脚本所在目录"""
    return Path(__file__).parent.absolute()

def clean_clan_bot_folder():
    """清理clan_bot文件夹"""
    clan_bot_dir = get_script_dir() / "clan_bot"
    
    if clan_bot_dir.exists():
        print("🧹 清理旧的clan_bot文件夹...")
        shutil.rmtree(clan_bot_dir)
    
    clan_bot_dir.mkdir(exist_ok=True)
    print(f"✅ 创建新的clan_bot文件夹: {clan_bot_dir}")
    return clan_bot_dir

def copy_core_files(clan_bot_dir):
    """复制核心文件到clan_bot"""
    script_dir = get_script_dir()
    
    # 需要复制的核心文件
    core_files = [
        "lsjmain.py",
        "monitoring_engine.py", 
        "cloning_engine.py",
        "message_engine.py",
        "config.py",
        "log_config.py",
        "ui_layouts.py",
        "data_manager.py",
        "local_data_manager.py",
        "channel_data_manager.py",
        "user_api_manager.py",
        "user_session_manager.py",
        "multi_bot_config_manager.py",
        "multi_bot_data_manager.py",
        "task_state_manager.py",
        "concurrent_task_manager.py",
        "memory_optimizer.py",
        "enhanced_link_filter.py",
        "firebase_batch_storage.py",
        "firebase_cache_manager.py",
        "firebase_quota_manager.py",
        "firebase_quota_monitor.py",
        "intelligent_like_system.py",
        "like_speed_optimizer.py",
        "optimize_concurrent_monitoring.py",
        "session_converter.py",
        "web_server.py",
        "quick_deploy.py",
        "setup_render_user_api.py",
        "requirements.txt",
        ".env",
        ".gitignore",
        "Procfile",
        "render.yaml",
        "render_env_template.env"
    ]
    
    # 需要复制的部署相关文件
    deployment_files = [
        "multi_bot_deployment.py",
        "optimized_firebase_manager.py", 
        "firebase_performance_analysis.py",
        "firebase_performance_test.py",
        "render_multi_bot.yaml",
        "RENDER_DEPLOYMENT_GUIDE.md",
        "FIREBASE_PERFORMANCE_ANALYSIS.md"
    ]
    
    all_files = core_files + deployment_files
    
    copied_count = 0
    for file_name in all_files:
        src_file = script_dir / file_name
        if src_file.exists():
            dst_file = clan_bot_dir / file_name
            shutil.copy2(src_file, dst_file)
            copied_count += 1
            print(f"📋 复制: {file_name}")
        else:
            print(f"⚠️  文件不存在: {file_name}")
    
    print(f"✅ 成功复制 {copied_count} 个文件")
    return copied_count

def exclude_user_data():
    """排除用户数据文件"""
    script_dir = get_script_dir()
    
    # 需要排除的用户数据目录和文件
    exclude_patterns = [
        "data/",
        "sessions/", 
        "__pycache__/",
        "*.log",
        "*.session",
        "*.session-journal",
        "test_*.py",
        "*_test.py",
        "*_analysis.md",
        "*_report.md",
        "*_fix_report.md",
        "*_guide.md",
        "check_*.py",
        "diagnose_*.py",
        "simple_*.py",
        "bulk_*.md",
        "concurrent_*.md",
        "deployment_*.md",
        "firebase_*.md",
        "intelligent_*.md",
        "media_group_*.md",
        "monitoring_*.md",
        "optimization_*.md",
        "render_*.md",
        "简化版监听系统启动指南.md"
    ]
    
    print("🚫 排除用户数据文件:")
    for pattern in exclude_patterns:
        print(f"   - {pattern}")

def update_gitignore():
    """更新.gitignore文件"""
    clan_bot_dir = get_script_dir() / "clan_bot"
    gitignore_content = """# ==================== .gitignore ====================
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# 用户数据
data/
sessions/
*.session
*.session-journal
*.log

# 环境配置
.env
.env.local
.env.production

# IDE
.vscode/
.idea/
*.swp
*.swo

# 测试文件
test_*.py
*_test.py

# 临时文件
*.tmp
*.temp
.DS_Store
Thumbs.db

# Firebase
firebase-adminsdk-*.json
service-account-key.json
"""
    
    gitignore_file = clan_bot_dir / ".gitignore"
    with open(gitignore_file, 'w', encoding='utf-8') as f:
        f.write(gitignore_content)
    
    print("✅ 更新.gitignore文件")

def commit_and_push():
    """提交并推送到GitHub"""
    try:
        # 添加文件到Git
        print("📝 添加文件到Git...")
        subprocess.run(["git", "add", "clan_bot/"], check=True)
        subprocess.run(["git", "add", "lsjmain.py"], check=True)
        subprocess.run(["git", "add", "requirements.txt"], check=True)
        
        # 提交更改
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"🔄 更新干净版本 - {timestamp}\n\n- 同步最新代码到clan_bot/\n- 排除用户数据文件\n- 保持部署就绪状态"
        
        print("💾 提交更改...")
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        
        # 推送到GitHub
        print("🚀 推送到GitHub...")
        subprocess.run(["git", "push", "origin", "main"], check=True)
        
        print("✅ 成功推送到GitHub!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git操作失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始更新干净版本...")
    print("=" * 50)
    
    # 1. 清理并创建clan_bot文件夹
    clan_bot_dir = clean_clan_bot_folder()
    
    # 2. 复制核心文件
    copied_count = copy_core_files(clan_bot_dir)
    
    # 3. 排除用户数据
    exclude_user_data()
    
    # 4. 更新.gitignore
    update_gitignore()
    
    # 5. 提交并推送
    print("\n" + "=" * 50)
    print("📤 准备上传到GitHub...")
    
    if commit_and_push():
        print("\n🎉 干净版本更新完成!")
        print(f"📊 统计: 复制了 {copied_count} 个文件")
        print("🌐 GitHub仓库已更新: https://github.com/laowangbot/-3.0-.git")
    else:
        print("\n❌ 更新失败，请检查Git配置")
        sys.exit(1)

if __name__ == "__main__":
    main()
