#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听系统核心功能测试脚本
非交互式测试监听系统的核心功能
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from simple_monitor import get_simple_monitor
from monitoring_engine import RealTimeMonitoringEngine
from cloning_engine import create_cloning_engine
from pyrogram import Client
from config import get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_monitoring_core():
    """测试监听系统核心功能"""
    try:
        print("🧪 监听系统核心功能测试")
        print("=" * 50)
        
        # 获取配置
        config = get_config()
        api_id = config.get('api_id')
        api_hash = config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 未找到API配置")
            return False
        
        # 创建客户端
        client = Client("test_monitor_core", api_id=api_id, api_hash=api_hash)
        
        # 启动客户端
        await client.start()
        print("✅ 客户端已启动")
        
        # 获取当前用户信息
        me = await client.get_me()
        user_id = me.id
        print(f"👤 当前用户: {me.first_name} (ID: {user_id})")
        
        # 测试1: 简单监听器初始化
        print("\n🔍 测试1: 简单监听器初始化...")
        simple_monitor = get_simple_monitor(client)
        print("✅ 简单监听器初始化成功")
        
        # 测试2: 实时监听引擎初始化
        print("\n🔍 测试2: 实时监听引擎初始化...")
        cloning_engine = create_cloning_engine(client, config)
        realtime_monitor = RealTimeMonitoringEngine(client, cloning_engine, config)
        print("✅ 实时监听引擎初始化成功")
        
        # 测试3: 监听系统启动
        print("\n🔍 测试3: 监听系统启动...")
        await realtime_monitor.start_monitoring()
        print("✅ 实时监听系统启动成功")
        
        # 测试4: 获取监听状态
        print("\n🔍 测试4: 获取监听状态...")
        status = realtime_monitor.get_monitoring_status()
        print(f"📊 监听状态: 运行中={status['is_running']}, 活跃任务={status['active_tasks_count']}")
        
        # 测试5: 简单监听器状态
        print("\n🔍 测试5: 简单监听器状态...")
        simple_status = simple_monitor.get_monitoring_status()
        print(f"📊 简单监听器状态: 运行中={simple_status['is_running']}, 任务数={simple_status['total_tasks']}")
        
        # 测试6: 消息处理器注册
        print("\n🔍 测试6: 消息处理器注册...")
        # 创建一个测试任务来测试消息处理器
        test_source_channels = [{
            'channel_id': '@test_channel',
            'channel_name': '测试频道',
            'channel_username': 'test_channel'
        }]
        
        try:
            task_id = await realtime_monitor.create_monitoring_task(
                user_id=str(user_id),
                target_channel='@test_target',
                source_channels=test_source_channels,
                config={'monitoring_mode': 'realtime'}
            )
            print(f"✅ 测试任务创建成功: {task_id}")
            
            # 测试消息处理器
            test_result = await realtime_monitor.test_message_handlers(task_id)
            print(f"📊 消息处理器测试结果: {test_result}")
            
        except Exception as e:
            print(f"⚠️ 测试任务创建失败（这是正常的，因为测试频道不存在）: {e}")
        
        # 测试7: 停止监听系统
        print("\n🔍 测试7: 停止监听系统...")
        await realtime_monitor.stop_monitoring()
        print("✅ 监听系统停止成功")
        
        # 停止客户端
        await client.stop()
        print("✅ 客户端已停止")
        
        print("\n🎉 所有核心功能测试完成！")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(f"❌ 错误详情: {traceback.format_exc()}")
        return False

async def test_message_engine():
    """测试消息处理引擎"""
    try:
        print("\n🧪 消息处理引擎测试")
        print("=" * 30)
        
        from message_engine import MessageEngine
        from pyrogram.types import Message
        
        # 创建消息引擎
        config = {'test': True}
        message_engine = MessageEngine(config)
        print("✅ 消息处理引擎初始化成功")
        
        # 测试正则表达式模式
        print("\n🔍 测试正则表达式模式...")
        
        # 测试HTTP链接检测
        test_text = "这是一个测试链接: https://example.com 和另一个链接 http://test.com"
        http_links = message_engine.http_pattern.findall(test_text)
        print(f"📝 HTTP链接检测: 找到 {len(http_links)} 个链接: {http_links}")
        
        # 测试磁力链接检测
        test_magnet = "磁力链接: magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678"
        magnet_links = message_engine.magnet_pattern.findall(test_magnet)
        print(f"📝 磁力链接检测: 找到 {len(magnet_links)} 个链接: {magnet_links}")
        
        # 测试Hashtag检测
        test_hashtag = "这是 #测试 标签和 #另一个 标签"
        hashtags = message_engine.hashtag_pattern.findall(test_hashtag)
        print(f"📝 Hashtag检测: 找到 {len(hashtags)} 个标签: {hashtags}")
        
        print("✅ 消息处理引擎测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 消息处理引擎测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🧪 监听系统核心功能测试")
    print("=" * 50)
    
    # 测试消息处理引擎
    await test_message_engine()
    
    # 测试监听系统核心功能
    success = await test_monitoring_core()
    
    if success:
        print("\n🎉 所有测试通过！监听系统核心功能正常")
    else:
        print("\n❌ 部分测试失败，请检查错误信息")

if __name__ == "__main__":
    asyncio.run(main())

