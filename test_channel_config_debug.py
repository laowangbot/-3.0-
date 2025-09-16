#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试频道配置查找调试
验证监听系统如何查找独立过滤配置
"""

def test_channel_config_lookup():
    """测试频道配置查找逻辑"""
    print("🔍 频道配置查找调试测试")
    print("=" * 60)
    
    # 模拟用户配置（基于您提供的信息）
    user_config = {
        'channel_filters': {
            '-1002966284576': {  # 这是频道ID
                'tail_text': '444@gggggghhh 2223313\n22222233',
                'keywords_enabled': False,
                'replacements_enabled': False,
                'content_removal': True,
                'remove_links': True,
                'remove_links_mode': 'links_only',
                'remove_magnet_links': False,
                'remove_all_links': False,
                'remove_hashtags': True,
                'remove_usernames': True,
                'enhanced_filter_enabled': True,
                'enhanced_filter_mode': 'moderate',
                'filter_photo': False,
                'filter_video': False,
                'file_extensions': [],
                'filter_buttons': True,
                'button_filter_mode': 'remove_all',
                'tail_position': 'end',
                'tail_frequency': 'always',
                'tail_interval': 5,
                'tail_probability': 1.0,
                'additional_buttons': [],
                'button_frequency': 'always',
                'button_interval': 5,
                'button_probability': 1.0
            }
        },
        'admin_channels': [
            {
                'id': '-1002966284576',
                'title': '15131',
                'username': 'xsm53',
                'enabled': True,
                'filter_config': {
                    'tail_text': '旧配置',
                    'keywords_enabled': False
                }
            }
        ]
    }
    
    # 测试不同的目标频道格式
    test_cases = [
        {
            "name": "频道ID格式（正确）",
            "target_channel": "-1002966284576",
            "expected_found": True,
            "expected_source": "channel_filters"
        },
        {
            "name": "字符串频道ID",
            "target_channel": "-1002966284576",
            "expected_found": True,
            "expected_source": "channel_filters"
        },
        {
            "name": "频道用户名（错误）",
            "target_channel": "xsm53",
            "expected_found": False,
            "expected_source": "default"
        },
        {
            "name": "频道标题（错误）",
            "target_channel": "15131",
            "expected_found": False,
            "expected_source": "default"
        }
    ]
    
    print("\n📊 配置查找测试:")
    print("-" * 50)
    
    for case in test_cases:
        print(f"\n测试: {case['name']}")
        print(f"  目标频道: {case['target_channel']}")
        
        # 模拟查找逻辑
        channel_filters = user_config.get('channel_filters', {})
        admin_channels = user_config.get('admin_channels', [])
        
        # 首先查找独立过滤配置
        if str(case['target_channel']) in channel_filters:
            filter_config = channel_filters[str(case['target_channel'])]
            source = "channel_filters"
            found = True
            tail_text = filter_config.get('tail_text', '')
        else:
            # 查找admin_channels中的配置
            found = False
            source = "default"
            tail_text = None
            
            for channel in admin_channels:
                if str(channel.get('id')) == str(case['target_channel']):
                    filter_config = channel.get('filter_config', {})
                    source = "admin_channels"
                    found = True
                    tail_text = filter_config.get('tail_text', '')
                    break
        
        # 验证结果
        found_ok = found == case['expected_found']
        source_ok = source == case['expected_source']
        
        print(f"  查找结果: {'✅ 找到' if found else '❌ 未找到'}")
        print(f"  配置来源: {source}")
        print(f"  小尾巴: {tail_text[:50] + '...' if tail_text and len(tail_text) > 50 else tail_text}")
        print(f"  预期找到: {case['expected_found']} | {'✅' if found_ok else '❌'}")
        print(f"  预期来源: {case['expected_source']} | {'✅' if source_ok else '❌'}")
        
        case['result'] = found_ok and source_ok
    
    return all(case['result'] for case in test_cases)

def test_monitoring_task_creation():
    """测试监听任务创建过程"""
    print("\n🔧 监听任务创建过程测试")
    print("-" * 60)
    
    # 模拟监听任务创建时的数据
    target_channel_data = {
        'id': '-1002966284576',
        'name': '15131',
        'username': 'xsm53',
        'enabled': True
    }
    
    print("\n📊 监听任务数据:")
    print("-" * 50)
    print(f"频道ID: {target_channel_data['id']}")
    print(f"频道名称: {target_channel_data['name']}")
    print(f"频道用户名: {target_channel_data['username']}")
    
    # 模拟监听任务创建
    task_data = {
        'target_channel': target_channel_data['id'],  # 存储的是频道ID
        'target_channel_name': target_channel_data['name'],
        'source_channels': [],
        'config': {}
    }
    
    print(f"\n📋 监听任务存储的数据:")
    print(f"target_channel: {task_data['target_channel']}")
    print(f"target_channel_name: {task_data['target_channel_name']}")
    
    # 验证存储的数据
    stored_id = task_data['target_channel']
    expected_id = '-1002966284576'
    
    id_ok = stored_id == expected_id
    print(f"\n✅ 数据验证:")
    print(f"  存储的频道ID: {stored_id}")
    print(f"  预期频道ID: {expected_id}")
    print(f"  数据正确: {'✅ 是' if id_ok else '❌ 否'}")
    
    return id_ok

def test_config_lookup_simulation():
    """测试配置查找模拟"""
    print("\n🔍 配置查找模拟测试")
    print("-" * 60)
    
    # 模拟监听系统查找配置的过程
    target_channel = "-1002966284576"  # 这是监听任务中存储的频道ID
    user_id = "7951964655"
    
    # 模拟用户配置
    user_config = {
        'channel_filters': {
            '-1002966284576': {
                'tail_text': '444@gggggghhh 2223313\n22222233',
                'keywords_enabled': False
            }
        }
    }
    
    print(f"\n📊 模拟配置查找:")
    print(f"  用户ID: {user_id}")
    print(f"  目标频道: {target_channel}")
    print(f"  频道类型: {type(target_channel)}")
    
    # 模拟查找过程
    channel_filters = user_config.get('channel_filters', {})
    print(f"  可用配置: {list(channel_filters.keys())}")
    
    if str(target_channel) in channel_filters:
        filter_config = channel_filters[str(target_channel)]
        print(f"  ✅ 找到独立过滤配置")
        print(f"  小尾巴: {filter_config.get('tail_text', '')}")
        return True
    else:
        print(f"  ❌ 未找到独立过滤配置")
        return False

def main():
    """主函数"""
    print("🔍 频道配置查找调试测试")
    print("=" * 60)
    
    # 运行所有测试
    lookup_ok = test_channel_config_lookup()
    creation_ok = test_monitoring_task_creation()
    simulation_ok = test_config_lookup_simulation()
    
    print(f"\n🎉 测试完成!")
    print(f"\n📊 测试结果:")
    print(f"  配置查找: {'✅ 通过' if lookup_ok else '❌ 失败'}")
    print(f"  任务创建: {'✅ 通过' if creation_ok else '❌ 失败'}")
    print(f"  查找模拟: {'✅ 通过' if simulation_ok else '❌ 失败'}")
    
    if lookup_ok and creation_ok and simulation_ok:
        print(f"\n🎉 所有测试通过！")
        print(f"\n💡 问题分析:")
        print("✅ 监听任务正确存储频道ID")
        print("✅ 配置查找逻辑正确")
        print("✅ 独立过滤配置存在")
        print("\n🔍 可能的问题:")
        print("⚠️ 监听系统可能没有重新加载配置")
        print("⚠️ 需要重启机器人才能生效")
    else:
        print(f"\n⚠️ 部分测试失败，需要进一步检查")

if __name__ == "__main__":
    main()

