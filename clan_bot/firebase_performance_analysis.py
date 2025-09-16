# ==================== Firebase性能分析和优化 ====================
"""
Firebase性能分析和优化方案
分析可能导致卡顿的问题并提供解决方案
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import firebase_admin
from firebase_admin import credentials, firestore

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

@dataclass
class PerformanceMetrics:
    """性能指标"""
    operation: str
    duration: float
    success: bool
    error: Optional[str] = None

class FirebasePerformanceAnalyzer:
    """Firebase性能分析器"""
    
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    def analyze_current_issues(self) -> Dict[str, Any]:
        """分析当前代码中的性能问题"""
        
        issues = {
            "critical_issues": [],
            "performance_bottlenecks": [],
            "optimization_suggestions": []
        }
        
        # 问题1: 同步Firebase操作在异步函数中
        issues["critical_issues"].append({
            "issue": "同步Firebase操作阻塞异步事件循环",
            "location": "multi_bot_deployment.py:58-59",
            "code": "doc_ref.set(data)  # 同步操作",
            "impact": "高 - 会阻塞整个事件循环",
            "solution": "使用线程池执行同步操作"
        })
        
        # 问题2: 每次操作都创建新的连接
        issues["critical_issues"].append({
            "issue": "重复的Firebase连接创建",
            "location": "multi_bot_deployment.py:44-45",
            "code": "firebase_admin.initialize_app(cred)",
            "impact": "中 - 增加延迟和资源消耗",
            "solution": "使用单例模式管理连接"
        })
        
        # 问题3: 没有连接池和重试机制
        issues["performance_bottlenecks"].append({
            "issue": "缺乏连接池和重试机制",
            "impact": "中 - 网络故障时无自动恢复",
            "solution": "实现连接池和指数退避重试"
        })
        
        # 问题4: 会话数据没有压缩
        issues["performance_bottlenecks"].append({
            "issue": "会话数据未压缩，传输量大",
            "location": "multi_bot_deployment.py:88-90",
            "code": "base64.b64encode(session_data)",
            "impact": "中 - 增加网络传输时间",
            "solution": "使用gzip压缩会话数据"
        })
        
        # 问题5: 没有批量操作优化
        issues["performance_bottlenecks"].append({
            "issue": "单条操作，没有批量优化",
            "impact": "中 - 增加API调用次数",
            "solution": "实现批量写入和读取"
        })
        
        return issues
    
    def measure_operation_time(self, operation_name: str, func, *args, **kwargs):
        """测量操作执行时间"""
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            success = True
            error = None
        except Exception as e:
            duration = time.time() - start_time
            success = False
            error = str(e)
            result = None
        
        metric = PerformanceMetrics(
            operation=operation_name,
            duration=duration,
            success=success,
            error=error
        )
        self.metrics.append(metric)
        
        return result, metric
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        if not self.metrics:
            return {"message": "暂无性能数据"}
        
        total_operations = len(self.metrics)
        successful_operations = sum(1 for m in self.metrics if m.success)
        failed_operations = total_operations - successful_operations
        
        avg_duration = sum(m.duration for m in self.metrics) / total_operations
        max_duration = max(m.duration for m in self.metrics)
        min_duration = min(m.duration for m in self.metrics)
        
        # 按操作类型分组
        operation_stats = {}
        for metric in self.metrics:
            if metric.operation not in operation_stats:
                operation_stats[metric.operation] = {
                    'count': 0,
                    'total_time': 0,
                    'avg_time': 0,
                    'max_time': 0,
                    'min_time': float('inf'),
                    'success_rate': 0
                }
            
            stats = operation_stats[metric.operation]
            stats['count'] += 1
            stats['total_time'] += metric.duration
            stats['max_time'] = max(stats['max_time'], metric.duration)
            stats['min_time'] = min(stats['min_time'], metric.duration)
            if metric.success:
                stats['success_rate'] += 1
        
        # 计算平均值
        for stats in operation_stats.values():
            stats['avg_time'] = stats['total_time'] / stats['count']
            stats['success_rate'] = stats['success_rate'] / stats['count'] * 100
        
        return {
            "summary": {
                "total_operations": total_operations,
                "successful_operations": successful_operations,
                "failed_operations": failed_operations,
                "success_rate": successful_operations / total_operations * 100,
                "avg_duration": avg_duration,
                "max_duration": max_duration,
                "min_duration": min_duration
            },
            "operation_breakdown": operation_stats,
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成性能优化建议"""
        recommendations = []
        
        if self.metrics:
            avg_duration = sum(m.duration for m in self.metrics) / len(self.metrics)
            
            if avg_duration > 1.0:
                recommendations.append("平均操作时间超过1秒，建议使用异步操作和缓存")
            
            if avg_duration > 0.5:
                recommendations.append("平均操作时间超过500ms，建议实现批量操作")
            
            failed_rate = sum(1 for m in self.metrics if not m.success) / len(self.metrics)
            if failed_rate > 0.1:
                recommendations.append("失败率超过10%，建议添加重试机制")
        
        return recommendations

class OptimizedFirebaseManager:
    """优化的Firebase管理器"""
    
    def __init__(self, credentials_path: str = None):
        """初始化优化的Firebase管理器"""
        self.db = None
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.connection_pool = {}
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1.0,
            'max_delay': 10.0
        }
        
        # 初始化Firebase连接
        self._initialize_firebase(credentials_path)
    
    def _initialize_firebase(self, credentials_path: str = None):
        """初始化Firebase连接"""
        try:
            if credentials_path:
                cred = credentials.Certificate(credentials_path)
            else:
                import json, os
                cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS', '{}'))
                cred = credentials.Certificate(cred_dict)
            
            # 检查是否已经初始化
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            logger.info("✅ 优化的Firebase管理器初始化成功")
        except Exception as e:
            logger.error(f"❌ Firebase初始化失败: {e}")
            self.db = None
    
    async def _run_in_thread(self, func, *args, **kwargs):
        """在线程池中运行同步函数"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args, **kwargs)
    
    async def _retry_operation(self, operation_name: str, func, *args, **kwargs):
        """带重试机制的操作"""
        last_exception = None
        
        for attempt in range(self.retry_config['max_retries']):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"✅ {operation_name} 在第{attempt + 1}次尝试后成功")
                return result
            except Exception as e:
                last_exception = e
                if attempt < self.retry_config['max_retries'] - 1:
                    delay = min(
                        self.retry_config['base_delay'] * (2 ** attempt),
                        self.retry_config['max_delay']
                    )
                    logger.warning(f"⚠️ {operation_name} 第{attempt + 1}次尝试失败，{delay}秒后重试: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ {operation_name} 所有重试都失败: {e}")
        
        raise last_exception
    
    async def save_document_async(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """异步保存文档"""
        if not self.db:
            return False
        
        def _save_sync():
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.set(data)
            return True
        
        try:
            await self._retry_operation("保存文档", self._run_in_thread, _save_sync)
            return True
        except Exception as e:
            logger.error(f"❌ 异步保存文档失败: {e}")
            return False
    
    async def get_document_async(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """异步获取文档"""
        if not self.db:
            return None
        
        def _get_sync():
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        
        try:
            result = await self._retry_operation("获取文档", self._run_in_thread, _get_sync)
            return result
        except Exception as e:
            logger.error(f"❌ 异步获取文档失败: {e}")
            return None
    
    async def batch_save_async(self, operations: List[Dict[str, Any]]) -> bool:
        """异步批量保存"""
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
            return True
        except Exception as e:
            logger.error(f"❌ 异步批量保存失败: {e}")
            return False
    
    def compress_session_data(self, session_data: bytes) -> bytes:
        """压缩会话数据"""
        import gzip
        try:
            compressed = gzip.compress(session_data)
            logger.debug(f"✅ 会话数据压缩: {len(session_data)} -> {len(compressed)} bytes")
            return compressed
        except Exception as e:
            logger.error(f"❌ 会话数据压缩失败: {e}")
            return session_data
    
    def decompress_session_data(self, compressed_data: bytes) -> bytes:
        """解压会话数据"""
        import gzip
        try:
            decompressed = gzip.decompress(compressed_data)
            logger.debug(f"✅ 会话数据解压: {len(compressed_data)} -> {len(decompressed)} bytes")
            return decompressed
        except Exception as e:
            logger.error(f"❌ 会话数据解压失败: {e}")
            return compressed_data
    
    async def save_session_optimized(self, user_id: int, session_data: bytes) -> bool:
        """优化的会话保存"""
        try:
            # 压缩会话数据
            compressed_data = self.compress_session_data(session_data)
            
            # 转换为Base64
            import base64
            session_str = base64.b64encode(compressed_data).decode('utf-8')
            
            data = {
                'session_data': session_str,
                'compressed': True,
                'original_size': len(session_data),
                'compressed_size': len(compressed_data),
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            
            return await self.save_document_async('sessions', str(user_id), data)
        except Exception as e:
            logger.error(f"❌ 优化会话保存失败: {e}")
            return False
    
    async def load_session_optimized(self, user_id: int) -> Optional[bytes]:
        """优化的会话加载"""
        try:
            data = await self.get_document_async('sessions', str(user_id))
            if not data or 'session_data' not in data:
                return None
            
            # 解码Base64
            import base64
            compressed_data = base64.b64decode(data['session_data'])
            
            # 检查是否压缩
            if data.get('compressed', False):
                return self.decompress_session_data(compressed_data)
            else:
                return compressed_data
        except Exception as e:
            logger.error(f"❌ 优化会话加载失败: {e}")
            return None
    
    def cleanup(self):
        """清理资源"""
        if self.executor:
            self.executor.shutdown(wait=True)

# 性能测试函数
async def performance_test():
    """性能测试"""
    analyzer = FirebasePerformanceAnalyzer()
    manager = OptimizedFirebaseManager()
    
    # 测试数据
    test_data = {
        'user_id': 123456789,
        'name': '测试用户',
        'timestamp': time.time()
    }
    
    # 测试保存操作
    start_time = time.time()
    success = await manager.save_document_async('test_users', '123456789', test_data)
    save_time = time.time() - start_time
    
    # 测试读取操作
    start_time = time.time()
    data = await manager.get_document_async('test_users', '123456789')
    read_time = time.time() - start_time
    
    # 测试会话压缩
    session_data = b"test_session_data_" * 100  # 模拟会话数据
    start_time = time.time()
    compressed = manager.compress_session_data(session_data)
    compression_time = time.time() - start_time
    
    print(f"性能测试结果:")
    print(f"保存操作: {save_time:.3f}秒 ({'成功' if success else '失败'})")
    print(f"读取操作: {read_time:.3f}秒 ({'成功' if data else '失败'})")
    print(f"压缩操作: {compression_time:.3f}秒")
    print(f"压缩率: {len(compressed)/len(session_data)*100:.1f}%")
    
    # 生成性能报告
    report = analyzer.get_performance_report()
    print(f"性能报告: {report}")
    
    manager.cleanup()

if __name__ == "__main__":
    asyncio.run(performance_test())
