#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试消息处理流程 - 模拟实际的消息处理
"""

import json
import sys
import os
import asyncio
from unittest.mock import Mock

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from message_engine import MessageEngine
from cloning_engine import CloningEngine
from local_data_manager import LocalDataManager
from config import DEFAULT_USER_CONFIG

async def test_message_processing():
    """测试消息处理流程"""
    print("=== 测试消息处理流程 ===")
    
    try:
        # 1. 初始化数据管理器
        data_manager = LocalDataManager("default_bot")
        
        # 2. 获取用户配置
        user_config = await data_manager.get_user_config(994678447)
        print(f"\n1. 用户配置加载: {'成功' if user_config else '失败'}")
        
        if not user_config:
            print("   无法获取用户配置，退出测试")
            return
        
        # 3. 创建模拟的Telegram客户端和配置
        mock_client = Mock()
        config = DEFAULT_USER_CONFIG.copy()
        
        # 4. 初始化CloningEngine
        cloning_engine = CloningEngine(mock_client, config)
        
        # 5. 获取频道过滤配置
        channel_filters = user_config.get('channel_filters', {})
        if not channel_filters:
            print("   没有找到频道过滤配置")
            return
        
        # 使用第一个频道过滤配置
        pair_id = list(channel_filters.keys())[0]
        pair_config = channel_filters[pair_id]
        print(f"\n2. 测试频道对: {pair_id}")
        print(f"   频道配置: {pair_config}")
        
        # 6. 获取有效配置
        effective_config = await cloning_engine.get_effective_config_for_pair(994678447, pair_id)
        print(f"\n3. 有效配置生成: {'成功' if effective_config else '失败'}")
        
        if effective_config:
            print(f"   enhanced_filter_enabled: {effective_config.get('enhanced_filter_enabled', 'N/A')}")
            print(f"   enhanced_filter_mode: {effective_config.get('enhanced_filter_mode', 'N/A')}")
            print(f"   remove_links: {effective_config.get('remove_links', 'N/A')}")
            print(f"   filter_keywords: {effective_config.get('filter_keywords', 'N/A')}")
            print(f"   _debug_enhanced_filter_enabled: {effective_config.get('_debug_enhanced_filter_enabled', 'N/A')}")
            print(f"   _debug_links_removal: {effective_config.get('_debug_links_removal', 'N/A')}")
        
        # 7. 初始化MessageEngine
        message_engine = MessageEngine(config)
        
        # 8. 创建模拟消息
        mock_message = Mock()
        mock_message.text = "[25.09新增] 解锁百位福利姬 https://t.me/test ✅ #福利姬 #新增"
        mock_message.caption = None
        mock_message.media = None
        mock_message.id = 12345
        
        print(f"\n4. 测试消息: {mock_message.text}")
        
        # 9. 处理消息
        print("\n5. 开始处理消息...")
        processed_result, should_skip = message_engine.process_message(mock_message, effective_config)
        
        print(f"\n6. 处理结果:")
        print(f"   should_skip: {should_skip}")
        print(f"   processed_result: {processed_result}")
        
        if 'text' in processed_result:
            print(f"   原始文本: {mock_message.text}")
            print(f"   处理后文本: {processed_result['text']}")
            print(f"   过滤效果: {'有效' if processed_result['text'] != mock_message.text else '无效'}")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    asyncio.run(test_message_processing())