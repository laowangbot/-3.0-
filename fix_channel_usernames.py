#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复数据库中的频道用户名信息
尝试重新获取频道的真实用户名
"""

import asyncio
import os
from dotenv import load_dotenv
from data_manager import DataManager
from pyrogram import Client
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

async def get_real_channel_username(client: Client, chat_id: str) -> str:
    """获取频道的真实用户名，优雅处理无法访问的频道"""
    try:
        # 如果已经是用户名格式，直接返回
        if isinstance(chat_id, str) and chat_id.startswith('@'):
            return chat_id
        
        # 处理PENDING格式
        if chat_id.startswith('PENDING_'):
            original_id = chat_id.replace('PENDING_', '')
            if original_id.startswith('@'):
                return original_id
            chat_id = original_id
        
        # 如果是数字ID，尝试获取频道信息
        if isinstance(chat_id, str) and (chat_id.startswith('-100') or chat_id.startswith('-')):
            try:
                logger.info(f"尝试获取频道信息: {chat_id}")
                chat = await client.get_chat(chat_id)
                
                if hasattr(chat, 'username') and chat.username:
                    username = f"@{chat.username}"
                    logger.info(f"成功获取用户名: {chat_id} -> {username}")
                    return username
                elif hasattr(chat, 'title') and chat.title:
                    title = chat.title
                    logger.info(f"获取到频道标题: {chat_id} -> {title}")
                    return title
                else:
                    logger.warning(f"频道 {chat_id} 没有用户名和标题")
                    return str(chat_id)
            except Exception as e:
                error_msg = str(e)
                if "PEER_ID_INVALID" in error_msg:
                    logger.warning(f"频道 {chat_id} 无法访问（机器人未加入或频道不存在），保持原ID")
                elif "CHAT_ADMIN_REQUIRED" in error_msg:
                    logger.warning(f"频道 {chat_id} 需要管理员权限，保持原ID")
                elif "CHANNEL_PRIVATE" in error_msg:
                    logger.warning(f"频道 {chat_id} 是私有频道，保持原ID")
                else:
                    logger.warning(f"获取频道 {chat_id} 信息失败: {e}")
                return str(chat_id)
        else:
            return str(chat_id)
    except Exception as e:
        logger.warning(f"处理频道 {chat_id} 失败: {e}")
        return str(chat_id)

async def fix_channel_usernames():
    """修复数据库中的频道用户名"""
    
    # 初始化数据管理器
    data_manager = DataManager()
    
    if not data_manager.initialized:
        print("❌ Firebase连接失败")
        return
    
    # 初始化Telegram客户端
    try:
        api_id = int(os.getenv('API_ID', '0'))
        api_hash = os.getenv('API_HASH', '')
        bot_token = os.getenv('BOT_TOKEN', '')
        
        if api_id == 0 or not api_hash or not bot_token:
            print("❌ Telegram配置信息不完整")
            return
        
        client = Client(
            "fix_usernames_session",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token
        )
        
        await client.start()
        print("✅ Telegram客户端连接成功")
        
    except Exception as e:
        print(f"❌ Telegram客户端初始化失败: {e}")
        return
    
    print("🔧 开始修复频道用户名...\n")
    
    try:
        # 获取所有用户的频道组信息
        users_ref = data_manager.db.collection('users')
        users = users_ref.stream()
        
        total_fixed = 0
        total_processed = 0
        
        for user_doc in users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            if 'channel_pairs' in user_data:
                channel_pairs = user_data['channel_pairs']
                updated_pairs = []
                
                # 处理列表格式的channel_pairs
                if isinstance(channel_pairs, list):
                    for i, pair_data in enumerate(channel_pairs):
                        if isinstance(pair_data, dict):
                            total_processed += 1
                            
                            source_id = pair_data.get('source_id', '')
                            target_id = pair_data.get('target_id', '')
                            source_username = pair_data.get('source_username', '')
                            target_username = pair_data.get('target_username', '')
                            
                            print(f"处理用户 {user_id} 的频道组 {i}:")
                            print(f"  当前源频道用户名: {source_username}")
                            print(f"  当前目标频道用户名: {target_username}")
                            
                            # 检查是否需要修复源频道用户名
                            new_source_username = source_username
                            if source_username.startswith('-') or not source_username.startswith('@'):
                                new_source_username = await get_real_channel_username(client, source_id)
                                if new_source_username != source_username:
                                    print(f"  ✅ 修复源频道用户名: {source_username} -> {new_source_username}")
                                    total_fixed += 1
                            
                            # 检查是否需要修复目标频道用户名
                            new_target_username = target_username
                            if target_username.startswith('-') or not target_username.startswith('@'):
                                new_target_username = await get_real_channel_username(client, target_id)
                                if new_target_username != target_username:
                                    print(f"  ✅ 修复目标频道用户名: {target_username} -> {new_target_username}")
                                    total_fixed += 1
                            
                            # 更新数据
                            updated_pair = pair_data.copy()
                            updated_pair['source_username'] = new_source_username
                            updated_pair['target_username'] = new_target_username
                            updated_pairs.append(updated_pair)
                            
                            print()
                    
                    # 更新数据库
                    if updated_pairs:
                        user_ref = data_manager.db.collection('users').document(user_id)
                        user_ref.update({'channel_pairs': updated_pairs})
                        print(f"✅ 已更新用户 {user_id} 的频道组数据\n")
        
        print(f"\n📊 修复完成:")
        print(f"总处理频道组: {total_processed}")
        print(f"成功修复: {total_fixed}")
        
    except Exception as e:
        print(f"❌ 修复过程中出错: {e}")
    
    finally:
        await client.stop()
        print("\n🔚 Telegram客户端已断开")

if __name__ == "__main__":
    asyncio.run(fix_channel_usernames())