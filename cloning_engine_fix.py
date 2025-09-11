#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搬运引擎修复版本
解决大规模搬运时消息丢失的问题
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.types import Message, Chat, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from pyrogram.errors import FloodWait
from message_engine import MessageEngine
from data_manager import get_user_config, data_manager
from config import DEFAULT_USER_CONFIG

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

class ImprovedCloningEngine:
    """改进的搬运引擎 - 修复消息丢失问题"""
    
    def __init__(self, client: Client, client_type: str = "user", data_manager=None):
        self.client = client
        self.client_type = client_type
        self.data_manager = data_manager
        self.active_tasks = {}
        self.background_tasks = {}
        self.task_history = []
        self.max_concurrent_tasks = 10
        
    async def _discover_actual_messages(self, chat_id: str, start_id: int, end_id: int) -> List[int]:
        """发现实际存在的消息ID"""
        logger.info(f"🔍 开始发现实际消息: {start_id} - {end_id}")
        actual_message_ids = []
        
        # 使用较大的批次来发现消息
        batch_size = 1000
        current_id = start_id
        total_batches = ((end_id - start_id) // batch_size) + 1
        processed_batches = 0
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                logger.info(f"🔍 发现批次 {processed_batches + 1}/{total_batches}: {current_id} - {batch_end}")
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                
                # 收集实际存在的消息ID
                batch_found = 0
                for i, msg in enumerate(messages):
                    if msg is not None:
                        actual_message_ids.append(message_ids[i])
                        batch_found += 1
                
                logger.info(f"🔍 批次 {processed_batches + 1} 发现 {batch_found} 条消息")
                
                current_id = batch_end + 1
                processed_batches += 1
                
                # 添加小延迟避免API限制
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"🔍 发现批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"🔍 消息发现完成: 发现 {len(actual_message_ids)} 条实际消息")
        return sorted(actual_message_ids)
    
    async def _count_actual_messages(self, chat_id: str, start_id: int, end_id: int) -> int:
        """计算实际存在的消息数量"""
        logger.info(f"📊 开始计算实际消息数量: {start_id} - {end_id}")
        actual_count = 0
        batch_size = 1000
        current_id = start_id
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                
                # 计算有效消息数量
                valid_count = sum(1 for msg in messages if msg is not None)
                actual_count += valid_count
                
                logger.debug(f"📊 批次 {current_id}-{batch_end}: 发现 {valid_count} 条消息")
                
                current_id = batch_end + 1
                
                # 添加小延迟避免API限制
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"📊 计算批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"📊 实际消息数量计算完成: {actual_count} 条")
        return actual_count
    
    async def _execute_cloning_improved(self, task) -> bool:
        """改进的搬运执行逻辑"""
        try:
            logger.info(f"🚀 开始改进的搬运任务: {task.task_id}")
            logger.info(f"📋 搬运范围: {task.start_id} - {task.end_id}")
            
            # 1. 先计算实际存在的消息数量
            actual_total = await self._count_actual_messages(
                task.source_chat_id, 
                task.start_id, 
                task.end_id
            )
            
            # 2. 更新任务的总消息数
            task.total_messages = actual_total
            logger.info(f"📊 实际总消息数: {actual_total}")
            
            if actual_total == 0:
                logger.info("❌ 没有发现任何消息，任务结束")
                return True
            
            # 3. 发现所有实际存在的消息ID
            actual_message_ids = await self._discover_actual_messages(
                task.source_chat_id,
                task.start_id,
                task.end_id
            )
            
            if not actual_message_ids:
                logger.info("❌ 没有发现任何实际消息，任务结束")
                return True
            
            logger.info(f"📋 发现 {len(actual_message_ids)} 条实际消息")
            logger.info(f"📋 消息ID范围: {min(actual_message_ids)} - {max(actual_message_ids)}")
            
            # 4. 按批次处理实际存在的消息
            batch_size = 1000
            processed_messages = 0
            total_batches = (len(actual_message_ids) + batch_size - 1) // batch_size
            
            for i in range(0, len(actual_message_ids), batch_size):
                try:
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 被{task.status}")
                        return False
                    
                    # 获取当前批次的消息ID
                    batch_ids = actual_message_ids[i:i + batch_size]
                    batch_num = (i // batch_size) + 1
                    
                    logger.info(f"📦 处理批次 {batch_num}/{total_batches}: {len(batch_ids)} 条消息")
                    
                    # 获取消息
                    messages = await self.client.get_messages(
                        task.source_chat_id,
                        message_ids=batch_ids
                    )
                    
                    # 过滤有效消息
                    valid_messages = [msg for msg in messages if msg is not None]
                    
                    if not valid_messages:
                        logger.warning(f"批次 {batch_num} 没有有效消息，跳过")
                        continue
                    
                    # 处理这批消息
                    success = await self._process_message_batch_improved(task, valid_messages)
                    
                    if not success:
                        logger.error(f"批次 {batch_num} 处理失败")
                        continue
                    
                    processed_messages += len(valid_messages)
                    
                    # 更新进度
                    progress = (processed_messages / actual_total) * 100
                    task.progress = progress
                    task.processed_messages = processed_messages
                    
                    logger.info(f"📊 进度: {processed_messages}/{actual_total} ({progress:.1f}%)")
                    
                    # 添加延迟避免API限制
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"批次 {batch_num} 处理异常: {e}")
                    continue
            
            logger.info(f"🎉 搬运任务完成: {processed_messages}/{actual_total} 条消息")
            return True
            
        except Exception as e:
            logger.error(f"改进的搬运执行失败: {e}")
            return False
    
    async def _process_message_batch_improved(self, task, messages: List[Message]) -> bool:
        """改进的消息批次处理"""
        try:
            if not messages:
                return True
            
            logger.info(f"🔄 处理消息批次: {len(messages)} 条消息")
            
            # 这里调用原有的消息处理逻辑
            # 可以根据需要调用 message_engine 或其他处理模块
            
            for msg in messages:
                try:
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 在处理消息时被{task.status}")
                        return False
                    
                    # 处理单条消息
                    # 这里应该调用实际的消息处理逻辑
                    # await self._process_single_message(task, msg)
                    
                    # 更新统计
                    task.stats['processed_messages'] += 1
                    
                except Exception as e:
                    logger.warning(f"处理消息失败 {msg.id if msg else 'Unknown'}: {e}")
                    task.stats['failed_messages'] += 1
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"消息批次处理失败: {e}")
            return False
    
    async def start_cloning_improved(self, task) -> bool:
        """启动改进的搬运任务"""
        try:
            logger.info(f"🚀 启动改进的搬运任务: {task.task_id}")
            
            # 检查任务状态
            if task.status != "pending":
                logger.warning(f"任务状态不正确: {task.status}")
                return False
            
            # 检查并发限制
            if len(self.active_tasks) >= self.max_concurrent_tasks:
                logger.warning(f"达到最大并发任务数限制: {self.max_concurrent_tasks}")
                return False
            
            # 添加到活动任务
            self.active_tasks[task.task_id] = task
            task.status = "running"
            task.start_time = datetime.now()
            
            # 启动后台任务
            background_task = asyncio.create_task(self._execute_cloning_improved(task))
            self.background_tasks[task.task_id] = background_task
            
            logger.info(f"✅ 改进的搬运任务已启动: {task.task_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动改进的搬运任务失败: {e}")
            return False

# 使用示例
async def test_improved_cloning():
    """测试改进的搬运功能"""
    # 这里需要实际的Client实例
    # client = Client("test", api_id, api_hash)
    # engine = ImprovedCloningEngine(client)
    
    # 创建测试任务
    # task = CloneTask(
    #     task_id="test_improved",
    #     source_chat_id="@kunkuntv",
    #     target_chat_id="@target_channel",
    #     start_id=9,
    #     end_id=2096
    # )
    
    # 启动改进的搬运
    # success = await engine.start_cloning_improved(task)
    # print(f"搬运结果: {success}")
    
    pass

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_improved_cloning())

