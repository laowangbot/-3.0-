# ==================== 优化的Firebase管理器 ====================
"""
优化的Firebase管理器
解决性能问题，避免卡顿
"""

import os
import json
import asyncio
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import firebase_admin
from firebase_admin import credentials, firestore
import gzip
import base64

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

@dataclass
class ConnectionConfig:
    """连接配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    timeout: float = 30.0
    max_workers: int = 10

class OptimizedFirebaseManager:
    """优化的Firebase管理器 - 解决卡顿问题"""
    
    def __init__(self, credentials_path: str = None, config: ConnectionConfig = None):
        """初始化优化的Firebase管理器"""
        self.config = config or ConnectionConfig()
        self.db = None
        self.executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        self._initialized = False
        
        # 性能统计
        self.stats = {
            'operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # 初始化Firebase连接
        self._initialize_firebase(credentials_path)
    
    def _initialize_firebase(self, credentials_path: str = None):
        """初始化Firebase连接 - 单例模式"""
        if self._initialized:
            return
        
        try:
            if credentials_path:
                cred = credentials.Certificate(credentials_path)
            else:
                cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS', '{}'))
                cred = credentials.Certificate(cred_dict)
            
            # 检查是否已经初始化
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            self._initialized = True
            logger.info("✅ 优化的Firebase管理器初始化成功")
        except Exception as e:
            logger.error(f"❌ Firebase初始化失败: {e}")
            self.db = None
    
    async def _run_in_thread(self, func, *args, **kwargs):
        """在线程池中运行同步函数 - 避免阻塞事件循环"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args, **kwargs)
    
    async def _retry_operation(self, operation_name: str, func, *args, **kwargs):
        """带重试机制的操作 - 提高可靠性"""
        last_exception = None
        
        for attempt in range(self.config.max_retries):
            try:
                start_time = time.time()
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # 更新统计
                self.stats['operations'] += 1
                self.stats['successful_operations'] += 1
                self.stats['total_time'] += duration
                
                if attempt > 0:
                    logger.info(f"✅ {operation_name} 在第{attempt + 1}次尝试后成功 ({duration:.3f}s)")
                else:
                    logger.debug(f"✅ {operation_name} 成功 ({duration:.3f}s)")
                
                return result
            except Exception as e:
                last_exception = e
                duration = time.time() - start_time if 'start_time' in locals() else 0
                
                # 更新统计
                self.stats['operations'] += 1
                self.stats['failed_operations'] += 1
                self.stats['total_time'] += duration
                
                if attempt < self.config.max_retries - 1:
                    delay = min(
                        self.config.base_delay * (2 ** attempt),
                        self.config.max_delay
                    )
                    logger.warning(f"⚠️ {operation_name} 第{attempt + 1}次尝试失败，{delay:.1f}秒后重试: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ {operation_name} 所有重试都失败: {e}")
        
        raise last_exception
    
    async def save_document(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """异步保存文档 - 非阻塞"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return False
        
        def _save_sync():
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.set(data)
            return True
        
        try:
            await self._retry_operation("保存文档", self._run_in_thread, _save_sync)
            return True
        except Exception as e:
            logger.error(f"❌ 保存文档失败: {e}")
            return False
    
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """异步获取文档 - 非阻塞"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return None
        
        def _get_sync():
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        
        try:
            result = await self._retry_operation("获取文档", self._run_in_thread, _get_sync)
            return result
        except Exception as e:
            logger.error(f"❌ 获取文档失败: {e}")
            return None
    
    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """异步删除文档 - 非阻塞"""
        if not self.db:
            logger.warning("Firebase未初始化")
            return False
        
        def _delete_sync():
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            return True
        
        try:
            await self._retry_operation("删除文档", self._run_in_thread, _delete_sync)
            return True
        except Exception as e:
            logger.error(f"❌ 删除文档失败: {e}")
            return False
    
    async def batch_save(self, operations: List[Dict[str, Any]]) -> bool:
        """异步批量保存 - 提高效率"""
        if not self.db or not operations:
            return False
        
        def _batch_save_sync():
            batch = self.db.batch()
            for op in operations:
                doc_ref = self.db.collection(op['collection']).document(op['doc_id'])
                batch.set(doc_ref, op['data'])
            batch.commit()
            return True
        
        try:
            await self._retry_operation("批量保存", self._run_in_thread, _batch_save_sync)
            logger.info(f"✅ 批量保存成功: {len(operations)} 个文档")
            return True
        except Exception as e:
            logger.error(f"❌ 批量保存失败: {e}")
            return False
    
    def compress_data(self, data: bytes) -> bytes:
        """压缩数据 - 减少传输量"""
        try:
            compressed = gzip.compress(data)
            compression_ratio = len(compressed) / len(data)
            logger.debug(f"✅ 数据压缩: {len(data)} -> {len(compressed)} bytes ({compression_ratio:.2f})")
            return compressed
        except Exception as e:
            logger.error(f"❌ 数据压缩失败: {e}")
            return data
    
    def decompress_data(self, compressed_data: bytes) -> bytes:
        """解压数据"""
        try:
            decompressed = gzip.decompress(compressed_data)
            logger.debug(f"✅ 数据解压: {len(compressed_data)} -> {len(decompressed)} bytes")
            return decompressed
        except Exception as e:
            logger.error(f"❌ 数据解压失败: {e}")
            return compressed_data
    
    async def save_session(self, user_id: int, session_data: bytes) -> bool:
        """保存用户会话 - 优化版本"""
        try:
            # 压缩会话数据
            compressed_data = self.compress_data(session_data)
            
            # 转换为Base64
            session_str = base64.b64encode(compressed_data).decode('utf-8')
            
            data = {
                'session_data': session_str,
                'compressed': True,
                'original_size': len(session_data),
                'compressed_size': len(compressed_data),
                'compression_ratio': len(compressed_data) / len(session_data),
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            
            return await self.save_document('sessions', str(user_id), data)
        except Exception as e:
            logger.error(f"❌ 保存会话失败: {e}")
            return False
    
    async def load_session(self, user_id: int) -> Optional[bytes]:
        """加载用户会话 - 优化版本"""
        try:
            data = await self.get_document('sessions', str(user_id))
            if not data or 'session_data' not in data:
                return None
            
            # 解码Base64
            compressed_data = base64.b64decode(data['session_data'])
            
            # 检查是否压缩
            if data.get('compressed', False):
                return self.decompress_data(compressed_data)
            else:
                return compressed_data
        except Exception as e:
            logger.error(f"❌ 加载会话失败: {e}")
            return None
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        if self.stats['operations'] == 0:
            return {"message": "暂无操作数据"}
        
        avg_time = self.stats['total_time'] / self.stats['operations']
        success_rate = self.stats['successful_operations'] / self.stats['operations'] * 100
        
        return {
            "operations": self.stats['operations'],
            "successful_operations": self.stats['successful_operations'],
            "failed_operations": self.stats['failed_operations'],
            "success_rate": f"{success_rate:.1f}%",
            "average_time": f"{avg_time:.3f}s",
            "total_time": f"{self.stats['total_time']:.3f}s"
        }
    
    def cleanup(self):
        """清理资源"""
        if self.executor:
            self.executor.shutdown(wait=True)
        logger.info("✅ Firebase管理器已清理")

# 全局优化管理器实例
optimized_firebase_manager = OptimizedFirebaseManager()

# 导出函数
async def save_document(collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
    """保存文档"""
    return await optimized_firebase_manager.save_document(collection, doc_id, data)

async def get_document(collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """获取文档"""
    return await optimized_firebase_manager.get_document(collection, doc_id)

async def save_session(user_id: int, session_data: bytes) -> bool:
    """保存会话"""
    return await optimized_firebase_manager.save_session(user_id, session_data)

async def load_session(user_id: int) -> Optional[bytes]:
    """加载会话"""
    return await optimized_firebase_manager.load_session(user_id)

def get_performance_stats() -> Dict[str, Any]:
    """获取性能统计"""
    return optimized_firebase_manager.get_performance_stats()

# 兼容性函数
def get_global_optimized_manager():
    """获取全局优化管理器"""
    return optimized_firebase_manager

async def get_doc(collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """获取文档 - 简化接口"""
    return await get_document(collection, doc_id)

async def set_doc(collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
    """设置文档 - 简化接口"""
    return await save_document(collection, doc_id, data)

async def update_doc(collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
    """更新文档 - 简化接口"""
    return await save_document(collection, doc_id, data)

async def delete_doc(collection: str, doc_id: str) -> bool:
    """删除文档 - 简化接口"""
    return await optimized_firebase_manager.delete_document(collection, doc_id)

async def start_optimization_services():
    """启动优化服务"""
    logger.info("✅ Firebase优化服务已启动")
    return True
