#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听功能调试测试脚本
"""

import asyncio
import logging
from simple_monitor import get_simple_monitor
from pyrogram import Client

# 配置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_monitor_debug():
    """测试监听功能调试"""
    try:
        from config import get_config
        config = get_config()
        
        api_id = config.get('api_id')
        api_hash = config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 未找到API配置")
            return
        
        print("🔍 开始监听功能调试测试")
        
        # 获取用户输入
        print("\n📝 请输入监听配置:")
        source_channel = input("源频道 (例如: @xsm58 或 -1001234567890): ").strip()
        target_channel = input("目标频道 (例如: @xsm53 或 -1001234567890): ").strip()
        
        if not source_channel or not target_channel:
            print("❌ 源频道和目标频道不能为空")
            return
        
        # 创建客户端
        client = Client("test_monitor_debug", api_id=api_id, api_hash=api_hash)
        
        # 启动客户端
        await client.start()
        print("✅ 客户端已启动")
        
        # 获取当前登录用户的信息
        me = await client.get_me()
        user_id = me.id
        print(f"👤 当前登录用户: {me.first_name} (ID: {user_id})")
        
        print(f"\n📋 监听配置:")
        print(f"• 源频道: {source_channel}")
        print(f"• 目标频道: {target_channel}")
        print(f"• 用户ID: {user_id} (自动获取)")
        
        # 获取监听器
        monitor = get_simple_monitor(client)
        
        # 创建新的监听任务
        print(f"\n🔧 创建监听任务...")
        success, message = await monitor.start_monitoring(source_channel, target_channel, user_id)
        
        if not success:
            print(f"❌ 创建监听任务失败: {message}")
            await client.stop()
            return
        
        print(f"✅ 监听任务创建成功: {message}")
        
        # 检查现有任务
        status = monitor.get_monitoring_status()
        print(f"\n📊 当前监听状态:")
        print(f"• 运行状态: {'✅ 运行中' if status['is_running'] else '❌ 已停止'}")
        print(f"• 活跃任务: {status['active_tasks']} 个")
        print(f"• 总任务数: {status['total_tasks']} 个")
        print(f"• 处理消息: {status['total_messages_processed']} 条")
        
        if status['tasks']:
            print(f"\n📋 任务详情:")
            for i, task in enumerate(status['tasks'], 1):
                print(f"{i}. 任务ID: {task['task_id']}")
                print(f"   源频道: {task['source_channel']} ({task['source_title']})")
                print(f"   目标频道: {task['target_channel']} ({task['target_title']})")
                print(f"   状态: {task['status']}")
                print(f"   消息数: {task['message_count']}")
        
        print(f"\n⏰ 监听器将运行60秒，请在源频道发送消息...")
        print(f"💡 观察日志输出，应该看到消息监听和转发信息")
        
        # 运行60秒监听
        await asyncio.sleep(60)
        
        # 检查最终状态
        final_status = monitor.get_monitoring_status()
        print(f"\n📊 最终监听状态:")
        print(f"• 处理消息: {final_status['total_messages_processed']} 条")
        
        # 停止客户端
        await client.stop()
        print("✅ 调试测试完成")
        
    except Exception as e:
        logger.error(f"❌ 调试测试失败: {e}")

if __name__ == "__main__":
    print("🧪 监听功能调试测试")
    print("=" * 50)
    print("⚠️ 请确保：")
    print("1. 已配置正确的API凭据")
    print("2. User API已登录")
    print("3. 有源频道和目标频道的访问权限")
    print("4. 在测试期间在源频道发送消息")
    print("=" * 50)
    
    asyncio.run(test_monitor_debug())
