# ==================== 评论搬运引擎 ====================
"""
评论搬运引擎
负责将指定信息搬运到目标频道的某个信息的评论区
支持媒体组搬运功能
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from pyrogram.client import Client
from pyrogram.types import Message, Chat, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from pyrogram.errors import FloodWait, ChatAdminRequired, MessageNotModified
from message_engine import MessageEngine
from data_manager import get_user_config, data_manager
from config import DEFAULT_USER_CONFIG
from task_state_manager import get_global_task_state_manager, TaskStatus
from anti_detection_integration import AntiDetectionIntegration, ANTI_DETECTION_CONFIG

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

class CommentCloneTask:
    """评论搬运任务类"""
    
    def __init__(self, task_id: str, source_chat_id: str, target_chat_id: str, 
                 target_message_id: int, message_ids: List[int],
                 config: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None):
        """初始化评论搬运任务"""
        self.task_id = task_id
        self.source_chat_id = source_chat_id
        self.target_chat_id = target_chat_id
        self.target_message_id = target_message_id  # 目标消息ID，将在此消息下评论
        self.message_ids = message_ids  # 要搬运的消息ID列表
        self.config = config or {}
        self.user_id = user_id
        
        # 任务状态
        self.status = "pending"  # pending, running, completed, failed, paused, cancelled
        self.progress = 0.0  # 0.0 - 100.0
        self.current_message_index = 0
        self.total_messages = len(message_ids)
        self.processed_messages = 0
        self.failed_messages = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # 频道名称信息
        self.source_channel_name: Optional[str] = None
        self.target_channel_name: Optional[str] = None
        
        # 取消标志
        self._cancelled = False  # 内部取消标志，用于立即停止任务
        
        # 统计信息
        self.stats = {
            'total_messages': len(message_ids),
            'processed_messages': 0,
            'failed_messages': 0,
            'skipped_messages': 0
        }
        
        logger.info(f"📝 创建评论搬运任务: {task_id}")
        logger.info(f"  • 源频道: {source_chat_id}")
        logger.info(f"  • 目标频道: {target_chat_id}")
        logger.info(f"  • 目标消息ID: {target_message_id}")
        logger.info(f"  • 要搬运的消息数量: {len(message_ids)}")
        logger.info(f"  • AI改写: {self.ai_rewrite_enabled} ({self.ai_rewrite_mode})")

    def should_stop(self) -> bool:
        """检查任务是否应该停止"""
        return self.status in ["cancelled", "failed", "paused"]
    
    def is_cancelled(self) -> bool:
        """检查任务是否已被取消"""
        return self.status == "cancelled"
    
    def mark_message_processed(self, message_id: int):
        """标记消息为已处理"""
        self.processed_message_ids.add(message_id)
        self.processed_messages += 1
        self.current_message_index += 1
        
        # 更新进度
        if self.total_messages > 0:
            self.progress = (self.processed_messages / self.total_messages) * 100.0
    
    def mark_message_failed(self, message_id: int):
        """标记消息处理失败"""
        self.failed_messages += 1
        self.current_message_index += 1
        
        # 更新进度
        if self.total_messages > 0:
            self.progress = (self.processed_messages / self.total_messages) * 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "source_chat_id": self.source_chat_id,
            "target_chat_id": self.target_chat_id,
            "target_message_id": self.target_message_id,
            "message_ids": self.message_ids,
            "status": self.status,
            "progress": self.progress,
            "current_message_index": self.current_message_index,
            "total_messages": self.total_messages,
            "processed_messages": self.processed_messages,
            "failed_messages": self.failed_messages,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source_channel_name": self.source_channel_name,
            "target_channel_name": self.target_channel_name,
            "processed_message_ids": list(self.processed_message_ids),
            "config": self.config,
            "user_id": self.user_id
        }

class CommentCloningEngine:
    """评论搬运引擎"""
    
    def __init__(self, client: Client, config: Optional[Dict[str, Any]] = None):
        """初始化评论搬运引擎"""
        self.client = client
        self.config = config or {}
        
        # 使用配置或默认配置初始化消息引擎
        user_config = self.config.get('user_config', DEFAULT_USER_CONFIG)
        self.message_engine = MessageEngine(user_config)
        self.anti_detection = AntiDetectionIntegration()
        
        # 重试设置
        self.retry_attempts = self.config.get('retry_attempts', 3)
        self.retry_delay = self.config.get('retry_delay', 2.0)
        
        # 评论发送设置
        self.comment_delay = self.config.get('comment_delay', 1.0)  # 评论间延迟
        self.max_comments_per_message = self.config.get('max_comments_per_message', 10)  # 每条消息最大评论数
        
        # 媒体组设置
        self.media_group_search_range = self.config.get('media_group_search_range', 50)  # 媒体组搜索范围
        self.media_group_timeout = self.config.get('media_group_timeout', 30.0)  # 媒体组处理超时
        
        # 错误处理设置
        self.continue_on_error = self.config.get('continue_on_error', True)  # 遇到错误是否继续
        self.max_consecutive_errors = self.config.get('max_consecutive_errors', 5)  # 最大连续错误数
        
        # AI文本改写配置
        self.ai_config = {
            'ai_rewrite_enabled': config.get('ai_rewrite_enabled', False) if config else False,
            'ai_rewrite_mode': config.get('ai_rewrite_mode', 'auto') if config else 'auto',
            'ai_rewrite_intensity': config.get('ai_rewrite_intensity', 'medium') if config else 'medium',
            'gemini_api_key': config.get('gemini_api_key', '') if config else ''
        }
        
        # 任务管理
        self.active_tasks: Dict[str, CommentCloneTask] = {}
        
        logger.info("🚀 评论搬运引擎初始化完成")
        logger.info(f"  • 重试次数: {self.retry_attempts}")
        logger.info(f"  • 重试延迟: {self.retry_delay}秒")
        logger.info(f"  • 评论延迟: {self.comment_delay}秒")
        logger.info(f"  • AI改写: {self.ai_config['ai_rewrite_enabled']}")

    async def create_comment_clone_task(self, source_chat_id: str, target_chat_id: str, 
                                      target_message_id: int, message_ids: List[int],
                                      config: Optional[Dict[str, Any]] = None, 
                                      user_id: str = None) -> str:
        """创建评论搬运任务"""
        try:
            # 生成任务ID
            task_id = f"comment_clone_{int(time.time())}_{len(self.active_tasks)}"
            
            # 验证参数
            if not message_ids:
                raise ValueError("消息ID列表不能为空")
            
            if target_message_id <= 0:
                raise ValueError("目标消息ID必须大于0")
            
            # 创建任务
            task = CommentCloneTask(
                task_id=task_id,
                source_chat_id=source_chat_id,
                target_chat_id=target_chat_id,
                target_message_id=target_message_id,
                message_ids=message_ids,
                config=config,
                user_id=user_id
            )
            
            # 验证频道访问权限
            await self._validate_channel_access(task)
            
            # 添加到活跃任务列表
            self.active_tasks[task_id] = task
            
            logger.info(f"✅ 评论搬运任务创建成功: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"❌ 创建评论搬运任务失败: {e}")
            raise
    
    async def _validate_channel_access(self, task: CommentCloneTask):
        """验证频道访问权限"""
        try:
            # 验证源频道
            source_chat = await self.client.get_chat(task.source_chat_id)
            task.source_channel_name = getattr(source_chat, 'title', task.source_chat_id)
            logger.info(f"✅ 源频道访问成功: {task.source_channel_name}")
            
            # 验证目标频道
            target_chat = await self.client.get_chat(task.target_chat_id)
            task.target_channel_name = getattr(target_chat, 'title', task.target_chat_id)
            logger.info(f"✅ 目标频道访问成功: {task.target_channel_name}")
            
            # 验证目标消息是否存在
            try:
                target_message = await self.client.get_messages(task.target_chat_id, task.target_message_id)
                if not target_message:
                    raise ValueError(f"目标消息 {task.target_message_id} 不存在")
                logger.info(f"✅ 目标消息验证成功: {task.target_message_id}")
            except Exception as e:
                raise ValueError(f"无法访问目标消息 {task.target_message_id}: {e}")
            
        except Exception as e:
            logger.error(f"❌ 频道访问验证失败: {e}")
            raise
    
    async def start_comment_clone_task(self, task_id: str) -> bool:
        """启动评论搬运任务"""
        try:
            if task_id not in self.active_tasks:
                logger.error(f"❌ 任务不存在: {task_id}")
                return False
            
            task = self.active_tasks[task_id]
            
            if task.status != "pending":
                logger.warning(f"⚠️ 任务状态不是pending: {task.status}")
                return False
            
            # 更新任务状态
            task.status = "running"
            task.start_time = time.time()
            
            logger.info(f"🚀 开始执行评论搬运任务: {task_id}")
            logger.info(f"  • 源频道: {task.source_channel_name}")
            logger.info(f"  • 目标频道: {task.target_channel_name}")
            logger.info(f"  • 目标消息ID: {task.target_message_id}")
            logger.info(f"  • 要搬运的消息数量: {task.total_messages}")
            
            # 执行搬运
            success = await self._execute_comment_cloning(task)
            
            if success:
                task.status = "completed"
                task.end_time = time.time()
                logger.info(f"🎉 评论搬运任务完成: {task_id}")
            else:
                task.status = "failed"
                task.end_time = time.time()
                logger.error(f"❌ 评论搬运任务失败: {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 启动评论搬运任务失败: {e}")
            if task_id in self.active_tasks:
                self.active_tasks[task_id].status = "failed"
            return False
    
    async def _execute_comment_cloning(self, task: CommentCloneTask) -> bool:
        """执行评论搬运"""
        try:
            logger.info(f"🔄 开始处理 {task.total_messages} 条消息")
            
            # 获取要搬运的消息
            messages = await self.client.get_messages(task.source_chat_id, message_ids=task.message_ids)
            valid_messages = [msg for msg in messages if msg is not None]
            
            if not valid_messages:
                logger.warning("没有找到有效的消息")
                return True
            
            logger.info(f"📊 找到 {len(valid_messages)} 条有效消息")
            
            # 连续错误计数器
            consecutive_errors = 0
            
            # 处理每条消息
            for i, message in enumerate(valid_messages):
                try:
                    # 跳过已经处理过的消息（支持断点续传时避免重复发送）
                    try:
                        msg_id_check = message.id
                    except Exception:
                        msg_id_check = None

                    if msg_id_check is not None and msg_id_check in task.processed_message_ids:
                        logger.info(f"🔁 跳过已处理消息 {msg_id_check}")
                        continue

                    # 检查任务状态
                    if task.should_stop():
                        logger.info(f"任务 {task.task_id} 已被{task.status}")
                        return False
                    
                    # 检查连续错误数
                    if consecutive_errors >= self.max_consecutive_errors:
                        logger.error(f"❌ 连续错误数达到上限 ({self.max_consecutive_errors})，停止任务")
                        task.status = "failed"
                        return False
                    
                    logger.info(f"📝 处理消息 {i+1}/{len(valid_messages)}: {message.id}")
                    
                    # 处理消息
                    success = await self._process_single_message(task, message)
                    
                    if success:
                        task.mark_message_processed(message.id)
                        consecutive_errors = 0  # 重置连续错误计数
                        logger.info(f"✅ 消息 {message.id} 处理成功")
                    else:
                        task.mark_message_failed(message.id)
                        consecutive_errors += 1
                        logger.warning(f"⚠️ 消息 {message.id} 处理失败 (连续错误: {consecutive_errors})")
                        
                        # 如果遇到错误且不继续，停止任务
                        if not self.continue_on_error:
                            logger.error("❌ 遇到错误且设置为不继续，停止任务")
                            task.status = "failed"
                            return False
                    
                    # 添加延迟避免API限制
                    await asyncio.sleep(self.comment_delay)
                    
                except Exception as e:
                    logger.error(f"❌ 处理消息 {message.id} 时出错: {e}")
                    task.mark_message_failed(message.id)
                    consecutive_errors += 1
                    
                    # 如果遇到错误且不继续，停止任务
                    if not self.continue_on_error:
                        logger.error("❌ 遇到错误且设置为不继续，停止任务")
                        task.status = "failed"
                        return False
                    
                    continue
            
            logger.info(f"🎉 评论搬运完成")
            logger.info(f"  • 成功: {task.processed_messages}")
            logger.info(f"  • 失败: {task.failed_messages}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 执行评论搬运失败: {e}")
            return False
    
    async def _process_single_message(self, task: CommentCloneTask, message: Message) -> bool:
        """处理单条消息"""
        try:
            logger.info(f"📝 处理消息: {message.id}")
            
            # 处理文本内容
            text = message.text or message.caption or ""
            
            # 如果启用了AI改写，则先进行AI处理
            if task.ai_rewrite_enabled:
                logger.info(f"🤖 开始AI文本改写: {message.id}")
                original_text = text
                text, was_rewritten = await self.message_engine.process_text_with_ai(text, task.user_id)
                
                if was_rewritten:
                    logger.info(f"✅ 消息 {message.id} 已AI改写")
                else:
                    logger.info(f"ℹ️ 消息 {message.id} 未进行AI改写")
            
            # 处理文本（包括过滤、替换等）
            processed_result, _ = self.message_engine.process_message(
                message, 
                self.config, 
                skip_blank_check=True
            )
            
            # 使用AI处理后的文本替换原始文本
            if task.ai_rewrite_enabled and text != (message.text or message.caption or ""):
                processed_result['text'] = text
            
            # 发送评论
            if message.text:
                success = await self._send_text_comment(task, processed_result)
            elif message.media:
                success = await self._send_media_comment(task, message, processed_result)
            else:
                logger.warning(f"⚠️ 消息 {message.id} 既不是文本也不是媒体消息")
                success = True  # 空消息当作成功处理
            
            # 添加评论间延迟
            if success and self.comment_delay > 0:
                await asyncio.sleep(self.comment_delay)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 处理消息 {message.id} 失败: {e}")
            return False
    
    async def _send_message_as_comment(self, task: CommentCloneTask, original_message: Message, 
                                     processed_result: Dict[str, Any]) -> bool:
        """将消息作为评论发送"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送评论")
                return False
            
            # 判断消息类型
            has_media = (
                original_message.photo or original_message.video or original_message.document or 
                original_message.audio or original_message.voice or original_message.sticker or 
                original_message.animation or original_message.video_note or original_message.media
            )
            
            message_type = "媒体消息" if has_media else "文本消息"
            logger.info(f"💬 发送 {message_type} 作为评论: {original_message.id}")
            
            # 重试机制
            for attempt in range(self.retry_attempts):
                try:
                    if has_media:
                        # 媒体消息
                        success = await self._send_media_comment(task, original_message, processed_result)
                    else:
                        # 文本消息
                        success = await self._send_text_comment(task, processed_result)
                    
                    if success:
                        logger.info(f"✅ {message_type} {original_message.id} 评论发送成功")
                        return True
                    
                except Exception as e:
                    logger.warning(f"⚠️ 发送 {message_type} {original_message.id} 评论失败 (尝试 {attempt + 1}/{self.retry_attempts}): {e}")
                    
                    if attempt < self.retry_attempts - 1:
                        logger.debug(f"⏳ 等待 {self.retry_delay} 秒后重试...")
                        await asyncio.sleep(self.retry_delay)
            
            logger.error(f"❌ {message_type} {original_message.id} 评论发送失败，已达到最大重试次数")
            return False
            
        except Exception as e:
            logger.error(f"❌ 发送评论失败: {e}")
            return False
    
    async def _send_text_comment(self, task: CommentCloneTask, processed_result: Dict[str, Any]) -> bool:
        """发送文本评论"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送文本评论")
                return False
            
            text = processed_result.get('text', '')
            buttons = processed_result.get('buttons')
            
            if not text and not buttons:
                logger.debug("📝 跳过空文本评论")
                return True  # 空消息，跳过
            
            # 显示文本内容摘要
            text_preview = text[:50] + "..." if len(text) > 50 else text
            logger.debug(f"📝 发送文本评论: {text_preview}")
            
            # 发送评论（回复目标消息）
            await self.client.send_message(
                chat_id=task.target_chat_id,
                text=text or " ",  # 空文本用空格代替
                reply_to_message_id=task.target_message_id,
                reply_markup=buttons
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送文本评论失败: {e}")
            return False
    
    async def _send_media_comment(self, task: CommentCloneTask, original_message: Message, 
                                processed_result: Dict[str, Any]) -> bool:
        """发送媒体评论"""
        try:
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体评论")
                return False
            
            # 检查是否为媒体组
            if original_message.media_group_id:
                # 获取媒体组的所有消息
                media_group_messages = await self._get_media_group_messages(task.source_chat_id, original_message.id)
                if media_group_messages:
                    return await self._send_media_group_comment(task, media_group_messages, processed_result)
            
            # 单媒体消息
            caption = processed_result.get('caption', '')
            buttons = processed_result.get('buttons')
            
            logger.debug(f"📱 发送单媒体评论: {original_message.id}")
            logger.debug(f"  • Caption: '{caption[:50]}...' (长度: {len(caption)})")
            logger.debug(f"  • 按钮: {bool(buttons)}")
            
            # 根据媒体类型发送
            if original_message.photo:
                await self.client.send_photo(
                    chat_id=task.target_chat_id,
                    photo=original_message.photo.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.video:
                await self.client.send_video(
                    chat_id=task.target_chat_id,
                    video=original_message.video.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.document:
                await self.client.send_document(
                    chat_id=task.target_chat_id,
                    document=original_message.document.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.audio:
                await self.client.send_audio(
                    chat_id=task.target_chat_id,
                    audio=original_message.audio.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.voice:
                await self.client.send_voice(
                    chat_id=task.target_chat_id,
                    voice=original_message.voice.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.sticker:
                await self.client.send_sticker(
                    chat_id=task.target_chat_id,
                    sticker=original_message.sticker.file_id,
                    reply_to_message_id=task.target_message_id
                )
            elif original_message.animation:
                await self.client.send_animation(
                    chat_id=task.target_chat_id,
                    animation=original_message.animation.file_id,
                    caption=caption,
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            elif original_message.video_note:
                await self.client.send_video_note(
                    chat_id=task.target_chat_id,
                    video_note=original_message.video_note.file_id,
                    reply_to_message_id=task.target_message_id
                )
            else:
                logger.warning(f"⚠️ 不支持的媒体类型: {original_message.id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送媒体评论失败: {e}")
            return False
    
    async def _get_media_group_messages(self, chat_id: str, media_group_id: str) -> List[Message]:
        """获取媒体组的所有消息"""
        try:
            logger.debug(f"🔍 尝试获取媒体组消息: {media_group_id}")
            
            # 由于Pyrogram没有直接的方法获取媒体组，我们需要通过搜索来获取
            # 这里实现一个简化的方法，通过消息ID范围搜索
            
            # 首先获取当前消息
            current_message = await self.client.get_messages(chat_id, message_ids=[media_group_id])
            if not current_message or not current_message[0]:
                logger.warning(f"无法获取媒体组起始消息: {media_group_id}")
                return []
            
            current_msg = current_message[0]
            if not current_msg.media_group_id:
                logger.warning(f"消息 {media_group_id} 不是媒体组消息")
                return [current_msg]
            
            # 搜索媒体组的其他消息
            media_group_messages = [current_msg]
            
            # 向前搜索（查找更早的消息）
            search_range = self.media_group_search_range
            for offset in range(1, search_range + 1):
                try:
                    msg_id = current_msg.id - offset
                    if msg_id <= 0:
                        break
                    
                    msg = await self.client.get_messages(chat_id, msg_id)
                    if msg and msg.media_group_id == media_group_id:
                        media_group_messages.insert(0, msg)  # 插入到开头保持顺序
                    else:
                        break
                        
                except Exception:
                    break
            
            # 向后搜索（查找更晚的消息）
            for offset in range(1, search_range + 1):
                try:
                    msg_id = current_msg.id + offset
                    msg = await self.client.get_messages(chat_id, msg_id)
                    if msg and msg.media_group_id == media_group_id:
                        media_group_messages.append(msg)
                    else:
                        break
                        
                except Exception:
                    break
            
            # 按消息ID排序
            media_group_messages.sort(key=lambda x: x.id)
            
            logger.info(f"📱 找到媒体组 {media_group_id} 的 {len(media_group_messages)} 条消息")
            return media_group_messages
            
        except Exception as e:
            logger.error(f"❌ 获取媒体组消息失败: {e}")
            return []
    
    async def _send_media_group_comment(self, task: CommentCloneTask, messages: List[Message], 
                                      processed_result: Dict[str, Any]) -> bool:
        """发送媒体组评论"""
        try:
            if not messages:
                return False
            
            # 检查任务状态
            if task.should_stop():
                logger.info(f"任务 {task.task_id} 已被{task.status}，停止发送媒体组评论")
                return False
            
            media_group_id = messages[0].media_group_id
            logger.info(f"📱 开始发送媒体组评论 {media_group_id} ({len(messages)} 条消息)")
            
            # 构建媒体组
            media_list = []
            caption = processed_result.get('caption', '')
            buttons = processed_result.get('buttons')
            
            logger.debug(f"🔍 媒体组评论内容:")
            logger.debug(f"  • Caption: '{caption[:50]}...' (长度: {len(caption)})")
            logger.debug(f"  • 按钮: {bool(buttons)}")
            
            # 统计媒体类型
            photo_count = 0
            video_count = 0
            document_count = 0
            
            for i, message in enumerate(messages):
                try:
                    logger.debug(f"🔍 处理媒体组消息 {i+1}/{len(messages)}: ID={message.id}")
                    
                    if message.photo:
                        media_item = InputMediaPhoto(
                            media=message.photo.file_id,
                            caption=caption if i == 0 else None  # 只在第一个媒体上添加caption
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        
                    elif message.video:
                        media_item = InputMediaVideo(
                            media=message.video.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        video_count += 1
                        
                    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
                        media_item = InputMediaVideo(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        video_count += 1
                        
                    elif message.document and message.document.mime_type and 'image' in message.document.mime_type:
                        media_item = InputMediaPhoto(
                            media=message.document.file_id,
                            caption=caption if i == 0 else None
                        )
                        media_list.append(media_item)
                        photo_count += 1
                        
                    else:
                        logger.warning(f"   ⚠️ 消息 {message.id} 不是支持的媒体类型")
                        continue
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ 处理媒体组消息 {message.id} 失败: {e}")
                    continue
            
            if not media_list:
                logger.warning("媒体组中没有有效的媒体")
                return False
            
            logger.info(f"📊 媒体组统计: 照片={photo_count}, 视频={video_count}, 文档={document_count}")
            logger.info(f"📤 发送媒体组评论 ({len(media_list)} 个媒体)")
            
            # 发送媒体组评论
            await self.client.send_media_group(
                chat_id=task.target_chat_id,
                media=media_list,
                reply_to_message_id=task.target_message_id
            )
            
            # 如果有按钮，单独发送一条消息包含按钮
            if buttons:
                await self.client.send_message(
                    chat_id=task.target_chat_id,
                    text="📎 相关链接:",
                    reply_to_message_id=task.target_message_id,
                    reply_markup=buttons
                )
            
            logger.info(f"✅ 媒体组评论发送成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送媒体组评论失败: {e}")
            return False
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id not in self.active_tasks:
            return None
        
        task = self.active_tasks[task_id]
        return task.to_dict()
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.active_tasks:
            return False
        
        task = self.active_tasks[task_id]
        task.status = "cancelled"
        task._cancelled = True
        
        logger.info(f"🛑 任务已取消: {task_id}")
        return True
    
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        if task_id not in self.active_tasks:
            return False
        
        task = self.active_tasks[task_id]
        if task.status == "running":
            task.status = "paused"
            logger.info(f"⏸️ 任务已暂停: {task_id}")
            return True
        
        return False
    
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        if task_id not in self.active_tasks:
            return False
        
        task = self.active_tasks[task_id]
        if task.status == "paused":
            task.status = "running"
            logger.info(f"▶️ 任务已恢复: {task_id}")
            return True
        
        return False
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务状态"""
        return {task_id: task.to_dict() for task_id, task in self.active_tasks.items()}
    
    def clear_completed_tasks(self):
        """清理已完成的任务"""
        completed_tasks = [task_id for task_id, task in self.active_tasks.items() 
                          if task.status in ["completed", "failed", "cancelled"]]
        
        for task_id in completed_tasks:
            del self.active_tasks[task_id]
        
        logger.info(f"🧹 清理了 {len(completed_tasks)} 个已完成的任务")
