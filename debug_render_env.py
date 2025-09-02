#!/usr/bin/env python3
"""
调试Render环境变量
"""

import os
import json

def debug_render_environment():
    """调试Render环境变量"""
    print("🔍 Render环境变量调试:")
    print("=" * 50)
    
    # 检查环境检测
    print("📋 环境检测:")
    print(f"   RENDER: {os.getenv('RENDER')}")
    print(f"   RENDER_EXTERNAL_URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    print(f"   PORT: {os.getenv('PORT')}")
    print(f"   HOST: {os.getenv('HOST')}")
    
    # 检查机器人配置
    print("\n🤖 机器人配置:")
    print(f"   BOT_ID: {os.getenv('BOT_ID')}")
    print(f"   BOT_NAME: {os.getenv('BOT_NAME')}")
    print(f"   API_ID: {os.getenv('API_ID')}")
    print(f"   API_HASH: {os.getenv('API_HASH', '')[:8]}...")
    print(f"   BOT_TOKEN: {os.getenv('BOT_TOKEN', '')[:8]}...")
    
    # 检查Firebase配置
    print("\n🔥 Firebase配置:")
    print(f"   FIREBASE_PROJECT_ID: {os.getenv('FIREBASE_PROJECT_ID')}")
    firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
    if firebase_creds:
        try:
            creds = json.loads(firebase_creds)
            print(f"   FIREBASE_CREDENTIALS: project_id={creds.get('project_id')}")
        except:
            print(f"   FIREBASE_CREDENTIALS: 格式错误")
    else:
        print(f"   FIREBASE_CREDENTIALS: 未设置")
    
    # 检查存储配置
    print("\n💾 存储配置:")
    print(f"   USE_LOCAL_STORAGE: {os.getenv('USE_LOCAL_STORAGE')}")
    
    # 检查所有环境变量
    print("\n📝 所有环境变量:")
    for key, value in sorted(os.environ.items()):
        if any(keyword in key.upper() for keyword in ['BOT', 'API', 'FIREBASE', 'RENDER', 'PORT', 'HOST']):
            if 'TOKEN' in key.upper() or 'HASH' in key.upper() or 'CREDENTIALS' in key.upper():
                print(f"   {key}: {value[:8]}...")
            else:
                print(f"   {key}: {value}")

if __name__ == "__main__":
    debug_render_environment()
