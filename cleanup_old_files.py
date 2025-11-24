# ==================== GitHub仓库清理脚本 ====================
"""
清理旧文件脚本
用于删除模块化重构后不再需要的旧文件
"""

import os
import shutil

# 需要删除的旧文件列表
OLD_FILES = [
    "ai_rewrite_commands.py",
    "ai_text_rewriter.py",
    "cloning_engine.py",
    "comment_cloning_integration.py",
    "monitoring_engine.py",
    "user_api_manager.py",
    "user_session_manager.py",
    "channel_data_manager.py",
    "message_engine.py",
    "ui_layouts.py",
    "web_server.py"
]

# 需要删除的旧目录列表
OLD_DIRS = [
    "backups_sessions",
    "bot_configs",
    "data",
    "downloads",
    "logs",
    "sessions",
    "supervisor_templates",
    "web",
    "服务器秘钥"
]

def cleanup_old_files():
    """清理旧文件"""
    print("开始清理旧文件...")
    
    # 删除旧文件
    for file_name in OLD_FILES:
        file_path = os.path.join(os.getcwd(), file_name)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"✅ 已删除文件: {file_name}")
            except Exception as e:
                print(f"❌ 删除文件失败 {file_name}: {e}")
        else:
            print(f"ℹ️  文件不存在: {file_name}")
    
    # 删除旧目录
    for dir_name in OLD_DIRS:
        dir_path = os.path.join(os.getcwd(), dir_name)
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"✅ 已删除目录: {dir_name}")
            except Exception as e:
                print(f"❌ 删除目录失败 {dir_name}: {e}")
        else:
            print(f"ℹ️  目录不存在: {dir_name}")
    
    print("旧文件清理完成!")

if __name__ == "__main__":
    cleanup_old_files()
