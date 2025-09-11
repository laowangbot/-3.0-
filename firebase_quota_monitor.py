#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firebase配额监控器
监控API使用情况，防止超出免费版配额
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import threading
from collections import deque

logger = logging.getLogger(__name__)

class FirebaseQuotaMonitor:
    """Firebase配额监控器"""
    
    def __init__(self, bot_id: str):
        """初始化配额监控器
        
        Args:
            bot_id: 机器人ID
        """
        self.bot_id = bot_id
        
        # 免费版Firebase配额限制
        self.quota_limits = {
            'reads_per_day': 50000,      # 每日读取限制
            'writes_per_day': 20000,     # 每日写入限制
            'deletes_per_day': 20000,    # 每日删除限制
            'reads_per_minute': 1000,    # 每分钟读取限制
            'writes_per_minute': 500,    # 每分钟写入限制
            'deletes_per_minute': 500,   # 每分钟删除限制
        }
        
        # 当前使用量
        self.current_usage = {
            'reads_today': 0,
            'writes_today': 0,
            'deletes_today': 0,
            'reads_this_minute': 0,
            'writes_this_minute': 0,
            'deletes_this_minute': 0,
        }
        
        # 历史记录（用于趋势分析）
        self.usage_history = deque(maxlen=1440)  # 保留24小时的数据（每分钟一条）
        
        # 监控状态
        self.monitoring = False
        self.monitor_task = None
        self.last_reset_date = datetime.now().date()
        
        # 预警阈值
        self.warning_thresholds = {
            'daily': 0.8,    # 80%时预警
            'minute': 0.9,   # 90%时预警
        }
        
        # 统计信息
        self.stats = {
            'total_operations': 0,
            'quota_warnings': 0,
            'quota_exceeded': 0,
            'auto_throttling': 0,
            'last_warning_time': None,
        }
        
        # 线程锁
        self.lock = threading.RLock()
        
        logger.info(f"✅ Firebase配额监控器初始化完成 (Bot: {bot_id})")
    
    async def start_monitoring(self):
        """启动配额监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ 配额监控已启动")
    
    async def stop_monitoring(self):
        """停止配额监控"""
        if not self.monitoring:
            return
        
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 配额监控已停止")
    
    async def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                self._check_quotas()
                self._record_usage()
                self._reset_daily_if_needed()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"配额监控错误: {e}")
    
    def _check_quotas(self):
        """检查配额使用情况"""
        with self.lock:
            current_time = datetime.now()
            
            # 检查每日配额
            daily_warnings = []
            if self.current_usage['reads_today'] >= self.quota_limits['reads_per_day'] * self.warning_thresholds['daily']:
                daily_warnings.append(f"读取: {self.current_usage['reads_today']}/{self.quota_limits['reads_per_day']}")
            
            if self.current_usage['writes_today'] >= self.quota_limits['writes_per_day'] * self.warning_thresholds['daily']:
                daily_warnings.append(f"写入: {self.current_usage['writes_today']}/{self.quota_limits['writes_per_day']}")
            
            if self.current_usage['deletes_today'] >= self.quota_limits['deletes_per_day'] * self.warning_thresholds['daily']:
                daily_warnings.append(f"删除: {self.current_usage['deletes_today']}/{self.quota_limits['deletes_per_day']}")
            
            # 检查每分钟配额
            minute_warnings = []
            if self.current_usage['reads_this_minute'] >= self.quota_limits['reads_per_minute'] * self.warning_thresholds['minute']:
                minute_warnings.append(f"读取: {self.current_usage['reads_this_minute']}/{self.quota_limits['reads_per_minute']}")
            
            if self.current_usage['writes_this_minute'] >= self.quota_limits['writes_per_minute'] * self.warning_thresholds['minute']:
                minute_warnings.append(f"写入: {self.current_usage['writes_this_minute']}/{self.quota_limits['writes_per_minute']}")
            
            if self.current_usage['deletes_this_minute'] >= self.quota_limits['deletes_per_minute'] * self.warning_thresholds['minute']:
                minute_warnings.append(f"删除: {self.current_usage['deletes_this_minute']}/{self.quota_limits['deletes_per_minute']}")
            
            # 发送预警
            if daily_warnings:
                self._send_warning("每日配额预警", daily_warnings, current_time)
            
            if minute_warnings:
                self._send_warning("每分钟配额预警", minute_warnings, current_time)
    
    def _send_warning(self, warning_type: str, details: List[str], current_time: datetime):
        """发送预警"""
        warning_message = f"⚠️ Firebase配额预警 ({warning_type}):\n" + "\n".join(f"  - {detail}" for detail in details)
        
        logger.warning(warning_message)
        
        with self.lock:
            self.stats['quota_warnings'] += 1
            self.stats['last_warning_time'] = current_time.isoformat()
    
    def _record_usage(self):
        """记录使用情况"""
        with self.lock:
            usage_record = {
                'timestamp': datetime.now().isoformat(),
                'reads_today': self.current_usage['reads_today'],
                'writes_today': self.current_usage['writes_today'],
                'deletes_today': self.current_usage['deletes_today'],
                'reads_this_minute': self.current_usage['reads_this_minute'],
                'writes_this_minute': self.current_usage['writes_this_minute'],
                'deletes_this_minute': self.current_usage['deletes_this_minute'],
            }
            
            self.usage_history.append(usage_record)
    
    def _reset_daily_if_needed(self):
        """如果需要，重置每日计数"""
        current_date = datetime.now().date()
        if current_date != self.last_reset_date:
            with self.lock:
                self.current_usage['reads_today'] = 0
                self.current_usage['writes_today'] = 0
                self.current_usage['deletes_today'] = 0
                self.last_reset_date = current_date
                logger.info("🔄 每日配额计数已重置")
    
    def record_operation(self, operation_type: str, count: int = 1):
        """记录操作使用量"""
        with self.lock:
            self.stats['total_operations'] += count
            
            if operation_type == 'read':
                self.current_usage['reads_today'] += count
                self.current_usage['reads_this_minute'] += count
            elif operation_type == 'write':
                self.current_usage['writes_today'] += count
                self.current_usage['writes_this_minute'] += count
            elif operation_type == 'delete':
                self.current_usage['deletes_today'] += count
                self.current_usage['deletes_this_minute'] += count
    
    def can_perform_operation(self, operation_type: str, count: int = 1) -> bool:
        """检查是否可以执行操作"""
        with self.lock:
            if operation_type == 'read':
                daily_limit = self.quota_limits['reads_per_day']
                minute_limit = self.quota_limits['reads_per_minute']
                daily_usage = self.current_usage['reads_today']
                minute_usage = self.current_usage['reads_this_minute']
            elif operation_type == 'write':
                daily_limit = self.quota_limits['writes_per_day']
                minute_limit = self.quota_limits['writes_per_minute']
                daily_usage = self.current_usage['writes_today']
                minute_usage = self.current_usage['writes_this_minute']
            elif operation_type == 'delete':
                daily_limit = self.quota_limits['deletes_per_day']
                minute_limit = self.quota_limits['deletes_per_minute']
                daily_usage = self.current_usage['deletes_today']
                minute_usage = self.current_usage['deletes_this_minute']
            else:
                return True
            
            # 检查是否超出限制
            if daily_usage + count > daily_limit:
                logger.error(f"❌ 超出每日{operation_type}配额: {daily_usage + count}/{daily_limit}")
                self.stats['quota_exceeded'] += 1
                return False
            
            if minute_usage + count > minute_limit:
                logger.error(f"❌ 超出每分钟{operation_type}配额: {minute_usage + count}/{minute_limit}")
                self.stats['quota_exceeded'] += 1
                return False
            
            return True
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """获取使用统计"""
        with self.lock:
            return {
                'current_usage': self.current_usage.copy(),
                'quota_limits': self.quota_limits.copy(),
                'usage_percentages': {
                    'reads_daily': round(self.current_usage['reads_today'] / self.quota_limits['reads_per_day'] * 100, 2),
                    'writes_daily': round(self.current_usage['writes_today'] / self.quota_limits['writes_per_day'] * 100, 2),
                    'deletes_daily': round(self.current_usage['deletes_today'] / self.quota_limits['deletes_per_day'] * 100, 2),
                    'reads_minute': round(self.current_usage['reads_this_minute'] / self.quota_limits['reads_per_minute'] * 100, 2),
                    'writes_minute': round(self.current_usage['writes_this_minute'] / self.quota_limits['writes_per_minute'] * 100, 2),
                    'deletes_minute': round(self.current_usage['deletes_this_minute'] / self.quota_limits['deletes_per_minute'] * 100, 2),
                },
                'stats': self.stats.copy(),
                'monitoring': self.monitoring,
                'last_reset_date': self.last_reset_date.isoformat(),
            }
    
    def get_usage_trend(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取使用趋势"""
        with self.lock:
            # 返回最近N小时的数据
            cutoff_time = datetime.now() - timedelta(hours=hours)
            trend_data = []
            
            for record in self.usage_history:
                record_time = datetime.fromisoformat(record['timestamp'])
                if record_time >= cutoff_time:
                    trend_data.append(record)
            
            return trend_data
    
    def reset_minute_counters(self):
        """重置每分钟计数器"""
        with self.lock:
            self.current_usage['reads_this_minute'] = 0
            self.current_usage['writes_this_minute'] = 0
            self.current_usage['deletes_this_minute'] = 0
            logger.debug("🔄 每分钟配额计数已重置")
    
    def set_warning_thresholds(self, daily: float = None, minute: float = None):
        """设置预警阈值"""
        with self.lock:
            if daily is not None:
                self.warning_thresholds['daily'] = daily
            if minute is not None:
                self.warning_thresholds['minute'] = minute
            
            logger.info(f"预警阈值已更新: 每日={self.warning_thresholds['daily']}, 每分钟={self.warning_thresholds['minute']}")

# ==================== 全局配额监控器 ====================

_global_quota_monitor = None

def get_global_quota_monitor(bot_id: str = None) -> Optional[FirebaseQuotaMonitor]:
    """获取全局配额监控器"""
    global _global_quota_monitor
    
    if _global_quota_monitor is None and bot_id:
        _global_quota_monitor = FirebaseQuotaMonitor(bot_id)
    
    return _global_quota_monitor

def set_global_quota_monitor(monitor: FirebaseQuotaMonitor):
    """设置全局配额监控器"""
    global _global_quota_monitor
    _global_quota_monitor = monitor

# ==================== 便捷函数 ====================

def record_firebase_operation(operation_type: str, count: int = 1, bot_id: str = None):
    """记录Firebase操作"""
    monitor = get_global_quota_monitor(bot_id)
    if monitor:
        monitor.record_operation(operation_type, count)

def can_perform_firebase_operation(operation_type: str, count: int = 1, bot_id: str = None) -> bool:
    """检查是否可以执行Firebase操作"""
    monitor = get_global_quota_monitor(bot_id)
    if not monitor:
        return True
    
    return monitor.can_perform_operation(operation_type, count)

async def start_quota_monitoring(bot_id: str = None):
    """启动配额监控"""
    monitor = get_global_quota_monitor(bot_id)
    if not monitor:
        return False
    
    return await monitor.start_monitoring()

async def stop_quota_monitoring(bot_id: str = None):
    """停止配额监控"""
    monitor = get_global_quota_monitor(bot_id)
    if monitor:
        await monitor.stop_monitoring()

def get_quota_stats(bot_id: str = None) -> Dict[str, Any]:
    """获取配额统计信息"""
    monitor = get_global_quota_monitor(bot_id)
    if not monitor:
        return {}
    
    return monitor.get_usage_stats()

__all__ = [
    "FirebaseQuotaMonitor",
    "get_global_quota_monitor",
    "set_global_quota_monitor",
    "record_firebase_operation",
    "can_perform_firebase_operation",
    "start_quota_monitoring",
    "stop_quota_monitoring",
    "get_quota_stats"
]
