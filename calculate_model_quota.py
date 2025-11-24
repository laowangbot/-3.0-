#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
模型配额计算器
用于计算不同AI模型的每日文本编辑能力
"""

def calculate_daily_capacity():
    """计算每日文本编辑能力"""
    print("📊 AI模型每日文本编辑能力分析")
    print("=" * 50)
    
    # gemma-3-27b模型参数
    gemma_daily_calls = 14400  # 14.4K次调用/天
    gemma_rpm = 30  # 每分钟30次调用
    
    # 假设每次调用处理一个文本
    print(f"gemma-3-27b模型:")
    print(f"  - 每日调用限制: {gemma_daily_calls:,} 次")
    print(f"  - 每分钟调用限制: {gemma_rpm} 次")
    print(f"  - 理论上每日可处理文本数: {gemma_daily_calls:,} 条")
    print()
    
    # gemini-2.5-flash模型参数（根据用户最新信息）
    gemini_flash_daily_calls = 250  # 每日250次调用
    gemini_flash_rpm = 10  # 假设值
    
    print(f"Gemini-2.5-flash模型:")
    print(f"  - 每日调用限制: {gemini_flash_daily_calls:,} 次")
    print(f"  - 每分钟调用限制: {gemini_flash_rpm} 次")
    print(f"  - 理论上每日可处理文本数: {gemini_flash_daily_calls:,} 条")
    print()
    
    # gemini-2.5-flash-lite模型参数（根据用户最新信息）
    gemini_flash_lite_daily_calls = 1000  # 每日1000次调用
    gemini_flash_lite_rpm = 15  # 假设值
    
    print(f"Gemini-2.5-flash-lite模型:")
    print(f"  - 每日调用限制: {gemini_flash_lite_daily_calls:,} 次")
    print(f"  - 每分钟调用限制: {gemini_flash_lite_rpm} 次")
    print(f"  - 理论上每日可处理文本数: {gemini_flash_lite_daily_calls:,} 条")
    print()
    
    # 比较分析
    print("📈 比较分析:")
    print(f"  - 如果需要每日处理5000-10000条文本:")
    print(f"    * gemma-3-27b可以满足需求 ({gemma_daily_calls >= 10000})")
    print(f"    * Gemini-2.5-flash无法满足需求 ({gemini_flash_daily_calls >= 10000})")
    print(f"    * Gemini-2.5-flash-lite无法满足需求 ({gemini_flash_lite_daily_calls >= 10000})")
    print()
    print("💡 建议策略:")
    print("  1. 主要使用gemma-3-27b模型处理日常任务")
    print("  2. 将Gemini模型作为备用选项或用于特殊场景")
    print("  3. 考虑结合其他免费AI服务构建混合解决方案")

if __name__ == "__main__":
    calculate_daily_capacity()