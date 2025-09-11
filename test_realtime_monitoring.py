#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时监听功能测试脚本
"""

import asyncio
import logging
from simple_monitor import SimpleMonitor
from pyrogram import Client

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_realtime_monitoring():
    """测试实时监听功能"""
    try:
        # 这里需要您的User API配置
        from config import get_config
        config = get_config()
        
        api_id = config.get('api_id')
        api_hash = config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 未找到API配置，请先配置.env文件")
            return
        
        print("🔍 开始测试实时监听功能")
        
        # 创建客户端
        client = Client("test_realtime_monitor", api_id=api_id, api_hash=api_hash)
        
        # 启动客户端
        await client.start()
        print("✅ 客户端已启动")
        
        # 获取当前登录用户的信息
        me = await client.get_me()
        user_id = me.id
        print(f"👤 当前登录用户: {me.first_name} (ID: {user_id})")
        
        # 创建监听器
        monitor = SimpleMonitor(client)
        print("✅ 监听器已创建")
        
        # 获取用户输入
        print("\n📝 请输入监听配置:")
        source_channel = input("源频道 (例如: @xsm58 或 -1001234567890): ").strip()
        target_channel = input("目标频道 (例如: @xsm53 或 -1001234567890): ").strip()
        
        if not source_channel or not target_channel:
            print("❌ 源频道和目标频道不能为空")
            return
        
        print(f"\n📋 监听配置:")
        print(f"• 源频道: {source_channel}")
        print(f"• 目标频道: {target_channel}")
        print(f"• 用户ID: {user_id} (自动获取)")
        
        print(f"🔍 创建监听任务: {source_channel} -> {target_channel}")
        success, message = await monitor.start_monitoring(source_channel, target_channel, user_id)
        
        if success:
            print(f"✅ 监听任务创建成功: {message}")
            
            # 获取监听状态
            status = monitor.get_monitoring_status()
            print(f"📊 监听状态: {status}")
            
            # 获取用户任务
            user_tasks = monitor.get_user_tasks(user_id)
            print(f"👤 用户任务: {len(user_tasks)} 个")
            
            # 测试连接
            if user_tasks:
                task = user_tasks[0]
                test_result = await monitor.test_monitoring(task['task_id'])
                print(f"🧪 连接测试: {test_result}")
            
            print("\n💡 现在请在源频道发送一条消息来测试实时监听")
            print("⏰ 监听器将运行30秒...")
            
            # 运行30秒监听
            await asyncio.sleep(30)
            
        else:
            print(f"❌ 监听任务创建失败: {message}")
        
        # 停止客户端
        await client.stop()
        print("✅ 测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🧪 实时监听功能测试")
    print("=" * 50)
    print("⚠️ 请确保：")
    print("1. 已配置正确的API凭据")
    print("2. User API已登录")
    print("3. 有源频道和目标频道的访问权限")
    print("=" * 50)
    
    asyncio.run(test_realtime_monitoring())
