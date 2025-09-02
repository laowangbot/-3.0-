#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查当前数据库中的频道数据
"""

import asyncio
import logging
from multi_bot_data_manager import create_multi_bot_data_manager
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_current_data():
    """检查当前数据"""
    try:
        logger.info("🔍 开始检查当前数据...")
        
        # 获取配置
        config = get_config()
        bot_id = config.get('bot_id', 'default_bot')
        
        # 创建数据管理器
        data_manager = create_multi_bot_data_manager(bot_id)
        
        if not data_manager.initialized:
            logger.error("❌ 数据管理器初始化失败")
            return False
        
        # 获取所有用户
        user_ids = await data_manager.get_all_user_ids()
        logger.info(f"找到 {len(user_ids)} 个用户")
        
        for user_id in user_ids:
            logger.info(f"\n👤 用户: {user_id}")
            
            # 获取用户的频道组
            channel_pairs = await data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                logger.info("   📋 无频道组")
                continue
            
            for i, pair in enumerate(channel_pairs, 1):
                logger.info(f"   📺 频道组 {i}:")
                logger.info(f"      ID: {pair.get('id', '未知')}")
                
                # 源频道信息
                source_username = pair.get('source_username', '')
                source_name = pair.get('source_name', '')
                source_id = pair.get('source_id', '')
                logger.info(f"      📡 采集频道:")
                logger.info(f"         用户名: '{source_username}'")
                logger.info(f"         名称: '{source_name}'")
                logger.info(f"         ID: '{source_id}'")
                logger.info(f"         私密: {pair.get('is_private_source', False)}")
                
                # 目标频道信息
                target_username = pair.get('target_username', '')
                target_name = pair.get('target_name', '')
                target_id = pair.get('target_id', '')
                logger.info(f"      📤 发布频道:")
                logger.info(f"         用户名: '{target_username}'")
                logger.info(f"         名称: '{target_name}'")
                logger.info(f"         ID: '{target_id}'")
                logger.info(f"         私密: {pair.get('is_private_target', False)}")
                
                # 分析问题
                if source_username and source_name:
                    if source_username == source_name:
                        logger.warning(f"         ⚠️ 源频道用户名和名称重复: '{source_username}'")
                    else:
                        logger.info(f"         ✅ 源频道信息正常")
                else:
                    logger.warning(f"         ⚠️ 源频道缺少用户名或名称")
                
                if target_username and target_name:
                    if target_username == target_name:
                        logger.warning(f"         ⚠️ 目标频道用户名和名称重复: '{target_username}'")
                    else:
                        logger.info(f"         ✅ 目标频道信息正常")
                else:
                    logger.warning(f"         ⚠️ 目标频道缺少用户名或名称")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 检查过程中发生错误: {e}")
        return False

async def main():
    """主函数"""
    print("="*60)
    print("🔍 当前数据检查工具")
    print("="*60)
    
    success = await check_current_data()
    
    if success:
        print("\n✅ 检查完成！")
    else:
        print("\n❌ 检查失败，请检查日志")

if __name__ == "__main__":
    asyncio.run(main())
