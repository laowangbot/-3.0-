#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目部署脚本
用于简化项目部署过程
"""

import os
import sys
import subprocess
import argparse

def check_dependencies():
    """检查项目依赖"""
    print("检查项目依赖...")
    try:
        # 检查Python版本
        python_version = sys.version_info
        if python_version < (3, 8):
            print("❌ Python版本过低，需要3.8或更高版本")
            return False
        
        print(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # 检查依赖包
        required_packages = [
            ('pyrogram', 'pyrogram'),
            ('tgcrypto', 'tgcrypto'), 
            ('aiohttp', 'aiohttp'),
            ('dotenv', 'python-dotenv'),
            ('colorlog', 'colorlog'),
            ('psutil', 'psutil')
        ]
        
        missing_packages = []
        for module_name, package_name in required_packages:
            try:
                __import__(module_name)
                print(f"✅ {package_name} 已安装")
            except ImportError:
                missing_packages.append(package_name)
                print(f"❌ {package_name} 未安装")
        
        if missing_packages:
            print(f"缺失的依赖包: {', '.join(missing_packages)}")
            return False
            
        return True
    except Exception as e:
        print(f"检查依赖时出错: {e}")
        return False

def check_config():
    """检查配置文件"""
    print("检查配置文件...")
    env_file = '.env'
    if not os.path.exists(env_file):
        print("❌ 未找到 .env 配置文件")
        print("请复制 render_env_template.env 为 .env 并填写相关信息")
        return False
    
    # 检查必要配置项
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = []
    
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ 缺失必要配置项: {', '.join(missing_vars)}")
        return False
    
    print("✅ 配置文件检查通过")
    return True

def setup_directories():
    """设置必要目录"""
    print("设置必要目录...")
    directories = [
        'sessions',
        'data',
        'logs',
        'backups_sessions'
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ 目录 {directory} 创建成功")
        except Exception as e:
            print(f"❌ 创建目录 {directory} 失败: {e}")
            return False
    
    return True

def deploy():
    """执行部署"""
    print("开始部署BTbot模块化Telegram机器人...")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        print("❌ 依赖检查失败")
        return False
    
    # 检查配置
    if not check_config():
        print("❌ 配置检查失败")
        return False
    
    # 设置目录
    if not setup_directories():
        print("❌ 目录设置失败")
        return False
    
    print("=" * 50)
    print("✅ 部署检查完成，项目已准备就绪！")
    print("\n下一步操作：")
    print("1. 运行 python start.py 启动机器人")
    print("2. 或运行 python main.py 直接启动")
    return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='BTbot部署脚本')
    parser.add_argument('--check', action='store_true', help='仅检查配置')
    
    args = parser.parse_args()
    
    if args.check:
        # 仅检查配置
        check_dependencies()
        check_config()
        setup_directories()
    else:
        # 执行完整部署
        deploy()

if __name__ == "__main__":
    main()