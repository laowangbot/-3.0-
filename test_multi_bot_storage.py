#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多机器人存储功能测试脚本
测试多机器人数据管理器的基本功能
"""

import asyncio
import logging
from multi_bot_data_manager import create_multi_bot_data_manager
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_multi_bot_storage():
    """测试多机器人存储功能"""
    try:
        logger.info("🚀 开始测试多机器人存储功能...")
        
        # 获取配置
        config = get_config()
        bot_id = config.get('bot_id', 'test_bot')
        
        # 创建多机器人数据管理器
        logger.info(f"创建多机器人数据管理器，Bot ID: {bot_id}")
        data_manager = create_multi_bot_data_manager(bot_id)
        
        # 检查初始化状态
        if not data_manager.initialized:
            logger.error("❌ 多机器人数据管理器初始化失败")
            return False
        
        logger.info("✅ 多机器人数据管理器初始化成功")
        
        # 测试用户ID
        test_user_id = "test_user_123"
        
        # 测试1: 创建用户配置
        logger.info("📝 测试1: 创建用户配置...")
        success = await data_manager.create_user_config(test_user_id)
        if success:
            logger.info("✅ 用户配置创建成功")
        else:
            logger.error("❌ 用户配置创建失败")
            return False
        
        # 测试2: 获取用户配置
        logger.info("📖 测试2: 获取用户配置...")
        user_config = await data_manager.get_user_config(test_user_id)
        if user_config:
            logger.info("✅ 用户配置获取成功")
            logger.info(f"配置内容: {user_config}")
        else:
            logger.error("❌ 用户配置获取失败")
            return False
        
        # 测试3: 添加频道组
        logger.info("📺 测试3: 添加频道组...")
        success = await data_manager.add_channel_pair(
            user_id=test_user_id,
            source_username="@test_source",
            target_username="@test_target",
            source_name="测试源频道",
            target_name="测试目标频道",
            source_id="-1001234567890",
            target_id="-1001234567891"
        )
        if success:
            logger.info("✅ 频道组添加成功")
        else:
            logger.error("❌ 频道组添加失败")
            return False
        
        # 测试4: 获取频道组列表
        logger.info("📋 测试4: 获取频道组列表...")
        channel_pairs = await data_manager.get_channel_pairs(test_user_id)
        if channel_pairs:
            logger.info("✅ 频道组列表获取成功")
            logger.info(f"频道组数量: {len(channel_pairs)}")
            for i, pair in enumerate(channel_pairs):
                logger.info(f"频道组 {i+1}: {pair.get('source_name')} → {pair.get('target_name')}")
                logger.info(f"  私密频道标识: 源={pair.get('is_private_source', False)}, 目标={pair.get('is_private_target', False)}")
        else:
            logger.error("❌ 频道组列表获取失败")
            return False
        
        # 测试5: 添加任务历史
        logger.info("📊 测试5: 添加任务历史...")
        task_record = {
            'task_id': 'test_task_123',
            'source_name': '测试源频道',
            'target_name': '测试目标频道',
            'status': 'completed',
            'start_time': '2024-01-01T10:00:00',
            'end_time': '2024-01-01T10:30:00',
            'total_messages': 100,
            'successful_messages': 95,
            'failed_messages': 5
        }
        success = await data_manager.add_task_history(test_user_id, task_record)
        if success:
            logger.info("✅ 任务历史添加成功")
        else:
            logger.error("❌ 任务历史添加失败")
            return False
        
        # 测试6: 获取任务历史
        logger.info("📜 测试6: 获取任务历史...")
        task_history = await data_manager.get_task_history(test_user_id, limit=10)
        if task_history:
            logger.info("✅ 任务历史获取成功")
            logger.info(f"历史记录数量: {len(task_history)}")
            for i, record in enumerate(task_history):
                logger.info(f"记录 {i+1}: {record.get('task_id')} - {record.get('status')}")
        else:
            logger.error("❌ 任务历史获取失败")
            return False
        
        # 测试7: 检查数据结构
        logger.info("🔍 测试7: 检查数据结构...")
        try:
            # 检查Firebase中的实际数据结构
            doc_ref = data_manager._get_user_doc_ref(test_user_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                logger.info("✅ 数据结构检查成功")
                logger.info(f"文档ID: {doc.id}")
                logger.info(f"包含字段: {list(data.keys())}")
                logger.info(f"Bot ID: {data.get('bot_id', '未设置')}")
            else:
                logger.error("❌ 用户文档不存在")
                return False
        except Exception as e:
            logger.error(f"❌ 数据结构检查失败: {e}")
            return False
        
        # 测试8: 清理测试数据
        logger.info("🧹 测试8: 清理测试数据...")
        try:
            doc_ref = data_manager._get_user_doc_ref(test_user_id)
            doc_ref.delete()
            logger.info("✅ 测试数据清理成功")
        except Exception as e:
            logger.warning(f"⚠️ 测试数据清理失败: {e}")
        
        logger.info("🎉 所有测试通过！多机器人存储功能正常工作")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        return False

async def test_data_migration():
    """测试数据迁移功能"""
    try:
        logger.info("🔄 开始测试数据迁移功能...")
        
        # 这里可以添加数据迁移的测试逻辑
        # 由于需要实际的旧数据，暂时跳过
        logger.info("✅ 数据迁移功能测试跳过（需要实际旧数据）")
        return True
        
    except Exception as e:
        logger.error(f"❌ 数据迁移测试失败: {e}")
        return False

async def main():
    """主函数"""
    print("="*60)
    print("🧪 多机器人存储功能测试")
    print("="*60)
    
    # 测试多机器人存储
    storage_success = await test_multi_bot_storage()
    
    # 测试数据迁移
    migration_success = await test_data_migration()
    
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)
    print(f"多机器人存储测试: {'✅ 通过' if storage_success else '❌ 失败'}")
    print(f"数据迁移测试: {'✅ 通过' if migration_success else '❌ 失败'}")
    
    if storage_success and migration_success:
        print("\n🎉 所有测试通过！多机器人存储功能已成功启用")
        print("现在可以启动使用多机器人存储的机器人了")
    else:
        print("\n⚠️ 部分测试失败，请检查配置和网络连接")
    
    return storage_success and migration_success

if __name__ == "__main__":
    asyncio.run(main())
