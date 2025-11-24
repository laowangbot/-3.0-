#!/usr/bin/env python3
"""
Session转换工具
用于在本地和Render环境之间转换User API session数据
"""

import base64
import os
import json
import sys
from pathlib import Path

def convert_session_to_env(session_file="user_session.session"):
    """将session文件转换为环境变量格式"""
    try:
        if not os.path.exists(session_file):
            print(f"❌ Session文件不存在: {session_file}")
            return False
        
        # 读取session文件
        with open(session_file, 'rb') as f:
            session_data = f.read()
        
        # 编码为base64
        encoded_session = base64.b64encode(session_data).decode('utf-8')
        
        print("🔧 Session转换成功！")
        print("=" * 50)
        print("📋 将以下内容添加到Render环境变量：")
        print("=" * 50)
        print(f"USER_SESSION_DATA={encoded_session}")
        print("=" * 50)
        print("💡 使用方法：")
        print("1. 复制上面的环境变量")
        print("2. 在Render Dashboard中添加环境变量")
        print("3. 重新部署应用")
        print("4. 机器人将自动恢复User API session")
        
        return True
        
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False

def convert_env_to_session(env_data):
    """将环境变量数据转换为session文件"""
    try:
        # 解码base64数据
        decoded_session = base64.b64decode(env_data)
        
        # 写入session文件
        with open('user_session.session', 'wb') as f:
            f.write(decoded_session)
        
        print("✅ 从环境变量恢复session成功")
        print("📁 Session文件已保存: user_session.session")
        
        return True
        
    except Exception as e:
        print(f"❌ 恢复失败: {e}")
        return False

def create_session_script():
    """创建自动恢复session的脚本"""
    script_content = '''#!/usr/bin/env python3
"""
自动恢复User API session
在Render环境中运行此脚本
"""

import os
import base64
import logging

def restore_user_session():
    """从环境变量恢复User API session"""
    try:
        # 获取环境变量
        session_data = os.getenv('USER_SESSION_DATA')
        
        if not session_data:
            print("❌ 未找到USER_SESSION_DATA环境变量")
            return False
        
        # 解码session数据
        decoded_session = base64.b64decode(session_data)
        
        # 写入session文件
        with open('user_session.session', 'wb') as f:
            f.write(decoded_session)
        
        print("✅ User API session恢复成功")
        return True
        
    except Exception as e:
        print(f"❌ 恢复session失败: {e}")
        return False

if __name__ == "__main__":
    restore_user_session()
'''
    
    with open('restore_session.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("✅ 自动恢复脚本已创建: restore_session.py")

def main():
    """主函数"""
    print("🔧 User API Session转换工具")
    print("=" * 40)
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python session_converter.py convert [session_file]")
        print("  python session_converter.py restore [env_data]")
        print("  python session_converter.py script")
        print("")
        print("示例:")
        print("  python session_converter.py convert")
        print("  python session_converter.py convert user_session.session")
        print("  python session_converter.py restore <base64_data>")
        print("  python session_converter.py script")
        return
    
    command = sys.argv[1]
    
    if command == "convert":
        session_file = sys.argv[2] if len(sys.argv) > 2 else "user_session.session"
        convert_session_to_env(session_file)
        
    elif command == "restore":
        if len(sys.argv) < 3:
            print("❌ 请提供环境变量数据")
            return
        env_data = sys.argv[2]
        convert_env_to_session(env_data)
        
    elif command == "script":
        create_session_script()
        
    else:
        print(f"❌ 未知命令: {command}")

if __name__ == "__main__":
    main()
