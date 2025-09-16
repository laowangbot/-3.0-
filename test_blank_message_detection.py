#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试智能空白消息检测功能
验证消息引擎的空白消息检测和过滤功能
"""

import sys
import os
from unittest.mock import Mock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from message_engine import MessageEngine

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

def test_blank_message_detection():
    """测试空白消息检测功能"""
    print("🧪 智能空白消息检测功能测试")
    print("=" * 60)
    
    # 创建消息引擎
    message_engine = MessageEngine({})
    
    # 测试用例
    test_cases = [
        # 正常消息
        {"name": "正常文本消息", "text": "这是一条正常的消息", "expected": False},
        {"name": "正常媒体消息", "text": None, "caption": "图片说明", "media": True, "expected": False},
        {"name": "正常长文本", "text": "这是一条很长的消息，包含很多内容，应该不会被过滤", "expected": False},
        
        # 空白消息
        {"name": "空文本消息", "text": "", "expected": True},
        {"name": "None文本消息", "text": None, "expected": True},
        {"name": "空白字符消息", "text": "   ", "expected": True},
        {"name": "制表符消息", "text": "\t\t", "expected": True},
        {"name": "换行符消息", "text": "\n\n", "expected": True},
        {"name": "混合空白字符", "text": " \t\n\r ", "expected": True},
        
        # 空标题消息
        {"name": "空标题消息", "text": None, "caption": "", "expected": True},
        {"name": "空白标题消息", "text": None, "caption": "   ", "expected": True},
        
        # 重复字符消息
        {"name": "重复字符消息", "text": "aaaaa", "expected": True},
        {"name": "重复数字消息", "text": "11111", "expected": True},
        {"name": "重复符号消息", "text": "....", "expected": True},
        
        # 过短消息
        {"name": "过短数字消息", "text": "123", "expected": True},
        {"name": "过短符号消息", "text": "!@#", "expected": True},
        {"name": "过短表情消息", "text": "😀", "expected": True},
        
        # 只包含链接的消息
        {"name": "只包含链接", "text": "https://example.com", "expected": True},
        {"name": "多个链接", "text": "https://example.com https://test.com", "expected": True},
        
        # 特殊消息类型
        {"name": "空消息属性", "text": "test", "empty": True, "expected": True},
        {"name": "服务消息", "text": "test", "service": True, "expected": True},
        
        # 边界情况
        {"name": "短但有意义", "text": "OK", "expected": False},
        {"name": "短数字但有意义", "text": "12345", "expected": False},
        {"name": "链接加文字", "text": "查看链接 https://example.com", "expected": False},
    ]
    
    print("\n📊 测试结果:")
    print("-" * 60)
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        # 创建模拟消息
        message = create_mock_message(
            text=case.get('text'),
            caption=case.get('caption'),
            media=case.get('media'),
            empty=case.get('empty', False),
            service=case.get('service', False)
        )
        
        # 测试空白消息检测
        is_blank = message_engine._is_blank_message(message)
        expected = case['expected']
        
        # 检查结果
        if is_blank == expected:
            status = "✅ 通过"
            passed += 1
        else:
            status = "❌ 失败"
            failed += 1
        
        print(f"{i:2d}. {case['name']:<20} | 预期: {expected} | 实际: {is_blank} | {status}")
        
        # 显示消息内容（用于调试）
        if is_blank != expected:
            print(f"    消息内容: {repr(case.get('text', 'None'))}")
    
    print(f"\n📈 测试总结:")
    print(f"  总测试数: {len(test_cases)}")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  成功率: {passed/len(test_cases)*100:.1f}%")
    
    return failed == 0

def test_should_process_message():
    """测试should_process_message方法"""
    print("\n🔍 should_process_message 方法测试")
    print("-" * 60)
    
    message_engine = MessageEngine({})
    
    # 测试空白消息是否被跳过
    blank_message = create_mock_message(text="   ")
    should_process = message_engine.should_process_message(blank_message)
    
    print(f"空白消息处理结果: {should_process}")
    print(f"预期结果: False (应该跳过)")
    
    if not should_process:
        print("✅ 空白消息被正确跳过")
        return True
    else:
        print("❌ 空白消息未被跳过")
        return False

def test_performance():
    """测试性能"""
    print("\n⚡ 性能测试")
    print("-" * 60)
    
    import time
    
    message_engine = MessageEngine({})
    
    # 创建大量测试消息
    test_messages = []
    for i in range(1000):
        if i % 10 == 0:
            # 每10条消息中1条是空白消息
            message = create_mock_message(text="   ")
        else:
            message = create_mock_message(text=f"正常消息 {i}")
        test_messages.append(message)
    
    # 测试检测性能
    start_time = time.time()
    
    blank_count = 0
    for message in test_messages:
        if message_engine._is_blank_message(message):
            blank_count += 1
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"处理消息数: {len(test_messages)}")
    print(f"检测到空白消息: {blank_count}")
    print(f"处理时间: {processing_time:.3f}秒")
    print(f"平均每条消息: {processing_time/len(test_messages)*1000:.3f}毫秒")
    
    # 性能要求：每条消息处理时间应小于1毫秒
    avg_time_per_message = processing_time / len(test_messages) * 1000
    if avg_time_per_message < 1.0:
        print("✅ 性能测试通过")
        return True
    else:
        print("❌ 性能测试失败")
        return False

def main():
    """主函数"""
    print("🤖 智能空白消息检测功能完整测试")
    print("=" * 60)
    
    # 运行所有测试
    test1_passed = test_blank_message_detection()
    test2_passed = test_should_process_message()
    test3_passed = test_performance()
    
    print(f"\n🎉 测试完成!")
    print(f"空白消息检测: {'✅ 通过' if test1_passed else '❌ 失败'}")
    print(f"消息处理逻辑: {'✅ 通过' if test2_passed else '❌ 失败'}")
    print(f"性能测试: {'✅ 通过' if test3_passed else '❌ 失败'}")
    
    all_passed = test1_passed and test2_passed and test3_passed
    print(f"\n总体结果: {'✅ 所有测试通过' if all_passed else '❌ 部分测试失败'}")
    
    if all_passed:
        print("\n💡 功能特性总结:")
        print("✅ 智能检测空白消息")
        print("✅ 检测重复字符消息")
        print("✅ 检测过短无意义消息")
        print("✅ 检测只包含链接的消息")
        print("✅ 检测特殊消息类型")
        print("✅ 高性能处理")
        print("✅ 集成到消息处理流程")

if __name__ == "__main__":
    main()

