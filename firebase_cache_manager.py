#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firebase缓存管理器
减少Firebase API调用次数，优化免费版配额使用
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import OrderedDict
import threading
import json

logger = logging.getLogger(__name__)

class FirebaseCacheManager:
    """Firebase缓存管理器 - 减少API调用次数"""
    
    def __init__(self, bot_id: str, cache_ttl: int = 300, max_cache_size: int = 1000):
        """初始化缓存管理器
        
        Args:
            bot_id: 机器人ID
            cache_ttl: 缓存生存时间（秒），默认5分钟
            max_cache_size: 最大缓存条目数
        """
        self.bot_id = bot_id
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        
        # 缓存存储：OrderedDict保持访问顺序
        self.cache = OrderedDict()
        self.cache_lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_evictions': 0,
            'total_requests': 0,
            'api_calls_saved': 0
        }
        
        # 清理任务
        self.cleanup_task = None
        self.running = False
        
        logger.info(f"✅ Firebase缓存管理器初始化完成 (Bot: {bot_id}, TTL: {cache_ttl}秒)")
    
    async def start_cleanup_task(self):
        """启动缓存清理任务"""
        if self.running:
            return
        
        self.running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ 缓存清理任务已启动")
    
    async def stop_cleanup_task(self):
        """停止缓存清理任务"""
        if not self.running:
            return
        
        self.running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 缓存清理任务已停止")
    
    async def _cleanup_loop(self):
        """缓存清理循环"""
        while self.running:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存清理错误: {e}")
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        with self.cache_lock:
            for key, (data, timestamp) in self.cache.items():
                if current_time - timestamp > self.cache_ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                self.stats['cache_evictions'] += 1
        
        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")
    
    def _evict_oldest(self):
        """淘汰最旧的缓存条目"""
        with self.cache_lock:
            if len(self.cache) >= self.max_cache_size:
                # 移除最旧的条目
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats['cache_evictions'] += 1
                logger.debug(f"淘汰缓存条目: {oldest_key}")
    
    def get_cache_key(self, collection: str, document: str, operation: str = "get") -> str:
        """生成缓存键"""
        return f"{self.bot_id}:{collection}:{document}:{operation}"
    
    def get(self, collection: str, document: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据"""
        cache_key = self.get_cache_key(collection, document, "get")
        current_time = time.time()
        
        with self.cache_lock:
            self.stats['total_requests'] += 1
            
            if cache_key in self.cache:
                data, timestamp = self.cache[cache_key]
                
                # 检查是否过期
                if current_time - timestamp <= self.cache_ttl:
                    # 更新访问时间（移到末尾）
                    del self.cache[cache_key]
                    self.cache[cache_key] = (data, timestamp)
                    
                    self.stats['cache_hits'] += 1
                    self.stats['api_calls_saved'] += 1
                    logger.debug(f"缓存命中: {cache_key}")
                    return data
                else:
                    # 过期，删除
                    del self.cache[cache_key]
                    self.stats['cache_evictions'] += 1
            
            self.stats['cache_misses'] += 1
            return None
    
    def set(self, collection: str, document: str, data: Dict[str, Any], operation: str = "set"):
        """设置缓存数据"""
        cache_key = self.get_cache_key(collection, document, operation)
        current_time = time.time()
        
        with self.cache_lock:
            # 如果缓存已满，淘汰最旧的条目
            if len(self.cache) >= self.max_cache_size and cache_key not in self.cache:
                self._evict_oldest()
            
            # 设置缓存
            self.cache[cache_key] = (data, current_time)
            logger.debug(f"缓存设置: {cache_key}")
    
    def invalidate(self, collection: str, document: str = None):
        """使缓存失效"""
        with self.cache_lock:
            if document:
                # 使特定文档的所有操作缓存失效
                keys_to_remove = []
                for key in self.cache.keys():
                    if key.startswith(f"{self.bot_id}:{collection}:{document}:"):
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.cache[key]
                    self.stats['cache_evictions'] += 1
                
                logger.debug(f"使缓存失效: {collection}/{document} ({len(keys_to_remove)} 个条目)")
            else:
                # 使整个集合的缓存失效
                keys_to_remove = []
                for key in self.cache.keys():
                    if key.startswith(f"{self.bot_id}:{collection}:"):
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.cache[key]
                    self.stats['cache_evictions'] += 1
                
                logger.debug(f"使集合缓存失效: {collection} ({len(keys_to_remove)} 个条目)")
    
    def clear(self):
        """清空所有缓存"""
        with self.cache_lock:
            cache_size = len(self.cache)
            self.cache.clear()
            self.stats['cache_evictions'] += cache_size
            logger.info(f"清空缓存: {cache_size} 个条目")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.cache_lock:
            hit_rate = 0
            if self.stats['total_requests'] > 0:
                hit_rate = self.stats['cache_hits'] / self.stats['total_requests']
            
            return {
                **self.stats,
                'cache_size': len(self.cache),
                'hit_rate': round(hit_rate, 3),
                'cache_ttl': self.cache_ttl,
                'max_cache_size': self.max_cache_size,
                'running': self.running
            }
    
    def set_cache_ttl(self, ttl: int):
        """设置缓存生存时间"""
        self.cache_ttl = ttl
        logger.info(f"缓存TTL已设置为 {ttl} 秒")
    
    def set_max_cache_size(self, size: int):
        """设置最大缓存大小"""
        self.max_cache_size = size
        logger.info(f"最大缓存大小已设置为 {size}")

# ==================== 全局缓存管理器 ====================

_global_cache_manager = None

def get_global_cache_manager(bot_id: str = None) -> Optional[FirebaseCacheManager]:
    """获取全局缓存管理器"""
    global _global_cache_manager
    
    if _global_cache_manager is None and bot_id:
        _global_cache_manager = FirebaseCacheManager(bot_id)
    
    return _global_cache_manager

def set_global_cache_manager(cache_manager: FirebaseCacheManager):
    """设置全局缓存管理器"""
    global _global_cache_manager
    _global_cache_manager = cache_manager

# ==================== 便捷函数 ====================

def cache_get(collection: str, document: str, bot_id: str = None) -> Optional[Dict[str, Any]]:
    """从缓存获取数据"""
    cache_manager = get_global_cache_manager(bot_id)
    if not cache_manager:
        return None
    
    return cache_manager.get(collection, document)

def cache_set(collection: str, document: str, data: Dict[str, Any], 
              operation: str = "set", bot_id: str = None):
    """设置缓存数据"""
    cache_manager = get_global_cache_manager(bot_id)
    if not cache_manager:
        return
    
    cache_manager.set(collection, document, data, operation)

def cache_invalidate(collection: str, document: str = None, bot_id: str = None):
    """使缓存失效"""
    cache_manager = get_global_cache_manager(bot_id)
    if not cache_manager:
        return
    
    cache_manager.invalidate(collection, document)

async def start_cache_cleanup(bot_id: str = None):
    """启动缓存清理"""
    cache_manager = get_global_cache_manager(bot_id)
    if not cache_manager:
        return False
    
    return await cache_manager.start_cleanup_task()

async def stop_cache_cleanup(bot_id: str = None):
    """停止缓存清理"""
    cache_manager = get_global_cache_manager(bot_id)
    if cache_manager:
        await cache_manager.stop_cleanup_task()

def get_cache_stats(bot_id: str = None) -> Dict[str, Any]:
    """获取缓存统计信息"""
    cache_manager = get_global_cache_manager(bot_id)
    if not cache_manager:
        return {}
    
    return cache_manager.get_stats()

__all__ = [
    "FirebaseCacheManager",
    "get_global_cache_manager",
    "set_global_cache_manager",
    "cache_get",
    "cache_set", 
    "cache_invalidate",
    "start_cache_cleanup",
    "stop_cache_cleanup",
    "get_cache_stats"
]
