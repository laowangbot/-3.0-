#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试监听引擎日志输出
"""

import asyncio
import logging
from log_config import get_logger

# 获取监听引擎的日志记录器
logger = get_logger('monitoring_engine')

async def test_logging():
    """测试日志输出"""
    print("开始测试监听引擎日志输出...")
    
    # 测试不同级别的日志
    logger.debug("这是DEBUG级别的日志")
    logger.info("这是INFO级别的日志")
    logger.warning("这是WARNING级别的日志")
    logger.error("这是ERROR级别的日志")
    
    # 测试监听引擎相关的日志
    logger.info("🔧 监听引擎初始化完成")
    logger.info("🚀 启动监听系统")
    logger.info("✅ 监听系统启动成功")
    logger.info("🔍 检查监听任务: test_task_123")
    logger.info("🚀 启动监听搬运任务: 测试频道 (1001-1050)")
    logger.info("✅ 监听搬运任务完成: 测试频道 -> 1050")
    logger.info("🔔 检测到 3 条新消息 from 测试频道")
    logger.info("🔍 开始处理消息: ID=12345 来源=测试频道")
    logger.info("🚀 开始搬运消息: 12345 -> -1001234567890")
    logger.info("✅ 消息搬运成功: 12345")
    
    print("日志测试完成！")

if __name__ == "__main__":
    asyncio.run(test_logging())
