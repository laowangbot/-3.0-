#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单版实时监听修复 - 直接集成到机器人中
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

class SimpleRealtimeMonitor:
    """简单版实时监听器"""
    
    def __init__(self, client):
        self.client = client
        self.handlers_registered = False
    
    async def start_monitoring(self):
        """启动简单版实时监听"""
        try:
            if self.handlers_registered:
                logger.info("✅ 简单版监听器已经启动")
                return
            
            # 注册消息处理器
            async def simple_message_handler(client, message):
                logger.info(f"🔔 [简单监听] 收到消息: {message.id} from {message.chat.id}")
                logger.info(f"   消息类型: {message.media}")
                logger.info(f"   消息内容: {message.text[:100] if message.text else '无文本'}")
            
            # 使用最简单的过滤器
            handler = MessageHandler(simple_message_handler, filters.all)
            self.client.add_handler(handler)
            self.handlers_registered = True
            
            logger.info("✅ 简单版实时监听器启动成功")
            
        except Exception as e:
            logger.error(f"❌ 简单版监听器启动失败: {e}")
    
    async def stop_monitoring(self):
        """停止简单版实时监听"""
        try:
            if self.handlers_registered:
                # 这里可以添加停止逻辑
                self.handlers_registered = False
                logger.info("✅ 简单版监听器已停止")
        except Exception as e:
            logger.error(f"❌ 简单版监听器停止失败: {e}")

# 测试函数
async def test_simple_monitor():
    """测试简单版监听器"""
    
    # 从环境文件读取配置
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_id = os.getenv('API_ID')
    api_hash = os.getenv('API_HASH')
    
    if not api_id or not api_hash:
        logger.error("❌ 未找到API_ID或API_HASH")
        return
    
    # 创建客户端
    client = Client(
        "bot_session_default",
        api_id=int(api_id),
        api_hash=api_hash
    )
    
    try:
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 创建简单版监听器
        monitor = SimpleRealtimeMonitor(client)
        await monitor.start_monitoring()
        
        # 等待消息
        logger.info("⏳ 等待消息... (30秒)")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
    finally:
        await client.stop()
        logger.info("✅ 客户端已停止")

if __name__ == "__main__":
    asyncio.run(test_simple_monitor())

