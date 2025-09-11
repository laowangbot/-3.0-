#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搬运引擎修复补丁
专门解决大规模搬运时消息丢失的问题
"""

import asyncio
import logging
from typing import List, Optional
from pyrogram import Client
from pyrogram.types import Message

logger = logging.getLogger(__name__)

class CloningEnginePatch:
    """搬运引擎修复补丁"""
    
    def __init__(self, client: Client):
        self.client = client
    
    async def discover_and_process_messages(self, chat_id: str, start_id: int, end_id: int, 
                                          process_callback=None) -> dict:
        """
        发现并处理消息的改进方法
        
        Args:
            chat_id: 频道ID
            start_id: 起始消息ID
            end_id: 结束消息ID
            process_callback: 消息处理回调函数
            
        Returns:
            dict: 处理结果统计
        """
        logger.info(f"🔍 开始发现和处理消息: {chat_id}, 范围: {start_id} - {end_id}")
        
        # 统计信息
        stats = {
            'total_range': end_id - start_id + 1,
            'actual_found': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'message_ids': []
        }
        
        # 发现实际存在的消息
        actual_message_ids = await self._discover_messages_in_range(
            chat_id, start_id, end_id, stats
        )
        
        if not actual_message_ids:
            logger.warning("❌ 没有发现任何实际消息")
            return stats
        
        logger.info(f"✅ 发现 {len(actual_message_ids)} 条实际消息")
        stats['actual_found'] = len(actual_message_ids)
        
        # 处理发现的消息
        if process_callback:
            await self._process_discovered_messages(
                chat_id, actual_message_ids, process_callback, stats
            )
        
        return stats
    
    async def _discover_messages_in_range(self, chat_id: str, start_id: int, end_id: int, 
                                        stats: dict) -> List[int]:
        """在指定范围内发现实际存在的消息"""
        actual_message_ids = []
        batch_size = 1000
        current_id = start_id
        
        logger.info(f"🔍 开始发现消息，范围: {start_id} - {end_id}")
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                logger.info(f"🔍 检查批次: {current_id} - {batch_end} ({len(message_ids)} 个ID)")
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                
                # 统计结果
                batch_found = 0
                batch_none = 0
                
                for i, msg in enumerate(messages):
                    if msg is not None:
                        actual_message_ids.append(message_ids[i])
                        batch_found += 1
                    else:
                        batch_none += 1
                
                logger.info(f"🔍 批次结果: 发现 {batch_found} 条，缺失 {batch_none} 条")
                
                current_id = batch_end + 1
                
                # 添加延迟避免API限制
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"🔍 发现批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"🔍 发现完成: 总共发现 {len(actual_message_ids)} 条实际消息")
        return actual_message_ids
    
    async def _process_discovered_messages(self, chat_id: str, message_ids: List[int], 
                                         process_callback, stats: dict):
        """处理发现的消息"""
        if not message_ids:
            return
        
        batch_size = 1000
        total_batches = (len(message_ids) + batch_size - 1) // batch_size
        
        logger.info(f"🔄 开始处理 {len(message_ids)} 条消息，分 {total_batches} 个批次")
        
        for i in range(0, len(message_ids), batch_size):
            try:
                batch_ids = message_ids[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                logger.info(f"📦 处理批次 {batch_num}/{total_batches}: {len(batch_ids)} 条消息")
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=batch_ids)
                
                # 过滤有效消息
                valid_messages = [msg for msg in messages if msg is not None]
                
                if not valid_messages:
                    logger.warning(f"批次 {batch_num} 没有有效消息")
                    continue
                
                # 处理消息
                for msg in valid_messages:
                    try:
                        if process_callback:
                            await process_callback(msg)
                        stats['processed'] += 1
                    except Exception as e:
                        logger.warning(f"处理消息失败 {msg.id}: {e}")
                        stats['failed'] += 1
                
                # 更新进度
                progress = (stats['processed'] / len(message_ids)) * 100
                logger.info(f"📊 进度: {stats['processed']}/{len(message_ids)} ({progress:.1f}%)")
                
                # 添加延迟避免API限制
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"处理批次 {batch_num} 失败: {e}")
                continue
        
        logger.info(f"🎉 处理完成: 成功 {stats['processed']} 条，失败 {stats['failed']} 条")

# 使用示例和测试函数
async def test_message_discovery():
    """测试消息发现功能"""
    # 这里需要实际的Client实例
    # client = Client("test", api_id, api_hash)
    # patch = CloningEnginePatch(client)
    
    # 测试发现消息
    # stats = await patch.discover_and_process_messages(
    #     chat_id="@kunkuntv",
    #     start_id=9,
    #     end_id=2096,
    #     process_callback=lambda msg: print(f"处理消息: {msg.id}")
    # )
    
    # print(f"发现统计: {stats}")
    
    pass

# 集成到现有代码的补丁函数
def apply_cloning_patch():
    """应用搬运引擎修复补丁"""
    
    # 这个函数可以替换现有的搬运逻辑
    # 在 cloning_engine.py 中调用
    
    patch_code = '''
    # 在 _execute_cloning 方法中添加以下代码
    
    # 1. 替换消息计数逻辑
    async def _count_actual_messages_improved(self, chat_id: str, start_id: int, end_id: int) -> int:
        """计算实际存在的消息数量"""
        logger.info(f"📊 开始计算实际消息数量: {start_id} - {end_id}")
        actual_count = 0
        batch_size = 1000
        current_id = start_id
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                valid_count = sum(1 for msg in messages if msg is not None)
                actual_count += valid_count
                
                logger.debug(f"📊 批次 {current_id}-{batch_end}: 发现 {valid_count} 条消息")
                current_id = batch_end + 1
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"📊 计算批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"📊 实际消息数量: {actual_count} 条")
        return actual_count
    
    # 2. 在 _execute_cloning 方法开始时调用
    # 替换原有的消息计数逻辑
    actual_total = await self._count_actual_messages_improved(
        task.source_chat_id, 
        task.start_id, 
        task.end_id
    )
    task.total_messages = actual_total
    logger.info(f"📊 实际总消息数: {actual_total}")
    '''
    
    return patch_code

if __name__ == "__main__":
    print("搬运引擎修复补丁")
    print("=" * 50)
    print("问题: 大规模搬运时消息丢失")
    print("原因: 消息ID不连续，但代码假设连续")
    print("解决: 先发现实际存在的消息，再处理")
    print("=" * 50)
    
    # 显示补丁代码
    print("\n补丁代码:")
    print(apply_cloning_patch())

