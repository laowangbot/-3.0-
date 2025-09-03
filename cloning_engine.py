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

# 配置日志 - 显示详细状态信息
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CloneTask:
    """搬运任务类"""
    
    def __init__(self, task_id: str, source_chat_id: str, target_chat_id: str,
                 start_id: Optional[int] = None, end_id: Optional[int] = None,
                 config: Optional[Dict[str, Any]] = None):
        """初始化搬运任务"""
        self.task_id = task_id
        self.source_chat_id = source_chat_id
        self.target_chat_id = target_chat_id
        self.start_id = start_id
        self.end_id = end_id
        self.config = config or {}
        
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
        return self.status in ["cancelled", "paused"]
    
    def save_progress(self, message_id: int):
        """保存当前进度"""
        self.last_processed_message_id = message_id
        self.current_message_id = message_id
    
    def prepare_for_resume(self, from_message_id: int):
        """准备断点续传"""
        self.resume_from_id = from_message_id
        self.is_resumed = True
        self.status = "pending"

class CloningEngine:
    """搬运引擎类"""
    
    def __init__(self, client: Client, config: Dict[str, Any], data_manager=None):
        """初始化搬运引擎"""
        self.client = client
        self.config = config
        self.data_manager = data_manager
        self.message_engine = MessageEngine(config)
        self.active_tasks: Dict[str, CloneTask] = {}
        self.task_history: List[Dict[str, Any]] = []
        
        # 性能设置
        self.message_delay = config.get('message_delay', 0.3)  # 减少延迟到0.3秒
        self.batch_size = config.get('batch_size', 100)  # 批次大小改为100
        self.retry_attempts = config.get('retry_attempts', 3)
        self.retry_delay = config.get('retry_delay', 1.5)  # 减少重试延迟到1.5秒
        self.max_concurrent_tasks = config.get('max_concurrent_tasks', 20)  # 支持最多20个并发任务
        self.max_concurrent_channels = config.get('max_concurrent_channels', 3)  # 每个任务最多3个频道组并发启动
        
        # 进度回调
        self.progress_callback: Optional[Callable] = None
    
    async def get_effective_config_for_pair(self, user_id: str, pair_id: str) -> Dict[str, Any]:
        """获取频道组的有效配置（优先使用独立配置，否则使用全局配置）"""
        try:
            # 获取用户配置
            if self.data_manager:
                user_config = await self.data_manager.get_user_config(user_id)
            else:
                user_config = await get_user_config(user_id)
            
            # 检查是否有频道组独立过滤配置
            channel_filters = user_config.get('channel_filters', {}).get(pair_id, {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            # 添加详细的调试信息
            logger.info(f"频道组 {pair_id} 配置检查:")
            logger.info(f"  • 用户配置中的channel_filters: {list(user_config.get('channel_filters', {}).keys())}")
            logger.info(f"  • 当前频道组配置: {channel_filters}")
            logger.info(f"  • independent_enabled: {independent_enabled}")
            logger.info(f"  • 全局tail_text: '{user_config.get('tail_text', '')}'")
            logger.info(f"  • 频道组tail_text: '{channel_filters.get('tail_text', '')}'")
            logger.info(f"  • 频道组tail_frequency: {channel_filters.get('tail_frequency', 'not_set')}")
            logger.info(f"  • 频道组tail_position: {channel_filters.get('tail_position', 'not_set')}")
            
            if independent_enabled:
                # 使用频道组独立配置
                logger.info(f"频道组 {pair_id} 使用独立过滤配置")
                logger.info(f"频道组 {pair_id} 原始配置: {channel_filters}")
                effective_config = {
                    # 关键字过滤 - 只有在启用时才设置
                    'filter_keywords': channel_filters.get('keywords', []) if channel_filters.get('keywords_enabled', False) else [],
                    
                    # 敏感词替换 - 只有在启用时才设置
                    'replacement_words': channel_filters.get('replacements', {}) if channel_filters.get('replacements_enabled', False) else {},
                    
                    # 内容移除
                    'content_removal': channel_filters.get('content_removal', False),
                    'content_removal_mode': channel_filters.get('content_removal_mode', 'text_only'),
                    
                    # 链接移除
                    'remove_links': channel_filters.get('links_removal', False),
                    'remove_magnet_links': channel_filters.get('links_removal', False),
                    'remove_all_links': channel_filters.get('links_removal', False),
                    'remove_links_mode': channel_filters.get('links_removal_mode', 'links_only'),
                    
                    # 用户名移除
                    'remove_usernames': channel_filters.get('usernames_removal', False),
                    
                    # 按钮移除
                    'filter_buttons': channel_filters.get('buttons_removal', False),
                    'button_filter_mode': channel_filters.get('buttons_removal_mode', 'remove_all'),
                    
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
                
                # 添加调试信息
                logger.info(f"频道组 {pair_id} 映射后的配置:")
                logger.info(f"  • filter_keywords: {effective_config['filter_keywords']}")
                logger.info(f"  • content_removal: {effective_config['content_removal']}")
                logger.info(f"  • remove_links: {effective_config['remove_links']}")
                logger.info(f"  • remove_usernames: {effective_config['remove_usernames']}")
                logger.info(f"  • filter_buttons: {effective_config['filter_buttons']}")
                logger.info(f"  • tail_text: '{effective_config['tail_text']}'")
                logger.info(f"  • tail_frequency: {effective_config['tail_frequency']}")
                logger.info(f"  • tail_position: {effective_config['tail_position']}")
                logger.info(f"  • additional_buttons: {effective_config['additional_buttons']}")
                
                # 添加原始频道组配置调试
                logger.info(f"频道组 {pair_id} 原始配置:")
                logger.info(f"  • channel_filters: {channel_filters}")
                logger.info(f"  • 是否使用频道组配置: {pair_id in user_config.get('channel_filters', {})}")
            else:
                # 使用全局配置
                logger.info(f"频道组 {pair_id} 使用全局过滤配置")
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
                       'remove_magnet_links', 'remove_all_links', 'remove_usernames', 'filter_buttons']:
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
                         source_username: str = "", target_username: str = "") -> CloneTask:
        """创建新的搬运任务"""
        task_id = f"clone_{int(time.time())}_{len(self.active_tasks)}"
        
        try:
            # 添加超时保护的频道验证
            logger.info(f"🔍 开始验证频道: {source_chat_id} -> {target_chat_id}")
            validation_result = await asyncio.wait_for(
                self._validate_channels(source_chat_id, target_chat_id, source_username, target_username),
                timeout=30.0  # 30秒超时
            )
            is_valid, validated_source_id, validated_target_id = validation_result
            if not is_valid:
                raise ValueError("频道验证失败")
            logger.info(f"✅ 频道验证成功: {source_chat_id} -> {target_chat_id}")
            logger.info(f"✅ 使用验证后的频道ID: {validated_source_id} -> {validated_target_id}")
            
            # 使用验证成功的频道ID创建任务
            task = CloneTask(task_id, validated_source_id, validated_target_id, start_id, end_id, config)
            
            # 添加超时保护的消息计数
            logger.info(f"📊 开始计算消息数量: {validated_source_id}")
            task.total_messages = await asyncio.wait_for(
                self._count_messages(validated_source_id, start_id, end_id),
                timeout=15.0  # 15秒超时
            )
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
        """批量创建多个搬运任务"""
        created_tasks = []
        
        for i, task_config in enumerate(tasks_config):
            try:
                # 检查并发限制
                if len(self.active_tasks) >= self.max_concurrent_tasks:
                    logger.warning(f"达到最大并发任务数限制: {self.max_concurrent_tasks}")
                    break
                
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
                    logger.info(f"批量任务 {i+1}/{len(tasks_config)} 创建成功: {task.task_id}")
                else:
                    logger.error(f"批量任务 {i+1}/{len(tasks_config)} 创建失败")
                    
            except Exception as e:
                logger.error(f"批量任务 {i+1}/{len(tasks_config)} 创建异常: {e}")
                continue
        
        logger.info(f"批量创建任务完成: {len(created_tasks)}/{len(tasks_config)} 成功")
        return created_tasks
    
    async def _validate_channels(self, source_chat_id: str, target_chat_id: str, 
                                source_username: str = "", target_username: str = "") -> tuple[bool, str, str]:
        """验证频道是否有效，支持通过用户名访问公开频道
        返回: (验证结果, 实际源频道ID, 实际目标频道ID)
        """
        try:
            # 处理PENDING格式的频道ID
            actual_source_id = self._resolve_pending_channel_id(source_chat_id)
            actual_target_id = self._resolve_pending_channel_id(target_chat_id)
            
            # 用于存储验证成功的实际频道ID
            validated_source_id = actual_source_id
            validated_target_id = actual_target_id
            
            # 检查源频道
            source_chat = None
            try:
                # 如果是私密频道格式（@c/数字 或 -100数字），尝试多种前缀
                if actual_source_id.startswith('@c/') or actual_source_id.startswith('-100'):
                    source_chat = await self._try_private_channel_access(actual_source_id)
                    if source_chat:
                        # 记录验证成功的实际频道ID
                        validated_source_id = str(source_chat.id)
                        logger.info(f"私密源频道验证成功: {actual_source_id} -> {validated_source_id} ({source_chat.type})")
                    else:
                        # 如果多种前缀都失败，抛出异常进入用户名尝试逻辑
                        raise Exception(f"所有前缀格式都无法访问私密频道: {actual_source_id}")
                else:
                    source_chat = await self.client.get_chat(actual_source_id)
                    if source_chat:
                        validated_source_id = str(source_chat.id)
                
                if not source_chat:
                    logger.error(f"源频道不存在: {actual_source_id}")
                    return False, actual_source_id, actual_target_id
                logger.info(f"源频道验证成功: {actual_source_id} ({source_chat.type})")
            except Exception as e:
                logger.warning(f"通过ID访问源频道失败 {actual_source_id}: {e}")
                # 如果有用户名，尝试通过用户名访问
                if source_username:
                    try:
                        logger.info(f"尝试通过用户名访问源频道: @{source_username}")
                        source_chat = await self.client.get_chat(source_username)
                        if source_chat:
                            validated_source_id = str(source_chat.id)
                            logger.info(f"通过用户名访问源频道成功: @{source_username} -> {validated_source_id} ({source_chat.type})")
                        else:
                            logger.error(f"通过用户名访问源频道失败: @{source_username}")
                            return False, actual_source_id, actual_target_id
                    except Exception as username_error:
                        logger.error(f"通过用户名访问源频道失败 @{source_username}: {username_error}")
                        return False, actual_source_id, actual_target_id
                else:
                    logger.error(f"无法访问源频道且没有用户名信息: {actual_source_id}")
                    return False, actual_source_id, actual_target_id
            
            # 检查目标频道
            target_chat = None
            try:
                # 如果是私密频道格式（@c/数字 或 -100数字），尝试多种前缀
                if actual_target_id.startswith('@c/') or actual_target_id.startswith('-100'):
                    target_chat = await self._try_private_channel_access(actual_target_id)
                    if target_chat:
                        # 记录验证成功的实际频道ID
                        validated_target_id = str(target_chat.id)
                        logger.info(f"私密目标频道验证成功: {actual_target_id} -> {validated_target_id} ({target_chat.type})")
                    else:
                        # 如果多种前缀都失败，抛出异常进入用户名尝试逻辑
                        raise Exception(f"所有前缀格式都无法访问私密频道: {actual_target_id}")
                else:
                    target_chat = await self.client.get_chat(actual_target_id)
                    if target_chat:
                        validated_target_id = str(target_chat.id)
                
                if not target_chat:
                    logger.error(f"目标频道不存在: {actual_target_id}")
                    return False, actual_source_id, actual_target_id
                logger.info(f"目标频道验证成功: {actual_target_id} ({target_chat.type})")
            except Exception as e:
                logger.warning(f"通过ID访问目标频道失败 {actual_target_id}: {e}")
                # 如果有用户名，尝试通过用户名访问
                if target_username:
                    try:
                        logger.info(f"尝试通过用户名访问目标频道: @{target_username}")
                        target_chat = await self.client.get_chat(target_username)
                        if target_chat:
                            validated_target_id = str(target_chat.id)
                            logger.info(f"通过用户名访问目标频道成功: @{target_username} -> {validated_target_id} ({target_chat.type})")
                        else:
                            logger.error(f"通过用户名访问目标频道失败: @{target_username}")
                            return False, actual_source_id, actual_target_id
                    except Exception as username_error:
                        logger.error(f"通过用户名访问目标频道失败 @{target_username}: {username_error}")
                        return False, actual_source_id, actual_target_id
                else:
                    logger.error(f"无法访问目标频道且没有用户名信息: {actual_target_id}")
                    return False, actual_source_id, actual_target_id
            
            # 检查权限（使用验证成功的频道ID）
            if not await self._check_permissions(validated_source_id, validated_target_id):
                return False, actual_source_id, actual_target_id
            
            logger.info(f"频道验证完成: {actual_source_id} -> {actual_target_id}")
            logger.info(f"验证成功的频道ID: {validated_source_id} -> {validated_target_id}")
            return True, validated_source_id, validated_target_id
            
        except Exception as e:
            logger.error(f"频道验证失败: {e}")
            return False, source_chat_id, target_chat_id
    
    def _resolve_pending_channel_id(self, channel_id: str) -> str:
        """解析PENDING格式的频道ID，转换为实际可用的频道ID"""
        if not isinstance(channel_id, str) or not channel_id.startswith('PENDING_'):
            return channel_id
        
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
                    # 获取最近的一些消息来估算
                    recent_messages = await self.client.get_messages(chat_id, 500)
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
        if task.status != "pending":
            logger.warning(f"任务状态不正确: {task.status}")
            return False
        
        # 检查总并发任务数限制
        if len(self.active_tasks) >= self.max_concurrent_tasks:
            logger.warning(f"达到最大并发任务数限制: {self.max_concurrent_tasks}")
            return False
        
        # 检查用户并发任务数限制（支持动态配置）
        user_id = task.config.get('user_id') if task.config else None
        if user_id:
            # 从用户配置读取并发限制，默认20个
            try:
                user_config = await get_user_config(user_id)
                max_user_concurrent = user_config.get('max_user_concurrent_tasks', 20)
            except:
                max_user_concurrent = 20  # 默认支持20个并发任务
            
            user_active_tasks = [t for t in self.active_tasks.values() if t.config.get('user_id') == user_id]
            if len(user_active_tasks) >= max_user_concurrent:
                logger.warning(f"用户 {user_id} 已达到最大并发任务数限制: {max_user_concurrent}")
                return False
        
        try:
            # 将任务添加到活动任务列表
            self.active_tasks[task.task_id] = task
            
            task.status = "running"
            task.start_time = datetime.now()
            
            logger.info(f"开始搬运任务: {task.task_id}")
            
            # 异步启动搬运任务，不等待完成
            asyncio.create_task(self._execute_cloning_background(task))
            
            logger.info(f"搬运任务已启动: {task.task_id}")
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
        """批量启动多个搬运任务"""
        results = {}
        
        for i, task in enumerate(tasks):
            try:
                logger.info(f"启动批量任务 {i+1}/{len(tasks)}: {task.task_id}")
                success = await self.start_cloning(task)
                results[task.task_id] = success
                
                if success:
                    logger.info(f"✅ 批量任务 {i+1}/{len(tasks)} 启动成功")
                else:
                    logger.error(f"❌ 批量任务 {i+1}/{len(tasks)} 启动失败")
                
                # 添加小延迟避免同时启动过多任务
                if i < len(tasks) - 1:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"批量任务 {i+1}/{len(tasks)} 启动异常: {e}")
                results[task.task_id] = False
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"批量启动完成: {success_count}/{len(tasks)} 成功")
        return results
    
    async def _execute_cloning_background(self, task: CloneTask):
        """后台执行搬运任务"""
        try:
            logger.info(f"🚀 开始后台执行搬运任务: {task.task_id}")
            
            # 执行搬运
            success = await self._execute_cloning(task)
            
            if success:
                task.status = "completed"
                task.progress = 100.0
                task.processed_messages = task.stats['processed_messages']
                logger.info(f"✅ 搬运任务完成: {task.task_id}")
            else:
                task.status = "failed"
                logger.error(f"❌ 搬运任务失败: {task.task_id}")
            
            task.end_time = datetime.now()
            
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
            
            logger.info(f"搬运任务结束: {task.task_id}, 状态: {task.status}")
            
        except Exception as e:
            logger.error(f"后台执行搬运任务失败: {e}")
            task.status = "failed"
            task.end_time = datetime.now()
    
    async def _execute_cloning(self, task: CloneTask) -> bool:
        """执行搬运逻辑（改为流式处理，支持断点续传）"""
        try:
            # 添加超时保护
            task_start_time = time.time()
            # 保持start_time为datetime类型，用于UI显示
            if not task.start_time:
                task.start_time = datetime.now()
            # 从配置中获取超时时间，如果没有配置则使用默认值
            max_execution_time = task.config.get('task_timeout', 7200)  # 默认1小时
            
            # 检查是否为断点续传
            if task.is_resumed and task.resume_from_id:
                logger.info(f"🔄 断点续传任务，从消息ID {task.resume_from_id} 开始")
                # 调整起始ID为断点续传位置
                actual_start_id = task.resume_from_id
            else:
                logger.info(f"🚀 开始新的流式搬运任务")
                actual_start_id = task.start_id
            
            # 获取第一批消息（100条）
            first_batch = await self._get_first_batch(task.source_chat_id, actual_start_id, task.end_id)
            
            if not first_batch:
                logger.info("没有找到需要搬运的消息")
                return True
            
            # 计算总消息数
            if actual_start_id and task.end_id:
                task.total_messages = task.end_id - actual_start_id + 1
            else:
                task.total_messages = len(first_batch)
            
            logger.info(f"📊 第一批获取完成，共 {len(first_batch)} 条消息，预计总消息数: {task.total_messages}")
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
                return True
            
            logger.info(f"🔄 开始流式处理剩余消息: {remaining_start} - {end_id}")
            
            # 流式处理：边获取边搬运，支持预取和动态批次调整
            batch_size = 500  # 初始批次大小
            min_batch_size = 200  # 最小批次大小
            max_batch_size = 1000  # 最大批次大小
            current_id = remaining_start
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
                        logger.info(f"批次 {current_id}-{batch_end} 没有有效消息，跳过")
                        current_id = batch_end + 1
                        continue
                    
                    # 检查媒体组完整性
                    last_message = valid_messages[-1]
                    if last_message.media_group_id:
                        extended_batch_end = await self._extend_batch_to_complete_media_group(
                            task.source_chat_id, batch_end, end_id
                        )
                        
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
                    current_id += batch_size
                    continue
            
            logger.info(f"🎉 流式处理完成，共处理 {processed_batches} 个批次")
            return True
            
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
                        batch_messages = await self.client.get_messages(
                            chat_id, 
                            message_ids=list(range(current_id, batch_end + 1))
                        )
                        
                        # 过滤掉None值（不存在的消息）
                        valid_messages = [msg for msg in batch_messages if msg is not None]
                        
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
                        
                        # 使用配置中的消息延迟设置
                        message_delay = task.config.get('message_delay', 0.05) if hasattr(task, 'config') and task.config else 0.05
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
                            logger.info(f"📊 消息ID范围: {min_id} - {max_id}")
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
            
            # 获取频道组配置
            user_id = task.config.get('user_id')
            pair_id = task.config.get('pair_id')
            pair_index = task.config.get('pair_index', 'unknown')  # 保留用于日志显示，添加默认值
            
            if user_id and pair_id:
                # 获取频道组有效配置
                effective_config = await self.get_effective_config_for_pair(user_id, pair_id)
                logger.debug(f"媒体组使用频道组 {pair_id} (索引{pair_index}) 的过滤配置")
            else:
                # 使用默认配置
                effective_config = self.config
                logger.debug("媒体组使用默认过滤配置")
            
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
                # 使用默认配置
                effective_config = self.config
                logger.debug("使用默认过滤配置")
            
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
                has_content = (
                    processed_result.get('text', '').strip() or 
                    processed_result.get('caption', '').strip() or 
                    processed_result.get('media', False)
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
                        logger.info(f"⏳ 等待 {self.retry_delay} 秒后重试...")
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
            media_list = []
            caption = processed_result.get('caption', '')
            buttons = processed_result.get('buttons')
            
            # 统计媒体类型
            photo_count = 0
            video_count = 0
            document_count = 0
            
            for i, message in enumerate(messages):
                try:
                    if message.photo:
                        # 图片
                        media_item = InputMediaPhoto(
                            media=message.photo.file_id,
                            caption=caption if i == 0 else None  # 只在第一个媒体上添加caption
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        logger.debug(f"   📷 添加照片 {i+1}/{len(messages)}")
                        
                    elif message.video:
                        # 视频
                        media_item = InputMediaVideo(
                            media=message.video.file_id,
                            caption=caption if i == 0 else None  # 只在第一个媒体上添加caption
                        )
                        media_list.append(media_item)
                        video_count += 1
                        logger.debug(f"   🎥 添加视频 {i+1}/{len(messages)}")
                        
                    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
                        # 文档视频
                        media_item = InputMediaVideo(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        video_count += 1
                        logger.debug(f"   📄🎥 添加文档视频 {i+1}/{len(messages)}")
                        
                    elif message.document and message.document.mime_type and 'image' in message.document.mime_type:
                        # 文档图片
                        media_item = InputMediaPhoto(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        logger.debug(f"   📄📷 添加文档图片 {i+1}/{len(messages)}")
                        
                    else:
                        logger.warning(f"   ⚠️ 消息 {message.id} 不是媒体类型")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ 处理媒体组消息失败 {message.id}: {e}")
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
            
            # 发送媒体组
            logger.info(f"📤 正在发送媒体组 {media_group_id}...")
            await self.client.send_media_group(
                chat_id=task.target_chat_id,
                media=media_list
            )
            logger.info(f"✅ 媒体组 {media_group_id} 发送成功")
            
            # 如果有按钮，单独发送
            if buttons:
                logger.info(f"🔘 发送媒体组 {media_group_id} 的附加按钮")
                await self.client.send_message(
                    chat_id=task.target_chat_id,
                    text="📎 媒体组附加按钮",
                    reply_markup=buttons
                )
                logger.info(f"✅ 媒体组 {media_group_id} 按钮发送成功")
            
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
            logger.info(f"🔍 媒体消息发送: caption='{caption[:100]}...', buttons={bool(buttons)}")
            logger.info(f"🔍 目标频道ID: {task.target_chat_id}")
            logger.info(f"🔍 源消息ID: {message_id}")
            logger.info(f"🔍 媒体类型: photo={bool(original_message.photo)}, video={bool(original_message.video)}, document={bool(original_message.document)}")
            
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
            
            # 复制媒体文件
            try:
                if original_message.photo:
                    logger.info(f"📷 尝试发送照片到 {task.target_chat_id}")
                    result = await self.client.send_photo(
                        chat_id=task.target_chat_id,
                        photo=original_message.photo.file_id,
                        caption=caption,
                        reply_markup=buttons
                    )
                    logger.info(f"✅ 照片发送成功，消息ID: {result.id}")
                elif original_message.video:
                    logger.info(f"🎥 尝试发送视频到 {task.target_chat_id}")
                    result = await self.client.send_video(
                        chat_id=task.target_chat_id,
                        video=original_message.video.file_id,
                        caption=caption,
                        reply_markup=buttons
                    )
                    logger.info(f"✅ 视频发送成功，消息ID: {result.id}")
                elif original_message.document:
                    logger.info(f"📄 尝试发送文档到 {task.target_chat_id}")
                    result = await self.client.send_document(
                        chat_id=task.target_chat_id,
                        document=original_message.document.file_id,
                        caption=caption,
                        reply_markup=buttons
                    )
                    logger.info(f"✅ 文档发送成功，消息ID: {result.id}")
                else:
                    # 其他类型的媒体，发送为文档
                    logger.info(f"📎 尝试发送其他媒体到 {task.target_chat_id}")
                    result = await self.client.send_document(
                        chat_id=task.target_chat_id,
                        document=original_message.document.file_id if original_message.document else None,
                        caption=caption,
                        reply_markup=buttons
                    )
                    logger.info(f"✅ 其他媒体发送成功，消息ID: {result.id}")
                
                return True
                
            except FloodWait as flood_error:
                # 解析等待时间
                wait_time = int(str(flood_error).split('A wait of ')[1].split(' seconds')[0])
                logger.warning(f"⚠️ 遇到FloodWait限制，需要等待 {wait_time} 秒")
                
                # 等待指定时间
                logger.info(f"⏳ 等待 {wait_time} 秒后重试...")
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
            return False
        
        task = self.active_tasks[task_id]
        task.status = "cancelled"
        task.end_time = datetime.now()
        
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
        
        logger.info(f"任务已取消: {task_id}")
        return True
    
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

    async def _get_first_batch(self, chat_id: str, start_id: Optional[int], end_id: Optional[int]) -> List[Message]:
        """获取第一批消息（500条）"""
        try:
            if start_id and end_id:
                # 指定范围的消息，获取前500条
                batch_size = 500
                batch_end = min(start_id + batch_size - 1, end_id)
                
                logger.info(f"获取第一批消息: {start_id} - {batch_end}")
                
                messages = await self.client.get_messages(
                    chat_id, 
                    message_ids=list(range(start_id, batch_end + 1))
                )
                
                # 过滤掉None值
                valid_messages = [msg for msg in messages if msg is not None]
                logger.info(f"第一批消息获取成功: {len(valid_messages)} 条")
                return valid_messages
            else:
                # 获取最近500条消息
                messages = await self.client.get_messages(chat_id, 500)
                
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
            max_execution_time = task.config.get('task_timeout', 7200) if hasattr(task, 'config') and task.config else 7200
            
            if not messages:
                return True
            
            # 按媒体组分组处理消息
            media_groups = {}
            standalone_messages = []
            
            for message in messages:
                try:
                    if hasattr(message, 'media_group_id') and message.media_group_id:
                        if message.media_group_id not in media_groups:
                            media_groups[message.media_group_id] = []
                        media_groups[message.media_group_id].append(message)
                    else:
                        standalone_messages.append(message)
                except Exception as e:
                    logger.warning(f"分析消息失败: {e}")
                    standalone_messages.append(message)
            
            # 处理媒体组
            for media_group_id, group_messages in media_groups.items():
                try:
                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 已被{task.status}，停止处理")
                        return False
                    
                    # 检查超时
                    if time.time() - task_start_time > max_execution_time:
                        logger.warning(f"任务执行超时（{max_execution_time}秒），停止处理")
                        return False
                    
                    group_messages.sort(key=lambda m: m.id)
                    success = await self._process_media_group(task, group_messages)
                    
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
                        task.progress = (task.processed_messages / task.total_messages) * 100.0
                    else:
                        # 如果没有总消息数，使用已处理消息数作为进度
                        task.progress = min(task.processed_messages * 10, 100.0)
                    
                    # 调用进度回调
                    if self.progress_callback:
                        await self.progress_callback(task)
                    
                    # 使用配置中的媒体组延迟设置
                    media_group_delay = task.config.get('media_group_delay', 0.3)
                    await asyncio.sleep(media_group_delay)
                    
                except Exception as e:
                    logger.error(f"处理媒体组失败 {media_group_id}: {e}")
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
                        task.progress = (task.processed_messages / task.total_messages) * 100.0
                    else:
                        # 如果没有总消息数，使用已处理消息数作为进度
                        task.progress = min(task.processed_messages * 10, 100.0)
                    
                    # 调用进度回调
                    if self.progress_callback:
                        await self.progress_callback(task)
                    
                    # 使用配置中的消息延迟设置
                    message_delay = task.config.get('message_delay', 0.2)
                    await asyncio.sleep(message_delay)
                    
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

# ==================== 导出函数 ====================
def create_cloning_engine(client: Client, config: Dict[str, Any], data_manager=None) -> CloningEngine:
    """创建搬运引擎实例"""
    return CloningEngine(client, config, data_manager)

__all__ = [
    "CloneTask", "CloningEngine", "create_cloning_engine"
]

