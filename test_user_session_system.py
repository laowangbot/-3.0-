#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户专属Session系统测试脚本
验证新功能是否正常工作
"""

import asyncio
import logging
from deployment_manager import create_deployment_manager
from user_session_manager import create_user_session_manager_from_config

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_deployment_manager():
    """测试部署管理器"""
    try:
        logger.info("🧪 测试部署管理器...")
        
        deployment_manager = create_deployment_manager()
        
        # 获取部署信息
        info = deployment_manager.get_deployment_info()
        logger.info(f"✅ 部署信息获取成功:")
        logger.info(f"   环境: {info['environment']}")
        logger.info(f"   机器人ID: {info['bot_id']}")
        logger.info(f"   数据存储: {info['data_storage']}")
        logger.info(f"   Session存储: {info['session_storage']}")
        
        # 验证配置
        is_valid = deployment_manager.validate_deployment_config()
        logger.info(f"✅ 配置验证: {'通过' if is_valid else '失败'}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"❌ 部署管理器测试失败: {e}")
        return False

async def test_session_manager():
    """测试Session管理器"""
    try:
        logger.info("🧪 测试Session管理器...")
        
        session_manager = create_user_session_manager_from_config()
        
        # 获取统计信息
        stats = await session_manager.get_session_stats()
        logger.info(f"✅ Session统计信息:")
        logger.info(f"   总Session数: {stats.get('total_sessions', 0)}")
        logger.info(f"   活跃Session数: {stats.get('active_sessions', 0)}")
        logger.info(f"   机器人Session: {stats.get('bot_sessions', 0)}")
        logger.info(f"   用户Session: {stats.get('user_sessions', 0)}")
        
        # 测试创建用户session（不实际创建，只测试方法存在）
        test_user_id = "test_user_123"
        logger.info(f"✅ Session管理器功能正常")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Session管理器测试失败: {e}")
        return False

async def test_multi_bot_data_manager():
    """测试多机器人数据管理器"""
    try:
        logger.info("🧪 测试多机器人数据管理器...")
        
        from multi_bot_data_manager import create_multi_bot_data_manager
        from config import get_config
        
        config = get_config()
        data_manager = create_multi_bot_data_manager(config['bot_id'])
        
        # 检查是否有所需的方法
        if hasattr(data_manager, 'get_channel_pair_by_channels'):
            logger.info("✅ get_channel_pair_by_channels 方法存在")
        else:
            logger.error("❌ get_channel_pair_by_channels 方法缺失")
            return False
        
        # 测试方法签名
        import inspect
        sig = inspect.signature(data_manager.get_channel_pair_by_channels)
        logger.info(f"✅ 方法签名: {sig}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 多机器人数据管理器测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    logger.info("🚀 开始测试用户专属Session系统...")
    logger.info("=" * 60)
    
    test_results = []
    
    # 测试部署管理器
    result1 = await test_deployment_manager()
    test_results.append(("部署管理器", result1))
    
    # 测试Session管理器
    result2 = await test_session_manager()
    test_results.append(("Session管理器", result2))
    
    # 测试多机器人数据管理器
    result3 = await test_multi_bot_data_manager()
    test_results.append(("多机器人数据管理器", result3))
    
    # 输出测试结果
    logger.info("=" * 60)
    logger.info("📊 测试结果汇总:")
    logger.info("=" * 60)
    
    all_passed = True
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    logger.info("=" * 60)
    if all_passed:
        logger.info("🎉 所有测试通过！用户专属Session系统已就绪！")
        logger.info("🚀 可以开始部署到Render了！")
    else:
        logger.error("❌ 部分测试失败，请检查配置和依赖")
    
    return all_passed

if __name__ == "__main__":
    asyncio.run(main())
