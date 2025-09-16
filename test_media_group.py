#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
媒体组处理诊断脚本
测试媒体组消息是否能正常搬运
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from unittest.mock import Mock

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from message_engine import MessageEngine
from monitoring_engine import RealTimeMonitoringEngine
from pyrogram.types import Message, Chat, User, Photo, Video, Document

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_media_group_messages():
    """创建模拟的媒体组消息"""
    mock_chat = Mock(spec=Chat)
    mock_chat.id = -1001234567890
    mock_chat.title = "测试频道"
    mock_chat.username = "test_channel"
    
    mock_user = Mock(spec=User)
    mock_user.id = 123456789
    mock_user.first_name = "测试用户"
    
    # 创建媒体组消息
    messages = []
    media_group_id = "1234567890"
    
    # 消息1：照片
    msg1 = Mock(spec=Message)
    msg1.id = 1001
    msg1.chat = mock_chat
    msg1.from_user = mock_user
    msg1.text = None
    msg1.caption = "这是第一张照片的说明"
    msg1.media = True
    msg1.media_group_id = media_group_id
    msg1.photo = Mock(spec=Photo)
    msg1.photo.file_id = "photo_file_id_1"
    msg1.video = None
    msg1.document = None
    msg1.audio = None
    msg1.voice = None
    msg1.sticker = None
    msg1.animation = None
    msg1.video_note = None
    msg1.contact = None
    msg1.location = None
    msg1.venue = None
    msg1.poll = None
    msg1.dice = None
    msg1.game = None
    msg1.web_page = None
    msg1.forward_from = None
    msg1.forward_from_chat = None
    msg1.reply_to_message = None
    msg1.views = None
    msg1.edit_date = None
    msg1.author_signature = None
    msg1.entities = None
    msg1.caption_entities = None
    msg1.reply_markup = None
    msg1.via_bot = None
    msg1.sender_chat = None
    msg1.message_thread_id = None
    msg1.effective_attachment = None
    msg1.service = None
    msg1.empty = False
    msg1.date = datetime.now()
    messages.append(msg1)
    
    # 消息2：视频
    msg2 = Mock(spec=Message)
    msg2.id = 1002
    msg2.chat = mock_chat
    msg2.from_user = mock_user
    msg2.text = None
    msg2.caption = None
    msg2.media = True
    msg2.media_group_id = media_group_id
    msg2.photo = None
    msg2.video = Mock(spec=Video)
    msg2.video.file_id = "video_file_id_1"
    msg2.document = None
    msg2.audio = None
    msg2.voice = None
    msg2.sticker = None
    msg2.animation = None
    msg2.video_note = None
    msg2.contact = None
    msg2.location = None
    msg2.venue = None
    msg2.poll = None
    msg2.dice = None
    msg2.game = None
    msg2.web_page = None
    msg2.forward_from = None
    msg2.forward_from_chat = None
    msg2.reply_to_message = None
    msg2.views = None
    msg2.edit_date = None
    msg2.author_signature = None
    msg2.entities = None
    msg2.caption_entities = None
    msg2.reply_markup = None
    msg2.via_bot = None
    msg2.sender_chat = None
    msg2.message_thread_id = None
    msg2.effective_attachment = None
    msg2.service = None
    msg2.empty = False
    msg2.date = datetime.now()
    messages.append(msg2)
    
    # 消息3：文档
    msg3 = Mock(spec=Message)
    msg3.id = 1003
    msg3.chat = mock_chat
    msg3.from_user = mock_user
    msg3.text = None
    msg3.caption = None
    msg3.media = True
    msg3.media_group_id = media_group_id
    msg3.photo = None
    msg3.video = None
    msg3.document = Mock(spec=Document)
    msg3.document.file_id = "document_file_id_1"
    msg3.audio = None
    msg3.voice = None
    msg3.sticker = None
    msg3.animation = None
    msg3.video_note = None
    msg3.contact = None
    msg3.location = None
    msg3.venue = None
    msg3.poll = None
    msg3.dice = None
    msg3.game = None
    msg3.web_page = None
    msg3.forward_from = None
    msg3.forward_from_chat = None
    msg3.reply_to_message = None
    msg3.views = None
    msg3.edit_date = None
    msg3.author_signature = None
    msg3.entities = None
    msg3.caption_entities = None
    msg3.reply_markup = None
    msg3.via_bot = None
    msg3.sender_chat = None
    msg3.message_thread_id = None
    msg3.effective_attachment = None
    msg3.service = None
    msg3.empty = False
    msg3.date = datetime.now()
    messages.append(msg3)
    
    return messages, media_group_id

def test_media_group_processing():
    """测试媒体组消息处理"""
    print("🧪 测试媒体组消息处理")
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
    
    # 创建媒体组消息
    messages, media_group_id = create_media_group_messages()
    
    print(f"📝 创建了 {len(messages)} 条媒体组消息，媒体组ID: {media_group_id}")
    
    # 测试每条消息的处理
    processed_messages = []
    for i, message in enumerate(messages, 1):
        print(f"\n🔍 处理媒体组消息 {i}:")
        print(f"  消息ID: {message.id}")
        print(f"  媒体类型: {'照片' if message.photo else '视频' if message.video else '文档' if message.document else '未知'}")
        print(f"  说明文字: {message.caption or '无'}")
        
        # 处理消息
        processed_result, should_process = message_engine.process_message(message, config)
        
        print(f"  处理结果: should_process={should_process}")
        print(f"  处理后文本: '{processed_result.get('text', '')}'")
        print(f"  媒体信息: photo={bool(processed_result.get('photo'))}, video={bool(processed_result.get('video'))}, document={bool(processed_result.get('document'))}")
        
        if should_process and processed_result:
            processed_messages.append(processed_result)
            print("  ✅ 消息处理成功")
        else:
            print("  ❌ 消息被过滤")
    
    print(f"\n📊 媒体组处理结果:")
    print(f"  总消息数: {len(messages)}")
    print(f"  成功处理: {len(processed_messages)}")
    print(f"  被过滤: {len(messages) - len(processed_messages)}")
    
    if processed_messages:
        print(f"\n📤 媒体组发送数据:")
        media_group_data = {
            'media_group_messages': processed_messages
        }
        
        # 模拟构建媒体列表
        media_list = []
        caption = ""
        buttons = None
        
        # 收集caption和buttons
        for msg_data in processed_messages:
            if not caption and msg_data.get('text'):
                caption = msg_data['text']
            if not buttons and msg_data.get('buttons'):
                buttons = msg_data['buttons']
        
        # 构建媒体列表
        for i, msg_data in enumerate(processed_messages):
            media_caption = caption if i == 0 else None
            
            if msg_data.get('photo'):
                media_list.append(f"InputMediaPhoto(file_id={msg_data['photo'].file_id}, caption='{media_caption}')")
            elif msg_data.get('video'):
                media_list.append(f"InputMediaVideo(file_id={msg_data['video'].file_id}, caption='{media_caption}')")
            elif msg_data.get('document'):
                media_list.append(f"InputMediaDocument(file_id={msg_data['document'].file_id}, caption='{media_caption}')")
        
        print(f"  媒体列表 ({len(media_list)} 个):")
        for i, media in enumerate(media_list, 1):
            print(f"    {i}. {media}")
        
        print(f"  说明文字: '{caption}'")
        print(f"  按钮: {bool(buttons)}")
        
        print("\n✅ 媒体组数据构建成功，可以发送")
    else:
        print("\n❌ 没有可发送的媒体组消息")

def test_media_group_edge_cases():
    """测试媒体组边界情况"""
    print("\n🧪 测试媒体组边界情况")
    print("=" * 50)
    
    # 测试空媒体组
    print("1. 空媒体组测试:")
    empty_data = {'media_group_messages': []}
    if not empty_data.get('media_group_messages'):
        print("  ❌ 空媒体组被正确检测")
    else:
        print("  ✅ 空媒体组检测失败")
    
    # 测试只有文本的媒体组
    print("\n2. 只有文本的媒体组测试:")
    text_only_data = {
        'media_group_messages': [
            {'text': '只有文本，没有媒体', 'buttons': None}
        ]
    }
    
    media_list = []
    for msg_data in text_only_data['media_group_messages']:
        if msg_data.get('photo'):
            media_list.append("photo")
        elif msg_data.get('video'):
            media_list.append("video")
        elif msg_data.get('document'):
            media_list.append("document")
    
    if not media_list:
        print("  ❌ 只有文本的媒体组没有有效媒体")
    else:
        print("  ✅ 只有文本的媒体组有有效媒体")
    
    # 测试混合媒体组
    print("\n3. 混合媒体组测试:")
    mixed_data = {
        'media_group_messages': [
            {'text': '说明文字', 'photo': Mock(file_id='photo_1')},
            {'text': '', 'video': Mock(file_id='video_1')},
            {'text': '', 'document': Mock(file_id='doc_1')}
        ]
    }
    
    media_list = []
    caption = ""
    for msg_data in mixed_data['media_group_messages']:
        if not caption and msg_data.get('text'):
            caption = msg_data['text']
        if msg_data.get('photo'):
            media_list.append("photo")
        elif msg_data.get('video'):
            media_list.append("video")
        elif msg_data.get('document'):
            media_list.append("document")
    
    print(f"  媒体数量: {len(media_list)}")
    print(f"  说明文字: '{caption}'")
    print(f"  媒体类型: {media_list}")

def main():
    """主函数"""
    print("🔍 媒体组处理诊断工具")
    print("=" * 50)
    print("此工具将帮助诊断媒体组消息处理问题")
    print()
    
    # 测试媒体组处理
    test_media_group_processing()
    
    # 测试边界情况
    test_media_group_edge_cases()
    
    print("\n🎯 诊断建议:")
    print("1. 检查媒体组消息是否正确识别")
    print("2. 检查媒体组消息处理是否成功")
    print("3. 检查媒体组数据构建是否正确")
    print("4. 检查媒体组发送是否成功")
    print("5. 查看机器人日志中的媒体组处理信息")

if __name__ == "__main__":
    main()

