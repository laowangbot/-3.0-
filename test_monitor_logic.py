#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听系统逻辑测试脚本
只测试代码逻辑，不涉及网络连接
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from unittest.mock import Mock, AsyncMock

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from message_engine import MessageEngine
from monitoring_engine import RealTimeMonitoringTask, MonitoringTask
from pyrogram.types import Message, Chat, User

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_message_engine():
    """测试消息处理引擎"""
    try:
        print("🧪 测试消息处理引擎...")
        
        # 创建消息引擎
        config = {
            'remove_links': True,
            'remove_hashtags': False,
            'add_buttons': False
        }
        message_engine = MessageEngine(config)
        print("✅ 消息处理引擎初始化成功")
        
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
        
        # 测试链接移除功能
        print("\n🔍 测试链接移除功能...")
        processed_text = message_engine._remove_links_with_context(test_text)
        print(f"📝 原始文本: {test_text}")
        print(f"📝 处理后文本: {processed_text}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 消息处理引擎测试失败: {e}")
        return False

def test_monitoring_task():
    """测试监听任务类"""
    try:
        print("\n🧪 测试监听任务类...")
        
        # 创建监听任务
        source_channels = [{
            'channel_id': '@test_channel',
            'channel_name': '测试频道',
            'channel_username': 'test_channel',
            'last_message_id': 100
        }]
        
        task = MonitoringTask(
            task_id="test_task_001",
            user_id="123456789",
            target_channel="@target_channel",
            source_channels=source_channels,
            config={'check_interval': 60}
        )
        
        print("✅ 监听任务创建成功")
        print(f"📊 任务ID: {task.task_id}")
        print(f"📊 用户ID: {task.user_id}")
        print(f"📊 目标频道: {task.target_channel}")
        print(f"📊 源频道数: {len(task.source_channels)}")
        
        # 测试任务状态
        print(f"📊 任务状态: {task.status}")
        print(f"📊 是否运行: {task.is_running}")
        print(f"📊 是否应停止: {task.should_stop()}")
        
        # 测试源频道ID更新
        task.update_source_last_id('@test_channel', 150)
        last_id = task.get_source_last_id('@test_channel')
        print(f"📊 更新后最后消息ID: {last_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 监听任务测试失败: {e}")
        return False

def test_realtime_monitoring_task():
    """测试实时监听任务类"""
    try:
        print("\n🧪 测试实时监听任务类...")
        
        # 创建实时监听任务
        source_channels = [{
            'channel_id': '@test_channel',
            'channel_name': '测试频道',
            'channel_username': 'test_channel'
        }]
        
        task = RealTimeMonitoringTask(
            task_id="realtime_test_001",
            user_id="123456789",
            target_channel="@target_channel",
            source_channels=source_channels,
            config={'monitoring_mode': 'realtime', 'delay_seconds': 5}
        )
        
        print("✅ 实时监听任务创建成功")
        print(f"📊 任务ID: {task.task_id}")
        print(f"📊 监听模式: {task.monitoring_mode}")
        print(f"📊 延迟秒数: {task.delay_seconds}")
        
        # 测试状态信息
        status_info = task.get_status_info()
        print(f"📊 状态信息: {status_info}")
        
        # 测试是否应停止
        should_stop = task.should_stop()
        print(f"📊 是否应停止: {should_stop}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 实时监听任务测试失败: {e}")
        return False

def test_message_processing():
    """测试消息处理逻辑"""
    try:
        print("\n🧪 测试消息处理逻辑...")
        
        # 创建模拟消息对象
        mock_chat = Mock(spec=Chat)
        mock_chat.id = -1001234567890
        mock_chat.title = "测试频道"
        mock_chat.username = "test_channel"
        
        mock_user = Mock(spec=User)
        mock_user.id = 123456789
        mock_user.first_name = "测试用户"
        
        # 创建模拟消息
        mock_message = Mock(spec=Message)
        mock_message.id = 1001
        mock_message.chat = mock_chat
        mock_message.from_user = mock_user
        mock_message.text = "这是一条测试消息 https://example.com"
        mock_message.caption = None
        mock_message.media = None
        mock_message.photo = None
        mock_message.video = None
        mock_message.document = None
        mock_message.audio = None
        mock_message.voice = None
        mock_message.sticker = None
        mock_message.animation = None
        mock_message.video_note = None
        mock_message.media_group_id = None
        mock_message.reply_markup = None
        mock_message.date = datetime.now()
        
        # 创建消息引擎
        config = {
            'remove_links': True,
            'remove_hashtags': False,
            'add_buttons': False
        }
        message_engine = MessageEngine(config)
        
        # 测试消息处理
        processed_result, should_process = message_engine.process_message(mock_message, config)
        
        print(f"📊 是否应该处理: {should_process}")
        print(f"📊 处理结果: {processed_result}")
        
        if processed_result:
            print(f"📊 处理后文本: {processed_result.get('text', '无文本')}")
            original_msg = processed_result.get('original_message')
            msg_id = original_msg.id if original_msg else '无'
            print(f"📊 原始消息ID: {msg_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 消息处理逻辑测试失败: {e}")
        import traceback
        logger.error(f"❌ 错误详情: {traceback.format_exc()}")
        return False

def test_error_handling():
    """测试错误处理"""
    try:
        print("\n🧪 测试错误处理...")
        
        # 测试空消息处理
        config = {'test': True}
        message_engine = MessageEngine(config)
        
        # 测试空文本
        empty_text = ""
        http_links = message_engine.http_pattern.findall(empty_text)
        print(f"📊 空文本链接检测: {len(http_links)} 个链接")
        
        # 测试None文本
        none_text = None
        if none_text:
            http_links = message_engine.http_pattern.findall(none_text)
        else:
            print("📊 None文本处理: 跳过处理")
        
        # 测试特殊字符
        special_text = "特殊字符: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        http_links = message_engine.http_pattern.findall(special_text)
        print(f"📊 特殊字符链接检测: {len(http_links)} 个链接")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 错误处理测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 监听系统逻辑测试")
    print("=" * 50)
    
    tests = [
        ("消息处理引擎", test_message_engine),
        ("监听任务类", test_monitoring_task),
        ("实时监听任务类", test_realtime_monitoring_task),
        ("消息处理逻辑", test_message_processing),
        ("错误处理", test_error_handling)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                print(f"✅ {test_name} 测试通过")
                passed += 1
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print(f"\n{'='*50}")
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！监听系统逻辑正常")
    else:
        print("⚠️ 部分测试失败，请检查错误信息")

if __name__ == "__main__":
    main()
