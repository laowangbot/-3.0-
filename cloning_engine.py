# ==================== 搬运引擎 ====================
"""
搬运引擎
负责消息搬运的核心逻辑、进度监控、错误处理和断点续传
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
from task_state_manager import get_global_task_state_manager, TaskStatus

# 配置日志 - 使用优化的日志配置
from log_config import get_logger
logger = get_logger(__name__)

class CloneTask:
    """搬运任务类"""
    
    def __init__(self, task_id: str, source_chat_id: str, target_chat_id: str,
                 start_id: Optional[int] = None, end_id: Optional[int] = None,
                 config: Optional[Dict[str, Any]] = None, user_id: str = None):
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
        self.start_time = None
        self.end_time = None
        
        # 断点续传相关字段
        self.last_processed_message_id = None  # 最后处理的消息ID
        self.resume_from_id = None  # 恢复时的起始消息ID
        self.is_resumed = False  # 是否为恢复的任务
        
        # 取消标志
        self._cancelled = False  # 内部取消标志，用于立即停止任务
        
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
        self.status = "pending"

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
                    
                    # 评论搬运配置已移除
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
                    # 评论转发配置已移除
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
            task = CloneTask(task_id, validated_source_id, validated_target_id, start_id, end_id, config)
            
            # 添加超时保护的消息计数，增加重试机制
            logger.debug(f"📊 开始计算消息数量: {validated_source_id}")
            
            # 检查是否跳过消息数量计算（多任务优化）
            if config and config.get('skip_message_count', False):
                logger.info(f"🚀 跳过消息数量计算，使用快速估算: {start_id}-{end_id}")
                task.total_messages = int((end_id - start_id + 1) * 0.8)  # 快速估算
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
                    if source_chat:
                        validated_source_id = str(source_chat.id)
                        logger.info(f"通过用户名访问源频道成功: @{source_username} -> {validated_source_id} ({source_chat.type})")
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
                        if source_chat:
                            validated_source_id = str(source_chat.id)
                            logger.info(f"私密源频道验证成功: {actual_source_id} -> {validated_source_id} ({source_chat.type})")
                    else:
                        source_chat = await self.client.get_chat(actual_source_id)
                        if source_chat:
                            validated_source_id = str(source_chat.id)
                except Exception as e:
                    logger.error(f"通过ID访问源频道失败 {actual_source_id}: {e}")
                
                if not source_chat:
                    logger.error(f"源频道验证失败: {actual_source_id}")
                    return False, actual_source_id, actual_target_id
            
            logger.info(f"源频道验证成功: {actual_source_id} ({source_chat.type})")
            
            # 检查目标频道 - 优先使用用户名
            target_chat = None
            if target_username:
                try:
                    logger.info(f"优先通过用户名访问目标频道: @{target_username}")
                    target_chat = await self.client.get_chat(target_username)
                    if target_chat:
                        validated_target_id = str(target_chat.id)
                        logger.info(f"通过用户名访问目标频道成功: @{target_username} -> {validated_target_id} ({target_chat.type})")
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
                        if target_chat:
                            validated_target_id = str(target_chat.id)
                            logger.info(f"私密目标频道验证成功: {actual_target_id} -> {validated_target_id} ({target_chat.type})")
                    else:
                        target_chat = await self.client.get_chat(actual_target_id)
                        if target_chat:
                            validated_target_id = str(target_chat.id)
                except Exception as e:
                    logger.error(f"通过ID访问目标频道失败 {actual_target_id}: {e}")
                
                if not target_chat:
                    logger.error(f"目标频道验证失败: {actual_target_id}")
                    return False, actual_source_id, actual_target_id
            
            logger.info(f"目标频道验证成功: {actual_target_id} ({target_chat.type})")
            
            # 检查权限（使用验证成功的频道ID）
            if not await self._check_permissions(validated_source_id, validated_target_id):
                return False, actual_source_id, actual_target_id
            
            logger.info(f"频道验证完成: {actual_source_id} -> {actual_target_id}")
            logger.info(f"验证成功的频道ID: {validated_source_id} -> {validated_target_id}")
            return True, validated_source_id, validated_target_id
            
        except Exception as e:
            logger.error(f"频道验证失败: {e}")
            return False, source_chat_id, target_chat_id
    
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
                        if not member.can_read_messages:
                            logger.warning(f"没有读取源频道的权限: {source_chat_id}, 但尝试继续")
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
                        if not member.can_post_messages:
                            logger.error(f"没有发送到目标频道的权限: {target_chat_id}")
                            return False
                    except Exception as e:
                        logger.warning(f"无法获取目标频道成员信息: {e}, 但尝试继续")
                        # 对于公开频道，即使无法获取成员信息也可能可以发送
                else:
                    logger.warning(f"未知的目标频道类型: {target_chat.type}")
            except Exception as e:
                logger.warning(f"无法获取目标频道信息: {e}, 但尝试继续")
                # 对于某些频道，即使无法获取信息也可能可以访问
            
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
            if start_id and end_id:
                # 指定范围的消息，精确计算
                return end_id - start_id + 1
            else:
                # 从最近消息开始，尝试获取实际消息数量
                try:
                    # 获取最近的一些消息来估算，添加重试机制
                    retry_count = 0
                    max_retries = 3
                    while retry_count < max_retries:
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
                    logger.warning(f"无法获取最近消息: {e}")
                    # 回退到频道成员数估算
                    try:
                        chat = await self.client.get_chat(chat_id)
                        if hasattr(chat, 'members_count'):
                            return min(chat.members_count * 5, 5000)
                        else:
                            return 1000
                    except Exception as chat_error:
                        logger.warning(f"无法获取频道信息: {chat_error}")
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
            
            # 从活动任务中移除
            if task.task_id in self.active_tasks:
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
                # 先计算实际存在的消息数量
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
            processed_result, should_skip = self.message_engine.process_media_group(messages, effective_config)
            
            if should_skip:
                logger.info(f"媒体组被过滤: {messages[0].media_group_id}")
                return True
            
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
            success = await self._send_media_group(task, messages, processed_result)
            
            # 评论转发功能已移除
            
            if success:
                logger.debug(f"媒体组发送成功: {messages[0].media_group_id}")
            else:
                logger.error(f"媒体组发送失败: {messages[0].media_group_id}")
            
            return success
            
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
            processed_result, should_skip = self.message_engine.process_message(message, effective_config)
            
            if should_skip:
                task.stats['filtered_messages'] += 1
                logger.info(f"消息被过滤: {message.id}")
                return True
            
            if not processed_result:
                logger.warning(f"消息处理结果为空: {message.id}")
                # 如果消息被完全过滤，标记为已处理但跳过
                task.stats['filtered_messages'] += 1
                logger.info(f"消息内容被完全过滤，跳过: {message.id}")
                return True
            
            # 检查处理结果是否有效
            if isinstance(processed_result, dict):
                # 对于媒体消息，即使文本为空也应该被认为是有效内容
                has_content = (
                    processed_result.get('text', '').strip() or 
                    processed_result.get('caption', '').strip() or 
                    processed_result.get('media', False) or
                    message.media  # 原始消息包含媒体内容
                )
                if not has_content:
                    logger.warning(f"消息处理结果无有效内容: {message.id}")
                    task.stats['filtered_messages'] += 1
                    logger.info(f"消息内容被完全过滤，跳过: {message.id}")
                    return True
            
            # 发送处理后的消息
            success = await self._send_processed_message(task, message, processed_result)
            
            # 评论转发功能已移除
            
            if success:
                logger.debug(f"消息发送成功: {message.id}")
            else:
                logger.error(f"消息发送失败: {message.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"处理单条消息失败: {e}")
            return False
    
    async def _send_processed_message(self, task: CloneTask, original_message: Message, 
                                    processed_result: Dict[str, Any]) -> bool:
        """发送处理后的消息"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送处理后的消息")
                return False
            
            message_id = original_message.id
            message_type = "媒体消息" if original_message.media else "文本消息"
            
            logger.info(f"📤 发送 {message_type} {message_id}")
            
            # 重试机制
            for attempt in range(self.retry_attempts):
                try:
                    if original_message.media:
                        # 媒体消息
                        success = await self._send_media_message(task, original_message, processed_result)
                    else:
                        # 文本消息
                        success = await self._send_text_message(task, processed_result)
                    
                    if success:
                        logger.info(f"✅ {message_type} {message_id} 发送成功")
                        return True
                    
                except Exception as e:
                    logger.warning(f"⚠️ 发送 {message_type} {message_id} 失败 (尝试 {attempt + 1}/{self.retry_attempts}): {e}")
                    
                    if attempt < self.retry_attempts - 1:
                        logger.debug(f"⏳ 等待 {self.retry_delay} 秒后重试...")
                        await asyncio.sleep(self.retry_delay)
            
            logger.error(f"❌ {message_type} {message_id} 发送失败，已达到最大重试次数")
            return False
            
        except Exception as e:
            logger.error(f"❌ 发送处理后的消息失败: {e}")
            return False
    
    async def _send_text_message(self, task: CloneTask, processed_result: Dict[str, Any]) -> bool:
        """发送文本消息"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送文本消息")
                return False
            
            text = processed_result.get('text', '')
            buttons = processed_result.get('buttons')
            
            if not text and not buttons:
                logger.debug("📝 跳过空文本消息")
                return True  # 空消息，跳过
            
            # 显示文本内容摘要
            text_preview = text[:50] + "..." if len(text) > 50 else text
            logger.debug(f"📝 发送文本: {text_preview}")
            
            await self.client.send_message(
                chat_id=task.target_chat_id,
                text=text or " ",  # 空文本用空格代替
                reply_markup=buttons
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送文本消息失败: {e}")
            return False
    
    async def _send_media_group(self, task: CloneTask, messages: List[Message], 
                               processed_result: Dict[str, Any]) -> bool:
        """发送媒体组消息"""
        try:
            if not messages:
                return False
            
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体组")
                return False
            
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
                    logger.debug(f"🔍 处理媒体组消息 {i+1}/{len(messages)}: ID={message.id}")
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
                        logger.warning(f"   ⚠️ 消息 {message.id} 不是媒体类型")
                        logger.debug(f"  • 详细信息: photo={message.photo}, video={message.video}, document={message.document}")
                        if message.document:
                            logger.debug(f"  • 文档MIME类型: {message.document.mime_type}")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ 处理媒体组消息失败 {message.id}: {e}")
                    logger.debug(f"  • 错误类型: {type(e).__name__}")
                    logger.debug(f"  • 错误详情: {str(e)}")
                    continue
            
            if not media_list:
                logger.warning(f"❌ 媒体组 {media_group_id} 没有有效的媒体内容")
                return False
            
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
                return False
            
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
                    break
                    
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ 媒体组 {media_group_id} 发送超时 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    else:
                        logger.error(f"❌ 媒体组 {media_group_id} 发送失败，已达到最大重试次数")
                        return False
                        
                except FloodWait as flood_error:
                    # 解析等待时间
                    wait_time = int(str(flood_error).split('A wait of ')[1].split(' seconds')[0])
                    logger.warning(f"⚠️ 遇到FloodWait限制，需要等待 {wait_time} 秒")
                    
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"⚠️ 任务 {task.task_id} 在FloodWait等待期间被{task.status}，停止处理")
                        return False
                    
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
                        await self.client.send_media_group(
                            chat_id=task.target_chat_id,
                            media=media_list
                        )
                        logger.info(f"✅ 媒体组 {media_group_id} 重试发送成功")
                        break
                    except Exception as retry_error:
                        logger.error(f"❌ 重试发送失败: {retry_error}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return False
                            
                except Exception as send_error:
                    logger.error(f"❌ 发送媒体组 {media_group_id} 失败 (尝试 {attempt + 1}/{max_retries}): {send_error}")
                    if attempt < max_retries - 1:
                        logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error(f"❌ 媒体组 {media_group_id} 发送失败，已达到最大重试次数")
                        return False
            
            # 如果有按钮，单独发送
            if buttons:
                logger.debug(f"🔘 发送媒体组 {media_group_id} 的附加按钮")
                await self.client.send_message(
                    chat_id=task.target_chat_id,
                    text="📎 媒体组附加按钮",
                    reply_markup=buttons
                )
                logger.debug(f"✅ 媒体组 {media_group_id} 按钮发送成功")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送媒体组 {media_group_id} 失败: {e}")
            return False
    
    async def _send_media_message(self, task: CloneTask, original_message: Message, 
                                 processed_result: Dict[str, Any]) -> bool:
        """发送媒体消息"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体消息")
                return False
            
            message_id = original_message.id
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
                            return True
                            
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
                            return True
                            
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
                            return True
                            
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
                                return True
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
                                return True
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"⚠️ {media_type} {message_id} 发送超时 (尝试 {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error(f"❌ {media_type} {message_id} 发送失败，已达到最大重试次数")
                            return False
                            
                    except Exception as send_error:
                        logger.error(f"❌ 发送 {media_type} {message_id} 失败 (尝试 {attempt + 1}/{max_retries}): {send_error}")
                        if attempt < max_retries - 1:
                            logger.debug(f"⏳ 等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            logger.error(f"❌ {media_type} {message_id} 发送失败，已达到最大重试次数")
                            return False
                
            except FloodWait as flood_error:
                # 解析等待时间
                wait_time = int(str(flood_error).split('A wait of ')[1].split(' seconds')[0])
                logger.warning(f"⚠️ 遇到FloodWait限制，需要等待 {wait_time} 秒")
                
                # 检查任务状态
                if task.should_stop():
                    logger.info(f"⚠️ 任务 {task.task_id} 在FloodWait等待期间被{task.status}，停止处理")
                    return False
                
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
                    return True
                    
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
            return False
    
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
            return True
        
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
                logger.warning(f"任务 {task_id} 不存在")
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
            
            # 按媒体组分组处理消息
            media_groups = {}
            standalone_messages = []
            
            logger.debug(f"🔍 开始分析消息类型...")
            for i, message in enumerate(messages):
                try:
                    logger.debug(f"🔍 分析消息 {i+1}/{len(messages)}: ID={message.id}")
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
            
            # 处理媒体组 - 安全顺序处理（确保媒体组完整性）
            logger.info(f"🔄 开始顺序处理 {len(media_groups)} 个媒体组...")
            
            # 按媒体组ID排序，确保处理顺序
            sorted_media_groups = sorted(media_groups.items(), key=lambda x: x[0])
            
            for media_group_index, (media_group_id, group_messages) in enumerate(sorted_media_groups):
                try:
                    logger.info(f"📱 处理媒体组 {media_group_index + 1}/{len(media_groups)}: {media_group_id}")
                    logger.info(f"🔍 媒体组详情:")
                    logger.info(f"  • 媒体组ID: {media_group_id}")
                    logger.info(f"  • 消息数量: {len(group_messages)}")
                    logger.info(f"  • 任务状态: {task.status}")
                    logger.info(f"  • 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"⚠️ 任务 {task.task_id} 已被{task.status}，停止处理")
                        return False
                    
                    # 检查超时
                    elapsed_time = time.time() - task_start_time
                    if elapsed_time > max_execution_time:
                        logger.warning(f"⚠️ 任务执行超时（{elapsed_time:.1f}秒 > {max_execution_time}秒），停止处理")
                        return False
                    
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
                        # 确保进度不超过100%
                        task.progress = min((task.processed_messages / task.total_messages) * 100.0, 100.0)
                    else:
                        # 如果没有总消息数，使用已处理消息数作为进度
                        task.progress = min(task.processed_messages * 10, 100.0)
                    
                    logger.debug(f"📊 任务进度更新:")
                    logger.info(f"  • 已处理消息: {task.processed_messages}")
                    logger.info(f"  • 总消息数: {task.total_messages}")
                    # 确保进度不超过100%
                    if task.progress > 100.0:
                        task.progress = 100.0
                    logger.info(f"  • 进度百分比: {task.progress:.1f}%")
                    
                    # 调用进度回调
                    if self.progress_callback:
                        await self.progress_callback(task)
                    
                    # 媒体组间安全延迟（确保媒体组完整性）
                    media_group_delay = self.media_group_delay
                    logger.debug(f"⏳ 媒体组处理完成，等待 {media_group_delay} 秒...")
                    await asyncio.sleep(media_group_delay)
                    
                except Exception as e:
                    logger.error(f"❌ 处理媒体组失败 {media_group_id}: {e}")
                    logger.error(f"  • 错误类型: {type(e).__name__}")
                    logger.error(f"  • 错误详情: {str(e)}")
                    task.stats['failed_messages'] += len(group_messages)
                    task.failed_messages += len(group_messages)
            
            # 处理独立消息
            for message in standalone_messages:
                try:
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 已被{task.status}，停止处理")
                        return False
                    
                    # 检查超时
                    if time.time() - task_start_time > max_execution_time:
                        logger.warning(f"任务执行超时（{max_execution_time}秒），停止处理")
                        return False
                    
                    success = await self._process_single_message(task, message)
                    
                    if success:
                        task.stats['processed_messages'] += 1
                        task.processed_messages += 1
                        # 保存进度
                        task.save_progress(message.id)
                        logger.info(f"✅ 独立消息 {message.id} 处理成功")
                    else:
                        task.stats['failed_messages'] += 1
                        task.failed_messages += 1
                        logger.error(f"❌ 独立消息 {message.id} 处理失败")
                    
                    # 更新进度百分比
                    if hasattr(task, 'total_messages') and task.total_messages > 0:
                        # 确保进度不超过100%
                        task.progress = min((task.processed_messages / task.total_messages) * 100.0, 100.0)
                    else:
                        # 如果没有总消息数，使用已处理消息数作为进度
                        task.progress = min(task.processed_messages * 10, 100.0)
                    
                    # 调用进度回调
                    if self.progress_callback:
                        await self.progress_callback(task)
                    
                    # 应用安全延迟（避免规律性操作）
                    await self._apply_safe_delay()
                    
                except Exception as e:
                    logger.error(f"处理消息失败: {e}")
                    task.stats['failed_messages'] += 1
                    task.failed_messages += 1
            
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

# ==================== 导出函数 ====================
def create_cloning_engine(client: Client, config: Dict[str, Any], data_manager=None, bot_id: str = "default_bot") -> CloningEngine:
    """创建搬运引擎实例"""
    return CloningEngine(client, config, data_manager, bot_id)

__all__ = [
    "CloneTask", "CloningEngine", "create_cloning_engine"
]

