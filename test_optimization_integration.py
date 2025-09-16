#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化系统集成测试脚本
测试Firebase优化系统是否正确集成到主程序中
"""

import asyncio
import logging
import time
from datetime import datetime
from config import get_config
from data_manager import get_data_manager
from multi_bot_data_manager import create_multi_bot_data_manager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_data_manager_integration():
    """测试数据管理器集成"""
    logger.info("🔧 测试数据管理器集成...")
    
    # 获取配置
    config = get_config()
    bot_id = config.get('bot_id', 'test_bot')
    
    try:
        # 测试data_manager
        logger.info("📊 测试data_manager...")
        data_manager = get_data_manager(bot_id)
        
        # 测试用户配置操作
        test_user_id = "test_user_123"
        test_config = {
            'test_field': 'integration_test',
            'timestamp': datetime.now().isoformat(),
            'bot_id': bot_id
        }
        
        # 保存配置
        success = await data_manager.save_user_config(test_user_id, test_config)
        if success:
            logger.info("✅ data_manager.save_user_config 测试成功")
        else:
            logger.error("❌ data_manager.save_user_config 测试失败")
            return False
        
        # 读取配置
        read_config = await data_manager.get_user_config(test_user_id)
        if read_config and read_config.get('test_field') == 'integration_test':
            logger.info("✅ data_manager.get_user_config 测试成功")
        else:
            logger.error("❌ data_manager.get_user_config 测试失败")
            return False
        
        # 测试multi_bot_data_manager
        logger.info("📊 测试multi_bot_data_manager...")
        multi_bot_manager = create_multi_bot_data_manager(bot_id)
        
        # 测试用户配置操作
        test_config2 = {
            'test_field': 'multi_bot_test',
            'timestamp': datetime.now().isoformat(),
            'bot_id': bot_id
        }
        
        # 保存配置
        success = await multi_bot_manager.save_user_config(test_user_id, test_config2)
        if success:
            logger.info("✅ multi_bot_data_manager.save_user_config 测试成功")
        else:
            logger.error("❌ multi_bot_data_manager.save_user_config 测试失败")
            return False
        
        # 读取配置
        read_config2 = await multi_bot_manager.get_user_config(test_user_id)
        if read_config2 and read_config2.get('test_field') == 'multi_bot_test':
            logger.info("✅ multi_bot_data_manager.get_user_config 测试成功")
        else:
            logger.error("❌ multi_bot_data_manager.get_user_config 测试失败")
            return False
        
        # 检查是否使用了优化的Firebase管理器
        if hasattr(data_manager, 'optimized_manager') and data_manager.optimized_manager:
            logger.info("✅ data_manager 使用了优化的Firebase管理器")
        else:
            logger.info("ℹ️ data_manager 使用标准Firebase连接（可能因为本地存储模式）")
        
        if hasattr(multi_bot_manager, 'optimized_manager') and multi_bot_manager.optimized_manager:
            logger.info("✅ multi_bot_data_manager 使用了优化的Firebase管理器")
        else:
            logger.info("ℹ️ multi_bot_data_manager 使用标准Firebase连接（可能因为本地存储模式）")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        return False

async def test_main_program_integration():
    """测试主程序集成"""
    logger.info("🔧 测试主程序集成...")
    
    try:
        # 导入主程序
        from lsjmain import TelegramBot
        
        # 创建机器人实例（不启动）
        bot = TelegramBot("test_bot")
        
        # 检查机器人是否初始化了优化服务
        if hasattr(bot, 'data_manager'):
            logger.info("✅ 主程序已集成数据管理器")
            
            # 检查数据管理器类型
            data_manager_type = type(bot.data_manager).__name__
            logger.info(f"📊 数据管理器类型: {data_manager_type}")
            
            # 检查是否使用了优化的Firebase管理器
            if hasattr(bot.data_manager, 'optimized_manager'):
                if bot.data_manager.optimized_manager:
                    logger.info("✅ 主程序使用了优化的Firebase管理器")
                else:
                    logger.info("ℹ️ 主程序使用标准Firebase连接")
            else:
                logger.info("ℹ️ 主程序使用本地存储模式")
        else:
            logger.error("❌ 主程序未集成数据管理器")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 主程序集成测试失败: {e}")
        return False

async def test_optimization_components():
    """测试优化组件"""
    logger.info("🔧 测试优化组件...")
    
    try:
        # 测试优化Firebase管理器
        from optimized_firebase_manager import get_global_optimized_manager, get_optimization_stats
        
        config = get_config()
        bot_id = config.get('bot_id', 'test_bot')
        
        # 获取优化管理器
        manager = get_global_optimized_manager(bot_id)
        if manager:
            logger.info("✅ 优化Firebase管理器可用")
            
            # 获取统计信息
            stats = get_optimization_stats(bot_id)
            logger.info(f"📊 优化统计: {stats}")
        else:
            logger.info("ℹ️ 优化Firebase管理器不可用（可能因为本地存储模式）")
        
        # 测试批量存储
        from firebase_batch_storage import get_global_batch_storage
        batch_storage = get_global_batch_storage(bot_id)
        if batch_storage:
            logger.info("✅ 批量存储组件可用")
        else:
            logger.info("ℹ️ 批量存储组件不可用")
        
        # 测试缓存管理器
        from firebase_cache_manager import get_global_cache_manager
        cache_manager = get_global_cache_manager(bot_id)
        if cache_manager:
            logger.info("✅ 缓存管理器可用")
        else:
            logger.info("ℹ️ 缓存管理器不可用")
        
        # 测试配额监控器
        from firebase_quota_monitor import get_global_quota_monitor
        quota_monitor = get_global_quota_monitor(bot_id)
        if quota_monitor:
            logger.info("✅ 配额监控器可用")
        else:
            logger.info("ℹ️ 配额监控器不可用")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 优化组件测试失败: {e}")
        return False

async def main():
    """主函数"""
    logger.info("🔧 Firebase优化系统集成测试工具")
    logger.info("=" * 60)
    
    # 获取配置信息
    config = get_config()
    logger.info(f"📋 当前配置:")
    logger.info(f"   Bot ID: {config.get('bot_id')}")
    logger.info(f"   使用本地存储: {config.get('use_local_storage', False)}")
    logger.info(f"   Firebase项目: {config.get('firebase_project_id', '未配置')}")
    logger.info("=" * 60)
    
    # 运行测试
    tests = [
        ("优化组件测试", test_optimization_components),
        ("数据管理器集成测试", test_data_manager_integration),
        ("主程序集成测试", test_main_program_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 运行测试: {test_name}")
        logger.info("-" * 40)
        
        try:
            success = await test_func()
            if success:
                logger.info(f"✅ {test_name} 通过")
                passed += 1
            else:
                logger.error(f"❌ {test_name} 失败")
        except Exception as e:
            logger.error(f"❌ {test_name} 异常: {e}")
    
    # 输出测试结果
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试结果汇总")
    logger.info("=" * 60)
    logger.info(f"通过: {passed}/{total}")
    logger.info(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        logger.info("🎉 所有测试通过！Firebase优化系统集成成功")
    else:
        logger.warning("⚠️ 部分测试失败，请检查配置和集成状态")
    
    # 输出建议
    logger.info("\n💡 建议:")
    if config.get('use_local_storage', False):
        logger.info("   - 当前使用本地存储模式，Firebase优化功能不会激活")
        logger.info("   - 如需测试Firebase优化，请设置 USE_LOCAL_STORAGE=false")
    else:
        logger.info("   - 当前使用Firebase存储模式，优化功能应该正常工作")
        logger.info("   - 请确保Firebase凭据配置正确")

if __name__ == "__main__":
    asyncio.run(main())
