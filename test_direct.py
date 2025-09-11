#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
直接测试User API客户端的实时监听能力
"""

import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_direct_monitoring():
    """直接测试实时监听"""
    
    # 从.env文件读取配置
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_id = int(os.getenv('API_ID'))
    api_hash = os.getenv('API_HASH')
    
    # 创建客户端，使用现有的session文件
    client = Client("bot_session_default", api_id=api_id, api_hash=api_hash)
    
    # 消息处理器
    async def message_handler(client, message):
        logger.info(f"🔔 收到消息: {message.id} from {message.chat.id} ({message.chat.title if hasattr(message.chat, 'title') else '未知'})")
        logger.info(f"   消息类型: {message.media}")
        logger.info(f"   消息内容: {message.text[:100] if message.text else '无文本'}")
    
    try:
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 注册消息处理器
        client.add_handler(MessageHandler(message_handler, filters.all))
        logger.info("✅ 消息处理器注册成功")
        
        # 获取客户端信息
        me = await client.get_me()
        logger.info(f"✅ 客户端用户: {me.first_name} (@{me.username})")
        
        # 测试访问目标频道
        target_channel = -1003011899824  # 您的测试频道
        try:
            chat = await client.get_chat(target_channel)
            logger.info(f"✅ 频道访问权限: {chat.title}")
        except Exception as e:
            logger.error(f"❌ 频道访问失败: {e}")
        
        logger.info("🔍 开始监听消息...")
        logger.info("   请在源频道发送消息进行测试")
        logger.info("   按 Ctrl+C 停止监听")
        
        # 保持运行
        try:
            await asyncio.sleep(30)  # 等待30秒
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        try:
            await client.stop()
            logger.info("✅ 客户端已停止")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_direct_monitoring())
