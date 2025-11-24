#!/usr/bin/env python3
"""
Render环境User API快速设置脚本
"""

import os
import sys
import base64
import subprocess
from pathlib import Path

def check_local_session():
    """检查本地是否有session文件"""
    session_files = [
        'user_session.session',
        'sessions/user_session.session',
        'bot_session_default.session'
    ]
    
    for session_file in session_files:
        if os.path.exists(session_file):
            print(f"✅ 找到session文件: {session_file}")
            return session_file
    
    print("❌ 未找到任何session文件")
    return None

def convert_session_to_env(session_file):
    """转换session文件为环境变量"""
    try:
        with open(session_file, 'rb') as f:
            session_data = f.read()
        
        encoded_session = base64.b64encode(session_data).decode('utf-8')
        
        print("🔧 Session转换成功！")
        print("=" * 60)
        print("📋 请将以下内容添加到Render环境变量：")
        print("=" * 60)
        print(f"USER_SESSION_DATA={encoded_session}")
        print("=" * 60)
        print("💡 操作步骤：")
        print("1. 复制上面的环境变量")
        print("2. 登录Render Dashboard")
        print("3. 进入您的服务设置")
        print("4. 在Environment Variables中添加上述变量")
        print("5. 重新部署服务")
        print("6. 机器人将自动恢复User API功能")
        
        return True
        
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False

def create_render_env_file():
    """创建Render环境变量文件"""
    env_content = """# Render环境变量配置
# 复制以下内容到Render Dashboard的Environment Variables中

# 基本配置
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token

# User API Session数据（从本地转换）
USER_SESSION_DATA=your_base64_encoded_session_data

# 其他配置
USE_LOCAL_STORAGE=false
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_PRIVATE_KEY=your_firebase_private_key
FIREBASE_CLIENT_EMAIL=your_firebase_client_email
"""
    
    with open('render_env_template.txt', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ Render环境变量模板已创建: render_env_template.txt")

def test_session_conversion():
    """测试session转换"""
    print("🧪 测试session转换...")
    
    # 创建测试session文件
    test_data = b"test_session_data"
    with open('test_session.session', 'wb') as f:
        f.write(test_data)
    
    # 转换测试
    encoded = base64.b64encode(test_data).decode('utf-8')
    decoded = base64.b64decode(encoded)
    
    if decoded == test_data:
        print("✅ Session转换测试通过")
        os.remove('test_session.session')
        return True
    else:
        print("❌ Session转换测试失败")
        return False

def main():
    """主函数"""
    print("🚀 Render环境User API快速设置")
    print("=" * 50)
    
    # 检查Python版本
    if sys.version_info < (3, 6):
        print("❌ 需要Python 3.6或更高版本")
        return
    
    # 测试转换功能
    if not test_session_conversion():
        print("❌ 转换功能测试失败，请检查Python环境")
        return
    
    # 检查本地session文件
    session_file = check_local_session()
    
    if session_file:
        print(f"\n📁 使用session文件: {session_file}")
        
        # 转换session
        if convert_session_to_env(session_file):
            print("\n✅ 设置完成！")
            print("💡 请按照上述步骤在Render中配置环境变量")
        else:
            print("\n❌ 转换失败，请检查session文件")
    else:
        print("\n💡 未找到本地session文件")
        print("请先在本地完成User API登录：")
        print("1. 运行: python lsjmain.py")
        print("2. 完成User API登录")
        print("3. 重新运行此脚本")
    
    # 创建环境变量模板
    create_render_env_file()
    
    print("\n📋 其他方法：")
    print("1. 使用Telegram Web授权")
    print("2. 使用代理服务器")
    print("3. 使用Bot API模式（无需User API）")
    
    print("\n🔗 详细指南: render_user_api_session_guide.md")

if __name__ == "__main__":
    main()
