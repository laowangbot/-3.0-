#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试5个频道同时更新的处理能力
验证轮询监听系统是否能不漏信息地搬运
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from monitoring_engine import RealTimeMonitoringEngine
from log_config import setup_bot_logging

async def test_concurrent_channels():
    """测试5个频道同时更新的处理能力"""
    print("🧪 开始测试5个频道同时更新的处理能力...")
    
    # 设置日志
    logger = setup_bot_logging(level='INFO', enable_file=False)
    
    # 模拟客户端
    class MockClient:
        def __init__(self):
            self.is_connected = True
            self.me = None
            self.message_history = {}  # 模拟频道消息历史
        
        async def get_chat_history(self, chat_id, limit=100):
            """模拟获取频道历史消息"""
            channel_id = str(chat_id)
            if channel_id not in self.message_history:
                self.message_history[channel_id] = []
            
            # 返回模拟消息
            for msg in self.message_history[channel_id][-limit:]:
                yield msg
        
        def add_handler(self, handler):
            """模拟添加消息处理器"""
            pass
    
    # 创建模拟客户端
    mock_client = MockClient()
    
    # 创建模拟搬运引擎
    class MockCloningEngine:
        def __init__(self):
            self.tasks = {}
        
        async def create_task(self, **kwargs):
            """模拟创建搬运任务"""
            task_id = f"mock_task_{len(self.tasks)}"
            self.tasks[task_id] = kwargs
            return task_id
    
    # 创建实时监听引擎
    realtime_engine = RealTimeMonitoringEngine(
        client=mock_client,
        cloning_engine=MockCloningEngine(),
        config={'bot_id': 'test_bot'}
    )
    
    # 创建5个频道的监听任务
    source_channels = []
    for i in range(5):
        channel_id = f"-100{i+1}"
        source_channels.append({
            'channel_id': channel_id,
            'channel_name': f'测试频道{i+1}',
            'channel_username': f'test_channel_{i+1}',
            'last_message_id': 0
        })
    
    # 创建监听任务
    task_id = await realtime_engine.create_monitoring_task(
        user_id="test_user",
        target_channel="-100999",
        source_channels=source_channels,
        config={'monitoring_mode': 'realtime'}
    )
    
    print(f"✅ 创建监听任务: {task_id}")
    
    # 启动监听系统
    await realtime_engine.start_monitoring()
    await realtime_engine.start_monitoring_task(task_id)
    
    print("🚀 监听系统已启动")
    
    # 模拟5个频道同时更新消息
    print("\n📡 模拟5个频道同时更新消息...")
    
    # 为每个频道添加多条消息
    for i, channel in enumerate(source_channels):
        channel_id = channel['channel_id']
        mock_client.message_history[channel_id] = []
        
        # 每个频道添加10条消息
        for j in range(1, 11):
            message_id = j
            message = MockMessage(
                id=message_id,
                chat_id=int(channel_id),
                text=f"频道{i+1}消息{j}",
                date=datetime.now()
            )
            mock_client.message_history[channel_id].append(message)
    
    print("✅ 模拟消息已添加")
    
    # 启动轮询检查
    print("\n🔄 启动轮询检查...")
    
    # 运行轮询检查5次
    for round_num in range(5):
        print(f"\n--- 第{round_num+1}轮检查 ---")
        
        # 模拟轮询检查（不等待5秒）
        try:
            # 直接调用轮询逻辑，不等待
            for task_id, task in realtime_engine.active_tasks.items():
                if not task.is_running:
                    continue
                
                for source_channel in task.source_channels:
                    channel_id = source_channel['channel_id']
                    
                    try:
                        # 获取频道最新消息
                        messages = []
                        async for message in mock_client.get_chat_history(
                            chat_id=channel_id, 
                            limit=100
                        ):
                            messages.append(message)
                        
                        if messages:
                            # 按消息ID排序
                            messages.sort(key=lambda x: x.id)
                            
                            # 处理所有消息
                            for message in messages:
                                source_config = {
                                    'channel_id': channel_id,
                                    'channel_name': source_channel.get('channel_name', 'Unknown')
                                }
                                await realtime_engine._handle_new_message(task, message, source_config)
                                
                    except Exception as e:
                        print(f"❌ 检查频道 {channel_id} 失败: {e}")
        except Exception as e:
            print(f"❌ 轮询检查失败: {e}")
        
        # 检查任务状态
        task_status = realtime_engine.get_task_status(task_id)
        if task_status:
            stats = task_status['stats']
            print(f"📊 任务统计:")
            print(f"  - 总处理消息: {stats.get('total_processed', 0)}")
            print(f"  - 成功搬运: {stats.get('successful_transfers', 0)}")
            print(f"  - 失败搬运: {stats.get('failed_transfers', 0)}")
            print(f"  - 过滤消息: {stats.get('filtered_messages', 0)}")
            
            # 显示各频道统计
            source_stats = stats.get('source_channel_stats', {})
            for channel_id, channel_stats in source_stats.items():
                print(f"  - 频道{channel_id}: 处理{channel_stats.get('processed', 0)}条")
        
        # 等待0.5秒
        await asyncio.sleep(0.5)
    
    # 检查最终结果
    print("\n📋 最终检查结果:")
    task_status = realtime_engine.get_task_status(task_id)
    if task_status:
        stats = task_status['stats']
        total_processed = stats.get('total_processed', 0)
        successful_transfers = stats.get('successful_transfers', 0)
        
        print(f"✅ 总处理消息数: {total_processed}")
        print(f"✅ 成功搬运数: {successful_transfers}")
        
        # 检查是否漏消息
        expected_messages = 5 * 10  # 5个频道，每个10条消息
        if total_processed >= expected_messages:
            print(f"✅ 消息处理完整: {total_processed}/{expected_messages}")
        else:
            print(f"❌ 可能漏消息: {total_processed}/{expected_messages}")
        
        # 检查各频道处理情况
        source_stats = stats.get('source_channel_stats', {})
        for i, channel in enumerate(source_channels):
            channel_id = channel['channel_id']
            channel_stats = source_stats.get(channel_id, {})
            processed = channel_stats.get('processed', 0)
            print(f"  - 频道{i+1}({channel_id}): {processed}/10条消息")
    
    # 停止监听系统
    await realtime_engine.stop_monitoring()
    print("\n🛑 监听系统已停止")
    
    return task_status

class MockMessage:
    """模拟消息对象"""
    def __init__(self, id, chat_id, text, date):
        self.id = id
        self.chat = MockChat(chat_id)
        self.text = text
        self.date = date
        self.media_group_id = None

class MockChat:
    """模拟聊天对象"""
    def __init__(self, id):
        self.id = id

async def main():
    """主函数"""
    try:
        result = await test_concurrent_channels()
        print(f"\n🎯 测试完成，结果: {result is not None}")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
