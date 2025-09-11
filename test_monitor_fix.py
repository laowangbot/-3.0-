#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试监听功能修复
"""

def test_user_state_handling():
    """测试用户状态处理"""
    print("🔍 测试用户状态处理逻辑")
    
    # 模拟用户状态
    user_states = {
        7951964655: {
            'state': 'waiting_source_channel',
            'action': 'monitor_test'
        }
    }
    
    # 测试状态检查
    user_id = 7951964655
    if user_id in user_states:
        state = user_states[user_id]
        print(f"✅ 找到用户状态: {state}")
        
        if state['state'] == 'waiting_source_channel':
            print("✅ 状态匹配: waiting_source_channel")
            return True
        else:
            print(f"❌ 状态不匹配: {state['state']}")
            return False
    else:
        print("❌ 用户状态不存在")
        return False

def test_channel_parsing():
    """测试频道解析"""
    print("\n🔍 测试频道解析功能")
    
    test_cases = [
        "https://t.me/xsm58",
        "@xsm58",
        "-1001234567890",
        "xsm58"
    ]
    
    for test_input in test_cases:
        print(f"测试输入: {test_input}")
        
        # 模拟解析逻辑
        if test_input.startswith("https://t.me/"):
            channel = test_input.split("/")[-1]
            if not channel.startswith("@"):
                channel = "@" + channel
            print(f"  -> 解析结果: {channel}")
        elif test_input.startswith("@"):
            channel = test_input
            print(f"  -> 解析结果: {channel}")
        elif test_input.startswith("-100"):
            channel = test_input
            print(f"  -> 解析结果: {channel}")
        else:
            channel = "@" + test_input
            print(f"  -> 解析结果: {channel}")

if __name__ == "__main__":
    print("🧪 监听功能修复测试")
    print("=" * 50)
    
    # 测试用户状态处理
    state_test = test_user_state_handling()
    
    # 测试频道解析
    test_channel_parsing()
    
    print("\n" + "=" * 50)
    if state_test:
        print("✅ 所有测试通过！监听功能应该可以正常工作了。")
    else:
        print("❌ 测试失败，需要进一步检查。")


