#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firebase批量存储管理器
解决Firebase API配额超限问题，通过定时批量存储减少API调用
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from collections import defaultdict, deque
from threading import Lock
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

class FirebaseBatchStorage:
    """Firebase批量存储管理器"""
    
    def __init__(self, bot_id: str, batch_interval: int = 300, max_batch_size: int = 100):
        """初始化批量存储管理器
        
        Args:
            bot_id: 机器人ID
            batch_interval: 批量存储间隔（秒），默认5分钟
            max_batch_size: 最大批量大小，默认100
        """
        self.bot_id = bot_id
        self.batch_interval = batch_interval
        self.max_batch_size = max_batch_size
        
        # 存储队列
        self.pending_operations = deque()
        self.operation_lock = Lock()
        
        # 统计信息
        self.stats = {
            'total_operations': 0,
            'batch_operations': 0,
            'failed_operations': 0,
            'last_batch_time': None,
            'pending_count': 0
        }
        
        # Firebase连接
        self.db = None
        self.initialized = False
        
        # 批量存储任务
        self.batch_task = None
        self.running = False
        
        # 初始化Firebase
        self._init_firebase()
        
        logger.info(f"✅ Firebase批量存储管理器初始化完成 (Bot: {bot_id}, 间隔: {batch_interval}秒)")
    
    def _init_firebase(self):
        """初始化Firebase连接"""
        try:
            from config import get_config
            config = get_config()
            firebase_credentials = config.get('firebase_credentials')
            
            if not self._validate_firebase_credentials(firebase_credentials):
                logger.error("❌ Firebase凭据验证失败")
                return
            
            if not firebase_admin._apps:
                cred = credentials.Certificate(firebase_credentials)
                firebase_admin.initialize_app(cred, {
                    'projectId': config.get('firebase_project_id')
                })
            
            self.db = firestore.client()
            self.initialized = True
            logger.info(f"✅ Firebase连接初始化成功 (Bot: {self.bot_id})")
            
        except Exception as e:
            logger.error(f"❌ Firebase连接初始化失败: {e}")
            self.initialized = False
    
    def _validate_firebase_credentials(self, credentials: Dict[str, Any]) -> bool:
        """验证Firebase凭据"""
        required_fields = [
            'type', 'project_id', 'private_key_id', 'private_key',
            'client_email', 'client_id', 'auth_uri', 'token_uri'
        ]
        
        for field in required_fields:
            if field not in credentials or not credentials[field]:
                logger.error(f"❌ Firebase凭据缺少必需字段: {field}")
                return False
            
            if str(credentials[field]).startswith('your_'):
                logger.error(f"❌ Firebase凭据字段 {field} 仍为占位符值")
                return False
        
        return True
    
    async def start_batch_processor(self):
        """启动批量处理器"""
        if not self.initialized:
            logger.error("❌ Firebase未初始化，无法启动批量处理器")
            return False
        
        if self.running:
            logger.warning("批量处理器已在运行")
            return True
        
        self.running = True
        self.batch_task = asyncio.create_task(self._batch_processor())
        logger.info("✅ 批量处理器已启动")
        return True
    
    async def stop_batch_processor(self):
        """停止批量处理器"""
        if not self.running:
            return
        
        self.running = False
        if self.batch_task:
            self.batch_task.cancel()
            try:
                await self.batch_task
            except asyncio.CancelledError:
                pass
        
        # 处理剩余的待处理操作
        await self._process_pending_operations()
        logger.info("✅ 批量处理器已停止")
    
    async def _batch_processor(self):
        """批量处理器主循环"""
        while self.running:
            try:
                await asyncio.sleep(self.batch_interval)
                
                if self.pending_operations:
                    await self._process_pending_operations()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"批量处理器错误: {e}")
                await asyncio.sleep(10)  # 错误后等待10秒再继续
    
    async def _process_pending_operations(self):
        """处理待处理的操作"""
        if not self.pending_operations:
            return
        
        with self.operation_lock:
            operations = list(self.pending_operations)
            self.pending_operations.clear()
        
        if not operations:
            return
        
        logger.info(f"🔄 开始批量处理 {len(operations)} 个操作")
        
        # 按操作类型分组
        operations_by_type = defaultdict(list)
        for op in operations:
            operations_by_type[op['type']].append(op)
        
        # 批量处理每种类型的操作
        for op_type, ops in operations_by_type.items():
            try:
                if op_type == 'set':
                    await self._batch_set_operations(ops)
                elif op_type == 'update':
                    await self._batch_update_operations(ops)
                elif op_type == 'delete':
                    await self._batch_delete_operations(ops)
                else:
                    logger.warning(f"未知操作类型: {op_type}")
                    
            except Exception as e:
                logger.error(f"批量处理 {op_type} 操作失败: {e}")
                self.stats['failed_operations'] += len(ops)
        
        self.stats['batch_operations'] += 1
        self.stats['last_batch_time'] = datetime.now().isoformat()
        logger.info(f"✅ 批量处理完成，处理了 {len(operations)} 个操作")
    
    async def _batch_set_operations(self, operations: List[Dict[str, Any]]):
        """批量设置操作"""
        batch = self.db.batch()
        batch_count = 0
        
        for op in operations:
            try:
                doc_ref = self.db.collection(op['collection']).document(op['document'])
                batch.set(doc_ref, op['data'])
                batch_count += 1
                
                # Firestore批量操作限制为500个
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
                    
            except Exception as e:
                logger.error(f"批量设置操作失败: {e}")
        
        if batch_count > 0:
            batch.commit()
    
    async def _batch_update_operations(self, operations: List[Dict[str, Any]]):
        """批量更新操作"""
        batch = self.db.batch()
        batch_count = 0
        
        for op in operations:
            try:
                doc_ref = self.db.collection(op['collection']).document(op['document'])
                batch.update(doc_ref, op['data'])
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
                    
            except Exception as e:
                logger.error(f"批量更新操作失败: {e}")
        
        if batch_count > 0:
            batch.commit()
    
    async def _batch_delete_operations(self, operations: List[Dict[str, Any]]):
        """批量删除操作"""
        batch = self.db.batch()
        batch_count = 0
        
        for op in operations:
            try:
                doc_ref = self.db.collection(op['collection']).document(op['document'])
                batch.delete(doc_ref)
                batch_count += 1
                
                if batch_count >= 500:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
                    
            except Exception as e:
                logger.error(f"批量删除操作失败: {e}")
        
        if batch_count > 0:
            batch.commit()
    
    def add_operation(self, operation_type: str, collection: str, document: str, 
                     data: Dict[str, Any] = None, priority: int = 0):
        """添加操作到队列
        
        Args:
            operation_type: 操作类型 (set, update, delete)
            collection: 集合名称
            document: 文档ID
            data: 数据（对于delete操作可为None）
            priority: 优先级（0=普通，1=高优先级）
        """
        if not self.initialized:
            logger.warning("Firebase未初始化，操作已忽略")
            return False
        
        operation = {
            'type': operation_type,
            'collection': collection,
            'document': document,
            'data': data or {},
            'priority': priority,
            'timestamp': time.time()
        }
        
        with self.operation_lock:
            if priority > 0:
                # 高优先级操作插入到队列前面
                self.pending_operations.appendleft(operation)
            else:
                self.pending_operations.append(operation)
            
            self.stats['pending_count'] = len(self.pending_operations)
            self.stats['total_operations'] += 1
        
        # 如果队列过大，立即处理
        if len(self.pending_operations) >= self.max_batch_size:
            asyncio.create_task(self._process_pending_operations())
        
        return True
    
    def force_flush(self):
        """强制刷新所有待处理操作"""
        if self.pending_operations:
            asyncio.create_task(self._process_pending_operations())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.operation_lock:
            pending_count = len(self.pending_operations)
        
        return {
            **self.stats,
            'pending_count': pending_count,
            'batch_interval': self.batch_interval,
            'max_batch_size': self.max_batch_size,
            'running': self.running,
            'initialized': self.initialized
        }
    
    def set_batch_interval(self, interval: int):
        """设置批量存储间隔"""
        self.batch_interval = interval
        logger.info(f"批量存储间隔已设置为 {interval} 秒")
    
    def set_max_batch_size(self, size: int):
        """设置最大批量大小"""
        self.max_batch_size = size
        logger.info(f"最大批量大小已设置为 {size}")

# ==================== 全局批量存储管理器 ====================

_global_batch_storage = None

def get_global_batch_storage(bot_id: str = None) -> Optional[FirebaseBatchStorage]:
    """获取全局批量存储管理器"""
    global _global_batch_storage
    
    if _global_batch_storage is None and bot_id:
        _global_batch_storage = FirebaseBatchStorage(bot_id)
    
    return _global_batch_storage

def set_global_batch_storage(storage: FirebaseBatchStorage):
    """设置全局批量存储管理器"""
    global _global_batch_storage
    _global_batch_storage = storage

# ==================== 便捷函数 ====================

async def batch_set(collection: str, document: str, data: Dict[str, Any], 
                   bot_id: str = None, priority: int = 0) -> bool:
    """批量设置文档"""
    storage = get_global_batch_storage(bot_id)
    if not storage:
        return False
    
    return storage.add_operation('set', collection, document, data, priority)

async def batch_update(collection: str, document: str, data: Dict[str, Any], 
                      bot_id: str = None, priority: int = 0) -> bool:
    """批量更新文档"""
    storage = get_global_batch_storage(bot_id)
    if not storage:
        return False
    
    return storage.add_operation('update', collection, document, data, priority)

async def batch_delete(collection: str, document: str, 
                      bot_id: str = None, priority: int = 0) -> bool:
    """批量删除文档"""
    storage = get_global_batch_storage(bot_id)
    if not storage:
        return False
    
    return storage.add_operation('delete', collection, document, None, priority)

async def start_batch_processing(bot_id: str = None) -> bool:
    """启动批量处理"""
    storage = get_global_batch_storage(bot_id)
    if not storage:
        return False
    
    return await storage.start_batch_processor()

async def stop_batch_processing(bot_id: str = None):
    """停止批量处理"""
    storage = get_global_batch_storage(bot_id)
    if storage:
        await storage.stop_batch_processor()

def force_flush_batch(bot_id: str = None):
    """强制刷新批量操作"""
    storage = get_global_batch_storage(bot_id)
    if storage:
        storage.force_flush()

def get_batch_stats(bot_id: str = None) -> Dict[str, Any]:
    """获取批量处理统计信息"""
    storage = get_global_batch_storage(bot_id)
    if not storage:
        return {}
    
    return storage.get_stats()

__all__ = [
    "FirebaseBatchStorage",
    "get_global_batch_storage",
    "set_global_batch_storage",
    "batch_set",
    "batch_update", 
    "batch_delete",
    "start_batch_processing",
    "stop_batch_processing",
    "force_flush_batch",
    "get_batch_stats"
]
