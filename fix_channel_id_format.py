#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复频道ID格式问题
清理频道ID中错误包含的消息ID
"""

import asyncio
import logging
from multi_bot_data_manager import create_multi_bot_data_manager
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fix_channel_id_format():
    """修复频道ID格式"""
    try:
        logger.info("🔧 开始修复频道ID格式...")
        
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
                
                # 修复源频道ID格式
                if source_username and source_username.startswith('@c/') and '/' in source_username[3:]:
                    # 提取频道ID，去掉消息ID
                    channel_id = source_username.split('/')[0] + '/' + source_username.split('/')[1]
                    logger.info(f"修复源频道ID: {source_username} -> {channel_id}")
                    pair['source_username'] = channel_id
                    updated = True
                
                # 修复目标频道ID格式
                if target_username and target_username.startswith('@c/') and '/' in target_username[3:]:
                    # 提取频道ID，去掉消息ID
                    channel_id = target_username.split('/')[0] + '/' + target_username.split('/')[1]
                    logger.info(f"修复目标频道ID: {target_username} -> {channel_id}")
                    pair['target_username'] = channel_id
                    updated = True
                
                # 修复频道名称中的消息ID
                if source_name and source_name.startswith('@c/') and '/' in source_name[3:]:
                    channel_id = source_name.split('/')[0] + '/' + source_name.split('/')[1]
                    logger.info(f"修复源频道名称: {source_name} -> {channel_id}")
                    pair['source_name'] = channel_id
                    updated = True
                
                if target_name and target_name.startswith('@c/') and '/' in target_name[3:]:
                    channel_id = target_name.split('/')[0] + '/' + target_name.split('/')[1]
                    logger.info(f"修复目标频道名称: {target_name} -> {channel_id}")
                    pair['target_name'] = channel_id
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
    print("🔧 频道ID格式修复工具")
    print("="*60)
    
    success = await fix_channel_id_format()
    
    if success:
        print("\n✅ 修复完成！")
        print("现在频道ID格式应该正确了")
        print("请重新尝试启动搬运任务")
    else:
        print("\n❌ 修复失败，请检查日志")

if __name__ == "__main__":
    asyncio.run(main())
