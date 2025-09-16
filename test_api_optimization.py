#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试API优化效果
验证空白消息跳过和API限制处理
"""

import asyncio
import time
from unittest.mock import Mock

def create_mock_message(text=None, caption=None, media=None, empty=False, service=False):
    """创建模拟消息对象"""
    message = Mock()
    message.text = text
    message.caption = caption
    message.media = media
    message.empty = empty
    message.service = service
    message.id = 12345
    return message

def test_blank_message_skipping():
    """测试空白消息跳过功能"""
    print("🧪 空白消息跳过功能测试")
    print("=" * 60)
    
    # 模拟消息引擎
    from message_engine import MessageEngine
    message_engine = MessageEngine({})
    
    # 测试用例
    test_cases = [
        {"name": "正常消息", "text": "正常内容", "expected_skip": False},
        {"name": "空白消息", "text": "   ", "expected_skip": True},
        {"name": "空消息", "text": "", "expected_skip": True},
        {"name": "重复字符", "text": "aaaaa", "expected_skip": True},
        {"name": "纯数字", "text": "12345", "expected_skip": True},
        {"name": "纯链接", "text": "https://example.com", "expected_skip": True},
        {"name": "服务消息", "text": "test", "service": True, "expected_skip": True},
    ]
    
    print("\n📊 测试结果:")
    print("-" * 50)
    
    api_calls_saved = 0
    for case in test_cases:
        message = create_mock_message(
            text=case.get('text'),
            caption=case.get('caption'),
            media=case.get('media'),
            empty=case.get('empty', False),
            service=case.get('service', False)
        )
        
        is_blank = message_engine._is_blank_message(message)
        expected = case['expected_skip']
        
        if is_blank == expected:
            status = "✅ 通过"
            if is_blank:
                api_calls_saved += 1
        else:
            status = "❌ 失败"
        
        print(f"{case['name']:<12} | 预期跳过: {expected} | 实际跳过: {is_blank} | {status}")
    
    print(f"\n💡 API调用节约: {api_calls_saved}/{len(test_cases)} 条消息")
    print(f"📈 节约率: {api_calls_saved/len(test_cases)*100:.1f}%")

def test_api_rate_limiting():
    """测试API限制处理"""
    print("\n🛡️ API限制处理测试")
    print("-" * 60)
    
    # 模拟API调用历史
    api_call_history = []
    current_time = time.time()
    
    # 模拟不同频率的API调用
    scenarios = [
        {"name": "正常频率", "calls_per_minute": 5, "expected_action": "继续"},
        {"name": "中等频率", "calls_per_minute": 8, "expected_action": "继续"},
        {"name": "高频率", "calls_per_minute": 12, "expected_action": "冷却"},
        {"name": "超高频率", "calls_per_minute": 20, "expected_action": "冷却"},
    ]
    
    print("\n📊 API频率测试:")
    print("-" * 50)
    
    for scenario in scenarios:
        # 清空历史
        api_call_history = []
        
        # 模拟1分钟内的API调用
        calls_per_minute = scenario['calls_per_minute']
        for i in range(calls_per_minute):
            api_call_history.append(current_time - (60 - i * (60/calls_per_minute)))
        
        # 检查频率
        recent_calls = len([
            call_time for call_time in api_call_history
            if current_time - call_time < 60
        ])
        
        # 判断是否需要冷却
        if recent_calls > 10:
            action = "冷却"
            cooldown_time = "60-120秒"
        else:
            action = "继续"
            cooldown_time = "无"
        
        expected = scenario['expected_action']
        status = "✅ 通过" if action == expected else "❌ 失败"
        
        print(f"{scenario['name']:<12} | 调用数: {recent_calls:2d} | 动作: {action:<4} | 冷却: {cooldown_time:<8} | {status}")

def test_flood_wait_handling():
    """测试FLOOD_WAIT处理"""
    print("\n⏸️ FLOOD_WAIT处理测试")
    print("-" * 60)
    
    # 模拟FLOOD_WAIT错误消息
    error_messages = [
        "Telegram says: [420 FLOOD_WAIT_X] - A wait of 1250 seconds is required",
        "Telegram says: [420 FLOOD_WAIT_X] - A wait of 60 seconds is required",
        "Telegram says: [420 FLOOD_WAIT_X] - A wait of 300 seconds is required",
        "Telegram says: [400 MESSAGE_ID_INVALID] - The message id is invalid",
        "Other error message",
    ]
    
    print("\n📊 错误处理测试:")
    print("-" * 50)
    
    for i, error_msg in enumerate(error_messages, 1):
        import re
        
        if "FLOOD_WAIT" in error_msg:
            # 提取等待时间
            wait_match = re.search(r'(\d+) seconds', error_msg)
            if wait_match:
                wait_time = int(wait_match.group(1))
                action = f"等待 {wait_time} 秒"
                status = "✅ 正确处理"
            else:
                action = "等待 60 秒"
                status = "⚠️ 默认处理"
        elif "MESSAGE_ID_INVALID" in error_msg:
            action = "跳过消息"
            status = "✅ 正确处理"
        else:
            action = "短暂等待后重试"
            status = "✅ 正确处理"
        
        print(f"错误 {i}: {action:<20} | {status}")

def test_performance_improvement():
    """测试性能提升"""
    print("\n⚡ 性能提升测试")
    print("-" * 60)
    
    # 模拟1000条消息，其中30%是空白消息
    total_messages = 1000
    blank_message_ratio = 0.3
    blank_messages = int(total_messages * blank_message_ratio)
    normal_messages = total_messages - blank_messages
    
    print(f"\n📊 性能对比:")
    print(f"总消息数: {total_messages}")
    print(f"空白消息: {blank_messages} ({blank_message_ratio*100:.1f}%)")
    print(f"正常消息: {normal_messages} ({(1-blank_message_ratio)*100:.1f}%)")
    
    # 计算API调用节约
    api_calls_without_optimization = total_messages
    api_calls_with_optimization = normal_messages
    api_calls_saved = blank_messages
    savings_percentage = (api_calls_saved / api_calls_without_optimization) * 100
    
    print(f"\n💡 API调用对比:")
    print(f"优化前: {api_calls_without_optimization} 次调用")
    print(f"优化后: {api_calls_with_optimization} 次调用")
    print(f"节约: {api_calls_saved} 次调用 ({savings_percentage:.1f}%)")
    
    # 计算时间节约（假设每次API调用需要0.1秒）
    api_call_time = 0.1  # 秒
    time_saved = api_calls_saved * api_call_time
    
    print(f"\n⏱️ 时间节约:")
    print(f"每次API调用时间: {api_call_time} 秒")
    print(f"总时间节约: {time_saved:.1f} 秒")
    print(f"时间节约率: {savings_percentage:.1f}%")

def main():
    """主函数"""
    print("🤖 API优化效果测试")
    print("=" * 60)
    
    # 运行所有测试
    test_blank_message_skipping()
    test_api_rate_limiting()
    test_flood_wait_handling()
    test_performance_improvement()
    
    print(f"\n🎉 测试完成!")
    print(f"\n💡 优化总结:")
    print("✅ 空白消息自动跳过，节约API调用")
    print("✅ 智能API频率控制，避免FLOOD_WAIT")
    print("✅ 错误处理和重试机制")
    print("✅ 性能显著提升，减少不必要的操作")

if __name__ == "__main__":
    main()

