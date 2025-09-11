#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单监听功能测试脚本
"""

import asyncio
import logging
from simple_monitor import SimpleMonitor
from pyrogram import Client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_monitor():
    """测试监听功能"""
    try:
        # 这里需要您的User API配置
        # 请替换为您的实际配置
        api_id = "YOUR_API_ID"
        api_hash = "YOUR_API_HASH"
        
        # 创建客户端
        client = Client("test_monitor", api_id=api_id, api_hash=api_hash)
        
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端已启动")
        
        # 创建监听器
        monitor = SimpleMonitor(client)
        logger.info("✅ 监听器已创建")
        
        # 测试监听状态
        status = monitor.get_monitoring_status()
        logger.info(f"📊 监听状态: {status}")
        
        # 停止客户端
        await client.stop()
        logger.info("✅ 测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🔍 监听功能测试")
    print("⚠️ 请确保已配置正确的API凭据")
    print("📝 此脚本仅用于测试监听器基本功能")
    
    # 检查是否有API配置
    try:
        from config import get_config
        config = get_config()
        if config.get('api_id') and config.get('api_hash'):
            print("✅ 找到API配置，可以运行测试")
            asyncio.run(test_monitor())
        else:
            print("❌ 未找到API配置，请先配置.env文件")
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")


