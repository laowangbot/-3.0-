#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firebase优化效果测试脚本
测试集成后的Firebase优化系统是否正常工作
"""

import asyncio
import logging
import time
from datetime import datetime
from config import get_config
from optimized_firebase_manager import get_global_optimized_manager, start_optimization_services, get_optimization_stats

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_firebase_optimization():
    """测试Firebase优化效果"""
    logger.info("🚀 开始测试Firebase优化系统...")
    
    # 获取配置
    config = get_config()
    bot_id = config.get('bot_id', 'test_bot')
    
    try:
        # 1. 启动优化服务
        logger.info("📡 启动Firebase优化服务...")
        await start_optimization_services(bot_id)
        logger.info("✅ Firebase优化服务启动成功")
        
        # 2. 获取优化管理器
        manager = get_global_optimized_manager(bot_id)
        if not manager:
            logger.error("❌ 无法获取优化管理器")
            return False
        
        # 3. 测试基本操作
        logger.info("🔧 测试基本Firebase操作...")
        
        # 测试文档写入
        test_data = {
            'test_field': 'optimization_test',
            'timestamp': datetime.now().isoformat(),
            'bot_id': bot_id
        }
        
        # 写入测试文档
        success = await manager.set_document('test_collection', 'test_doc', test_data)
        if success:
            logger.info("✅ 文档写入测试成功")
        else:
            logger.error("❌ 文档写入测试失败")
            return False
        
        # 读取测试文档
        read_data = await manager.get_document('test_collection', 'test_doc')
        if read_data and read_data.get('test_field') == 'optimization_test':
            logger.info("✅ 文档读取测试成功")
        else:
            logger.error("❌ 文档读取测试失败")
            return False
        
        # 4. 测试批量操作
        logger.info("📦 测试批量操作...")
        
        # 添加多个操作到批量队列
        for i in range(10):
            batch_data = {
                'batch_test': f'batch_item_{i}',
                'timestamp': datetime.now().isoformat(),
                'index': i
            }
            await manager.set_document('batch_test', f'item_{i}', batch_data)
        
        logger.info("✅ 批量操作添加完成，等待批量处理...")
        
        # 等待批量处理
        await asyncio.sleep(2)
        
        # 5. 获取优化统计
        logger.info("📊 获取优化统计信息...")
        stats = get_optimization_stats(bot_id)
        
        logger.info("=" * 50)
        logger.info("📈 Firebase优化统计报告")
        logger.info("=" * 50)
        
        # 批量存储统计
        if 'batch_storage' in stats:
            batch_stats = stats['batch_storage']
            logger.info(f"📦 批量存储:")
            logger.info(f"   总操作数: {batch_stats.get('total_operations', 0)}")
            logger.info(f"   批量操作数: {batch_stats.get('batch_operations', 0)}")
            logger.info(f"   待处理操作: {batch_stats.get('pending_count', 0)}")
            logger.info(f"   失败操作: {batch_stats.get('failed_operations', 0)}")
            logger.info(f"   运行状态: {'运行中' if batch_stats.get('running') else '已停止'}")
        
        # 缓存统计
        if 'cache' in stats:
            cache_stats = stats['cache']
            logger.info(f"💾 缓存系统:")
            logger.info(f"   缓存大小: {cache_stats.get('cache_size', 0)}")
            logger.info(f"   缓存命中率: {cache_stats.get('hit_rate', 0):.2%}")
            logger.info(f"   缓存命中: {cache_stats.get('cache_hits', 0)}")
            logger.info(f"   缓存未命中: {cache_stats.get('cache_misses', 0)}")
            logger.info(f"   API调用节省: {cache_stats.get('api_calls_saved', 0)}")
        
        # 配额监控统计
        if 'quota' in stats:
            quota_stats = stats['quota']
            logger.info(f"📊 配额监控:")
            current_usage = quota_stats.get('current_usage', {})
            usage_percentages = quota_stats.get('usage_percentages', {})
            
            logger.info(f"   今日使用量:")
            logger.info(f"     读取: {current_usage.get('reads_today', 0)} ({usage_percentages.get('reads_daily', 0):.2f}%)")
            logger.info(f"     写入: {current_usage.get('writes_today', 0)} ({usage_percentages.get('writes_daily', 0):.2f}%)")
            logger.info(f"     删除: {current_usage.get('deletes_today', 0)} ({usage_percentages.get('deletes_daily', 0):.2f}%)")
            
            logger.info(f"   当前分钟使用量:")
            logger.info(f"     读取: {current_usage.get('reads_this_minute', 0)} ({usage_percentages.get('reads_minute', 0):.2f}%)")
            logger.info(f"     写入: {current_usage.get('writes_this_minute', 0)} ({usage_percentages.get('writes_minute', 0):.2f}%)")
            logger.info(f"     删除: {current_usage.get('deletes_this_minute', 0)} ({usage_percentages.get('deletes_minute', 0):.2f}%)")
        
        # 6. 性能测试
        logger.info("⚡ 性能测试...")
        
        # 测试缓存效果
        start_time = time.time()
        for i in range(5):
            await manager.get_document('test_collection', 'test_doc')
        cache_time = time.time() - start_time
        
        logger.info(f"💾 缓存性能测试:")
        logger.info(f"   5次读取耗时: {cache_time:.3f}秒")
        logger.info(f"   平均每次: {cache_time/5:.3f}秒")
        
        # 7. 清理测试数据
        logger.info("🧹 清理测试数据...")
        await manager.delete_document('test_collection', 'test_doc')
        
        for i in range(10):
            await manager.delete_document('batch_test', f'item_{i}')
        
        logger.info("✅ 测试数据清理完成")
        
        logger.info("=" * 50)
        logger.info("🎉 Firebase优化系统测试完成！")
        logger.info("=" * 50)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        return False

async def main():
    """主函数"""
    logger.info("🔧 Firebase优化系统测试工具")
    logger.info("=" * 50)
    
    # 检查配置
    config = get_config()
    if not config.get('firebase_credentials'):
        logger.error("❌ 未配置Firebase凭据，请检查.env文件")
        return
    
    if not config.get('firebase_project_id'):
        logger.error("❌ 未配置Firebase项目ID，请检查.env文件")
        return
    
    # 运行测试
    success = await test_firebase_optimization()
    
    if success:
        logger.info("✅ 所有测试通过！Firebase优化系统工作正常")
    else:
        logger.error("❌ 测试失败，请检查配置和网络连接")

if __name__ == "__main__":
    asyncio.run(main())
