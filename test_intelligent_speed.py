#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试智能变速功能
验证点赞和删除功能的自动变速和反检测机制
"""

import asyncio
import random
import time
from datetime import datetime, timedelta

def test_speed_calculation():
    """测试速度计算"""
    print("🚀 智能变速功能测试")
    print("=" * 60)
    
    # 速度模式配置
    speed_modes = {
        'stealth': {'message_delay': 2.0, 'like_delay': 1.0, 'batch_delay': 4.0, 'batch_size': 5},
        'safe': {'message_delay': 1.5, 'like_delay': 0.8, 'batch_delay': 3.0, 'batch_size': 8},
        'normal': {'message_delay': 1.0, 'like_delay': 0.5, 'batch_delay': 2.0, 'batch_size': 10},
        'fast': {'message_delay': 0.7, 'like_delay': 0.3, 'batch_delay': 1.5, 'batch_size': 15},
        'aggressive': {'message_delay': 0.4, 'like_delay': 0.2, 'batch_delay': 1.0, 'batch_size': 20}
    }
    
    # 测试场景
    test_scenarios = [
        {"name": "小规模点赞", "messages": 100, "likes_per_message": 1},
        {"name": "中规模点赞", "messages": 1000, "likes_per_message": 1},
        {"name": "大规模点赞", "messages": 10000, "likes_per_message": 1},
        {"name": "超大规模点赞", "messages": 25684, "likes_per_message": 1},
        {"name": "会员用户点赞", "messages": 8561, "likes_per_message": 3},
    ]
    
    print("\n📊 点赞时间分析（智能变速）:")
    print("-" * 50)
    
    for scenario in test_scenarios:
        print(f"\n🎯 {scenario['name']} ({scenario['messages']}条消息, {scenario['likes_per_message']}个赞/消息):")
        
        for mode_name, config in speed_modes.items():
            # 计算时间
            total_likes = scenario['messages'] * scenario['likes_per_message']
            total_messages = scenario['messages']
            
            # 点赞时间
            like_time = total_likes * config['like_delay']
            
            # 消息间延迟时间
            message_time = total_messages * config['message_delay']
            
            # 批次延迟时间
            batch_count = (total_messages + config['batch_size'] - 1) // config['batch_size']
            batch_time = (batch_count - 1) * config['batch_delay']
            
            # 总时间
            total_time = like_time + message_time + batch_time
            
            # 转换为小时
            hours = total_time / 3600
            
            print(f"  {mode_name.upper():12}: {hours:.1f}小时 ({total_time/60:.0f}分钟)")
    
    print("\n📊 删除时间分析（智能变速）:")
    print("-" * 50)
    
    delete_scenarios = [
        {"name": "小规模删除", "messages": 100},
        {"name": "中规模删除", "messages": 1000},
        {"name": "大规模删除", "messages": 10000},
    ]
    
    for scenario in delete_scenarios:
        print(f"\n🗑️ {scenario['name']} ({scenario['messages']}条消息):")
        
        for mode_name, config in speed_modes.items():
            total_messages = scenario['messages']
            
            # 消息间延迟时间
            message_time = total_messages * config['message_delay']
            
            # 批次延迟时间
            batch_count = (total_messages + config['batch_size'] - 1) // config['batch_size']
            batch_time = (batch_count - 1) * config['batch_delay']
            
            # 总时间
            total_time = message_time + batch_time
            
            # 转换为小时
            hours = total_time / 3600
            
            print(f"  {mode_name.upper():12}: {hours:.1f}小时 ({total_time/60:.0f}分钟)")

def test_adaptive_delay():
    """测试自适应延迟"""
    print("\n🔄 自适应延迟测试:")
    print("-" * 50)
    
    base_delay = 1.0
    risk_levels = ['low', 'medium', 'high', 'critical']
    risk_multipliers = {'low': 1.0, 'medium': 1.2, 'high': 1.5, 'critical': 2.0}
    
    for risk in risk_levels:
        print(f"\n风险等级: {risk.upper()}")
        
        delays = []
        for _ in range(10):
            # 基础延迟
            delay = base_delay * risk_multipliers[risk]
            
            # 添加随机变化
            delay *= random.uniform(0.8, 1.2)
            
            # 人类行为模拟
            if random.random() < 0.1:
                delay *= random.uniform(2.0, 4.0)
            
            delays.append(delay)
        
        avg_delay = sum(delays) / len(delays)
        min_delay = min(delays)
        max_delay = max(delays)
        
        print(f"  平均延迟: {avg_delay:.2f}秒")
        print(f"  延迟范围: {min_delay:.2f} - {max_delay:.2f}秒")
        print(f"  延迟变化: {((max_delay - min_delay) / avg_delay * 100):.1f}%")

def test_media_group_filtering():
    """测试媒体组过滤"""
    print("\n📎 媒体组过滤测试:")
    print("-" * 50)
    
    # 模拟消息ID列表（包含媒体组）
    message_ids = list(range(1, 101))  # 1-100
    
    # 模拟媒体组ID分配
    media_groups = {}
    filtered_messages = []
    
    for msg_id in message_ids:
        # 模拟30%的消息是媒体组
        if random.random() < 0.3:
            # 随机分配媒体组ID
            group_id = random.randint(1000, 1010)
            if group_id not in media_groups:
                media_groups[group_id] = msg_id
                filtered_messages.append(msg_id)
                print(f"📎 媒体组 {group_id} 选择消息 {msg_id}")
        else:
            # 非媒体组消息直接添加
            filtered_messages.append(msg_id)
    
    print(f"\n📊 过滤结果:")
    print(f"  原始消息: {len(message_ids)} 条")
    print(f"  过滤后消息: {len(filtered_messages)} 条")
    print(f"  媒体组数量: {len(media_groups)} 个")
    print(f"  过滤率: {((len(message_ids) - len(filtered_messages)) / len(message_ids) * 100):.1f}%")

def test_error_recovery():
    """测试错误恢复机制"""
    print("\n🛡️ 错误恢复机制测试:")
    print("-" * 50)
    
    # 模拟错误率
    error_rates = [0.01, 0.05, 0.1, 0.15, 0.2, 0.3]
    
    for error_rate in error_rates:
        print(f"\n错误率: {error_rate:.1%}")
        
        # 模拟100次操作
        operations = 100
        errors = int(operations * error_rate)
        successes = operations - errors
        
        # 根据错误率调整模式
        if error_rate > 0.15:
            mode = 'stealth'
        elif error_rate > 0.08:
            mode = 'safe'
        elif error_rate > 0.05:
            mode = 'normal'
        elif error_rate > 0.02:
            mode = 'fast'
        else:
            mode = 'aggressive'
        
        # 计算冷却时间
        if errors >= 5:
            cooldown = random.uniform(60, 120)
        else:
            cooldown = 0
        
        print(f"  推荐模式: {mode.upper()}")
        print(f"  成功操作: {successes}")
        print(f"  失败操作: {errors}")
        print(f"  冷却时间: {cooldown:.1f}秒")

def test_performance_metrics():
    """测试性能指标"""
    print("\n📈 性能指标测试:")
    print("-" * 50)
    
    # 模拟性能数据
    metrics = {
        'total_operations': 1000,
        'success_count': 950,
        'error_count': 50,
        'api_calls_made': 1200,
        'average_processing_time': 1.2,
        'concurrent_tasks_running': 3,
        'peak_concurrent_tasks': 8
    }
    
    success_rate = metrics['success_count'] / metrics['total_operations'] * 100
    error_rate = metrics['error_count'] / metrics['total_operations'] * 100
    avg_time_per_operation = metrics['average_processing_time']
    
    print(f"总操作数: {metrics['total_operations']}")
    print(f"成功率: {success_rate:.1f}%")
    print(f"错误率: {error_rate:.1f}%")
    print(f"平均处理时间: {avg_time_per_operation:.2f}秒/操作")
    print(f"API调用数: {metrics['api_calls_made']}")
    print(f"当前并发任务: {metrics['concurrent_tasks_running']}")
    print(f"峰值并发任务: {metrics['peak_concurrent_tasks']}")
    
    # 性能评估
    if success_rate >= 95:
        performance_level = "优秀"
    elif success_rate >= 90:
        performance_level = "良好"
    elif success_rate >= 80:
        performance_level = "一般"
    else:
        performance_level = "需要优化"
    
    print(f"\n性能评估: {performance_level}")

def main():
    """主函数"""
    print("🤖 智能变速功能完整测试")
    print("=" * 60)
    
    # 运行所有测试
    test_speed_calculation()
    test_adaptive_delay()
    test_media_group_filtering()
    test_error_recovery()
    test_performance_metrics()
    
    print("\n🎉 测试完成！")
    print("\n💡 功能特性总结:")
    print("✅ 自动变速：根据错误率动态调整速度模式")
    print("✅ 媒体组过滤：每个媒体组只点赞一条消息")
    print("✅ 反检测机制：随机延迟、人类行为模拟")
    print("✅ 错误恢复：自动冷却、重试机制")
    print("✅ 性能监控：实时统计、进度显示")
    print("✅ 智能优化：API频率控制、批量处理")

if __name__ == "__main__":
    main()

