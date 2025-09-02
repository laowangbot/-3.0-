#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取频道ID工具
帮助获取私密频道的正确ID格式
"""

import asyncio
import logging
from pyrogram import Client
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def get_channel_info():
    """获取频道信息"""
    try:
        # 获取配置
        config = get_config()
        
        # 创建客户端
        client = Client(
            "bot_session",
            api_id=config['api_id'],
            api_hash=config['api_hash'],
            bot_token=config['bot_token']
        )
        
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 尝试不同的频道ID格式
        channel_formats = [
            "@c/2692998023",
            "-1002692998023",
            "2692998023",
            "https://t.me/c/2692998023/123"
        ]
        
        for channel_format in channel_formats:
            try:
                logger.info(f"🔍 尝试访问频道: {channel_format}")
                chat = await client.get_chat(channel_format)
                
                logger.info(f"✅ 成功访问频道: {channel_format}")
                logger.info(f"   频道ID: {chat.id}")
                logger.info(f"   频道类型: {chat.type}")
                logger.info(f"   频道标题: {getattr(chat, 'title', 'N/A')}")
                logger.info(f"   用户名: {getattr(chat, 'username', 'N/A')}")
                
                # 检查机器人权限
                try:
                    member = await client.get_chat_member(chat.id, "me")
                    logger.info(f"   机器人权限: {member.status}")
                    logger.info(f"   可以发送消息: {getattr(member, 'can_send_messages', 'N/A')}")
                except Exception as perm_error:
                    logger.warning(f"   无法检查权限: {perm_error}")
                
                logger.info("=" * 50)
                
            except Exception as e:
                logger.warning(f"❌ 无法访问 {channel_format}: {e}")
        
        await client.stop()
        
    except Exception as e:
        logger.error(f"❌ 获取频道信息失败: {e}")

async def main():
    """主函数"""
    print("="*60)
    print("🔍 频道ID获取工具")
    print("="*60)
    
    await get_channel_info()

if __name__ == "__main__":
    asyncio.run(main())
