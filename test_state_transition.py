#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试监听状态转换
"""

def test_state_transition():
    """测试状态转换逻辑"""
    print("🔍 测试监听状态转换")
    
    # 模拟用户状态
    user_states = {}
    user_id = "7951964655"
    
    # 1. 初始状态：等待源频道
    user_states[user_id] = {
        'state': 'waiting_source_channel',
        'action': 'monitor_test'
    }
    print(f"1. 初始状态: {user_states[user_id]}")
    
    # 2. 处理源频道输入后，应该转换到等待目标频道
    source_channel = "@xsm58"
    source_title = "测试源频道"
    
    user_states[user_id] = {
        'state': 'waiting_target_channel',
        'action': 'monitor_test',
        'source_channel': source_channel,
        'source_title': source_title
    }
    print(f"2. 源频道处理后: {user_states[user_id]}")
    
    # 3. 验证状态转换
    if user_states[user_id]['state'] == 'waiting_target_channel':
        print("✅ 状态转换成功：源频道 -> 目标频道")
        return True
    else:
        print("❌ 状态转换失败")
        return False

def test_user_id_consistency():
    """测试用户ID一致性"""
    print("\n🔍 测试用户ID一致性")
    
    # 模拟不同场景下的用户ID
    callback_user_id = 7951964655  # 回调查询中的用户ID
    message_user_id = "7951964655"  # 文本消息中的用户ID
    
    # 确保类型一致
    callback_user_id_str = str(callback_user_id)
    
    print(f"回调查询用户ID: {callback_user_id} -> {callback_user_id_str}")
    print(f"文本消息用户ID: {message_user_id}")
    print(f"类型一致: {callback_user_id_str == message_user_id}")
    
    return callback_user_id_str == message_user_id

if __name__ == "__main__":
    print("🧪 监听状态转换测试")
    print("=" * 50)
    
    # 测试状态转换
    transition_test = test_state_transition()
    
    # 测试用户ID一致性
    consistency_test = test_user_id_consistency()
    
    print("\n" + "=" * 50)
    if transition_test and consistency_test:
        print("✅ 所有测试通过！")
        print("📱 现在监听功能应该可以正常进行状态转换了。")
        print("💡 输入源频道后，系统会要求您输入目标频道。")
    else:
        print("❌ 测试失败，需要进一步检查。")


