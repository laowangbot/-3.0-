# ==================== Firebase性能对比测试 ====================
"""
Firebase性能对比测试
对比原始实现和优化实现的性能差异
"""

import asyncio
import time
import logging
from typing import Dict, Any, List
import firebase_admin
from firebase_admin import credentials, firestore

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

class OriginalFirebaseManager:
    """原始Firebase管理器 - 有卡顿问题"""
    
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """初始化Firebase连接"""
        try:
            import json, os
            cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS', '{}'))
            cred = credentials.Certificate(cred_dict)
            
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            logger.info("✅ 原始Firebase管理器初始化成功")
        except Exception as e:
            logger.error(f"❌ Firebase初始化失败: {e}")
            self.db = None
    
    async def save_user_data(self, user_id: int, data: Dict[str, Any]):
        """保存用户数据 - 同步操作在异步函数中"""
        if not self.db:
            return False
        
        try:
            # 问题：同步操作阻塞事件循环
            doc_ref = self.db.collection('users').document(str(user_id))
            doc_ref.set(data)  # 同步操作！
            return True
        except Exception as e:
            logger.error(f"❌ 保存用户数据失败: {e}")
            return False
    
    async def load_user_data(self, user_id: int) -> Dict[str, Any]:
        """加载用户数据 - 同步操作在异步函数中"""
        if not self.db:
            return None
        
        try:
            # 问题：同步操作阻塞事件循环
            doc_ref = self.db.collection('users').document(str(user_id))
            doc = doc_ref.get()  # 同步操作！
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error(f"❌ 加载用户数据失败: {e}")
            return None

class PerformanceTest:
    """性能测试类"""
    
    def __init__(self):
        self.original_manager = OriginalFirebaseManager()
        # 导入优化管理器
        from optimized_firebase_manager import OptimizedFirebaseManager
        self.optimized_manager = OptimizedFirebaseManager()
    
    async def test_single_operation(self, manager, manager_name: str, operation: str):
        """测试单个操作"""
        test_data = {
            'user_id': 123456789,
            'name': '测试用户',
            'timestamp': time.time(),
            'data': 'x' * 1000  # 1KB测试数据
        }
        
        start_time = time.time()
        
        if operation == 'save':
            if manager_name == 'original':
                success = await manager.save_user_data(123456789, test_data)
            else:
                success = await manager.save_document('users', '123456789', test_data)
        elif operation == 'load':
            if manager_name == 'original':
                data = await manager.load_user_data(123456789)
            else:
                data = await manager.get_document('users', '123456789')
            success = data is not None
        
        duration = time.time() - start_time
        
        return {
            'manager': manager_name,
            'operation': operation,
            'duration': duration,
            'success': success
        }
    
    async def test_concurrent_operations(self, manager, manager_name: str, num_operations: int = 10):
        """测试并发操作"""
        tasks = []
        
        for i in range(num_operations):
            test_data = {
                'user_id': i,
                'name': f'并发测试用户{i}',
                'timestamp': time.time(),
                'data': 'x' * 1000
            }
            
            if manager_name == 'original':
                task = manager.save_user_data(i, test_data)
            else:
                task = manager.save_document('users', str(i), test_data)
            
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_duration = time.time() - start_time
        
        successful_operations = sum(1 for r in results if r is True)
        failed_operations = len(results) - successful_operations
        
        return {
            'manager': manager_name,
            'total_operations': num_operations,
            'successful_operations': successful_operations,
            'failed_operations': failed_operations,
            'total_duration': total_duration,
            'avg_duration_per_operation': total_duration / num_operations,
            'operations_per_second': num_operations / total_duration
        }
    
    async def test_session_compression(self):
        """测试会话压缩性能"""
        # 模拟会话数据
        session_data = b"test_session_data_" * 1000  # 约17KB
        
        # 测试压缩
        start_time = time.time()
        compressed = self.optimized_manager.compress_data(session_data)
        compression_time = time.time() - start_time
        
        # 测试解压
        start_time = time.time()
        decompressed = self.optimized_manager.decompress_data(compressed)
        decompression_time = time.time() - start_time
        
        compression_ratio = len(compressed) / len(session_data)
        
        return {
            'original_size': len(session_data),
            'compressed_size': len(compressed),
            'compression_ratio': compression_ratio,
            'compression_time': compression_time,
            'decompression_time': decompression_time,
            'space_saved_percent': (1 - compression_ratio) * 100
        }
    
    async def run_comprehensive_test(self):
        """运行综合性能测试"""
        print("🚀 开始Firebase性能对比测试...\n")
        
        # 测试1: 单个操作性能
        print("📊 测试1: 单个操作性能")
        print("-" * 50)
        
        # 原始管理器保存
        result1 = await self.test_single_operation(self.original_manager, 'original', 'save')
        print(f"原始管理器保存: {result1['duration']:.3f}秒 ({'✅' if result1['success'] else '❌'})")
        
        # 优化管理器保存
        result2 = await self.test_single_operation(self.optimized_manager, 'optimized', 'save')
        print(f"优化管理器保存: {result2['duration']:.3f}秒 ({'✅' if result2['success'] else '❌'})")
        
        # 原始管理器加载
        result3 = await self.test_single_operation(self.original_manager, 'original', 'load')
        print(f"原始管理器加载: {result3['duration']:.3f}秒 ({'✅' if result3['success'] else '❌'})")
        
        # 优化管理器加载
        result4 = await self.test_single_operation(self.optimized_manager, 'optimized', 'load')
        print(f"优化管理器加载: {result4['duration']:.3f}秒 ({'✅' if result4['success'] else '❌'})")
        
        print()
        
        # 测试2: 并发操作性能
        print("📊 测试2: 并发操作性能 (10个并发操作)")
        print("-" * 50)
        
        # 原始管理器并发测试
        result5 = await self.test_concurrent_operations(self.original_manager, 'original', 10)
        print(f"原始管理器并发:")
        print(f"  总耗时: {result5['total_duration']:.3f}秒")
        print(f"  成功率: {result5['successful_operations']}/{result5['total_operations']}")
        print(f"  平均每操作: {result5['avg_duration_per_operation']:.3f}秒")
        print(f"  操作/秒: {result5['operations_per_second']:.2f}")
        
        # 优化管理器并发测试
        result6 = await self.test_concurrent_operations(self.optimized_manager, 'optimized', 10)
        print(f"优化管理器并发:")
        print(f"  总耗时: {result6['total_duration']:.3f}秒")
        print(f"  成功率: {result6['successful_operations']}/{result6['total_operations']}")
        print(f"  平均每操作: {result6['avg_duration_per_operation']:.3f}秒")
        print(f"  操作/秒: {result6['operations_per_second']:.2f}")
        
        print()
        
        # 测试3: 会话压缩性能
        print("📊 测试3: 会话压缩性能")
        print("-" * 50)
        
        compression_result = await self.test_session_compression()
        print(f"原始大小: {compression_result['original_size']} bytes")
        print(f"压缩后大小: {compression_result['compressed_size']} bytes")
        print(f"压缩率: {compression_result['compression_ratio']:.2f}")
        print(f"空间节省: {compression_result['space_saved_percent']:.1f}%")
        print(f"压缩时间: {compression_result['compression_time']:.3f}秒")
        print(f"解压时间: {compression_result['decompression_time']:.3f}秒")
        
        print()
        
        # 测试4: 性能统计
        print("📊 测试4: 性能统计")
        print("-" * 50)
        
        stats = self.optimized_manager.get_performance_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")
        
        print()
        
        # 性能对比总结
        print("📈 性能对比总结")
        print("=" * 50)
        
        save_improvement = (result1['duration'] - result2['duration']) / result1['duration'] * 100
        load_improvement = (result3['duration'] - result4['duration']) / result3['duration'] * 100
        concurrent_improvement = (result5['total_duration'] - result6['total_duration']) / result5['total_duration'] * 100
        
        print(f"保存操作性能提升: {save_improvement:.1f}%")
        print(f"加载操作性能提升: {load_improvement:.1f}%")
        print(f"并发操作性能提升: {concurrent_improvement:.1f}%")
        print(f"会话数据压缩节省: {compression_result['space_saved_percent']:.1f}%")
        
        # 清理测试数据
        print("\n🧹 清理测试数据...")
        for i in range(10):
            await self.optimized_manager.delete_document('users', str(i))
        await self.optimized_manager.delete_document('users', '123456789')
        
        print("✅ 性能测试完成")

# 运行测试
if __name__ == "__main__":
    async def main():
        test = PerformanceTest()
        await test.run_comprehensive_test()
    
    asyncio.run(main())
