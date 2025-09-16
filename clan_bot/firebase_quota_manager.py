# ==================== Firebase配额管理器 ====================
"""
Firebase配额管理器
优化读写操作，减少API调用次数，管理配额使用
"""

import os
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

@dataclass
class QuotaStats:
    """配额统计"""
    reads: int = 0
    writes: int = 0
    deletes: int = 0
    last_reset: datetime = field(default_factory=datetime.now)
    
    def reset_daily(self):
        """重置每日配额"""
        if datetime.now().date() > self.last_reset.date():
            self.reads = 0
            self.writes = 0
            self.deletes = 0
            self.last_reset = datetime.now()

@dataclass
class CacheItem:
    """缓存项"""
    data: Any
    timestamp: datetime
    ttl: int = 300  # 5分钟TTL
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() - self.timestamp > timedelta(seconds=self.ttl)

class FirebaseQuotaManager:
    """Firebase配额管理器"""
    
    def __init__(self, credentials_path: str = None):
        """初始化配额管理器"""
        self.quota_stats = QuotaStats()
        self.cache = {}
        self.write_buffer = []
        self.batch_size = 100
        self.max_cache_size = 1000
        
        # Firebase初始化
        try:
            if credentials_path:
                cred = credentials.Certificate(credentials_path)
            else:
                cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS', '{}'))
                cred = credentials.Certificate(cred_dict)
            
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.info("✅ Firebase配额管理器初始化成功")
        except Exception as e:
            logger.error(f"❌ Firebase初始化失败: {e}")
            self.db = None
    
    def _check_quota_limit(self, operation: str) -> bool:
        """检查配额限制"""
        self.quota_stats.reset_daily()
        
        # Firestore免费配额限制
        limits = {
            'reads': 50000,    # 每日读取限制
            'writes': 20000,   # 每日写入限制
            'deletes': 20000   # 每日删除限制
        }
        
        current_count = getattr(self.quota_stats, operation)
        limit = limits.get(operation, 0)
        
        if current_count >= limit:
            logger.warning(f"⚠️ {operation}配额已达限制: {current_count}/{limit}")
            return False
        
        return True
    
    def _update_quota_stats(self, operation: str, count: int = 1):
        """更新配额统计"""
        current_count = getattr(self.quota_stats, operation)
        setattr(self.quota_stats, operation, current_count + count)
    
    def _get_cache_key(self, collection: str, doc_id: str) -> str:
        """生成缓存键"""
        return f"{collection}:{doc_id}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if cache_key in self.cache:
            item = self.cache[cache_key]
            if not item.is_expired():
                logger.debug(f"✅ 缓存命中: {cache_key}")
                return item.data
            else:
                # 清理过期缓存
                del self.cache[cache_key]
        
        return None
    
    def _set_cache(self, cache_key: str, data: Any, ttl: int = 300):
        """设置缓存"""
        # 清理过期缓存
        self._cleanup_expired_cache()
        
        # 限制缓存大小
        if len(self.cache) >= self.max_cache_size:
            self._evict_oldest_cache()
        
        self.cache[cache_key] = CacheItem(data, datetime.now(), ttl)
        logger.debug(f"✅ 缓存已设置: {cache_key}")
    
    def _cleanup_expired_cache(self):
        """清理过期缓存"""
        expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
        for key in expired_keys:
            del self.cache[key]
    
    def _evict_oldest_cache(self):
        """清理最旧的缓存"""
        if not self.cache:
            return
        
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].timestamp)
        del self.cache[oldest_key]
    
    async def get_document(self, collection: str, doc_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取文档（带缓存）"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return None
        
        cache_key = self._get_cache_key(collection, doc_id)
        
        # 尝试从缓存获取
        if use_cache:
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # 检查读取配额
        if not self._check_quota_limit('reads'):
            logger.warning("读取配额不足，返回缓存数据")
            return self._get_from_cache(cache_key)
        
        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            self._update_quota_stats('reads')
            
            if doc.exists:
                data = doc.to_dict()
                # 缓存数据
                if use_cache:
                    self._set_cache(cache_key, data)
                logger.debug(f"✅ 文档已获取: {collection}/{doc_id}")
                return data
            else:
                logger.debug(f"文档不存在: {collection}/{doc_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取文档失败: {e}")
            return None
    
    async def set_document(self, collection: str, doc_id: str, data: Dict[str, Any], use_batch: bool = True) -> bool:
        """设置文档（支持批量写入）"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return False
        
        if use_batch:
            # 添加到批量写入缓冲区
            self.write_buffer.append({
                'collection': collection,
                'doc_id': doc_id,
                'data': data,
                'operation': 'set'
            })
            
            # 检查是否需要刷新缓冲区
            if len(self.write_buffer) >= self.batch_size:
                await self.flush_write_buffer()
            
            return True
        else:
            # 直接写入
            if not self._check_quota_limit('writes'):
                logger.warning("写入配额不足")
                return False
            
            try:
                doc_ref = self.db.collection(collection).document(doc_id)
                doc_ref.set(data)
                
                self._update_quota_stats('writes')
                
                # 更新缓存
                cache_key = self._get_cache_key(collection, doc_id)
                self._set_cache(cache_key, data)
                
                logger.debug(f"✅ 文档已设置: {collection}/{doc_id}")
                return True
                
            except Exception as e:
                logger.error(f"❌ 设置文档失败: {e}")
                return False
    
    async def flush_write_buffer(self) -> bool:
        """刷新写入缓冲区"""
        if not self.write_buffer or not self.db:
            return True
        
        # 检查写入配额
        if not self._check_quota_limit('writes'):
            logger.warning("写入配额不足，跳过批量写入")
            return False
        
        try:
            batch = self.db.batch()
            
            for item in self.write_buffer:
                doc_ref = self.db.collection(item['collection']).document(item['doc_id'])
                batch.set(doc_ref, item['data'])
            
            # 执行批量写入
            batch.commit()
            
            # 更新配额统计
            self._update_quota_stats('writes', len(self.write_buffer))
            
            # 更新缓存
            for item in self.write_buffer:
                cache_key = self._get_cache_key(item['collection'], item['doc_id'])
                self._set_cache(cache_key, item['data'])
            
            logger.info(f"✅ 批量写入完成: {len(self.write_buffer)} 个文档")
            
            # 清空缓冲区
            self.write_buffer.clear()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 批量写入失败: {e}")
            return False
    
    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """删除文档"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return False
        
        if not self._check_quota_limit('deletes'):
            logger.warning("删除配额不足")
            return False
        
        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            
            self._update_quota_stats('deletes')
            
            # 清理缓存
            cache_key = self._get_cache_key(collection, doc_id)
            if cache_key in self.cache:
                del self.cache[cache_key]
            
            logger.debug(f"✅ 文档已删除: {collection}/{doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 删除文档失败: {e}")
            return False
    
    def get_quota_stats(self) -> Dict[str, Any]:
        """获取配额统计"""
        self.quota_stats.reset_daily()
        
        return {
            'reads': self.quota_stats.reads,
            'writes': self.quota_stats.writes,
            'deletes': self.quota_stats.deletes,
            'cache_size': len(self.cache),
            'buffer_size': len(self.write_buffer),
            'last_reset': self.quota_stats.last_reset.isoformat()
        }
    
    async def cleanup(self):
        """清理资源"""
        # 刷新写入缓冲区
        await self.flush_write_buffer()
        
        # 清理缓存
        self.cache.clear()
        
        logger.info("✅ 配额管理器已清理")

# 全局配额管理器实例
quota_manager = FirebaseQuotaManager()

# 导出函数
async def get_document(collection: str, doc_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """获取文档"""
    return await quota_manager.get_document(collection, doc_id, use_cache)

async def set_document(collection: str, doc_id: str, data: Dict[str, Any], use_batch: bool = True) -> bool:
    """设置文档"""
    return await quota_manager.set_document(collection, doc_id, data, use_batch)

async def delete_document(collection: str, doc_id: str) -> bool:
    """删除文档"""
    return await quota_manager.delete_document(collection, doc_id)

async def flush_writes():
    """刷新写入缓冲区"""
    return await quota_manager.flush_write_buffer()

def get_quota_stats() -> Dict[str, Any]:
    """获取配额统计"""
    return quota_manager.get_quota_stats()

# ==================== 使用示例 ====================
if __name__ == "__main__":
    async def test_quota_manager():
        """测试配额管理器"""
        manager = FirebaseQuotaManager()
        
        # 测试写入
        test_data = {
            'user_id': 123456789,
            'name': '测试用户',
            'timestamp': datetime.now().isoformat()
        }
        
        success = await manager.set_document('users', '123456789', test_data)
        print(f"写入测试: {'成功' if success else '失败'}")
        
        # 测试读取
        data = await manager.get_document('users', '123456789')
        print(f"读取测试: {data}")
        
        # 显示配额统计
        stats = manager.get_quota_stats()
        print(f"配额统计: {stats}")
        
        # 清理
        await manager.cleanup()
    
    # 运行测试
    asyncio.run(test_quota_manager())
