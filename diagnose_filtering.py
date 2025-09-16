#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听过滤诊断脚本
诊断为什么消息被过滤而没有搬运
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from message_engine import MessageEngine
from pyrogram.types import Message, Chat, User
from unittest.mock import Mock

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_message(text="测试消息", has_media=False, media_type="photo"):
    """创建测试消息"""
    mock_chat = Mock(spec=Chat)
    mock_chat.id = -1001234567890
    mock_chat.title = "测试频道"
    mock_chat.username = "test_channel"
    
    mock_user = Mock(spec=User)
    mock_user.id = 123456789
    mock_user.first_name = "测试用户"
    
    mock_message = Mock(spec=Message)
    mock_message.id = 1001
    mock_message.chat = mock_chat
    mock_message.from_user = mock_user
    mock_message.text = text if not has_media else None
    mock_message.caption = text if has_media else None
    mock_message.media = has_media
    mock_message.reply_markup = None
    mock_message.media_group_id = None
    mock_message.date = datetime.now()
    
    # 设置媒体类型
    if has_media:
        if media_type == "photo":
            mock_message.photo = Mock()
            mock_message.video = None
            mock_message.document = None
        elif media_type == "video":
            mock_message.photo = None
            mock_message.video = Mock()
            mock_message.document = None
        elif media_type == "document":
            mock_message.photo = None
            mock_message.video = None
            mock_message.document = Mock()
    else:
        mock_message.photo = None
        mock_message.video = None
        mock_message.document = None
    
    # 设置所有可能的媒体属性
    mock_message.audio = None
    mock_message.voice = None
    mock_message.sticker = None
    mock_message.animation = None
    mock_message.video_note = None
    mock_message.contact = None
    mock_message.location = None
    mock_message.venue = None
    mock_message.poll = None
    mock_message.dice = None
    mock_message.game = None
    mock_message.web_page = None
    mock_message.forward_from = None
    mock_message.forward_from_chat = None
    mock_message.reply_to_message = None
    mock_message.views = None
    mock_message.edit_date = None
    mock_message.author_signature = None
    mock_message.entities = None
    mock_message.caption_entities = None
    mock_message.via_bot = None
    mock_message.sender_chat = None
    mock_message.message_thread_id = None
    mock_message.effective_attachment = None
    mock_message.service = None
    mock_message.empty = False
    
    return mock_message

def test_message_filtering():
    """测试消息过滤逻辑"""
    print("🔍 诊断消息过滤问题")
    print("=" * 50)
    
    # 创建消息引擎
    config = {
        'remove_links': True,
        'remove_hashtags': False,
        'add_buttons': False,
        'filter_keywords': [],
        'content_removal': False
    }
    message_engine = MessageEngine(config)
    
    # 测试用例
    test_cases = [
        {
            'name': '普通文本消息',
            'message': create_test_message("这是一条普通文本消息"),
            'config': config
        },
        {
            'name': '包含链接的文本消息',
            'message': create_test_message("这是一条包含链接的消息: https://example.com"),
            'config': config
        },
        {
            'name': '包含磁力链接的消息',
            'message': create_test_message("磁力链接: magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678"),
            'config': config
        },
        {
            'name': '包含Hashtag的消息',
            'message': create_test_message("这是 #测试 标签消息"),
            'config': config
        },
        {
            'name': '纯媒体消息（照片）',
            'message': create_test_message("这是照片说明", has_media=True, media_type="photo"),
            'config': config
        },
        {
            'name': '纯媒体消息（视频）',
            'message': create_test_message("这是视频说明", has_media=True, media_type="video"),
            'config': config
        },
        {
            'name': '空消息',
            'message': create_test_message(""),
            'config': config
        },
        {
            'name': '只有空格的消息',
            'message': create_test_message("   "),
            'config': config
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 测试用例 {i}: {test_case['name']}")
        print("-" * 30)
        
        message = test_case['message']
        config = test_case['config']
        
        # 测试should_process_message
        print(f"📝 消息内容: text='{message.text}', caption='{message.caption}', media={message.media}")
        
        should_process = message_engine.should_process_message(message, config)
        print(f"🔍 should_process_message 结果: {should_process}")
        
        if not should_process:
            print("❌ 消息被should_process_message过滤")
            continue
        
        # 测试process_message
        processed_result, should_process_final = message_engine.process_message(message, config)
        print(f"🔍 process_message 结果: should_process={should_process_final}")
        print(f"🔍 处理结果: {processed_result}")
        
        if not should_process_final or not processed_result:
            print("❌ 消息被process_message过滤")
            if processed_result:
                print(f"   原因: should_process={should_process_final}, processed_result={bool(processed_result)}")
            else:
                print("   原因: processed_result为空")
        else:
            print("✅ 消息通过所有过滤检查")
            if processed_result.get('text'):
                print(f"   处理后文本: {processed_result['text']}")
            if processed_result.get('text_modified'):
                print("   文本被修改")
            if processed_result.get('buttons_modified'):
                print("   按钮被修改")

def test_different_configs():
    """测试不同配置下的过滤行为"""
    print("\n🔍 测试不同配置下的过滤行为")
    print("=" * 50)
    
    # 不同配置
    configs = [
        {
            'name': '默认配置',
            'config': {
                'remove_links': True,
                'remove_hashtags': False,
                'add_buttons': False
            }
        },
        {
            'name': '移除所有链接',
            'config': {
                'remove_links': True,
                'remove_hashtags': True,
                'add_buttons': False
            }
        },
        {
            'name': '内容移除模式',
            'config': {
                'content_removal': True,
                'content_removal_mode': 'text_only',
                'remove_links': True
            }
        },
        {
            'name': '关键字过滤',
            'config': {
                'filter_keywords': ['广告', '推广'],
                'remove_links': True
            }
        }
    ]
    
    test_message = create_test_message("这是一条包含链接的测试消息: https://example.com 和 #标签")
    
    for config_info in configs:
        print(f"\n🧪 配置: {config_info['name']}")
        print("-" * 30)
        
        message_engine = MessageEngine(config_info['config'])
        
        # 测试should_process_message
        should_process = message_engine.should_process_message(test_message, config_info['config'])
        print(f"🔍 should_process_message: {should_process}")
        
        if should_process:
            # 测试process_message
            processed_result, should_process_final = message_engine.process_message(test_message, config_info['config'])
            print(f"🔍 process_message: should_process={should_process_final}")
            print(f"🔍 处理后文本: '{processed_result.get('text', '')}'")
            print(f"🔍 文本被修改: {processed_result.get('text_modified', False)}")

def main():
    """主函数"""
    print("🔍 监听过滤诊断工具")
    print("=" * 50)
    print("此工具将帮助诊断为什么消息被过滤而没有搬运")
    print()
    
    # 测试消息过滤
    test_message_filtering()
    
    # 测试不同配置
    test_different_configs()
    
    print("\n🎯 诊断建议:")
    print("1. 检查should_process_message是否返回False")
    print("2. 检查process_message是否返回空结果")
    print("3. 检查过滤配置是否过于严格")
    print("4. 检查消息内容是否符合过滤条件")
    print("5. 查看机器人日志中的详细过滤信息")

if __name__ == "__main__":
    main()
