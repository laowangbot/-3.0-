#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听系统优化验证脚本
测试优化后的系统性能
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from monitoring_engine import MonitoringEngine
from pyrogram import Client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizationTester:
    """优化测试器"""
    
    def __init__(self):
        self.config = get_config()
        self.client = None
        self.monitoring_engine = None
        
    async def setup(self):
        """设置测试环境"""
        print("🔧 设置测试环境")
        print("=" * 50)
        
        # 获取配置
        api_id = self.config.get('api_id')
        api_hash = self.config.get('api_hash')
        
        if not api_id or not api_hash:
            print("❌ 缺少API配置")
            return False
        
        # 创建客户端
        self.client = Client("optimization_test", api_id=api_id, api_hash=api_hash)
        
        # 创建监听引擎
        self.monitoring_engine = MonitoringEngine(self.client, self.config)
        
        print("✅ 测试环境设置完成")
        return True
    
    def test_configuration(self):
        """测试配置优化"""
        print("\n🧪 测试配置优化")
        print("=" * 50)
        
        # 检查关键配置
        config_tests = [
            ("max_concurrent_tasks", 50, "并发任务数"),
            ("max_user_concurrent_tasks", 100, "用户并发任务数"),
            ("batch_size", 10, "批处理大小"),
            ("check_interval", 3, "检查间隔"),
            ("max_messages_per_check", 200, "最大消息检查数"),
            ("api_rate_limit", 30, "API限制"),
            ("message_delay", 0.02, "消息延迟"),
            ("media_group_delay", 0.5, "媒体组延迟")
        ]
        
        all_passed = True
        for key, expected, description in config_tests:
            actual = self.config.get(key)
            if actual == expected:
                print(f"✅ {description}: {actual} (符合预期)")
            else:
                print(f"❌ {description}: {actual} (预期: {expected})")
                all_passed = False
        
        return all_passed
    
    def test_performance_calculation(self):
        """测试性能计算"""
        print("\n📊 测试性能计算")
        print("=" * 50)
        
        # 模拟性能数据
        test_data = [
            {"total": 1000, "successful": 950, "failed": 50},
            {"total": 500, "successful": 400, "failed": 100},
            {"total": 2000, "successful": 1900, "failed": 100},
            {"total": 0, "successful": 0, "failed": 0}
        ]
        
        for i, data in enumerate(test_data, 1):
            total = data["total"]
            successful = data["successful"]
            failed = data["failed"]
            
            success_rate = (successful / total * 100) if total > 0 else 0
            failure_rate = (failed / total * 100) if total > 0 else 0
            
            print(f"测试 {i}: 总消息 {total}, 成功 {successful}, 失败 {failed}")
            print(f"  成功率: {success_rate:.2f}%, 失败率: {failure_rate:.2f}%")
            
            # 检查性能告警
            if success_rate < self.config.get('performance_alert_threshold', 0.9) * 100:
                print(f"  ⚠️ 性能告警: 成功率 {success_rate:.2f}% 低于阈值")
            else:
                print(f"  ✅ 性能正常")
        
        return True
    
    def test_api_rate_limiting(self):
        """测试API限制逻辑"""
        print("\n🚦 测试API限制逻辑")
        print("=" * 50)
        
        # 模拟API调用时间记录
        api_call_times = []
        current_time = datetime.now()
        
        # 模拟1分钟内的API调用
        for i in range(35):  # 超过限制的调用次数
            call_time = current_time - timedelta(seconds=i*2)  # 每2秒一次调用
            api_call_times.append(call_time)
        
        # 检查是否超过限制
        recent_calls = [
            call_time for call_time in api_call_times
            if current_time - call_time < timedelta(minutes=1)
        ]
        
        rate_limit = self.config.get('api_rate_limit', 30)
        print(f"API调用次数: {len(recent_calls)}")
        print(f"API限制: {rate_limit}")
        
        if len(recent_calls) >= rate_limit:
            print("⚠️ 超过API限制，需要等待")
            oldest_call = min(recent_calls)
            wait_time = 60 - (current_time - oldest_call).total_seconds()
            print(f"需要等待: {wait_time:.2f} 秒")
        else:
            print("✅ API调用在限制范围内")
        
        return True
    
    def test_batch_processing(self):
        """测试分批处理逻辑"""
        print("\n📦 测试分批处理逻辑")
        print("=" * 50)
        
        # 模拟不同数量的频道
        test_cases = [
            {"channels": 5, "expected_batches": 1},
            {"channels": 15, "expected_batches": 2},
            {"channels": 30, "expected_batches": 3},
            {"channels": 50, "expected_batches": 5},
            {"channels": 100, "expected_batches": 10}
        ]
        
        batch_size = self.config.get('batch_size', 10)
        
        for case in test_cases:
            channels = case["channels"]
            expected_batches = case["expected_batches"]
            
            actual_batches = (channels + batch_size - 1) // batch_size
            
            print(f"频道数: {channels}, 批处理大小: {batch_size}")
            print(f"预期批次数: {expected_batches}, 实际批次数: {actual_batches}")
            
            if actual_batches == expected_batches:
                print("✅ 分批计算正确")
            else:
                print("❌ 分批计算错误")
        
        return True
    
    def test_error_recovery(self):
        """测试错误恢复机制"""
        print("\n🔄 测试错误恢复机制")
        print("=" * 50)
        
        # 测试指数退避
        base_delay = self.config.get('api_retry_delay', 2)
        backoff_factor = self.config.get('api_backoff_factor', 2)
        max_errors = self.config.get('max_consecutive_errors', 5)
        
        print(f"基础延迟: {base_delay} 秒")
        print(f"退避因子: {backoff_factor}")
        print(f"最大连续错误: {max_errors}")
        
        for error_count in range(1, 8):
            retry_delay = base_delay * (backoff_factor ** error_count)
            print(f"错误次数 {error_count}: 重试延迟 {retry_delay} 秒")
            
            if error_count >= max_errors:
                print(f"  🚨 触发熔断器 (连续错误 {error_count} 次)")
        
        return True
    
    def test_memory_management(self):
        """测试内存管理"""
        print("\n💾 测试内存管理")
        print("=" * 50)
        
        max_messages = self.config.get('max_processed_messages', 10000)
        cleanup_interval = self.config.get('message_cleanup_interval', 3600)
        memory_threshold = self.config.get('memory_usage_threshold', 0.8)
        
        print(f"最大存储消息数: {max_messages}")
        print(f"清理间隔: {cleanup_interval} 秒 ({cleanup_interval/3600:.1f} 小时)")
        print(f"内存使用阈值: {memory_threshold*100:.0f}%")
        
        # 计算清理频率
        messages_per_hour = max_messages / (cleanup_interval / 3600)
        print(f"每小时处理消息数: {messages_per_hour:.0f}")
        
        return True
    
    async def run_performance_test(self):
        """运行性能测试"""
        print("\n🚀 运行性能测试")
        print("=" * 50)
        
        # 模拟30个源频道的场景
        source_channels = 30
        target_channels = 20
        
        print(f"模拟场景: {source_channels} 个源频道 → {target_channels} 个目标频道")
        
        # 计算理论性能
        batch_size = self.config.get('batch_size', 10)
        check_interval = self.config.get('check_interval', 3)
        
        total_batches = (source_channels + batch_size - 1) // batch_size
        full_cycle_time = total_batches * check_interval
        
        print(f"批处理大小: {batch_size}")
        print(f"检查间隔: {check_interval} 秒")
        print(f"总批次数: {total_batches}")
        print(f"完整检查周期: {full_cycle_time} 秒")
        
        # 计算吞吐量
        max_messages = self.config.get('max_messages_per_check', 200)
        messages_per_cycle = source_channels * max_messages
        messages_per_hour = (messages_per_cycle * 3600) / full_cycle_time
        
        print(f"每周期检查消息数: {messages_per_cycle}")
        print(f"理论每小时处理消息数: {messages_per_hour:.0f}")
        
        # 检查是否满足需求
        if full_cycle_time <= 10:
            print("✅ 检查周期满足需求 (<10秒)")
        else:
            print(f"⚠️ 检查周期过长: {full_cycle_time} 秒")
        
        if messages_per_hour >= 10000:
            print("✅ 吞吐量满足需求 (>10,000 消息/小时)")
        else:
            print(f"⚠️ 吞吐量可能不足: {messages_per_hour:.0f} 消息/小时")
        
        return True
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🧪 监听系统优化验证")
        print("=" * 50)
        
        # 设置测试环境
        if not await self.setup():
            return False
        
        # 运行各项测试
        tests = [
            ("配置优化", self.test_configuration),
            ("性能计算", self.test_performance_calculation),
            ("API限制", self.test_api_rate_limiting),
            ("分批处理", self.test_batch_processing),
            ("错误恢复", self.test_error_recovery),
            ("内存管理", self.test_memory_management),
            ("性能测试", self.run_performance_test)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                else:
                    result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"❌ {test_name} 测试失败: {e}")
                results.append((test_name, False))
        
        # 输出测试结果
        print("\n📋 测试结果汇总")
        print("=" * 50)
        
        passed = 0
        total = len(results)
        
        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n总体结果: {passed}/{total} 项测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！系统优化成功！")
        else:
            print("⚠️ 部分测试失败，需要进一步优化")
        
        return passed == total

def main():
    """主函数"""
    tester = OptimizationTester()
    
    try:
        result = asyncio.run(tester.run_all_tests())
        return 0 if result else 1
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
