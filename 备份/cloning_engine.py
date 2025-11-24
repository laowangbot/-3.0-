# ==================== 搬运引擎 ====================
"""
搬运引擎
负责消息搬运的核心逻辑、进度监控、错误处理和断点续传
"""

import asyncio
import logging
import time
import os
import shutil
from typing import Dict, List, Any, Optional, Tuple, Callable, Union, AsyncGenerator
from datetime import datetime, timedelta
from dataclasses import dataclass
from pyrogram.client import Client
from pyrogram.types import (
    Message, ChatPreview, ChatMember, 
    InputMediaPhoto, InputMediaVideo, InputMediaDocument,
    InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, RPCError, ChannelPrivate, ChatAdminRequired, UserNotParticipant

from message_engine import MessageEngine
from data_manager import get_user_config, data_manager
from config import DEFAULT_USER_CONFIG
from task_state_manager import get_global_task_state_manager, TaskStatus
from anti_detection_integration import AntiDetectionIntegration, ANTI_DETECTION_CONFIG

# 配置日志 - 使用优化的日志配置
from log_config import get_logger
logger = get_logger(__name__)

class RateLimiter:
    """速率限制器 - 用于管理媒体组发送的动态延迟和限流预防"""
    
    def __init__(self, base_delay: float = 6.0, min_delay: float = 3.0, max_delay: float = 30.0,
                 max_groups_per_minute: float = 6.0):
        """
        初始化速率限制器
        
        Args:
            base_delay: 基础延迟（秒）
            min_delay: 最小延迟（秒）
            max_delay: 最大延迟（秒）
            max_groups_per_minute: 每分钟最大发送媒体组数
        """
        self.base_delay = base_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = base_delay
        self.max_groups_per_minute = max_groups_per_minute
        
        # 发送时间记录（用于计算发送速率）
        self.send_times: List[float] = []
        self.window_size = 60.0  # 时间窗口（秒）
        
        # 限流历史记录
        self.flood_wait_history: List[Tuple[float, float]] = []  # [(时间, 等待秒数)]
        self.flood_wait_window = 300.0  # 限流历史窗口（5分钟）
        
        # 连续成功/失败计数
        self.consecutive_successes = 0
        self.consecutive_flood_waits = 0
        
        # 严重限流阈值
        self.severe_rate_limit_threshold = 1000.0  # 秒
    
    def get_current_delay(self) -> float:
        """获取当前延迟时间"""
        return max(self.min_delay, min(self.current_delay, self.max_delay))
    
    def record_send(self, current_time: float):
        """记录发送时间"""
        self.send_times.append(current_time)
        # 清理过期的发送记录
        self.send_times = [t for t in self.send_times if current_time - t < self.window_size]
    
    def check_rate_limit(self, current_time: float) -> Optional[float]:
        """
        检查是否超过速率限制
        
        Returns:
            如果需要等待，返回等待时间（秒），否则返回None
        """
        # 清理过期的发送记录
        self.send_times = [t for t in self.send_times if current_time - t < self.window_size]
        
        if len(self.send_times) == 0:
            return None
        
        # 计算当前速率（媒体组/分钟）
        rate = len(self.send_times) / (self.window_size / 60.0)
        
        if rate >= self.max_groups_per_minute:
            # 计算需要等待的时间
            oldest_time = min(self.send_times)
            time_passed = current_time - oldest_time
            wait_time = self.window_size - time_passed
            return max(0, wait_time)
        
        return None
    
    def check_recent_flood_wait(self, current_time: float) -> bool:
        """检查最近是否有限流历史"""
        # 清理过期的限流记录
        self.flood_wait_history = [
            (t, w) for t, w in self.flood_wait_history 
            if current_time - t < self.flood_wait_window
        ]
        
        # 如果最近有限流，返回True
        if len(self.flood_wait_history) > 0:
            return True
        
        return False
    
    def adjust_after_success(self):
        """成功发送后调整延迟（渐进减少，但有下限）"""
        self.consecutive_successes += 1
        self.consecutive_flood_waits = 0
        
        # 连续成功5次后，轻微减少延迟
        if self.consecutive_successes >= 5:
            # 每次减少5%，但不能低于最小延迟
            new_delay = self.current_delay * 0.95
            if new_delay >= self.min_delay:
                self.current_delay = new_delay
                logger.debug(f"[速率控制] 连续成功 {self.consecutive_successes} 次，延迟减少到 {self.current_delay:.2f} 秒")
                self.consecutive_successes = 0  # 重置计数
    
    def adjust_after_flood_wait(self, wait_time: float, current_time: float):
        """
        遇到限流后调整延迟（大幅增加）
        
        Args:
            wait_time: FloodWait的等待时间（秒）
            current_time: 当前时间戳
        """
        self.consecutive_flood_waits += 1
        self.consecutive_successes = 0
        
        # 记录限流历史
        self.flood_wait_history.append((current_time, wait_time))
        
        # 根据等待时间调整延迟
        if wait_time >= self.severe_rate_limit_threshold:
            # 严重限流，大幅增加延迟
            self.current_delay = min(self.max_delay, self.current_delay * 2.5)
            logger.warning(f"[速率控制] 检测到严重限流 ({wait_time:.0f}秒)，延迟增加到 {self.current_delay:.2f} 秒")
        elif wait_time >= 100:
            # 中等限流，显著增加延迟
            self.current_delay = min(self.max_delay, self.current_delay * 2.0)
            logger.warning(f"[速率控制] 检测到中等限流 ({wait_time:.0f}秒)，延迟增加到 {self.current_delay:.2f} 秒")
        else:
            # 轻微限流，适度增加延迟
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
            logger.warning(f"[速率控制] 检测到轻微限流 ({wait_time:.0f}秒)，延迟增加到 {self.current_delay:.2f} 秒")
        
        # 如果最近多次限流，进一步增加延迟
        if self.consecutive_flood_waits >= 2:
            self.current_delay = min(self.max_delay, self.current_delay * 1.3)
            logger.warning(f"[速率控制] 连续 {self.consecutive_flood_waits} 次限流，延迟进一步增加到 {self.current_delay:.2f} 秒")
    
    def get_delay_with_prevention(self, current_time: float) -> float:
        """
        获取延迟时间（包含预防性限流）
        
        如果最近有限流历史，自动增加延迟
        """
        base_delay = self.get_current_delay()
        
        # 如果最近有限流，增加预防性延迟
        if self.check_recent_flood_wait(current_time):
            preventive_delay = base_delay * 1.5  # 增加50%作为预防
            logger.debug(f"[速率控制] 检测到最近的限流历史，预防性延迟增加到 {preventive_delay:.2f} 秒")
            return min(preventive_delay, self.max_delay)
        
        return base_delay
    
    def is_severe_rate_limit(self, wait_time: float) -> bool:
        """判断是否为严重限流"""
        return wait_time >= self.severe_rate_limit_threshold

@dataclass
class DownloadedMediaGroup:
    """已下载的媒体组数据"""
    group_id: Any
    group_comments: List[Message]
    media_list: List[Any]
    downloaded_files: List[str]
    queue_index: int
    total_count: int = 0  # 动态总数（包括拆分后的媒体组）

class CloneTask:
    """搬运任务类"""
    
    def __init__(self, task_id: str, source_chat_id: str, target_chat_id: str,
                 start_id: Optional[int] = None, end_id: Optional[int] = None,
                 config: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None):
        """初始化搬运任务"""
        self.task_id = task_id
        self.source_chat_id = source_chat_id
        self.target_chat_id = target_chat_id
        self.start_id = start_id
        self.end_id = end_id
        self.config = config or {}
        self.user_id = user_id
        
        # 任务状态
        self.status = "pending"  # pending, running, completed, failed, paused, cancelled
        self.progress = 0.0  # 0.0 - 100.0
        self.current_message_id = start_id or 0
        self.total_messages = 0
        self.processed_messages = 0
        self.failed_messages = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # 断点续传相关字段
        self.last_processed_message_id: Optional[int] = None  # 最后处理的消息ID
        self.resume_from_id: Optional[int] = None  # 恢复时的起始消息ID
        self.is_resumed = False  # 是否为恢复的任务
        
        # 频道名称信息
        self.source_channel_name: Optional[str] = None
        self.target_channel_name: Optional[str] = None
        
        # 取消标志
        self._cancelled = False  # 内部取消标志，用于立即停止任务
        
        # 重复检测相关字段
        self.processed_message_ids = set()  # 已处理的消息ID集合
        self.duplicate_count = 0  # 重复消息计数
        
        # 统计信息
        self.stats = {
            'total_messages': 0,
            'processed_messages': 0,
            'failed_messages': 0,
            'skipped_messages': 0,
            'media_messages': 0,
            'text_messages': 0,
            'filtered_messages': 0,
            'media_groups': 0
        }
        
        # 任务状态管理器
        self.task_state_manager = get_global_task_state_manager()
        self._last_save_time = 0
        self._save_interval = 10  # 10秒保存一次进度
        
        # 添加last_activity_time属性
        self.last_activity_time: Optional[datetime] = None
        
        # 添加is_running属性
        self.is_running = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'task_id': self.task_id,
            'source_chat_id': self.source_chat_id,
            'target_chat_id': self.target_chat_id,
            'start_id': self.start_id,
            'end_id': self.end_id,
            'status': self.status,
            'progress': self.progress,
            'current_message_id': self.current_message_id,
            'total_messages': self.total_messages,
            'processed_messages': self.processed_messages,
            'failed_messages': self.failed_messages,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'last_processed_message_id': self.last_processed_message_id,
            'resume_from_id': self.resume_from_id,
            'is_resumed': self.is_resumed,
            'user_id': self.user_id,
            'source_channel_name': self.source_channel_name,
            'target_channel_name': self.target_channel_name,
            'stats': self.stats.copy(),
            'config': self.config.copy() if self.config else {}
        }
    
    def is_cancelled(self) -> bool:
        """检查任务是否已被取消"""
        return self.status == "cancelled"
    
    def is_paused(self) -> bool:
        """检查任务是否已暂停"""
        return self.status == "paused"
    
    def should_stop(self) -> bool:
        """检查任务是否应该停止（取消或暂停）"""
        return self.status in ["cancelled", "paused"] or self._cancelled
    
    def is_duplicate_message(self, message_id: int) -> bool:
        """检查消息是否已处理过（重复检测）"""
        # 临时禁用重复检测，因为逻辑有问题
        # TODO: 重新设计重复检测逻辑
        return False
        
        # 原始逻辑（已禁用）
        # if message_id in self.processed_message_ids:
        #     self.duplicate_count += 1
        #     logger.warning(f"🔄 检测到重复消息: {message_id} (第{self.duplicate_count}次重复)")
        #     return True
        # return False
    
    def mark_message_processed(self, message_id: int):
        """标记消息为已处理"""
        self.processed_message_ids.add(message_id)
    
    def save_progress(self, message_id: int):
        """保存当前进度"""
        self.last_processed_message_id = message_id
        self.current_message_id = message_id
        
        # 异步保存到数据库
        asyncio.create_task(self._async_save_progress())
    
    async def _async_save_progress(self):
        """异步保存进度"""
        try:
            current_time = time.time()
            if current_time - self._last_save_time < self._save_interval:
                return  # 保存间隔未到
            
            # 更新任务状态
            await self.task_state_manager.update_task_progress(
                self.task_id,
                status=TaskStatus(self.status),
                progress=self.progress,
                current_message_id=self.current_message_id,
                total_messages=self.total_messages,
                processed_messages=self.processed_messages,
                failed_messages=self.failed_messages,
                last_processed_message_id=self.last_processed_message_id,
                stats=self.stats
            )
            
            self._last_save_time = current_time
            logger.debug(f"任务进度已保存: {self.task_id}")
            
        except Exception as e:
            logger.error(f"保存任务进度失败 {self.task_id}: {e}")
    
    async def save_final_state(self):
        """保存最终状态"""
        try:
            await self.task_state_manager.update_task_progress(
                self.task_id,
                status=TaskStatus(self.status),
                progress=self.progress,
                current_message_id=self.current_message_id,
                total_messages=self.total_messages,
                processed_messages=self.processed_messages,
                failed_messages=self.failed_messages,
                last_processed_message_id=self.last_processed_message_id,
                end_time=self.end_time,
                stats=self.stats
            )
            
            # 立即保存
            await self.task_state_manager.save_task_progress(self.task_id)
            logger.info(f"任务最终状态已保存: {self.task_id}")
            
        except Exception as e:
            logger.error(f"保存任务最终状态失败 {self.task_id}: {e}")
    
    def prepare_for_resume(self, from_message_id: int):
        """准备断点续传"""
        self.resume_from_id = from_message_id
        self.is_resumed = True
        # 不改变状态，让调用者决定状态

class CloningEngine:
    """搬运引擎类"""
    
    def __init__(self, client: Client, config: Dict[str, Any], data_manager=None, bot_id: str = "default_bot"):
        """初始化搬运引擎"""
        self.client = client
        self.config = config
        self.data_manager = data_manager
        self.bot_id = bot_id
        self.message_engine = MessageEngine(config)
        self.active_tasks: Dict[str, CloneTask] = {}
        self.task_history: List[Dict[str, Any]] = []
        
        # 初始化AI改写器为None
        self.ai_rewriter = None
        
        # User API 客户端（用于获取评论）
        self.user_api_client = None
        
        # 任务状态管理器
        self.task_state_manager = get_global_task_state_manager(bot_id)
        
        # 记录客户端类型
        self.client_type = type(client).__name__
        logger.info(f"🔧 搬运引擎初始化，使用客户端类型: {self.client_type}")
        self.background_tasks: Dict[str, asyncio.Task] = {}  # 保存后台任务引用
        
        # 性能设置 - User API 模式优化 + 安全限制
        self.message_delay = config.get('message_delay', 0.1)  # 安全延迟: 0.1秒 (10条/秒)
        self.batch_size = config.get('batch_size', 500)  # 安全批次: 500条消息
        self.retry_attempts = config.get('retry_attempts', 3)  # 安全重试: 3次
        self.retry_delay = config.get('retry_delay', 1.0)  # 安全重试延迟: 1秒
        self.max_concurrent_tasks = config.get('max_concurrent_tasks', 10)  # 安全并发: 10个任务
        self.max_concurrent_channels = config.get('max_concurrent_channels', 5)  # 安全频道并发: 5个
        
        # 媒体组安全设置
        self.media_group_sequential = True  # 媒体组必须顺序处理
        self.media_group_delay = 0.5  # 媒体组间延迟0.5秒
        
        # 随机延迟设置（避免规律性操作）
        self.random_delay_range = (0.05, 0.15)  # 随机延迟范围：0.05-0.15秒
        
        # API限流控制
        self.api_call_count = 0  # API调用计数器
        self.api_call_window = 60  # 时间窗口（秒）
        self.max_api_calls_per_window = 600  # 每窗口最大调用次数（10条/秒）
        self.api_call_times = []  # API调用时间记录
        self.last_rate_limit_warning = 0  # 上次限流警告时间
        
        # 消息缓存
        self.message_cache = {}  # 消息缓存
        self.last_cache_cleanup = 0  # 上次缓存清理时间
        self.cache_cleanup_interval = 300  # 缓存清理间隔（秒）
        self.max_memory_messages = 1000  # 最大内存消息数
        
        # 进度回调
        self.progress_callback: Optional[Callable] = None
    
    async def _cleanup_message_cache(self):
        """清理消息缓存，释放内存"""
        try:
            current_time = time.time()
            if current_time - self.last_cache_cleanup < self.cache_cleanup_interval:
                return
            
            # 清理过期缓存
            cache_keys_to_remove = []
            for key, (message, timestamp) in self.message_cache.items():
                if current_time - timestamp > 300:  # 5分钟过期
                    cache_keys_to_remove.append(key)
            
            for key in cache_keys_to_remove:
                del self.message_cache[key]
            
            # 如果缓存仍然过大，清理最旧的条目
            if len(self.message_cache) > self.max_memory_messages:
                sorted_items = sorted(self.message_cache.items(), key=lambda x: x[1][1])
                items_to_remove = len(self.message_cache) - self.max_memory_messages
                for key, _ in sorted_items[:items_to_remove]:
                    del self.message_cache[key]
            
            self.last_cache_cleanup = current_time
            logger.info(f"🧹 缓存清理完成，当前缓存大小: {len(self.message_cache)}")
            
        except Exception as e:
            logger.warning(f"缓存清理失败: {e}")
    
    async def _check_api_rate_limit(self) -> bool:
        """检查API调用频率限制"""
        try:
            current_time = time.time()
            
            # 清理过期的API调用记录
            self.api_call_times = [t for t in self.api_call_times if current_time - t < self.api_call_window]
            
            # 检查是否超过限制
            if len(self.api_call_times) >= self.max_api_calls_per_window:
                # 计算需要等待的时间
                oldest_call = min(self.api_call_times)
                wait_time = self.api_call_window - (current_time - oldest_call)
                
                if wait_time > 0:
                    logger.warning(f"⚠️ API调用频率过高，需要等待 {wait_time:.1f} 秒")
                    await asyncio.sleep(wait_time)
                    return False
            
            # 记录当前API调用
            self.api_call_times.append(current_time)
            self.api_call_count += 1
            
            # 定期警告
            if current_time - self.last_rate_limit_warning > 300:  # 5分钟警告一次
                current_rate = len(self.api_call_times) / self.api_call_window
                if current_rate > self.max_api_calls_per_window * 0.8:  # 超过80%时警告
                    logger.warning(f"⚠️ API调用频率较高: {current_rate:.1f} 次/秒")
                    self.last_rate_limit_warning = current_time
            
            return True
            
        except Exception as e:
            logger.warning(f"API限流检查失败: {e}")
            return True
    
    async def _apply_safe_delay(self):
        """应用安全延迟（基础延迟 + 随机延迟）"""
        try:
            import random
            # 基础延迟
            base_delay = self.message_delay
            # 随机延迟
            random_delay = random.uniform(*self.random_delay_range)
            # 总延迟
            total_delay = base_delay + random_delay
            
            logger.debug(f"⏳ 应用安全延迟: {total_delay:.3f}秒 (基础: {base_delay:.3f}s + 随机: {random_delay:.3f}s)")
            await asyncio.sleep(total_delay)
            
        except Exception as e:
            logger.warning(f"应用安全延迟失败: {e}")
            await asyncio.sleep(self.message_delay)  # 降级到基础延迟
        self.api_call_window = 60  # 时间窗口（秒）
        self.max_api_calls_per_window = 600  # 每窗口最大调用次数（10条/秒）
        self.api_call_times = []  # API调用时间记录
        self.last_rate_limit_warning = 0  # 上次限流警告时间
    
    async def get_effective_config_for_pair(self, user_id: str, pair_id: str) -> Dict[str, Any]:
        """获取频道组的有效配置（优先使用独立配置，否则使用全局配置）"""
        try:
            # 获取用户配置
            if self.data_manager:
                user_config = await self.data_manager.get_user_config(user_id)
            else:
                user_config = await get_user_config(user_id)
            
            # 检查是否有频道组独立过滤配置
            # 如果是频道管理的虚拟pair_id，从admin_channel_filters获取配置
            if pair_id.startswith('admin_test_'):
                channel_id = pair_id.replace('admin_test_', '')
                channel_filters = user_config.get('admin_channel_filters', {}).get(channel_id, {})
                independent_enabled = channel_filters.get('independent_enabled', False)
            else:
                channel_filters = user_config.get('channel_filters', {}).get(pair_id, {})
                independent_enabled = channel_filters.get('independent_enabled', False)
            
            # 获取频道名字用于显示
            channel_name = "未知频道"
            if pair_id.startswith("admin_test_"):
                channel_id = pair_id.replace("admin_test_", "")
                # 尝试从配置中获取频道名字
                channel_name = f"频道({channel_id})"
            
            # 频道名字将在后续的调用中通过其他方式传递
            
            # 添加详细的调试信息（仅在DEBUG模式下显示）
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"频道组 {channel_name} 配置检查:")
                logger.debug(f"  • 用户配置中的channel_filters: {list(user_config.get('channel_filters', {}).keys())}")
                logger.debug(f"  • 当前频道组配置: {channel_filters}")
                logger.debug(f"  • independent_enabled: {independent_enabled}")
                logger.debug(f"  • 全局tail_text: '{user_config.get('tail_text', '')}'")
                logger.debug(f"  • 频道组tail_text: '{channel_filters.get('tail_text', '')}'")
                logger.debug(f"  • 频道组tail_frequency: {channel_filters.get('tail_frequency', 'not_set')}")
                logger.debug(f"  • 频道组tail_position: {channel_filters.get('tail_position', 'not_set')}")
            
            if independent_enabled:
                # 使用频道组独立配置
                logger.debug(f"频道组 {channel_name} 使用独立过滤配置")
                logger.debug(f"频道组 {channel_name} 原始配置: {channel_filters}")
                effective_config = {
                    # 关键字过滤 - 只有在启用时才设置
                    'filter_keywords': channel_filters.get('keywords', []) if channel_filters.get('keywords_enabled', False) else [],
                    
                    # 敏感词替换 - 只有在启用时才设置
                    'replacement_words': channel_filters.get('replacements', {}) if channel_filters.get('replacements_enabled', False) else {},
                    
                    # 内容移除
                    'content_removal': channel_filters.get('content_removal', False),
                    'content_removal_mode': channel_filters.get('content_removal_mode', 'text_only'),
                    
                    # 链接移除 - 映射到增强链接过滤
                    'remove_links': channel_filters.get('remove_links', channel_filters.get('links_removal', False)),
                    'remove_magnet_links': channel_filters.get('remove_magnet_links', False),
                    'remove_all_links': channel_filters.get('remove_all_links', False),
                    'remove_links_mode': channel_filters.get('remove_links_mode', 'links_only'),
                    
                    # 增强过滤 - 独立的增强过滤设置
                    'enhanced_filter_enabled': channel_filters.get('enhanced_filter_enabled', channel_filters.get('links_removal', False)),
                    'enhanced_filter_mode': channel_filters.get('enhanced_filter_mode', channel_filters.get('links_removal_mode', 'moderate')) if channel_filters.get('enhanced_filter_mode', channel_filters.get('links_removal_mode', 'moderate')) in ['aggressive', 'moderate', 'conservative'] else 'moderate',
                    
                    # 调试日志
                    '_debug_enhanced_filter_enabled': channel_filters.get('enhanced_filter_enabled'),
                    '_debug_links_removal': channel_filters.get('links_removal'),
                    
                    # 用户名移除
                    'remove_usernames': channel_filters.get('remove_usernames', channel_filters.get('usernames_removal', False)),
                    
                    # 按钮移除
                    'filter_buttons': channel_filters.get('filter_buttons', channel_filters.get('buttons_removal', False)),
                    'button_filter_mode': channel_filters.get('buttons_removal_mode', channel_filters.get('button_filter_mode', 'remove_buttons_only')),
                    
                    # 小尾巴和附加按钮
                    'tail_text': channel_filters.get('tail_text', ''),
                    'tail_position': channel_filters.get('tail_position', 'end'),
                    'tail_frequency': channel_filters.get('tail_frequency', 'always'),
                    'tail_interval': channel_filters.get('tail_interval', 5),
                    'tail_probability': channel_filters.get('tail_probability', 0.3),
                    
                    'additional_buttons': channel_filters.get('additional_buttons', []),
                    'button_frequency': channel_filters.get('button_frequency', 'always'),
                    'button_interval': channel_filters.get('button_interval', 5),
                    'button_probability': channel_filters.get('button_probability', 0.3),
                    
                    # 评论区搬运配置
                    'clone_comments': channel_filters.get('clone_comments', False),
                    'comment_clone_limit': channel_filters.get('comment_clone_limit', 50),
                    'comment_clone_sort': channel_filters.get('comment_clone_sort', 'chronological'),
                }
                
                # 添加调试信息（仅在DEBUG模式下显示）
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"频道组 {channel_name} 映射后的配置:")
                    logger.debug(f"  • filter_keywords: {effective_config['filter_keywords']}")
                    logger.debug(f"  • content_removal: {effective_config['content_removal']}")
                    logger.debug(f"  • remove_links: {effective_config['remove_links']}")
                    logger.debug(f"  • remove_usernames: {effective_config['remove_usernames']}")
                    logger.debug(f"  • filter_buttons: {effective_config['filter_buttons']}")
                    logger.debug(f"  • enhanced_filter_enabled: {effective_config['enhanced_filter_enabled']}")
                    logger.debug(f"  • enhanced_filter_mode: {effective_config['enhanced_filter_mode']}")
                    logger.debug(f"  • tail_text: '{effective_config['tail_text']}'")
                    logger.debug(f"  • tail_frequency: {effective_config['tail_frequency']}")
                    logger.debug(f"  • tail_position: {effective_config['tail_position']}")
                    logger.debug(f"  • additional_buttons: {effective_config['additional_buttons']}")
                    logger.debug(f"  • clone_comments: {effective_config['clone_comments']}")
                    logger.debug(f"  • comment_clone_limit: {effective_config['comment_clone_limit']}")
                    logger.debug(f"  • comment_clone_sort: {effective_config['comment_clone_sort']}")
                    
                    # 添加原始频道组配置调试
                    logger.debug(f"频道组 {channel_name} 原始配置:")
                    logger.debug(f"  • channel_filters: {channel_filters}")
                    logger.debug(f"  • 是否使用频道组配置: {pair_id in user_config.get('channel_filters', {})}")
            else:
                # 使用全局配置
                logger.debug(f"频道组 {channel_name} 使用全局过滤配置")
                effective_config = {
                    'filter_keywords': user_config.get('filter_keywords', []) if user_config.get('keywords_enabled', False) else [],
                    'replacement_words': user_config.get('replacement_words', {}) if user_config.get('replacements_enabled', False) else {},
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'remove_links': user_config.get('remove_links', False),
                    'remove_magnet_links': user_config.get('remove_magnet_links', False),
                    'remove_all_links': user_config.get('remove_all_links', False),
                    'remove_links_mode': user_config.get('remove_links_mode', 'links_only'),
                    'remove_usernames': user_config.get('remove_usernames', False),
                    'filter_buttons': user_config.get('filter_buttons', False),
                    'button_filter_mode': user_config.get('button_filter_mode', 'remove_all'),
                    'enhanced_filter_enabled': user_config.get('enhanced_filter_enabled', False),
                    'enhanced_filter_mode': user_config.get('enhanced_filter_mode', 'moderate'),
                    'tail_text': user_config.get('tail_text', ''),
                    'tail_position': user_config.get('tail_position', 'end'),
                    'tail_frequency': user_config.get('tail_frequency', 'always'),
                    'tail_interval': user_config.get('tail_interval', 5),
                    'tail_probability': user_config.get('tail_probability', 0.3),
                    'additional_buttons': user_config.get('additional_buttons', []),
                    'button_frequency': user_config.get('button_frequency', 'always'),
                    'button_interval': user_config.get('button_interval', 5),
                    'button_probability': user_config.get('button_probability', 0.3),
                    
                    # 评论区搬运配置（从全局配置读取）
                    'clone_comments': user_config.get('clone_comments', False),
                    'comment_clone_limit': user_config.get('comment_clone_limit', 50),
                    'comment_clone_sort': user_config.get('comment_clone_sort', 'chronological'),
                }
            
            # 合并基础配置（但不覆盖频道组特定配置）
            base_config = self.config.copy()
            # 移除可能冲突的键
            for key in ['filter_keywords', 'replacement_words', 'content_removal', 'remove_links', 
                       'remove_magnet_links', 'remove_all_links', 'remove_usernames', 'filter_buttons',
                       'enhanced_filter_enabled', 'enhanced_filter_mode']:
                if key in effective_config:
                    base_config.pop(key, None)
            
            effective_config.update(base_config)
            
            logger.debug(f"频道组 {pair_id} 最终有效配置: {effective_config}")
            return effective_config
            
        except Exception as e:
            logger.error(f"获取频道组 {pair_id} 有效配置失败: {e}")
            # 返回基础配置
            return self.config.copy()
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    async def create_task(self, source_chat_id: str, target_chat_id: str,
                         start_id: Optional[int] = None, end_id: Optional[int] = None,
                         config: Optional[Dict[str, Any]] = None,
                         source_username: str = "", target_username: str = "",
                         task_id: Optional[str] = None) -> CloneTask:
        """创建新的搬运任务"""
        if task_id is None:
            task_id = f"clone_{int(time.time())}_{len(self.active_tasks)}"
        
        try:
            # 添加超时保护的频道验证
            logger.debug(f"🔍 开始验证频道: {source_chat_id} -> {target_chat_id}")
            validation_result = await asyncio.wait_for(
                self._validate_channels(source_chat_id, target_chat_id, source_username, target_username),
                timeout=60.0  # 增加到60秒超时
            )
            is_valid, validated_source_id, validated_target_id = validation_result
            if not is_valid:
                logger.error(f"❌ 频道验证失败详情:")
                logger.error(f"   源频道: {source_chat_id} -> {validated_source_id}")
                logger.error(f"   目标频道: {target_chat_id} -> {validated_target_id}")
                logger.error(f"   验证结果: {is_valid}")
                raise ValueError(f"频道验证失败: 源频道={source_chat_id}, 目标频道={target_chat_id}")
            logger.info(f"✅ 频道验证成功: {source_chat_id} -> {target_chat_id}")
            logger.info(f"✅ 使用验证后的频道ID: {validated_source_id} -> {validated_target_id}")
            
            # 使用验证成功的频道ID创建任务
            user_id = config.get('user_id') if config else None
            task = CloneTask(task_id, validated_source_id, validated_target_id, start_id, end_id, config, user_id)
            
            # 设置频道名称
            task.source_channel_name = source_username or validated_source_id
            task.target_channel_name = target_username or validated_target_id
            
            # 添加超时保护的消息计数，增加重试机制
            logger.debug(f"📊 开始计算消息数量: {validated_source_id}")
            
            # 检查是否跳过消息数量计算（多任务优化）
            if config and config.get('skip_message_count', False):
                logger.info(f"🚀 跳过消息数量计算，使用快速估算: {start_id}-{end_id}")
                # 修复类型错误：当start_id或end_id为None时提供默认值
                estimated_start = start_id if start_id is not None else 1
                estimated_end = end_id if end_id is not None else 1000
                task.total_messages = int((estimated_end - estimated_start + 1) * 0.8)  # 快速估算
            else:
                retry_count = 0
                max_retries = 3
                while retry_count < max_retries:
                    try:
                        task.total_messages = await asyncio.wait_for(
                            self._count_messages(validated_source_id, start_id, end_id),
                            timeout=120.0  # 增加到120秒超时
                        )
                        break
                    except asyncio.TimeoutError:
                        retry_count += 1
                        if retry_count < max_retries:
                            wait_time = retry_count * 2  # 递增延迟
                            logger.warning(f"⚠️ 消息计数超时，{wait_time}秒后重试 ({retry_count}/{max_retries})")
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"❌ 消息计数失败，已达到最大重试次数")
                            task.total_messages = 1000  # 使用默认值
                    except Exception as e:
                        logger.error(f"❌ 消息计数异常: {e}")
                        task.total_messages = 1000  # 使用默认值
                        break
            task.stats['total_messages'] = task.total_messages
            logger.info(f"✅ 消息计数完成: {task.total_messages} 条")
            
        except asyncio.TimeoutError:
            logger.error(f"❌ 任务创建超时: {task_id}")
            raise ValueError("任务创建超时，请检查网络连接或频道权限")
        except Exception as e:
            logger.error(f"❌ 任务创建失败: {task_id}, 错误: {e}")
            raise
        
        logger.info(f"🎉 创建搬运任务成功: {task_id}, 总消息数: {task.total_messages}")
        return task
    
    async def create_batch_tasks(self, tasks_config: List[Dict[str, Any]]) -> List[CloneTask]:
        """批量创建多个搬运任务（优化版）"""
        created_tasks = []
        
        logger.info(f"🚀 开始批量创建 {len(tasks_config)} 个任务")
        
        for i, task_config in enumerate(tasks_config):
            try:
                # 检查并发限制
                if len(self.active_tasks) >= self.max_concurrent_tasks:
                    logger.warning(f"达到最大并发任务数限制: {self.max_concurrent_tasks}")
                    break
                
                # 为多任务优化：跳过消息数量计算，使用快速估算
                task_config['skip_message_count'] = True  # 标记跳过消息数量计算
                
                # 创建单个任务
                task = await self.create_task(
                    source_chat_id=task_config['source_chat_id'],
                    target_chat_id=task_config['target_chat_id'],
                    start_id=task_config.get('start_id'),
                    end_id=task_config.get('end_id'),
                    config=task_config.get('config', {})
                )
                
                if task:
                    created_tasks.append(task)
                    logger.info(f"✅ 批量任务 {i+1}/{len(tasks_config)} 创建成功: {task.task_id}")
                else:
                    logger.error(f"❌ 批量任务 {i+1}/{len(tasks_config)} 创建失败")
                    
                # 添加小延迟避免API限制
                if i < len(tasks_config) - 1:
                    await asyncio.sleep(0.5)  # 减少延迟，提高速度
                    
            except Exception as e:
                logger.error(f"❌ 批量任务 {i+1}/{len(tasks_config)} 创建异常: {e}")
                continue
        
        logger.info(f"🎉 批量创建任务完成: {len(created_tasks)}/{len(tasks_config)} 成功")
        return created_tasks
    
    async def _validate_channels(self, source_chat_id: str, target_chat_id: str, 
                                source_username: str = "", target_username: str = "") -> tuple[bool, str, str]:
        """验证频道是否有效，优先使用用户名验证
        返回: (验证结果, 实际源频道ID, 实际目标频道ID)
        """
        try:
            # 处理PENDING格式的频道ID
            actual_source_id = self._resolve_pending_channel_id(source_chat_id)
            actual_target_id = self._resolve_pending_channel_id(target_chat_id)
            
            # 用于存储验证成功的实际频道ID
            validated_source_id = actual_source_id
            validated_target_id = actual_target_id
            
            # 检查源频道 - 优先使用用户名
            source_chat = None
            if source_username:
                try:
                    logger.info(f"优先通过用户名访问源频道: @{source_username}")
                    source_chat = await self.client.get_chat(source_username)
                    # 检查source_chat是否为ChatPreview类型，如果是则无法获取id
                    if source_chat and not isinstance(source_chat, ChatPreview) and hasattr(source_chat, 'id') and source_chat.id is not None:
                        validated_source_id = str(source_chat.id)
                        logger.info(f"通过用户名访问源频道成功: @{source_username} -> {validated_source_id} ({source_chat.type})")
                    elif isinstance(source_chat, ChatPreview):
                        # ChatPreview类型没有id属性，需要特殊处理
                        logger.warning(f"通过用户名访问源频道返回预览类型，无法获取完整信息: @{source_username}")
                        source_chat = None
                except Exception as username_error:
                    logger.warning(f"通过用户名访问源频道失败 @{source_username}: {username_error}")
                    source_chat = None
            
            # 如果用户名验证失败，再尝试ID验证
            if not source_chat:
                try:
                    logger.info(f"尝试通过ID访问源频道: {actual_source_id}")
                    # 如果是私密频道格式，尝试多种前缀
                    if actual_source_id.startswith('@c/') or actual_source_id.startswith('-100'):
                        source_chat = await self._try_private_channel_access(actual_source_id)
                        if source_chat and not isinstance(source_chat, ChatPreview) and hasattr(source_chat, 'id') and source_chat.id is not None:
                            validated_source_id = str(source_chat.id)
                            logger.info(f"私密源频道验证成功: {actual_source_id} -> {validated_source_id} ({source_chat.type})")
                        elif isinstance(source_chat, ChatPreview):
                            logger.warning(f"通过ID访问私密源频道返回预览类型，无法获取完整信息: {actual_source_id}")
                            source_chat = None
                    else:
                        source_chat = await self.client.get_chat(actual_source_id)
                        # 检查source_chat是否为ChatPreview类型
                        if source_chat and not isinstance(source_chat, ChatPreview) and hasattr(source_chat, 'id') and source_chat.id is not None:
                            validated_source_id = str(source_chat.id)
                        elif isinstance(source_chat, ChatPreview):
                            logger.warning(f"通过ID访问源频道返回预览类型，无法获取完整信息: {actual_source_id}")
                            source_chat = None
                except Exception as e:
                    logger.error(f"通过ID访问源频道失败 {actual_source_id}: {e}")
                
                if not source_chat:
                    logger.error(f"源频道验证失败: {actual_source_id}")
                    return False, actual_source_id, actual_target_id
            
            # 再次检查source_chat是否有效
            if source_chat and not isinstance(source_chat, ChatPreview) and hasattr(source_chat, 'id') and source_chat.id is not None:
                logger.info(f"源频道验证成功: {actual_source_id} ({source_chat.type})")
            else:
                logger.error(f"源频道验证失败: 无法获取频道完整信息")
                return False, actual_source_id, actual_target_id
            
            # 检查目标频道 - 优先使用用户名
            target_chat = None
            if target_username:
                try:
                    logger.info(f"优先通过用户名访问目标频道: @{target_username}")
                    target_chat = await self.client.get_chat(target_username)
                    # 检查target_chat是否为ChatPreview类型
                    if target_chat and not isinstance(target_chat, ChatPreview) and hasattr(target_chat, 'id') and target_chat.id is not None:
                        validated_target_id = str(target_chat.id)
                        logger.info(f"通过用户名访问目标频道成功: @{target_username} -> {validated_target_id} ({target_chat.type})")
                    elif isinstance(target_chat, ChatPreview):
                        # ChatPreview类型没有id属性
                        logger.warning(f"通过用户名访问目标频道返回预览类型，无法获取完整信息: @{target_username}")
                        target_chat = None
                except Exception as username_error:
                    logger.warning(f"通过用户名访问目标频道失败 @{target_username}: {username_error}")
                    target_chat = None
            
            # 如果用户名验证失败，再尝试ID验证
            if not target_chat:
                try:
                    logger.info(f"尝试通过ID访问目标频道: {actual_target_id}")
                    # 如果是私密频道格式，尝试多种前缀
                    if actual_target_id.startswith('@c/') or actual_target_id.startswith('-100'):
                        target_chat = await self._try_private_channel_access(actual_target_id)
                        if target_chat and not isinstance(target_chat, ChatPreview) and hasattr(target_chat, 'id') and target_chat.id is not None:
                            validated_target_id = str(target_chat.id)
                            logger.info(f"私密目标频道验证成功: {actual_target_id} -> {validated_target_id} ({target_chat.type})")
                        elif isinstance(target_chat, ChatPreview):
                            logger.warning(f"通过ID访问私密目标频道返回预览类型，无法获取完整信息: {actual_target_id}")
                            target_chat = None
                    else:
                        target_chat = await self.client.get_chat(actual_target_id)
                        if target_chat and not isinstance(target_chat, ChatPreview) and hasattr(target_chat, 'id') and target_chat.id is not None:
                            validated_target_id = str(target_chat.id)
                        elif isinstance(target_chat, ChatPreview):
                            logger.warning(f"通过ID访问目标频道返回预览类型，无法获取完整信息: {actual_target_id}")
                            target_chat = None
                except Exception as e:
                    logger.error(f"通过ID访问目标频道失败 {actual_target_id}: {e}")
                
                if not target_chat:
                    logger.error(f"目标频道验证失败: {actual_target_id}")
                    return False, actual_source_id, actual_target_id
            
            if target_chat and not isinstance(target_chat, ChatPreview) and hasattr(target_chat, 'id') and target_chat.id is not None:
                logger.info(f"目标频道验证成功: {actual_target_id} ({target_chat.type})")
            else:
                logger.error(f"目标频道验证失败: 无法获取频道信息")
                return False, actual_source_id, actual_target_id
            
            return True, validated_source_id, validated_target_id
            
        except Exception as e:
            logger.error(f"频道验证过程中发生异常: {e}")
            import traceback
            logger.debug(f"详细错误信息:\n{traceback.format_exc()}")
            return False, actual_source_id, actual_target_id
    
    def _resolve_pending_channel_id(self, channel_id) -> str:
        """解析PENDING格式的频道ID，转换为实际可用的频道ID"""
        # 确保channel_id是字符串
        channel_id_str = str(channel_id)
        if not channel_id_str.startswith('PENDING_'):
            return channel_id_str
        
        # 移除PENDING_前缀
        pending_part = channel_id.replace('PENDING_', '')
        logger.info(f"处理PENDING频道ID: {channel_id} -> {pending_part}")
        
        # 处理 @c/数字 格式（私密频道链接格式）
        if pending_part.startswith('@c/'):
            try:
                # 提取数字部分
                channel_num = pending_part.replace('@c/', '')
                if channel_num.isdigit():
                    # 私密频道ID可能需要不同的前缀，返回原始格式让验证逻辑处理
                    # 这样可以在验证时尝试多种前缀格式
                    logger.info(f"私密频道ID保持原格式用于多前缀尝试: {pending_part}")
                    return pending_part  # 返回 @c/数字 格式，让验证逻辑尝试多种前缀
                else:
                    logger.warning(f"私密频道ID格式错误: {pending_part}")
                    return pending_part
            except Exception as e:
                logger.error(f"解析私密频道ID失败: {e}")
                return pending_part
        
        # 处理 @用户名 格式
        elif pending_part.startswith('@'):
            logger.info(f"用户名格式频道: {pending_part}")
            return pending_part
        
        # 处理纯数字格式
        elif pending_part.isdigit():
            # 尝试添加-100前缀
            resolved_id = f"-100{pending_part}"
            logger.info(f"数字ID转换: {pending_part} -> {resolved_id}")
            return resolved_id
        
        # 其他格式直接返回
        else:
            logger.info(f"保持原格式: {pending_part}")
            return pending_part
    
    async def _try_private_channel_access(self, channel_id: str):
        """尝试多种前缀格式访问私密频道"""
        # 首先尝试直接访问原始ID
        try:
            logger.info(f"尝试直接访问频道: {channel_id}")
            chat = await self.client.get_chat(channel_id)
            if chat:
                logger.info(f"频道直接访问成功: {channel_id} ({chat.type})")
                return chat
        except Exception as e:
            logger.debug(f"频道直接访问失败: {e}")
        
        # 如果直接访问失败，尝试不同的格式
        channel_num = None
        
        if channel_id.startswith('@c/'):
            # @c/1234567890 格式
            channel_num = channel_id.replace('@c/', '')
        elif channel_id.startswith('-100'):
            # -1001234567890 格式，提取数字部分
            channel_num = channel_id[4:]  # 移除-100前缀
        elif channel_id.startswith('-'):
            # 其他负数格式，提取数字部分
            channel_num = channel_id[1:]
        else:
            # 纯数字格式
            channel_num = channel_id
        
        if not channel_num or not channel_num.isdigit():
            logger.warning(f"私密频道ID格式错误: {channel_id}")
            return None
        
        # 尝试不同的前缀格式
        prefixes = ['-100', '-1001', '']
        
        for prefix in prefixes:
            try:
                if prefix:
                    test_id = int(f"{prefix}{channel_num}")
                else:
                    test_id = int(channel_num)
                
                logger.info(f"尝试访问私密频道: {test_id}")
                chat = await self.client.get_chat(test_id)
                if chat:
                    logger.info(f"私密频道访问成功: {channel_id} -> {test_id} ({chat.type})")
                    return chat
            except Exception as e:
                logger.debug(f"私密频道ID {test_id} 访问失败: {e}")
                continue
        
        logger.error(f"所有前缀格式都无法访问私密频道: {channel_id}")
        return None
    
    async def _check_permissions(self, source_chat_id: str, target_chat_id: str) -> bool:
        """检查频道权限"""
        try:
            # 检查是否有读取源频道的权限
            try:
                source_chat = await self.client.get_chat(source_chat_id)
                if source_chat.type in ['private', 'bot']:
                    # 私聊和机器人聊天不需要特殊权限
                    logger.info(f"源频道类型: {source_chat.type}, 跳过权限检查")
                elif source_chat.type in ['channel', 'supergroup']:
                    # 对于频道和超级群组，尝试获取成员信息
                    try:
                        member = await self.client.get_chat_member(source_chat_id, "me")
                        # 根据Pyrogram文档，检查用户状态而不是直接检查can_read_messages
                        # restricted状态表示用户受到某些限制
                        if hasattr(member, 'status') and str(member.status) in ['restricted']:
                            # 在受限状态下，我们尝试获取消息来验证访问权限
                            logger.warning(f"账号在源频道中受限: {source_chat_id}, 将通过实际访问测试权限")
                        # 对于公开频道，即使没有读取权限也可能可以访问
                    except Exception as e:
                        logger.warning(f"无法获取源频道成员信息: {e}, 但尝试继续")
                        # 对于公开频道，即使无法获取成员信息也可能可以访问
                else:
                    logger.warning(f"未知的源频道类型: {source_chat.type}")
            except Exception as e:
                logger.warning(f"无法获取源频道信息: {e}, 但尝试继续")
                # 对于某些频道，即使无法获取信息也可能可以访问
            
            # 检查是否有发送到目标频道的权限
            try:
                target_chat = await self.client.get_chat(target_chat_id)
                if target_chat.type in ['private', 'bot']:
                    # 私聊和机器人聊天不需要特殊权限
                    logger.info(f"目标频道类型: {target_chat.type}, 跳过权限检查")
                elif target_chat.type in ['channel', 'supergroup']:
                    # 对于频道和超级群组，尝试获取成员信息
                    try:
                        member = await self.client.get_chat_member(target_chat_id, "me")
                        # 检查是否是受限用户且没有发送消息权限
                        if hasattr(member, 'status') and str(member.status) == 'restricted':
                            # Pyrogram的ChatMemberRestricted类有can_post_messages属性
                            if hasattr(member, 'can_post_messages') and not member.can_post_messages:
                                logger.error(f"没有向目标频道发送消息的权限: {target_chat_id}")
                                return False
                        # 检查是否是管理员或创建者（有权限）
                        elif hasattr(member, 'status') and str(member.status) in ['administrator', 'creator']:
                            pass  # 管理员或创建者有权限
                        # 其他情况（普通成员）可能没有权限
                        elif hasattr(member, 'status') and str(member.status) == 'member':
                            logger.warning(f"作为普通成员可能没有向频道发送消息的权限: {target_chat_id}")
                    except Exception as e:
                        logger.warning(f"无法获取目标频道成员信息: {e}")
                        # 无法确定权限，继续尝试
                else:
                    logger.warning(f"未知的目标频道类型: {target_chat.type}")
            except Exception as e:
                logger.warning(f"无法获取目标频道信息: {e}")
                # 无法确定权限，继续尝试
            
            return True
            
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            return False
    

    async def _count_actual_messages_in_range(self, chat_id: str, start_id: int, end_id: int) -> int:
        """计算指定范围内实际存在的消息数量"""
        logger.info(f"📊 开始计算实际消息数量: {start_id} - {end_id}")
        
        # 如果范围太大，直接使用范围估算（避免API调用延迟）
        total_range = end_id - start_id + 1
        if total_range > 200:  # 超过200条直接使用范围估算
            logger.info(f"📊 范围较大({total_range}条)，使用范围估算方法（避免API延迟）")
            # 直接返回范围大小，假设大部分消息都存在
            estimated_count = int(total_range * 0.8)  # 假设80%的消息存在
            logger.info(f"📊 范围估算消息数量: {estimated_count} 条")
            return estimated_count
        
        # 小范围使用精确计算
        actual_count = 0
        batch_size = 500  # 减小批次大小
        current_id = start_id
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                logger.debug(f"📊 检查批次: {current_id} - {batch_end} ({len(message_ids)} 个ID)")
                
                # 添加超时控制
                messages = await asyncio.wait_for(
                    self.client.get_messages(chat_id, message_ids=message_ids),
                    timeout=30.0  # 30秒超时
                )
                
                # 计算有效消息数量
                valid_count = sum(1 for msg in messages if msg is not None)
                actual_count += valid_count
                
                logger.debug(f"📊 批次 {current_id}-{batch_end}: 发现 {valid_count} 条消息")
                
                current_id = batch_end + 1
                
                # 添加延迟避免API限制
                await asyncio.sleep(0.1)
                
            except asyncio.TimeoutError:
                logger.warning(f"📊 批次超时 {current_id}-{batch_end}，跳过")
                current_id += batch_size
                continue
            except Exception as e:
                logger.warning(f"📊 计算批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"📊 实际消息数量计算完成: {actual_count} 条")
        return actual_count
    
    async def _count_messages(self, chat_id: str, start_id: Optional[int] = None, 
                             end_id: Optional[int] = None) -> int:
        """计算消息数量"""
        try:
            if start_id is not None and end_id is not None:
                # 如果提供了起始和结束ID，计算确切的数量
                return end_id - start_id + 1
            else:
                # 如果没有提供ID范围，估算消息数量
                retry_count = 0
                max_retries = 3
                batch_size = 100
                try:
                    recent_messages = await asyncio.wait_for(
                        self.client.get_messages(chat_id, 500),
                        timeout=30.0  # 30秒超时
                    )
                    if recent_messages:
                        # 根据最近消息的ID范围估算
                        latest_id = max(msg.id for msg in recent_messages if msg and msg.id)
                        oldest_id = min(msg.id for msg in recent_messages if msg and msg.id)
                        estimated_count = latest_id - oldest_id + 1
                        # 限制在合理范围内
                        return min(max(estimated_count, 100), 10000)
                    else:
                        # 如果无法获取消息，使用默认值
                        return 1000
                except asyncio.TimeoutError:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = retry_count * 2
                        logger.warning(f"⚠️ 获取消息超时，{wait_time}秒后重试 ({retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ 获取消息失败，已达到最大重试次数")
                        return 1000
                except Exception as e:
                    logger.error(f"❌ 获取消息异常: {e}")
                    return 1000
        except Exception as e:
            logger.error(f"消息计数失败: {e}")
            return 1000  # 默认值
    
    async def start_cloning(self, task: CloneTask) -> bool:
        """开始搬运任务"""
        logger.info(f"🔧 [DEBUG] 进入start_cloning方法: {task.task_id}")
        logger.info(f"🔧 [DEBUG] 检查任务状态: {task.status}")
        if task.status != "pending":
            logger.warning(f"任务状态不正确: {task.status}")
            return False
        logger.info(f"🔧 [DEBUG] 任务状态检查通过: {task.status}")
        
        # 检查总并发任务数限制
        logger.info(f"🔧 [DEBUG] 检查总并发任务数: {len(self.active_tasks)}/{self.max_concurrent_tasks}")
        if len(self.active_tasks) >= self.max_concurrent_tasks:
            logger.warning(f"达到最大并发任务数限制: {self.max_concurrent_tasks}")
            return False
        
        # 检查用户并发任务数限制（支持动态配置）
        user_id = task.config.get('user_id') if task.config else None
        logger.info(f"🔧 [DEBUG] 获取用户ID: {user_id}")
        if user_id:
            # 从用户配置读取并发限制，默认20个
            logger.info(f"🔧 [DEBUG] 开始获取用户配置: {user_id}")
            try:
                if self.data_manager:
                    user_config = await self.data_manager.get_user_config(user_id)
                else:
                    user_config = await get_user_config(user_id)
                max_user_concurrent = user_config.get('max_user_concurrent_tasks', 50)
                logger.info(f"🔧 [DEBUG] 用户配置获取成功，最大并发数: {max_user_concurrent}")
            except Exception as e:
                max_user_concurrent = 50  # 默认支持50个并发任务
                logger.info(f"🔧 [DEBUG] 用户配置获取失败，使用默认值: {max_user_concurrent}, 错误: {e}")
            
            user_active_tasks = [t for t in self.active_tasks.values() if t.config.get('user_id') == user_id]
            logger.info(f"🔧 [DEBUG] 用户当前活动任务数: {len(user_active_tasks)}/{max_user_concurrent}")
            if len(user_active_tasks) >= max_user_concurrent:
                logger.warning(f"用户 {user_id} 已达到最大并发任务数限制: {max_user_concurrent}")
                return False
        
        try:
            # 创建任务状态记录
            user_id = task.config.get('user_id') if task.config else None
            if user_id:
                await self.task_state_manager.create_task(
                    task_id=task.task_id,
                    user_id=user_id,
                    source_chat_id=task.source_chat_id,
                    target_chat_id=task.target_chat_id,
                    start_id=task.start_id,
                    end_id=task.end_id,
                    config=task.config
                )
                logger.info(f"✅ 任务状态记录已创建: {task.task_id} (用户: {user_id})")
            else:
                logger.warning(f"⚠️ 任务缺少user_id，跳过状态记录创建: {task.task_id}")
            
            # 将任务添加到活动任务列表
            logger.info(f"🔧 [DEBUG] 添加任务到活动列表: {task.task_id}")
            self.active_tasks[task.task_id] = task
            
            logger.info(f"🔧 [DEBUG] 设置任务状态为running: {task.task_id}")
            task.status = "running"
            task.start_time = datetime.now()
            
            # 更新任务状态到数据库
            if task.user_id:
                await self.task_state_manager.update_task_progress(
                    task.task_id,
                    status=TaskStatus.RUNNING,
                    start_time=task.start_time
                )
            
            logger.info(f"🔧 [DEBUG] 开始搬运任务: {task.task_id}")
            
            # 异步启动搬运任务，不等待完成
            logger.info(f"🔧 [DEBUG] 创建后台执行任务: {task.task_id}")
            background_task = asyncio.create_task(self._execute_cloning_background(task))
            self.background_tasks[task.task_id] = background_task  # 保存后台任务引用
            logger.info(f"🔧 [DEBUG] 后台任务已创建: {task.task_id}, task_obj={background_task}")
            
            logger.info(f"🔧 [DEBUG] 搬运任务启动完成: {task.task_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动搬运任务失败: {e}")
            task.status = "failed"
            task.end_time = datetime.now()
            
            # 如果启动失败，从活动任务中移除
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]
            
            return False
    
    async def start_batch_cloning(self, tasks: List[CloneTask]) -> Dict[str, bool]:
        """批量启动多个搬运任务（优化版）"""
        results = {}
        
        logger.info(f"🚀 开始批量启动 {len(tasks)} 个任务")
        
        # 使用并发启动，但限制并发数量
        max_concurrent_start = min(5, len(tasks))  # 最多同时启动5个任务
        semaphore = asyncio.Semaphore(max_concurrent_start)
        
        async def start_single_task(task, index):
            async with semaphore:
                try:
                    logger.info(f"🚀 启动批量任务 {index+1}/{len(tasks)}: {task.task_id}")
                    success = await self.start_cloning(task)
                    results[task.task_id] = success
                    
                    if success:
                        logger.info(f"✅ 批量任务 {index+1}/{len(tasks)} 启动成功")
                    else:
                        logger.error(f"❌ 批量任务 {index+1}/{len(tasks)} 启动失败")
                    
                    return success
                    
                except Exception as e:
                    logger.error(f"❌ 批量任务 {index+1}/{len(tasks)} 启动异常: {e}")
                    results[task.task_id] = False
                    return False
        
        # 并发启动所有任务
        start_tasks = [start_single_task(task, i) for i, task in enumerate(tasks)]
        await asyncio.gather(*start_tasks, return_exceptions=True)
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"🎉 批量启动完成: {success_count}/{len(tasks)} 成功")
        return results
    
    async def _execute_cloning_background(self, task: CloneTask):
        """后台执行搬运任务"""
        try:
            logger.info(f"🔧 [DEBUG] 进入后台执行方法: {task.task_id}")
            logger.info(f"🚀 开始后台执行搬运任务: {task.task_id}")
            
            # 执行搬运，添加超时保护
            logger.info(f"🔧 [DEBUG] 准备调用_execute_cloning: {task.task_id}")
            try:
                timeout_value = task.config.get('task_timeout', 86400)
                logger.info(f"🔧 [DEBUG] 设置超时时间: {timeout_value}秒, 任务: {task.task_id}")
                success = await asyncio.wait_for(
                    self._execute_cloning(task), 
                    timeout=timeout_value  # 默认24小时超时
                )
                logger.info(f"🔧 [DEBUG] _execute_cloning完成，结果: {success}, 任务: {task.task_id}")
            except asyncio.TimeoutError:
                logger.error(f"❌ 任务执行超时（{task.config.get('task_timeout', 86400)}秒），停止处理")
                success = False
            
            if success:
                task.status = "completed"
                task.progress = 100.0
                task.processed_messages = task.stats['processed_messages']
                logger.info(f"✅ 搬运任务完成: {task.task_id}")
            else:
                # 检查任务是否是因为暂停而停止
                if task.status == "paused":
                    logger.info(f"⏸️ 搬运任务已暂停: {task.task_id}")
                else:
                    task.status = "failed"
                    logger.error(f"❌ 搬运任务失败: {task.task_id}")
            
            task.end_time = datetime.now()
            
            # 保存最终状态到数据库
            await task.save_final_state()
            
            # 保存到历史记录
            self.task_history.append(task.to_dict())
            
            # 保存到数据库
            try:
                user_id = task.config.get('user_id') if task.config else None
                if user_id:
                    await data_manager.add_task_record(user_id, task.to_dict())
                    logger.info(f"任务记录已保存到数据库: {task.task_id}")
                else:
                    logger.warning(f"无法保存任务记录到数据库，缺少用户ID: {task.task_id}")
            except Exception as e:
                logger.error(f"保存任务记录到数据库失败: {e}")
            
            # 从活动任务中移除（暂停的任务不移除）
            if task.task_id in self.active_tasks and task.status != "paused":
                del self.active_tasks[task.task_id]
            
            # 清理后台任务引用
            if task.task_id in self.background_tasks:
                del self.background_tasks[task.task_id]
            
            logger.info(f"搬运任务结束: {task.task_id}, 状态: {task.status}")
            
        except Exception as e:
            logger.error(f"后台执行搬运任务失败: {e}")
            task.status = "failed"
            task.end_time = datetime.now()
            
            # 保存最终状态到数据库
            await task.save_final_state()
            
            # 清理后台任务引用
            if task.task_id in self.background_tasks:
                del self.background_tasks[task.task_id]
    
    async def _execute_cloning(self, task: CloneTask) -> bool:
        """执行搬运逻辑（改为流式处理，支持断点续传）"""
        try:
            logger.info(f"🔧 [DEBUG] 进入_execute_cloning方法: {task.task_id}")
            logger.info(f"🔧 使用客户端类型: {self.client_type}")
            # 添加超时保护
            task_start_time = time.time()
            logger.info(f"🔧 [DEBUG] 记录任务开始时间: {task_start_time}, 任务: {task.task_id}")
            # 保持start_time为datetime类型，用于UI显示
            if not task.start_time:
                task.start_time = datetime.now()
                logger.info(f"🔧 [DEBUG] 设置任务开始时间: {task.start_time}, 任务: {task.task_id}")
            # 从配置中获取超时时间，如果没有配置则使用默认值
            max_execution_time = task.config.get('task_timeout', 86400)  # 默认24小时
            logger.info(f"🔧 [DEBUG] 设置最大执行时间: {max_execution_time}秒, 任务: {task.task_id}")
            
            # 检查是否为断点续传
            if task.is_resumed and task.resume_from_id:
                logger.info(f"🔄 断点续传任务，从消息ID {task.resume_from_id} 开始")
                # 调整起始ID为断点续传位置
                actual_start_id = task.resume_from_id
            else:
                logger.info(f"🚀 开始新的流式搬运任务")
                actual_start_id = task.start_id
            logger.info(f"🔧 [DEBUG] 实际起始ID: {actual_start_id}, 任务: {task.task_id}")
            
            # 获取第一批消息（100条），添加超时保护
            logger.info(f"🔧 [DEBUG] 准备获取第一批消息，任务: {task.task_id}")
            try:
                logger.info(f"🔧 [DEBUG] 调用_get_first_batch，参数: source_chat_id={task.source_chat_id}, start_id={actual_start_id}, end_id={task.end_id}, 任务: {task.task_id}")
                first_batch = await asyncio.wait_for(
                    self._get_first_batch(task.source_chat_id, actual_start_id, task.end_id),
                    timeout=180.0  # 增加到180秒超时
                )
                logger.info(f"🔧 [DEBUG] _get_first_batch完成，获得{len(first_batch) if first_batch else 0}条消息，任务: {task.task_id}")
            except asyncio.TimeoutError:
                logger.error(f"获取第一批消息超时（180秒），任务: {task.task_id}")
                return False
            
            if not first_batch:
                logger.info("没有找到需要搬运的消息")
                return True
            
            # 计算总消息数 - 修复版本
            if actual_start_id and task.end_id:
                # 如果是断点续传，保持原始总消息数，只计算剩余消息数用于显示
                if task.is_resumed:
                    # 断点续传：保持原始总消息数，计算剩余消息数
                    remaining_total = await self._count_actual_messages_in_range(
                        task.source_chat_id, actual_start_id, task.end_id
                    )
                    # 不修改total_messages，保持原始值
                    logger.info(f"📊 断点续传剩余消息数: {remaining_total} (范围: {actual_start_id}-{task.end_id})")
                    logger.info(f"📊 原始总消息数: {task.total_messages}")
                else:
                    # 新任务：计算实际存在的消息数量
                    actual_total = await self._count_actual_messages_in_range(
                        task.source_chat_id, actual_start_id, task.end_id
                    )
                    task.total_messages = actual_total
                    logger.info(f"📊 实际总消息数: {actual_total} (范围: {actual_start_id}-{task.end_id})")
            else:
                task.total_messages = len(first_batch)
            
            logger.debug(f"📊 第一批获取完成，共 {len(first_batch)} 条消息，预计总消息数: {task.total_messages}")
            logger.info(f"🚀 立即开始搬运第一批消息")
            
            # 立即开始搬运第一批
            success = await self._process_message_batch(task, first_batch, task_start_time)
            if not success:
                if task.should_stop():
                    logger.info(f"任务 {task.task_id} 已被{task.status}")
                    return False
                logger.error("第一批消息搬运失败")
                return False
            
            # 流式处理剩余消息（边获取边搬运）
            if actual_start_id and task.end_id:
                success = await self._process_remaining_messages_streaming(task, first_batch, actual_start_id, task.end_id, task_start_time)
                if not success:
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 已被{task.status}")
                        return False
                    logger.error("剩余消息搬运失败")
                    return False
            
            logger.info(f"🎉 搬运任务完成")
            return True
            
        except Exception as e:
            logger.error(f"执行搬运失败: {e}")
            return False
    
    async def _process_remaining_messages_streaming(self, task: CloneTask, first_batch: List[Message], 
                                                   actual_start_id: int, end_id: int, task_start_time: float) -> bool:
        """流式处理剩余消息（边获取边搬运，支持预取优化）"""
        try:
            if not first_batch:
                return True
            
            # 计算剩余范围
            first_batch_end = max(msg.id for msg in first_batch if hasattr(msg, 'id') and msg.id is not None)
            remaining_start = first_batch_end + 1
            
            if remaining_start > end_id:
                logger.info("没有剩余消息需要搬运")
                logger.info(f"✅ 任务 {task.task_id} 已完成所有消息处理")
                return True
            
            logger.info(f"🔄 开始流式处理剩余消息: {remaining_start} - {end_id}")
            
            # 流式处理：边获取边搬运，支持预取和动态批次调整 - 修复版本
            batch_size = 200  # 修复: 减少批次大小避免跳过消息
            min_batch_size = 100  # 修复: 减少最小批次大小
            max_batch_size = 500  # 修复: 减少最大批次大小
            current_id = remaining_start
            
            # 预取缓存设置
            prefetch_size = 2000  # 预取2000条消息
            cache_size = 5000  # 缓存5000条消息
            prefetch_tasks = []  # 预取任务列表
            processed_batches = 0
            next_batch_task = None  # 预取任务
            batch_times = []  # 记录批次处理时间用于动态调整
            
            while current_id <= end_id:
                try:
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 在流式处理中被{task.status}")
                        # 取消预取任务
                        if next_batch_task and not next_batch_task.done():
                            next_batch_task.cancel()
                        return False
                    
                    # 计算本次批次的结束ID
                    batch_end = min(current_id + batch_size - 1, end_id)
                    
                    # 如果有预取任务，等待其完成
                    if next_batch_task:
                        try:
                            batch_messages = await next_batch_task
                            logger.info(f"📦 使用预取批次 {processed_batches + 1}: {current_id} - {batch_end}")
                        except Exception as e:
                            logger.warning(f"预取失败，重新获取: {e}")
                            batch_messages = await self.client.get_messages(
                                task.source_chat_id, 
                                message_ids=list(range(current_id, batch_end + 1))
                            )
                    else:
                        logger.info(f"📦 获取批次 {processed_batches + 1}: {current_id} - {batch_end}")
                        batch_messages = await self.client.get_messages(
                            task.source_chat_id, 
                            message_ids=list(range(current_id, batch_end + 1))
                        )
                    
                    # 过滤掉None值
                    valid_messages = [msg for msg in batch_messages if msg is not None]
                    
                    if not valid_messages:
                        # 检查是否真的没有消息，还是批次太大导致跳过
                        if batch_end - current_id + 1 > 100:  # 如果批次很大
                            logger.warning(f"⚠️ 大批次 {current_id}-{batch_end} 没有有效消息，可能跳过消息")
                            # 分成更小的批次重新检查
                            sub_batch_size = 50
                            sub_current = current_id
                            found_any = False
                            
                            while sub_current <= batch_end:
                                sub_end = min(sub_current + sub_batch_size - 1, batch_end)
                                sub_message_ids = list(range(sub_current, sub_end + 1))
                                
                                try:
                                    sub_messages = await self.client.get_messages(
                                        task.source_chat_id,
                                        message_ids=sub_message_ids
                                    )
                                    sub_valid = [msg for msg in sub_messages if msg is not None]
                                    
                                    if sub_valid:
                                        found_any = True
                                        logger.info(f"🔍 子批次 {sub_current}-{sub_end} 发现 {len(sub_valid)} 条消息")
                                        # 处理这批消息
                                        success = await self._process_message_batch(task, sub_valid, task_start_time)
                                        if not success:
                                            logger.warning(f"子批次 {sub_current}-{sub_end} 处理失败")
                                    
                                    await asyncio.sleep(0.01)  # 小延迟
                                    
                                except Exception as e:
                                    logger.warning(f"子批次 {sub_current}-{sub_end} 检查失败: {e}")
                                
                                sub_current = sub_end + 1
                            
                            if not found_any:
                                logger.info(f"✅ 确认批次 {current_id}-{batch_end} 没有有效消息")
                        else:
                            logger.info(f"批次 {current_id}-{batch_end} 没有有效消息，跳过")
                        
                        current_id = batch_end + 1
                        continue
                    
                    # 检查媒体组完整性
                    last_message = valid_messages[-1]
                    first_message = valid_messages[0]
                    
                    # 检查是否需要扩展媒体组
                    need_extension = False
                    extended_batch_end = batch_end
                    
                    # 如果最后一个消息是媒体组，需要向后扩展
                    if last_message.media_group_id:
                        extended_batch_end = await self._extend_batch_to_complete_media_group(
                            task.source_chat_id, batch_end, end_id
                        )
                        if extended_batch_end > batch_end:
                            need_extension = True
                    
                    # 如果第一个消息是媒体组，需要向前扩展
                    if first_message.media_group_id:
                        extended_batch_start = await self._extend_batch_to_complete_media_group(
                            task.source_chat_id, current_id, end_id
                        )
                        if extended_batch_start < current_id:
                            # 需要获取前面的消息
                            extended_messages = await self.client.get_messages(
                                task.source_chat_id,
                                message_ids=list(range(extended_batch_start, current_id))
                            )
                            extended_valid = [msg for msg in extended_messages if msg is not None]
                            valid_messages = extended_valid + valid_messages
                            current_id = extended_batch_start
                            need_extension = True
                    
                    if need_extension:
                        if extended_batch_end > batch_end:
                            extended_messages = await self.client.get_messages(
                                task.source_chat_id,
                                message_ids=list(range(batch_end + 1, extended_batch_end + 1))
                            )
                            extended_valid = [msg for msg in extended_messages if msg is not None]
                            valid_messages.extend(extended_valid)
                            batch_end = extended_batch_end
                        logger.info(f"📦 媒体组扩展批次: {current_id} - {batch_end}, 消息数: {len(valid_messages)}")
                    else:
                        logger.info(f"📦 标准批次: {current_id} - {batch_end}, 消息数: {len(valid_messages)}")
                    
                    # 立即搬运这批消息
                    # 启动预取下一批次（在处理当前批次之前）
                    next_current_id = batch_end + 1
                    if next_current_id <= end_id:
                        next_batch_end = min(next_current_id + batch_size - 1, end_id)
                        next_batch_task = asyncio.create_task(
                            self.client.get_messages(
                                task.source_chat_id,
                                message_ids=list(range(next_current_id, next_batch_end + 1))
                            )
                        )
                    else:
                        next_batch_task = None
                    
                    logger.info(f"🚀 并发处理批次 {processed_batches + 1}（同时预取下一批次，批次大小: {len(valid_messages)}）")
                    
                    # 记录批次开始时间
                    batch_start_time = time.time()
                    
                    # 并发执行：处理当前批次 + 预取下一批次
                    success = await self._process_message_batch(task, valid_messages, task_start_time)
                    
                    # 记录批次处理时间
                    batch_duration = time.time() - batch_start_time
                    batch_times.append(batch_duration)
                    
                    # 动态调整批次大小（每5个批次调整一次）
                    if len(batch_times) >= 5:
                        avg_time = sum(batch_times[-5:]) / 5
                        if avg_time < 2.0:  # 处理速度快，增加批次大小
                            batch_size = min(batch_size + 100, max_batch_size)
                            logger.info(f"📈 批次处理快速（{avg_time:.1f}s），增加批次大小到 {batch_size}")
                        elif avg_time > 5.0:  # 处理速度慢，减少批次大小
                            batch_size = max(batch_size - 100, min_batch_size)
                            logger.info(f"📉 批次处理缓慢（{avg_time:.1f}s），减少批次大小到 {batch_size}")
                        # 保留最近5次记录
                        batch_times = batch_times[-5:]
                    
                    if not success:
                        if task.should_stop():
                            logger.info(f"任务 {task.task_id} 在批次处理中被{task.status}")
                            # 取消预取任务
                            if next_batch_task and not next_batch_task.done():
                                next_batch_task.cancel()
                            return False
                        logger.error(f"批次 {current_id}-{batch_end} 搬运失败")
                        # 继续处理下一批次，不中断整个任务
                    
                    processed_batches += 1
                    current_id = batch_end + 1
                    
                    # 优化延迟设置，减少等待时间
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    logger.warning(f"批次 {current_id}-{batch_end} 处理失败: {e}")
                    # 不要跳过整个批次大小，只跳过当前批次
                    current_id = batch_end + 1
                    continue
            
            logger.info(f"🎉 流式处理完成，共处理 {processed_batches} 个批次")
            
            # 检查是否真的完成了所有消息
            if current_id > end_id:
                logger.info(f"✅ 任务 {task.task_id} 已完成所有消息处理 (current_id: {current_id}, end_id: {end_id})")
                return True
            else:
                logger.warning(f"⚠️ 任务 {task.task_id} 可能未完成所有消息 (current_id: {current_id}, end_id: {end_id})")
                return True  # 仍然返回True，因为可能没有更多消息
            
        except Exception as e:
            logger.error(f"流式处理剩余消息失败: {e}")
            # 取消预取任务
            if 'next_batch_task' in locals() and next_batch_task and not next_batch_task.done():
                next_batch_task.cancel()
            return False
    
    async def _get_messages(self, chat_id: str, start_id: Optional[int] = None, 
                           end_id: Optional[int] = None) -> List[Message]:
        """获取消息列表"""
        try:
            messages = []
            
            # 优化：使用媒体组感知的批量获取
            if start_id and end_id:
                # 指定范围的消息，使用智能批量获取
                batch_size = 500  # 目标批次大小
                current_id = start_id
                
                logger.info(f"开始智能批量获取消息，范围: {start_id} - {end_id}")
                
                while current_id <= end_id:
                    try:
                        # 计算本次批次的结束ID
                        batch_end = min(current_id + batch_size - 1, end_id)
                        
                        # 获取当前批次的消息
                        message_ids = list(range(current_id, batch_end + 1))
                        logger.info(f"🔍 尝试获取消息ID: {message_ids[:10]}{'...' if len(message_ids) > 10 else ''}")
                        
                        batch_messages = await self.client.get_messages(
                            chat_id, 
                            message_ids=message_ids
                        )
                        
                        logger.info(f"🔍 get_messages返回结果: {type(batch_messages)}, 长度: {len(batch_messages) if batch_messages else 'None'}")
                        if batch_messages:
                            logger.info(f"🔍 前5个消息类型: {[type(msg).__name__ if msg else 'None' for msg in batch_messages[:5]]}")
                            logger.info(f"🔍 None值数量: {sum(1 for msg in batch_messages if msg is None)}")
                        
                        # 过滤掉None值（不存在的消息）
                        valid_messages = [msg for msg in batch_messages if msg is not None]
                        logger.info(f"🔍 有效消息数量: {len(valid_messages)}")
                        
                        if not valid_messages:
                            current_id = batch_end + 1
                            continue
                        
                        # 检查最后一个消息是否属于媒体组
                        last_message = valid_messages[-1]
                        if last_message.media_group_id:
                            # 如果最后一条消息属于媒体组，需要扩展批次到媒体组结束
                            extended_batch_end = await self._extend_batch_to_complete_media_group(
                                chat_id, batch_end, end_id
                            )
                            
                            if extended_batch_end > batch_end:
                                # 获取扩展部分的消息
                                extended_messages = await self.client.get_messages(
                                    chat_id,
                                    message_ids=list(range(batch_end + 1, extended_batch_end + 1))
                                )
                                
                                # 过滤并添加到有效消息中
                                extended_valid = [msg for msg in extended_messages if msg is not None]
                                valid_messages.extend(extended_valid)
                                
                                logger.info(f"媒体组感知批次: {current_id}-{extended_batch_end}, 消息数: {len(valid_messages)}")
                                
                                # 更新批次结束位置
                                batch_end = extended_batch_end
                            else:
                                logger.info(f"标准批次: {current_id}-{batch_end}, 消息数: {len(valid_messages)}")
                        else:
                            logger.info(f"标准批次: {current_id}-{batch_end}, 消息数: {len(valid_messages)}")
                        
                        messages.extend(valid_messages)
                        current_id = batch_end + 1
                        
                        # 使用默认的消息延迟设置
                        message_delay = 0.05  # 默认延迟
                        await asyncio.sleep(message_delay)
                        
                    except Exception as e:
                        logger.warning(f"批次获取消息失败 {current_id}-{batch_end}: {e}")
                        current_id += batch_size
                        continue
                        
                    # 添加超时保护
                    if len(messages) > 10000:  # 限制最大消息数
                        logger.warning(f"消息数量过多，限制为10000条")
                        break
                        
            else:
                # 获取最近的消息
                try:
                    # 获取最近500条消息，使用位置参数（兼容不同版本的Pyrogram）
                    messages = await self.client.get_messages(chat_id, 500)
                    logger.info(f"获取最近500条消息成功")
                    
                    # 确保返回的是列表
                    if not isinstance(messages, list):
                        messages = [messages] if messages else []
                    
                    # 过滤掉None值
                    messages = [msg for msg in messages if msg is not None]
                    
                    # 显示消息ID范围
                    if messages:
                        try:
                            min_id = min(msg.id for msg in messages if hasattr(msg, 'id') and msg.id is not None)
                            max_id = max(msg.id for msg in messages if hasattr(msg, 'id') and msg.id is not None)
                            logger.debug(f"📊 消息ID范围: {min_id} - {max_id}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"无法获取消息ID范围: {e}")
                        
                        # 显示前几条消息的类型
                        for i, msg in enumerate(messages[:3]):
                            try:
                                msg_type = "媒体" if msg.media else "文本"
                                has_text = bool(msg.text and msg.text.strip())
                                has_caption = bool(msg.caption and msg.caption.strip())
                                logger.info(f"📝 消息 {msg.id}: 类型={msg_type}, 有文本={has_text}, 有caption={has_caption}")
                            except Exception as e:
                                logger.warning(f"分析消息 {i+1} 失败: {e}")
                    
                except Exception as e:
                    logger.error(f"获取最近消息失败: {e}")
                    return []
            
            # 按消息ID排序，确保搬运顺序正确
            if messages:
                try:
                    messages.sort(key=lambda msg: msg.id if msg and hasattr(msg, 'id') and msg.id is not None else 0)
                    logger.info(f"✅ 消息已按ID排序，范围: {messages[0].id} - {messages[-1].id}")
                except Exception as e:
                    logger.warning(f"消息排序失败: {e}")
            
            logger.info(f"消息获取完成，总数: {len(messages)}")
            return messages
            
        except Exception as e:
            logger.error(f"获取消息列表失败: {e}")
            return []
    
    async def _extend_batch_to_complete_media_group(self, chat_id: str, current_end: int, max_end: int) -> int:
        """扩展批次到媒体组完整结束"""
        try:
            # 获取当前消息的媒体组ID
            current_message = await self.client.get_messages(chat_id, current_end)
            if not current_message or not current_message.media_group_id:
                return current_end
            
            media_group_id = current_message.media_group_id
            extended_end = current_end
            
            # 向前查找媒体组的开始
            start_search = max(current_end - 50, 1)  # 向前最多搜索50条
            for msg_id in range(current_end - 1, start_search - 1, -1):
                try:
                    msg = await self.client.get_messages(chat_id, msg_id)
                    if msg and msg.media_group_id == media_group_id:
                        # 找到媒体组开始，更新批次开始位置
                        start_search = msg_id
                    else:
                        break
                except:
                    break
            
            # 向后查找媒体组的结束
            end_search = min(current_end + 50, max_end)  # 向后最多搜索50条
            for msg_id in range(current_end + 1, end_search + 1):
                try:
                    msg = await self.client.get_messages(chat_id, msg_id)
                    if msg and msg.media_group_id == media_group_id:
                        # 找到媒体组结束，更新批次结束位置
                        extended_end = msg_id
                    else:
                        break
                except:
                    break
            
            if extended_end > current_end:
                logger.info(f"媒体组 {media_group_id} 扩展批次: {current_end} -> {extended_end}")
            
            return extended_end
            
        except Exception as e:
            logger.warning(f"扩展媒体组批次失败: {e}")
            return current_end
    
    # 已删除 _process_batch 方法，逻辑整合到 _execute_cloning 中
    
    async def _process_media_group(self, task: CloneTask, messages: List[Message]) -> bool:
        """处理媒体组消息"""
        try:
            if not messages:
                return False
            
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止处理媒体组")
                return False
            
            # 检查任务是否超时（防止无限期卡住）
            if hasattr(task, 'start_time') and task.start_time:
                elapsed_time = (datetime.now() - task.start_time).total_seconds()
                max_task_time = task.config.get('max_task_time', DEFAULT_USER_CONFIG.get('max_task_time', 172800))  # 从配置读取，默认48小时
                if elapsed_time > max_task_time:
                    logger.warning(f"⚠️ 任务 {task.task_id} 运行时间过长 ({elapsed_time:.1f}秒 > {max_task_time}秒)，停止处理")
                    task.status = "timeout"
                    return False
            
            # 获取频道组配置
            user_id = task.config.get('user_id')
            pair_id = task.config.get('pair_id')
            pair_index = task.config.get('pair_index', 'unknown')  # 保留用于日志显示，添加默认值
            
            if user_id and pair_id:
                # 获取频道组有效配置
                effective_config = await self.get_effective_config_for_pair(user_id, pair_id)
                logger.debug(f"媒体组使用频道组 {pair_id} (索引{pair_index}) 的过滤配置")
            else:
                # 使用任务配置或默认配置
                effective_config = task.config if task.config else self.config
                logger.debug("媒体组使用任务配置或默认过滤配置")
            
            # 使用消息引擎处理媒体组，传递频道组配置
            processed_result, should_process = self.message_engine.process_media_group(messages, effective_config)
            
            if not should_process:
                logger.info(f"媒体组被过滤: {messages[0].media_group_id}")
                return False  # 被过滤的媒体组应该返回False，表示未成功处理
            
            if not processed_result:
                logger.warning(f"媒体组处理结果为空: {messages[0].media_group_id}")
                return False
            
            # 检查处理结果是否有效
            if isinstance(processed_result, dict):
                has_content = (
                    processed_result.get('caption', '').strip() or 
                    processed_result.get('media_count', 0) > 0
                )
                if not has_content:
                    logger.warning(f"媒体组处理结果无有效内容: {messages[0].media_group_id}")
                    return False
            
            # 发送媒体组
            sent_messages = await self._send_media_group(task, messages, processed_result)
            
            if sent_messages:
                logger.debug(f"媒体组发送成功: {messages[0].media_group_id}")
                
                # 如果开启了评论区搬运，搬运评论区
                clone_comments_enabled = effective_config.get('clone_comments', False)
                if clone_comments_enabled:
                    # 获取源媒体组的第一条消息作为源消息
                    source_message = messages[0]
                    # 获取目标媒体组的第一条消息作为目标消息
                    target_message = sent_messages[0] if sent_messages else None
                    
                    if target_message:
                        logger.info(f"💬 [评论区] 准备搬运媒体组 {messages[0].media_group_id} 的评论区")
                        logger.debug(f"🔧 [评论区] 源消息ID: {source_message.id}, 目标消息ID: {target_message.id}")
                        try:
                            await self._clone_message_comments(
                                task,
                                source_message,  # 源消息（媒体组的第一条消息）
                                target_message,  # 目标消息（发送的媒体组的第一条消息）
                                effective_config
                            )
                        except Exception as e:
                            logger.warning(f"💬 [评论区] 搬运媒体组评论区失败: {e}")
                            # 评论搬运失败不影响主消息搬运的成功状态
                    else:
                        logger.warning(f"💬 [评论区] 无法获取目标消息，跳过评论区搬运")
                else:
                    logger.debug(f"💬 [评论区] 媒体组 {messages[0].media_group_id} 评论区搬运未启用，跳过")
            else:
                logger.error(f"媒体组发送失败: {messages[0].media_group_id}")
            
            return sent_messages is not None
            
        except Exception as e:
            logger.error(f"处理媒体组失败: {e}")
            return False
    
    async def _process_single_message(self, task: CloneTask, message: Message) -> bool:
        """处理单条消息"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止处理单条消息")
                return False
            
            # 安全访问消息属性，防止UTF-16编码错误
            try:
                message_id = message.id
            except UnicodeDecodeError as e:
                logger.warning(f"消息ID访问失败，使用默认值: {e}")
                message_id = "unknown"
            except Exception as e:
                logger.warning(f"消息属性访问失败: {e}")
                message_id = "unknown"
            
            # 获取频道组配置
            user_id = task.config.get('user_id')
            pair_id = task.config.get('pair_id')
            pair_index = task.config.get('pair_index', 'unknown')  # 保留用于日志显示，添加默认值
            
            if user_id and pair_id:
                # 获取频道组有效配置
                effective_config = await self.get_effective_config_for_pair(user_id, pair_id)
                logger.debug(f"使用频道组 {pair_id} (索引{pair_index}) 的过滤配置")
            else:
                # 使用任务配置或默认配置
                effective_config = task.config if task.config else self.config
                logger.debug("使用任务配置或默认过滤配置")
            
            # 使用消息引擎处理，传递频道组配置
            processed_result, should_process = self.message_engine.process_message(message, effective_config)
            
            if not should_process:
                task.stats['filtered_messages'] += 1
                logger.info(f"消息被过滤: {message_id}")
                return True  # 被过滤的消息返回True，表示成功跳过
            
            if not processed_result:
                logger.warning(f"消息处理结果为空: {message_id}")
                # 如果消息被完全过滤，标记为已处理但跳过
                task.stats['filtered_messages'] += 1
                logger.info(f"消息内容被完全过滤，跳过: {message_id}")
                return True  # 被过滤的消息返回True，表示成功跳过
            
            # 检查处理结果是否有效
            if isinstance(processed_result, dict):
                # 对于媒体消息，即使文本为空也应该被认为是有效内容
                # 检查原始消息的媒体属性（更全面的检查）
                has_media_content = (
                    message.photo or message.video or message.document or 
                    message.audio or message.voice or message.sticker or 
                    message.animation or message.video_note or message.media
                )
                
                has_content = (
                    processed_result.get('text', '').strip() or 
                    processed_result.get('caption', '').strip() or 
                    processed_result.get('media', False) or
                    processed_result.get('photo') or
                    processed_result.get('video') or
                    processed_result.get('document') or
                    has_media_content  # 使用更全面的媒体检查
                )
                
                if not has_content:
                    logger.warning(f"消息处理结果无有效内容: {message_id}")
                    logger.debug(f"  • 文本: '{processed_result.get('text', '')}'")
                    logger.debug(f"  • 标题: '{processed_result.get('caption', '')}'")
                    logger.debug(f"  • 媒体: {processed_result.get('media', False)}")
                    logger.debug(f"  • 原始消息媒体: photo={bool(message.photo)}, video={bool(message.video)}, document={bool(message.document)}")
                    logger.debug(f"  • 原始消息media属性: {message.media}")
                    task.stats['filtered_messages'] += 1
                    logger.info(f"消息内容被完全过滤，跳过: {message_id}")
                    return True  # 被过滤的消息返回True，表示成功跳过
            
            # 发送处理后的消息
            sent_message = await self._send_processed_message(task, message, processed_result)
            
            # 调试：输出评论区搬运配置
            clone_comments_enabled = effective_config.get('clone_comments', False)
            logger.debug(f"🔧 [评论区] 消息 {message_id} 发送结果: {'成功' if sent_message else '失败'}, clone_comments={clone_comments_enabled}")
            
            # 如果消息发送成功且开启了评论区搬运，搬运评论区
            if sent_message and clone_comments_enabled:
                logger.info(f"💬 [评论区] 准备搬运消息 {message_id} 的评论区")
                try:
                    await self._clone_message_comments(
                        task, 
                        message,  # 源消息
                        sent_message,  # 目标消息
                        effective_config
                    )
                except Exception as e:
                    logger.warning(f"搬运评论区失败: {e}")
                    # 评论搬运失败不影响主消息搬运的成功状态
            elif sent_message and not clone_comments_enabled:
                logger.debug(f"💬 [评论区] 消息 {message_id} 评论区搬运未启用，跳过")
            
            success = sent_message is not None
            if success:
                logger.debug(f"消息发送成功: {message_id}")
            else:
                logger.error(f"消息发送失败: {message_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"处理单条消息失败: {e}")
            return False
    
    def _initialize_ai_rewriter(self):
        """初始化AI改写器"""
        try:
            if not self.data_manager:
                logger.warning("数据管理器未初始化，无法初始化AI改写器")
                return
            
            # 获取用户配置
            user_config = self.data_manager.get_user_config(self.user_id)
            
            # 检查是否启用AI改写
            if not user_config.get('ai_rewrite_enabled', False):
                self.ai_rewriter = None
                return
            
            # 获取AI配置
            ai_config = self.data_manager.get_ai_rewrite_config(self.user_id)
            
            # 创建获取当前API密钥的回调函数
            def get_current_api_key():
                try:
                    # 获取用户配置中的AI改写配置
                    ai_config = self.data_manager.get_ai_rewrite_config(self.user_id) if self.data_manager else {}
                    api_keys = ai_config.get('api_keys', [])
                    if not api_keys:
                        return ""
                    current_index = ai_config.get('current_key_index', 0)
                    current_index = current_index % len(api_keys)
                    return api_keys[current_index]
                except Exception as e:
                    logger.error(f"获取当前API密钥失败: {e}")
                    return ""
            
            # 初始化AI改写器
            from ai_text_rewriter import AITextRewriter
            self.ai_rewriter = AITextRewriter(user_config, get_current_api_key)
            
            if self.ai_rewriter.model:
                logger.info("✅ AI改写器初始化成功")
            else:
                logger.warning("⚠️ AI改写器初始化失败")
                self.ai_rewriter = None
                
        except Exception as e:
            logger.error(f"初始化AI改写器失败: {e}")
            self.ai_rewriter = None
    
    async def _send_processed_message(self, task: CloneTask, original_message: Message, 
                                    processed_result: Dict[str, Any]) -> Optional[Message]:
        """发送处理后的消息，返回发送的消息对象"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送处理后的消息")
                return None
            
            # 安全访问消息ID，防止UTF-16编码错误
            try:
                message_id = original_message.id
            except UnicodeDecodeError as e:
                logger.warning(f"消息ID访问失败，使用默认值: {e}")
                message_id = "unknown"
            except Exception as e:
                logger.warning(f"消息属性访问失败: {e}")
                message_id = "unknown"
            
            # 更准确地判断消息类型（考虑群组中的转发限制）
            has_media = (
                original_message.photo or original_message.video or original_message.document or 
                original_message.audio or original_message.voice or original_message.sticker or 
                original_message.animation or original_message.video_note or original_message.media
            )
            message_type = "媒体消息" if has_media else "文本消息"
            
            logger.info(f"📤 发送 {message_type} {message_id}")
            logger.debug(f"  • 媒体检查: photo={bool(original_message.photo)}, video={bool(original_message.video)}, document={bool(original_message.document)}")
            logger.debug(f"  • media属性: {original_message.media}")
            
            # 重试机制
            for attempt in range(self.retry_attempts):
                try:
                    if has_media:
                        # 媒体消息
                        sent_msg = await self._send_media_message(task, original_message, processed_result)
                    else:
                        # 文本消息
                        sent_msg = await self._send_text_message(task, processed_result)
                    
                    if sent_msg:
                        logger.info(f"✅ {message_type} {message_id} 发送成功")
                        # 标记消息为已处理（成功发送后）
                        task.mark_message_processed(message_id)
                        return sent_msg  # 返回发送的消息对象
                    
                except Exception as e:
                    logger.warning(f"⚠️ 发送 {message_type} {message_id} 失败 (尝试 {attempt + 1}/{self.retry_attempts}): {e}")
                    
                    if attempt < self.retry_attempts - 1:
                        logger.debug(f"⏳ 等待 {self.retry_delay} 秒后重试...")
                        await asyncio.sleep(self.retry_delay)
            
            logger.error(f"❌ {message_type} {message_id} 发送失败，已达到最大重试次数")
            return None
            
        except Exception as e:
            logger.error(f"❌ 发送处理后的消息失败: {e}")
            return None  # 修复：返回 None 而不是 False
    
    async def _send_text_message(self, task: CloneTask, processed_result: Dict[str, Any]) -> Optional[Message]:
        """发送文本消息，返回发送的消息对象"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送文本消息")
                return None
            
            text = processed_result.get('text', '')
            buttons = processed_result.get('buttons')
            
            if not text and not buttons:
                logger.debug("📝 跳过空文本消息")
                return None  # 空消息，跳过
            
            # 显示文本内容摘要
            text_preview = text[:50] + "..." if len(text) > 50 else text
            logger.debug(f"📝 发送文本: {text_preview}")
            
            sent_message = await self.client.send_message(
                chat_id=task.target_chat_id,
                text=text or " ",  # 空文本用空格代替
                reply_markup=buttons
            )
            
            return sent_message
            
        except Exception as e:
            logger.error(f"❌ 发送文本消息失败: {e}")
            return None
    
    async def _send_media_group(self, task: CloneTask, messages: List[Message], 
                               processed_result: Dict[str, Any]) -> Optional[List[Message]]:
        """发送媒体组消息"""
        try:
            if not messages:
                return None
            
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体组")
                return None
            
            media_group_id = messages[0].media_group_id
            logger.info(f"📱 开始发送媒体组 {media_group_id} ({len(messages)} 条消息)")
            
            # 构建媒体组
            logger.debug(f"🔧 开始构建媒体组 {media_group_id}")
            logger.debug(f"🔍 媒体组构建详情:")
            logger.debug(f"  • 消息数量: {len(messages)}")
            logger.debug(f"  • 处理结果: {processed_result}")
            
            media_list = []
            caption = processed_result.get('caption', '')
            buttons = processed_result.get('buttons')
            
            logger.debug(f"🔍 媒体组内容:")
            logger.debug(f"  • Caption: '{caption[:50]}...' (长度: {len(caption)})")
            logger.debug(f"  • 按钮: {bool(buttons)}")
            
            # 统计媒体类型
            photo_count = 0
            video_count = 0
            document_count = 0
            
            for i, message in enumerate(messages):
                try:
                    # 安全访问消息ID
                    try:
                        msg_id = message.id
                    except UnicodeDecodeError:
                        msg_id = f"unknown_{i}"
                    except Exception:
                        msg_id = f"unknown_{i}"
                    
                    logger.debug(f"🔍 处理媒体组消息 {i+1}/{len(messages)}: ID={msg_id}")
                    logger.debug(f"  • 消息类型: photo={bool(message.photo)}, video={bool(message.video)}, document={bool(message.document)}")
                    
                    if message.photo:
                        # 图片
                        logger.debug(f"  • 处理照片: file_id={message.photo.file_id}")
                        media_item = InputMediaPhoto(
                            media=message.photo.file_id,
                            caption=caption if i == 0 else None  # 只在第一个媒体上添加caption
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        logger.debug(f"   📷 添加照片 {i+1}/{len(messages)}")
                        
                    elif message.video:
                        # 视频
                        logger.debug(f"  • 处理视频: file_id={message.video.file_id}")
                        media_item = InputMediaVideo(
                            media=message.video.file_id,
                            caption=caption if i == 0 else None  # 只在第一个媒体上添加caption
                        )
                        media_list.append(media_item)
                        video_count += 1
                        logger.debug(f"   🎥 添加视频 {i+1}/{len(messages)}")
                        
                    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
                        # 文档视频
                        logger.debug(f"  • 处理文档视频: file_id={message.document.file_id}, mime_type={message.document.mime_type}")
                        media_item = InputMediaVideo(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        video_count += 1
                        logger.debug(f"   📄🎥 添加文档视频 {i+1}/{len(messages)}")
                        
                    elif message.document and message.document.mime_type and 'image' in message.document.mime_type:
                        # 文档图片
                        logger.debug(f"  • 处理文档图片: file_id={message.document.file_id}, mime_type={message.document.mime_type}")
                        media_item = InputMediaPhoto(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        logger.debug(f"   📄📷 添加文档图片 {i+1}/{len(messages)}")
                        
                    else:
                        logger.warning(f"   ⚠️ 消息 {msg_id} 不是媒体类型")
                        logger.debug(f"  • 详细信息: photo={message.photo}, video={message.video}, document={message.document}")
                        if message.document:
                            logger.debug(f"  • 文档MIME类型: {message.document.mime_type}")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ 处理媒体组消息失败 {msg_id}: {e}")
                    logger.debug(f"  • 错误类型: {type(e).__name__}")
                    logger.debug(f"  • 错误详情: {str(e)}")
                    continue
            
            if not media_list:
                logger.warning(f"❌ 媒体组 {media_group_id} 没有有效的媒体内容")
                return None
            
            # 媒体组完整性验证
            logger.info(f"🔍 媒体组完整性验证:")
            logger.info(f"  • 原始消息数: {len(messages)}")
            logger.info(f"  • 有效媒体数: {len(media_list)}")
            logger.info(f"  • 完整性: {len(media_list)}/{len(messages)} ({len(media_list)/len(messages)*100:.1f}%)")
            
            # 如果媒体组不完整，记录警告
            if len(media_list) < len(messages):
                missing_count = len(messages) - len(media_list)
                logger.warning(f"⚠️ 媒体组 {media_group_id} 不完整，丢失 {missing_count} 个媒体")
                logger.warning(f"⚠️ 建议检查源频道的媒体组是否完整")
            
            # 显示媒体组统计
            media_summary = []
            if photo_count > 0:
                media_summary.append(f"📷 {photo_count} 张")
            if video_count > 0:
                media_summary.append(f"🎥 {video_count} 个")
            if document_count > 0:
                media_summary.append(f"📄 {document_count} 个")
            
            logger.info(f"📱 媒体组 {media_group_id} 构建完成: {' + '.join(media_summary)}")
            
            # 发送媒体组（添加超时保护和重试机制）
            logger.info(f"📤 正在发送媒体组 {media_group_id}...")
            logger.debug(f"🔍 媒体组发送详情:")
            logger.debug(f"  • 目标频道ID: {task.target_chat_id}")
            logger.debug(f"  • 媒体数量: {len(media_list)}")
            logger.debug(f"  • 任务ID: {task.task_id}")
            logger.debug(f"  • 任务状态: {task.status}")
            logger.debug(f"  • 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # API限流检查
            if not await self._check_api_rate_limit():
                logger.warning(f"⚠️ API限流，跳过媒体组 {media_group_id}")
                return None
            
            # 重试机制
            max_retries = 3
            retry_delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    logger.debug(f"🔄 开始发送尝试 {attempt + 1}/{max_retries}")
                    logger.debug(f"🔍 发送前检查:")
                    logger.debug(f"  • 任务状态: {task.status}")
                    logger.debug(f"  • 是否应该停止: {task.should_stop()}")
                    logger.debug(f"  • 媒体列表长度: {len(media_list)}")
                    
                    # 检查任务状态
                    if task.should_stop():
                        logger.warning(f"⚠️ 任务 {task.task_id} 已被{task.status}，停止发送媒体组")
                        return False
                    
                    # 添加超时保护（30秒超时）
                    logger.debug(f"⏰ 开始发送媒体组，设置30秒超时...")
                    start_send_time = time.time()
                    
                    result = await asyncio.wait_for(
                        self.client.send_media_group(
                            chat_id=task.target_chat_id,
                            media=media_list
                        ),
                        timeout=30.0
                    )
                    
                    send_duration = time.time() - start_send_time
                    logger.info(f"✅ 媒体组 {media_group_id} 发送成功")
                    logger.debug(f"🔍 发送结果详情:")
                    logger.debug(f"  • 发送耗时: {send_duration:.2f}秒")
                    logger.debug(f"  • 返回结果类型: {type(result)}")
                    if hasattr(result, '__len__'):
                        logger.debug(f"  • 返回消息数量: {len(result)}")
                    # 保存发送结果以便返回
                    sent_messages = result
                    break
                    
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ 媒体组 {media_group_id} 发送超时 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        logger.error(f"❌ 媒体组 {media_group_id} 发送失败，已达到最大重试次数")
                        return None
                        
                except FloodWait as flood_error:
                    # 解析等待时间
                    wait_time = int(str(flood_error).split('A wait of ')[1].split(' seconds')[0])
                    logger.warning(f"⚠️ 遇到FloodWait限制，需要等待 {wait_time} 秒")
                    
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"⚠️ 任务 {task.task_id} 在FloodWait等待期间被{task.status}，停止处理")
                        return None
                    
                    # 如果等待时间过长（超过1小时），记录警告并考虑暂停任务
                    if wait_time > 3600:
                        logger.warning(f"⚠️ FloodWait等待时间过长: {wait_time}秒 ({wait_time/3600:.1f}小时)")
                        logger.warning(f"⚠️ 任务 {task.task_id} 可能需要很长时间才能继续")
                        
                        # 如果等待时间超过4小时，建议暂停任务
                        if wait_time > 14400:  # 4小时
                            logger.warning(f"⚠️ FloodWait等待时间过长（{wait_time/3600:.1f}小时），建议暂停任务")
                            logger.warning(f"⚠️ 任务 {task.task_id} 将在等待完成后继续，但可能需要很长时间")
                    
                    # 等待指定时间
                    logger.debug(f"⏳ 等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
                    
                    # 重试发送
                    logger.info(f"🔄 重试发送媒体组 {media_group_id}")
                    try:
                        retry_result = await self.client.send_media_group(
                            chat_id=task.target_chat_id,
                            media=media_list
                        )
                        logger.info(f"✅ 媒体组 {media_group_id} 重试发送成功")
                        # 保存发送结果以便返回
                        sent_messages = retry_result
                        break
                    except Exception as retry_error:
                        logger.error(f"❌ 重试发送失败: {retry_error}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return None
                            
                except Exception as send_error:
                    logger.error(f"❌ 发送媒体组 {media_group_id} 失败 (尝试 {attempt + 1}/{max_retries}): {send_error}")
                    if attempt < max_retries - 1:
                        logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error(f"❌ 媒体组 {media_group_id} 发送失败，已达到最大重试次数")
                        return None
            
            # 如果有按钮，单独发送
            if buttons:
                logger.debug(f"🔘 发送媒体组 {media_group_id} 的附加按钮")
                await self.client.send_message(
                    chat_id=task.target_chat_id,
                    text="📎 媒体组附加按钮",
                    reply_markup=buttons
                )
                logger.debug(f"✅ 媒体组 {media_group_id} 按钮发送成功")
            
            # 返回发送的消息列表（如果成功发送）
            if 'sent_messages' in locals() and sent_messages:
                return sent_messages
            else:
                logger.warning(f"⚠️ 媒体组 {media_group_id} 发送成功但未获取到返回消息")
                return None
            
        except Exception as e:
            logger.error(f"❌ 发送媒体组 {media_group_id} 失败: {e}")
            return None
    
    async def _send_media_message(self, task: CloneTask, original_message: Message, 
                                 processed_result: Dict[str, Any]) -> Optional[Message]:
        """发送媒体消息，返回发送的消息对象"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体消息")
                return None
            
            # 安全访问消息ID，防止UTF-16编码错误
            try:
                message_id = original_message.id
            except UnicodeDecodeError as e:
                logger.warning(f"消息ID访问失败，使用默认值: {e}")
                message_id = "unknown"
            except Exception as e:
                logger.warning(f"消息属性访问失败: {e}")
                message_id = "unknown"
            
            # 对于单条媒体消息，使用text字段（包含处理后的caption）
            caption = processed_result.get('text', '')
            buttons = processed_result.get('buttons')
            
            # 添加调试日志
            logger.debug(f"🔍 媒体消息发送: caption='{caption[:50]}...', buttons={bool(buttons)}")
            logger.debug(f"🔍 目标频道ID: {task.target_chat_id}")
            logger.debug(f"🔍 源消息ID: {message_id}")
            logger.debug(f"🔍 媒体类型: photo={bool(original_message.photo)}, video={bool(original_message.video)}, document={bool(original_message.document)}")
            
            # 确定媒体类型
            if original_message.photo:
                media_type = "📷 照片"
                logger.debug(f"   📷 发送照片 {message_id}")
            elif original_message.video:
                media_type = "🎥 视频"
                logger.debug(f"   🎥 发送视频 {message_id}")
            elif original_message.document:
                media_type = "📄 文档"
                logger.debug(f"   📄 发送文档 {message_id}")
            else:
                media_type = "📎 其他媒体"
                logger.debug(f"   📎 发送其他媒体 {message_id}")
            
            # 复制媒体文件（添加超时保护）
            try:
                # 重试机制
                max_retries = 3
                retry_delay = 2.0
                
                for attempt in range(max_retries):
                    try:
                        if original_message.photo:
                            logger.info(f"📷 尝试发送照片到 {task.target_chat_id} (尝试 {attempt + 1}/{max_retries})")
                            result = await asyncio.wait_for(
                                self.client.send_photo(
                                    chat_id=task.target_chat_id,
                                    photo=original_message.photo.file_id,
                                    caption=caption,
                                    reply_markup=buttons
                                ),
                                timeout=30.0
                            )
                            logger.info(f"✅ 照片发送成功，消息ID: {result.id}")
                            return result  # 返回 Message 对象
                            
                        elif original_message.video:
                            logger.info(f"🎥 尝试发送视频到 {task.target_chat_id} (尝试 {attempt + 1}/{max_retries})")
                            result = await asyncio.wait_for(
                                self.client.send_video(
                                    chat_id=task.target_chat_id,
                                    video=original_message.video.file_id,
                                    caption=caption,
                                    reply_markup=buttons
                                ),
                                timeout=30.0
                            )
                            logger.info(f"✅ 视频发送成功，消息ID: {result.id}")
                            return result  # 返回 Message 对象
                            
                        elif original_message.document:
                            logger.info(f"📄 尝试发送文档到 {task.target_chat_id} (尝试 {attempt + 1}/{max_retries})")
                            result = await asyncio.wait_for(
                                self.client.send_document(
                                    chat_id=task.target_chat_id,
                                    document=original_message.document.file_id,
                                    caption=caption,
                                    reply_markup=buttons
                                ),
                                timeout=30.0
                            )
                            logger.info(f"✅ 文档发送成功，消息ID: {result.id}")
                            return result  # 返回 Message 对象
                            
                        else:
                            # 其他类型的媒体，检查是否有可用的媒体
                            logger.info(f"📎 尝试发送其他媒体到 {task.target_chat_id} (尝试 {attempt + 1}/{max_retries})")
                            
                            # 检查是否有其他类型的媒体
                            if hasattr(original_message, 'media') and original_message.media:
                                # 如果有媒体但类型未知，尝试转发原消息
                                logger.info(f"📎 转发未知媒体类型消息 {message_id}")
                                result = await asyncio.wait_for(
                                    self.client.forward_messages(
                                        chat_id=task.target_chat_id,
                                        from_chat_id=original_message.chat.id,
                                        message_ids=message_id
                                    ),
                                    timeout=30.0
                                )
                                logger.info(f"✅ 媒体转发成功，消息ID: {result.id}")
                                return result  # 返回 Message 对象
                            else:
                                # 没有媒体，只发送文本
                                logger.info(f"📎 发送纯文本消息 {message_id}")
                                result = await asyncio.wait_for(
                                    self.client.send_message(
                                        chat_id=task.target_chat_id,
                                        text=caption,
                                        reply_markup=buttons
                                    ),
                                    timeout=30.0
                                )
                                logger.info(f"✅ 文本消息发送成功，消息ID: {result.id}")
                                return result  # 返回 Message 对象
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"⚠️ {media_type} {message_id} 发送超时 (尝试 {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error(f"❌ {media_type} {message_id} 发送失败，已达到最大重试次数")
                            return None
                            
                    except Exception as send_error:
                        logger.error(f"❌ 发送 {media_type} {message_id} 失败 (尝试 {attempt + 1}/{max_retries}): {send_error}")
                        if attempt < max_retries - 1:
                            logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error(f"❌ {media_type} {message_id} 发送失败，已达到最大重试次数")
                            return None
                
            except FloodWait as flood_error:
                # 解析等待时间
                wait_time = int(str(flood_error).split('A wait of ')[1].split(' seconds')[0])
                logger.warning(f"⚠️ 遇到FloodWait限制，需要等待 {wait_time} 秒")
                
                # 检查任务状态
                if task.should_stop():
                    logger.info(f"⚠️ 任务 {task.task_id} 在FloodWait等待期间被{task.status}，停止处理")
                    return None
                
                # 如果等待时间过长（超过1小时），记录警告并考虑暂停任务
                if wait_time > 3600:
                    logger.warning(f"⚠️ FloodWait等待时间过长: {wait_time}秒 ({wait_time/3600:.1f}小时)")
                    logger.warning(f"⚠️ 任务 {task.task_id} 可能需要很长时间才能继续")
                    
                    # 如果等待时间超过4小时，建议暂停任务
                    if wait_time > 14400:  # 4小时
                        logger.warning(f"⚠️ FloodWait等待时间过长（{wait_time/3600:.1f}小时），建议暂停任务")
                        logger.warning(f"⚠️ 任务 {task.task_id} 将在等待完成后继续，但可能需要很长时间")
                
                # 等待指定时间
                logger.debug(f"⏳ 等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
                
                # 重试发送
                logger.info(f"🔄 重试发送媒体消息到 {task.target_chat_id}")
                try:
                    if original_message.photo:
                        result = await self.client.send_photo(
                            chat_id=task.target_chat_id,
                            photo=original_message.photo.file_id,
                            caption=caption,
                            reply_markup=buttons
                        )
                    elif original_message.video:
                        result = await self.client.send_video(
                            chat_id=task.target_chat_id,
                            video=original_message.video.file_id,
                            caption=caption,
                            reply_markup=buttons
                        )
                    elif original_message.document:
                        result = await self.client.send_document(
                            chat_id=task.target_chat_id,
                            document=original_message.document.file_id,
                            caption=caption,
                            reply_markup=buttons
                        )
                    else:
                        result = await self.client.send_document(
                            chat_id=task.target_chat_id,
                            document=original_message.document.file_id if original_message.document else None,
                            caption=caption,
                            reply_markup=buttons
                        )
                    
                    logger.info(f"✅ 重试成功，消息ID: {result.id}")
                    return result  # 返回 Message 对象
                    
                except Exception as retry_error:
                    logger.error(f"❌ 重试发送失败: {retry_error}")
                    raise retry_error
                    
            except Exception as send_error:
                logger.error(f"❌ 发送媒体消息到 {task.target_chat_id} 失败: {send_error}")
                logger.error(f"❌ 错误类型: {type(send_error).__name__}")
                logger.error(f"❌ 错误详情: {str(send_error)}")
                raise send_error
            
        except Exception as e:
            logger.error(f"❌ 发送媒体消息失败: {e}")
            return None  # 返回 None 而不是 False
    
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        if task_id not in self.active_tasks:
            return False
        
        task = self.active_tasks[task_id]
        if task.status == "running":
            task.status = "paused"
            logger.info(f"任务已暂停: {task_id}")
            return True
        
        return False
    
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        if task_id not in self.active_tasks:
            return False
        
        task = self.active_tasks[task_id]
        if task.status == "paused":
            task.status = "running"
            logger.info(f"任务已恢复: {task_id}")
            
            # 设置断点续传参数，从最后处理的消息ID继续
            if task.last_processed_message_id:
                task.prepare_for_resume(task.last_processed_message_id)
                logger.info(f"🔄 设置断点续传，从消息ID {task.last_processed_message_id} 继续")
            
            # 重新启动任务的后台处理
            try:
                # 创建新的后台任务
                background_task = asyncio.create_task(self._execute_cloning_background(task))
                self.background_tasks[task_id] = background_task
                logger.info(f"✅ 任务后台处理已重新启动: {task_id}")
                return True
            except Exception as e:
                logger.error(f"❌ 重新启动任务后台处理失败: {e}")
                task.status = "failed"
                return False
        
        return False
    
    async def resume_task_from_checkpoint(self, task_id: str, from_message_id: int) -> bool:
        """从断点恢复任务"""
        try:
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
                if task.status in ["failed", "cancelled", "paused"]:
                    # 准备断点续传
                    task.prepare_for_resume(from_message_id)
                    logger.info(f"任务 {task_id} 准备从消息ID {from_message_id} 断点续传")
                    
                    # 重新启动任务
                    return await self.start_cloning(task)
                else:
                    logger.warning(f"任务 {task_id} 状态为 {task.status}，无法断点续传")
                    return False
            else:
                # 任务不在活动列表中，尝试从历史记录中恢复
                logger.info(f"任务 {task_id} 不在活动列表中，尝试从历史记录中恢复")
                
                # 从历史记录中查找任务
                for i, task_record in enumerate(self.task_history):
                    if task_record.get('task_id') == task_id:
                        if task_record.get('status') in ["failed", "cancelled", "paused"]:
                            # 从历史记录重新创建任务
                            task = CloneTask(
                                task_id=task_record['task_id'],
                                source_chat_id=task_record['source_chat_id'],
                                target_chat_id=task_record['target_chat_id'],
                                start_id=task_record.get('start_id'),
                                end_id=task_record.get('end_id'),
                                config=task_record.get('config', {}),
                                user_id=task_record.get('user_id')
                            )
                            
                            # 恢复任务状态
                            task.status = "pending"
                            task.progress = task_record.get('progress', 0.0)
                            task.processed_messages = task_record.get('processed_messages', 0)
                            task.total_messages = task_record.get('total_messages', 0)
                            task.failed_messages = task_record.get('failed_messages', 0)
                            task.last_processed_message_id = task_record.get('last_processed_message_id')
                            
                            # 恢复频道名称信息
                            if 'source_channel_name' in task_record:
                                task.source_channel_name = task_record['source_channel_name']
                            if 'target_channel_name' in task_record:
                                task.target_channel_name = task_record['target_channel_name']
                            
                            # 准备断点续传
                            task.prepare_for_resume(from_message_id)
                            logger.info(f"从历史记录恢复任务 {task_id}，准备从消息ID {from_message_id} 断点续传")
                            
                            # 添加到活动任务
                            self.active_tasks[task_id] = task
                            
                            # 重新启动任务
                            return await self.start_cloning(task)
                        else:
                            logger.warning(f"历史任务 {task_id} 状态为 {task_record.get('status')}，无法断点续传")
                            return False
                
                logger.warning(f"任务 {task_id} 不存在于活动任务或历史记录中")
                return False
        except Exception as e:
            logger.error(f"断点续传任务失败: {e}")
            return False
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.active_tasks:
            # 尝试从历史记录中查找
            for i, task_record in enumerate(self.task_history):
                if task_record.get('task_id') == task_id:
                    # 更新历史记录中的状态
                    self.task_history[i]['status'] = 'cancelled'
                    self.task_history[i]['end_time'] = datetime.now().isoformat()
                    logger.info(f"历史任务已标记为取消: {task_id}")
                    return True
            logger.warning(f"任务不存在: {task_id}")
            return False
        
        task = self.active_tasks[task_id]
        task.status = "cancelled"
        task._cancelled = True  # 设置取消标志
        task.end_time = datetime.now()
        
        logger.info(f"🛑 正在取消任务: {task_id}")
        logger.debug(f"📊 任务统计: 已处理 {task.processed_messages}/{task.total_messages} 条消息")
        
        # 取消后台任务
        if task_id in self.background_tasks:
            background_task = self.background_tasks[task_id]
            if not background_task.done():
                background_task.cancel()
                logger.info(f"🛑 已取消后台任务: {task_id}")
            del self.background_tasks[task_id]
        
        # 保存到历史记录
        self.task_history.append(task.to_dict())
        
        # 保存到数据库
        try:
            user_id = task.config.get('user_id') if task.config else None
            if user_id:
                await data_manager.add_task_record(user_id, task.to_dict())
                logger.info(f"取消任务记录已保存到数据库: {task_id}")
            else:
                logger.warning(f"无法保存取消任务记录到数据库，缺少用户ID: {task_id}")
        except Exception as e:
            logger.error(f"保存取消任务记录到数据库失败: {e}")
        
        # 从活动任务中移除
        del self.active_tasks[task_id]
        
        logger.info(f"✅ 任务已成功取消: {task_id}")
        return True
    
    async def stop_all_tasks(self):
        """停止所有活动任务"""
        logger.info(f"🛑 开始停止所有活动任务，共 {len(self.active_tasks)} 个")
        
        # 停止所有任务
        for task_id in list(self.active_tasks.keys()):
            await self.cancel_task(task_id)
        
        logger.info(f"✅ 所有任务已停止")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id in self.active_tasks:
            return self.active_tasks[task_id].to_dict()
        
        # 从历史记录中查找
        for task_record in self.task_history:
            if task_record['task_id'] == task_id:
                return task_record
        
        return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        active_tasks = [task.to_dict() for task in self.active_tasks.values()]
        return active_tasks + self.task_history
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息"""
        # 按用户分组统计
        user_task_stats = {}
        for task in self.active_tasks.values():
            user_id = task.config.get('user_id', 'unknown')
            if user_id not in user_task_stats:
                user_task_stats[user_id] = {'running': 0, 'paused': 0, 'total': 0}
            user_task_stats[user_id][task.status] += 1
            user_task_stats[user_id]['total'] += 1
        
        # 按频道组统计
        channel_stats = {}
        for task in self.active_tasks.values():
            source_channel = task.source_chat_id
            if source_channel not in channel_stats:
                channel_stats[source_channel] = {'tasks': 0, 'status': 'active'}
            channel_stats[source_channel]['tasks'] += 1
        
        return {
            'active_tasks_count': len(self.active_tasks),
            'completed_tasks_count': len([t for t in self.task_history if t['status'] == 'completed']),
            'failed_tasks_count': len([t for t in self.task_history if t['status'] == 'failed']),
            'total_tasks_count': len(self.active_tasks) + len(self.task_history),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'max_concurrent_channels': getattr(self, 'max_concurrent_channels', 5),
            'message_delay': self.message_delay,
            'batch_size': self.batch_size,
            'user_task_stats': user_task_stats,
            'channel_stats': channel_stats,
            'system_load': {
                'active_channels': len(set([t.source_chat_id for t in self.active_tasks.values()])),
                'total_channels': len(set([t.source_chat_id for t in self.active_tasks.values()] + [t.target_chat_id for t in self.active_tasks.values()]))
            }
        }
    
    async def check_stuck_tasks(self) -> List[str]:
        """检查卡住的任务并返回需要取消的任务ID列表"""
        stuck_tasks = []
        current_time = datetime.now()
        
        for task_id, task in self.active_tasks.items():
            try:
                # 检查任务是否运行时间过长
                if hasattr(task, 'start_time') and task.start_time:
                    elapsed_time = (current_time - task.start_time).total_seconds()
                    max_task_time = task.config.get('max_task_time', DEFAULT_USER_CONFIG.get('max_task_time', 172800))  # 从配置读取，默认48小时
                    
                    if elapsed_time > max_task_time:
                        logger.warning(f"⚠️ 发现卡住的任务: {task_id}, 运行时间: {elapsed_time:.1f}秒")
                        stuck_tasks.append(task_id)
                        continue
                
                # 检查任务是否长时间没有进度更新
                if hasattr(task, 'last_activity_time') and task.last_activity_time:
                    inactive_time = (current_time - task.last_activity_time).total_seconds()
                    max_inactive_time = 300  # 5分钟无活动
                    
                    if inactive_time > max_inactive_time:
                        logger.warning(f"⚠️ 发现无活动的任务: {task_id}, 无活动时间: {inactive_time:.1f}秒")
                        stuck_tasks.append(task_id)
                        continue
                        
            except Exception as e:
                logger.error(f"检查任务 {task_id} 状态失败: {e}")
                # 如果无法检查状态，也标记为卡住
                stuck_tasks.append(task_id)
        
        return stuck_tasks
    
    async def auto_cancel_stuck_tasks(self) -> int:
        """自动取消卡住的任务"""
        stuck_tasks = await self.check_stuck_tasks()
        cancelled_count = 0
        
        for task_id in stuck_tasks:
            try:
                logger.info(f"🛑 自动取消卡住的任务: {task_id}")
                success = await self.cancel_task(task_id)
                if success:
                    cancelled_count += 1
                    logger.info(f"✅ 成功取消卡住的任务: {task_id}")
                else:
                    logger.warning(f"⚠️ 取消卡住的任务失败: {task_id}")
            except Exception as e:
                logger.error(f"❌ 自动取消任务 {task_id} 失败: {e}")
        
        if cancelled_count > 0:
            logger.info(f"🔄 自动清理完成，取消了 {cancelled_count} 个卡住的任务")
        
        return cancelled_count

    async def _get_first_batch(self, chat_id: str, start_id: Optional[int], end_id: Optional[int]) -> List[Message]:
        """获取第一批消息（500条）"""
        try:
            if start_id and end_id:
                # 指定范围的消息，获取前500条
                batch_size = 500
                batch_end = min(start_id + batch_size - 1, end_id)
                
                logger.info(f"获取第一批消息: {start_id} - {batch_end}")
                
                # 添加超时保护，避免大范围消息ID查询卡住
                try:
                    messages = await asyncio.wait_for(
                        self.client.get_messages(
                            chat_id, 
                            message_ids=list(range(start_id, batch_end + 1))
                        ),
                        timeout=120.0  # 增加到120秒超时
                    )
                except asyncio.TimeoutError:
                    logger.error(f"获取消息超时（120秒），范围: {start_id} - {batch_end}")
                    return []
                
                # 过滤掉None值
                valid_messages = [msg for msg in messages if msg is not None]
                logger.info(f"第一批消息获取成功: {len(valid_messages)} 条")
                return valid_messages
            else:
                # 获取最近500条消息，添加超时保护
                try:
                    messages = await asyncio.wait_for(
                        self.client.get_messages(chat_id, 500),
                        timeout=120.0  # 增加到120秒超时
                    )
                except asyncio.TimeoutError:
                    logger.error(f"获取最近500条消息超时（120秒），频道: {chat_id}")
                    return []
                
                # 确保返回的是列表
                if not isinstance(messages, list):
                    messages = [messages] if messages else []
                
                # 过滤掉None值
                valid_messages = [msg for msg in messages if msg is not None]
                logger.info(f"最近500条消息获取成功: {len(valid_messages)} 条")
                return valid_messages
                
        except Exception as e:
            logger.error(f"获取第一批消息失败: {e}")
            return []

    async def _get_remaining_messages(self, chat_id: str, start_id: int, end_id: int, first_batch: List[Message]) -> List[Message]:
        """获取剩余消息"""
        try:
            if not first_batch:
                return []
            
            # 计算剩余范围
            first_batch_end = max(msg.id for msg in first_batch if hasattr(msg, 'id') and msg.id is not None)
            remaining_start = first_batch_end + 1
            
            if remaining_start > end_id:
                return []
            
            logger.info(f"获取剩余消息: {remaining_start} - {end_id}")
            
            # 使用原有的批量获取逻辑
            return await self._get_messages(chat_id, remaining_start, end_id)
            
        except Exception as e:
            logger.error(f"获取剩余消息失败: {e}")
            return []

    async def _process_message_batch(self, task: CloneTask, messages: List[Message], task_start_time: float) -> bool:
        """处理一批消息"""
        try:
            # 获取任务超时设置
            max_execution_time = task.config.get('task_timeout', 86400) if hasattr(task, 'config') and task.config else 86400
            
            logger.debug(f"🔍 开始处理消息批次:")
            logger.info(f"  • 任务ID: {task.task_id}")
            logger.info(f"  • 消息数量: {len(messages)}")
            logger.info(f"  • 任务状态: {task.status}")
            logger.info(f"  • 任务开始时间: {task.start_time}")
            logger.info(f"  • 最大执行时间: {max_execution_time}秒")
            
            if not messages:
                logger.info("📝 消息批次为空，跳过处理")
                return True
            
            # 重复检测和去重 - 修复版本
            logger.info(f"🔍 开始重复检测和去重...")
            unique_messages = []
            duplicate_count = 0
            
            for message in messages:
                # 安全访问消息ID
                try:
                    msg_id = message.id
                except UnicodeDecodeError:
                    msg_id = "unknown"
                except Exception:
                    msg_id = "unknown"
                
                if task.is_duplicate_message(msg_id):
                    duplicate_count += 1
                    logger.warning(f"🔄 跳过重复消息: {msg_id}")
                    continue
                unique_messages.append(message)
                # 注意：不在这里标记为已处理，应该在消息成功发送后才标记
            
            if duplicate_count > 0:
                logger.warning(f"🔄 批次中发现 {duplicate_count} 条重复消息，已跳过")
            
            logger.info(f"✅ 重复检测完成: 原始{len(messages)}条 -> 去重后{len(unique_messages)}条")
            
            # 按媒体组分组处理消息
            media_groups = {}
            standalone_messages = []
            
            logger.debug(f"🔍 开始分析消息类型...")
            for i, message in enumerate(unique_messages):
                try:
                    # 安全访问消息ID
                    try:
                        msg_id = message.id
                    except UnicodeDecodeError:
                        msg_id = f"unknown_{i}"
                    except Exception:
                        msg_id = f"unknown_{i}"
                    
                    logger.debug(f"🔍 分析消息 {i+1}/{len(unique_messages)}: ID={msg_id}")
                    logger.debug(f"  • 媒体组ID: {getattr(message, 'media_group_id', None)}")
                    logger.debug(f"  • 消息类型: photo={bool(message.photo)}, video={bool(message.video)}, document={bool(message.document)}")
                    logger.debug(f"  • 文本内容: {bool(message.text)}, caption: {bool(message.caption)}")
                    
                    if hasattr(message, 'media_group_id') and message.media_group_id:
                        if message.media_group_id not in media_groups:
                            media_groups[message.media_group_id] = []
                        media_groups[message.media_group_id].append(message)
                        logger.info(f"  • 添加到媒体组: {message.media_group_id}")
                    else:
                        standalone_messages.append(message)
                        logger.info(f"  • 添加为独立消息")
                except Exception as e:
                    logger.warning(f"分析消息失败: {e}")
                    logger.warning(f"  • 错误类型: {type(e).__name__}")
                    standalone_messages.append(message)
            
            logger.debug(f"📊 消息分析完成:")
            logger.info(f"  • 媒体组数量: {len(media_groups)}")
            logger.info(f"  • 独立消息数量: {len(standalone_messages)}")
            for media_group_id, group_messages in media_groups.items():
                logger.info(f"  • 媒体组 {media_group_id}: {len(group_messages)} 条消息")
            
            # 创建统一的处理队列，按消息ID排序以保持原始顺序
            processing_queue = []
            
            # 添加媒体组到队列（使用最小消息ID作为排序键）
            for media_group_id, group_messages in media_groups.items():
                min_id = min(msg.id for msg in group_messages if hasattr(msg, 'id') and msg.id is not None)
                processing_queue.append(('media_group', min_id, media_group_id, group_messages))
            
            # 添加独立消息到队列
            for message in standalone_messages:
                msg_id = message.id if hasattr(message, 'id') and message.id is not None else 0
                processing_queue.append(('single', msg_id, message, None))
            
            # 按消息ID排序队列
            processing_queue.sort(key=lambda x: x[1])
            
            logger.info(f"🔄 开始按顺序处理 {len(processing_queue)} 个项目（{len(media_groups)} 个媒体组 + {len(standalone_messages)} 条独立消息）...")
            
            # 统一处理队列
            for queue_index, item in enumerate(processing_queue):
                item_type = item[0]
                
                # 检查任务状态
                if task.should_stop():
                    logger.info(f"⚠️ 任务 {task.task_id} 已被{task.status}，停止处理")
                    return False
                
                # 检查超时
                elapsed_time = time.time() - task_start_time
                if elapsed_time > max_execution_time:
                    logger.warning(f"⚠️ 任务执行超时（{elapsed_time:.1f}秒 > {max_execution_time}秒），停止处理")
                    return False
                
                if item_type == 'media_group':
                    # 处理媒体组
                    _, _, media_group_id, group_messages = item
                    try:
                        logger.info(f"📱 处理媒体组 {queue_index + 1}/{len(processing_queue)}: {media_group_id}")
                        logger.info(f"🔍 媒体组详情:")
                        logger.info(f"  • 媒体组ID: {media_group_id}")
                        logger.info(f"  • 消息数量: {len(group_messages)}")
                        logger.info(f"  • 任务状态: {task.status}")
                        logger.info(f"  • 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        logger.debug(f"🔍 媒体组处理前检查:")
                        logger.info(f"  • 任务运行时间: {elapsed_time:.1f}秒")
                        logger.info(f"  • 是否应该停止: {task.should_stop()}")
                        
                        group_messages.sort(key=lambda m: m.id)
                        logger.debug(f"🔧 开始处理媒体组 {media_group_id}...")
                        start_process_time = time.time()
                        
                        success = await self._process_media_group(task, group_messages)
                        
                        process_duration = time.time() - start_process_time
                        logger.debug(f"🔍 媒体组处理完成:")
                        logger.info(f"  • 处理耗时: {process_duration:.2f}秒")
                        logger.info(f"  • 处理结果: {success}")
                        
                        if success:
                            task.stats['processed_messages'] += len(group_messages)
                            task.processed_messages += len(group_messages)
                            task.stats['media_groups'] += 1
                            # 保存进度
                            last_message_id = max(msg.id for msg in group_messages if hasattr(msg, 'id') and msg.id is not None)
                            task.save_progress(last_message_id)
                            logger.info(f"✅ 媒体组 {media_group_id} 处理成功: {len(group_messages)} 条消息")
                        else:
                            task.stats['failed_messages'] += len(group_messages)
                            task.failed_messages += len(group_messages)
                            logger.error(f"❌ 媒体组 {media_group_id} 处理失败: {len(group_messages)} 条消息")
                        
                        # 更新进度百分比
                        if hasattr(task, 'total_messages') and task.total_messages > 0:
                            task.progress = min((task.processed_messages / task.total_messages) * 100.0, 100.0)
                        else:
                            task.progress = min(task.processed_messages * 10, 100.0)
                        
                        logger.debug(f"📊 任务进度更新:")
                        logger.info(f"  • 已处理消息: {task.processed_messages}")
                        logger.info(f"  • 总消息数: {task.total_messages}")
                        if task.progress > 100.0:
                            task.progress = 100.0
                        logger.info(f"  • 进度百分比: {task.progress:.1f}%")
                        
                        # 调用进度回调
                        if self.progress_callback:
                            await self.progress_callback(task)
                        
                        # 媒体组间安全延迟
                        media_group_delay = self.media_group_delay
                        logger.debug(f"⏳ 媒体组处理完成，等待 {media_group_delay} 秒...")
                        await asyncio.sleep(media_group_delay)
                        
                    except Exception as e:
                        logger.error(f"❌ 处理媒体组失败 {media_group_id}: {e}")
                        logger.error(f"  • 错误类型: {type(e).__name__}")
                        logger.error(f"  • 错误详情: {str(e)}")
                        task.stats['failed_messages'] += len(group_messages)
                        task.failed_messages += len(group_messages)
                
                elif item_type == 'single':
                    # 处理独立消息
                    _, _, message, _ = item
                    try:
                        success = await self._process_single_message(task, message)
                        
                        if success:
                            task.stats['processed_messages'] += 1
                            task.processed_messages += 1
                            # 保存进度
                            msg_id = message.id if hasattr(message, 'id') and message.id is not None else 0
                            task.save_progress(msg_id)
                            logger.info(f"✅ 独立消息 {msg_id} 处理成功")
                        else:
                            task.stats['failed_messages'] += 1
                            task.failed_messages += 1
                        
                        # 更新进度百分比
                        if hasattr(task, 'total_messages') and task.total_messages > 0:
                            task.progress = min((task.processed_messages / task.total_messages) * 100.0, 100.0)
                        else:
                            task.progress = min(task.processed_messages * 10, 100.0)
                        
                        # 调用进度回调
                        if self.progress_callback:
                            await self.progress_callback(task)
                        
                        # 消息间延迟
                        await asyncio.sleep(self.message_delay)
                        
                    except Exception as e:
                        logger.error(f"❌ 处理独立消息失败: {e}")
                        task.stats['failed_messages'] += 1
                        task.failed_messages += 1
            
            # 所有消息处理完毕
            return True
            
        except Exception as e:
            logger.error(f"处理消息批次失败: {e}")
            return False

    # ==================== 评论处理相关方法 ====================
    
    # 评论处理相关函数已移除
    
    # 所有评论处理相关函数已移除
    
    async def stop_all_tasks(self):
        """停止所有活动任务"""
        try:
            logger.info("🛑 开始停止所有搬运任务")
            
            stopped_count = 0
            for task_id, task in list(self.active_tasks.items()):
                try:
                    if task.status in ['pending', 'running']:
                        task.status = 'stopped'
                        task.is_running = False
                        stopped_count += 1
                        logger.info(f"✅ 已停止任务: {task_id}")
                except Exception as e:
                    logger.error(f"停止任务失败 {task_id}: {e}")
            
            logger.info(f"✅ 已停止 {stopped_count} 个搬运任务")
            
        except Exception as e:
            logger.error(f"停止所有任务失败: {e}")
    
    async def _ensure_user_api_ready(self) -> bool:
        """确保User API客户端完全启动并准备好发送（强制初始化，带详细调试）"""
        try:
            if not self.user_api_client:
                logger.debug(f"   ⚠️ [调试] User API客户端不存在")
                return False
            
            logger.debug(f"   🔍 [调试] _ensure_user_api_ready: 开始检查...")
            logger.debug(f"      • client存在: {self.user_api_client is not None}")
            logger.debug(f"      • is_connected: {self.user_api_client.is_connected}")
            
            # 强制确保客户端完全启动
            try:
                # 如果已连接但未完全启动，先断开
                if self.user_api_client.is_connected:
                    try:
                        # 先测试是否能正常获取用户信息
                        logger.debug(f"   🔍 [调试] 测试get_me...")
                        me_test = await self.user_api_client.get_me()
                        logger.debug(f"   🔍 [调试] get_me结果: {me_test}")
                        if me_test:
                            # 检查是否包含is_premium属性
                            if hasattr(me_test, 'is_premium'):
                                logger.debug(f"   ✅ [调试] User API已就绪，用户: {me_test.first_name if hasattr(me_test, 'first_name') else 'N/A'}, is_premium: {me_test.is_premium}")
                                return True
                            else:
                                logger.debug(f"   ⚠️ [调试] get_me成功但缺少is_premium属性，需要重新初始化")
                                try:
                                    await self.user_api_client.disconnect()
                                except:
                                    pass
                        else:
                            # get_me返回None，需要重新初始化
                            logger.debug(f"   ⚠️ [调试] get_me返回None，需要重新初始化")
                            try:
                                await self.user_api_client.disconnect()
                            except:
                                pass
                    except Exception as test_e:
                        # get_me失败，需要重新初始化
                        logger.debug(f"   ⚠️ [调试] get_me失败: {test_e}，需要重新初始化")
                        try:
                            await self.user_api_client.disconnect()
                        except:
                            pass
                
                # 重新连接并启动
                logger.debug(f"   🔧 [调试] 重新初始化User API客户端...")
                if not self.user_api_client.is_connected:
                    logger.debug(f"   🔧 [调试] 步骤1: 连接客户端...")
                    await self.user_api_client.connect()
                    logger.debug(f"   ✅ [调试] 已连接")
                
                # 强制启动客户端（确保完全初始化）
                logger.debug(f"   🔧 [调试] 步骤2: 启动客户端...")
                try:
                    await self.user_api_client.start()
                    logger.debug(f"   ✅ [调试] 客户端已启动")
                except Exception as start_e:
                    error_str = str(start_e).lower()
                    # 如果已经启动，继续验证
                    if "already started" in error_str or "already connected" in error_str:
                        logger.debug(f"   ℹ️ [调试] 客户端已启动（这是正常的）")
                    else:
                        logger.debug(f"   ⚠️ [调试] 启动User API客户端失败: {start_e}")
                
                # 验证客户端已完全初始化
                logger.debug(f"   🔧 [调试] 步骤3: 验证初始化...")
                me = await self.user_api_client.get_me()
                logger.debug(f"   🔍 [调试] get_me结果: {me}")
                if me:
                    logger.debug(f"      • 用户ID: {me.id}")
                    logger.debug(f"      • 用户名: {me.first_name if hasattr(me, 'first_name') else 'N/A'}")
                    logger.debug(f"      • hasattr(is_premium): {hasattr(me, 'is_premium')}")
                    if hasattr(me, 'is_premium'):
                        logger.debug(f"      • is_premium值: {me.is_premium}")
                        logger.debug(f"   ✅ [调试] User API客户端已完全初始化！")
                        return True
                    else:
                        logger.warning(f"      • ⚠️ 用户对象缺少is_premium属性！")
                        logger.warning(f"   ⚠️ [调试] User API用户对象未完全初始化（缺少is_premium）")
                        return False
                else:
                    logger.warning(f"   ⚠️ [调试] User API用户对象未完全初始化（get_me返回None）")
                    return False
                    
            except Exception as e:
                logger.warning(f"   ⚠️ [调试] 初始化User API客户端失败: {e}")
                import traceback
                logger.debug(f"   详细错误: {traceback.format_exc()}")
                return False
        except Exception as e:
            logger.warning(f"   ⚠️ [调试] 确保User API就绪失败: {e}")
            import traceback
            logger.debug(f"   详细错误: {traceback.format_exc()}")
            return False
    
    async def _download_media_groups_pipeline(self, processing_queue: List[Tuple], 
                                             send_queue: asyncio.Queue, temp_dir: str, 
                                             task: CloneTask, failed_count_ref: Dict[str, int]):
        """下载协程：批量下载媒体组"""
        queue_index = 0
        batch_size = 5  # 每次下载 5 组
        # 动态跟踪实际总数（包括拆分后的媒体组）
        actual_total_count = len(processing_queue)
        
        try:
            while queue_index < len(processing_queue):
                # 检查任务是否应该停止
                if task.should_stop():
                    logger.warning(f"[构建] ⚠️ 任务已停止，中断构建")
                    break
                
                # 从处理队列中取出 5 组
                batch = []
                for _ in range(batch_size):
                    if queue_index >= len(processing_queue):
                        break
                    
                    batch.append(processing_queue[queue_index])
                    queue_index += 1
                
                if not batch:
                    logger.info(f"[构建] ✅ 所有媒体组构建完成")
                    break
                
                logger.info(f"[构建] 🔧 批量构建 {len(batch)} 组媒体（使用 file_id）...")
                
                # 批量下载每组
                for item in batch:
                    try:
                        item_type = item[0]
                        if item_type != 'media_group' and item_type != 'single_media_group':
                            continue
                        
                        _, _, group_id, group_comments = item
                        group_idx = queue_index - batch_size + batch.index(item)
                        
                        logger.info(f"[构建] 📦 [{group_idx + 1}/{actual_total_count}] 构建媒体组 (ID: {str(group_id)[:8] if group_id else 'N/A'}...)")
                        
                        # 构建媒体组
                        media_list = []
                        downloaded_files = []
                        successful_comments = []
                        
                        for idx, comment in enumerate(group_comments, 1):
                            try:
                                # 直接使用 file_id，无需下载
                                if comment.photo:
                                    logger.info(f"[构建]    📷 添加图片 {idx}/{len(group_comments)}: {comment.id}")
                                    from pyrogram.types import InputMediaPhoto
                                    media_list.append(InputMediaPhoto(media=comment.photo.file_id))
                                    successful_comments.append(comment)
                                    logger.debug(f"[构建]    ✅ 图片已添加（使用 file_id）")
                                        
                                elif comment.video:
                                    logger.info(f"[构建]    🎥 添加视频 {idx}/{len(group_comments)}: {comment.id}")
                                    from pyrogram.types import InputMediaVideo
                                    
                                    # 获取缩略图 file_id（如果存在）
                                    thumb_file_id = None
                                    try:
                                        if hasattr(comment.video, 'thumbs') and comment.video.thumbs:
                                            thumb_file_id = comment.video.thumbs[0].file_id
                                        elif hasattr(comment.video, 'thumbnail') and comment.video.thumbnail:
                                            thumb_file_id = comment.video.thumbnail.file_id
                                    except Exception as thumb_e:
                                        logger.debug(f"[构建]    ⚠️ 无法获取缩略图 file_id: {thumb_e}")
                                    
                                    # 构建视频媒体项
                                    media_list.append(InputMediaVideo(
                                        media=comment.video.file_id,
                                        thumb=thumb_file_id
                                    ))
                                    successful_comments.append(comment)
                                    logger.debug(f"[构建]    ✅ 视频已添加（使用 file_id，缩略图={'有' if thumb_file_id else '无'}）")
                                        
                            except Exception as e:
                                logger.error(f"[构建]    ❌ 构建媒体 {idx} 失败: {e}")
                                continue
                        
                        # 检查完整性
                        if len(media_list) < len(group_comments) * 0.5:
                            logger.warning(f"[构建]    ⚠️ 媒体组不完整（{len(media_list)}/{len(group_comments)}），跳过")
                            failed_count_ref['count'] += len(group_comments)
                            continue
                        
                        # Telegram限制：媒体组最多10个媒体项
                        MAX_MEDIA_PER_GROUP = 10
                        
                        if len(media_list) > MAX_MEDIA_PER_GROUP:
                            # 媒体组超过限制，需要拆分成多个媒体组
                            logger.warning(f"[构建]    ⚠️ 媒体组包含 {len(media_list)} 个媒体，超过限制（{MAX_MEDIA_PER_GROUP}），自动拆分成多个媒体组")
                            # 拆分媒体组
                            split_groups = []
                            num_splits = (len(media_list) + MAX_MEDIA_PER_GROUP - 1) // MAX_MEDIA_PER_GROUP  # 向上取整
                            for split_idx in range(0, len(media_list), MAX_MEDIA_PER_GROUP):
                                split_media = media_list[split_idx:split_idx + MAX_MEDIA_PER_GROUP]
                                split_comments = successful_comments[split_idx:split_idx + MAX_MEDIA_PER_GROUP]
                                split_num = split_idx // MAX_MEDIA_PER_GROUP
                                
                                split_group = DownloadedMediaGroup(
                                    group_id=f"{group_id}_split_{split_num}" if group_id else None,
                                    group_comments=split_comments,
                                    media_list=split_media,
                                    downloaded_files=downloaded_files,
                                    queue_index=group_idx + split_num,
                                    total_count=actual_total_count + (num_splits - 1)  # 传递更新后的总数
                                )
                                split_groups.append(split_group)
                                logger.info(f"[构建]    📦 拆分媒体组 {split_num + 1}/{num_splits}: {len(split_media)} 个媒体")
                            
                            # 拆分后，1个组变成了多个组，需要更新总数
                            # 如果原始有1个组，拆分成N个组，则总数增加 (N-1)
                            actual_total_count += (len(split_groups) - 1)
                            
                            # 将拆分后的多个媒体组放入队列
                            for split_group in split_groups:
                                # 更新所有拆分组的 total_count 为最新值
                                split_group.total_count = actual_total_count
                                await send_queue.put(split_group)
                            logger.info(f"[构建]    ✅ 媒体组已拆分为 {len(split_groups)} 个组，已全部放入发送队列（更新后总数: {actual_total_count}）")
                        else:
                            # 媒体组数量在限制内，直接放入队列
                            downloaded_group = DownloadedMediaGroup(
                                group_id=group_id,
                                group_comments=group_comments,
                                media_list=media_list,
                                downloaded_files=downloaded_files,
                                queue_index=group_idx,
                                total_count=actual_total_count  # 传递当前总数
                            )
                            await send_queue.put(downloaded_group)
                            logger.info(f"[构建]    ✅ 媒体组构建完成（{len(media_list)} 个媒体），已放入发送队列")
                        
                    except Exception as e:
                        logger.error(f"[构建]    ❌ 媒体组构建失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        failed_count_ref['count'] += len(group_comments)
                        continue
                
                logger.info(f"[构建] ✅ 批量构建完成")
            
            # 发送结束信号
            await send_queue.put(None)
            
        except Exception as e:
            logger.error(f"[下载] ❌ 下载协程失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await send_queue.put(None)
    
    async def _send_media_groups_pipeline(self, send_queue: asyncio.Queue, bot_chat_id: str,
                                         reply_to_id: Optional[int], success_count_ref: Dict[str, int],
                                         failed_count_ref: Dict[str, int], task: CloneTask):
        """发送协程：批量发送已下载的媒体组（集成动态速率控制）"""
        try:
            # 初始化速率限制器
            rate_limiter = RateLimiter(
                base_delay=6.0,  # 基础延迟6秒（从3秒增加）
                min_delay=3.0,
                max_delay=30.0,
                max_groups_per_minute=6.0  # 每分钟最多6个媒体组
            )
            
            logger.info(f"[发送] 🚀 启动智能速率控制")
            logger.info(f"[发送]   基础延迟: {rate_limiter.base_delay} 秒")
            logger.info(f"[发送]   最大速率: {rate_limiter.max_groups_per_minute} 组/分钟")
            
            # 发送计数器，用于显示连续编号
            send_index = 0
            
            while True:
                # 检查任务是否应该停止
                if task.should_stop():
                    logger.warning(f"[发送] ⚠️ 任务已停止，中断发送")
                    break
                
                # 从队列获取已下载的媒体组
                downloaded_group = await send_queue.get()
                
                # None 表示结束
                if downloaded_group is None:
                    logger.info(f"[发送] ✅ 所有媒体组发送完成")
                    break
                
                try:
                    # 增加发送计数器
                    send_index += 1
                    
                    current_time = time.time()
                    
                    # 1. 检查速率限制（发送前预防性检查）
                    rate_limit_wait = rate_limiter.check_rate_limit(current_time)
                    if rate_limit_wait is not None and rate_limit_wait > 0:
                        logger.warning(f"[发送]    ⚠️ 发送速率过高，需要等待 {rate_limit_wait:.1f} 秒")
                        await asyncio.sleep(rate_limit_wait)
                        current_time = time.time()  # 更新当前时间
                    
                    # 2. 获取预防性延迟（考虑最近的限流历史）
                    preventive_delay = rate_limiter.get_delay_with_prevention(current_time)
                    base_delay = rate_limiter.get_current_delay()
                    # 只有当预防性延迟明显大于基础延迟时才应用（避免不必要的等待）
                    if preventive_delay > base_delay * 1.2:
                        extra_delay = preventive_delay - base_delay
                        logger.debug(f"[发送]    ⏳ 应用预防性额外延迟 {extra_delay:.2f} 秒（总延迟: {preventive_delay:.2f} 秒）...")
                        await asyncio.sleep(extra_delay)
                        current_time = time.time()
                    
                    # 显示编号，优先使用 total_count，否则使用发送计数器
                    if downloaded_group.total_count > 0:
                        logger.info(f"[发送] 📦 [{send_index}/{downloaded_group.total_count}] 发送媒体组 (ID: {str(downloaded_group.group_id)[:8] if downloaded_group.group_id else 'N/A'}...)")
                    else:
                        logger.info(f"[发送] 📦 [{send_index}] 发送媒体组 (ID: {str(downloaded_group.group_id)[:8] if downloaded_group.group_id else 'N/A'}...)")
                    logger.info(f"[发送]    包含 {len(downloaded_group.media_list)} 个媒体文件")
                    logger.info(f"[发送]    📤 使用 file_id 直接转发媒体组...")
                    logger.debug(f"[发送]    当前延迟设置: {rate_limiter.get_current_delay():.2f} 秒")
                    
                    # 使用User API发送媒体组（因为评论是通过User API获取的）
                    send_success = False
                    max_retries = 3
                    severe_rate_limit_detected = False
                    
                    for retry in range(max_retries):
                        try:
                            logger.info(f"[发送]    📤 使用User API发送媒体组（尝试 {retry + 1}/{max_retries}）...")
                            
                            await self.user_api_client.send_media_group(
                                chat_id=bot_chat_id,
                                media=downloaded_group.media_list,
                                reply_to_message_id=reply_to_id if reply_to_id else None
                            )
                            
                            # 发送成功
                            current_time = time.time()
                            rate_limiter.record_send(current_time)
                            rate_limiter.adjust_after_success()
                            success_count_ref['count'] += len(downloaded_group.media_list)
                            logger.info(f"[发送]    ✅ 媒体组发送成功！（User API）")
                            send_success = True
                            break
                            
                        except FloodWait as e:
                            wait_time = e.value
                            current_time = time.time()
                            
                            # 检测严重限流
                            if rate_limiter.is_severe_rate_limit(wait_time):
                                logger.warning(f"[发送]    🚨 检测到严重限流！需要等待 {wait_time} 秒 ({wait_time/60:.1f} 分钟)")
                                logger.warning(f"[发送]    ⏳ 等待限流时间结束后继续发送剩余媒体组...")
                                
                                # 更新速率限制器
                                rate_limiter.adjust_after_flood_wait(wait_time, current_time)
                                
                                # 等待限流时间（等待完整时间，但分段等待以便检查任务状态）
                                total_wait_time = wait_time
                                wait_chunk = min(300.0, total_wait_time / 10)  # 每次最多等待5分钟或总时间的1/10
                                waited_time = 0.0
                                
                                while waited_time < total_wait_time:
                                    # 检查任务是否被手动停止
                                    if task.should_stop():
                                        logger.warning(f"[发送]    ⚠️ 任务已被{task.status}，停止等待")
                                        failed_count_ref['count'] += len(downloaded_group.group_comments)
                                        severe_rate_limit_detected = True
                                        break
                                    
                                    remaining_wait = total_wait_time - waited_time
                                    current_chunk = min(wait_chunk, remaining_wait)
                                    
                                    logger.info(f"[发送]    ⏳ 等待限流中... ({waited_time:.0f}/{total_wait_time:.0f} 秒, 剩余 {remaining_wait:.0f} 秒)")
                                    await asyncio.sleep(current_chunk)
                                    waited_time += current_chunk
                                
                                # 如果完整等待完成，继续重试发送当前媒体组
                                if waited_time >= total_wait_time:
                                    logger.info(f"[发送]    ✅ 限流等待完成，继续尝试发送此媒体组...")
                                    # 继续重试发送（不设置severe_rate_limit_detected）
                                    continue  # 继续重试循环
                                else:
                                    # 任务被停止，退出循环
                                    severe_rate_limit_detected = True
                                    break
                            else:
                                # 一般限流处理
                                logger.warning(f"[发送]    ⚠️ 触发限流，需要等待 {wait_time} 秒")
                                
                                # 更新速率限制器
                                rate_limiter.adjust_after_flood_wait(wait_time, current_time)
                                
                                if retry < max_retries - 1:
                                    logger.info(f"[发送]    ⏳ 等待 {wait_time} 秒后重试 ({retry + 1}/{max_retries})...")
                                    logger.info(f"[发送]    📊 延迟已调整为: {rate_limiter.get_current_delay():.2f} 秒")
                                    await asyncio.sleep(wait_time)
                                    current_time = time.time()
                                else:
                                    logger.error(f"[发送]    ❌ 已达最大重试次数，跳过此媒体组")
                                    failed_count_ref['count'] += len(downloaded_group.group_comments)
                                    
                        except Exception as e:
                            logger.error(f"[发送]    ❌ User API 发送失败: {e}")
                            if retry < max_retries - 1:
                                logger.info(f"[发送]    ⏳ 等待 3 秒后重试 ({retry + 1}/{max_retries})...")
                                await asyncio.sleep(3)
                                current_time = time.time()
                            else:
                                logger.error(f"[发送]    ❌ 已达最大重试次数，跳过此媒体组")
                                failed_count_ref['count'] += len(downloaded_group.group_comments)
                    
                    # 如果检测到严重限流且任务被停止，跳出循环
                    if severe_rate_limit_detected and task.should_stop():
                        logger.warning(f"[发送]    ⚠️ 任务已被{task.status}，停止发送剩余媒体组")
                        break
                    
                    # 3. 发送后的智能延迟（根据当前速率和限流历史动态调整）
                    if send_success:
                        current_time = time.time()
                        delay = rate_limiter.get_delay_with_prevention(current_time)
                        
                        # 计算当前速率
                        recent_sends = [t for t in rate_limiter.send_times if current_time - t < 60.0]
                        current_rate = len(recent_sends)
                        
                        logger.debug(f"[发送]    📊 发送统计: 速率={current_rate:.1f} 组/分钟, 延迟={delay:.2f} 秒")
                        
                        if delay > 0:
                            logger.debug(f"[发送]    ⏳ 等待 {delay:.2f} 秒后发送下一个媒体组...")
                            await asyncio.sleep(delay)
                    
                except Exception as e:
                    failed_count_ref['count'] += len(downloaded_group.group_comments)
                    logger.error(f"[发送]    ❌ 媒体组处理失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"[发送] ❌ 发送协程失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _clone_message_comments(self, task: CloneTask, source_message: Message, 
                                     target_message: Message, config: Dict[str, Any]):
        """搬运消息的评论区（支持媒体组和讨论组）"""
        try:
            # 检查是否有 User API 客户端
            if not self.user_api_client:
                logger.warning(f"💬 无法搬运评论区：User API 客户端未设置")
                return
            
            # 获取配置
            comment_limit = config.get('comment_clone_limit', 50)
            sort_mode = config.get('comment_clone_sort', 'chronological')
            
            # 清理旧的下载缓存
            temp_dir = "downloads/comments_temp"
            if os.path.exists(temp_dir):
                try:
                    file_count = len([f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))])
                    if file_count > 0:
                        shutil.rmtree(temp_dir)
                        os.makedirs(temp_dir, exist_ok=True)
                        logger.info(f"🧹 已清理 {file_count} 个旧的缓存文件")
                except Exception as e:
                    logger.warning(f"⚠️ 清理缓存失败: {e}")
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"💬 开始搬运评论区")
            logger.info(f"   源消息: {source_message.id}")
            logger.info(f"   目标消息: {target_message.id}")
            logger.info(f"   评论数量限制: {comment_limit if comment_limit > 0 else '不限制'}")
            logger.info(f"   排序方式: {'时间顺序' if sort_mode == 'chronological' else '倒序'}")
            logger.info(f"{'='*60}")
            
            # 1. 获取目标频道的讨论组 ID，并找到对应的转发消息
            target_discussion_chat_id = None
            discussion_forward_msg_id = None
            can_access_discussion = False
            
            try:
                target_chat = await self.client.get_chat(target_message.chat.id)
                if hasattr(target_chat, 'linked_chat') and target_chat.linked_chat and hasattr(target_chat.linked_chat, 'id'):
                    target_discussion_chat_id = target_chat.linked_chat.id
                    logger.info(f"📍 检测到目标讨论组: {target_discussion_chat_id}")
                    
                    # 检查 User API 是否能访问讨论组（用于查找转发消息）
                    logger.info(f"🔍 检查 User API 是否可以访问讨论组...")
                    logger.info(f"   讨论组ID: {target_discussion_chat_id}")
                    logger.info(f"   注意：Bot API 仍会用于发送评论")
                    
                    # 检查是否配置了讨论组用户名
                    user_config = await self.data_manager.get_user_config(str(task.user_id)) if self.data_manager else {}
                    discussion_usernames = user_config.get('discussion_group_username', {})
                    discussion_username = discussion_usernames.get(str(target_message.chat.id), '')
                    
                    try:
                        # 优先尝试：使用用户配置的讨论组用户名
                        if discussion_username:
                            logger.info(f"📱 发现配置的讨论组用户名: {discussion_username}")
                            logger.info(f"🔄 优先使用用户名访问...")
                            try:
                                if self.user_api_client:
                                    discussion_chat = await self.user_api_client.get_chat(discussion_username)
                                    target_discussion_chat_id = discussion_chat.id  # 更新为实际ID
                                    can_access_discussion = True
                                    logger.info(f"✅ User API 可以访问讨论组（通过用户名）")
                                    logger.info(f"   讨论组名称: {discussion_chat.title if hasattr(discussion_chat, 'title') else '未知'}")
                                    logger.info(f"   讨论组ID: {target_discussion_chat_id}")
                                else:
                                    logger.warning("User API客户端未初始化")
                            except Exception as e_username:
                                logger.warning(f"⚠️ 通过用户名访问失败: {e_username}")
                                logger.info(f"🔄 回退到ID访问...")
                                # 回退到ID访问
                                if self.user_api_client:
                                    discussion_chat = await self.user_api_client.get_chat(target_discussion_chat_id)
                                    can_access_discussion = True
                                    logger.info(f"✅ User API 可以访问讨论组（通过ID）")
                                    logger.info(f"   讨论组名称: {discussion_chat.title if hasattr(discussion_chat, 'title') else '未知'}")
                        else:
                            # 尝试1：直接通过ID访问
                            logger.info(f"🔄 未配置讨论组用户名，使用ID访问...")
                            if self.user_api_client:
                                discussion_chat = await self.user_api_client.get_chat(target_discussion_chat_id)
                                can_access_discussion = True
                                logger.info(f"✅ User API 可以访问讨论组（通过ID）")
                                logger.info(f"   讨论组名称: {discussion_chat.title if hasattr(discussion_chat, 'title') else '未知'}")
                            else:
                                logger.warning("User API客户端未初始化")
                    except Exception as e:
                        logger.warning(f"⚠️ 通过ID访问失败: {e}")
                        logger.info(f"🔄 尝试通过 resolve_peer 方法...")
                        
                        try:
                            # 尝试2：使用 resolve_peer（这会强制更新 peer 缓存）
                            from pyrogram import raw
                            
                            # 将 -100 前缀的 chat_id 转换为正确的格式
                            chat_id_str = str(target_discussion_chat_id)
                            if chat_id_str.startswith('-100'):
                                channel_id = int(chat_id_str[4:])  # 移除 -100 前缀
                            else:
                                channel_id = abs(target_discussion_chat_id)
                            
                            logger.info(f"   尝试解析频道ID: {channel_id}")
                            
                            # 使用原始 API 调用
                            peer = await self.user_api_client.resolve_peer(target_discussion_chat_id)
                            logger.info(f"✅ Peer 解析成功，重新获取讨论组信息...")
                            
                            # 再次尝试获取
                            discussion_chat = await self.user_api_client.get_chat(target_discussion_chat_id)
                            can_access_discussion = True
                            logger.info(f"✅ User API 可以访问讨论组（通过 resolve_peer）")
                            logger.info(f"   讨论组名称: {discussion_chat.title if hasattr(discussion_chat, 'title') else '未知'}")
                            
                        except Exception as e2:
                            logger.warning(f"⚠️ resolve_peer 也失败: {e2}")
                            logger.info(f"🔄 最后尝试：通过 Bot API 获取讨论组信息...")
                            
                            try:
                                # 尝试3：通过 Bot API 获取讨论组信息，然后用 User API 重试
                                bot_discussion_chat = await self.client.get_chat(target_discussion_chat_id)
                                logger.info(f"✅ Bot API 可以访问讨论组: {bot_discussion_chat.title if hasattr(bot_discussion_chat, 'title') else '未知'}")
                                
                                # 现在让 User API 也尝试（可能已经缓存了）
                                logger.info(f"🔄 让 User API 重新尝试访问...")
                                await asyncio.sleep(1)
                                
                                discussion_chat = await self.user_api_client.get_chat(target_discussion_chat_id)
                                can_access_discussion = True
                                logger.info(f"✅ User API 现在可以访问讨论组了！")
                            except Exception as e3:
                                can_access_discussion = False
                                logger.error(f"❌ User API 仍无法访问: {e3}")
                                logger.error(f"")
                                logger.error(f"⚠️ 关键问题：无法查找转发消息（Bot API 和 User API 都不行）")
                                logger.error(f"")
                                logger.error(f"必须手动操作：")
                                logger.error(f"1. 用 User API 账号手动打开讨论组")
                                logger.error(f"2. 在讨论组中发送一条消息")
                                logger.error(f"3. 重启机器人")
                                logger.error(f"")
                                logger.error(f"⚠️ 评论将直接发送到讨论组，不会关联到频道")
                    
                    # 等待频道消息自动转发到讨论组（增加等待时间和重试）
                    logger.info(f"⏳ 等待频道消息转发到讨论组...")
                    
                    # 选择用于查找的客户端
                    search_client = self.user_api_client if can_access_discussion else self.client
                    search_client_name = "User API" if can_access_discussion else "Bot API"
                    logger.info(f"   使用 {search_client_name} 查找转发消息")
                    
                    # 重试最多3次，每次等待更长时间
                    for retry in range(3):
                        await asyncio.sleep(3 if retry == 0 else 5)  # 第一次3秒，之后5秒
                        
                        try:
                            logger.info(f"🔍 第 {retry+1}/3 次查找转发消息...")
                            found_count = 0
                            # 获取讨论组最近的几条消息
                            async for msg in search_client.get_chat_history(target_discussion_chat_id, limit=30):
                                found_count += 1
                                logger.debug(f"   检查消息 {msg.id}: forward_from_chat={hasattr(msg, 'forward_from_chat')}, "
                                           f"forward_from_message_id={getattr(msg, 'forward_from_message_id', None)}")
                                
                                # 检查是否是从目标频道转发的消息
                                if (hasattr(msg, 'forward_from_chat') and 
                                    msg.forward_from_chat and 
                                    msg.forward_from_chat.id == target_message.chat.id and
                                    hasattr(msg, 'forward_from_message_id') and
                                    msg.forward_from_message_id == target_message.id):
                                    discussion_forward_msg_id = msg.id
                                    logger.info(f"✅ 找到讨论组转发消息: {discussion_forward_msg_id} (在第 {retry+1} 次尝试)")
                                    break
                            
                            logger.info(f"   已检查 {found_count} 条消息")
                            
                            if discussion_forward_msg_id:
                                break  # 找到了，跳出重试循环
                            
                            if retry < 2:
                                logger.info(f"   未找到，继续等待...")
                        except Exception as e:
                            logger.warning(f"   查找失败: {e}")
                            if retry < 2:
                                logger.info(f"   {retry+1}/3 次查找失败，继续重试...")
                    
                    if not discussion_forward_msg_id:
                        logger.error(f"❌ 3次尝试后仍未找到讨论组转发消息！")
                        logger.error(f"   可能原因：1) 频道未开启自动转发 2) 转发延迟过长 3) 权限不足")
                        logger.error(f"   评论将无法正确关联到频道消息！")
                else:
                    logger.info(f"📍 目标频道无讨论组，评论将作为回复发送")
            except Exception as e:
                logger.error(f"❌ 获取讨论组信息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 2. 获取源消息的所有评论 - 使用 User API
            logger.info(f"")
            logger.info(f"📥 开始获取源消息的评论...")
            logger.info(f"   源频道ID: {source_message.chat.id}")
            logger.info(f"   源消息ID: {source_message.id}")
            logger.info(f"   源频道类型: {type(source_message.chat).__name__}")
            logger.info(f"   源频道标题: {getattr(source_message.chat, 'title', 'N/A')}")
            
            comments = []
            source_chat_id = source_message.chat.id
            source_msg_id = source_message.id
            get_comments_success = False
            
            # 调试步骤1: 检查User API是否能访问源频道
            logger.info(f"")
            logger.info(f"🔧 [DEBUG] 步骤1: 检查User API是否能访问源频道...")
            source_chat_accessible = False
            source_chat_username = None
            
            # 尝试1: 直接使用ID访问
            try:
                source_chat_info = await self.user_api_client.get_chat(source_chat_id)
                logger.info(f"🔧 [DEBUG] ✅ User API 可以访问源频道（通过ID）")
                logger.info(f"🔧 [DEBUG]    频道标题: {getattr(source_chat_info, 'title', 'N/A')}")
                logger.info(f"🔧 [DEBUG]    频道ID: {source_chat_info.id}")
                logger.info(f"🔧 [DEBUG]    频道类型: {type(source_chat_info).__name__}")
                if hasattr(source_chat_info, 'username') and source_chat_info.username:
                    source_chat_username = source_chat_info.username
                    logger.info(f"🔧 [DEBUG]    频道用户名: @{source_chat_username}")
                if hasattr(source_chat_info, 'linked_chat') and source_chat_info.linked_chat:
                    logger.info(f"🔧 [DEBUG]    关联讨论组ID: {source_chat_info.linked_chat.id}")
                else:
                    logger.info(f"🔧 [DEBUG]    未找到关联讨论组")
                source_chat_accessible = True
            except Exception as e:
                logger.error(f"🔧 [DEBUG] ❌ User API 无法通过ID访问源频道: {e}")
                logger.error(f"🔧 [DEBUG]     错误类型: {type(e).__name__}")
                
                # 尝试2: 检查用户配置中是否有源频道用户名
                try:
                    logger.info(f"🔧 [DEBUG]     尝试从用户配置获取源频道用户名...")
                    user_config = await self.data_manager.get_user_config(str(task.user_id))
                    source_channel_usernames = user_config.get('source_channel_username', {})
                    source_chat_username = source_channel_usernames.get(str(source_chat_id), '')
                    
                    if source_chat_username:
                        logger.info(f"🔧 [DEBUG]     找到配置的源频道用户名: @{source_chat_username}")
                        logger.info(f"🔧 [DEBUG]     尝试使用用户名访问...")
                        try:
                            source_chat_info = await self.user_api_client.get_chat(source_chat_username)
                            logger.info(f"🔧 [DEBUG] ✅ User API 可以访问源频道（通过用户名）")
                            logger.info(f"🔧 [DEBUG]    频道标题: {getattr(source_chat_info, 'title', 'N/A')}")
                            logger.info(f"🔧 [DEBUG]    频道ID: {source_chat_info.id}")
                            logger.info(f"🔧 [DEBUG]    频道类型: {type(source_chat_info).__name__}")
                            # 更新source_chat_id为实际ID（可能不同）
                            if source_chat_info.id != source_chat_id:
                                logger.warning(f"🔧 [DEBUG]    警告：用户名对应的ID ({source_chat_info.id}) 与原始ID ({source_chat_id}) 不同")
                            source_chat_id = source_chat_info.id  # 更新为正确的ID
                            source_chat_accessible = True
                        except Exception as e_username:
                            logger.error(f"🔧 [DEBUG] ❌ 通过用户名访问也失败: {e_username}")
                            logger.error(f"🔧 [DEBUG]     错误类型: {type(e_username).__name__}")
                    else:
                        logger.info(f"🔧 [DEBUG]     用户配置中未找到源频道用户名")
                except Exception as e_config:
                    logger.warning(f"🔧 [DEBUG]     读取用户配置失败: {e_config}")
                
                # 尝试3: 尝试从源消息对象获取用户名
                if not source_chat_accessible and hasattr(source_message.chat, 'username') and source_message.chat.username:
                    try:
                        logger.info(f"🔧 [DEBUG]     尝试从源消息对象获取用户名: @{source_message.chat.username}")
                        source_chat_info = await self.user_api_client.get_chat(source_message.chat.username)
                        logger.info(f"🔧 [DEBUG] ✅ User API 可以访问源频道（通过消息对象中的用户名）")
                        logger.info(f"🔧 [DEBUG]    频道标题: {getattr(source_chat_info, 'title', 'N/A')}")
                        logger.info(f"🔧 [DEBUG]    频道ID: {source_chat_info.id}")
                        source_chat_username = source_message.chat.username
                        if source_chat_info.id != source_chat_id:
                            logger.warning(f"🔧 [DEBUG]    警告：用户名对应的ID ({source_chat_info.id}) 与原始ID ({source_chat_id}) 不同")
                        source_chat_id = source_chat_info.id  # 更新为正确的ID
                        source_chat_accessible = True
                    except Exception as e_msg_username:
                        logger.error(f"🔧 [DEBUG] ❌ 通过消息对象中的用户名访问也失败: {e_msg_username}")
                
                if not source_chat_accessible:
                    import traceback
                    logger.debug(f"🔧 [DEBUG]     详细堆栈:\n{traceback.format_exc()}")
                    logger.error(f"🔧 [DEBUG]     所有访问源频道的方法都失败")
                    logger.error(f"🔧 [DEBUG]     建议：")
                    logger.error(f"🔧 [DEBUG]       1. 确保User API账号已加入源频道")
                    logger.error(f"🔧 [DEBUG]       2. 如果频道有公开用户名，可在配置中添加源频道用户名映射")
                    logger.error(f"🔧 [DEBUG]       3. 检查User API账号是否有访问该频道的权限")
            
            # 调试步骤2: 检查源消息是否存在
            logger.info(f"")
            logger.info(f"🔧 [DEBUG] 步骤2: 检查源消息是否存在...")
            try:
                source_msg_check = await self.user_api_client.get_messages(source_chat_id, source_msg_id)
                if source_msg_check:
                    logger.info(f"🔧 [DEBUG] ✅ 源消息存在")
                    logger.info(f"🔧 [DEBUG]    消息ID: {source_msg_check.id}")
                    logger.info(f"🔧 [DEBUG]    消息类型: {type(source_msg_check).__name__}")
                else:
                    logger.warning(f"🔧 [DEBUG] ⚠️ 源消息不存在或无法访问")
            except Exception as e:
                logger.error(f"🔧 [DEBUG] ❌ 无法获取源消息: {e}")
                logger.error(f"🔧 [DEBUG]     错误类型: {type(e).__name__}")
                import traceback
                logger.debug(f"🔧 [DEBUG]     详细堆栈:\n{traceback.format_exc()}")
            
            # 尝试使用 User API 获取评论，如果失败则尝试多种方法
            logger.info(f"")
            logger.info(f"🔧 [DEBUG] 步骤3: 开始尝试获取评论...")
            
            # 决定使用哪个标识符来访问（优先使用用户名）
            chat_identifier = source_chat_username if source_chat_username and source_chat_accessible else source_chat_id
            identifier_type = "用户名" if source_chat_username and source_chat_accessible else "ID"
            logger.info(f"🔧 [DEBUG]     将使用 {identifier_type} 访问: {chat_identifier}")
            
            # 尝试1: 使用最佳标识符获取评论
            logger.info(f"🔧 [DEBUG] 尝试1: 使用 {identifier_type} 获取评论...")
            try:
                logger.info(f"🔄 尝试使用 User API 获取评论...")
                logger.info(f"🔧 [DEBUG]     参数: chat_id={chat_identifier} ({identifier_type}), message_id={source_msg_id}, limit={comment_limit if comment_limit > 0 else None}")
                
                comment_count = 0
                async for comment in self.user_api_client.get_discussion_replies(
                    chat_identifier,
                    source_msg_id,
                    limit=comment_limit if comment_limit > 0 else None
                ):
                    comments.append(comment)
                    comment_count += 1
                    if comment_count <= 3:  # 只记录前3条评论的详细信息
                        logger.debug(f"🔧 [DEBUG]     评论 {comment_count}: ID={comment.id}, 类型={type(comment).__name__}")
                
                get_comments_success = True
                logger.info(f"✅ User API 获取评论成功: 共 {len(comments)} 条")
                logger.info(f"🔧 [DEBUG]     成功获取评论数量: {len(comments)}")
            except Exception as e:
                logger.error(f"⚠️ User API 获取评论失败: {e}")
                logger.error(f"🔧 [DEBUG]     错误类型: {type(e).__name__}")
                logger.error(f"🔧 [DEBUG]     错误消息: {str(e)}")
                import traceback
                logger.debug(f"🔧 [DEBUG]     详细堆栈:\n{traceback.format_exc()}")
                
                # 尝试2: 使用 resolve_peer 更新 peer 缓存后重试
                logger.info(f"")
                logger.info(f"🔧 [DEBUG] 尝试2: 使用 resolve_peer 更新 peer 缓存...")
                try:
                    logger.info(f"🔄 尝试使用 resolve_peer 更新 peer 缓存...")
                    from pyrogram import raw
                    
                    # 解析 peer（使用实际可用的标识符）
                    resolve_identifier = chat_identifier
                    logger.info(f"🔧 [DEBUG]     调用 resolve_peer({resolve_identifier})...")
                    peer = await self.user_api_client.resolve_peer(resolve_identifier)
                    logger.info(f"🔧 [DEBUG]     ✅ Peer 解析成功")
                    logger.info(f"🔧 [DEBUG]     Peer 类型: {type(peer).__name__}")
                    logger.info(f"🔧 [DEBUG]     Peer 值: {peer}")
                    
                    # 等待一下让缓存生效
                    await asyncio.sleep(2)  # 增加等待时间
                    logger.info(f"🔧 [DEBUG]     等待2秒后重试获取评论...")
                    
                    # 重新尝试获取评论（使用更新后的ID或用户名）
                    comment_count = 0
                    async for comment in self.user_api_client.get_discussion_replies(
                        resolve_identifier,
                        source_msg_id,
                        limit=comment_limit if comment_limit > 0 else None
                    ):
                        comments.append(comment)
                        comment_count += 1
                    
                    get_comments_success = True
                    logger.info(f"✅ resolve_peer 后获取评论成功: 共 {len(comments)} 条")
                    logger.info(f"🔧 [DEBUG]     成功获取评论数量: {len(comments)}")
                except Exception as e2:
                    logger.error(f"⚠️ resolve_peer 方法也失败: {e2}")
                    logger.error(f"🔧 [DEBUG]     错误类型: {type(e2).__name__}")
                    logger.error(f"🔧 [DEBUG]     错误消息: {str(e2)}")
                    import traceback
                    logger.debug(f"🔧 [DEBUG]     详细堆栈:\n{traceback.format_exc()}")
                    
                    # 尝试3: 尝试不同的chat_id格式
                    logger.info(f"")
                    logger.info(f"🔧 [DEBUG] 尝试3: 尝试不同的chat_id格式...")
                    try:
                        # 如果chat_id是负数，尝试转换为正数格式
                        if isinstance(source_chat_id, int) and source_chat_id < 0:
                            # 移除 -100 前缀
                            chat_id_str = str(source_chat_id)
                            if chat_id_str.startswith('-100'):
                                channel_id = int(chat_id_str[4:])
                                logger.info(f"🔧 [DEBUG]     尝试格式转换: {source_chat_id} -> {channel_id}")
                                logger.info(f"🔄 尝试使用转换后的ID格式获取评论...")
                                
                                # 先解析peer
                                peer = await self.user_api_client.resolve_peer(channel_id)
                                await asyncio.sleep(1)
                                
                                comment_count = 0
                                async for comment in self.user_api_client.get_discussion_replies(
                                    channel_id,
                                    source_msg_id,
                                    limit=comment_limit if comment_limit > 0 else None
                                ):
                                    comments.append(comment)
                                    comment_count += 1
                                
                                get_comments_success = True
                                source_chat_id = channel_id  # 更新为成功的ID
                                logger.info(f"✅ 使用转换后的ID格式获取评论成功: 共 {len(comments)} 条")
                            else:
                                raise Exception("不支持的ID格式")
                        else:
                            raise Exception("ID格式不符合转换条件")
                    except Exception as e3:
                        logger.error(f"⚠️ ID格式转换方法也失败: {e3}")
                        logger.error(f"🔧 [DEBUG]     错误类型: {type(e3).__name__}")
                        logger.error(f"🔧 [DEBUG]     错误消息: {str(e3)}")
            
            # 如果所有方法都失败，记录详细错误信息但不跳过
            if not get_comments_success:
                logger.error(f"")
                logger.error(f"❌ 获取评论失败: 所有方法都失败")
                logger.error(f"🔧 [DEBUG] 最终诊断信息:")
                logger.error(f"   源频道ID: {source_chat_id}")
                logger.error(f"   源消息ID: {source_msg_id}")
                logger.error(f"   源频道类型: {type(source_message.chat).__name__}")
                logger.error(f"   尝试使用的标识符: {chat_identifier} ({identifier_type})")
                if source_chat_username:
                    logger.error(f"   源频道用户名: @{source_chat_username}")
                else:
                    logger.error(f"   源频道用户名: 未找到")
                logger.error(f"   可能原因:")
                logger.error(f"   1. User API 账号未加入源频道（最常见原因）")
                logger.error(f"   2. 源频道设置了访问限制")
                logger.error(f"   3. 源消息没有关联的讨论组")
                logger.error(f"   4. Peer ID 缓存问题")
                logger.error(f"   5. 频道ID格式问题")
                logger.error(f"")
                logger.error(f"🔧 [DEBUG] 解决方案:")
                logger.error(f"   1. 确保User API账号已加入源频道（最重要）")
                logger.error(f"   2. 如果源频道有公开用户名，可在用户配置中添加映射:")
                logger.error(f"      source_channel_username['{source_chat_id}'] = '@channel_username'")
                logger.error(f"   3. 检查User API账号是否有访问该频道的权限")
                logger.error(f"   4. 如果是私有频道，确保User API账号已被邀请")
                logger.error(f"")
                logger.error(f"⚠️ 将使用空评论列表继续处理，但会记录此错误")
                comments = []  # 设置为空列表，继续执行后续流程
            
            # 如果成功但没有评论，记录信息
            if not comments:
                logger.info(f"ℹ️ 该消息没有评论（或获取失败），评论区为空")
                logger.info(f"🔧 [DEBUG]     评论数量: 0")
                # 不返回，继续执行后续流程（即使没有评论也可能需要处理其他逻辑）
            
            logger.info(f"✅ 找到 {len(comments)} 条评论")
            
            # 根据配置排序
            if sort_mode == 'reverse':
                comments.reverse()
                logger.info(f"🔄 已按倒序排列评论")
            
            # 3. 过滤：只保留有媒体的评论（图片、视频）
            logger.info(f"")
            logger.info(f"🔍 开始过滤评论（只保留图片和视频）...")
            media_comments = []
            text_count = 0
            for comment in comments:
                if comment.photo or comment.video or (comment.document and comment.document.mime_type and comment.document.mime_type.startswith(('image/', 'video/'))):
                    media_comments.append(comment)
                else:
                    text_count += 1
            
            logger.info(f"✅ 过滤完成:")
            logger.info(f"   • 保留媒体评论: {len(media_comments)} 条")
            logger.info(f"   • 跳过纯文本: {text_count} 条")
            
            if not media_comments:
                logger.info(f"ℹ️ 没有媒体评论，评论区搬运完成（无内容）")
                logger.info(f"🔧 [DEBUG]     评论总数: {len(comments)}, 媒体评论数: 0")
                # 不返回，继续执行后续流程（确保函数正常结束）
            
            # 4. 按媒体组分组（仅在有待处理的评论时执行）
            if media_comments:
                logger.info(f"")
                logger.info(f"🔗 开始检测媒体组...")
                media_groups = {}  # {media_group_id: [comments]}
                single_comments = []  # 非媒体组的评论
                
                for comment in media_comments:
                    if hasattr(comment, 'media_group_id') and comment.media_group_id:
                        if comment.media_group_id not in media_groups:
                            media_groups[comment.media_group_id] = []
                        media_groups[comment.media_group_id].append(comment)
                    else:
                        single_comments.append(comment)
                
                logger.info(f"✅ 分组完成:")
                logger.info(f"   • 媒体组: {len(media_groups)} 组")
                logger.info(f"   • 单条媒体: {len(single_comments)} 条")
                logger.info(f"🔧 [DEBUG]     媒体组详情: {[(gid, len(comms)) for gid, comms in media_groups.items()]}")
            else:
                # 没有媒体评论，设置空值
                logger.info(f"")
                logger.info(f"🔗 跳过媒体组检测（无媒体评论）")
                media_groups = {}
                single_comments = []
                logger.info(f"🔧 [DEBUG]     媒体组: 0 组, 单条媒体: 0 条")
            
            # 5. 准备临时目录
            temp_dir = "downloads/comments_temp"
            os.makedirs(temp_dir, exist_ok=True)
            
            # 6. 确定发送目标
            send_to_chat_id = target_discussion_chat_id if target_discussion_chat_id else target_message.chat.id
            reply_to_id = discussion_forward_msg_id if discussion_forward_msg_id else (None if target_discussion_chat_id else target_message.id)
            
            # 保存讨论组用户名（如果配置了）用于User API发送
            send_to_chat_username = None
            if target_discussion_chat_id:
                # 检查是否配置了讨论组用户名
                user_config = await self.data_manager.get_user_config(str(task.user_id))
                discussion_usernames = user_config.get('discussion_group_username', {})
                send_to_chat_username = discussion_usernames.get(str(target_message.chat.id), '')
            
            logger.info(f"")
            logger.info(f"📤 发送配置:")
            logger.info(f"   • 发送到: {'讨论组' if target_discussion_chat_id else '频道'} ({send_to_chat_id})")
            logger.info(f"   • 回复消息ID: {reply_to_id if reply_to_id else '无（直接发送）'}")
            logger.info(f"   • 获取方式: User API（获取评论和查找转发消息）")
            logger.info(f"   • 发送方式: User API（会员不限速）")
            
            if not discussion_forward_msg_id and target_discussion_chat_id:
                logger.warning(f"⚠️ 警告：未找到转发消息，评论将无法关联到频道！")
                logger.warning(f"   评论会发送到讨论组，但不会显示在频道评论区")
            
            success_count = 0
            failed_count = 0
            
            # 7. 创建统一的处理队列，按评论ID排序（保持原始顺序）
            processing_queue = []
            
            # 添加媒体组到队列（使用最小评论ID作为排序键）
            for group_id, group_comments in media_groups.items():
                min_id = min(c.id for c in group_comments if hasattr(c, 'id') and c.id)
                processing_queue.append(('media_group', min_id, group_id, group_comments))
            
            # 将单个图片/视频按顺序合并成媒体组一起发送
            # 而不是单个发送
            if single_comments:
                # 按评论ID排序单个媒体
                single_comments_sorted = sorted(single_comments, key=lambda c: c.id if hasattr(c, 'id') and c.id else 0)
                # 将它们作为一个媒体组
                min_single_id = min(c.id for c in single_comments_sorted if hasattr(c, 'id') and c.id) if single_comments_sorted else 0
                processing_queue.append(('single_media_group', min_single_id, None, single_comments_sorted))
            
            # 按评论ID排序队列
            processing_queue.sort(key=lambda x: x[1])
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"📋 处理队列已创建并排序")
            logger.info(f"   • 总项目: {len(processing_queue)}")
            logger.info(f"   • 媒体组: {len(media_groups)} 组（原媒体组）")
            logger.info(f"   • 单条媒体组: {1 if single_comments else 0} 组（由 {len(single_comments)} 个单个媒体组成）")
            logger.info(f"   • 排序方式: 按评论ID从小到大")
            logger.info(f"{'='*60}")
            logger.info(f"🔧 [DEBUG]     处理队列详情: {[item[0] for item in processing_queue]}")
            
            # 如果处理队列为空，直接结束
            if not processing_queue:
                logger.info(f"")
                logger.info(f"ℹ️ 处理队列为空，评论区搬运完成（无需处理）")
                logger.info(f"🔧 [DEBUG]     成功: 0, 失败: 0")
                success_count = 0
                failed_count = 0
            else:
                # 8. 流水线模式：并发下载和发送
                logger.info(f"")
                logger.info(f"{'='*60}")
                logger.info(f"🚀 启动流水线模式（批量下载 5 组 + 并发发送）")
                logger.info(f"{'='*60}")
                
                # 创建发送队列（用于在下载协程和发送协程间传递数据）
                send_queue = asyncio.Queue()
                
                # 确定Bot API的chat_id
                bot_chat_id = send_to_chat_username if send_to_chat_username else send_to_chat_id
                
                # 使用字典引用传递计数器（因为是整数不可变类型）
                success_count_ref = {'count': 0}
                failed_count_ref = {'count': 0}
                
                logger.info(f"🔧 [DEBUG]     启动下载和发送协程...")
                logger.info(f"🔧 [DEBUG]     发送到: {bot_chat_id}")
                logger.info(f"🔧 [DEBUG]     回复ID: {reply_to_id}")
                
                # 启动下载协程和发送协程
                download_task = asyncio.create_task(
                    self._download_media_groups_pipeline(
                        processing_queue, send_queue, temp_dir, task, failed_count_ref
                    )
                )
                send_task = asyncio.create_task(
                    self._send_media_groups_pipeline(
                        send_queue, bot_chat_id, reply_to_id, success_count_ref, failed_count_ref, task
                    )
                )
                
                # 等待两个协程完成
                logger.info(f"🔧 [DEBUG]     等待协程完成...")
                await asyncio.gather(download_task, send_task)
                logger.info(f"🔧 [DEBUG]     协程完成")
                
                # 更新计数器
                success_count = success_count_ref['count']
                failed_count = failed_count_ref['count']
            
            # 旧代码保留注释（已在上面替换为流水线模式）
            if False:  # 旧代码不再执行
                for queue_index, item in enumerate(processing_queue, 1):
                    item_type = item[0]
                    
                    if task.should_stop():
                        logger.warning(f"⚠️ 任务已停止，中断评论处理")
                        break
                    
                    if item_type == 'media_group' or item_type == 'single_media_group':
                        # 处理媒体组（原媒体组或由单个媒体组成的媒体组）
                        _, _, group_id, group_comments = item
                    logger.info(f"")
                    if item_type == 'media_group':
                        logger.info(f"📦 [{queue_index}/{len(processing_queue)}] 处理媒体组 (ID: {str(group_id)[:8]}...)")
                    else:
                        logger.info(f"📦 [{queue_index}/{len(processing_queue)}] 处理单条媒体组（由 {len(group_comments)} 个单个媒体组成）")
                    logger.info(f"   包含 {len(group_comments)} 个媒体文件")
                    
                    try:
                        # 构建媒体组
                        media_list = []
                        downloaded_files = []
                        successful_comments = []  # 记录成功下载的评论，用于重建媒体组
                        
                        for idx, comment in enumerate(group_comments, 1):
                            try:
                                # 下载媒体
                                if comment.photo:
                                    logger.info(f"   📥 下载图片 {idx}/{len(group_comments)}: {comment.id}")
                                    file_path = await self.user_api_client.download_media(
                                        comment.photo.file_id,
                                        file_name=f"{temp_dir}/comment_{comment.id}.jpg"
                                    )
                                    
                                    if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info(f"   ✅ 图片下载完成: {os.path.getsize(file_path)} bytes")
                                        # 使用绝对路径确保文件路径正确
                                        abs_path = os.path.abspath(file_path)
                                        from pyrogram.types import InputMediaPhoto
                                        media_list.append(InputMediaPhoto(abs_path))
                                        downloaded_files.append(abs_path)
                                        successful_comments.append(comment)  # 保存成功下载的评论
                                    else:
                                        logger.warning(f"   ⚠️ 图片下载失败或文件无效")
                                        
                                elif comment.video:
                                    logger.info(f"   📥 下载视频 {idx}/{len(group_comments)}: {comment.id}")
                                    file_path = await self.user_api_client.download_media(
                                        comment.video.file_id,
                                        file_name=f"{temp_dir}/comment_{comment.id}.mp4"
                                    )
                                    
                                    if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info(f"   ✅ 视频下载完成: {os.path.getsize(file_path)} bytes")
                                        
                                        # 下载视频缩略图（如果有）
                                        thumb_path = None
                                        try:
                                            # 尝试多种方式获取缩略图
                                            thumbnail_obj = None
                                            if hasattr(comment.video, 'thumbs') and comment.video.thumbs:
                                                # 使用thumbs列表中的第一个缩略图
                                                thumbnail_obj = comment.video.thumbs[0]
                                            elif hasattr(comment.video, 'thumbnail') and comment.video.thumbnail:
                                                # 使用thumbnail属性
                                                thumbnail_obj = comment.video.thumbnail
                                            
                                            if thumbnail_obj and hasattr(thumbnail_obj, 'file_id'):
                                                thumb_path = await self.user_api_client.download_media(
                                                    thumbnail_obj.file_id,
                                                    file_name=f"{temp_dir}/comment_{comment.id}_thumb.jpg"
                                                )
                                                if thumb_path and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                                                    logger.info(f"   ✅ 缩略图下载完成: {os.path.getsize(thumb_path)} bytes")
                                                else:
                                                    thumb_path = None
                                        except Exception as thumb_e:
                                            logger.debug(f"   ⚠️ 缩略图下载失败: {thumb_e}")
                                            thumb_path = None
                                        
                                        # 等待文件写入完成
                                        await asyncio.sleep(0.1)
                                        # 使用绝对路径确保文件路径正确
                                        abs_path = os.path.abspath(file_path)
                                        abs_thumb_path = os.path.abspath(thumb_path) if thumb_path else None
                                        from pyrogram.types import InputMediaVideo
                                        # 获取视频的宽度和高度（如果有）
                                        width = comment.video.width if hasattr(comment.video, 'width') else 0
                                        height = comment.video.height if hasattr(comment.video, 'height') else 0
                                        duration = comment.video.duration if hasattr(comment.video, 'duration') else 0
                                        media_list.append(InputMediaVideo(
                                            abs_path,
                                            width=width,
                                            height=height,
                                            duration=duration,
                                            supports_streaming=True,
                                            thumb=abs_thumb_path if abs_thumb_path else None
                                        ))
                                        downloaded_files.append(abs_path)
                                        if abs_thumb_path:
                                            downloaded_files.append(abs_thumb_path)
                                        successful_comments.append(comment)  # 保存成功下载的评论
                                    else:
                                        logger.warning(f"   ⚠️ 视频下载失败或文件无效")
                                        
                            except Exception as e:
                                logger.error(f"   ❌ 下载媒体 {idx} 失败: {e}")
                                continue
                        
                        if media_list:
                            # 检查媒体组完整性
                            if len(media_list) < len(group_comments) * 0.5:  # 如果成功下载的少于一半，跳过
                                logger.warning(f"   ⚠️ 媒体组不完整（{len(media_list)}/{len(group_comments)}），跳过")
                                failed_count += len(group_comments)
                                # 清理已下载的文件
                                for file_path in downloaded_files:
                                    try:
                                        if os.path.exists(file_path):
                                            os.remove(file_path)
                                    except:
                                        pass
                                continue
                            
                            logger.info(f"   📤 上传并发送媒体组（{len(media_list)} 个文件）...")
                            
                            # 发送前验证所有文件存在且有效
                            valid_files = []
                            invalid_files = []
                            for file_path in downloaded_files:
                                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                    # 转换为绝对路径
                                    abs_path = os.path.abspath(file_path)
                                    valid_files.append(abs_path)
                                else:
                                    invalid_files.append(file_path)
                            
                            if invalid_files:
                                logger.warning(f"   ⚠️ 发现 {len(invalid_files)} 个无效文件，将在发送前重建媒体组")
                                # 重建媒体组，只包含有效文件
                                valid_media_list = []
                                for idx, media_item in enumerate(media_list):
                                    if idx < len(downloaded_files) and downloaded_files[idx] in valid_files:
                                        valid_media_list.append(media_item)
                                media_list = valid_media_list
                                if not media_list:
                                    logger.error(f"   ❌ 没有有效的媒体文件，跳过此媒体组")
                                    failed_count += len(group_comments)
                                    # 清理文件
                                    for file_path in downloaded_files:
                                        try:
                                            if os.path.exists(file_path):
                                                os.remove(file_path)
                                        except:
                                            pass
                                    continue
                            
                            # 使用Bot API发送媒体组
                            send_success = False
                            max_retries = 3
                            bot_chat_id = send_to_chat_username if send_to_chat_username else send_to_chat_id
                            
                            for retry in range(max_retries):
                                try:
                                    logger.info(f"   📤 使用Bot API发送媒体组（尝试 {retry + 1}/{max_retries}）...")
                                    
                                    # 使用Bot API发送媒体组
                                    await self.client.send_media_group(
                                        chat_id=bot_chat_id,
                                        media=media_list,
                                        reply_to_message_id=reply_to_id if reply_to_id else None
                                    )
                                    success_count += len(media_list)
                                    logger.info(f"   ✅ 媒体组发送成功！（Bot API）")
                                    send_success = True
                                    break
                                except FloodWait as e:
                                    wait_time = e.value
                                    logger.warning(f"   ⚠️ 触发限流，需要等待 {wait_time} 秒")
                                    if retry < max_retries - 1:
                                        logger.info(f"   ⏳ 等待 {wait_time} 秒后重试 ({retry + 1}/{max_retries})...")
                                        await asyncio.sleep(wait_time)
                                    else:
                                        logger.error(f"   ❌ 已达最大重试次数，跳过此媒体组")
                                        failed_count += len(group_comments)
                                except Exception as e:
                                    logger.error(f"   ❌ Bot API 发送失败: {e}")
                                    if retry < max_retries - 1:
                                        logger.info(f"   ⏳ 等待 3 秒后重试 ({retry + 1}/{max_retries})...")
                                        await asyncio.sleep(3)
                                    else:
                                        logger.error(f"   ❌ 已达最大重试次数，跳过此媒体组")
                                        failed_count += len(group_comments)
                            else:
                                logger.warning(f"   ⚠️ 媒体组下载失败，跳过")
                                failed_count += len(group_comments)
                            
                            # 删除临时文件
                            if send_success:
                                for file_path in downloaded_files:
                                    try:
                                        if os.path.exists(file_path):
                                            os.remove(file_path)
                                    except Exception as e:
                                        logger.debug(f"清理文件失败: {e}")
                            
                            await asyncio.sleep(2.0)  # 增加延迟到2秒
                        
                    except Exception as e:
                        failed_count += len(group_comments)
                        logger.error(f"   ❌ 媒体组处理失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
            
            # 旧代码已禁用（保留用于参考）
            if False:  # 旧代码不再执行，已被上面的统一队列处理替代
                # 下面是旧代码（已禁用）
                pass
            
            if False and media_groups:  # 禁用旧的媒体组处理代码
                logger.info(f"")
                logger.info(f"{'='*60}")
                logger.info(f"📦 开始处理媒体组（共 {len(media_groups)} 组）")
                logger.info(f"{'='*60}")
                
                group_idx = 0
                for group_id, group_comments in media_groups.items():
                    group_idx += 1
                    try:
                        if task.should_stop():
                            logger.warning(f"⚠️ 任务已停止，中断媒体组处理")
                            break
                        
                        logger.info(f"")
                        logger.info(f"📦 处理第 {group_idx}/{len(media_groups)} 组 (ID: {str(group_id)[:8]}...)")
                        logger.info(f"   包含 {len(group_comments)} 个媒体文件")
                        
                        # 构建媒体组
                        media_list = []
                        downloaded_files = []  # 记录成功下载的文件，用于清理
                        
                        for idx, comment in enumerate(group_comments, 1):
                            try:
                                # 下载媒体
                                if comment.photo:
                                    logger.info(f"   📥 下载图片 {idx}/{len(group_comments)}: {comment.id}")
                                    file_path = await self.user_api_client.download_media(
                                        comment.photo.file_id,
                                        file_name=f"{temp_dir}/comment_{comment.id}.jpg"
                                    )
                                    
                                    # 验证文件是否成功下载
                                    if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info(f"   ✅ 图片下载完成: {os.path.getsize(file_path)} bytes")
                                        from pyrogram.types import InputMediaPhoto
                                        media_list.append(InputMediaPhoto(file_path))
                                        downloaded_files.append(file_path)
                                    else:
                                        logger.warning(f"   ⚠️ 图片下载失败或文件无效")
                                        
                                elif comment.video:
                                    logger.info(f"   📥 下载视频 {idx}/{len(group_comments)}: {comment.id}")
                                    file_path = await self.user_api_client.download_media(
                                        comment.video.file_id,
                                        file_name=f"{temp_dir}/comment_{comment.id}.mp4"
                                    )
                                    
                                    # 验证文件是否成功下载
                                    if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        logger.info(f"   ✅ 视频下载完成: {os.path.getsize(file_path)} bytes")
                                        from pyrogram.types import InputMediaVideo
                                        media_list.append(InputMediaVideo(file_path, supports_streaming=True))
                                        downloaded_files.append(file_path)
                                    else:
                                        logger.warning(f"   ⚠️ 视频下载失败或文件无效")
                                        
                            except Exception as e:
                                logger.error(f"   ❌ 下载媒体 {idx} 失败: {e}")
                                continue
                        
                        if media_list:
                            # 发送媒体组（使用 Bot API 发送）
                            logger.info(f"   📤 上传并发送媒体组（{len(media_list)} 个文件）...")
                            logger.info(f"   💡 使用 Bot API 发送（会显示机器人名字）")
                            await self.client.send_media_group(
                                chat_id=send_to_chat_id,
                                media=media_list,
                                reply_to_message_id=reply_to_id
                            )
                            success_count += len(media_list)
                            logger.info(f"   ✅ 媒体组发送成功！")
                            
                            # 删除临时文件
                            logger.info(f"   🧹 清理临时文件...")
                            for file_path in downloaded_files:
                                try:
                                    if os.path.exists(file_path):
                                        os.remove(file_path)
                                except Exception as e:
                                    logger.debug(f"清理文件失败: {e}")
                        else:
                            logger.warning(f"   ⚠️ 媒体组下载失败，跳过")
                            failed_count += len(group_comments)
                        
                        # 延迟，避免触发限制
                        await asyncio.sleep(1.0)
                        
                    except Exception as e:
                        failed_count += len(group_comments)
                        logger.error(f"   ❌ 媒体组处理失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
            # 8. 再发送单条媒体（旧代码，已禁用）
            if False and single_comments:  # 禁用旧的单条媒体处理代码
                logger.info(f"")
                logger.info(f"{'='*60}")
                logger.info(f"📄 开始处理单条媒体（共 {len(single_comments)} 条）")
                logger.info(f"{'='*60}")
                
                for idx, comment in enumerate(single_comments, 1):
                    try:
                        if task.should_stop():
                            logger.warning(f"⚠️ 任务已停止，中断单条媒体处理")
                            break
                        
                        logger.info(f"")
                        logger.info(f"📄 处理第 {idx}/{len(single_comments)} 条单媒体 (ID: {comment.id})")
                        
                        # 处理评论消息（应用过滤规则）
                        processed_result, should_process = self.message_engine.process_message(comment, config)
                        if not should_process or not processed_result:
                            logger.info(f"   ⚠️ 评论被过滤规则过滤，跳过")
                            continue
                        
                        text = processed_result.get('text', '') or processed_result.get('caption', '')
                        
                        if comment.photo:
                            logger.info(f"   📥 下载图片...")
                            photo_path = await self.user_api_client.download_media(
                                comment.photo.file_id,
                                file_name=f"{temp_dir}/comment_{comment.id}.jpg"
                            )
                            
                            # 验证文件
                            if photo_path and os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
                                logger.info(f"   ✅ 图片下载完成: {os.path.getsize(photo_path)} bytes")
                                logger.info(f"   📤 上传并发送图片（Bot API）...")
                                await self.client.send_photo(
                                    chat_id=send_to_chat_id,
                                    photo=photo_path,
                                    caption=text,
                                    reply_to_message_id=reply_to_id
                                )
                                logger.info(f"   ✅ 图片发送成功！")
                                try:
                                    os.remove(photo_path)
                                except:
                                    pass
                            else:
                                logger.warning(f"   ⚠️ 图片下载失败或文件无效，跳过")
                                failed_count += 1
                                continue
                        elif comment.video:
                            logger.info(f"   📥 下载视频...")
                            video_path = await self.user_api_client.download_media(
                                comment.video.file_id,
                                file_name=f"{temp_dir}/comment_{comment.id}.mp4"
                            )
                            
                            # 验证文件
                            if video_path and os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                                logger.info(f"   ✅ 视频下载完成: {os.path.getsize(video_path)} bytes")
                                logger.info(f"   📤 上传并发送视频（Bot API）...")
                                await self.client.send_video(
                                    chat_id=send_to_chat_id,
                                    video=video_path,
                                    caption=text,
                                    reply_to_message_id=reply_to_id
                                )
                                logger.info(f"   ✅ 视频发送成功！")
                                try:
                                    os.remove(video_path)
                                except:
                                    pass
                            else:
                                logger.warning(f"   ⚠️ 视频下载失败或文件无效，跳过")
                                failed_count += 1
                                continue
                        
                        success_count += 1
                        await asyncio.sleep(1.0)
                        
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"   ❌ 单条媒体处理失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
            # 最终统计
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"💬 评论区搬运完成！")
            logger.info(f"   ✅ 成功: {success_count} 条")
            logger.info(f"   ❌ 失败: {failed_count} 条")
            logger.info(f"   📊 成功率: {success_count/(success_count+failed_count)*100:.1f}%" if (success_count+failed_count) > 0 else "   📊 成功率: N/A")
            logger.info(f"{'='*60}")
            logger.info(f"🔧 [DEBUG] 最终统计详情:")
            logger.info(f"🔧 [DEBUG]     源频道ID: {source_message.chat.id}")
            logger.info(f"🔧 [DEBUG]     源消息ID: {source_message.id}")
            logger.info(f"🔧 [DEBUG]     获取到的评论总数: {len(comments)}")
            logger.info(f"🔧 [DEBUG]     媒体评论数: {len(media_comments)}")
            logger.info(f"🔧 [DEBUG]     媒体组数: {len(media_groups)}")
            logger.info(f"🔧 [DEBUG]     单条媒体数: {len(single_comments)}")
            logger.info(f"🔧 [DEBUG]     处理队列项目数: {len(processing_queue)}")
            logger.info(f"🔧 [DEBUG]     成功发送: {success_count}")
            logger.info(f"🔧 [DEBUG]     失败数量: {failed_count}")
            
        except Exception as e:
            logger.error(f"💬 评论区搬运失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

# ==================== 导出函数 ====================
def create_cloning_engine(client: Client, config: Dict[str, Any], data_manager=None, bot_id: str = "default_bot") -> CloningEngine:
    """创建搬运引擎实例"""
    return CloningEngine(client, config, data_manager, bot_id)

__all__ = [
    "CloneTask", "CloningEngine", "create_cloning_engine"
]

