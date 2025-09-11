#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交互式监听功能测试脚本
"""

import asyncio
import logging
from simple_monitor import get_simple_monitor
from pyrogram import Client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def interactive_monitor_test():
    """交互式监听功能测试"""
    try:
        from config import get_config
        config = get_config()
        
        api_id = config.get('api_id')
        api_hash = config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 未找到API配置，请先配置.env文件")
            return
        
        print("🧪 交互式监听功能测试")
        print("=" * 50)
        
        # 获取用户输入
        print("\n📝 请输入监听配置:")
        source_channel = input("源频道 (例如: @xsm58 或 -1001234567890): ").strip()
        target_channel = input("目标频道 (例如: @xsm53 或 -1001234567890): ").strip()
        
        if not source_channel or not target_channel:
            print("❌ 源频道和目标频道不能为空")
            return
        
        # 创建客户端
        client = Client("interactive_monitor_test", api_id=api_id, api_hash=api_hash)
        
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
        
        # 创建监听任务
        print(f"\n🔧 创建监听任务...")
        success, message = await monitor.start_monitoring(source_channel, target_channel, user_id)
        
        if not success:
            print(f"❌ 创建监听任务失败: {message}")
            await client.stop()
            return
        
        print(f"✅ 监听任务创建成功: {message}")
        
        # 显示监听状态
        status = monitor.get_monitoring_status()
        print(f"\n📊 监听状态:")
        print(f"• 运行状态: {'✅ 运行中' if status['is_running'] else '❌ 已停止'}")
        print(f"• 活跃任务: {status['active_tasks']} 个")
        print(f"• 总任务数: {status['total_tasks']} 个")
        print(f"• 处理消息: {status['total_messages_processed']} 条")
        
        # 测试连接
        user_tasks = monitor.get_user_tasks(user_id)
        if user_tasks:
            task = user_tasks[0]
            print(f"\n🧪 测试连接...")
            test_result = await monitor.test_monitoring(task['task_id'])
            
            if test_result['success']:
                print(f"✅ 连接测试成功: {test_result['message']}")
                if test_result['messages']:
                    print(f"📋 最新消息:")
                    for i, msg in enumerate(test_result['messages'][:3], 1):
                        print(f"  {i}. {msg['text'][:50]}...")
            else:
                print(f"❌ 连接测试失败: {test_result['message']}")
        
        print(f"\n⏰ 监听器已启动，请在源频道发送消息...")
        print(f"💡 观察下面的日志输出，应该看到消息监听和转发信息")
        print(f"⏹️ 按 Ctrl+C 停止监听")
        
        try:
            # 持续运行监听
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n⏹️ 用户停止监听")
        
        # 显示最终状态
        final_status = monitor.get_monitoring_status()
        print(f"\n📊 最终状态:")
        print(f"• 处理消息: {final_status['total_messages_processed']} 条")
        
        # 停止客户端
        await client.stop()
        print("✅ 测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🧪 交互式监听功能测试")
    print("=" * 50)
    print("⚠️ 请确保：")
    print("1. 已配置正确的API凭据")
    print("2. User API已登录")
    print("3. 有源频道和目标频道的访问权限")
    print("4. 在测试期间在源频道发送消息")
    print("=" * 50)
    
    asyncio.run(interactive_monitor_test())
