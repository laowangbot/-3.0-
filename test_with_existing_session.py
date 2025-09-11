#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用现有会话测试简化版监听系统
从现有会话文件中读取User API配置
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pyrogram import Client
from simple_monitoring_engine import SimpleMonitoringEngine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_with_existing_session():
    """使用现有会话测试监听系统"""
    try:
        print("🚀 使用现有会话测试简化版监听系统")
        print("=" * 50)
        
        # 检查现有会话文件
        session_files = [
            "sessions/user_session.session",
            "user_session.session",
            "bot_session_default.session"
        ]
        
        session_file = None
        for file in session_files:
            if os.path.exists(file):
                session_file = file
                break
        
        if not session_file:
            print("❌ 未找到现有会话文件")
            print("请先通过机器人界面登录User API")
            return False
        
        print(f"✅ 找到会话文件: {session_file}")
        
        # 尝试从会话文件中获取API信息
        # 注意：这里需要您手动提供API凭据，因为会话文件是加密的
        print("\n📝 请输入User API配置:")
        api_id = input("API ID: ").strip()
        api_hash = input("API Hash: ").strip()
        
        if not api_id or not api_hash:
            print("❌ API ID和API Hash不能为空")
            return False
        
        try:
            api_id = int(api_id)
        except ValueError:
            print("❌ API ID必须是数字")
            return False
        
        # 创建User API客户端
        client = Client(
            "test_session",
            api_id=api_id,
            api_hash=api_hash,
            workdir="sessions"
        )
        
        print("🔄 启动User API客户端...")
        await client.start()
        print("✅ User API客户端启动成功")
        
        # 获取客户端信息
        me = await client.get_me()
        print(f"📱 当前用户: {me.first_name} (@{me.username})")
        
        # 创建监听引擎
        config = {
            'bot_id': 'default_bot',
            'use_local_storage': True
        }
        
        monitoring_engine = SimpleMonitoringEngine(client, config)
        print("✅ 简化版监听引擎创建成功")
        
        # 启动监听系统
        await monitoring_engine.start_monitoring()
        print("✅ 监听系统启动成功")
        
        # 获取用户输入
        print("\n" + "=" * 50)
        print("📝 请输入测试参数:")
        
        target_channel = input("目标频道用户名或ID (例如: @your_channel): ").strip()
        if not target_channel:
            print("❌ 目标频道不能为空")
            return False
        
        source_channels_input = input("源频道用户名或ID，多个用逗号分隔 (例如: @source1,@source2): ").strip()
        if not source_channels_input:
            print("❌ 源频道不能为空")
            return False
        
        source_channels = [ch.strip() for ch in source_channels_input.split(',') if ch.strip()]
        if not source_channels:
            print("❌ 没有有效的源频道")
            return False
        
        print(f"\n📋 测试配置:")
        print(f"   目标频道: {target_channel}")
        print(f"   源频道: {', '.join(source_channels)}")
        
        # 创建监听任务
        test_user_id = "7951964655"  # 您的用户ID
        
        print(f"\n🔧 创建监听任务...")
        task_id = await monitoring_engine.create_monitoring_task(
            user_id=test_user_id,
            target_channel=target_channel,
            source_channels=source_channels
        )
        
        print(f"✅ 监听任务创建成功: {task_id}")
        
        # 获取监听状态
        status = monitoring_engine.get_monitoring_status()
        print(f"\n📊 监听状态:")
        print(f"   系统运行: {'✅' if status.get('is_running') else '❌'}")
        print(f"   活跃任务: {status.get('active_tasks_count', 0)} 个")
        print(f"   总任务数: {status.get('total_tasks_count', 0)} 个")
        
        # 等待用户确认
        print("\n" + "=" * 50)
        print("✅ 监听任务已创建并启动")
        print("💡 请在源频道发送一条测试消息")
        print("⏰ 监听系统将运行60秒进行测试")
        print("=" * 50)
        
        # 运行60秒进行测试
        for i in range(60):
            await asyncio.sleep(1)
            if i % 10 == 0 and i > 0:
                print(f"⏰ 已运行 {i} 秒...")
        
        # 再次检查状态
        status = monitoring_engine.get_monitoring_status()
        print(f"\n📊 最终监听状态:")
        print(f"   系统运行: {'✅' if status.get('is_running') else '❌'}")
        print(f"   活跃任务: {status.get('active_tasks_count', 0)} 个")
        
        # 显示任务统计
        tasks = status.get('tasks', [])
        for task in tasks:
            if task.get('task_id') == task_id:
                stats = task.get('stats', {})
                print(f"   任务统计:")
                print(f"     处理消息: {stats.get('total_processed', 0)} 条")
                print(f"     成功转发: {stats.get('successful_transfers', 0)} 条")
                print(f"     失败转发: {stats.get('failed_transfers', 0)} 条")
                print(f"     过滤消息: {stats.get('filtered_messages', 0)} 条")
                break
        
        # 停止监听系统
        print(f"\n🛑 停止监听系统...")
        await monitoring_engine.stop_monitoring()
        print("✅ 监听系统已停止")
        
        # 停止客户端
        print(f"🛑 停止User API客户端...")
        await client.stop()
        print("✅ User API客户端已停止")
        
        print("\n🎉 测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print(f"❌ 错误详情: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("🔧 使用现有会话测试简化版监听系统")
    print("=" * 50)
    
    # 运行测试
    success = asyncio.run(test_with_existing_session())
    
    if success:
        print("\n✅ 测试成功！简化版监听系统工作正常")
    else:
        print("\n❌ 测试失败！请检查配置和日志")




