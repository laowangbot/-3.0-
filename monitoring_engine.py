# ==================== 监听引擎 ====================
"""
监听引擎
负责实时监听频道消息并自动搬运到目标频道
支持自动检测最后消息ID和手动设置两种模式
"""

import asyncio
import logging
import time
import os
import json
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.types import Message, Chat, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio, InputMediaAnimation
from pyrogram.errors import FloodWait, ChannelPrivate, ChannelInvalid
from message_engine import MessageEngine
from data_manager import data_manager
from config import DEFAULT_USER_CONFIG

# 配置日志 - 使用优化的日志配置
from log_config import get_logger
logger = get_logger(__name__)

class MonitoringTask:
    """监听任务类"""
    
    def __init__(self, task_id: str, user_id: str, target_channel: str, 
                 source_channels: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None):
        """初始化监听任务"""
        self.task_id = task_id
        self.user_id = user_id
        self.target_channel = target_channel
        self.source_channels = source_channels  # 每个源频道的配置
        self.config = config or {}
        
        # 任务状态
        self.status = "pending"  # pending, active, paused, stopped, failed
        self.is_running = False
        self.start_time = None
        self.last_check_time = None
        self.next_check_time = None
        
        # 监听配置
        self.check_interval = self.config.get('check_interval', 60)  # 检查间隔（秒）
        self.max_retries = self.config.get('max_retries', 3)  # 最大重试次数
        self.retry_delay = self.config.get('retry_delay', 30)  # 重试延迟（秒）
        
        # 统计信息
        self.stats = {
            'total_checks': 0,
            'new_messages_found': 0,
            'messages_forwarded': 0,
            'failed_forwards': 0,
            'last_message_id': {},
            'last_check_times': {}
        }
        
        # 错误处理
        self.consecutive_errors = 0
        self.last_error = None
        self.last_error_time = None
    
    def should_stop(self) -> bool:
        """检查任务是否应该停止"""
        return self.status in ['stopped', 'failed'] or not self.is_running
    
    def get_next_check_time(self) -> datetime:
        """计算下次检查时间"""
        if self.next_check_time:
            return self.next_check_time
        
        # 为每个源频道计算错开的检查时间
        base_time = datetime.now()
        for i, source in enumerate(self.source_channels):
            offset_minutes = i * 2  # 每个频道错开2分钟
            check_time = base_time + timedelta(minutes=offset_minutes)
            source['next_check'] = check_time
        
        # 返回最早的检查时间
        next_times = [source.get('next_check', base_time) for source in self.source_channels]
        return min(next_times)
    
    def update_source_last_id(self, channel_id: str, message_id: int):
        """更新源频道的最后消息ID"""
        for source in self.source_channels:
            if source.get('channel_id') == channel_id:
                source['last_message_id'] = message_id
                self.stats['last_message_id'][channel_id] = message_id
                break
    
    def get_source_last_id(self, channel_id: str) -> int:
        """获取源频道的最后消息ID"""
        for source in self.source_channels:
            if source.get('channel_id') == channel_id:
                return source.get('last_message_id', 0)
        return 0

class MonitoringEngine:
    """监听引擎类"""
    
    def __init__(self, client: Client, config: Optional[Dict[str, Any]] = None):
        """初始化监听引擎"""
        self.client = client
        self.config = config or {}
        self.message_engine = MessageEngine(self.config)
        self.active_tasks: Dict[str, MonitoringTask] = {}
        self.is_running = False
        self.monitoring_loop_task = None
        
        # 监听配置
        self.global_check_interval = 60  # 全局检查间隔（60秒）
        self.max_concurrent_tasks = 10  # 最大并发任务数
        
        logger.info("监听引擎初始化完成")
    
    async def start_monitoring(self):
        """启动监听系统"""
        if self.is_running:
            logger.warning("监听系统已在运行")
            return
        
        self.is_running = True
        logger.info("🚀 启动监听系统")
        
        # 启动监听循环
        self.monitoring_loop_task = asyncio.create_task(self._monitoring_loop())
        
        logger.info("✅ 监听系统启动成功")
    
    async def stop_monitoring(self):
        """停止监听系统"""
        if not self.is_running:
            logger.warning("监听系统未运行")
            return
        
        self.is_running = False
        logger.info("🛑 停止监听系统")
        
        # 停止所有任务
        for task in self.active_tasks.values():
            task.status = "stopped"
            task.is_running = False
        
        # 取消监听循环
        if self.monitoring_loop_task:
            self.monitoring_loop_task.cancel()
            try:
                await self.monitoring_loop_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 监听系统已停止")
    
    async def create_monitoring_task(self, user_id: str, target_channel: str, 
                                   source_channels: List[Dict[str, Any]], 
                                   config: Optional[Dict[str, Any]] = None) -> str:
        """创建监听任务"""
        try:
            task_id = f"monitor_{user_id}_{int(time.time())}"
            
            # 严格验证目标频道（必须能访问才能转发消息）
            if not await self._validate_target_channel_access(target_channel):
                raise ValueError(f"无法访问目标频道: {target_channel}")
            
            # 验证源频道并获取最后消息ID
            validated_sources = []
            for source in source_channels:
                channel_id = source.get('channel_id')
                channel_username = source.get('channel_username', '')
                
                if not await self._validate_channel_access(channel_id):
                    logger.warning(f"无法访问源频道: {channel_id}")
                    continue
                
                # 获取最后消息ID（必须由用户手动指定）
                last_id = source.get('last_message_id')
                if last_id is None:
                    logger.warning(f"频道 {channel_id} 未指定起始消息ID，监听任务创建失败")
                    continue
                
                validated_source = {
                    'channel_id': channel_id,
                    'channel_name': source.get('channel_name', '未知频道'),
                    'channel_username': channel_username,
                    'last_message_id': last_id,
                    'id_range_increment': source.get('id_range_increment', 50),  # ID范围增量，默认50
                    'check_interval': source.get('check_interval', 60),
                    'next_check': datetime.now()
                }
                validated_sources.append(validated_source)
                
                channel_name = source.get('channel_name', '未知频道')
                logger.info(f"源频道 {channel_name} ({channel_id}) 最后消息ID: {last_id}")
            
            if not validated_sources:
                raise ValueError("没有可用的源频道")
            
            # 创建任务
            task = MonitoringTask(task_id, user_id, target_channel, validated_sources, config)
            self.active_tasks[task_id] = task
            
            # 保存任务到数据库
            await self._save_monitoring_task(task)
            
            logger.info(f"✅ 创建监听任务: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"创建监听任务失败: {e}")
            raise
    
    async def start_monitoring_task(self, task_id: str) -> bool:
        """启动指定的监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
            
            if task.status == "active":
                logger.warning(f"任务已在运行: {task_id}")
                return True
            
            task.status = "active"
            task.is_running = True
            task.start_time = datetime.now()
            
            # 保存任务状态
            await self._save_monitoring_task(task)
            
            logger.info(f"✅ 启动监听任务: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动监听任务失败: {e}")
            return False
    
    async def stop_monitoring_task(self, task_id: str) -> bool:
        """停止指定的监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return False
            
            task.status = "stopped"
            task.is_running = False
            
            # 保存任务状态
            await self._save_monitoring_task(task)
            
            logger.info(f"✅ 停止监听任务: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"停止监听任务失败: {e}")
            return False
    
    async def delete_monitoring_task(self, task_id: str) -> bool:
        """删除监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if task:
                task.status = "stopped"
                task.is_running = False
                del self.active_tasks[task_id]
            
            # 从数据库删除
            await self._delete_monitoring_task(task_id)
            
            logger.info(f"✅ 删除监听任务: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除监听任务失败: {e}")
            return False
    
    async def get_monitoring_tasks(self, user_id: str) -> List[MonitoringTask]:
        """获取用户的监听任务列表"""
        try:
            user_tasks = []
            for task in self.active_tasks.values():
                if task.user_id == user_id:
                    user_tasks.append(task)
            
            return user_tasks
            
        except Exception as e:
            logger.error(f"获取监听任务失败: {e}")
            return []
    
    async def _monitoring_loop(self):
        """监听循环"""
        logger.info("🔄 开始监听循环")
        
        while self.is_running:
            try:
                # 检查所有活跃任务
                active_tasks = [task for task in self.active_tasks.values() 
                              if task.status == "active" and task.is_running]
                
                if not active_tasks:
                    await asyncio.sleep(self.global_check_interval)
                    continue
                
                # 并发检查所有任务
                check_tasks = []
                for task in active_tasks:
                    if task.get_next_check_time() <= datetime.now():
                        check_tasks.append(self._check_task(task))
                
                if check_tasks:
                    await asyncio.gather(*check_tasks, return_exceptions=True)
                
                # 等待下次检查
                await asyncio.sleep(60)  # 每60秒检查一次
                
            except Exception as e:
                logger.error(f"监听循环异常: {e}")
                await asyncio.sleep(30)  # 出错时等待30秒
    
    async def _check_task(self, task: MonitoringTask):
        """检查单个监听任务 - 每60秒启动一次搬运任务"""
        try:
            if task.should_stop():
                return
            
            # 减少检查任务的日志输出频率
            if not hasattr(task, '_last_check_log') or (datetime.now() - task._last_check_log).seconds > 300:  # 5分钟记录一次
                logger.info(f"🔍 检查监听任务: {task.task_id}")
                task._last_check_log = datetime.now()
            
            for source in task.source_channels:
                if task.should_stop():
                    break
                
                channel_id = source['channel_id']
                channel_name = source.get('channel_name', '未知频道')
                last_id = source['last_message_id']
                
                # 获取ID范围增量配置（默认50）
                id_range_increment = source.get('id_range_increment', 50)
                
                # 计算下次尝试搬运的ID范围
                start_id = last_id + 1
                end_id = last_id + id_range_increment
                
                # 只在有实际搬运时才记录日志
                if start_id <= end_id:
                    logger.info(f"🚀 启动监听搬运任务: {channel_name} ({start_id}-{end_id})")
                
                # 创建搬运任务
                success = await self._create_monitoring_clone_task(
                    task, channel_id, start_id, end_id
                )
                
                if success:
                    # 更新监听ID到结束ID
                    task.update_source_last_id(channel_id, end_id)
                    source['last_message_id'] = end_id
                    
                    # 更新统计
                    task.stats['messages_forwarded'] += (end_id - start_id + 1)
                    
                    logger.info(f"✅ 监听搬运任务完成: {channel_name} -> {end_id}")
                    
                    # 保存任务状态
                    await self._save_monitoring_task(task)
                else:
                    logger.warning(f"❌ 监听搬运任务失败: {channel_name}，60秒后重试")
                    task.stats['failed_forwards'] += 1
                
                # 更新检查时间
                source['next_check'] = datetime.now() + timedelta(seconds=source['check_interval'])
            
            task.stats['total_checks'] += 1
            task.last_check_time = datetime.now()
            
        except Exception as e:
            logger.error(f"检查任务失败 {task.task_id}: {e}")
            task.consecutive_errors += 1
            task.last_error = str(e)
            task.last_error_time = datetime.now()
            
            # 如果连续错误过多，暂停任务
            if task.consecutive_errors >= task.max_retries:
                logger.error(f"任务 {task.task_id} 连续错误过多，暂停任务")
                task.status = "paused"
    
    async def _create_monitoring_clone_task(self, task: MonitoringTask, channel_id: str, start_id: int, end_id: int) -> bool:
        """创建监听搬运任务"""
        try:
            # 创建搬运任务配置
            clone_config = {
                'user_id': task.user_id,
                'source_chat_id': channel_id,
                'target_chat_id': task.target_channel,
                'start_id': start_id,
                'end_id': end_id,
                'description': f"监听搬运: {start_id}-{end_id}"
            }
            
            # 获取过滤配置
            filter_config = await self._get_channel_filter_config(task.user_id, task.target_channel)
            clone_config.update(filter_config)
            
            # 创建搬运任务
            from cloning_engine import create_cloning_engine
            clone_engine = create_cloning_engine(self.client, self.config)
            
            clone_task_id = f"monitor_clone_{task.task_id}_{start_id}_{end_id}"
            clone_task = await clone_engine.create_task(
                source_chat_id=channel_id,
                target_chat_id=task.target_channel,
                start_id=start_id,
                end_id=end_id,
                config=clone_config
            )
            
            if clone_task:
                logger.info(f"✅ 监听搬运任务创建成功: {clone_task_id}")
                return True
            else:
                logger.error(f"❌ 监听搬运任务创建失败: {clone_task_id}")
                return False
                
        except Exception as e:
            logger.error(f"创建监听搬运任务失败: {e}")
            return False
    
    async def update_monitoring_id_range_increment(self, task_id: str, channel_id: str, increment: int) -> bool:
        """更新监听任务的ID范围增量"""
        try:
            # 获取监听任务
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"监听任务不存在: {task_id}")
                return False
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                logger.error(f"源频道不存在: {channel_id}")
                return False
            
            # 更新ID范围增量
            source_channel['id_range_increment'] = increment
            
            # 保存任务状态
            await self._save_monitoring_task(task)
            
            logger.info(f"✅ 更新监听任务ID范围增量: {channel_id} -> {increment}")
            return True
            
        except Exception as e:
            logger.error(f"更新监听任务ID范围增量失败: {e}")
            return False
    
    async def _get_new_messages(self, channel_id: str, channel_name: str, last_id: int) -> List[Message]:
        """获取频道的新消息 - 纯被动监听模式"""
        try:
            # 纯被动监听模式：不主动获取消息，只等待用户手动触发
            logger.info(f"📡 被动监听模式: 频道 {channel_name} (监听ID: {last_id})")
            
            # 由于机器人无法获取频道历史消息，我们采用以下策略：
            # 1. 用户需要手动指定一个预估的最新消息ID
            # 2. 或者使用一个固定的检查间隔，假设每分钟可能有新消息
            
            # 这里我们返回空列表，表示没有新消息
            # 实际的监听将通过用户手动触发或外部事件来驱动
            logger.debug(f"📡 频道 {channel_name} 等待外部触发")
            return []
            
        except Exception as e:
            logger.error(f"获取新消息失败 {channel_name} ({channel_id}): {e}")
            return []
    
    async def manual_trigger_monitoring(self, task_id: str, channel_id: str, end_id: int) -> bool:
        """手动触发监听搬运"""
        try:
            # 获取监听任务
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"监听任务不存在: {task_id}")
                return False
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                logger.error(f"源频道不存在: {channel_id}")
                return False
            
            # 获取当前监听ID
            last_id = source_channel.get('last_message_id', 0)
            
            if end_id <= last_id:
                logger.info(f"结束ID {end_id} 不大于当前监听ID {last_id}，无需搬运")
                return True
            
            # 创建搬运任务
            start_id = last_id + 1
            logger.info(f"🚀 手动触发监听搬运: {channel_id} ({start_id}-{end_id})")
            
            # 创建搬运任务配置
            clone_config = {
                'user_id': task.user_id,
                'source_chat_id': channel_id,
                'target_chat_id': task.target_channel,
                'start_id': start_id,
                'end_id': end_id,
                'description': f"手动监听搬运: {start_id}-{end_id}"
            }
            
            # 获取过滤配置
            filter_config = await self._get_channel_filter_config(task.user_id, task.target_channel)
            clone_config.update(filter_config)
            
            # 创建搬运任务
            from cloning_engine import create_cloning_engine
            clone_engine = create_cloning_engine(self.client, self.config)
            
            clone_task_id = f"monitor_clone_{task_id}_{start_id}_{end_id}"
            clone_task = await clone_engine.create_task(
                source_chat_id=channel_id,
                target_chat_id=task.target_channel,
                start_id=start_id,
                end_id=end_id,
                config=clone_config
            )
            
            if clone_task:
                # 更新监听ID
                source_channel['last_message_id'] = end_id
                task.update_source_last_id(channel_id, end_id)
                
                # 保存任务状态
                await self._save_monitoring_task(task)
                
                logger.info(f"✅ 手动监听搬运任务创建成功: {clone_task_id}")
                return True
            else:
                logger.error(f"❌ 手动监听搬运任务创建失败: {clone_task_id}")
                return False
                
        except Exception as e:
            logger.error(f"手动触发监听失败: {e}")
            return False
    
    async def _forward_messages(self, task: MonitoringTask, messages: List[Message]) -> int:
        """转发消息到目标频道"""
        success_count = 0
        
        for message in messages:
            try:
                if task.should_stop():
                    break
                
                # 检查是否是消息范围格式
                if isinstance(message, dict) and message.get('is_range'):
                    # 处理消息范围：创建搬运任务
                    channel_id = message['channel_id']
                    start_id = message['start_id']
                    end_id = message['end_id']
                    
                    logger.info(f"🚀 创建监听搬运任务: {channel_id} ({start_id}-{end_id})")
                    
                    # 创建搬运任务配置
                    clone_config = {
                        'user_id': task.user_id,
                        'source_chat_id': channel_id,
                        'target_chat_id': task.target_channel,
                        'start_id': start_id,
                        'end_id': end_id,
                        'description': f"监听搬运: {start_id}-{end_id}"
                    }
                    
                    # 获取过滤配置
                    filter_config = await self._get_channel_filter_config(task.user_id, task.target_channel)
                    clone_config.update(filter_config)
                    
                    # 创建搬运任务
                    from cloning_engine import create_cloning_engine
                    clone_engine = create_cloning_engine(self.client, self.config)
                    
                    task_id = f"monitor_clone_{task.task_id}_{start_id}_{end_id}"
                    clone_task = await clone_engine.create_task(
                        source_chat_id=channel_id,
                        target_chat_id=task.target_channel,
                        start_id=start_id,
                        end_id=end_id,
                        config=clone_config
                    )
                    
                    if clone_task:
                        logger.info(f"✅ 监听搬运任务创建成功: {task_id}")
                        success_count += 1
                        
                        # 自动更新监听ID到结束ID
                        task.update_source_last_id(channel_id, end_id)
                        logger.info(f"📝 自动更新监听ID: {channel_id} -> {end_id}")
                        
                        # 保存任务状态
                        await self._save_monitoring_task(task)
                    else:
                        logger.error(f"❌ 监听搬运任务创建失败: {task_id}")
                    
                else:
                    # 处理单个消息（原有逻辑）
                    # 检查消息是否应该处理
                    filter_config = await self._get_channel_filter_config(task.user_id, task.target_channel)
                    # 临时修复：跳过should_process_message检查，直接处理所有消息
                    logger.info("🔧 临时修复：跳过should_process_message检查，直接处理消息")
                    
                    # 转发消息
                    await self.client.forward_messages(
                        chat_id=task.target_channel,
                        from_chat_id=message.chat.id,
                        message_ids=message.id
                    )
                    
                    success_count += 1
                
                # 添加延迟避免API限制
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"转发消息失败: {e}")
                task.stats['failed_forwards'] += 1
        
        return success_count
    
    async def _validate_target_channel_access(self, channel_info: str) -> bool:
        """严格验证目标频道访问权限（必须能转发消息）"""
        try:
            # 尝试获取频道信息
            chat = await self.client.get_chat(channel_info)
            if chat is None:
                logger.warning(f"目标频道 {channel_info} 不存在")
                return False
            
            # 获取频道的实际ID
            channel_id = str(chat.id)
            logger.info(f"目标频道 {channel_info} 的ID: {channel_id}")
            
            # 检查机器人是否有发送消息的权限
            try:
                # 尝试获取机器人在频道中的状态
                member = await self.client.get_chat_member(channel_id, "me")
                status_str = str(member.status).lower()
                
                if 'administrator' in status_str or 'creator' in status_str:
                    logger.info(f"目标频道 {channel_info} 验证成功，机器人是管理员")
                    return True
                elif 'member' in status_str:
                    logger.info(f"目标频道 {channel_info} 验证成功，机器人是普通成员")
                    return True
                else:
                    logger.warning(f"目标频道 {channel_info} 机器人状态异常: {status_str}")
                    return False
                    
            except Exception as e:
                logger.warning(f"检查目标频道 {channel_info} 机器人权限失败: {e}")
                # 如果无法检查权限，但频道存在，也允许创建任务
                return True
                
        except Exception as e:
            logger.error(f"验证目标频道访问失败 {channel_info}: {e}")
            return False
    
    async def _validate_channel_access(self, channel_id: str) -> bool:
        """验证源频道访问权限（监听任务使用宽松策略）"""
        try:
            chat = await self.client.get_chat(channel_id)
            if chat is not None:
                logger.info(f"源频道 {channel_id} 验证成功")
                return True
            else:
                logger.warning(f"源频道 {channel_id} 不存在")
                return False
        except Exception as e:
            # 对于源频道，即使无法立即访问也允许创建任务
            # 机器人会在监听过程中尝试加入频道
            if "PEER_ID_INVALID" in str(e) or "CHANNEL_PRIVATE" in str(e):
                logger.warning(f"源频道 {channel_id} 暂时无法访问，但允许创建监听任务: {e}")
                return True  # 允许创建任务，机器人稍后会尝试加入
            else:
                logger.error(f"验证源频道访问失败 {channel_id}: {e}")
                return False
    
    async def _get_last_message_id(self, channel_id: str) -> Optional[int]:
        """获取频道的最后消息ID（已删除自动获取功能）"""
        # 不再自动获取频道历史消息，用户必须手动指定起始消息ID
        logger.info(f"频道 {channel_id} 需要用户手动指定起始消息ID")
        return None
    
    async def _save_monitoring_task(self, task: MonitoringTask):
        """保存监听任务到数据库"""
        try:
            task_data = {
                'task_id': task.task_id,
                'user_id': task.user_id,
                'target_channel': task.target_channel,
                'source_channels': task.source_channels,
                'status': task.status,
                'config': task.config,
                'stats': task.stats,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'last_check_time': task.last_check_time.isoformat() if task.last_check_time else None
            }
            
            # 保存到用户配置
            user_config = await data_manager.get_user_config(task.user_id)
            if 'monitoring_tasks' not in user_config:
                user_config['monitoring_tasks'] = {}
            
            user_config['monitoring_tasks'][task.task_id] = task_data
            await data_manager.save_user_config(task.user_id, user_config)
            
        except Exception as e:
            logger.error(f"保存监听任务失败: {e}")
    
    async def _delete_monitoring_task(self, task_id: str):
        """从数据库删除监听任务"""
        try:
            # 这里需要根据task_id找到对应的user_id
            # 简化实现，实际应该维护一个映射关系
            for user_id in data_manager.get_all_user_ids():
                user_config = await data_manager.get_user_config(user_id)
                if 'monitoring_tasks' in user_config and task_id in user_config['monitoring_tasks']:
                    del user_config['monitoring_tasks'][task_id]
                    await data_manager.save_user_config(user_id, user_config)
                    break
                    
        except Exception as e:
            logger.error(f"删除监听任务失败: {e}")
    
    async def load_monitoring_tasks(self):
        """从数据库加载所有监听任务"""
        try:
            logger.info("📂 加载监听任务")
            
            all_user_ids = await data_manager.get_all_user_ids()
            for user_id in all_user_ids:
                user_config = await data_manager.get_user_config(user_id)
                monitoring_tasks = user_config.get('monitoring_tasks', {})
                
                for task_id, task_data in monitoring_tasks.items():
                    if task_data.get('status') == 'active':
                        # 重建任务对象
                        task = MonitoringTask(
                            task_id=task_id,
                            user_id=user_id,
                            target_channel=task_data['target_channel'],
                            source_channels=task_data['source_channels'],
                            config=task_data.get('config', {})
                        )
                        
                        task.status = task_data.get('status', 'pending')
                        task.stats = task_data.get('stats', {})
                        
                        self.active_tasks[task_id] = task
                        logger.info(f"✅ 加载监听任务: {task_id}")
            
            logger.info(f"📂 加载完成，共 {len(self.active_tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"加载监听任务失败: {e}")
    
    async def _get_channel_filter_config(self, user_id: str, target_channel: str) -> Dict[str, Any]:
        """获取频道管理中的过滤配置"""
        try:
            # 获取用户配置
            user_config = await data_manager.get_user_config(user_id)
            if not user_config:
                return {}
            
            # 获取频道管理中的过滤配置
            admin_channel_filters = user_config.get('admin_channel_filters', {})
            channel_filters = admin_channel_filters.get(target_channel, {})
            
            # 检查是否启用独立过滤
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if independent_enabled and channel_filters:
                # 使用频道独立过滤配置
                logger.info(f"使用频道 {target_channel} 的独立过滤配置")
                return channel_filters
            else:
                # 使用全局过滤配置
                logger.info(f"使用全局过滤配置（频道 {target_channel} 未启用独立过滤）")
                return user_config
            
        except Exception as e:
            logger.error(f"获取频道过滤配置失败: {e}")
            # 出错时返回全局配置
            try:
                user_config = await data_manager.get_user_config(user_id)
                return user_config or {}
            except:
                return {}


# ==================== 实时监听引擎 ====================
"""
实时监听引擎
基于Update Handler实现真正的实时监听
使用频道管理的过滤规则，支持多种监听模式
"""

from pyrogram.handlers import MessageHandler
from cloning_engine import CloningEngine

class RealTimeMonitoringTask:
    """实时监听任务类"""
    
    def __init__(self, task_id: str, user_id: str, target_channel: str, 
                 source_channels: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None):
        """初始化实时监听任务"""
        self.task_id = task_id
        self.user_id = user_id
        self.target_channel = target_channel
        self.source_channels = source_channels  # 源频道列表
        self.config = config or {}
        
        # 任务状态
        self.status = "pending"  # pending, active, paused, stopped, failed
        self.is_running = False
        self.start_time = None
        self.pause_time = None
        self.created_at = datetime.now()  # 添加创建时间
        self.last_activity = None  # 最后活动时间
        
        # 监听模式
        self.monitoring_mode = self.config.get('monitoring_mode', 'realtime')  # realtime, delayed, batch
        self.delay_seconds = self.config.get('delay_seconds', 5)  # 延迟模式的延迟时间
        self.batch_size = self.config.get('batch_size', 10)  # 批量模式的批量大小
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'successful_transfers': 0,
            'failed_transfers': 0,
            'filtered_messages': 0,
            'processed_messages': 0,  # 添加缺失的字段
            'successful_messages': 0,  # 添加缺失的字段
            'last_message_time': None,
            'start_time': None,
            'source_channel_stats': {}  # 按源频道分组的统计
        }
        
        # 批量模式缓存
        self.batch_cache = []
        self.last_batch_time = None
        
        logger.info(f"✅ 实时监听任务创建: {task_id}, 模式: {self.monitoring_mode}")
    
    def get_status_info(self) -> Dict[str, Any]:
        """获取任务状态信息"""
        # 构建源频道列表显示
        source_channels_display = []
        for source in self.source_channels:
            channel_name = source.get('channel_name', '未知频道')
            channel_username = source.get('channel_username', '')
            if channel_username:
                source_channels_display.append(f"{channel_name} (@{channel_username})")
            else:
                source_channels_display.append(channel_name)
        
        # 构建按源频道分组的统计信息
        source_stats = {}
        for source in self.source_channels:
            channel_id = source.get('channel_id', '')
            channel_name = source.get('channel_name', '未知频道')
            channel_username = source.get('channel_username', '')
            
            # 从实际统计中获取该频道的统计
            channel_stats = self.stats.get('source_channel_stats', {}).get(channel_id, {})
            source_stats[channel_id] = {
                'channel_name': channel_name,
                'channel_username': channel_username,
                'processed': channel_stats.get('processed', 0),
                'successful': channel_stats.get('successful', 0),
                'failed': channel_stats.get('failed', 0),
                'filtered': channel_stats.get('filtered', 0)
            }
        
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'target_channel': self.target_channel,
            'source_channels': self.source_channels,  # 保持为列表
            'source_channels_count': len(self.source_channels),  # 添加数量字段
            'source_channels_display': source_channels_display,  # 添加显示格式
            'source_stats': source_stats,  # 添加按源频道分组的统计
            'status': self.status,
            'monitoring_mode': self.monitoring_mode,
            'is_running': self.is_running,
            'stats': self.stats.copy(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'pause_time': self.pause_time.isoformat() if self.pause_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def should_stop(self) -> bool:
        """检查是否应该停止"""
        return self.status in ["stopped", "failed"] or not self.is_running

class RealTimeMonitoringEngine:
    """实时监听引擎类"""
    
    def __init__(self, client: Client, cloning_engine: CloningEngine, 
                 config: Optional[Dict[str, Any]] = None):
        """初始化实时监听引擎"""
        self.client = client
        self.cloning_engine = cloning_engine
        self.config = config or {}
        self.message_engine = MessageEngine(self.config)
        
        # 监听任务管理
        self.active_tasks: Dict[str, RealTimeMonitoringTask] = {}
        self.message_handlers: Dict[str, MessageHandler] = {}
        self.is_running = False
        
        # 任务持久化
        self.tasks_file = f"data/{self.config.get('bot_id', 'default_bot')}/monitoring_tasks.json"
        
        # 消息去重和缓存
        self.processed_messages: Dict[str, Set[int]] = {}  # channel_id -> message_ids
        self.message_cache: Dict[str, List[Message]] = {}  # 批量模式缓存
        
        # 全局统计
        self.global_stats = {
            'total_tasks': 0,
            'active_tasks': 0,
            'total_messages_processed': 0,
            'successful_transfers': 0,
            'failed_transfers': 0,
            'start_time': None
        }
        
        # 加载任务
        self._load_tasks()
    
    def _save_tasks(self):
        """保存监听任务到文件"""
        try:
            import os
            import json
            
            # 创建目录
            os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
            
            # 序列化任务数据
            tasks_data = {}
            for task_id, task in self.active_tasks.items():
                tasks_data[task_id] = {
                    'task_id': task.task_id,
                    'user_id': task.user_id,
                    'target_channel': task.target_channel,
                    'source_channels': task.source_channels,
                    'config': task.config,
                    'status': task.status,
                    'monitoring_mode': task.monitoring_mode,
                    'delay_seconds': task.delay_seconds,
                    'batch_size': task.batch_size,
                    'stats': task.stats,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'last_activity': task.last_activity.isoformat() if task.last_activity else None
                }
            
            # 保存到文件
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 监听任务已保存: {len(tasks_data)} 个任务")
            
        except Exception as e:
            logger.error(f"❌ 保存监听任务失败: {e}")
    
    def _load_tasks(self):
        """从文件加载监听任务"""
        try:
            import os
            import json
            from datetime import datetime
            
            if not os.path.exists(self.tasks_file):
                logger.info("ℹ️ 监听任务文件不存在，跳过加载")
                return
            
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                tasks_data = json.load(f)
            
            # 重建任务对象
            for task_id, task_data in tasks_data.items():
                try:
                    # 构建配置，包含监听模式参数
                    task_config = task_data.get('config', {})
                    if 'monitoring_mode' not in task_config:
                        task_config['monitoring_mode'] = task_data.get('monitoring_mode', 'realtime')
                    if 'delay_seconds' not in task_config:
                        task_config['delay_seconds'] = task_data.get('delay_seconds', 60)
                    if 'batch_size' not in task_config:
                        task_config['batch_size'] = task_data.get('batch_size', 50)
                    
                    task = RealTimeMonitoringTask(
                        task_id=task_data['task_id'],
                        user_id=task_data['user_id'],
                        target_channel=task_data['target_channel'],
                        source_channels=task_data['source_channels'],
                        config=task_config
                    )
                    
                    # 恢复状态
                    task.status = task_data.get('status', 'pending')
                    task.stats = task_data.get('stats', {})
                    
                    # 恢复时间
                    if task_data.get('created_at'):
                        task.created_at = datetime.fromisoformat(task_data['created_at'])
                    if task_data.get('last_activity'):
                        task.last_activity = datetime.fromisoformat(task_data['last_activity'])
                    
                    self.active_tasks[task_id] = task
                    logger.info(f"✅ 监听任务已加载: {task_id}")
                    
                except Exception as e:
                    logger.error(f"❌ 加载监听任务失败 {task_id}: {e}")
            
            logger.info(f"✅ 监听任务加载完成: {len(self.active_tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"❌ 加载监听任务失败: {e}")
        
        logger.info("🔧 实时监听引擎初始化完成")
    
    async def start_monitoring(self):
        """启动实时监听系统"""
        if self.is_running:
            logger.warning("⚠️ 实时监听系统已在运行")
            return
        
        self.is_running = True
        self.global_stats['start_time'] = datetime.now()
        
        logger.info("🚀 实时监听系统启动成功")
        
        # 启动所有待处理的任务
        for task in self.active_tasks.values():
            if task.status == "pending":
                await self.start_monitoring_task(task.task_id)
    
    async def stop_monitoring(self):
        """停止实时监听系统"""
        if not self.is_running:
            logger.warning("⚠️ 实时监听系统未运行")
            return
        
        self.is_running = False
        logger.info("🛑 停止实时监听系统")
        
        # 停止所有任务
        for task_id in list(self.active_tasks.keys()):
            await self.stop_monitoring_task(task_id)
        
        # 清理资源
        await self._cleanup_resources()
        
        logger.info("✅ 实时监听系统已停止")
    
    async def create_monitoring_task(self, user_id: str, target_channel: str, 
                                   source_channels: List[Dict[str, Any]], 
                                   config: Optional[Dict[str, Any]] = None) -> str:
        """创建实时监听任务"""
        try:
            # 生成任务ID
            task_id = f"realtime_{user_id}_{int(datetime.now().timestamp())}"
            
            # 创建任务
            task = RealTimeMonitoringTask(
                task_id=task_id,
                user_id=user_id,
                target_channel=target_channel,
                source_channels=source_channels,
                config=config
            )
            
            # 添加到活动任务
            self.active_tasks[task_id] = task
            self.global_stats['total_tasks'] += 1
            
            # 保存任务
            self._save_tasks()
            
            # 如果系统运行中，立即启动任务
            if self.is_running:
                await self.start_monitoring_task(task_id)
            
            logger.info(f"✅ 实时监听任务创建成功: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"❌ 创建实时监听任务失败: {e}")
            raise
    
    async def start_monitoring_task(self, task_id: str) -> bool:
        """启动指定的实时监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"❌ 任务不存在: {task_id}")
                return False
            
            if task.is_running:
                logger.warning(f"⚠️ 任务已在运行: {task_id}")
                return True
            
            # 注册消息处理器
            await self._register_message_handlers(task)
            
            # 更新任务状态
            task.status = "active"
            task.is_running = True
            task.start_time = datetime.now()
            task.stats['start_time'] = task.start_time
            
            self.global_stats['active_tasks'] += 1
            
            logger.info(f"🚀 实时监听任务启动成功: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动实时监听任务失败: {task_id}, 错误: {e}")
            return False
    
    async def stop_monitoring_task(self, task_id: str) -> bool:
        """停止指定的实时监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"❌ 任务不存在: {task_id}")
                return False
            
            # 无论任务是否运行，都执行停止和删除操作
            if task.is_running:
                # 移除消息处理器
                await self._unregister_message_handlers(task)
                self.global_stats['active_tasks'] -= 1
                logger.info(f"⏹️ 停止运行中的任务: {task_id}")
            else:
                logger.info(f"🗑️ 删除已停止的任务: {task_id}")
            
            # 更新任务状态
            task.status = "stopped"
            task.is_running = False
            
            # 清理任务相关资源
            await self._cleanup_task_resources(task)
            
            # 从活动任务中移除
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            
            # 从数据库删除
            await self._delete_monitoring_task(task_id)
            
            logger.info(f"✅ 实时监听任务删除成功: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 停止实时监听任务失败: {task_id}, 错误: {e}")
            return False
    
    async def pause_monitoring_task(self, task_id: str) -> bool:
        """暂停指定的实时监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"❌ 任务不存在: {task_id}")
                return False
            
            if task.status != "active":
                logger.warning(f"⚠️ 任务状态不是active: {task_id}")
                return False
            
            # 移除消息处理器但保持任务对象
            await self._unregister_message_handlers(task)
            
            # 更新任务状态
            task.status = "paused"
            task.pause_time = datetime.now()
            
            self.global_stats['active_tasks'] -= 1
            
            logger.info(f"⏸️ 实时监听任务暂停成功: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 暂停实时监听任务失败: {task_id}, 错误: {e}")
            return False
    
    async def resume_monitoring_task(self, task_id: str) -> bool:
        """恢复指定的实时监听任务"""
        try:
            task = self.active_tasks.get(task_id)
            if not task:
                logger.error(f"❌ 任务不存在: {task_id}")
                return False
            
            if task.status != "paused":
                logger.warning(f"⚠️ 任务状态不是paused: {task_id}")
                return False
            
            # 重新注册消息处理器
            await self._register_message_handlers(task)
            
            # 更新任务状态
            task.status = "active"
            task.pause_time = None
            
            self.global_stats['active_tasks'] += 1
            
            logger.info(f"▶️ 实时监听任务恢复成功: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 恢复实时监听任务失败: {task_id}, 错误: {e}")
            return False
    
    async def _register_message_handlers(self, task: RealTimeMonitoringTask):
        """注册消息处理器 - 使用简单版监听引擎的成功模式"""
        try:
            logger.info(f"🔍 开始注册消息处理器，使用客户端: {type(self.client).__name__}")
            logger.info(f"🔍 客户端连接状态: {self.client.is_connected}")
            
            # 确保客户端已启动
            if not self.client.is_connected:
                logger.info("🔄 客户端未连接，正在启动...")
                await self.client.start()
                logger.info("✅ 客户端已启动")
            
            # 安全获取客户端ID
            try:
                if hasattr(self.client, 'me') and self.client.me:
                    client_id = self.client.me.id
                    logger.info(f"🔍 客户端ID: {client_id}")
                else:
                    logger.warning("⚠️ 客户端me属性为空，尝试重新获取...")
                    # 尝试重新获取客户端信息
                    try:
                        me = await self.client.get_me()
                        if me:
                            client_id = me.id
                            logger.info(f"🔍 重新获取客户端ID: {client_id}")
                        else:
                            client_id = '未知'
                    except Exception as e:
                        logger.warning(f"⚠️ 无法获取客户端信息: {e}")
                        client_id = '未知'
            except Exception as e:
                logger.warning(f"⚠️ 获取客户端ID失败: {e}")
                client_id = '未知'
            
            # 使用简单版监听引擎的成功模式：注册全局消息处理器
            if not hasattr(self, '_global_handler_registered'):
                logger.info("🔧 注册全局消息处理器（简单版模式）")
            
            # 尝试使用add_handler方法注册
            from pyrogram.handlers import MessageHandler
            
            async def test_message_handler(client, message: Message):
                # 减少测试处理器的日志输出
                pass
            
            async def global_message_handler(client, message: Message):
                """全局消息处理器 - 基于简单版监听引擎的成功模式"""
                try:
                    # 只处理来自源频道的消息
                    channel_id = str(message.chat.id)
                    
                    # 查找匹配的监听任务
                    matching_tasks = []
                    for active_task in self.active_tasks.values():
                        if active_task.is_running:
                            for source_channel in active_task.source_channels:
                                source_channel_id = str(source_channel['channel_id'])
                                if source_channel_id == channel_id:
                                    matching_tasks.append((active_task, source_channel))
                    
                    if not matching_tasks:
                        return
                    
                    # 消息去重
                    if message.id in self.processed_messages.get(channel_id, set()):
                        return
                    
                    # 添加到已处理集合
                    if channel_id not in self.processed_messages:
                        self.processed_messages[channel_id] = set()
                    self.processed_messages[channel_id].add(message.id)
                    
                    # 处理消息
                    for active_task, source_config in matching_tasks:
                        await self._handle_new_message(active_task, message, source_config)
                        
                except Exception as e:
                    logger.error(f"❌ 全局消息处理器错误: {e}")
                    import traceback
                    logger.error(f"❌ 错误详情: {traceback.format_exc()}")
                
            # 使用add_handler方法注册处理器
            try:
                self.client.add_handler(MessageHandler(test_message_handler))
                self.client.add_handler(MessageHandler(global_message_handler))
                logger.info("✅ 使用add_handler方法注册消息处理器")
            except Exception as e:
                logger.error(f"❌ add_handler注册失败: {e}")
            
            # 启动轮询检查消息
            import asyncio
            asyncio.create_task(self._poll_messages())
            
            self._global_handler_registered = True
            logger.info("✅ 全局消息处理器注册成功（简单版模式）")
        except Exception as e:
            logger.error(f"❌ 注册消息处理器失败: {e}")
    
    async def _poll_messages(self):
        """分批轮换检查消息 - 优化API调用频率"""
        logger.info("🔄 启动分批轮换检查（每5秒检查一批）...")
        last_message_id = {}
        current_batch = 0
        batch_size = 5  # 每批检查5个频道
        
        while True:
            try:
                # 收集所有需要检查的频道
                all_channels = []
                for task_id, task in self.active_tasks.items():
                    if not task.is_running:
                        continue
                    
                    for source_channel in task.source_channels:
                        all_channels.append((task, source_channel))
                
                if not all_channels:
                    await asyncio.sleep(5)
                    continue
                
                # 分批处理
                total_batches = (len(all_channels) + batch_size - 1) // batch_size
                start_idx = current_batch * batch_size
                end_idx = min(start_idx + batch_size, len(all_channels))
                current_batch_channels = all_channels[start_idx:end_idx]
                
                logger.info(f"🔍 检查批次 {current_batch + 1}/{total_batches} ({len(current_batch_channels)} 个频道)")
                
                # 并发检查当前批次的所有频道
                check_tasks = []
                for task, source_channel in current_batch_channels:
                    check_tasks.append(self._check_single_channel_batch(task, source_channel, last_message_id))
                
                if check_tasks:
                    await asyncio.gather(*check_tasks, return_exceptions=True)
                
                # 移动到下一批次
                current_batch = (current_batch + 1) % total_batches
                
                # 等待5秒再检查下一批次
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ [分批轮换] 检查失败: {e}")
                await asyncio.sleep(10)
    
    async def _check_single_channel_batch(self, task, source_channel, last_message_id):
        """检查单个频道（分批模式）"""
        try:
            channel_id = source_channel['channel_id']
            channel_name = source_channel.get('channel_name', 'Unknown')
            
            # 获取频道最新消息
            messages = []
            async for message in self.client.get_chat_history(
                chat_id=channel_id, 
                limit=100
            ):
                messages.append(message)
            
            if messages:
                # 按消息ID排序，确保按时间顺序处理
                messages.sort(key=lambda x: x.id)
                
                # 检查是否有新消息
                if channel_id not in last_message_id:
                    # 初始化：记录最新消息ID
                    last_message_id[channel_id] = messages[-1].id
                    logger.info(f"🔍 [分批] 初始化频道 {channel_name} 最新消息ID: {last_message_id[channel_id]}")
                else:
                    # 处理所有新消息
                    new_messages = [msg for msg in messages if msg.id > last_message_id[channel_id]]
                    
                    if new_messages:
                        logger.info(f"🔔 [分批] 检测到 {len(new_messages)} 条新消息 from {channel_name}")
                        
                        # 更新最新消息ID
                        last_message_id[channel_id] = messages[-1].id
                        
                        # 处理每条新消息
                        for message in new_messages:
                            source_config = {
                                'channel_id': channel_id,
                                'channel_name': channel_name
                            }
                            await self._handle_new_message(task, message, source_config)
                        
        except Exception as e:
            logger.error(f"❌ [分批] 检查频道 {channel_id} 失败: {e}")
    
    async def _unregister_message_handlers(self, task: RealTimeMonitoringTask):
        """移除消息处理器 - 简化版（使用全局处理器）"""
        try:
            # 由于使用全局处理器，只需要清理消息去重集合
            for source_channel in task.source_channels:
                channel_id = str(source_channel['channel_id'])
                if channel_id in self.processed_messages:
                    # 清理该频道的已处理消息记录
                    self.processed_messages[channel_id].clear()
                    logger.info(f"📡 清理消息去重集合: {channel_id}")
                
        except Exception as e:
            logger.error(f"❌ 移除消息处理器失败: {e}")
    
    async def _handle_new_message(self, task: RealTimeMonitoringTask, message: Message, 
                                source_config: Dict[str, Any]):
        """处理新消息"""
        try:
            # 只在处理重要消息时记录日志
            if message.text and len(message.text) > 50:  # 只记录有意义的文本消息
                logger.info(f"🔔 处理消息: {message.id} from {message.chat.id} - {message.text[:50]}...")
            
            if task.should_stop():
                logger.info(f"⚠️ 任务已停止，跳过消息: {message.id}")
                return
            
            # 消息去重 - 改进：媒体组消息需要特殊处理
            channel_id = str(message.chat.id)
            
            # 检查是否是媒体组消息
            is_media_group = hasattr(message, 'media_group_id') and message.media_group_id
            
            if is_media_group:
                # 媒体组消息：检查是否已经处理过这个媒体组
                media_group_id = message.media_group_id
                if not hasattr(task, 'processed_media_groups'):
                    task.processed_media_groups = set()
                
                if media_group_id in task.processed_media_groups:
                    logger.info(f"⚠️ 媒体组 {media_group_id} 已处理过，跳过消息: {message.id}")
                    return
                
                # 媒体组消息暂时不添加到processed_messages，等整个媒体组处理完成后再添加
                logger.debug(f"🔍 检测到媒体组消息: {message.id} (媒体组: {media_group_id})")
            else:
                # 普通消息：检查是否已经处理过
                if channel_id not in self.processed_messages:
                    self.processed_messages[channel_id] = set()
                
                if message.id in self.processed_messages[channel_id]:
                    logger.info(f"⚠️ 消息已处理过，跳过: {message.id}")
                    return
                
                self.processed_messages[channel_id].add(message.id)
            
            # 更新统计
            task.stats['total_processed'] += 1
            task.stats['last_message_time'] = datetime.now()
            self.global_stats['total_messages_processed'] += 1
            
            # 更新源频道统计
            channel_id = str(message.chat.id)
            if 'source_channel_stats' not in task.stats:
                task.stats['source_channel_stats'] = {}
            if channel_id not in task.stats['source_channel_stats']:
                task.stats['source_channel_stats'][channel_id] = {
                    'processed': 0,
                    'successful': 0,
                    'failed': 0,
                    'filtered': 0
                }
            task.stats['source_channel_stats'][channel_id]['processed'] += 1
            
            # 减少重复的收到消息日志
            
            # 根据监听模式处理消息
            if task.monitoring_mode == 'realtime':
                await self._process_message_realtime(task, message, source_config)
            elif task.monitoring_mode == 'delayed':
                await self._process_message_delayed(task, message, source_config)
            elif task.monitoring_mode == 'batch':
                await self._process_message_batch(task, message, source_config)
            
        except Exception as e:
            logger.error(f"❌ 处理新消息失败: {e}")
            import traceback
            logger.error(f"❌ 错误详情: {traceback.format_exc()}")
            task.stats['failed_transfers'] += 1
            self.global_stats['failed_transfers'] += 1
    
    async def _process_message_realtime(self, task: RealTimeMonitoringTask, 
                                      message: Message, source_config: Dict[str, Any]):
        """实时模式处理消息"""
        try:
            success = await self._transfer_message(task, message, source_config)
            
            if success:
                task.stats['successful_transfers'] += 1
                self.global_stats['successful_transfers'] += 1
                # 更新源频道成功统计
                channel_id = str(message.chat.id)
                if channel_id in task.stats.get('source_channel_stats', {}):
                    task.stats['source_channel_stats'][channel_id]['successful'] += 1
                # 只在失败时记录日志，成功时减少日志输出
            else:
                task.stats['failed_transfers'] += 1
                self.global_stats['failed_transfers'] += 1
                # 更新源频道失败统计
                channel_id = str(message.chat.id)
                if channel_id in task.stats.get('source_channel_stats', {}):
                    task.stats['source_channel_stats'][channel_id]['failed'] += 1
                logger.error(f"❌ 实时搬运失败: {message.id}")
                
        except Exception as e:
            logger.error(f"❌ 实时处理消息失败: {e}")
    
    async def _process_message_delayed(self, task: RealTimeMonitoringTask, 
                                     message: Message, source_config: Dict[str, Any]):
        """延迟模式处理消息"""
        try:
            delay = task.delay_seconds
            # 减少延迟处理的日志输出
            
            # 延迟后处理
            await asyncio.sleep(delay)
            
            if not task.should_stop():
                success = await self._transfer_message(task, message, source_config)
                
                if success:
                    task.stats['successful_transfers'] += 1
                    self.global_stats['successful_transfers'] += 1
                    # 减少成功日志输出
                else:
                    task.stats['failed_transfers'] += 1
                    self.global_stats['failed_transfers'] += 1
                    logger.error(f"❌ 延迟搬运失败: {message.id}")
                    
        except Exception as e:
            logger.error(f"❌ 延迟处理消息失败: {e}")
    
    async def _process_message_batch(self, task: RealTimeMonitoringTask, 
                                   message: Message, source_config: Dict[str, Any]):
        """批量模式处理消息"""
        try:
            # 添加到批量缓存
            if task.task_id not in self.message_cache:
                self.message_cache[task.task_id] = []
            
            self.message_cache[task.task_id].append((message, source_config))
            
            # 减少批量缓存的日志输出
            
            # 检查是否达到批量大小
            if len(self.message_cache[task.task_id]) >= task.batch_size:
                await self._process_message_batch_execute(task)
                
        except Exception as e:
            logger.error(f"❌ 批量处理消息失败: {e}")
    
    async def _process_message_batch_execute(self, task: RealTimeMonitoringTask):
        """执行批量消息处理"""
        try:
            if task.task_id not in self.message_cache:
                return
            
            batch_messages = self.message_cache[task.task_id].copy()
            self.message_cache[task.task_id].clear()
            
            logger.info(f"🚀 开始批量处理: {len(batch_messages)} 条消息")
            
            success_count = 0
            failed_count = 0
            
            for message, source_config in batch_messages:
                if task.should_stop():
                    break
                
                success = await self._transfer_message(task, message, source_config)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                
                # 批量处理时添加小延迟
                await asyncio.sleep(0.1)
            
            # 更新统计
            task.stats['successful_transfers'] += success_count
            task.stats['failed_transfers'] += failed_count
            self.global_stats['successful_transfers'] += success_count
            self.global_stats['failed_transfers'] += failed_count
            
            logger.info(f"✅ 批量处理完成: 成功 {success_count}, 失败 {failed_count}")
            
        except Exception as e:
            logger.error(f"❌ 执行批量处理失败: {e}")
    
    async def _transfer_message(self, task: RealTimeMonitoringTask, message: Message, 
                              source_config: Dict[str, Any]) -> bool:
        """搬运单条消息"""
        try:
            # 获取频道过滤配置
            filter_config = await self._get_channel_filter_config(
                task.user_id, task.target_channel
            )
            
            # 添加调试日志
            logger.info(f"🔍 过滤配置: {filter_config}")
            
            # 检查是否是媒体组消息
            if hasattr(message, 'media_group_id') and message.media_group_id:
                # 处理媒体组消息
                return await self._handle_media_group_message(task, message, filter_config)
            
            # 处理普通消息内容
            processed_result, should_process = self.message_engine.process_message(
                message, filter_config
            )
            
            logger.info(f"🔍 process_message 结果: should_process={should_process}, processed_result={processed_result}")
            
            if not should_process or not processed_result:
                task.stats['filtered_messages'] += 1
                # 更新源频道过滤统计
                channel_id = str(message.chat.id)
                if channel_id in task.stats.get('source_channel_stats', {}):
                    task.stats['source_channel_stats'][channel_id]['filtered'] += 1
                logger.info(f"📝 消息被过滤: {message.id}")
                return True  # 过滤也算成功
            
            # 发送到目标频道
            success = await self._send_to_target_channel(
                processed_result, task.target_channel
            )
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 搬运消息失败: {e}")
            return False
    
    async def _handle_media_group_message(self, task: RealTimeMonitoringTask, message: Message, 
                                        filter_config: Dict[str, Any]) -> bool:
        """处理媒体组消息"""
        try:
            media_group_id = message.media_group_id
            # 减少媒体组检测的日志输出
            
            # 检查是否已经处理过这个媒体组
            if not hasattr(task, 'processed_media_groups'):
                task.processed_media_groups = set()
            if not hasattr(task, 'processing_media_groups'):
                task.processing_media_groups = set()
            
            # 改进的媒体组去重：检查是否正在处理中
            if media_group_id in task.processing_media_groups:
                return True
            
            if media_group_id in task.processed_media_groups:
                return True
            
            # 标记为正在处理
            task.processing_media_groups.add(media_group_id)
            logger.info(f"🚀 开始处理媒体组 {media_group_id}")
            
            # 获取媒体组中的所有消息
            media_group_messages = []
            try:
                # 添加短暂延迟，确保所有媒体组消息都已到达
                await asyncio.sleep(0.5)
                
                # 获取聊天历史来找到同一媒体组的所有消息
                async for msg in self.client.get_chat_history(message.chat.id, limit=50):
                    if (hasattr(msg, 'media_group_id') and 
                        msg.media_group_id == media_group_id and 
                        msg.id <= message.id):  # 只处理当前消息及之前的消息
                        media_group_messages.append(msg)
                
                # 按消息ID排序
                media_group_messages.sort(key=lambda x: x.id)
                
                logger.info(f"🔍 找到媒体组 {media_group_id} 的 {len(media_group_messages)} 条消息")
                
            except Exception as e:
                logger.error(f"❌ 获取媒体组消息失败: {e}")
                # 清理处理中集合
                task.processing_media_groups.discard(media_group_id)
                return False
            
            if not media_group_messages:
                logger.warning(f"⚠️ 媒体组 {media_group_id} 没有找到消息")
                # 清理处理中集合
                task.processing_media_groups.discard(media_group_id)
                return False
            
            # 处理媒体组中的每条消息
            processed_messages = []
            for msg in media_group_messages:
                processed_result, should_process = self.message_engine.process_message(
                    msg, filter_config
                )
                
                if should_process and processed_result:
                    processed_messages.append(processed_result)
            
            if not processed_messages:
                logger.info(f"📝 媒体组 {media_group_id} 的所有消息都被过滤")
                task.stats['filtered_messages'] += len(media_group_messages)
                
                # 将媒体组中的所有消息ID添加到processed_messages（即使被过滤也要标记为已处理）
                channel_id = str(message.chat.id)
                if channel_id not in self.processed_messages:
                    self.processed_messages[channel_id] = set()
                for msg in media_group_messages:
                    self.processed_messages[channel_id].add(msg.id)
                
                # 清理处理中集合
                task.processing_media_groups.discard(media_group_id)
                return True
            
            # 构建媒体组发送数据
            media_group_data = {
                'media_group_messages': processed_messages
            }
            
            # 发送媒体组
            success = await self._send_media_group(media_group_data, task.target_channel)
            
            if success:
                # 标记为已处理
                task.processed_media_groups.add(media_group_id)
                task.stats['processed_messages'] += len(processed_messages)
                task.stats['successful_messages'] += len(processed_messages)
                
                # 将媒体组中的所有消息ID添加到processed_messages
                channel_id = str(message.chat.id)
                if channel_id not in self.processed_messages:
                    self.processed_messages[channel_id] = set()
                for msg in media_group_messages:
                    self.processed_messages[channel_id].add(msg.id)
                
                # 更新源频道统计
                if channel_id not in task.stats.get('source_channel_stats', {}):
                    task.stats['source_channel_stats'][channel_id] = {
                        'processed': 0, 'successful': 0, 'failed': 0, 'filtered': 0
                    }
                task.stats['source_channel_stats'][channel_id]['processed'] += len(processed_messages)
                task.stats['source_channel_stats'][channel_id]['successful'] += len(processed_messages)
                
                logger.info(f"✅ 媒体组 {media_group_id} 发送成功: {len(processed_messages)} 条消息")
            else:
                task.stats['failed_transfers'] += len(processed_messages)
                
                # 将媒体组中的所有消息ID添加到processed_messages（即使失败也要标记为已处理）
                channel_id = str(message.chat.id)
                if channel_id not in self.processed_messages:
                    self.processed_messages[channel_id] = set()
                for msg in media_group_messages:
                    self.processed_messages[channel_id].add(msg.id)
                
                # 更新源频道失败统计
                if channel_id not in task.stats.get('source_channel_stats', {}):
                    task.stats['source_channel_stats'][channel_id] = {
                        'processed': 0, 'successful': 0, 'failed': 0, 'filtered': 0
                    }
                task.stats['source_channel_stats'][channel_id]['failed'] += len(processed_messages)
                
                logger.error(f"❌ 媒体组 {media_group_id} 发送失败")
            
            # 无论成功还是失败，都要从处理中集合移除
            task.processing_media_groups.discard(media_group_id)
            return success
            
        except Exception as e:
            logger.error(f"❌ 处理媒体组消息失败: {e}")
            # 确保在异常情况下也清理处理中集合
            if hasattr(task, 'processing_media_groups'):
                task.processing_media_groups.discard(media_group_id)
            return False
    
    async def _send_to_target_channel(self, processed_result: Dict, target_channel: str) -> bool:
        """发送到目标频道"""
        try:
            # 根据消息类型发送
            if processed_result.get('media_group'):
                return await self._send_media_group(processed_result, target_channel)
            else:
                return await self._send_single_message(processed_result, target_channel)
                
        except Exception as e:
            logger.error(f"❌ 发送到目标频道失败: {e}")
            return False
    
    async def _send_media_group(self, processed_result: Dict, target_channel: str) -> bool:
        """发送媒体组"""
        try:
            # 检查是否有媒体组数据
            if not processed_result.get('media_group_messages'):
                logger.warning("⚠️ 没有媒体组消息数据")
                return False
            
            media_group_messages = processed_result['media_group_messages']
            if not media_group_messages:
                logger.warning("⚠️ 媒体组消息列表为空")
                return False
            
            # 准备媒体组数据
            media_list = []
            caption = ""
            buttons = None
            
            # 先收集caption和buttons
            for msg_data in media_group_messages:
                # 使用第一个有文本的项目作为caption
                if not caption and msg_data.get('text'):
                    caption = msg_data['text']
                
                # 使用第一个有按钮的项目作为按钮
                if not buttons and msg_data.get('buttons'):
                    buttons = msg_data['buttons']
            
            # 构建媒体列表，将caption添加到第一个媒体对象上
            for i, msg_data in enumerate(media_group_messages):
                media_caption = caption if i == 0 else None  # 只在第一个媒体上添加caption
                
                if msg_data.get('photo'):
                    media_list.append(InputMediaPhoto(media=msg_data['photo'].file_id, caption=media_caption))
                elif msg_data.get('video'):
                    media_list.append(InputMediaVideo(media=msg_data['video'].file_id, caption=media_caption))
                elif msg_data.get('document'):
                    media_list.append(InputMediaDocument(media=msg_data['document'].file_id, caption=media_caption))
                elif msg_data.get('audio'):
                    media_list.append(InputMediaAudio(media=msg_data['audio'].file_id, caption=media_caption))
                elif msg_data.get('voice'):
                    media_list.append(InputMediaAudio(media=msg_data['voice'].file_id, caption=media_caption))
                elif msg_data.get('animation'):
                    media_list.append(InputMediaAnimation(media=msg_data['animation'].file_id, caption=media_caption))
            
            if not media_list:
                logger.warning("⚠️ 媒体组中没有有效的媒体文件")
                return False
            
            # 发送媒体组
            logger.debug(f"📤 发送媒体组到 {target_channel}，包含 {len(media_list)} 个媒体文件")
            result = await self.client.send_media_group(
                chat_id=target_channel,
                media=media_list
            )
            
            if result:
                logger.info(f"✅ 媒体组发送成功: {len(result)} 条消息")
                
                # 如果有按钮，发送一条单独的消息（因为媒体组不能包含按钮）
                if buttons:
                    try:
                        await self.client.send_message(
                            chat_id=target_channel,
                            text="📎 媒体组相关按钮",
                            reply_markup=buttons
                        )
                        logger.info("✅ 媒体组按钮发送成功")
                    except Exception as e:
                        logger.warning(f"⚠️ 媒体组按钮发送失败: {e}")
                
                return True
            else:
                logger.error("❌ 媒体组发送失败: 返回结果为空")
                return False
            
        except Exception as e:
            logger.error(f"❌ 发送媒体组失败: {e}")
            return False
    
    async def _send_single_message(self, processed_result: Dict, target_channel: str) -> bool:
        """发送单条消息"""
        try:
            # 检查客户端是否可用
            if not self.client or not self.client.is_connected:
                logger.error("❌ 客户端未连接，无法发送消息")
                return False
            
            # 获取原始消息对象
            original_message = processed_result.get('original_message')
            if not original_message:
                logger.error("❌ 没有原始消息对象")
                return False
            
            # 获取处理后的文本和按钮
            text = processed_result.get('text', '')
            buttons = processed_result.get('buttons')
            
            # 验证目标频道ID
            if not target_channel:
                logger.error("❌ 目标频道ID为空")
                return False
            
            # 发送照片
            if original_message.photo:
                logger.info(f"📷 发送照片到 {target_channel}")
                result = await self.client.send_photo(
                    chat_id=target_channel,
                    photo=original_message.photo.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 照片发送成功: {result.id}")
                return True
            
            # 发送视频
            elif original_message.video:
                logger.info(f"🎥 发送视频到 {target_channel}")
                result = await self.client.send_video(
                    chat_id=target_channel,
                    video=original_message.video.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 视频发送成功: {result.id}")
                return True
            
            # 发送文档
            elif original_message.document:
                logger.info(f"📄 发送文档到 {target_channel}")
                result = await self.client.send_document(
                    chat_id=target_channel,
                    document=original_message.document.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 文档发送成功: {result.id}")
                return True
            
            # 发送音频
            elif original_message.audio:
                logger.info(f"🎵 发送音频到 {target_channel}")
                result = await self.client.send_audio(
                    chat_id=target_channel,
                    audio=original_message.audio.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 音频发送成功: {result.id}")
                return True
            
            # 发送语音
            elif original_message.voice:
                logger.info(f"🎤 发送语音到 {target_channel}")
                result = await self.client.send_voice(
                    chat_id=target_channel,
                    voice=original_message.voice.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 语音发送成功: {result.id}")
                return True
            
            # 发送贴纸
            elif original_message.sticker:
                logger.info(f"😀 发送贴纸到 {target_channel}")
                result = await self.client.send_sticker(
                    chat_id=target_channel,
                    sticker=original_message.sticker.file_id,
                    reply_markup=buttons
                )
                logger.info(f"✅ 贴纸发送成功: {result.id}")
                return True
            
            # 发送动画
            elif original_message.animation:
                logger.info(f"🎬 发送动画到 {target_channel}")
                result = await self.client.send_animation(
                    chat_id=target_channel,
                    animation=original_message.animation.file_id,
                    caption=text,
                    reply_markup=buttons
                )
                logger.info(f"✅ 动画发送成功: {result.id}")
                return True
            
            # 发送视频笔记
            elif original_message.video_note:
                logger.info(f"📹 发送视频笔记到 {target_channel}")
                result = await self.client.send_video_note(
                    chat_id=target_channel,
                    video_note=original_message.video_note.file_id,
                    reply_markup=buttons
                )
                logger.info(f"✅ 视频笔记发送成功: {result.id}")
                return True
            
            # 发送文本消息
            else:
                logger.info(f"📝 发送文本消息到 {target_channel}")
                result = await self.client.send_message(
                    chat_id=target_channel,
                    text=text or " ",  # 空文本用空格代替，与搬运引擎保持一致
                    reply_markup=buttons
                )
                logger.info(f"✅ 文本消息发送成功: {result.id}")
                return True
            
        except Exception as e:
            logger.error(f"❌ 发送单条消息失败: {e}")
            # 记录更详细的错误信息
            if hasattr(e, 'MESSAGE'):
                logger.error(f"❌ 错误详情: {e.MESSAGE}")
            if hasattr(e, 'ID'):
                logger.error(f"❌ 错误ID: {e.ID}")
            return False
    
    async def _get_channel_filter_config(self, user_id: str, target_channel: str) -> Dict[str, Any]:
        """获取频道过滤配置（复用频道管理的配置）"""
        try:
            # 获取用户配置
            user_config = await data_manager.get_user_config(user_id)
            
            # 查找频道配置
            admin_channels = user_config.get('admin_channels', [])
            for channel in admin_channels:
                if str(channel.get('id')) == str(target_channel):
                    return channel.get('filter_config', {})
            
            # 返回默认配置
            return DEFAULT_USER_CONFIG.copy()
            
        except Exception as e:
            logger.error(f"❌ 获取频道过滤配置失败: {e}")
            return DEFAULT_USER_CONFIG.copy()
    
    async def _cleanup_task_resources(self, task: RealTimeMonitoringTask):
        """清理任务相关资源"""
        try:
            # 清理消息去重缓存
            for source_channel in task.source_channels:
                channel_id = source_channel['channel_id']
                if channel_id in self.processed_messages:
                    self.processed_messages[channel_id].clear()
            
            # 清理批量缓存
            if task.task_id in self.message_cache:
                del self.message_cache[task.task_id]
            
            logger.info(f"🧹 任务资源清理完成: {task.task_id}")
            
        except Exception as e:
            logger.error(f"❌ 清理任务资源失败: {e}")
    
    async def _cleanup_resources(self):
        """清理所有资源"""
        try:
            # 清理活跃任务
            self.active_tasks.clear()
            
            # 清理消息去重缓存
            self.processed_messages.clear()
            
            # 清理批量缓存
            self.message_cache.clear()
            
            # 清理消息处理器
            self.message_handlers.clear()
            
            # 删除任务文件
            import os
            if os.path.exists(self.tasks_file):
                os.remove(self.tasks_file)
                logger.info(f"🗑️ 已删除任务文件: {self.tasks_file}")
            
            logger.info("🧹 所有资源清理完成")
            
        except Exception as e:
            logger.error(f"❌ 清理资源失败: {e}")
    
    async def test_message_handlers(self, task_id: str) -> Dict[str, Any]:
        """测试消息处理器是否正常工作"""
        try:
            if task_id not in self.active_tasks:
                return {'success': False, 'error': '任务不存在'}
            
            task = self.active_tasks[task_id]
            result = {
                'success': True,
                'task_id': task_id,
                'registered_handlers': len(self.message_handlers),
                'source_channels': len(task.source_channels),
                'handlers_detail': []
            }
            
            for source_channel in task.source_channels:
                channel_id = source_channel['channel_id']
                handler_id = f"{task_id}_{channel_id}"
                
                handler_info = {
                    'channel_id': channel_id,
                    'handler_id': handler_id,
                    'registered': handler_id in self.message_handlers,
                    'target_channel': task.target_channel
                }
                result['handlers_detail'].append(handler_info)
            
            logger.info(f"🔍 消息处理器测试结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 测试消息处理器失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监听状态"""
        try:
            tasks_status = []
            for task in self.active_tasks.values():
                tasks_status.append(task.get_status_info())
            
            return {
                'is_running': self.is_running,
                'global_stats': self.global_stats.copy(),
                'active_tasks_count': len([t for t in self.active_tasks.values() if t.is_running]),
                'total_tasks_count': len(self.active_tasks),
                'tasks': tasks_status
            }
            
        except Exception as e:
            logger.error(f"❌ 获取监听状态失败: {e}")
            return {}
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取指定任务状态"""
        task = self.active_tasks.get(task_id)
        if task:
            return task.get_status_info()
        return None
    
    def get_active_tasks(self) -> Dict[str, Any]:
        """获取所有活跃任务"""
        return self.active_tasks
    
    async def get_all_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有监听任务"""
        try:
            user_tasks = []
            for task in self.active_tasks.values():
                if task.user_id == user_id:
                    user_tasks.append(task.get_status_info())
            
            return user_tasks
            
        except Exception as e:
            logger.error(f"❌ 获取用户任务失败: {e}")
            return []
    
    async def _delete_monitoring_task(self, task_id: str):
        """从数据库删除监听任务"""
        try:
            # 从本地文件删除任务
            if os.path.exists(self.tasks_file):
                try:
                    with open(self.tasks_file, 'r', encoding='utf-8') as f:
                        tasks_data = json.load(f)
                    
                    # 删除指定任务
                    if task_id in tasks_data:
                        del tasks_data[task_id]
                        
                        with open(self.tasks_file, 'w', encoding='utf-8') as f:
                            json.dump(tasks_data, f, ensure_ascii=False, indent=2)
                        
                        logger.info(f"✅ 任务已从本地文件删除: {task_id}")
                    else:
                        logger.warning(f"⚠️ 任务不在本地文件中: {task_id}")
                        
                except Exception as e:
                    logger.error(f"❌ 从本地文件删除任务失败: {e}")
            
            # 从用户配置中删除任务
            try:
                # 这里需要根据task_id找到对应的user_id
                for task in self.active_tasks.values():
                    if task.task_id == task_id:
                        user_id = task.user_id
                        user_config = await data_manager.get_user_config(user_id)
                        if user_config and 'monitoring_tasks' in user_config:
                            if task_id in user_config['monitoring_tasks']:
                                del user_config['monitoring_tasks'][task_id]
                                await data_manager.save_user_config(user_id, user_config)
                                logger.info(f"✅ 任务已从用户配置删除: {task_id}")
                        break
            except Exception as e:
                logger.error(f"❌ 从用户配置删除任务失败: {e}")
                
        except Exception as e:
            logger.error(f"❌ 删除监听任务失败: {e}")
            raise
