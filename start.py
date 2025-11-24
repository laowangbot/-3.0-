#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目启动脚本
用于简化项目启动过程
"""

import sys
import os
import argparse
import asyncio

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='BTbot模块化Telegram机器人')
    parser.add_argument('--bot', type=str, help='指定机器人名称')
    parser.add_argument('--test', action='store_true', help='运行测试')
    parser.add_argument('--example', action='store_true', help='运行示例')
    
    args = parser.parse_args()
    
    if args.test:
        # 运行导入测试
        print("运行模块导入测试...")
        from tests.test_imports import main as test_main
        sys.exit(test_main())
    
    if args.example:
        # 运行使用示例
        print("运行模块使用示例...")
        from examples.module_usage_example import main as example_main
        example_main()
        return
    
    # 启动主程序
    print("启动BTbot模块化Telegram机器人...")
    try:
        from main import main as bot_main
        asyncio.run(bot_main())
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()