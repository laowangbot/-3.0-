#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试实时监听模式
"""

import asyncio
import logging
from pyrogram import Client
from monitoring_engine import RealTimeMonitoringEngine
from cloning_engine import CloningEngine
from message_engine import MessageEngine
from config import Config

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_realtime_mode():
    """测试实时监听模式"""
    try:
        # 初始化配置
        config = Config()
        
        # 创建客户端
        client = Client(
            "test_realtime_session",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN
        )
        
        # 初始化引擎
        message_engine = MessageEngine(config)
        cloning_engine = CloningEngine(client, message_engine, config)
        monitoring_engine = RealTimeMonitoringEngine(client, cloning_engine, config)
        
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 启动监听引擎
        await monitoring_engine.start_monitoring()
        logger.info("✅ 实时监听引擎启动成功")
        
        # 创建测试任务
        test_source_channels = [
            {
                'channel_id': '-1003011899824',  # 替换为您的测试频道ID
                'channel_name': '测试源频道',
                'channel_username': ''
            }
        ]
        
        task_id = await monitoring_engine.create_monitoring_task(
            user_id='7951964655',  # 替换为您的用户ID
            target_channel='-1001959897119',  # 替换为您的目标频道ID
            source_channels=test_source_channels,
            config={'monitoring_mode': 'realtime'}
        )
        
        logger.info(f"✅ 创建测试任务: {task_id}")
        
        # 启动任务
        success = await monitoring_engine.start_monitoring_task(task_id)
        if success:
            logger.info("✅ 测试任务启动成功")
            logger.info("🔍 现在请在源频道发送消息进行测试...")
            logger.info("📝 按 Ctrl+C 停止测试")
            
            # 保持运行
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 停止测试")
        else:
            logger.error("❌ 测试任务启动失败")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(f"❌ 错误详情: {traceback.format_exc()}")
    
    finally:
        # 清理资源
        try:
            await monitoring_engine.stop_monitoring()
            await client.stop()
            logger.info("✅ 资源清理完成")
        except Exception as e:
            logger.error(f"❌ 清理资源失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_realtime_mode())

