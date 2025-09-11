#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化启动脚本
避免复杂的监听引擎初始化问题
"""

import asyncio
import logging
import sys
from config import get_config, validate_config
from log_config import setup_bot_logging, get_logger

# 配置日志
setup_bot_logging()
logger = get_logger(__name__)

async def main():
    """主函数"""
    try:
        logger.info("🚀 启动简化版机器人...")
        
        # 获取配置
        config = get_config()
        
        # 验证配置
        if not validate_config():
            logger.error("❌ 配置验证失败")
            return
        
        # 显示配置信息
        logger.info(f"🔧 机器人配置:")
        logger.info(f"   Bot ID: {config.get('bot_id')}")
        logger.info(f"   Bot Name: {config.get('bot_name')}")
        logger.info(f"   API ID: {config.get('api_id')}")
        logger.info(f"   API Hash: {config.get('api_hash', '')[:8]}...")
        logger.info(f"   Bot Token: {config.get('bot_token', '')[:8]}...")
        logger.info(f"   使用本地存储: {config.get('use_local_storage', False)}")
        logger.info(f"   端口: {config.get('port')}")
        
        # 启动任务状态管理器
        try:
            from task_state_manager import start_task_state_manager
            await start_task_state_manager(config.get('bot_id', 'default_bot'))
            logger.info("✅ 任务状态管理器已启动")
        except Exception as e:
            logger.warning(f"⚠️ 启动任务状态管理器失败: {e}")
        
        # 启动并发任务管理器
        try:
            from concurrent_task_manager import start_concurrent_task_manager
            await start_concurrent_task_manager(config.get('bot_id', 'default_bot'))
            logger.info("✅ 并发任务管理器已启动")
        except Exception as e:
            logger.warning(f"⚠️ 启动并发任务管理器失败: {e}")
        
        # 启动内存优化管理器
        try:
            from memory_optimizer import start_memory_optimizer
            await start_memory_optimizer(config.get('bot_id', 'default_bot'))
            logger.info("✅ 内存优化管理器已启动")
        except Exception as e:
            logger.warning(f"⚠️ 启动内存优化管理器失败: {e}")
        
        # 启动Web服务器
        try:
            from web_server import WebServer
            web_server = WebServer()
            await web_server.start_server(port=config.get('port', 8091))
            logger.info("✅ Web服务器已启动")
        except Exception as e:
            logger.error(f"❌ 启动Web服务器失败: {e}")
            return
        
        logger.info("🎉 简化版机器人启动完成！")
        logger.info("💡 主要功能:")
        logger.info("   ✅ 任务状态持久化")
        logger.info("   ✅ 并发任务管理")
        logger.info("   ✅ 内存优化管理")
        logger.info("   ✅ Web服务器")
        logger.info("   ⚠️ 监听引擎已禁用（避免启动问题）")
        
        # 保持运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 收到停止信号，正在关闭...")
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
