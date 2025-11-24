# ==================== 反查重集成模块 ====================
"""
反查重集成模块
将成人内容反查重功能集成到现有的搬运引擎中
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from adult_content_rewriter import AdultContentProcessor
from log_config import get_logger

logger = get_logger(__name__)

class AntiDetectionIntegration:
    """反查重集成类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """初始化反查重集成"""
        self.config = config or {}
        self.processor = AdultContentProcessor()
        self.enabled = self.config.get('anti_detection_enabled', True)
        self.processing_stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "similarity_reduced": 0
        }
        
        logger.info(f"🔧 反查重系统初始化完成 - 启用状态: {self.enabled}")
    
    async def process_message_for_cloning(self, message: Message, target_chat_id: str) -> Tuple[bool, Optional[Message], Optional[str]]:
        """为搬运处理消息"""
        if not self.enabled:
            return True, message, None
        
        try:
            # 检查是否是媒体组
            if message.media_group_id:
                return await self._process_media_group(message, target_chat_id)
            else:
                return await self._process_single_message(message, target_chat_id)
                
        except Exception as e:
            logger.error(f"❌ 反查重处理失败: {e}")
            self.processing_stats["failed_processed"] += 1
            return False, message, str(e)
    
    async def _process_media_group(self, message: Message, target_chat_id: str) -> Tuple[bool, Optional[Message], Optional[str]]:
        """处理媒体组"""
        try:
            # 获取媒体组的所有消息
            media_group_messages = await self._get_media_group_messages(message)
            
            if not media_group_messages:
                return True, message, None
            
            # 处理文本内容
            original_caption = message.caption or ""
            text_result = self.processor.content_rewriter.rewrite_content(original_caption)
            
            # 处理媒体文件
            processed_media = []
            for msg in media_group_messages:
                if msg.media:
                    processed_media.append(await self._process_media_file(msg))
            
            # 创建新的媒体组
            new_media_group = await self._create_new_media_group(processed_media, text_result)
            
            self.processing_stats["successful_processed"] += 1
            if text_result["similarity"] < 0.3:
                self.processing_stats["similarity_reduced"] += 1
            
            logger.info(f"✅ 媒体组反查重处理完成 - 相似度: {text_result['similarity']:.2f}")
            
            return True, new_media_group, text_result["rewritten_content"]
            
        except Exception as e:
            logger.error(f"❌ 媒体组处理失败: {e}")
            return False, message, str(e)
    
    async def _process_single_message(self, message: Message, target_chat_id: str) -> Tuple[bool, Optional[Message], Optional[str]]:
        """处理单条消息"""
        try:
            if not message.text and not message.caption:
                return True, message, None
            
            # 处理文本内容
            original_text = message.text or message.caption or ""
            text_result = self.processor.content_rewriter.rewrite_content(original_text)
            
            # 创建新消息
            new_message = await self._create_new_message(message, text_result)
            
            self.processing_stats["successful_processed"] += 1
            if text_result["similarity"] < 0.3:
                self.processing_stats["similarity_reduced"] += 1
            
            logger.info(f"✅ 单消息反查重处理完成 - 相似度: {text_result['similarity']:.2f}")
            
            return True, new_message, text_result["rewritten_content"]
            
        except Exception as e:
            logger.error(f"❌ 单消息处理失败: {e}")
            return False, message, str(e)
    
    async def _get_media_group_messages(self, message: Message) -> List[Message]:
        """获取媒体组的所有消息"""
        # 这里需要根据您的实际实现来获取媒体组消息
        # 暂时返回单个消息，实际实现时需要获取完整的媒体组
        return [message]
    
    async def _process_media_file(self, message: Message) -> Dict[str, Any]:
        """处理媒体文件"""
        return {
            "message": message,
            "file_id": message.file_id,
            "file_type": message.media.__class__.__name__,
            "processed": True,
            "new_identifier": self.processor.media_processor.generate_file_identifier(
                message.file_id,
                message.file_size or 0,
                int(time.time())
            )
        }
    
    async def _create_new_media_group(self, processed_media: List[Dict], text_result: Dict) -> Message:
        """创建新的媒体组"""
        # 这里需要根据您的实际实现来创建新的媒体组
        # 暂时返回原始消息，实际实现时需要创建新的媒体组
        return processed_media[0]["message"] if processed_media else None
    
    async def _create_new_message(self, original_message: Message, text_result: Dict) -> Message:
        """创建新消息"""
        # 这里需要根据您的实际实现来创建新消息
        # 暂时返回原始消息，实际实现时需要创建新消息
        return original_message
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        stats = self.processing_stats.copy()
        stats.update(self.processor.get_processing_stats())
        
        # 计算成功率
        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["successful_processed"] / stats["total_processed"]
        else:
            stats["success_rate"] = 0.0
        
        # 计算相似度降低率
        if stats["successful_processed"] > 0:
            stats["similarity_reduction_rate"] = stats["similarity_reduced"] / stats["successful_processed"]
        else:
            stats["similarity_reduction_rate"] = 0.0
        
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.processing_stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "similarity_reduced": 0
        }
        self.processor.reset_stats()

# 集成到搬运引擎的装饰器
def with_anti_detection(original_method):
    """反查重装饰器"""
    async def wrapper(self, *args, **kwargs):
        # 检查是否启用反查重
        if hasattr(self, 'anti_detection') and self.anti_detection.enabled:
            # 在搬运前进行反查重处理
            result = await self.anti_detection.process_message_for_cloning(*args, **kwargs)
            if result[0]:  # 处理成功
                return await original_method(self, *args, **kwargs)
            else:  # 处理失败
                logger.warning(f"⚠️ 反查重处理失败，使用原始内容: {result[2]}")
        
        return await original_method(self, *args, **kwargs)
    
    return wrapper

# 配置示例
ANTI_DETECTION_CONFIG = {
    "anti_detection_enabled": True,
    "similarity_threshold": 0.3,
    "auto_retry": True,
    "max_retry_attempts": 3,
    "retry_delay": 1.0,
    "logging_enabled": True,
    "stats_collection": True
}

