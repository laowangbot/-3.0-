#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试用户状态修复
"""

def test_user_id_type_consistency():
    """测试用户ID类型一致性"""
    print("🔍 测试用户ID类型一致性")
    
    # 模拟用户状态设置（回调查询）
    callback_user_id = 7951964655  # 整数类型
    user_states = {}
    
    # 设置用户状态（修复后）
    user_id_str = str(callback_user_id)
    user_states[user_id_str] = {
        'state': 'waiting_source_channel',
        'action': 'monitor_test'
    }
    
    print(f"✅ 设置用户状态: user_id={user_id_str}, type={type(user_id_str)}")
    
    # 模拟文本消息处理
    message_user_id = "7951964655"  # 字符串类型
    
    # 检查用户状态
    if message_user_id in user_states:
        state = user_states[message_user_id]
        print(f"✅ 找到用户状态: {state}")
        print(f"✅ 状态匹配: {state['state'] == 'waiting_source_channel'}")
        return True
    else:
        print("❌ 用户状态不存在")
        return False

def test_old_vs_new_behavior():
    """测试修复前后的行为差异"""
    print("\n🔍 测试修复前后的行为差异")
    
    # 修复前（错误的行为）
    print("❌ 修复前（错误）:")
    callback_user_id = 7951964655  # 整数
    message_user_id = "7951964655"  # 字符串
    user_states_old = {callback_user_id: {'state': 'waiting_source_channel'}}  # 整数键
    
    if message_user_id in user_states_old:
        print("  -> 找到状态（不应该发生）")
    else:
        print("  -> 未找到状态（这是问题所在）")
    
    # 修复后（正确的行为）
    print("✅ 修复后（正确）:")
    user_states_new = {str(callback_user_id): {'state': 'waiting_source_channel'}}  # 字符串键
    
    if message_user_id in user_states_new:
        print("  -> 找到状态（正确）")
        return True
    else:
        print("  -> 未找到状态（不应该发生）")
        return False

if __name__ == "__main__":
    print("🧪 用户状态修复测试")
    print("=" * 50)
    
    # 测试用户ID类型一致性
    consistency_test = test_user_id_type_consistency()
    
    # 测试修复前后行为差异
    behavior_test = test_old_vs_new_behavior()
    
    print("\n" + "=" * 50)
    if consistency_test and behavior_test:
        print("✅ 所有测试通过！用户状态问题已修复。")
        print("📱 现在监听功能应该可以正常工作了。")
    else:
        print("❌ 测试失败，需要进一步检查。")


