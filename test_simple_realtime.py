#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的实时监听测试脚本
"""

import asyncio
import logging
from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram import filters

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_realtime_listening():
    """测试实时监听功能"""
    
    # 从环境文件读取配置
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_id = os.getenv('API_ID')
    api_hash = os.getenv('API_HASH')
    
    if not api_id or not api_hash:
        logger.error("❌ 未找到API_ID或API_HASH")
        return
    
    # 创建客户端 - 使用现有的session文件
    client = Client(
        "bot_session_default",  # 使用现有的session文件
        api_id=int(api_id),
        api_hash=api_hash
    )
    
    try:
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 检查客户端状态
        logger.info(f"✅ 客户端连接状态: {client.is_connected}")
        logger.info(f"✅ 客户端用户: {await client.get_me()}")
        
        # 注册消息处理器
        async def message_handler(client, message):
            logger.info(f"🔔 [测试] 收到消息: {message.id} from {message.chat.id}")
            logger.info(f"   消息类型: {message.media}")
            logger.info(f"   消息内容: {message.text[:100] if message.text else '无文本'}")
        
        # 注册多个处理器
        client.add_handler(MessageHandler(message_handler, filters.all))
        logger.info("✅ 消息处理器注册成功")
        
        # 测试频道访问
        test_channel_id = -1003011899824  # xsm58频道
        try:
            chat = await client.get_chat(test_channel_id)
            logger.info(f"✅ 频道访问成功: {chat.title}")
            
            # 获取最新消息
            messages = []
            async for message in client.get_chat_history(test_channel_id, limit=1):
                messages.append(message)
            if messages:
                latest_msg = messages[0]
                logger.info(f"✅ 最新消息: {latest_msg.id} ({latest_msg.media})")
            else:
                logger.info("⚠️ 频道没有消息")
        except Exception as e:
            logger.error(f"❌ 频道访问失败: {e}")
        
        # 等待消息
        logger.info("⏳ 等待消息... (30秒)")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
    finally:
        await client.stop()
        logger.info("✅ 客户端已停止")

if __name__ == "__main__":
    asyncio.run(test_realtime_listening())
