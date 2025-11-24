#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发任务管理器
负责大批量多任务的并发控制、资源管理和负载均衡
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass
from enum import Enum
import threading
from collections import defaultdict, deque
import psutil
import gc

from task_state_manager import get_global_task_state_manager, TaskStatus, TaskProgress

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class TaskResource:
    """任务资源需求"""
    memory_mb: int = 100  # 内存需求（MB）
    cpu_percent: float = 10.0  # CPU需求（百分比）
    network_bandwidth: int = 1  # 网络带宽需求（相对值）
    max_concurrent: int = 1  # 最大并发数

@dataclass
class TaskSlot:
    """任务槽位"""
    task_id: str
    priority: TaskPriority
    resource: TaskResource
    created_at: float
    started_at: Optional[float] = None
    estimated_duration: float = 0.0  # 预计持续时间（秒）

class ConcurrentTaskManager:
    """并发任务管理器"""
    
    def __init__(self, bot_id: str = "default_bot"):
        """初始化并发任务管理器"""
        self.bot_id = bot_id
        self.task_state_manager = get_global_task_state_manager(bot_id)
        
        # 任务队列（按优先级排序）
        self.task_queues = {
            TaskPriority.URGENT: deque(),
            TaskPriority.HIGH: deque(),
            TaskPriority.NORMAL: deque(),
            TaskPriority.LOW: deque()
        }
        
        # 运行中的任务
        self.running_tasks: Dict[str, TaskSlot] = {}
        self.running_tasks_lock = threading.RLock()
        
        # 资源限制
        self.max_memory_mb = psutil.virtual_memory().total // (1024 * 1024) * 0.8  # 80%系统内存
        self.max_cpu_percent = 80.0  # 80%CPU使用率
        self.max_concurrent_tasks = 10  # 最大并发任务数
        self.max_user_tasks = 5  # 每用户最大并发任务数
        
        # 用户任务计数
        self.user_task_counts: Dict[str, int] = defaultdict(int)
        self.user_task_counts_lock = threading.RLock()
        
        # 任务调度器
        self.scheduler_task = None
        self.scheduler_running = False
        self.scheduler_interval = 5.0  # 调度间隔（秒）
        
        # 统计信息
        self.stats = {
            'total_queued': 0,
            'total_started': 0,
            'total_completed': 0,
            'total_failed': 0,
            'current_memory_usage': 0,
            'current_cpu_usage': 0,
            'queue_lengths': {priority.value: 0 for priority in TaskPriority}
        }
        
        # 回调函数
        self.task_start_callback: Optional[Callable] = None
        self.task_complete_callback: Optional[Callable] = None
        self.task_fail_callback: Optional[Callable] = None
        
        logger.info(f"✅ 并发任务管理器初始化完成 (Bot: {bot_id})")
    
    async def start_scheduler(self):
        """启动任务调度器"""
        if self.scheduler_running:
            return
        
        self.scheduler_running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ 任务调度器已启动")
    
    async def stop_scheduler(self):
        """停止任务调度器"""
        if not self.scheduler_running:
            return
        
        self.scheduler_running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 任务调度器已停止")
    
    async def _scheduler_loop(self):
        """任务调度循环"""
        while self.scheduler_running:
            try:
                await self._schedule_tasks()
                await asyncio.sleep(self.scheduler_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"任务调度器异常: {e}")
                await asyncio.sleep(1.0)
    
    async def _schedule_tasks(self):
        """调度任务"""
        try:
            # 更新系统资源使用情况
            self._update_system_stats()
            
            # 检查是否有可用的资源来启动新任务
            while self._can_start_new_task():
                # 从队列中获取下一个任务
                task_slot = self._get_next_task()
                if not task_slot:
                    break
                
                # 启动任务
                await self._start_task(task_slot)
            
            # 清理已完成的任务
            await self._cleanup_completed_tasks()
            
        except Exception as e:
            logger.error(f"调度任务失败: {e}")
    
    def _can_start_new_task(self) -> bool:
        """检查是否可以启动新任务"""
        # 检查最大并发任务数
        if len(self.running_tasks) >= self.max_concurrent_tasks:
            return False
        
        # 检查系统资源
        if self.stats['current_memory_usage'] > self.max_memory_mb:
            return False
        
        if self.stats['current_cpu_usage'] > self.max_cpu_percent:
            return False
        
        return True
    
    def _get_next_task(self) -> Optional[TaskSlot]:
        """获取下一个要执行的任务"""
        # 按优先级顺序检查队列
        for priority in [TaskPriority.URGENT, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            if self.task_queues[priority]:
                task_slot = self.task_queues[priority].popleft()
                
                # 检查用户任务限制
                user_id = self._get_task_user_id(task_slot.task_id)
                if user_id and self.user_task_counts[user_id] >= self.max_user_tasks:
                    # 放回队列末尾
                    self.task_queues[priority].append(task_slot)
                    continue
                
                return task_slot
        
        return None
    
    async def _start_task(self, task_slot: TaskSlot):
        """启动任务"""
        try:
            task_slot.started_at = time.time()
            
            with self.running_tasks_lock:
                self.running_tasks[task_slot.task_id] = task_slot
            
            # 更新用户任务计数
            user_id = self._get_task_user_id(task_slot.task_id)
            if user_id:
                with self.user_task_counts_lock:
                    self.user_task_counts[user_id] += 1
            
            # 更新统计信息
            self.stats['total_started'] += 1
            
            # 调用启动回调
            if self.task_start_callback:
                try:
                    await self.task_start_callback(task_slot.task_id)
                except Exception as e:
                    logger.error(f"任务启动回调失败 {task_slot.task_id}: {e}")
            
            logger.info(f"✅ 任务已启动: {task_slot.task_id} (优先级: {task_slot.priority.name})")
            
        except Exception as e:
            logger.error(f"启动任务失败 {task_slot.task_id}: {e}")
    
    async def _cleanup_completed_tasks(self):
        """清理已完成的任务"""
        try:
            completed_tasks = []
            
            with self.running_tasks_lock:
                for task_id, task_slot in list(self.running_tasks.items()):
                    # 检查任务状态
                    task_progress = await self.task_state_manager.get_task(task_id)
                    if not task_progress:
                        # 任务不存在，清理
                        completed_tasks.append(task_id)
                        continue
                    
                    if task_progress.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                        completed_tasks.append(task_id)
            
            # 清理已完成的任务
            for task_id in completed_tasks:
                await self._remove_task(task_id)
            
        except Exception as e:
            logger.error(f"清理完成任务失败: {e}")
    
    async def _remove_task(self, task_id: str):
        """移除任务"""
        try:
            with self.running_tasks_lock:
                if task_id in self.running_tasks:
                    task_slot = self.running_tasks[task_id]
                    del self.running_tasks[task_id]
                    
                    # 更新用户任务计数
                    user_id = self._get_task_user_id(task_id)
                    if user_id:
                        with self.user_task_counts_lock:
                            self.user_task_counts[user_id] = max(0, self.user_task_counts[user_id] - 1)
                    
                    # 更新统计信息
                    task_progress = await self.task_state_manager.get_task(task_id)
                    if task_progress:
                        if task_progress.status == TaskStatus.COMPLETED:
                            self.stats['total_completed'] += 1
                        elif task_progress.status == TaskStatus.FAILED:
                            self.stats['total_failed'] += 1
                    
                    logger.debug(f"任务已移除: {task_id}")
            
        except Exception as e:
            logger.error(f"移除任务失败 {task_id}: {e}")
    
    def _get_task_user_id(self, task_id: str) -> Optional[str]:
        """获取任务所属用户ID"""
        # 这里需要从任务状态管理器中获取用户ID
        # 简化实现，实际应该从数据库查询
        return None
    
    def _update_system_stats(self):
        """更新系统统计信息"""
        try:
            # 更新内存使用情况
            memory_info = psutil.virtual_memory()
            self.stats['current_memory_usage'] = memory_info.used // (1024 * 1024)
            
            # 更新CPU使用情况
            self.stats['current_cpu_usage'] = psutil.cpu_percent(interval=0.1)
            
            # 更新队列长度
            for priority in TaskPriority:
                self.stats['queue_lengths'][priority.value] = len(self.task_queues[priority])
            
        except Exception as e:
            logger.error(f"更新系统统计信息失败: {e}")
    
    async def queue_task(self, task_id: str, user_id: str, priority: TaskPriority = TaskPriority.NORMAL,
                        resource: TaskResource = None, estimated_duration: float = 0.0) -> bool:
        """将任务加入队列"""
        try:
            if resource is None:
                resource = TaskResource()
            
            task_slot = TaskSlot(
                task_id=task_id,
                priority=priority,
                resource=resource,
                created_at=time.time(),
                estimated_duration=estimated_duration
            )
            
            # 添加到对应优先级的队列
            self.task_queues[priority].append(task_slot)
            self.stats['total_queued'] += 1
            
            logger.info(f"任务已加入队列: {task_id} (优先级: {priority.name})")
            return True
            
        except Exception as e:
            logger.error(f"加入任务队列失败 {task_id}: {e}")
            return False
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            # 从队列中移除
            for priority in TaskPriority:
                queue = self.task_queues[priority]
                for i, task_slot in enumerate(queue):
                    if task_slot.task_id == task_id:
                        del queue[i]
                        logger.info(f"任务已从队列中移除: {task_id}")
                        return True
            
            # 从运行中任务移除
            with self.running_tasks_lock:
                if task_id in self.running_tasks:
                    await self._remove_task(task_id)
                    logger.info(f"运行中任务已取消: {task_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"取消任务失败 {task_id}: {e}")
            return False
    
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        try:
            # 更新任务状态
            await self.task_state_manager.update_task_progress(
                task_id,
                status=TaskStatus.PAUSED
            )
            
            logger.info(f"任务已暂停: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"暂停任务失败 {task_id}: {e}")
            return False
    
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        try:
            # 更新任务状态
            await self.task_state_manager.update_task_progress(
                task_id,
                status=TaskStatus.RUNNING
            )
            
            logger.info(f"任务已恢复: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"恢复任务失败 {task_id}: {e}")
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        with self.running_tasks_lock:
            return {
                'queue_lengths': {
                    priority.name: len(queue) 
                    for priority, queue in self.task_queues.items()
                },
                'running_tasks': len(self.running_tasks),
                'user_task_counts': dict(self.user_task_counts),
                'system_stats': self.stats.copy(),
                'max_concurrent_tasks': self.max_concurrent_tasks,
                'max_user_tasks': self.max_user_tasks,
                'max_memory_mb': self.max_memory_mb,
                'max_cpu_percent': self.max_cpu_percent
            }
    
    def set_callbacks(self, start_callback: Callable = None, complete_callback: Callable = None, 
                     fail_callback: Callable = None):
        """设置回调函数"""
        self.task_start_callback = start_callback
        self.task_complete_callback = complete_callback
        self.task_fail_callback = fail_callback
    
    async def optimize_memory(self):
        """优化内存使用"""
        try:
            # 强制垃圾回收
            gc.collect()
            
            # 如果内存使用过高，暂停低优先级任务
            if self.stats['current_memory_usage'] > self.max_memory_mb * 0.9:
                logger.warning("内存使用过高，暂停低优先级任务")
                
                # 暂停低优先级任务
                for task_id, task_slot in self.running_tasks.items():
                    if task_slot.priority in [TaskPriority.LOW, TaskPriority.NORMAL]:
                        await self.pause_task(task_id)
            
        except Exception as e:
            logger.error(f"优化内存失败: {e}")
    
    async def get_task_priority(self, task_id: str) -> Optional[TaskPriority]:
        """获取任务优先级"""
        # 从队列中查找
        for priority in TaskPriority:
            for task_slot in self.task_queues[priority]:
                if task_slot.task_id == task_id:
                    return priority
        
        # 从运行中任务查找
        with self.running_tasks_lock:
            if task_id in self.running_tasks:
                return self.running_tasks[task_id].priority
        
        return None

# 全局并发任务管理器
_global_concurrent_task_manager = None

def get_global_concurrent_task_manager(bot_id: str = "default_bot") -> ConcurrentTaskManager:
    """获取全局并发任务管理器"""
    global _global_concurrent_task_manager
    
    if _global_concurrent_task_manager is None:
        _global_concurrent_task_manager = ConcurrentTaskManager(bot_id)
    
    return _global_concurrent_task_manager

async def start_concurrent_task_manager(bot_id: str = "default_bot"):
    """启动并发任务管理器"""
    manager = get_global_concurrent_task_manager(bot_id)
    await manager.start_scheduler()
    return manager

async def stop_concurrent_task_manager(bot_id: str = "default_bot"):
    """停止并发任务管理器"""
    manager = get_global_concurrent_task_manager(bot_id)
    await manager.stop_scheduler()

__all__ = [
    "ConcurrentTaskManager",
    "TaskPriority",
    "TaskResource",
    "TaskSlot",
    "get_global_concurrent_task_manager",
    "start_concurrent_task_manager",
    "stop_concurrent_task_manager"
]
