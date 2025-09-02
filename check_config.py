#!/usr/bin/env python3
"""
配置检查脚本
帮助用户验证机器人配置是否正确
"""

import os
import sys
from dotenv import load_dotenv

def check_config():
    """检查配置是否正确"""
    print("🔍 检查机器人配置...")
    
    # 加载 .env 文件
    load_dotenv()
    
    # 检查必要的环境变量
    required_vars = {
        'BOT_ID': '机器人ID',
        'BOT_NAME': '机器人名称', 
        'API_ID': 'API ID',
        'API_HASH': 'API Hash',
        'BOT_TOKEN': '机器人Token'
    }
    
    missing_vars = []
    invalid_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value or value.startswith('your_'):
            missing_vars.append(f"{var} ({description})")
        else:
            # 验证格式
            if var == 'API_ID':
                try:
                    int(value)
                except ValueError:
                    invalid_vars.append(f"{var} 必须是数字")
            elif var == 'API_HASH':
                if len(value) != 32:
                    invalid_vars.append(f"{var} 必须是32位字符串")
            elif var == 'BOT_TOKEN':
                if ':' not in value or len(value.split(':')) != 2:
                    invalid_vars.append(f"{var} 格式错误，应为 '数字:字符串'")
    
    # 显示结果
    if missing_vars:
        print("❌ 缺少以下配置:")
        for var in missing_vars:
            print(f"   • {var}")
    
    if invalid_vars:
        print("❌ 以下配置格式错误:")
        for var in invalid_vars:
            print(f"   • {var}")
    
    if not missing_vars and not invalid_vars:
        print("✅ 配置检查通过！")
        print("\n📋 当前配置:")
        for var, description in required_vars.items():
            value = os.getenv(var)
            if var == 'BOT_TOKEN':
                # 隐藏token的大部分内容
                if ':' in value:
                    prefix, suffix = value.split(':', 1)
                    display_value = f"{prefix}:{suffix[:8]}..."
                else:
                    display_value = value[:8] + "..."
            else:
                display_value = value
            print(f"   • {description}: {display_value}")
        
        # 检查存储配置
        use_local = os.getenv('USE_LOCAL_STORAGE', 'false').lower() == 'true'
        print(f"   • 存储模式: {'本地存储' if use_local else 'Firebase'}")
        
        return True
    else:
        print("\n💡 请参考 '本地配置指南.md' 文件进行配置")
        return False

if __name__ == "__main__":
    success = check_config()
    sys.exit(0 if success else 1)
