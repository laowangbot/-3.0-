#!/usr/bin/env python3
"""
修复Firebase数据结构问题
"""

import asyncio
import logging
from datetime import datetime
from multi_bot_data_manager import create_multi_bot_data_manager

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_firebase_data_structure():
    """修复Firebase数据结构问题"""
    try:
        # 创建数据管理器
        data_manager = create_multi_bot_data_manager('default_bot')
        
        if not data_manager.initialized:
            logger.error("❌ 数据管理器未初始化")
            return
        
        logger.info("✅ 数据管理器初始化成功")
        
        # 获取所有用户数据
        users_collection = data_manager.db.collection('bots').document('default_bot').collection('users')
        users = users_collection.stream()
        
        fixed_count = 0
        
        for user_doc in users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            logger.info(f"🔍 检查用户: {user_id}")
            
            # 检查频道组数据
            channel_pairs = user_data.get('channel_pairs', [])
            if not channel_pairs:
                logger.info(f"   - 用户 {user_id} 没有频道组数据")
                continue
            
            # 检查每个频道组的数据结构
            needs_fix = False
            for i, pair in enumerate(channel_pairs):
                # 检查是否有无效的数据类型
                for key, value in pair.items():
                    if value is None:
                        logger.warning(f"   - 用户 {user_id} 频道组 {i} 有None值: {key}")
                        pair[key] = ""  # 将None替换为空字符串
                        needs_fix = True
                    elif isinstance(value, dict) and not value:
                        logger.warning(f"   - 用户 {user_id} 频道组 {i} 有空字典: {key}")
                        pair[key] = ""  # 将空字典替换为空字符串
                        needs_fix = True
                    elif isinstance(value, list) and not value:
                        logger.warning(f"   - 用户 {user_id} 频道组 {i} 有空列表: {key}")
                        pair[key] = []  # 保持空列表
                    elif isinstance(value, (int, float)) and str(value) == 'nan':
                        logger.warning(f"   - 用户 {user_id} 频道组 {i} 有NaN值: {key}")
                        pair[key] = 0  # 将NaN替换为0
                        needs_fix = True
            
            # 如果需要修复，保存数据
            if needs_fix:
                try:
                    # 确保所有字段都是Firebase兼容的类型
                    cleaned_pairs = []
                    for pair in channel_pairs:
                        cleaned_pair = {}
                        for key, value in pair.items():
                            if value is None:
                                cleaned_pair[key] = ""
                            elif isinstance(value, dict) and not value:
                                cleaned_pair[key] = ""
                            elif isinstance(value, (int, float)) and str(value) == 'nan':
                                cleaned_pair[key] = 0
                            else:
                                cleaned_pair[key] = value
                        cleaned_pairs.append(cleaned_pair)
                    
                    # 保存修复后的数据
                    success = await data_manager.save_channel_pairs(user_id, cleaned_pairs)
                    if success:
                        logger.info(f"✅ 用户 {user_id} 数据修复成功")
                        fixed_count += 1
                    else:
                        logger.error(f"❌ 用户 {user_id} 数据修复失败")
                        
                except Exception as e:
                    logger.error(f"❌ 修复用户 {user_id} 数据时出错: {e}")
            else:
                logger.info(f"   - 用户 {user_id} 数据正常，无需修复")
        
        logger.info(f"🎉 数据修复完成，共修复 {fixed_count} 个用户的数据")
        
    except Exception as e:
        logger.error(f"❌ 修复过程出错: {e}")

if __name__ == "__main__":
    asyncio.run(fix_firebase_data_structure())
