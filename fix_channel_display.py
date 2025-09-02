#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复频道显示问题
解决频道名称和用户名重复显示的问题
"""

import asyncio
import logging
from multi_bot_data_manager import create_multi_bot_data_manager
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fix_channel_display():
    """修复频道显示问题"""
    try:
        logger.info("🔧 开始修复频道显示问题...")
        
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
        
        fixed_count = 0
        
        for user_id in user_ids:
            logger.info(f"处理用户: {user_id}")
            
            # 获取用户的频道组
            channel_pairs = await data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                continue
            
            updated = False
            
            for pair in channel_pairs:
                source_username = pair.get('source_username', '')
                target_username = pair.get('target_username', '')
                source_name = pair.get('source_name', '')
                target_name = pair.get('target_name', '')
                
                # 检查源频道
                if source_username and source_name:
                    # 如果用户名和名称相同，说明是重复保存
                    if source_username == source_name:
                        logger.info(f"修复源频道重复: {source_username}")
                        # 对于公开频道，保留用户名，清空名称让系统自动处理
                        if not source_username.startswith('@c/'):
                            pair['source_name'] = ''
                            updated = True
                        # 对于私密频道，保留用户名，设置合适的名称
                        else:
                            pair['source_name'] = '私密频道'
                            updated = True
                
                # 检查目标频道
                if target_username and target_name:
                    # 如果用户名和名称相同，说明是重复保存
                    if target_username == target_name:
                        logger.info(f"修复目标频道重复: {target_username}")
                        # 对于公开频道，保留用户名，清空名称让系统自动处理
                        if not target_username.startswith('@c/'):
                            pair['target_name'] = ''
                            updated = True
                        # 对于私密频道，保留用户名，设置合适的名称
                        else:
                            pair['target_name'] = '私密频道'
                            updated = True
                
                # 检查私密频道的显示名称
                if target_username and target_username.startswith('@c/'):
                    # 如果私密频道的名称不是默认的，且不是"私密频道"，则清空让系统处理
                    if target_name and target_name != '私密频道' and target_name != target_username:
                        # 如果名称和用户名不同，保留名称
                        pass
                    elif target_name == target_username:
                        # 如果名称和用户名相同，清空名称
                        pair['target_name'] = ''
                        updated = True
                
                if source_username and source_username.startswith('@c/'):
                    # 如果私密频道的名称不是默认的，且不是"私密频道"，则清空让系统处理
                    if source_name and source_name != '私密频道' and source_name != source_username:
                        # 如果名称和用户名不同，保留名称
                        pass
                    elif source_name == source_username:
                        # 如果名称和用户名相同，清空名称
                        pair['source_name'] = ''
                        updated = True
            
            # 如果有更新，保存频道组
            if updated:
                success = await data_manager.save_channel_pairs(user_id, channel_pairs)
                if success:
                    logger.info(f"✅ 用户 {user_id} 的频道组已修复")
                    fixed_count += 1
                else:
                    logger.error(f"❌ 用户 {user_id} 的频道组保存失败")
        
        logger.info(f"🎉 修复完成！共修复了 {fixed_count} 个用户的频道组")
        return True
        
    except Exception as e:
        logger.error(f"❌ 修复过程中发生错误: {e}")
        return False

async def main():
    """主函数"""
    print("="*60)
    print("🔧 频道显示问题修复工具")
    print("="*60)
    
    success = await fix_channel_display()
    
    if success:
        print("\n✅ 修复完成！")
        print("现在频道组应该正确显示频道名称和用户名了")
        print("请重新查看频道管理页面验证修复效果")
    else:
        print("\n❌ 修复失败，请检查日志")

if __name__ == "__main__":
    asyncio.run(main())
