# ==================== 简单监听引擎 ====================
"""
简单监听引擎
用于测试实时监听功能
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChannelPrivate, ChannelInvalid

# 配置日志
logger = logging.getLogger(__name__)

class SimpleMonitor:
    """简单监听器类"""
    
    def __init__(self, client: Client):
        """初始化简单监听器"""
        self.client = client
        self.monitoring_tasks = {}  # 存储监听任务
        self.is_running = False
        self._global_handler_registered = False
        self._client_id = id(client)  # 记录客户端ID
        logger.info(f"🔍 监听器初始化: client_id={self._client_id}")
        
    async def start_monitoring(self, source_channel: str, target_channel: str, user_id: int):
        """开始监听"""
        try:
            logger.info(f"🔍 开始监听: source={source_channel}, target={target_channel}, user={user_id}")
            
            # 解析频道信息
            parsed_source = self._parse_channel_info(source_channel)
            parsed_target = self._parse_channel_info(target_channel)
            
            if not parsed_source:
                return False, f"无效的源频道格式: {source_channel}"
            if not parsed_target:
                return False, f"无效的目标频道格式: {target_channel}"
            
            logger.info(f"🔍 解析后的频道: source={parsed_source}, target={parsed_target}")
            
            task_id = f"{user_id}_{parsed_source}_{parsed_target}"
            
            # 检查任务是否已存在
            if task_id in self.monitoring_tasks:
                logger.warning(f"⚠️ 监听任务已存在: {task_id}")
                return False, "监听任务已存在"
            
            # 验证频道
            try:
                logger.info(f"🔍 验证源频道: {parsed_source}")
                # 验证源频道
                source_chat = await self.client.get_chat(parsed_source)
                logger.info(f"✅ 源频道验证成功: {source_chat.title}")
                
                logger.info(f"🔍 验证目标频道: {parsed_target}")
                # 验证目标频道
                target_chat = await self.client.get_chat(parsed_target)
                logger.info(f"✅ 目标频道验证成功: {target_chat.title}")
                
            except Exception as e:
                logger.error(f"❌ 频道验证失败: {e}")
                return False, f"频道验证失败: {str(e)}"
            
            # 创建监听任务
            task_info = {
                'task_id': task_id,
                'user_id': user_id,
                'source_channel': parsed_source,
                'target_channel': parsed_target,
                'source_title': source_chat.title,
                'target_title': target_chat.title,
                'status': 'active',
                'message_count': 0
            }
            
            self.monitoring_tasks[task_id] = task_info
            
            # 注册消息处理器
            await self._register_message_handler(task_info)
            
            # 注册全局消息处理器（如果还没有注册）
            if not self._global_handler_registered:
                await self._register_global_handler()
                self._global_handler_registered = True
            
            logger.info(f"✅ 监听任务已启动: {source_channel} -> {target_channel}")
            return True, f"监听任务已启动: {source_chat.title} -> {target_chat.title}"
            
        except Exception as e:
            logger.error(f"启动监听失败: {e}")
            return False, f"启动监听失败: {str(e)}"
    
    async def stop_monitoring(self, task_id: str):
        """停止监听"""
        try:
            if task_id in self.monitoring_tasks:
                task_info = self.monitoring_tasks[task_id]
                task_info['status'] = 'stopped'
                del self.monitoring_tasks[task_id]
                logger.info(f"✅ 监听任务已停止: {task_id}")
                return True, "监听任务已停止"
            else:
                return False, "监听任务不存在"
        except Exception as e:
            logger.error(f"停止监听失败: {e}")
            return False, f"停止监听失败: {str(e)}"
    
    async def _register_message_handler(self, task_info: Dict[str, Any]):
        """注册消息处理器"""
        try:
            source_channel = task_info['source_channel']
            target_channel = task_info['target_channel']
            task_id = task_info['task_id']
            
            logger.info(f"🔍 注册消息处理器: source={source_channel}, target={target_channel}")
            
            # 创建消息处理器
            async def message_handler(client, message: Message):
                try:
                    # 记录所有接收到的消息（用于调试）
                    logger.info(f"🔍 收到消息: chat_id={message.chat.id}, chat_title={getattr(message.chat, 'title', 'Unknown')}")
                    logger.info(f"🔍 消息类型: {type(message).__name__}")
                    
                    # 检查消息是否来自源频道
                    chat_id = str(message.chat.id)
                    chat_username = getattr(message.chat, 'username', None)
                    
                    logger.info(f"🔍 频道匹配检查: chat_id={chat_id}, chat_username={chat_username}")
                    logger.info(f"🔍 源频道: {source_channel}")
                    
                    # 检查频道匹配
                    is_source_channel = False
                    
                    # 1. 检查频道ID匹配
                    if chat_id == str(source_channel):
                        is_source_channel = True
                        logger.info(f"✅ 频道ID匹配: {chat_id}")
                    
                    # 2. 检查用户名匹配
                    elif chat_username:
                        if source_channel.startswith('@'):
                            if chat_username == source_channel[1:]:
                                is_source_channel = True
                                logger.info(f"✅ 用户名匹配: {chat_username} == {source_channel[1:]}")
                        else:
                            if chat_username == source_channel.replace('@', ''):
                                is_source_channel = True
                                logger.info(f"✅ 用户名匹配: {chat_username} == {source_channel.replace('@', '')}")
                    
                    logger.info(f"🔍 是否匹配源频道: {is_source_channel}")
                    
                    if is_source_channel:
                        # 更新消息计数
                        if task_id in self.monitoring_tasks:
                            self.monitoring_tasks[task_id]['message_count'] += 1
                        
                        logger.info(f"🔔 监听到新消息: {message.id} from {message.chat.title}")
                        logger.info(f"   消息内容: {message.text or message.caption or '媒体消息'}")
                        
                        # 转发消息到目标频道
                        try:
                            await self.client.forward_messages(
                                chat_id=target_channel,
                                from_chat_id=message.chat.id,
                                message_ids=message.id
                            )
                            logger.info(f"✅ 消息已转发到目标频道: {target_channel}")
                        except Exception as e:
                            logger.error(f"转发消息失败: {e}")
                    else:
                        logger.info(f"⏭️ 消息不匹配源频道，跳过")
                            
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
            
            # 注册处理器
            from pyrogram.handlers import MessageHandler
            from pyrogram import filters
            
            # 使用更具体的过滤器来确保消息被捕获
            handler = MessageHandler(
                message_handler, 
                filters.chat(source_channel) & filters.incoming
            )
            self.client.add_handler(handler)
            logger.info(f"✅ 消息处理器已注册: {source_channel}")
            logger.info(f"🔍 处理器过滤器: chat={source_channel}, incoming=True")
            
        except Exception as e:
            logger.error(f"注册消息处理器失败: {e}")
    
    async def _register_global_handler(self):
        """注册全局消息处理器"""
        try:
            from pyrogram.handlers import MessageHandler
            from pyrogram import filters
            
            async def global_message_handler(client, message):
                try:
                    # 记录所有接收到的消息
                    logger.info(f"🔍 全局处理器收到消息: chat_id={message.chat.id}, chat_title={getattr(message.chat, 'title', 'Unknown')}")
                    logger.info(f"🔍 消息来源客户端: {id(client)}")
                    logger.info(f"🔍 监听器客户端: {self._client_id}")
                    
                    # 检查是否有匹配的监听任务
                    for task in self.monitoring_tasks.values():
                        if task['status'] != 'active':
                            continue
                            
                        source_channel = task['source_channel']
                        target_channel = task['target_channel']
                        task_id = task['task_id']
                        
                        # 检查频道匹配
                        chat_id = str(message.chat.id)
                        chat_username = getattr(message.chat, 'username', None)
                        
                        is_source_channel = False
                        
                        # 1. 检查频道ID匹配
                        if chat_id == str(source_channel):
                            is_source_channel = True
                            logger.info(f"✅ 全局处理器频道ID匹配: {chat_id}")
                        
                        # 2. 检查用户名匹配
                        elif chat_username:
                            if source_channel.startswith('@'):
                                if chat_username == source_channel[1:]:
                                    is_source_channel = True
                                    logger.info(f"✅ 全局处理器用户名匹配: {chat_username} == {source_channel[1:]}")
                            else:
                                if chat_username == source_channel.replace('@', ''):
                                    is_source_channel = True
                                    logger.info(f"✅ 全局处理器用户名匹配: {chat_username} == {source_channel.replace('@', '')}")
                        
                        if is_source_channel:
                            # 更新消息计数
                            if task_id in self.monitoring_tasks:
                                self.monitoring_tasks[task_id]['message_count'] += 1
                            
                            logger.info(f"🔔 全局处理器监听到新消息: {message.id} from {message.chat.title}")
                            logger.info(f"   消息内容: {message.text or message.caption or '媒体消息'}")
                            
                            # 转发消息到目标频道
                            try:
                                await self.client.forward_messages(
                                    chat_id=target_channel,
                                    from_chat_id=message.chat.id,
                                    message_ids=message.id
                                )
                                logger.info(f"✅ 全局处理器消息已转发到目标频道: {target_channel}")
                            except Exception as e:
                                logger.error(f"全局处理器转发消息失败: {e}")
                            
                except Exception as e:
                    logger.error(f"全局处理器处理消息时出错: {e}")
            
            # 注册全局处理器
            handler = MessageHandler(global_message_handler, filters.all)
            self.client.add_handler(handler)
            logger.info(f"✅ 全局消息处理器已注册到客户端: {self._client_id}")
            
        except Exception as e:
            logger.error(f"注册全局消息处理器失败: {e}")
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监听状态"""
        active_tasks = [task for task in self.monitoring_tasks.values() if task['status'] == 'active']
        total_messages = sum(task['message_count'] for task in self.monitoring_tasks.values())
        
        return {
            'is_running': len(active_tasks) > 0,  # 有活跃任务就是运行中
            'active_tasks': len(active_tasks),
            'total_tasks': len(self.monitoring_tasks),
            'total_messages_processed': total_messages,
            'tasks': list(self.monitoring_tasks.values())
        }
    
    def get_user_tasks(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的监听任务"""
        # 确保用户ID类型一致
        user_id_str = str(user_id)
        logger.info(f"🔍 查找用户任务: user_id={user_id}, user_id_str={user_id_str}")
        logger.info(f"🔍 所有任务: {list(self.monitoring_tasks.keys())}")
        
        user_tasks = []
        for task in self.monitoring_tasks.values():
            task_user_id = str(task['user_id'])
            logger.info(f"🔍 任务用户ID: {task_user_id}, 匹配: {task_user_id == user_id_str}")
            if task_user_id == user_id_str:
                user_tasks.append(task)
        
        logger.info(f"🔍 找到用户任务: {len(user_tasks)} 个")
        return user_tasks
    
    async def test_monitoring(self, task_id: str) -> Dict[str, Any]:
        """测试监听功能"""
        try:
            if task_id not in self.monitoring_tasks:
                return {"success": False, "message": "监听任务不存在"}
            
            task_info = self.monitoring_tasks[task_id]
            source_channel = task_info['source_channel']
            
            # 尝试获取源频道的最新消息
            try:
                messages = []
                # 使用offset参数获取最新消息，避免缓存问题
                async for message in self.client.get_chat_history(source_channel, limit=5, offset=0):
                    messages.append({
                        'id': message.id,
                        'text': message.text or message.caption or '媒体消息',
                        'date': message.date,
                        'chat_title': getattr(message.chat, 'title', 'Unknown')
                    })
                
                return {
                    "success": True,
                    "message": f"成功获取源频道 {source_channel} 的最新 {len(messages)} 条消息",
                    "messages": messages,
                    "task_info": task_info
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"无法获取源频道消息: {str(e)}",
                    "task_info": task_info
                }
                
        except Exception as e:
            logger.error(f"测试监听失败: {e}")
            return {"success": False, "message": f"测试失败: {str(e)}"}
    
    async def stop_all_monitoring(self):
        """停止所有监听"""
        try:
            self.monitoring_tasks.clear()
            self.is_running = False
            logger.info("✅ 所有监听任务已停止")
        except Exception as e:
            logger.error(f"停止所有监听失败: {e}")
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """获取详细状态信息"""
        active_tasks = [task for task in self.monitoring_tasks.values() if task['status'] == 'active']
        
        status = {
            'is_running': len(active_tasks) > 0,
            'active_tasks': len(active_tasks),
            'total_tasks': len(self.monitoring_tasks),
            'total_messages_processed': sum(task['message_count'] for task in self.monitoring_tasks.values()),
            'tasks': []
        }
        
        for task in self.monitoring_tasks.values():
            task_info = {
                'task_id': task['task_id'],
                'user_id': task['user_id'],
                'source_channel': task['source_channel'],
                'target_channel': task['target_channel'],
                'source_title': task['source_title'],
                'target_title': task['target_title'],
                'status': task['status'],
                'message_count': task['message_count']
            }
            status['tasks'].append(task_info)
        
        return status
    
    def get_debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        return {
            'client_id': self._client_id,
            'client_is_connected': self.client.is_connected if hasattr(self.client, 'is_connected') else 'unknown',
            'monitoring_tasks_count': len(self.monitoring_tasks),
            'active_tasks_count': len([task for task in self.monitoring_tasks.values() if task['status'] == 'active']),
            'global_handler_registered': self._global_handler_registered,
            'tasks': [
                {
                    'task_id': task['task_id'],
                    'source_channel': task['source_channel'],
                    'target_channel': task['target_channel'],
                    'status': task['status'],
                    'message_count': task['message_count']
                }
                for task in self.monitoring_tasks.values()
            ]
        }
    
    def _parse_channel_info(self, text: str) -> Optional[str]:
        """解析频道信息"""
        try:
            text = text.strip()
            
            # 处理频道链接
            if text.startswith('https://t.me/'):
                channel = text.split('/')[-1]
                if channel.startswith('@'):
                    return channel
                else:
                    return f"@{channel}"
            
            # 处理@开头的用户名
            if text.startswith('@'):
                return text
            
            # 处理数字ID
            if text.startswith('-100') and text[1:].isdigit():
                return text
            
            # 处理纯数字ID（添加-100前缀）
            if text.isdigit() and len(text) > 10:
                return f"-100{text}"
            
            return None
            
        except Exception as e:
            logger.error(f"解析频道信息失败: {e}")
            return None

# 创建全局监听器实例字典
monitor_instances = {}

def get_simple_monitor(client: Client) -> SimpleMonitor:
    """获取简单监听器实例"""
    # 使用客户端ID作为键，确保每个客户端有独立的监听器
    client_id = id(client)
    
    if client_id not in monitor_instances:
        monitor_instances[client_id] = SimpleMonitor(client)
        logger.info(f"✅ 创建新的监听器实例: client_id={client_id}")
    
    return monitor_instances[client_id]
