#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试配置脚本 - 检查增强过滤配置
"""

import json
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cloning_engine import CloningEngine
from data_manager import DataManager

def debug_config():
    """调试配置信息"""
    print("=== 调试增强过滤配置 ===")
    
    # 1. 检查用户配置
    try:
        data_manager = DataManager()
        user_config = data_manager.get_user_config(994678447)
        print(f"\n1. 用户配置加载: {'成功' if user_config else '失败'}")
        
        if user_config:
            print(f"   全局增强过滤: {user_config.get('enhanced_filter_enabled', 'N/A')}")
            print(f"   全局增强模式: {user_config.get('enhanced_filter_mode', 'N/A')}")
            
            # 检查频道配置
            channel_pairs = user_config.get('channel_pairs', [])
            print(f"\n   频道对数量: {len(channel_pairs)}")
            
            for i, pair in enumerate(channel_pairs[:3]):  # 只显示前3个
                pair_id = pair.get('pair_id', f'pair_{i}')
                filters = pair.get('channel_filters', {})
                print(f"   频道对 {pair_id}:")
                print(f"     enhanced_filter_enabled: {filters.get('enhanced_filter_enabled', 'N/A')}")
                print(f"     enhanced_filter_mode: {filters.get('enhanced_filter_mode', 'N/A')}")
                print(f"     links_removal: {filters.get('links_removal', 'N/A')}")
    except Exception as e:
        print(f"   用户配置检查失败: {e}")
    
    # 2. 检查CloningEngine配置生成
    try:
        print("\n2. CloningEngine配置测试:")
        engine = CloningEngine()
        
        # 模拟一个频道对配置
        test_pair = {
            'pair_id': 'test_pair',
            'channel_filters': {
                'enhanced_filter_enabled': True,
                'enhanced_filter_mode': 'aggressive',
                'links_removal': False
            }
        }
        
        effective_config = engine.get_effective_config_for_pair(test_pair)
        print(f"   测试配置生成: {'成功' if effective_config else '失败'}")
        
        if effective_config:
            print(f"   enhanced_filter_enabled: {effective_config.get('enhanced_filter_enabled', 'N/A')}")
            print(f"   enhanced_filter_mode: {effective_config.get('enhanced_filter_mode', 'N/A')}")
            print(f"   remove_links: {effective_config.get('remove_links', 'N/A')}")
            
    except Exception as e:
        print(f"   CloningEngine配置测试失败: {e}")
    
    # 3. 检查增强过滤模块
    try:
        print("\n3. 增强过滤模块测试:")
        from enhanced_link_filter import enhanced_link_filter
        
        test_text = "[25.09新增] 解锁百位福利姬 https://t.me/test ✅"
        test_config = {
            'enhanced_filter_enabled': True,
            'enhanced_filter_mode': 'aggressive'
        }
        
        filtered_text = enhanced_link_filter(test_text, test_config)
        print(f"   模块导入: 成功")
        print(f"   测试文本: {test_text}")
        print(f"   过滤结果: {filtered_text}")
        print(f"   过滤效果: {'有效' if filtered_text != test_text else '无效'}")
        
    except Exception as e:
        print(f"   增强过滤模块测试失败: {e}")
    
    print("\n=== 调试完成 ===")

if __name__ == "__main__":
    debug_config()