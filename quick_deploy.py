#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速部署脚本
帮助用户快速配置Render部署所需的环境变量
"""

import json
import os
from typing import Dict, Any

def print_banner():
    """打印欢迎横幅"""
    print("=" * 60)
    print("🚀 Telegram搬运机器人 - Render快速部署工具")
    print("=" * 60)
    print()

def get_user_input() -> Dict[str, str]:
    """获取用户输入"""
    config = {}
    
    print("📋 请提供以下配置信息：")
    print()
    
    # Telegram配置
    print("🔑 Telegram配置：")
    config['BOT_TOKEN'] = input("请输入Bot Token: ").strip()
    config['API_ID'] = input("请输入API ID: ").strip()
    config['API_HASH'] = input("请输入API Hash: ").strip()
    print()
    
    # Firebase配置
    print("🔥 Firebase配置：")
    config['FIREBASE_PROJECT_ID'] = input("请输入Firebase项目ID: ").strip()
    
    print("\n📄 Firebase凭据配置：")
    print("请选择Firebase凭据配置方式：")
    print("1. 直接输入JSON内容")
    print("2. 从文件读取")
    
    choice = input("请选择 (1/2): ").strip()
    
    if choice == "1":
        print("\n请输入Firebase凭据JSON内容（可以多行输入，输入完成后按Ctrl+Z+Enter结束）：")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        config['FIREBASE_CREDENTIALS'] = '\n'.join(lines)
    elif choice == "2":
        file_path = input("请输入JSON文件路径: ").strip()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config['FIREBASE_CREDENTIALS'] = f.read()
        except FileNotFoundError:
            print("❌ 文件不存在，请检查路径")
            return {}
    else:
        print("❌ 无效选择")
        return {}
    
    # Render配置
    print("\n🌐 Render配置：")
    app_name = input("请输入Render应用名称（将用于生成URL）: ").strip()
    config['RENDER_EXTERNAL_URL'] = f"https://{app_name}.onrender.com"
    
    # 其他配置
    config['PORT'] = "8080"
    config['USE_LOCAL_STORAGE'] = "false"
    
    return config

def validate_config(config: Dict[str, str]) -> bool:
    """验证配置"""
    required_fields = ['BOT_TOKEN', 'API_ID', 'API_HASH', 'FIREBASE_PROJECT_ID', 'FIREBASE_CREDENTIALS']
    
    for field in required_fields:
        if not config.get(field):
            print(f"❌ 缺少必需配置: {field}")
            return False
    
    # 验证Firebase凭据格式
    try:
        json.loads(config['FIREBASE_CREDENTIALS'])
    except json.JSONDecodeError:
        print("❌ Firebase凭据JSON格式错误")
        return False
    
    return True

def generate_render_yaml():
    """生成render.yaml文件"""
    yaml_content = """services:
  - type: web
    name: telegram-bot
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: PORT
        value: 8080
      - key: RENDER_EXTERNAL_URL
        sync: false
      - key: BOT_TOKEN
        sync: false
      - key: API_ID
        sync: false
      - key: API_HASH
        sync: false
      - key: FIREBASE_PROJECT_ID
        sync: false
      - key: FIREBASE_CREDENTIALS
        sync: false
    healthCheckPath: /health
    autoDeploy: true
    disk:
      name: data
      mountPath: /opt/render/project/src/data
      sizeGB: 1
"""
    
    with open('render.yaml', 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    
    print("✅ 已生成 render.yaml 文件")

def generate_env_example(config: Dict[str, str]):
    """生成环境变量示例文件"""
    env_content = f"""# Telegram配置
BOT_TOKEN={config['BOT_TOKEN']}
API_ID={config['API_ID']}
API_HASH={config['API_HASH']}

# Firebase配置
FIREBASE_PROJECT_ID={config['FIREBASE_PROJECT_ID']}
FIREBASE_CREDENTIALS={config['FIREBASE_CREDENTIALS']}

# Render配置
RENDER_EXTERNAL_URL={config['RENDER_EXTERNAL_URL']}
PORT={config['PORT']}

# 其他配置
USE_LOCAL_STORAGE={config['USE_LOCAL_STORAGE']}
"""
    
    with open('.env.example', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ 已生成 .env.example 文件")

def print_deployment_instructions(config: Dict[str, str]):
    """打印部署说明"""
    print("\n" + "=" * 60)
    print("📋 Render部署说明")
    print("=" * 60)
    print()
    print("1. 访问 https://render.com")
    print("2. 使用GitHub账号登录")
    print("3. 点击 'New' → 'Web Service'")
    print("4. 选择仓库: laowangbot/bybot3.0")
    print("5. 配置服务设置：")
    print("   - Name: telegram-bot")
    print("   - Region: Singapore (推荐)")
    print("   - Branch: main")
    print("   - Runtime: Python 3")
    print("   - Build Command: pip install -r requirements.txt")
    print("   - Start Command: python main.py")
    print()
    print("6. 在Environment标签中添加以下环境变量：")
    print()
    for key, value in config.items():
        if key == 'FIREBASE_CREDENTIALS':
            print(f"   {key}=<您的Firebase凭据JSON>")
        else:
            print(f"   {key}={value}")
    print()
    print("7. 设置Health Check Path: /health")
    print("8. 点击 'Create Web Service'")
    print()
    print("🎉 部署完成后，您的机器人将在以下地址运行：")
    print(f"   {config['RENDER_EXTERNAL_URL']}")
    print()
    print("📊 健康检查端点：")
    print(f"   {config['RENDER_EXTERNAL_URL']}/health")
    print(f"   {config['RENDER_EXTERNAL_URL']}/status")

def main():
    """主函数"""
    print_banner()
    
    # 获取用户配置
    config = get_user_input()
    
    if not config:
        print("❌ 配置获取失败")
        return
    
    # 验证配置
    if not validate_config(config):
        print("❌ 配置验证失败")
        return
    
    print("\n✅ 配置验证通过")
    
    # 生成配置文件
    generate_render_yaml()
    generate_env_example(config)
    
    # 打印部署说明
    print_deployment_instructions(config)
    
    print("\n🎉 快速部署配置完成！")
    print("请按照上述说明在Render上部署您的机器人。")

if __name__ == "__main__":
    main()
