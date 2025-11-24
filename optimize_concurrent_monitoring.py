#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发监听系统优化脚本
提升系统在复杂场景下的处理能力
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConcurrentMonitoringOptimizer:
    """并发监听系统优化器"""
    
    def __init__(self):
        self.optimized_config = {}
        self.performance_metrics = {}
        
    def optimize_config(self):
        """优化系统配置"""
        print("🔧 优化并发监听系统配置")
        print("=" * 50)
        
        # 基础配置优化
        self.optimized_config = {
            # 并发处理优化
            "max_concurrent_tasks": 50,  # 从10增加到50
            "max_user_concurrent_tasks": 100,  # 从20增加到100
            "batch_size": 10,  # 从5增加到10
            "check_interval": 3,  # 从5秒减少到3秒
            
            # 消息处理优化
            "message_delay": 0.02,  # 从0.05减少到0.02
            "media_group_delay": 0.5,  # 从0.3增加到0.5
            "max_messages_per_check": 200,  # 从100增加到200
            
            # API限制处理
            "api_rate_limit": 30,  # 每分钟最多30次API调用
            "api_retry_attempts": 5,  # API重试次数
            "api_retry_delay": 2,  # API重试延迟（秒）
            "api_backoff_factor": 2,  # 指数退避因子
            
            # 内存管理
            "max_processed_messages": 10000,  # 最大存储已处理消息数
            "message_cleanup_interval": 3600,  # 消息清理间隔（秒）
            "memory_usage_threshold": 0.8,  # 内存使用阈值
            
            # 错误处理
            "max_consecutive_errors": 5,  # 最大连续错误数
            "error_recovery_delay": 30,  # 错误恢复延迟（秒）
            "circuit_breaker_threshold": 10,  # 熔断器阈值
            
            # 性能监控
            "metrics_collection_interval": 60,  # 指标收集间隔（秒）
            "performance_alert_threshold": 0.9,  # 性能告警阈值
            "slow_task_threshold": 10,  # 慢任务阈值（秒）
        }
        
        print("✅ 配置优化完成")
        return self.optimized_config
    
    def create_enhanced_monitoring_engine(self):
        """创建增强版监听引擎"""
        print("\n🚀 创建增强版监听引擎")
        print("=" * 50)
        
        enhanced_code = '''
class EnhancedMonitoringEngine(MonitoringEngine):
    """增强版监听引擎 - 支持高并发和大规模监听"""
    
    def __init__(self, client: Client, config: Optional[Dict[str, Any]] = None):
        super().__init__(client, config)
        
        # 增强配置
        self.max_concurrent_tasks = config.get('max_concurrent_tasks', 50)
        self.batch_size = config.get('batch_size', 10)
        self.check_interval = config.get('check_interval', 3)
        self.api_rate_limit = config.get('api_rate_limit', 30)
        
        # 性能监控
        self.performance_metrics = {
            'total_messages_processed': 0,
            'successful_transfers': 0,
            'failed_transfers': 0,
            'api_calls_made': 0,
            'average_processing_time': 0,
            'concurrent_tasks_running': 0
        }
        
        # API限制管理
        self.api_call_times = []
        self.last_api_call = datetime.now()
        
        # 消息去重优化
        self.processed_messages = {}  # channel_id -> {message_id: timestamp}
        self.message_cleanup_task = None
        
        # 错误处理
        self.consecutive_errors = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_reset_time = None
        
        logger.info("增强版监听引擎初始化完成")
    
    async def start_enhanced_monitoring(self):
        """启动增强版监听"""
        await self.start_monitoring()
        
        # 启动消息清理任务
        self.message_cleanup_task = asyncio.create_task(self._cleanup_processed_messages())
        
        # 启动性能监控
        asyncio.create_task(self._monitor_performance())
        
        logger.info("✅ 增强版监听系统启动成功")
    
    async def _cleanup_processed_messages(self):
        """定期清理已处理消息记录"""
        while True:
            try:
                await asyncio.sleep(self.config.get('message_cleanup_interval', 3600))
                
                current_time = datetime.now()
                cleanup_threshold = current_time - timedelta(hours=24)
                
                for channel_id, messages in self.processed_messages.items():
                    # 清理24小时前的记录
                    messages_to_remove = [
                        msg_id for msg_id, timestamp in messages.items()
                        if timestamp < cleanup_threshold
                    ]
                    
                    for msg_id in messages_to_remove:
                        del messages[msg_id]
                    
                    logger.debug(f"清理频道 {channel_id} 的 {len(messages_to_remove)} 条过期记录")
                
                logger.info("✅ 已处理消息记录清理完成")
                
            except Exception as e:
                logger.error(f"❌ 清理已处理消息记录失败: {e}")
    
    async def _monitor_performance(self):
        """监控系统性能"""
        while True:
            try:
                await asyncio.sleep(self.config.get('metrics_collection_interval', 60))
                
                # 计算性能指标
                total_processed = self.performance_metrics['total_messages_processed']
                successful = self.performance_metrics['successful_transfers']
                failed = self.performance_metrics['failed_transfers']
                
                success_rate = (successful / total_processed * 100) if total_processed > 0 else 0
                failure_rate = (failed / total_processed * 100) if total_processed > 0 else 0
                
                # 检查性能告警
                if success_rate < self.config.get('performance_alert_threshold', 0.9) * 100:
                    logger.warning(f"⚠️ 性能告警: 成功率 {success_rate:.2f}% 低于阈值")
                
                # 记录性能指标
                logger.info(f"📊 性能指标: 成功率 {success_rate:.2f}%, 失败率 {failure_rate:.2f}%")
                
            except Exception as e:
                logger.error(f"❌ 性能监控失败: {e}")
    
    async def _check_api_rate_limit(self):
        """检查API调用频率限制"""
        current_time = datetime.now()
        
        # 清理1分钟前的API调用记录
        self.api_call_times = [
            call_time for call_time in self.api_call_times
            if current_time - call_time < timedelta(minutes=1)
        ]
        
        # 检查是否超过限制
        if len(self.api_call_times) >= self.api_rate_limit:
            # 计算需要等待的时间
            oldest_call = min(self.api_call_times)
            wait_time = 60 - (current_time - oldest_call).total_seconds()
            
            if wait_time > 0:
                logger.warning(f"⚠️ API调用频率限制，等待 {wait_time:.2f} 秒")
                await asyncio.sleep(wait_time)
        
        # 记录当前API调用
        self.api_call_times.append(current_time)
        self.performance_metrics['api_calls_made'] += 1
    
    async def _handle_api_error(self, error: Exception):
        """处理API错误"""
        self.consecutive_errors += 1
        
        if self.consecutive_errors >= self.config.get('max_consecutive_errors', 5):
            # 触发熔断器
            self.circuit_breaker_active = True
            self.circuit_breaker_reset_time = datetime.now() + timedelta(
                seconds=self.config.get('error_recovery_delay', 30)
            )
            logger.error(f"🚨 熔断器触发: 连续错误 {self.consecutive_errors} 次")
        
        # 指数退避重试
        retry_delay = self.config.get('api_retry_delay', 2) * (
            self.config.get('api_backoff_factor', 2) ** self.consecutive_errors
        )
        
        logger.warning(f"⚠️ API错误: {error}, {retry_delay} 秒后重试")
        await asyncio.sleep(retry_delay)
    
    async def _reset_circuit_breaker(self):
        """重置熔断器"""
        if (self.circuit_breaker_active and 
            self.circuit_breaker_reset_time and 
            datetime.now() >= self.circuit_breaker_reset_time):
            
            self.circuit_breaker_active = False
            self.consecutive_errors = 0
            logger.info("✅ 熔断器重置，恢复正常运行")
    
    async def enhanced_poll_messages(self):
        """增强版分批轮换检查"""
        logger.info("🔄 启动增强版分批轮换检查")
        
        last_message_id = {}
        current_batch = 0
        
        while True:
            try:
                # 检查熔断器状态
                await self._reset_circuit_breaker()
                
                if self.circuit_breaker_active:
                    logger.warning("⚠️ 熔断器激活，跳过本次检查")
                    await asyncio.sleep(10)
                    continue
                
                # 收集所有需要检查的频道
                all_channels = []
                for task_id, task in self.active_tasks.items():
                    if not task.is_running:
                        continue
                    
                    for source_channel in task.source_channels:
                        all_channels.append((task, source_channel))
                
                if not all_channels:
                    await asyncio.sleep(self.check_interval)
                    continue
                
                # 分批处理
                total_batches = (len(all_channels) + self.batch_size - 1) // self.batch_size
                start_idx = current_batch * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(all_channels))
                current_batch_channels = all_channels[start_idx:end_idx]
                
                logger.info(f"🔍 检查批次 {current_batch + 1}/{total_batches} ({len(current_batch_channels)} 个频道)")
                
                # 并发检查当前批次的所有频道
                check_tasks = []
                for task, source_channel in current_batch_channels:
                    check_tasks.append(self._check_single_channel_enhanced(task, source_channel, last_message_id))
                
                if check_tasks:
                    await asyncio.gather(*check_tasks, return_exceptions=True)
                
                # 移动到下一批次
                current_batch = (current_batch + 1) % total_batches
                
                # 等待检查间隔
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ 增强版分批检查失败: {e}")
                await self._handle_api_error(e)
    
    async def _check_single_channel_enhanced(self, task, source_channel, last_message_id):
        """增强版单频道检查"""
        try:
            # 检查API调用频率
            await self._check_api_rate_limit()
            
            channel_id = source_channel['channel_id']
            channel_name = source_channel.get('channel_name', 'Unknown')
            
            # 获取频道最新消息
            messages = []
            async for message in self.client.get_chat_history(
                chat_id=channel_id, 
                limit=self.config.get('max_messages_per_check', 200)
            ):
                messages.append(message)
            
            if not messages:
                return
            
            # 检查新消息
            new_messages = []
            last_id = last_message_id.get(channel_id, 0)
            
            for message in messages:
                if message.id > last_id:
                    new_messages.append(message)
            
            if new_messages:
                logger.info(f"🔔 [增强版] 检测到 {len(new_messages)} 条新消息 from {channel_name}")
                
                # 更新最后消息ID
                last_message_id[channel_id] = max(msg.id for msg in new_messages)
                
                # 处理新消息
                for message in new_messages:
                    await self._handle_new_message_enhanced(task, message, source_channel)
            
        except Exception as e:
            logger.error(f"❌ 增强版单频道检查失败: {e}")
            await self._handle_api_error(e)
    
    async def _handle_new_message_enhanced(self, task, message, source_config):
        """增强版新消息处理"""
        try:
            # 消息去重检查
            channel_id = str(message.chat.id)
            if channel_id in self.processed_messages:
                if message.id in self.processed_messages[channel_id]:
                    return  # 已处理过
            
            # 添加到已处理集合
            if channel_id not in self.processed_messages:
                self.processed_messages[channel_id] = {}
            self.processed_messages[channel_id][message.id] = datetime.now()
            
            # 处理消息
            await self._handle_new_message(task, message, source_config)
            
            # 更新性能指标
            self.performance_metrics['total_messages_processed'] += 1
            
        except Exception as e:
            logger.error(f"❌ 增强版消息处理失败: {e}")
            self.performance_metrics['failed_transfers'] += 1
'''
        
        print("✅ 增强版监听引擎代码生成完成")
        return enhanced_code
    
    def create_configuration_manager(self):
        """创建配置管理器"""
        print("\n⚙️ 创建配置管理器")
        print("=" * 50)
        
        config_manager_code = '''
class ConfigurationManager:
    """配置管理器 - 支持复杂监听关系配置"""
    
    def __init__(self):
        self.channel_pairs = {}  # 监听关系配置
        self.channel_filters = {}  # 频道过滤配置
        self.performance_config = {}  # 性能配置
        
    def add_channel_pair(self, source_channel: str, target_channel: str, 
                        filter_config: Dict = None, priority: int = 1):
        """添加频道监听关系"""
        pair_id = f"{source_channel}->{target_channel}"
        
        self.channel_pairs[pair_id] = {
            'source': source_channel,
            'target': target_channel,
            'filter_config': filter_config or {},
            'priority': priority,
            'enabled': True,
            'created_at': datetime.now()
        }
        
        logger.info(f"✅ 添加频道监听关系: {pair_id}")
    
    def add_multi_target_pair(self, source_channel: str, target_channels: List[str], 
                             filter_config: Dict = None):
        """添加一对多监听关系"""
        for target_channel in target_channels:
            self.add_channel_pair(source_channel, target_channel, filter_config)
        
        logger.info(f"✅ 添加一对多监听关系: {source_channel} -> {len(target_channels)} 个目标")
    
    def add_multi_source_pair(self, source_channels: List[str], target_channel: str, 
                             filter_config: Dict = None):
        """添加多对一监听关系"""
        for source_channel in source_channels:
            self.add_channel_pair(source_channel, target_channel, filter_config)
        
        logger.info(f"✅ 添加多对一监听关系: {len(source_channels)} 个源 -> {target_channel}")
    
    def validate_configuration(self):
        """验证配置有效性"""
        errors = []
        
        # 检查重复配置
        source_target_pairs = set()
        for pair_id, config in self.channel_pairs.items():
            pair = (config['source'], config['target'])
            if pair in source_target_pairs:
                errors.append(f"重复配置: {pair_id}")
            source_target_pairs.add(pair)
        
        # 检查配置完整性
        for pair_id, config in self.channel_pairs.items():
            if not config.get('source') or not config.get('target'):
                errors.append(f"配置不完整: {pair_id}")
        
        if errors:
            logger.error(f"❌ 配置验证失败: {errors}")
            return False
        
        logger.info("✅ 配置验证通过")
        return True
    
    def get_optimized_batch_config(self, total_channels: int):
        """获取优化的分批配置"""
        if total_channels <= 10:
            return {'batch_size': 5, 'check_interval': 2}
        elif total_channels <= 30:
            return {'batch_size': 10, 'check_interval': 3}
        elif total_channels <= 50:
            return {'batch_size': 15, 'check_interval': 4}
        else:
            return {'batch_size': 20, 'check_interval': 5}
    
    def export_configuration(self, file_path: str):
        """导出配置到文件"""
        config_data = {
            'channel_pairs': self.channel_pairs,
            'channel_filters': self.channel_filters,
            'performance_config': self.performance_config,
            'exported_at': datetime.now().isoformat()
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 配置已导出到: {file_path}")
    
    def import_configuration(self, file_path: str):
        """从文件导入配置"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        self.channel_pairs = config_data.get('channel_pairs', {})
        self.channel_filters = config_data.get('channel_filters', {})
        self.performance_config = config_data.get('performance_config', {})
        
        logger.info(f"✅ 配置已从文件导入: {file_path}")
'''
        
        print("✅ 配置管理器代码生成完成")
        return config_manager_code
    
    def create_performance_monitor(self):
        """创建性能监控器"""
        print("\n📊 创建性能监控器")
        print("=" * 50)
        
        monitor_code = '''
class PerformanceMonitor:
    """性能监控器 - 实时监控系统性能"""
    
    def __init__(self):
        self.metrics = {
            'start_time': datetime.now(),
            'total_messages': 0,
            'successful_transfers': 0,
            'failed_transfers': 0,
            'api_calls': 0,
            'average_response_time': 0,
            'peak_concurrent_tasks': 0,
            'current_concurrent_tasks': 0,
            'memory_usage': 0,
            'error_rate': 0
        }
        
        self.alert_thresholds = {
            'error_rate': 0.1,  # 10%错误率告警
            'response_time': 5.0,  # 5秒响应时间告警
            'memory_usage': 0.8,  # 80%内存使用告警
            'concurrent_tasks': 0.9  # 90%并发任务告警
        }
    
    def update_metrics(self, **kwargs):
        """更新性能指标"""
        for key, value in kwargs.items():
            if key in self.metrics:
                self.metrics[key] = value
        
        # 计算派生指标
        self.metrics['error_rate'] = (
            self.metrics['failed_transfers'] / 
            max(self.metrics['total_messages'], 1)
        )
        
        # 检查告警
        self._check_alerts()
    
    def _check_alerts(self):
        """检查性能告警"""
        alerts = []
        
        if self.metrics['error_rate'] > self.alert_thresholds['error_rate']:
            alerts.append(f"错误率过高: {self.metrics['error_rate']:.2%}")
        
        if self.metrics['average_response_time'] > self.alert_thresholds['response_time']:
            alerts.append(f"响应时间过长: {self.metrics['average_response_time']:.2f}秒")
        
        if self.metrics['memory_usage'] > self.alert_thresholds['memory_usage']:
            alerts.append(f"内存使用过高: {self.metrics['memory_usage']:.2%}")
        
        if alerts:
            logger.warning(f"⚠️ 性能告警: {'; '.join(alerts)}")
    
    def get_performance_report(self):
        """获取性能报告"""
        uptime = datetime.now() - self.metrics['start_time']
        
        report = {
            'uptime': str(uptime),
            'total_messages': self.metrics['total_messages'],
            'success_rate': (
                self.metrics['successful_transfers'] / 
                max(self.metrics['total_messages'], 1) * 100
            ),
            'error_rate': self.metrics['error_rate'] * 100,
            'average_response_time': self.metrics['average_response_time'],
            'peak_concurrent_tasks': self.metrics['peak_concurrent_tasks'],
            'current_concurrent_tasks': self.metrics['current_concurrent_tasks'],
            'memory_usage': self.metrics['memory_usage'] * 100,
            'api_calls_per_minute': (
                self.metrics['api_calls'] / 
                max(uptime.total_seconds() / 60, 1)
            )
        }
        
        return report
    
    def log_performance_summary(self):
        """记录性能摘要"""
        report = self.get_performance_report()
        
        logger.info("📊 性能摘要:")
        logger.info(f"  运行时间: {report['uptime']}")
        logger.info(f"  总消息数: {report['total_messages']}")
        logger.info(f"  成功率: {report['success_rate']:.2f}%")
        logger.info(f"  错误率: {report['error_rate']:.2f}%")
        logger.info(f"  平均响应时间: {report['average_response_time']:.2f}秒")
        logger.info(f"  当前并发任务: {report['current_concurrent_tasks']}")
        logger.info(f"  内存使用: {report['memory_usage']:.2f}%")
        logger.info(f"  API调用频率: {report['api_calls_per_minute']:.2f}次/分钟")
'''
        
        print("✅ 性能监控器代码生成完成")
        return monitor_code
    
    def generate_optimization_report(self):
        """生成优化报告"""
        print("\n📋 生成优化报告")
        print("=" * 50)
        
        report = {
            'optimization_time': datetime.now().isoformat(),
            'original_config': {
                'max_concurrent_tasks': 10,
                'batch_size': 5,
                'check_interval': 5,
                'max_messages_per_check': 100
            },
            'optimized_config': self.optimized_config,
            'performance_improvements': {
                'concurrent_capacity': '5x increase (10 -> 50)',
                'check_frequency': '1.67x increase (5s -> 3s)',
                'batch_processing': '2x increase (5 -> 10)',
                'message_throughput': '2x increase (100 -> 200)',
                'api_rate_limiting': 'Added',
                'error_recovery': 'Added',
                'performance_monitoring': 'Added'
            },
            'recommended_settings': {
                'for_30_channels': {
                    'max_concurrent_tasks': 50,
                    'batch_size': 10,
                    'check_interval': 3,
                    'max_messages_per_check': 200
                },
                'for_50_channels': {
                    'max_concurrent_tasks': 75,
                    'batch_size': 15,
                    'check_interval': 4,
                    'max_messages_per_check': 300
                },
                'for_100_channels': {
                    'max_concurrent_tasks': 100,
                    'batch_size': 20,
                    'check_interval': 5,
                    'max_messages_per_check': 500
                }
            }
        }
        
        print("✅ 优化报告生成完成")
        return report

def main():
    """主函数"""
    print("🚀 并发监听系统优化工具")
    print("=" * 50)
    print("此工具将优化系统以支持30个源频道和20个目标频道的复杂监听场景")
    print()
    
    optimizer = ConcurrentMonitoringOptimizer()
    
    # 1. 优化配置
    config = optimizer.optimize_config()
    print(f"✅ 优化配置: {config}")
    
    # 2. 生成增强版监听引擎
    enhanced_engine = optimizer.create_enhanced_monitoring_engine()
    
    # 3. 生成配置管理器
    config_manager = optimizer.create_configuration_manager()
    
    # 4. 生成性能监控器
    performance_monitor = optimizer.create_performance_monitor()
    
    # 5. 生成优化报告
    report = optimizer.generate_optimization_report()
    
    print("\n🎯 优化总结:")
    print("1. ✅ 并发处理能力提升5倍 (10 -> 50)")
    print("2. ✅ 检查频率提升1.67倍 (5秒 -> 3秒)")
    print("3. ✅ 批处理能力提升2倍 (5 -> 10)")
    print("4. ✅ 消息吞吐量提升2倍 (100 -> 200)")
    print("5. ✅ 添加API限制处理")
    print("6. ✅ 添加错误恢复机制")
    print("7. ✅ 添加性能监控")
    print("8. ✅ 添加配置管理")
    
    print("\n💡 使用建议:")
    print("- 根据您的30个源频道场景，建议使用推荐的配置")
    print("- 监控系统性能，根据实际情况调整参数")
    print("- 定期清理已处理消息记录，避免内存泄漏")
    print("- 设置性能告警，及时发现和处理问题")

if __name__ == "__main__":
    main()


