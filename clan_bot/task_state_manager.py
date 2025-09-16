#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务状态管理器
负责大批量多任务的状态持久化、恢复和同步
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor

from data_manager import get_data_manager
from config import get_config

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskProgress:
    """任务进度信息"""
    task_id: str
    user_id: str
    status: TaskStatus
    progress: float  # 0.0 - 100.0
    current_message_id: int
    total_messages: int
    processed_messages: int
    failed_messages: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    last_processed_message_id: Optional[int] = None
    resume_from_id: Optional[int] = None
    is_resumed: bool = False
    error_message: Optional[str] = None
    stats: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = {
                'total_messages': 0,
                'processed_messages': 0,
                'failed_messages': 0,
                'skipped_messages': 0,
                'media_messages': 0,
                'text_messages': 0,
                'filtered_messages': 0,
                'media_groups': 0
            }

class TaskStateManager:
    """任务状态管理器"""
    
    def __init__(self, bot_id: str = "default_bot"):
        """初始化任务状态管理器"""
        self.bot_id = bot_id
        self.data_manager = get_data_manager(bot_id)
        
        # 内存中的任务状态缓存
        self._task_cache: Dict[str, TaskProgress] = {}
        self._cache_lock = threading.RLock()
        
        # 持久化配置
        self.config = get_config()
        self.save_interval = self.config.get('task_save_interval', 30)  # 30秒保存一次
        self.batch_save_size = self.config.get('task_batch_save_size', 10)  # 批量保存大小
        
        # 自动保存任务
        self._auto_save_task = None
        self._auto_save_running = False
        self._pending_saves: Set[str] = set()
        self._pending_saves_lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            'total_tasks': 0,
            'active_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'saves_performed': 0,
            'last_save_time': None
        }
        
        logger.info(f"✅ 任务状态管理器初始化完成 (Bot: {bot_id})")
    
    async def start_auto_save(self):
        """启动自动保存任务"""
        if self._auto_save_running:
            return
        
        self._auto_save_running = True
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())
        logger.info("✅ 任务状态自动保存已启动")
    
    async def stop_auto_save(self):
        """停止自动保存任务"""
        if not self._auto_save_running:
            return
        
        self._auto_save_running = False
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass
        
        # 执行最后一次保存
        await self._save_all_pending_tasks()
        logger.info("✅ 任务状态自动保存已停止")
    
    async def _auto_save_loop(self):
        """自动保存循环"""
        while self._auto_save_running:
            try:
                await asyncio.sleep(self.save_interval)
                await self._save_all_pending_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动保存任务状态失败: {e}")
    
    async def create_task(self, task_id: str, user_id: str, source_chat_id: str, 
                         target_chat_id: str, start_id: Optional[int] = None, 
                         end_id: Optional[int] = None, config: Optional[Dict[str, Any]] = None) -> TaskProgress:
        """创建新任务"""
        try:
            # 创建任务进度对象
            task_progress = TaskProgress(
                task_id=task_id,
                user_id=user_id,
                status=TaskStatus.PENDING,
                progress=0.0,
                current_message_id=start_id or 0,
                total_messages=0,
                processed_messages=0,
                failed_messages=0,
                start_time=datetime.now(),
                stats={
                    'total_messages': 0,
                    'processed_messages': 0,
                    'failed_messages': 0,
                    'skipped_messages': 0,
                    'media_messages': 0,
                    'text_messages': 0,
                    'filtered_messages': 0,
                    'media_groups': 0,
                    'source_chat_id': source_chat_id,
                    'target_chat_id': target_chat_id,
                    'start_id': start_id,
                    'end_id': end_id,
                    'config': config or {}
                }
            )
            
            # 添加到缓存
            with self._cache_lock:
                self._task_cache[task_id] = task_progress
                self.stats['total_tasks'] += 1
                self.stats['active_tasks'] += 1
            
            # 立即保存到数据库
            await self._save_task_to_db(task_progress)
            
            logger.info(f"✅ 任务创建成功: {task_id} (用户: {user_id})")
            return task_progress
            
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            raise
    
    async def get_task(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务状态"""
        try:
            # 先从缓存获取
            with self._cache_lock:
                if task_id in self._task_cache:
                    return self._task_cache[task_id]
            
            # 从数据库加载
            task_progress = await self._load_task_from_db(task_id)
            if task_progress:
                with self._cache_lock:
                    self._task_cache[task_id] = task_progress
            
            return task_progress
            
        except Exception as e:
            logger.error(f"获取任务状态失败 {task_id}: {e}")
            return None
    
    async def update_task_progress(self, task_id: str, **updates) -> bool:
        """更新任务进度"""
        try:
            with self._cache_lock:
                if task_id not in self._task_cache:
                    logger.warning(f"任务不存在于缓存中: {task_id}")
                    # 尝试从数据库加载任务
                    task = await self._load_task_from_db(task_id)
                    if task:
                        self._task_cache[task_id] = task
                        logger.info(f"✅ 从数据库加载任务到缓存: {task_id}")
                    else:
                        logger.error(f"❌ 无法从数据库加载任务: {task_id}")
                        return False
                
                task = self._task_cache[task_id]
                
                # 更新字段
                for key, value in updates.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                
                # 更新统计信息
                if task.status == TaskStatus.RUNNING:
                    self.stats['active_tasks'] = len([t for t in self._task_cache.values() 
                                                    if t.status == TaskStatus.RUNNING])
                elif task.status == TaskStatus.COMPLETED:
                    self.stats['completed_tasks'] += 1
                    self.stats['active_tasks'] = len([t for t in self._task_cache.values() 
                                                    if t.status == TaskStatus.RUNNING])
                elif task.status == TaskStatus.FAILED:
                    self.stats['failed_tasks'] += 1
                    self.stats['active_tasks'] = len([t for t in self._task_cache.values() 
                                                    if t.status == TaskStatus.RUNNING])
                
                # 标记为待保存
                with self._pending_saves_lock:
                    self._pending_saves.add(task_id)
            
            logger.debug(f"任务进度已更新: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新任务进度失败 {task_id}: {e}")
            return False
    
    async def save_task_progress(self, task_id: str) -> bool:
        """立即保存任务进度"""
        try:
            with self._cache_lock:
                if task_id not in self._task_cache:
                    return False
                
                task = self._task_cache[task_id]
            
            # 保存到数据库
            success = await self._save_task_to_db(task)
            if success:
                with self._pending_saves_lock:
                    self._pending_saves.discard(task_id)
                self.stats['saves_performed'] += 1
                self.stats['last_save_time'] = datetime.now()
            
            return success
            
        except Exception as e:
            logger.error(f"保存任务进度失败 {task_id}: {e}")
            return False
    
    async def _save_all_pending_tasks(self):
        """保存所有待保存的任务"""
        try:
            with self._pending_saves_lock:
                pending_tasks = list(self._pending_saves)
            
            if not pending_tasks:
                return
            
            # 批量保存
            batch_size = self.batch_save_size
            for i in range(0, len(pending_tasks), batch_size):
                batch = pending_tasks[i:i + batch_size]
                await self._save_task_batch(batch)
            
            logger.debug(f"批量保存完成: {len(pending_tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"批量保存任务失败: {e}")
    
    async def _save_task_batch(self, task_ids: List[str]):
        """批量保存任务"""
        try:
            tasks_to_save = []
            with self._cache_lock:
                for task_id in task_ids:
                    if task_id in self._task_cache:
                        tasks_to_save.append(self._task_cache[task_id])
            
            if not tasks_to_save:
                return
            
            # 按用户分组保存
            user_tasks = {}
            for task in tasks_to_save:
                user_id = task.user_id
                if user_id not in user_tasks:
                    user_tasks[user_id] = []
                user_tasks[user_id].append(task)
            
            # 为每个用户保存任务
            for user_id, tasks in user_tasks.items():
                await self._save_user_tasks(user_id, tasks)
            
            # 清除待保存标记
            with self._pending_saves_lock:
                for task_id in task_ids:
                    self._pending_saves.discard(task_id)
            
        except Exception as e:
            logger.error(f"批量保存任务失败: {e}")
    
    async def _save_user_tasks(self, user_id: str, tasks: List[TaskProgress]):
        """保存用户的任务"""
        try:
            # 获取用户现有任务
            user_config = await self.data_manager.get_user_config(user_id)
            user_tasks = user_config.get('active_tasks', {})
            
            # 更新任务状态
            for task in tasks:
                user_tasks[task.task_id] = self._task_progress_to_dict(task)
            
            # 保存到数据库
            user_config['active_tasks'] = user_tasks
            user_config['updated_at'] = datetime.now().isoformat()
            
            success = await self.data_manager.save_user_config(user_id, user_config)
            if success:
                logger.debug(f"用户任务保存成功: {user_id} ({len(tasks)} 个任务)")
            else:
                logger.error(f"用户任务保存失败: {user_id}")
            
        except Exception as e:
            logger.error(f"保存用户任务失败 {user_id}: {e}")
    
    async def _save_task_to_db(self, task: TaskProgress) -> bool:
        """保存单个任务到数据库"""
        try:
            user_config = await self.data_manager.get_user_config(task.user_id)
            user_tasks = user_config.get('active_tasks', {})
            
            # 更新任务状态
            user_tasks[task.task_id] = self._task_progress_to_dict(task)
            
            # 保存到数据库
            user_config['active_tasks'] = user_tasks
            user_config['updated_at'] = datetime.now().isoformat()
            
            success = await self.data_manager.save_user_config(task.user_id, user_config)
            return success
            
        except Exception as e:
            logger.error(f"保存任务到数据库失败 {task.task_id}: {e}")
            return False
    
    async def _load_task_from_db(self, task_id: str) -> Optional[TaskProgress]:
        """从数据库加载任务"""
        try:
            # 这里需要实现从数据库加载任务的逻辑
            # 由于任务可能属于不同用户，需要搜索所有用户
            # 这是一个简化的实现，实际可能需要更复杂的查询
            
            # 获取所有用户
            all_user_ids = await self.data_manager.get_all_user_ids()
            
            for user_id in all_user_ids:
                try:
                    user_config = await self.data_manager.get_user_config(user_id)
                    if not user_config:
                        continue
                        
                    user_tasks = user_config.get('active_tasks', {})
                    
                    if task_id in user_tasks:
                        task_dict = user_tasks[task_id]
                        task_progress = self._dict_to_task_progress(task_dict)
                        if task_progress:
                            logger.info(f"✅ 从数据库成功加载任务 {task_id} (用户: {user_id})")
                            return task_progress
                except Exception as e:
                    logger.warning(f"搜索用户 {user_id} 的任务失败: {e}")
                    continue
            
            logger.warning(f"未找到任务 {task_id} 在数据库中")
            return None
            
        except Exception as e:
            logger.error(f"从数据库加载任务失败 {task_id}: {e}")
            return None
    
    def _task_progress_to_dict(self, task: TaskProgress) -> Dict[str, Any]:
        """将任务进度转换为字典"""
        return {
            'task_id': task.task_id,
            'user_id': task.user_id,
            'status': task.status.value,
            'progress': task.progress,
            'current_message_id': task.current_message_id,
            'total_messages': task.total_messages,
            'processed_messages': task.processed_messages,
            'failed_messages': task.failed_messages,
            'start_time': task.start_time.isoformat() if task.start_time else None,
            'end_time': task.end_time.isoformat() if task.end_time else None,
            'last_processed_message_id': task.last_processed_message_id,
            'resume_from_id': task.resume_from_id,
            'is_resumed': task.is_resumed,
            'error_message': task.error_message,
            'stats': task.stats
        }
    
    def _dict_to_task_progress(self, task_dict: Dict[str, Any]) -> TaskProgress:
        """将字典转换为任务进度"""
        return TaskProgress(
            task_id=task_dict['task_id'],
            user_id=task_dict['user_id'],
            status=TaskStatus(task_dict['status']),
            progress=task_dict['progress'],
            current_message_id=task_dict['current_message_id'],
            total_messages=task_dict['total_messages'],
            processed_messages=task_dict['processed_messages'],
            failed_messages=task_dict['failed_messages'],
            start_time=datetime.fromisoformat(task_dict['start_time']) if task_dict.get('start_time') else None,
            end_time=datetime.fromisoformat(task_dict['end_time']) if task_dict.get('end_time') else None,
            last_processed_message_id=task_dict.get('last_processed_message_id'),
            resume_from_id=task_dict.get('resume_from_id'),
            is_resumed=task_dict.get('is_resumed', False),
            error_message=task_dict.get('error_message'),
            stats=task_dict.get('stats', {})
        )
    
    async def get_user_tasks(self, user_id: str) -> List[TaskProgress]:
        """获取用户的所有任务"""
        try:
            user_config = await self.data_manager.get_user_config(user_id)
            user_tasks = user_config.get('active_tasks', {})
            
            tasks = []
            for task_id, task_dict in user_tasks.items():
                task = self._dict_to_task_progress(task_dict)
                tasks.append(task)
                
                # 更新缓存
                with self._cache_lock:
                    self._task_cache[task_id] = task
            
            return tasks
            
        except Exception as e:
            logger.error(f"获取用户任务失败 {user_id}: {e}")
            return []
    
    async def cleanup_completed_tasks(self, user_id: str, max_age_hours: int = 24):
        """清理已完成的任务"""
        try:
            user_config = await self.data_manager.get_user_config(user_id)
            user_tasks = user_config.get('active_tasks', {})
            
            current_time = datetime.now()
            tasks_to_remove = []
            
            for task_id, task_dict in user_tasks.items():
                task = self._dict_to_task_progress(task_dict)
                
                # 检查任务是否已完成且超过最大年龄
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if task.end_time:
                        age_hours = (current_time - task.end_time).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            tasks_to_remove.append(task_id)
            
            # 移除过期任务
            for task_id in tasks_to_remove:
                del user_tasks[task_id]
                with self._cache_lock:
                    self._task_cache.pop(task_id, None)
            
            if tasks_to_remove:
                # 保存更新后的任务列表
                user_config['active_tasks'] = user_tasks
                user_config['updated_at'] = datetime.now().isoformat()
                await self.data_manager.save_user_config(user_id, user_config)
                
                logger.info(f"清理完成的任务: {user_id} ({len(tasks_to_remove)} 个)")
            
        except Exception as e:
            logger.error(f"清理完成任务失败 {user_id}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._cache_lock:
            return {
                **self.stats,
                'cached_tasks': len(self._task_cache),
                'pending_saves': len(self._pending_saves),
                'auto_save_running': self._auto_save_running
            }

# 全局任务状态管理器
_global_task_state_manager = None

def get_global_task_state_manager(bot_id: str = "default_bot") -> TaskStateManager:
    """获取全局任务状态管理器"""
    global _global_task_state_manager
    
    if _global_task_state_manager is None:
        _global_task_state_manager = TaskStateManager(bot_id)
    
    return _global_task_state_manager

async def start_task_state_manager(bot_id: str = "default_bot"):
    """启动任务状态管理器"""
    manager = get_global_task_state_manager(bot_id)
    await manager.start_auto_save()
    return manager

async def stop_task_state_manager(bot_id: str = "default_bot"):
    """停止任务状态管理器"""
    manager = get_global_task_state_manager(bot_id)
    await manager.stop_auto_save()

__all__ = [
    "TaskStateManager",
    "TaskProgress", 
    "TaskStatus",
    "get_global_task_state_manager",
    "start_task_state_manager",
    "stop_task_state_manager"
]
