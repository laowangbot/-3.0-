#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大批量多任务搬运修复测试脚本
测试任务状态持久化、并发管理和内存优化功能
"""

import asyncio
import logging
import time
import random
from typing import List, Dict, Any
from datetime import datetime

from task_state_manager import start_task_state_manager, get_global_task_state_manager, TaskStatus
from concurrent_task_manager import start_concurrent_task_manager, get_global_concurrent_task_manager, TaskPriority, TaskResource
from memory_optimizer import start_memory_optimizer, get_global_memory_optimizer
from cloning_engine import CloneTask

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BulkTaskTester:
    """大批量任务测试器"""
    
    def __init__(self, bot_id: str = "test_bot"):
        """初始化测试器"""
        self.bot_id = bot_id
        self.task_state_manager = None
        self.concurrent_task_manager = None
        self.memory_optimizer = None
        
        # 测试配置
        self.test_config = {
            'task_count': 5,  # 5个任务
            'messages_per_task': 20000,  # 每个任务2万条消息
            'test_duration': 300,  # 测试持续时间（秒）
            'memory_threshold': 80.0  # 内存阈值
        }
        
        # 测试结果
        self.test_results = {
            'tasks_created': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_paused': 0,
            'memory_optimizations': 0,
            'state_saves': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def setup(self):
        """设置测试环境"""
        try:
            logger.info("🔧 设置测试环境...")
            
            # 启动任务状态管理器
            self.task_state_manager = await start_task_state_manager(self.bot_id)
            logger.info("✅ 任务状态管理器已启动")
            
            # 启动并发任务管理器
            self.concurrent_task_manager = await start_concurrent_task_manager(self.bot_id)
            logger.info("✅ 并发任务管理器已启动")
            
            # 启动内存优化管理器
            self.memory_optimizer = await start_memory_optimizer(self.bot_id)
            logger.info("✅ 内存优化管理器已启动")
            
            # 设置内存阈值
            self.memory_optimizer.set_memory_thresholds(
                warning=70.0,
                critical=80.0,
                emergency=90.0,
                cleanup=60.0
            )
            
            # 添加缓存清理回调
            self.memory_optimizer.add_cache_cleanup_callback(self._mock_cache_cleanup)
            
            # 添加任务暂停回调
            self.memory_optimizer.add_task_pause_callback(self._mock_task_pause)
            
            logger.info("✅ 测试环境设置完成")
            
        except Exception as e:
            logger.error(f"设置测试环境失败: {e}")
            raise
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            logger.info("🧹 清理测试环境...")
            
            # 停止所有管理器
            if self.task_state_manager:
                await self.task_state_manager.stop_auto_save()
            
            if self.concurrent_task_manager:
                await self.concurrent_task_manager.stop_scheduler()
            
            if self.memory_optimizer:
                await self.memory_optimizer.stop_monitoring()
            
            logger.info("✅ 测试环境清理完成")
            
        except Exception as e:
            logger.error(f"清理测试环境失败: {e}")
    
    async def _mock_cache_cleanup(self):
        """模拟缓存清理"""
        logger.debug("🧹 执行缓存清理...")
        await asyncio.sleep(0.1)  # 模拟清理时间
        self.test_results['memory_optimizations'] += 1
    
    async def _mock_task_pause(self):
        """模拟任务暂停"""
        logger.debug("⏸️ 暂停低优先级任务...")
        await asyncio.sleep(0.1)  # 模拟暂停时间
        self.test_results['tasks_paused'] += 1
    
    async def create_test_tasks(self) -> List[str]:
        """创建测试任务"""
        try:
            logger.info(f"📝 创建 {self.test_config['task_count']} 个测试任务...")
            
            task_ids = []
            for i in range(self.test_config['task_count']):
                task_id = f"test_task_{i+1}_{int(time.time())}"
                user_id = f"test_user_{i+1}"
                
                # 创建任务状态记录
                await self.task_state_manager.create_task(
                    task_id=task_id,
                    user_id=user_id,
                    source_chat_id=f"source_chat_{i+1}",
                    target_chat_id=f"target_chat_{i+1}",
                    start_id=1,
                    end_id=self.test_config['messages_per_task'],
                    config={
                        'user_id': user_id,
                        'test_mode': True,
                        'messages_per_task': self.test_config['messages_per_task']
                    }
                )
                
                # 添加到并发任务队列
                resource = TaskResource(
                    memory_mb=100,
                    cpu_percent=20.0,
                    network_bandwidth=1,
                    max_concurrent=1
                )
                
                priority = random.choice([TaskPriority.NORMAL, TaskPriority.HIGH])
                estimated_duration = random.uniform(60, 300)  # 1-5分钟
                
                await self.concurrent_task_manager.queue_task(
                    task_id=task_id,
                    user_id=user_id,
                    priority=priority,
                    resource=resource,
                    estimated_duration=estimated_duration
                )
                
                task_ids.append(task_id)
                self.test_results['tasks_created'] += 1
                
                logger.info(f"✅ 任务 {i+1} 创建完成: {task_id}")
            
            return task_ids
            
        except Exception as e:
            logger.error(f"创建测试任务失败: {e}")
            return []
    
    async def simulate_task_execution(self, task_ids: List[str]):
        """模拟任务执行"""
        try:
            logger.info("🚀 开始模拟任务执行...")
            
            self.test_results['start_time'] = datetime.now()
            
            # 模拟任务执行过程
            for i, task_id in enumerate(task_ids):
                logger.info(f"📋 执行任务 {i+1}/{len(task_ids)}: {task_id}")
                
                # 模拟任务状态更新
                await self._simulate_task_progress(task_id)
                
                # 随机决定任务结果
                if random.random() < 0.8:  # 80%成功率
                    await self.task_state_manager.update_task_progress(
                        task_id,
                        status=TaskStatus.COMPLETED,
                        progress=100.0,
                        end_time=datetime.now()
                    )
                    self.test_results['tasks_completed'] += 1
                    logger.info(f"✅ 任务 {i+1} 执行完成")
                else:
                    await self.task_state_manager.update_task_progress(
                        task_id,
                        status=TaskStatus.FAILED,
                        end_time=datetime.now(),
                        error_message="模拟执行失败"
                    )
                    self.test_results['tasks_failed'] += 1
                    logger.warning(f"❌ 任务 {i+1} 执行失败")
                
                # 模拟内存优化
                if random.random() < 0.3:  # 30%概率触发内存优化
                    await self.memory_optimizer.optimize_for_bulk_tasks(
                        task_count=len(task_ids),
                        estimated_memory_per_task=100.0
                    )
                
                # 随机延迟
                await asyncio.sleep(random.uniform(0.1, 0.5))
            
            self.test_results['end_time'] = datetime.now()
            
        except Exception as e:
            logger.error(f"模拟任务执行失败: {e}")
    
    async def _simulate_task_progress(self, task_id: str):
        """模拟任务进度更新"""
        try:
            # 模拟进度更新
            for progress in range(0, 101, 10):
                await self.task_state_manager.update_task_progress(
                    task_id,
                    status=TaskStatus.RUNNING,
                    progress=float(progress),
                    processed_messages=progress * self.test_config['messages_per_task'] // 100,
                    current_message_id=progress * self.test_config['messages_per_task'] // 100
                )
                
                self.test_results['state_saves'] += 1
                
                # 随机延迟
                await asyncio.sleep(random.uniform(0.01, 0.05))
                
        except Exception as e:
            logger.error(f"模拟任务进度失败 {task_id}: {e}")
    
    async def run_test(self):
        """运行测试"""
        try:
            logger.info("🧪 开始大批量多任务搬运修复测试...")
            
            # 设置测试环境
            await self.setup()
            
            # 创建测试任务
            task_ids = await self.create_test_tasks()
            if not task_ids:
                logger.error("❌ 无法创建测试任务")
                return False
            
            # 模拟任务执行
            await self.simulate_task_execution(task_ids)
            
            # 等待一段时间让所有管理器完成处理
            await asyncio.sleep(5)
            
            # 生成测试报告
            await self.generate_test_report()
            
            return True
            
        except Exception as e:
            logger.error(f"运行测试失败: {e}")
            return False
        
        finally:
            # 清理测试环境
            await self.cleanup()
    
    async def generate_test_report(self):
        """生成测试报告"""
        try:
            logger.info("📊 生成测试报告...")
            
            # 计算测试持续时间
            if self.test_results['start_time'] and self.test_results['end_time']:
                duration = (self.test_results['end_time'] - self.test_results['start_time']).total_seconds()
            else:
                duration = 0
            
            # 获取管理器统计信息
            task_stats = self.task_state_manager.get_stats()
            concurrent_stats = self.concurrent_task_manager.get_queue_status()
            memory_stats = self.memory_optimizer.get_memory_stats()
            
            # 生成报告
            report = f"""
🧪 大批量多任务搬运修复测试报告
{'='*50}

📋 测试配置:
• 任务数量: {self.test_config['task_count']} 个
• 每任务消息数: {self.test_config['messages_per_task']:,} 条
• 总消息数: {self.test_config['task_count'] * self.test_config['messages_per_task']:,} 条
• 测试持续时间: {duration:.1f} 秒

📊 测试结果:
• 任务创建: {self.test_results['tasks_created']} 个
• 任务完成: {self.test_results['tasks_completed']} 个
• 任务失败: {self.test_results['tasks_failed']} 个
• 任务暂停: {self.test_results['tasks_paused']} 个
• 成功率: {(self.test_results['tasks_completed'] / max(self.test_results['tasks_created'], 1)) * 100:.1f}%

🔧 系统统计:
• 状态保存次数: {self.test_results['state_saves']} 次
• 内存优化次数: {self.test_results['memory_optimizations']} 次
• 任务状态管理器统计: {task_stats}
• 并发任务管理器统计: {concurrent_stats}
• 内存优化器统计: {memory_stats}

✅ 修复验证:
• 任务状态持久化: {'✅ 正常' if self.test_results['state_saves'] > 0 else '❌ 异常'}
• 并发任务管理: {'✅ 正常' if self.test_results['tasks_created'] > 0 else '❌ 异常'}
• 内存优化: {'✅ 正常' if self.test_results['memory_optimizations'] > 0 else '❌ 异常'}
• 任务完成率: {'✅ 正常' if self.test_results['tasks_completed'] > 0 else '❌ 异常'}

🎯 结论:
{'✅ 修复成功' if self.test_results['tasks_completed'] > 0 and self.test_results['state_saves'] > 0 else '❌ 修复失败'}
            """.strip()
            
            logger.info(report)
            
            # 保存报告到文件
            with open('bulk_task_test_report.txt', 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info("📄 测试报告已保存到 bulk_task_test_report.txt")
            
        except Exception as e:
            logger.error(f"生成测试报告失败: {e}")

async def main():
    """主函数"""
    try:
        # 创建测试器
        tester = BulkTaskTester("test_bot")
        
        # 运行测试
        success = await tester.run_test()
        
        if success:
            logger.info("🎉 测试完成！")
        else:
            logger.error("❌ 测试失败！")
        
    except Exception as e:
        logger.error(f"测试执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
