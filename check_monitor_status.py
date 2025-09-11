#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查监听状态脚本
"""

import asyncio
import logging
from simple_monitor import get_simple_monitor
from pyrogram import Client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_monitor_status():
    """检查监听状态"""
    try:
        from config import get_config
        config = get_config()
        
        api_id = config.get('api_id')
        api_hash = config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 未找到API配置")
            return
        
        # 创建客户端
        client = Client("check_monitor", api_id=api_id, api_hash=api_hash)
        
        # 启动客户端
        await client.start()
        print("✅ 客户端已启动")
        
        # 获取监听器
        monitor = get_simple_monitor(client)
        
        # 获取详细状态
        status = monitor.get_detailed_status()
        
        print("\n📊 监听器详细状态:")
        print(f"• 运行状态: {'✅ 运行中' if status['is_running'] else '❌ 已停止'}")
        print(f"• 活跃任务: {status['active_tasks']} 个")
        print(f"• 总任务数: {status['total_tasks']} 个")
        print(f"• 处理消息: {status['total_messages_processed']} 条")
        
        if status['tasks']:
            print("\n📋 任务详情:")
            for i, task in enumerate(status['tasks'], 1):
                print(f"{i}. 任务ID: {task['task_id']}")
                print(f"   用户ID: {task['user_id']}")
                print(f"   源频道: {task['source_channel']} ({task['source_title']})")
                print(f"   目标频道: {task['target_channel']} ({task['target_title']})")
                print(f"   状态: {task['status']}")
                print(f"   消息数: {task['message_count']}")
                print()
        
        # 停止客户端
        await client.stop()
        print("✅ 检查完成")
        
    except Exception as e:
        logger.error(f"❌ 检查失败: {e}")

if __name__ == "__main__":
    print("🔍 监听状态检查")
    print("=" * 50)
    asyncio.run(check_monitor_status())


