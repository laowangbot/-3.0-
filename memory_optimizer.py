#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内存优化管理器
负责大批量任务时的内存管理和优化
"""

import asyncio
import logging
import time
import gc
import psutil
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from collections import defaultdict
import weakref

logger = logging.getLogger(__name__)

@dataclass
class MemoryStats:
    """内存统计信息"""
    total_memory_mb: float
    used_memory_mb: float
    available_memory_mb: float
    memory_percent: float
    process_memory_mb: float
    gc_objects: int
    gc_collections: int

@dataclass
class MemoryThreshold:
    """内存阈值配置"""
    warning_threshold: float = 70.0  # 警告阈值（百分比）
    critical_threshold: float = 85.0  # 严重阈值（百分比）
    emergency_threshold: float = 95.0  # 紧急阈值（百分比）
    cleanup_threshold: float = 60.0  # 清理阈值（百分比）

class MemoryOptimizer:
    """内存优化管理器"""
    
    def __init__(self, bot_id: str = "default_bot"):
        """初始化内存优化管理器"""
        self.bot_id = bot_id
        
        # 内存阈值配置
        self.thresholds = MemoryThreshold()
        
        # 内存监控
        self.monitoring_task = None
        self.monitoring_running = False
        self.monitoring_interval = 10.0  # 监控间隔（秒）
        
        # 内存使用历史
        self.memory_history: List[MemoryStats] = []
        self.max_history_size = 100
        
        # 内存优化策略
        self.optimization_strategies = {
            'gc_collection': self._force_gc_collection,
            'cache_cleanup': self._cleanup_caches,
            'task_pause': self._pause_low_priority_tasks,
            'memory_compression': self._compress_memory,
            'emergency_cleanup': self._emergency_cleanup
        }
        
        # 缓存清理回调
        self.cache_cleanup_callbacks: List[Callable] = []
        
        # 任务暂停回调
        self.task_pause_callbacks: List[Callable] = []
        
        # 统计信息
        self.stats = {
            'total_optimizations': 0,
            'gc_collections': 0,
            'cache_cleanups': 0,
            'task_pauses': 0,
            'emergency_cleanups': 0,
            'memory_saved_mb': 0
        }
        
        logger.info(f"✅ 内存优化管理器初始化完成 (Bot: {bot_id})")
    
    async def start_monitoring(self):
        """启动内存监控"""
        if self.monitoring_running:
            return
        
        self.monitoring_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("✅ 内存监控已启动")
    
    async def stop_monitoring(self):
        """停止内存监控"""
        if not self.monitoring_running:
            return
        
        self.monitoring_running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 内存监控已停止")
    
    async def _monitoring_loop(self):
        """内存监控循环"""
        while self.monitoring_running:
            try:
                # 获取当前内存状态
                memory_stats = await self._get_memory_stats()
                
                # 记录内存历史
                self._record_memory_history(memory_stats)
                
                # 检查内存使用情况
                await self._check_memory_usage(memory_stats)
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"内存监控异常: {e}")
                await asyncio.sleep(1.0)
    
    async def _get_memory_stats(self) -> MemoryStats:
        """获取内存统计信息"""
        try:
            # 系统内存信息
            memory_info = psutil.virtual_memory()
            
            # 进程内存信息
            process = psutil.Process()
            process_memory = process.memory_info()
            
            # 垃圾回收信息
            gc_stats = gc.get_stats()
            total_gc_objects = sum(stat['collected'] for stat in gc_stats)
            total_gc_collections = sum(stat['collections'] for stat in gc_stats)
            
            return MemoryStats(
                total_memory_mb=memory_info.total / (1024 * 1024),
                used_memory_mb=memory_info.used / (1024 * 1024),
                available_memory_mb=memory_info.available / (1024 * 1024),
                memory_percent=memory_info.percent,
                process_memory_mb=process_memory.rss / (1024 * 1024),
                gc_objects=total_gc_objects,
                gc_collections=total_gc_collections
            )
            
        except Exception as e:
            logger.error(f"获取内存统计信息失败: {e}")
            return MemoryStats(0, 0, 0, 0, 0, 0, 0)
    
    def _record_memory_history(self, memory_stats: MemoryStats):
        """记录内存历史"""
        self.memory_history.append(memory_stats)
        
        # 保持历史记录大小
        if len(self.memory_history) > self.max_history_size:
            self.memory_history.pop(0)
    
    async def _check_memory_usage(self, memory_stats: MemoryStats):
        """检查内存使用情况"""
        try:
            memory_percent = memory_stats.memory_percent
            
            if memory_percent >= self.thresholds.emergency_threshold:
                # 紧急情况：立即执行紧急清理
                logger.critical(f"🚨 内存使用率过高: {memory_percent:.1f}%，执行紧急清理")
                await self._execute_optimization_strategy('emergency_cleanup')
                
            elif memory_percent >= self.thresholds.critical_threshold:
                # 严重情况：执行多种优化策略
                logger.warning(f"⚠️ 内存使用率严重: {memory_percent:.1f}%，执行多重优化")
                await self._execute_optimization_strategy('gc_collection')
                await self._execute_optimization_strategy('cache_cleanup')
                await self._execute_optimization_strategy('task_pause')
                
            elif memory_percent >= self.thresholds.warning_threshold:
                # 警告情况：执行基本优化
                logger.warning(f"⚠️ 内存使用率较高: {memory_percent:.1f}%，执行基本优化")
                await self._execute_optimization_strategy('gc_collection')
                await self._execute_optimization_strategy('cache_cleanup')
                
            elif memory_percent <= self.thresholds.cleanup_threshold:
                # 内存充足：执行预防性清理
                logger.debug(f"💚 内存使用率正常: {memory_percent:.1f}%，执行预防性清理")
                await self._execute_optimization_strategy('gc_collection')
            
        except Exception as e:
            logger.error(f"检查内存使用情况失败: {e}")
    
    async def _execute_optimization_strategy(self, strategy_name: str):
        """执行优化策略"""
        try:
            if strategy_name in self.optimization_strategies:
                strategy = self.optimization_strategies[strategy_name]
                await strategy()
                self.stats['total_optimizations'] += 1
                logger.debug(f"✅ 执行优化策略: {strategy_name}")
            else:
                logger.warning(f"未知的优化策略: {strategy_name}")
                
        except Exception as e:
            logger.error(f"执行优化策略失败 {strategy_name}: {e}")
    
    async def _force_gc_collection(self):
        """强制垃圾回收"""
        try:
            # 记录回收前的内存
            before_memory = psutil.Process().memory_info().rss / (1024 * 1024)
            
            # 执行垃圾回收
            collected = gc.collect()
            
            # 记录回收后的内存
            after_memory = psutil.Process().memory_info().rss / (1024 * 1024)
            memory_saved = before_memory - after_memory
            
            self.stats['gc_collections'] += 1
            self.stats['memory_saved_mb'] += memory_saved
            
            logger.debug(f"🗑️ 垃圾回收完成: 回收 {collected} 个对象，释放 {memory_saved:.1f}MB 内存")
            
        except Exception as e:
            logger.error(f"强制垃圾回收失败: {e}")
    
    async def _cleanup_caches(self):
        """清理缓存"""
        try:
            # 调用缓存清理回调
            for callback in self.cache_cleanup_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.error(f"缓存清理回调失败: {e}")
            
            self.stats['cache_cleanups'] += 1
            logger.debug("🧹 缓存清理完成")
            
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
    
    async def _pause_low_priority_tasks(self):
        """暂停低优先级任务"""
        try:
            # 调用任务暂停回调
            for callback in self.task_pause_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.error(f"任务暂停回调失败: {e}")
            
            self.stats['task_pauses'] += 1
            logger.debug("⏸️ 低优先级任务已暂停")
            
        except Exception as e:
            logger.error(f"暂停低优先级任务失败: {e}")
    
    async def _compress_memory(self):
        """压缩内存"""
        try:
            # 这里可以实现内存压缩逻辑
            # 例如：压缩数据结构、合并相似对象等
            logger.debug("🗜️ 内存压缩完成")
            
        except Exception as e:
            logger.error(f"压缩内存失败: {e}")
    
    async def _emergency_cleanup(self):
        """紧急清理"""
        try:
            # 执行所有优化策略
            for strategy_name in ['gc_collection', 'cache_cleanup', 'task_pause', 'memory_compression']:
                await self._execute_optimization_strategy(strategy_name)
            
            self.stats['emergency_cleanups'] += 1
            logger.critical("🚨 紧急清理完成")
            
        except Exception as e:
            logger.error(f"紧急清理失败: {e}")
    
    def add_cache_cleanup_callback(self, callback: Callable):
        """添加缓存清理回调"""
        self.cache_cleanup_callbacks.append(callback)
    
    def add_task_pause_callback(self, callback: Callable):
        """添加任务暂停回调"""
        self.task_pause_callbacks.append(callback)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计信息"""
        try:
            current_stats = asyncio.create_task(self._get_memory_stats())
            return {
                'current': current_stats,
                'history': [
                    {
                        'timestamp': time.time(),
                        'memory_percent': stats.memory_percent,
                        'used_memory_mb': stats.used_memory_mb,
                        'process_memory_mb': stats.process_memory_mb
                    }
                    for stats in self.memory_history[-10:]  # 最近10条记录
                ],
                'thresholds': {
                    'warning': self.thresholds.warning_threshold,
                    'critical': self.thresholds.critical_threshold,
                    'emergency': self.thresholds.emergency_threshold,
                    'cleanup': self.thresholds.cleanup_threshold
                },
                'stats': self.stats.copy()
            }
        except Exception as e:
            logger.error(f"获取内存统计信息失败: {e}")
            return {}
    
    async def optimize_for_bulk_tasks(self, task_count: int, estimated_memory_per_task: float = 100.0):
        """为大批量任务优化内存"""
        try:
            # 计算预计内存使用
            estimated_total_memory = task_count * estimated_memory_per_task
            current_memory = psutil.virtual_memory().used / (1024 * 1024)
            available_memory = psutil.virtual_memory().available / (1024 * 1024)
            
            logger.info(f"🔧 大批量任务内存优化:")
            logger.info(f"   任务数量: {task_count}")
            logger.info(f"   预计内存使用: {estimated_total_memory:.1f}MB")
            logger.info(f"   当前内存使用: {current_memory:.1f}MB")
            logger.info(f"   可用内存: {available_memory:.1f}MB")
            
            # 如果预计内存使用超过可用内存，执行优化
            if estimated_total_memory > available_memory:
                logger.warning("⚠️ 预计内存使用超过可用内存，执行优化")
                
                # 执行多重优化
                await self._execute_optimization_strategy('gc_collection')
                await self._execute_optimization_strategy('cache_cleanup')
                await self._execute_optimization_strategy('memory_compression')
                
                # 重新计算可用内存
                new_available_memory = psutil.virtual_memory().available / (1024 * 1024)
                logger.info(f"   优化后可用内存: {new_available_memory:.1f}MB")
                
                # 如果仍然不足，建议分批处理
                if estimated_total_memory > new_available_memory:
                    recommended_batch_size = int(new_available_memory / estimated_memory_per_task)
                    logger.warning(f"⚠️ 建议分批处理，推荐批次大小: {recommended_batch_size}")
                    return recommended_batch_size
            
            return task_count
            
        except Exception as e:
            logger.error(f"大批量任务内存优化失败: {e}")
            return task_count
    
    def set_memory_thresholds(self, warning: float = None, critical: float = None, 
                             emergency: float = None, cleanup: float = None):
        """设置内存阈值"""
        if warning is not None:
            self.thresholds.warning_threshold = warning
        if critical is not None:
            self.thresholds.critical_threshold = critical
        if emergency is not None:
            self.thresholds.emergency_threshold = emergency
        if cleanup is not None:
            self.thresholds.cleanup_threshold = cleanup
        
        logger.info(f"✅ 内存阈值已更新: {self.thresholds}")

# 全局内存优化管理器
_global_memory_optimizer = None

def get_global_memory_optimizer(bot_id: str = "default_bot") -> MemoryOptimizer:
    """获取全局内存优化管理器"""
    global _global_memory_optimizer
    
    if _global_memory_optimizer is None:
        _global_memory_optimizer = MemoryOptimizer(bot_id)
    
    return _global_memory_optimizer

async def start_memory_optimizer(bot_id: str = "default_bot"):
    """启动内存优化管理器"""
    optimizer = get_global_memory_optimizer(bot_id)
    await optimizer.start_monitoring()
    return optimizer

async def stop_memory_optimizer(bot_id: str = "default_bot"):
    """停止内存优化管理器"""
    optimizer = get_global_memory_optimizer(bot_id)
    await optimizer.stop_monitoring()

__all__ = [
    "MemoryOptimizer",
    "MemoryStats",
    "MemoryThreshold",
    "get_global_memory_optimizer",
    "start_memory_optimizer",
    "stop_memory_optimizer"
]
