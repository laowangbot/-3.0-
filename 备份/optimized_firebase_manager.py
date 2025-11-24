#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化的Firebase管理器
集成缓存、配额监控和批量操作，最大化减少API调用
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_batch_storage import FirebaseBatchStorage, get_global_batch_storage
from firebase_cache_manager import FirebaseCacheManager, get_global_cache_manager
from firebase_quota_monitor import FirebaseQuotaMonitor, get_global_quota_monitor
from config import get_config

logger = logging.getLogger(__name__)

class OptimizedFirebaseManager:
    """优化的Firebase管理器 - 集成所有优化策略"""
    
    def __init__(self, bot_id: str):
        """初始化优化的Firebase管理器
        
        Args:
            bot_id: 机器人ID
        """
        self.bot_id = bot_id
        self.db = None
        self.initialized = False
        
        # 初始化各个组件
        self.batch_storage = None
        self.cache_manager = None
        self.quota_monitor = None
        
        # 配置
        self.config = get_config()
        self.use_batch_storage = self.config.get('firebase_batch_enabled', True)
        self.use_cache = True
        self.use_quota_monitoring = True
        
        # 批量查询缓存
        self.batch_query_cache = {}
        self.batch_query_lock = asyncio.Lock()
        
        # 初始化
        self._init_firebase()
        self._init_components()
        
        logger.info(f"✅ 优化Firebase管理器初始化完成 (Bot: {bot_id})")
    
    def _init_firebase(self):
        """初始化Firebase连接"""
        try:
            firebase_credentials = self.config.get('firebase_credentials')
            
            if not self._validate_firebase_credentials(firebase_credentials):
                logger.error("❌ Firebase凭据验证失败")
                return
            
            if not firebase_admin._apps:
                cred = credentials.Certificate(firebase_credentials)
                firebase_admin.initialize_app(cred, {
                    'projectId': self.config.get('firebase_project_id')
                })
            
            self.db = firestore.client()
            self.initialized = True
            logger.info(f"✅ Firebase连接初始化成功 (Bot: {self.bot_id})")
            
        except Exception as e:
            logger.error(f"❌ Firebase连接初始化失败: {e}")
            self.initialized = False
    
    def _init_components(self):
        """初始化各个优化组件"""
        try:
            # 初始化批量存储
            if self.use_batch_storage:
                self.batch_storage = FirebaseBatchStorage(
                    self.bot_id,
                    batch_interval=self.config.get('firebase_batch_interval', 300),
                    max_batch_size=self.config.get('firebase_max_batch_size', 100)
                )
                logger.info("✅ 批量存储组件已初始化")
            
            # 初始化缓存管理器
            if self.use_cache:
                self.cache_manager = FirebaseCacheManager(
                    self.bot_id,
                    cache_ttl=300,  # 5分钟缓存
                    max_cache_size=1000
                )
                logger.info("✅ 缓存管理器已初始化")
            
            # 初始化配额监控器
            if self.use_quota_monitoring:
                self.quota_monitor = FirebaseQuotaMonitor(self.bot_id)
                logger.info("✅ 配额监控器已初始化")
                
        except Exception as e:
            logger.error(f"❌ 组件初始化失败: {e}")
    
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
    
    async def start_optimization_services(self):
        """启动所有优化服务"""
        tasks = []
        
        # 启动批量存储
        if self.batch_storage:
            tasks.append(self.batch_storage.start_batch_processor())
        
        # 启动缓存清理
        if self.cache_manager:
            tasks.append(self.cache_manager.start_cleanup_task())
        
        # 启动配额监控
        if self.quota_monitor:
            tasks.append(self.quota_monitor.start_monitoring())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("✅ 所有优化服务已启动")
    
    async def stop_optimization_services(self):
        """停止所有优化服务"""
        tasks = []
        
        # 停止批量存储
        if self.batch_storage:
            tasks.append(self.batch_storage.stop_batch_processor())
        
        # 停止缓存清理
        if self.cache_manager:
            tasks.append(self.cache_manager.stop_cleanup_task())
        
        # 停止配额监控
        if self.quota_monitor:
            tasks.append(self.quota_monitor.stop_monitoring())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("✅ 所有优化服务已停止")
    
    # ==================== 优化的读取操作 ====================
    
    async def get_document(self, collection: str, document: str, 
                          use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取文档（带缓存优化）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return None
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('read', 1):
            logger.warning("❌ 读取操作被配额限制阻止")
            return None
        
        # 尝试从缓存获取
        if use_cache and self.cache_manager:
            cached_data = self.cache_manager.get(collection, document)
            if cached_data is not None:
                logger.debug(f"缓存命中: {collection}/{document}")
                return cached_data
        
        try:
            # 从Firebase获取
            doc_ref = self.db.collection(collection).document(document)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                
                # 记录配额使用
                if self.quota_monitor:
                    self.quota_monitor.record_operation('read', 1)
                
                # 存入缓存
                if use_cache and self.cache_manager:
                    self.cache_manager.set(collection, document, data)
                
                logger.debug(f"文档读取成功: {collection}/{document}")
                return data
            else:
                logger.debug(f"文档不存在: {collection}/{document}")
                return None
                
        except Exception as e:
            logger.error(f"读取文档失败 {collection}/{document}: {e}")
            return None
    
    async def get_collection(self, collection: str, limit: int = None, 
                           order_by: str = None, use_cache: bool = True) -> List[Dict[str, Any]]:
        """获取集合（带缓存优化）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return []
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('read', 1):
            logger.warning("❌ 读取操作被配额限制阻止")
            return []
        
        try:
            # 构建查询
            query = self.db.collection(collection)
            
            if order_by:
                query = query.order_by(order_by)
            
            if limit:
                query = query.limit(limit)
            
            # 执行查询
            docs = query.stream()
            
            # 记录配额使用
            if self.quota_monitor:
                self.quota_monitor.record_operation('read', 1)
            
            # 处理结果
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['_id'] = doc.id
                results.append(data)
                
                # 存入缓存
                if use_cache and self.cache_manager:
                    self.cache_manager.set(collection, doc.id, data)
            
            logger.debug(f"集合读取成功: {collection} ({len(results)} 个文档)")
            return results
            
        except Exception as e:
            logger.error(f"读取集合失败 {collection}: {e}")
            return []
    
    async def batch_get_documents(self, collection: str, document_ids: List[str],
                                 use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """批量获取文档（优化版）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return {}
        
        if not document_ids:
            return {}
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('read', len(document_ids)):
            logger.warning("❌ 批量读取操作被配额限制阻止")
            return {}
        
        results = {}
        uncached_ids = []
        
        # 先从缓存获取
        if use_cache and self.cache_manager:
            for doc_id in document_ids:
                cached_data = self.cache_manager.get(collection, doc_id)
                if cached_data is not None:
                    results[doc_id] = cached_data
                else:
                    uncached_ids.append(doc_id)
        else:
            uncached_ids = document_ids
        
        # 批量获取未缓存的文档
        if uncached_ids:
            try:
                # 使用Firestore的批量获取
                doc_refs = [self.db.collection(collection).document(doc_id) for doc_id in uncached_ids]
                docs = self.db.get_all(doc_refs)
                
                # 记录配额使用
                if self.quota_monitor:
                    self.quota_monitor.record_operation('read', len(uncached_ids))
                
                # 处理结果
                for doc in docs:
                    if doc.exists:
                        data = doc.to_dict()
                        data['_id'] = doc.id
                        results[doc.id] = data
                        
                        # 存入缓存
                        if use_cache and self.cache_manager:
                            self.cache_manager.set(collection, doc.id, data)
                
                logger.debug(f"批量读取成功: {collection} ({len(results)} 个文档)")
                
            except Exception as e:
                logger.error(f"批量读取失败 {collection}: {e}")
        
        return results
    
    # ==================== 优化的写入操作 ====================
    
    async def set_document(self, collection: str, document: str, data: Dict[str, Any],
                          use_batch: bool = None, use_cache: bool = True) -> bool:
        """设置文档（优化版）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return False
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('write', 1):
            logger.warning("❌ 写入操作被配额限制阻止")
            return False
        
        # 决定是否使用批量存储
        if use_batch is None:
            use_batch = self.use_batch_storage
        
        try:
            if use_batch and self.batch_storage:
                # 使用批量存储
                success = self.batch_storage.add_operation('set', collection, document, data)
                if success:
                    # 更新缓存
                    if use_cache and self.cache_manager:
                        self.cache_manager.set(collection, document, data, 'set')
                    logger.debug(f"文档已加入批量队列: {collection}/{document}")
                return success
            else:
                # 直接写入
                doc_ref = self.db.collection(collection).document(document)
                doc_ref.set(data)
                
                # 记录配额使用
                if self.quota_monitor:
                    self.quota_monitor.record_operation('write', 1)
                
                # 更新缓存
                if use_cache and self.cache_manager:
                    self.cache_manager.set(collection, document, data, 'set')
                
                logger.debug(f"文档写入成功: {collection}/{document}")
                return True
                
        except Exception as e:
            logger.error(f"写入文档失败 {collection}/{document}: {e}")
            return False
    
    async def update_document(self, collection: str, document: str, data: Dict[str, Any],
                             use_batch: bool = None, use_cache: bool = True) -> bool:
        """更新文档（优化版）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return False
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('write', 1):
            logger.warning("❌ 更新操作被配额限制阻止")
            return False
        
        # 决定是否使用批量存储
        if use_batch is None:
            use_batch = self.use_batch_storage
        
        try:
            if use_batch and self.batch_storage:
                # 使用批量存储
                success = self.batch_storage.add_operation('update', collection, document, data)
                if success:
                    # 使缓存失效
                    if use_cache and self.cache_manager:
                        self.cache_manager.invalidate(collection, document)
                    logger.debug(f"文档更新已加入批量队列: {collection}/{document}")
                return success
            else:
                # 直接更新
                doc_ref = self.db.collection(collection).document(document)
                doc_ref.update(data)
                
                # 记录配额使用
                if self.quota_monitor:
                    self.quota_monitor.record_operation('write', 1)
                
                # 使缓存失效
                if use_cache and self.cache_manager:
                    self.cache_manager.invalidate(collection, document)
                
                logger.debug(f"文档更新成功: {collection}/{document}")
                return True
                
        except Exception as e:
            logger.error(f"更新文档失败 {collection}/{document}: {e}")
            return False
    
    async def delete_document(self, collection: str, document: str,
                             use_batch: bool = None, use_cache: bool = True) -> bool:
        """删除文档（优化版）"""
        if not self.initialized:
            logger.error("Firebase未初始化")
            return False
        
        # 检查配额
        if self.quota_monitor and not self.quota_monitor.can_perform_operation('delete', 1):
            logger.warning("❌ 删除操作被配额限制阻止")
            return False
        
        # 决定是否使用批量存储
        if use_batch is None:
            use_batch = self.use_batch_storage
        
        try:
            if use_batch and self.batch_storage:
                # 使用批量存储
                success = self.batch_storage.add_operation('delete', collection, document)
                if success:
                    # 使缓存失效
                    if use_cache and self.cache_manager:
                        self.cache_manager.invalidate(collection, document)
                    logger.debug(f"文档删除已加入批量队列: {collection}/{document}")
                return success
            else:
                # 直接删除
                doc_ref = self.db.collection(collection).document(document)
                doc_ref.delete()
                
                # 记录配额使用
                if self.quota_monitor:
                    self.quota_monitor.record_operation('delete', 1)
                
                # 使缓存失效
                if use_cache and self.cache_manager:
                    self.cache_manager.invalidate(collection, document)
                
                logger.debug(f"文档删除成功: {collection}/{document}")
                return True
                
        except Exception as e:
            logger.error(f"删除文档失败 {collection}/{document}: {e}")
            return False
    
    # ==================== 统计和监控 ====================
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        stats = {
            'initialized': self.initialized,
            'use_batch_storage': self.use_batch_storage,
            'use_cache': self.use_cache,
            'use_quota_monitoring': self.use_quota_monitoring,
        }
        
        # 批量存储统计
        if self.batch_storage:
            stats['batch_storage'] = self.batch_storage.get_stats()
        
        # 缓存统计
        if self.cache_manager:
            stats['cache'] = self.cache_manager.get_stats()
        
        # 配额监控统计
        if self.quota_monitor:
            stats['quota'] = self.quota_monitor.get_usage_stats()
        
        return stats
    
    def force_flush_all(self):
        """强制刷新所有待处理操作"""
        if self.batch_storage:
            self.batch_storage.force_flush()
        logger.info("✅ 所有待处理操作已强制刷新")

# ==================== 全局优化管理器 ====================

_global_optimized_manager = None

def get_global_optimized_manager(bot_id: str = None) -> Optional[OptimizedFirebaseManager]:
    """获取全局优化Firebase管理器"""
    global _global_optimized_manager
    
    if _global_optimized_manager is None and bot_id:
        _global_optimized_manager = OptimizedFirebaseManager(bot_id)
    
    return _global_optimized_manager

def set_global_optimized_manager(manager: OptimizedFirebaseManager):
    """设置全局优化Firebase管理器"""
    global _global_optimized_manager
    _global_optimized_manager = manager

# ==================== 便捷函数 ====================

async def get_doc(collection: str, document: str, bot_id: str = None, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """获取文档（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return None
    
    return await manager.get_document(collection, document, use_cache)

async def set_doc(collection: str, document: str, data: Dict[str, Any], 
                 bot_id: str = None, use_batch: bool = None, use_cache: bool = True) -> bool:
    """设置文档（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return False
    
    return await manager.set_document(collection, document, data, use_batch, use_cache)

async def update_doc(collection: str, document: str, data: Dict[str, Any],
                    bot_id: str = None, use_batch: bool = None, use_cache: bool = True) -> bool:
    """更新文档（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return False
    
    return await manager.update_document(collection, document, data, use_batch, use_cache)

async def delete_doc(collection: str, document: str,
                    bot_id: str = None, use_batch: bool = None, use_cache: bool = True) -> bool:
    """删除文档（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return False
    
    return await manager.delete_document(collection, document, use_batch, use_cache)

async def start_optimization_services(bot_id: str = None):
    """启动优化服务（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return False
    
    return await manager.start_optimization_services()

async def stop_optimization_services(bot_id: str = None):
    """停止优化服务（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if manager:
        await manager.stop_optimization_services()

def get_optimization_stats(bot_id: str = None) -> Dict[str, Any]:
    """获取优化统计（便捷函数）"""
    manager = get_global_optimized_manager(bot_id)
    if not manager:
        return {}
    
    return manager.get_optimization_stats()

__all__ = [
    "OptimizedFirebaseManager",
    "get_global_optimized_manager",
    "set_global_optimized_manager",
    "get_doc",
    "set_doc",
    "update_doc",
    "delete_doc",
    "start_optimization_services",
    "stop_optimization_services",
    "get_optimization_stats"
]

