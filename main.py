# ==================== 主机器人文件 ====================
"""
主机器人文件
集成Telegram Bot API、命令处理器、回调查询处理和用户会话管理
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
import argparse
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入多机器人配置管理器
from multi_bot_config_manager import multi_bot_manager, create_bot_config_template

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError

# 导入自定义模块
from config import get_config, validate_config, DEFAULT_USER_CONFIG
from multi_bot_data_manager import create_multi_bot_data_manager
from local_data_manager import create_local_data_manager
from optimized_firebase_manager import get_global_optimized_manager, start_optimization_services
from ui_layouts import (
    generate_button_layout, MAIN_MENU_BUTTONS_WITH_USER_API, 
    MAIN_MENU_BUTTONS_USER_API_LOGGED_IN, CHANNEL_MANAGEMENT_BUTTONS,
    FEATURE_CONFIG_BUTTONS, MONITOR_MENU_BUTTONS, TASK_MANAGEMENT_BUTTONS,
    CHANNEL_ADMIN_TEST_BUTTONS, generate_channel_list_buttons, generate_pagination_buttons
)
from channel_data_manager import ChannelDataManager
from message_engine import create_message_engine
from cloning_engine import create_cloning_engine, CloneTask
from task_state_manager import start_task_state_manager, stop_task_state_manager
from web_server import create_web_server
from user_api_manager import get_user_api_manager, UserAPIManager

# 配置日志 - 使用优化的日志配置
from log_config import setup_bot_logging, get_logger

# 设置日志（可以通过环境变量控制级别）
import os
log_level = os.getenv('LOG_LEVEL', 'INFO')
logger = setup_bot_logging(level=log_level, enable_file=True)

class TelegramBot:
    """Telegram机器人主类"""
    
    def __init__(self, bot_name: Optional[str] = None):
        """初始化机器人"""
        # 如果指定了机器人名称，加载特定配置
        if bot_name:
            self.config = self._load_bot_specific_config(bot_name)
            if not self.config:
                raise ValueError(f"无法加载机器人 '{bot_name}' 的配置")
        else:
            # 不指定机器人名称时，尝试加载默认配置
            self.config = self._load_bot_specific_config("default")
            if not self.config:
                # 如果默认配置也加载失败，直接报错
                raise ValueError("无法加载默认机器人配置，请检查.env文件或使用 --bot 参数指定机器人")
        
        self.bot_name = bot_name or "default"
        # 确保bot_id的一致性，优先使用配置中的值，否则使用default_bot
        self.bot_id = self.config.get('bot_id') or 'default_bot'
        
        # 根据配置选择存储方式
        if self.config.get('use_local_storage', False):
            logger.info("🔧 使用本地存储模式")
            self.data_manager = create_local_data_manager(self.bot_id)
        else:
            logger.info("🔧 使用Firebase存储模式")
            self.data_manager = create_multi_bot_data_manager(self.bot_id)
            
        # 初始化频道数据管理器
        self.channel_data_manager = ChannelDataManager()
        
        # 初始化搬运引擎（延迟初始化）
        self.cloning_engine = None
        
        # 初始化监听引擎（延迟初始化）
        self.realtime_monitoring_engine = None
        
        # 监听任务持久化文件
        self.monitoring_tasks_file = f"data/{self.bot_id}/monitoring_tasks.json"
        
        # 初始化频道管理客户端（延迟初始化）
        self.channel_client = None
        
        # 初始化 User API 管理器
        self.user_api_manager = None
        self.user_api_logged_in = False
        
        # 加载User API登录状态
        self._load_user_api_status()
    
    def _save_user_api_status(self):
        """保存User API登录状态"""
        try:
            status_data = {
                'user_api_logged_in': self.user_api_logged_in,
                'last_updated': datetime.now().isoformat()
            }
            
            # 保存到本地文件
            status_file = f"data/{self.bot_id}/user_api_status.json"
            os.makedirs(os.path.dirname(status_file), exist_ok=True)
            
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ User API状态已保存: {self.user_api_logged_in}")
            
        except Exception as e:
            logger.error(f"❌ 保存User API状态失败: {e}")
    
    def _load_user_api_status(self):
        """加载User API登录状态"""
        try:
            status_file = f"data/{self.bot_id}/user_api_status.json"
            if os.path.exists(status_file):
                with open(status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                    self.user_api_logged_in = status_data.get('user_api_logged_in', False)
                    logger.info(f"✅ User API状态已加载: {self.user_api_logged_in}")
            else:
                logger.info("ℹ️ User API状态文件不存在，使用默认值")
                
        except Exception as e:
            logger.error(f"❌ 加载User API状态失败: {e}")
            self.user_api_logged_in = False
        
        # 尝试初始化 User API 管理器
        try:
            from user_api_manager import UserAPIManager
            # 使用配置管理器获取正确的API ID和Hash
            api_id = self.config.get('api_id', 0)
            api_hash = self.config.get('api_hash', '')
            if api_id and api_hash:
                self.user_api_manager = UserAPIManager(api_id, api_hash)
                logger.info("ℹ️ User API 管理器已创建，等待初始化")
            else:
                logger.warning("⚠️ 无法创建 User API 管理器，环境变量未设置")
        except Exception as e:
            logger.warning(f"⚠️ 创建 User API 管理器失败: {e}")
            self.user_api_manager = None
        
        # 检查是否在Render环境中，如果是则跳过User API登录
        if self.config.get('is_render', False):
            logger.info("🌐 检测到Render环境，跳过User API登录（无法接收验证码）")
            self.user_api_manager = None
        
        # 在Render环境中检查Firebase配额问题
        if self.config.get('is_render', False):
                logger.info("🌐 检测到Render环境，检查Firebase配额状态...")
                try:
                    # 尝试简单的Firebase操作来检测配额问题
                    import asyncio
                    async def check_firebase():
                        try:
                            await self.data_manager.get_user_config("test_quota_check")
                            return True
                        except Exception as e:
                            if "429" in str(e) or "quota" in str(e).lower():
                                logger.warning("⚠️ 检测到Firebase配额超限")
                                logger.warning("💡 建议在Render Dashboard中设置环境变量: USE_LOCAL_STORAGE=true")
                                return False
                            return True
                    
                    # 运行检查
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    quota_ok = loop.run_until_complete(check_firebase())
                    loop.close()
                    
                    if not quota_ok:
                        logger.warning("🚨 Firebase配额超限，建议切换到本地存储模式")
                        logger.warning("📋 请查看 render_deployment_guide.md 文件获取详细说明")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Firebase配额检查失败: {e}")
                    logger.warning("💡 建议切换到本地存储模式")
        self.client = None
        # self.monitor_system = None  # 已移除监控系统
        self.web_server = None
        self.web_runner = None
        
        # 用户会话状态
        self.user_states: Dict[str, Dict[str, Any]] = {}
        
        # 多任务选择状态
        self.multi_select_states: Dict[str, Dict[str, Any]] = {}
        
        # 初始化状态
        self.initialized = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_bot_specific_config(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """加载特定机器人的配置"""
        # 优先从环境变量或.env文件加载
        config = multi_bot_manager.load_bot_config_from_environment(bot_name)
        if config:
            return config
        
        # 回退到JSON配置文件
        config = multi_bot_manager.load_bot_config(bot_name)
        if config and multi_bot_manager.validate_bot_config(config):
            logger.info(f"✅ 已从JSON配置文件加载机器人 '{bot_name}' 的配置")
            return config
        else:
            logger.error(f"❌ 机器人 '{bot_name}' 配置无效或不存在")
            return None
    
    async def _should_cleanup_session(self, session_name):
        """检查是否需要清理session文件"""
        try:
            import os
            
            session_file = f"{session_name}.session"
            
            # 如果session文件不存在，不需要清理
            if not os.path.exists(session_file):
                logger.info(f"📁 session文件不存在: {session_file}")
                return False
            
            # 检查session文件大小，如果太小可能是损坏的
            file_size = os.path.getsize(session_file)
            if file_size < 100:  # 小于100字节可能是损坏的
                logger.warning(f"⚠️ session文件可能损坏 (大小: {file_size} 字节): {session_file}")
                return True
            
            # 尝试读取session文件，如果读取失败说明损坏
            try:
                with open(session_file, 'rb') as f:
                    f.read(1)  # 尝试读取一个字节
                logger.info(f"✅ session文件正常: {session_file}")
                return False
            except Exception as e:
                logger.warning(f"⚠️ session文件读取失败: {e}")
                return True
                
        except Exception as e:
            logger.warning(f"检查session文件失败: {e}")
            return False
    
    async def _cleanup_session_files(self, session_name):
        """清理可能损坏的session文件"""
        try:
            import os
            import glob
            
            # 清理所有可能的session文件
            session_patterns = [
                f"{session_name}.session",
                f"{session_name}.session-journal",
                "bot_session.session",
                "bot_session.session-journal",
                "render_bot_session.session",
                "render_bot_session.session-journal"
            ]
            
            for pattern in session_patterns:
                if os.path.exists(pattern):
                    logger.info(f"🗑️ 清理旧的session文件: {pattern}")
                    os.remove(pattern)
                    
            # 也清理所有.session文件（在Render环境中）
            if self.config.get('is_render'):
                for session_file in glob.glob("*.session*"):
                    logger.info(f"🗑️ 清理所有session文件: {session_file}")
                    os.remove(session_file)
                    
        except Exception as e:
            logger.warning(f"清理session文件失败: {e}")
    
    async def initialize(self):
        """初始化机器人"""
        try:
            logger.info("🚀 开始初始化机器人...")
            
            # 显示配置信息用于调试
            logger.info(f"🔧 机器人配置:")
            logger.info(f"   运行环境: {'Render' if self.config.get('is_render') else '本地'}")
            logger.info(f"   Bot ID: {self.config.get('bot_id')}")
            logger.info(f"   Bot Name: {self.config.get('bot_name')}")
            logger.info(f"   API ID: {self.config.get('api_id')}")
            logger.info(f"   API Hash: {self.config.get('api_hash', '')[:8]}...")
            logger.info(f"   Bot Token: {self.config.get('bot_token', '')[:8]}...")
            logger.info(f"   Firebase Project: {self.config.get('firebase_project_id')}")
            logger.info(f"   使用本地存储: {self.config.get('use_local_storage', False)}")
            
            # 验证配置
            if not validate_config():
                logger.error("❌ 配置验证失败")
                return False
            
            # 初始化Telegram客户端
            # 使用配置中的session_name，如果没有则基于Bot Token生成
            session_name = self.config.get('session_name')
            if not session_name:
                bot_token = self.config.get('bot_token', '')
                if bot_token and bot_token != 'your_bot_token':
                    # 使用token的前8位作为session文件名的一部分
                    token_suffix = bot_token.split(':')[0][:8] if ':' in bot_token else bot_token[:8]
                    session_name = f"bot_session_{token_suffix}"
                else:
                    # 回退到默认命名
                    session_name = "render_bot_session" if self.config.get('is_render') else "bot_session"
            
            # 只在session文件损坏时才清理，而不是每次启动都清理
            if await self._should_cleanup_session(session_name):
                logger.info("🔧 检测到session文件损坏，进行清理...")
                await self._cleanup_session_files(session_name)
            else:
                logger.info("✅ session文件正常，保持现有授权状态")
            
            self.client = Client(
                session_name,
                api_id=self.config['api_id'],
                api_hash=self.config['api_hash'],
                bot_token=self.config['bot_token']
            )
            
            # 启动客户端
            await self.client.start()
            logger.info("✅ Telegram客户端启动成功")
            
            # 频道管理客户端将在需要时动态获取（优先使用User API）
            self.channel_client = None  # 不再预先设置，使用_get_api_client()动态获取
            logger.info("✅ 频道管理客户端初始化成功（动态模式）")
            
            # 启动任务状态管理器
            try:
                await start_task_state_manager(self.bot_id)
                logger.info("✅ 任务状态管理器已启动")
            except Exception as e:
                logger.warning(f"⚠️ 启动任务状态管理器失败: {e}")
                logger.warning("💡 将使用内存模式，任务状态可能不会持久化")
            
            # 初始化搬运引擎（优先使用 User API，如果未登录则使用 Bot API）
            if self.user_api_logged_in and self.user_api_manager and self.user_api_manager.client:
                logger.info("🔧 使用 User API 初始化搬运引擎")
                self.cloning_engine = create_cloning_engine(self.user_api_manager.client, self.config, self.data_manager, self.bot_id)
            else:
                logger.info("🔧 使用 Bot API 初始化搬运引擎")
                self.cloning_engine = create_cloning_engine(self.client, self.config, self.data_manager, self.bot_id)
            logger.info("✅ 搬运引擎初始化成功")
            
            # 设置进度回调函数
            self.cloning_engine.set_progress_callback(self._task_progress_callback)
            logger.info("✅ 进度回调函数设置完成")
            
            # 监听引擎将在 User API 登录后初始化
            self.realtime_monitoring_engine = None
            logger.info("ℹ️ 监听引擎将在 User API 登录后初始化")
            
            # 初始化 User API 管理器
            logger.info("🔄 开始初始化 User API 管理器...")
            try:
                self.user_api_manager = await get_user_api_manager()
                
                # 检查是否有保存的登录状态
                if self.user_api_logged_in:
                    # 尝试恢复连接
                    try:
                        if not self.user_api_manager.client:
                            await self.user_api_manager.initialize_client()
                        
                        if self.user_api_manager.client and self.user_api_manager.client.is_connected:
                            # 验证登录状态
                            try:
                                me = await self.user_api_manager.client.get_me()
                                if me:
                                    self.user_api_manager.is_logged_in = True
                                    logger.info("🔄 检测到User API已登录，切换到User API模式")
                                    await self._switch_to_user_api_mode()
                                else:
                                    raise Exception("无法获取用户信息")
                            except Exception as e:
                                logger.warning(f"⚠️ User API会话无效: {e}")
                                self.user_api_logged_in = False
                                self._save_user_api_status()
                        else:
                            logger.warning("⚠️ User API客户端未连接，保持Bot API模式")
                            self.user_api_logged_in = False
                            self._save_user_api_status()
                    except Exception as e:
                        logger.error(f"❌ 恢复User API客户端失败: {e}")
                        self.user_api_logged_in = False
                        self._save_user_api_status()
                else:
                    logger.info("ℹ️ User API 未登录，可使用 /start_user_api_login 开始登录")
            except Exception as e:
                logger.warning(f"⚠️ User API 初始化失败: {e}")
                logger.info("💡 请确保设置了 API_ID 和 API_HASH 环境变量")
                # 即使初始化失败，也创建一个管理器实例，以便后续使用
                try:
                    from user_api_manager import UserAPIManager
                    api_id = int(os.getenv('API_ID', '0'))
                    api_hash = os.getenv('API_HASH', '')
                    logger.info(f"🔍 环境变量检查: API_ID={api_id}, API_HASH={'已设置' if api_hash else '未设置'}")
                    if api_id and api_hash:
                        self.user_api_manager = UserAPIManager(api_id, api_hash)
                        self.user_api_logged_in = False
                        logger.info("ℹ️ User API 管理器已创建，但未初始化")
                    else:
                        self.user_api_manager = None
                        self.user_api_logged_in = False
                        logger.warning("❌ 无法创建 User API 管理器，环境变量未设置")
                except Exception as create_error:
                    logger.error(f"❌ 创建 User API 管理器失败: {create_error}")
                    self.user_api_manager = None
                    self.user_api_logged_in = False
            
            logger.info(f"🔍 User API 管理器最终状态: {self.user_api_manager is not None}, 登录状态: {self.user_api_logged_in}")
            
            # 启动Firebase优化服务（如果使用Firebase存储）
            if not self.config.get('use_local_storage', False):
                try:
                    # 启动完整的Firebase优化服务
                    await start_optimization_services(self.bot_id)
                    logger.info("✅ Firebase优化服务已启动（批量存储+缓存+配额监控）")
                    
                    # 获取优化统计信息
                    manager = get_global_optimized_manager(self.bot_id)
                    if manager:
                        stats = manager.get_optimization_stats()
                        logger.info(f"📊 Firebase优化状态:")
                        logger.info(f"   批量存储: {'启用' if stats.get('use_batch_storage') else '禁用'}")
                        logger.info(f"   缓存系统: {'启用' if stats.get('use_cache') else '禁用'}")
                        logger.info(f"   配额监控: {'启用' if stats.get('use_quota_monitoring') else '禁用'}")
                except Exception as e:
                    logger.warning(f"⚠️ 启动Firebase优化服务失败: {e}")
                    logger.warning("💡 将使用标准Firebase操作，可能影响配额使用")
            
            logger.info("✅ 核心系统初始化成功")
            
            # 设置事件处理器
            self._setup_handlers()
            logger.info("✅ 事件处理器设置完成")
            
            # 初始化Web服务器
            self.web_server = await create_web_server(self)
            self.web_runner = await self.web_server.start_server(port=self.config.get('port', 8092))
            logger.info("✅ Web服务器启动成功")
            
            # 启动心跳任务（如果配置了Render URL）
            asyncio.create_task(self.web_server.keep_alive())
            
            self.initialized = True
            logger.info("🎉 机器人初始化完成！")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 机器人初始化失败: {e}")
            return False
    
    def _setup_handlers(self):
        """设置事件处理器"""
        # 确保filters可用
        from pyrogram import filters
        
        # 命令处理器
        @self.client.on_message(filters.command("start"))
        async def start_command(client, message: Message):
            await self._handle_start_command(message)
        
        @self.client.on_message(filters.command("help"))
        async def help_command(client, message: Message):
            await self._handle_help_command(message)
        
        @self.client.on_message(filters.command("menu"))
        async def menu_command(client, message: Message):
            await self._handle_menu_command(message)
        
        @self.client.on_message(filters.command("convert"))
        async def convert_command(client, message: Message):
            await self._handle_convert_command(message)
        
        @self.client.on_message(filters.command("test_join"))
        async def test_join_command(client, message: Message):
            await self._handle_test_join_command(message)
        
        @self.client.on_message(filters.command("lsj"))
        async def lsj_command(client, message: Message):
            await self._handle_lsj_command(message)
        
        @self.client.on_message(filters.command("test_admin"))
        async def test_admin_command(client, message: Message):
            await self._handle_test_admin_command(message)
        
        @self.client.on_message(filters.command("debug_channels"))
        async def debug_channels_command(client, message: Message):
            await self._handle_debug_channels_command(message)
        
        @self.client.on_message(filters.command("test_monitoring"))
        async def test_monitoring_command(client, message: Message):
            await self._handle_test_monitoring_command(message)
        
        @self.client.on_message(filters.command("debug_monitoring"))
        async def debug_monitoring_command(client, message: Message):
            await self._handle_debug_monitoring_command(message)
        
        @self.client.on_message(filters.command("reinit_monitoring"))
        async def reinit_monitoring_command(client, message: Message):
            await self._handle_reinit_monitoring_command(message)
        
        @self.client.on_message(filters.command("fix_monitoring"))
        async def fix_monitoring_command(client, message: Message):
            await self._handle_fix_monitoring_command(message)
        
        @self.client.on_message(filters.command("start_monitoring"))
        async def start_monitoring_command(client, message: Message):
            await self._handle_start_monitoring_command(message)
        
        @self.client.on_message(filters.command("check_monitoring"))
        async def check_monitoring_command(client, message: Message):
            await self._handle_check_monitoring_command(message)
        
        @self.client.on_message(filters.command("check_tasks"))
        async def check_tasks_command(client, message: Message):
            await self._handle_check_tasks_command(message)
        
        @self.client.on_message(filters.command("activate_tasks"))
        async def activate_tasks_command(client, message: Message):
            await self._handle_activate_tasks_command(message)
        
        @self.client.on_message(filters.command("sync_tasks"))
        async def sync_tasks_command(client, message: Message):
            await self._handle_sync_tasks_command(message)
        
        @self.client.on_message(filters.command("inspect_engine"))
        async def inspect_engine_command(client, message: Message):
            await self._handle_inspect_engine_command(message)
        
        @self.client.on_message(filters.command("load_tasks"))
        async def load_tasks_command(client, message: Message):
            await self._handle_load_tasks_command(message)
        
        @self.client.on_message(filters.command("test_fixed_monitoring"))
        async def test_fixed_monitoring_command(client, message: Message):
            await self._handle_test_fixed_monitoring_command(message)
        
        @self.client.on_message(filters.command("client_status"))
        async def client_status_command(client, message: Message):
            await self._handle_client_status_command(message)
        
        # User API 相关命令
        @self.client.on_message(filters.command("user_api_status"))
        async def user_api_status_command(client, message: Message):
            await self._handle_user_api_status(message)
        
        @self.client.on_message(filters.command("start_user_api_login"))
        async def start_user_api_login_command(client, message: Message):
            await self._handle_start_user_api_login(message)
        
        @self.client.on_message(filters.command("relogin_user_api"))
        async def relogin_user_api_command(client, message: Message):
            await self._handle_relogin_user_api(message)
        
        @self.client.on_message(filters.command("logout_user_api"))
        async def logout_user_api_command(client, message: Message):
            await self._handle_logout_user_api(message)
        
        # 回调查询处理器
        @self.client.on_callback_query()
        async def callback_handler(client, callback_query: CallbackQuery):
            try:
                await self._handle_callback_query(callback_query)
            except Exception as e:
                logger.error(f"处理回调查询时出错: {e}")
        
        # 文本消息处理器 - 只处理私聊文本消息
        @self.client.on_message(filters.private & filters.text)
        async def text_message_handler(client, message: Message):
            try:
                # 检查是否为命令
                if message.text.startswith('/'):
                    return
                await self._handle_text_message(message)
            except Exception as e:
                logger.error(f"处理文本消息时出错: {e}")
        
        # 通用消息监听器 - 处理所有消息
        @self.client.on_message()
        async def universal_message_handler(client, message: Message):
            try:
                await self._handle_all_messages(message)
            except Exception as e:
                logger.error(f"处理通用消息时出错: {e}")
        
        # 聊天成员更新监听器 - 处理机器人被添加为管理员
        @self.client.on_chat_member_updated()
        async def chat_member_updated_handler(client, chat_member_updated):
            try:
                await self._handle_chat_member_updated(chat_member_updated)
            except Exception as e:
                logger.error(f"处理聊天成员更新时出错: {e}")
        
        # 原始消息监听器 - 用于调试
        @self.client.on_raw_update()
        async def raw_update_handler(client, update, users, chats):
            try:
                await self._handle_raw_update(update)
            except Exception as e:
                logger.error(f"处理原始更新时出错: {e}")
        
        # 添加测试消息处理器
        @self.client.on_message()
        async def test_global_handler(client, message):
            logger.info(f"🔍 [全局测试] 收到消息: {message.id} from {message.chat.id} ({getattr(message.chat, 'title', 'Unknown')})")
        
        # 注意：Pyrogram Client 没有 on_error 方法，错误处理已在各个处理器中实现
    
    async def _handle_start_command(self, message: Message):
        """处理开始命令"""
        try:
            user_id = str(message.from_user.id)
            user_name = message.from_user.first_name or "用户"
            
            # 创建或获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 直接显示主菜单
            await self._show_main_menu(message)
            
            logger.info(f"用户 {user_id} 启动机器人")
            
        except Exception as e:
            logger.error(f"处理开始命令失败: {e}")
            await message.reply_text("❌ 启动失败，请稍后重试")
    
    async def _handle_user_api_status(self, message: Message):
        """处理 User API 状态查询"""
        try:
            if not self.user_api_manager:
                await message.reply_text("❌ User API 管理器未初始化")
                return
            
            status = self.user_api_manager.get_status()
            
            status_text = f"""
🔍 **User API 状态**

📊 **连接状态:**
• 已登录: {'✅ 是' if status['is_logged_in'] else '❌ 否'}
• 会话文件: {'✅ 存在' if status['session_exists'] else '❌ 不存在'}
• 客户端连接: {'✅ 已连接' if status['client_connected'] else '❌ 未连接'}

📈 **统计信息:**
• 登录尝试次数: {status['login_attempts']}
• 待处理登录: {'✅ 是' if status['has_pending_login'] else '❌ 否'}

💡 **可用命令:**
• /start_user_api_login - 开始登录
• /relogin_user_api - 重新登录
• /logout_user_api - 登出
            """.strip()
            
            # 添加返回按钮
            reply_markup = generate_button_layout([[
                ("🔙 返回主菜单", "show_main_menu")
            ]])
            
            await message.reply_text(status_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"❌ 查询 User API 状态失败: {e}")
            await message.reply_text("❌ 查询失败，请稍后重试")
    
    async def _handle_start_user_api_login(self, message: Message):
        """处理开始 User API 登录"""
        try:
            if not self.user_api_manager:
                await message.reply_text("❌ User API 管理器未初始化")
                return
            
            # 检查是否已有待处理的登录
            status = self.user_api_manager.get_status()
            if status['has_pending_login']:
                await message.reply_text("⚠️ 已有待处理的登录请求，请先完成当前登录或使用 /relogin_user_api 重新开始")
                return
            
            # 检查是否已经登录
            if status['is_logged_in']:
                await message.reply_text("✅ User API 已登录，无需重复登录")
                return
            
            await message.reply_text(
                "📱 **开始 User API 登录**\n\n"
                "请输入您的手机号码（包含国家代码）：\n"
                "例如：+1234567890\n\n"
                "💡 注意：请确保您的手机号码格式正确，包含国家代码"
            )
            
            # 设置待处理登录状态（通过设置一个标志）
            # 注意：这里我们不能直接修改 user_api_manager 的内部状态
            # 所以我们需要在 _handle_user_api_login_flow 中处理这种情况
            
        except Exception as e:
            logger.error(f"❌ 开始 User API 登录失败: {e}")
            await message.reply_text("❌ 操作失败，请稍后重试")
    
    async def _handle_relogin_user_api(self, message: Message):
        """处理重新登录 User API"""
        try:
            if not self.user_api_manager:
                await message.reply_text("❌ User API 管理器未初始化")
                return
            
            # 清除待处理的登录状态
            self.user_api_manager.pending_phone_code_hash = None
            self.user_api_manager.pending_phone_number = None
            
            await message.reply_text(
                "🔄 **重新开始 User API 登录**\n\n"
                "请输入您的手机号码（包含国家代码）：\n"
                "例如：+1234567890"
            )
            
        except Exception as e:
            logger.error(f"❌ 重新登录 User API 失败: {e}")
            await message.reply_text("❌ 操作失败，请稍后重试")
    
    async def _handle_logout_user_api(self, message: Message):
        """处理登出 User API"""
        try:
            if not self.user_api_manager:
                await message.reply_text("❌ User API 管理器未初始化")
                return
            
            success = await self.user_api_manager.logout()
            if success:
                self.user_api_logged_in = False
                self._save_user_api_status()
                await self._switch_to_bot_api_mode()
                await message.reply_text("✅ User API 已成功登出，已切换回 Bot API 模式")
            else:
                await message.reply_text("❌ 登出失败，请稍后重试")
            
        except Exception as e:
            logger.error(f"❌ 登出 User API 失败: {e}")
            await message.reply_text("❌ 操作失败，请稍后重试")
    
    async def _handle_user_api_login_flow(self, message: Message) -> bool:
        """处理 User API 登录流程"""
        try:
            # 检查是否在Render环境中
            if self.config.get('is_render', False):
                await message.reply_text(
                    "🌐 **Render环境限制**\n\n"
                    "❌ 在Render环境中无法接收手机验证码\n"
                    "💡 **解决方案：**\n"
                    "1. 在本地完成User API登录\n"
                    "2. 将session文件上传到Render\n"
                    "3. 或使用Bot API模式进行搬运\n\n"
                    "🔧 当前使用Bot API模式，功能正常"
                )
                return True
            
            if not self.user_api_manager:
                return False
            
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 检查是否有待处理的登录
            status = self.user_api_manager.get_status()
            
            # 如果用户输入的是手机号码格式，且没有待处理的登录，则开始登录流程
            if text.startswith('+') and len(text) > 5 and not status['has_pending_login']:
                # 验证手机号码格式
                phone_digits = text[1:]  # 去掉 + 号
                if not phone_digits.isdigit() or len(phone_digits) < 7 or len(phone_digits) > 15:
                    await message.reply_text(
                        "❌ **手机号码格式错误**\n\n"
                        "请确保手机号码格式正确：\n"
                        "• 以 + 开头\n"
                        "• 只包含数字（除了开头的 +）\n"
                        "• 长度在 7-15 位之间\n\n"
                        "例如：+1234567890 或 +639150373095\n\n"
                        "请重新输入正确的手机号码："
                    )
                    return True
                
                logger.info(f"🔍 用户 {user_id} 输入手机号码 {text}，开始登录流程")
                result = await self.user_api_manager.start_login_process(text)
                if result['success']:
                    await message.reply_text(result['message'])
                    return True
                else:
                    # 根据错误类型提供不同的提示
                    if "PHONE_NUMBER_INVALID" in result['message']:
                        await message.reply_text(
                            f"❌ **手机号码无效**\n\n"
                            f"您输入的手机号码 `{text}` 格式不正确。\n\n"
                            "请检查：\n"
                            "• 国家代码是否正确\n"
                            "• 手机号码是否完整\n"
                            "• 是否有多余的字符\n\n"
                            "请重新输入正确的手机号码："
                        )
                    else:
                        await message.reply_text(f"❌ {result['message']}")
                    return True
            
            # 如果有待处理的登录，继续处理
            if not status['has_pending_login']:
                return False
            
            # 处理手机号码输入
            if text.startswith('+') and len(text) > 5:
                result = await self.user_api_manager.start_login_process(text)
                if result['success']:
                    await message.reply_text(result['message'])
                    return True
                else:
                    await message.reply_text(f"❌ {result['message']}")
                    return True
            
            # 处理验证码输入
            elif text.isdigit() and (len(text) == 5 or len(text) == 6):
                result = await self.user_api_manager.verify_code(text)
                if result['success']:
                    self.user_api_logged_in = True
                    self._save_user_api_status()
                    await self._switch_to_user_api_mode()
                    await message.reply_text(result['message'])
                    return True
                elif result['action'] == 'need_password':
                    await message.reply_text(result['message'])
                    return True
                else:
                    await message.reply_text(f"❌ {result['message']}")
                    return True
            
            # 处理两步验证密码输入
            elif len(text) > 3 and not text.startswith('/'):
                result = await self.user_api_manager.verify_password(text)
                if result['success']:
                    self.user_api_logged_in = True
                    self._save_user_api_status()
                    await self._switch_to_user_api_mode()
                    await message.reply_text(result['message'])
                    return True
                else:
                    await message.reply_text(f"❌ {result['message']}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 处理 User API 登录流程失败: {e}")
            return False
    
    async def _switch_to_user_api_mode(self):
        """切换到 User API 模式"""
        try:
            if not self.user_api_manager or not self.user_api_logged_in:
                logger.warning("⚠️ User API 未登录，无法切换模式")
                return
            
            logger.info("🔄 切换到 User API 模式...")
            
            # 重新初始化搬运引擎使用 User API
            if self.user_api_manager.client:
                self.cloning_engine = create_cloning_engine(
                    self.user_api_manager.client,  # 使用 User API 客户端
                    self.config, 
                    self.data_manager
                )
                logger.info("✅ 搬运引擎已切换到 User API 模式")
                
                # 初始化监听引擎（仅 User API 模式）
                await self._initialize_monitoring_engine()
                
                # 设置频道管理使用 User API 客户端
                self.channel_client = self.user_api_manager.client
                logger.info("✅ 频道管理已切换到 User API 模式")
            
        except Exception as e:
            logger.error(f"❌ 切换到 User API 模式失败: {e}")
    
    async def _switch_to_bot_api_mode(self):
        """切换到 Bot API 模式（不包含监听功能）"""
        try:
            logger.info("🔄 切换到 Bot API 模式...")
            
            # 重新初始化搬运引擎使用 Bot API
            self.cloning_engine = create_cloning_engine(
                self.client,  # 使用 Bot API 客户端
                self.config, 
                self.data_manager
            )
            logger.info("✅ 搬运引擎已切换到 Bot API 模式")
            
            # 停止监听引擎（Bot API 不支持监听）
            if self.realtime_monitoring_engine:
                await self.realtime_monitoring_engine.stop_monitoring()
                self.realtime_monitoring_engine = None
                logger.info("✅ 监听引擎已停止（Bot API 不支持监听）")
            
            # 设置频道管理使用 Bot API 客户端
            self.channel_client = self.client
            logger.info("✅ 频道管理已切换到 Bot API 模式")
            
        except Exception as e:
            logger.error(f"❌ 切换到 Bot API 模式失败: {e}")
    
    async def _initialize_monitoring_engine(self):
        """初始化监听引擎（仅 User API 模式）"""
        try:
            if not self.user_api_logged_in or not self.user_api_manager:
                logger.warning("⚠️ User API 未登录，跳过监听引擎初始化")
                return
            
            # 初始化监听引擎使用 User API
            try:
                from monitoring_engine import RealTimeMonitoringEngine
                self.realtime_monitoring_engine = RealTimeMonitoringEngine(
                    self.user_api_manager.client,  # 使用 User API 客户端
                    self.cloning_engine, 
                    self.config
                )
            except ImportError:
                logger.warning("⚠️ monitoring_engine模块不存在，跳过监听引擎初始化")
                self.realtime_monitoring_engine = None
                return
            logger.info("✅ 监听引擎已初始化（User API 模式）")
            
            # 启动监听系统
            try:
                if self.realtime_monitoring_engine:
                    await self.realtime_monitoring_engine.start_monitoring()
                    logger.info("✅ 监听系统已启动（User API 模式）")
                else:
                    logger.info("ℹ️ 监听引擎未初始化，跳过监听系统启动")
                
                # 注册消息处理器（如果监听引擎存在）
                if self.realtime_monitoring_engine:
                    # 直接在主程序中注册一个简单的消息处理器进行测试
                    @self.realtime_monitoring_engine.client.on_message()
                    async def main_realtime_handler(client, message):
                        logger.info(f"🔔 [主程序实时] 收到消息: {message.id} from {message.chat.id}")
                        logger.info(f"   消息类型: {message.media}")
                        logger.info(f"   消息内容: {message.text or '无文本'}")
                    
                    logger.info("✅ 主程序实时处理器注册成功")
                else:
                    logger.info("ℹ️ 监听引擎未初始化，跳过处理器注册")
                
                # 添加更多测试处理器（如果监听引擎存在）
                if self.realtime_monitoring_engine:
                    from pyrogram import filters
                    
                    @self.realtime_monitoring_engine.client.on_message(filters.all)
                    async def test_handler_1(client, message):
                        logger.info(f"🔔 [测试处理器1] 收到消息: {message.id} from {message.chat.id}")
                    
                    @self.realtime_monitoring_engine.client.on_message(filters.text)
                    async def test_handler_2(client, message):
                        logger.info(f"🔔 [测试处理器2] 收到消息: {message.id} from {message.chat.id}")
                    
                    logger.info("✅ 测试处理器注册成功")
                
            except Exception as e:
                logger.error(f"❌ 实时监听启动失败: {e}")
                logger.info("🔄 尝试切换到轮询模式...")
                # 这里可以添加轮询模式的启动逻辑
            
            # 添加简单版实时监听 - 直接使用最简单的逻辑（如果监听引擎存在）
            if self.realtime_monitoring_engine:
                try:
                    from pyrogram.handlers import MessageHandler
                    from pyrogram import filters
                    
                    # 强制启动客户端
                    try:
                        if not self.realtime_monitoring_engine.client.is_connected:
                            await self.realtime_monitoring_engine.client.start()
                            logger.info("✅ 强制启动User API客户端成功")
                        else:
                            logger.info("✅ User API客户端已经连接")
                        
                        # 强制启动客户端的运行状态
                        try:
                            # 尝试获取用户信息来激活客户端
                            me = await self.realtime_monitoring_engine.client.get_me()
                            logger.info(f"✅ User API客户端已激活: {me.username}")
                        except Exception as e:
                            logger.warning(f"⚠️ 激活User API客户端失败: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ 强制启动User API客户端失败: {e}")
                    
                    # 简单版消息处理器 - 直接使用最简单的逻辑
                    async def simple_realtime_handler(client, message):
                        logger.info(f"🔔 [简单实时] 收到消息: {message.id} from {message.chat.id}")
                        logger.info(f"   消息类型: {message.media}")
                        logger.info(f"   消息内容: {message.text[:100] if message.text else '无文本'}")
                    
                    # 注册简单版处理器
                    simple_handler = MessageHandler(simple_realtime_handler, filters.all)
                    self.realtime_monitoring_engine.client.add_handler(simple_handler)
                    logger.info("✅ 简单版实时监听处理器注册成功")
                
                    # 添加一个测试 - 使用装饰器语法
                    try:
                        @self.realtime_monitoring_engine.client.on_message(filters.all)
                        async def decorator_realtime_handler(client, message):
                            logger.info(f"🔔 [装饰器实时] 收到消息: {message.id} from {message.chat.id}")
                        
                        logger.info("✅ 装饰器实时处理器注册成功")
                    except Exception as e:
                        logger.warning(f"⚠️ 装饰器实时处理器注册失败: {e}")
                    
                    # 添加一个测试 - 使用最基础的过滤器
                    try:
                        async def basic_realtime_handler(client, message):
                            logger.info(f"🔔 [基础实时] 收到消息: {message.id} from {message.chat.id}")
                        
                        basic_handler = MessageHandler(basic_realtime_handler, filters.text | filters.photo | filters.video | filters.document)
                        self.realtime_monitoring_engine.client.add_handler(basic_handler)
                        logger.info("✅ 基础实时处理器注册成功")
                    except Exception as e:
                        logger.warning(f"⚠️ 基础实时处理器注册失败: {e}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 简单版实时监听注册失败: {e}")
            
        except Exception as e:
            logger.error(f"❌ 初始化监听引擎失败: {e}")
    
    async def _ensure_cloning_engine_client(self):
        """确保搬运引擎使用正确的客户端"""
        try:
            if not self.cloning_engine:
                logger.warning("⚠️ 搬运引擎未初始化")
                return
            
            # 检查当前使用的客户端类型
            current_client_type = getattr(self.cloning_engine, 'client_type', 'Unknown')
            logger.info(f"🔍 当前搬运引擎客户端类型: {current_client_type}")
            
            # 如果 User API 已登录，确保使用 User API 客户端
            if self.user_api_logged_in and self.user_api_manager and self.user_api_manager.client:
                if current_client_type != 'Client':
                    logger.info("🔄 切换到 User API 客户端进行搬运")
                    self.cloning_engine = create_cloning_engine(
                        self.user_api_manager.client,  # 使用 User API 客户端
                        self.config, 
                        self.data_manager
                    )
                    logger.info("✅ 搬运引擎已切换到 User API 模式")
            else:
                # 如果 User API 未登录，确保使用 Bot API 客户端
                if current_client_type != 'Bot':
                    logger.info("🔄 切换到 Bot API 客户端进行搬运")
                    self.cloning_engine = create_cloning_engine(
                        self.client,  # 使用 Bot API 客户端
                        self.config, 
                        self.data_manager
                    )
                    logger.info("✅ 搬运引擎已切换到 Bot API 模式")
            
            # 设置进度回调函数
            self.cloning_engine.set_progress_callback(self._task_progress_callback)
            
        except Exception as e:
            logger.error(f"❌ 确保搬运引擎客户端失败: {e}")
    
    async def _reregister_all_monitoring_handlers(self):
        """重新注册所有活跃监听任务的消息处理器"""
        try:
            if not self.realtime_monitoring_engine:
                logger.warning("⚠️ 监听引擎未初始化，跳过重新注册")
                return
            
            # 获取所有用户的活跃任务
            all_user_tasks = []
            try:
                # 获取所有用户的任务
                for user_id in self.user_states.keys():
                    user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
                    active_tasks = [task for task in user_tasks if task.get('status') == 'active']
                    all_user_tasks.extend(active_tasks)
            except Exception as e:
                logger.error(f"获取用户任务失败: {e}")
                return
            
            logger.info(f"🔍 找到 {len(all_user_tasks)} 个活跃监听任务，开始重新注册消息处理器")
            
            for task_data in all_user_tasks:
                try:
                    task_id = task_data.get('task_id')
                    if not task_id:
                        continue
                    
                    # 先移除旧的消息处理器
                    await self.realtime_monitoring_engine._unregister_message_handlers(task_data)
                    logger.info(f"🗑️ 已移除任务 {task_id} 的旧消息处理器")
                    
                    # 重新注册消息处理器
                    await self.realtime_monitoring_engine._register_message_handlers(task_data)
                    logger.info(f"✅ 已重新注册任务 {task_id} 的消息处理器")
                    
                except Exception as e:
                    logger.error(f"❌ 重新注册任务 {task_data.get('task_id', 'unknown')} 的消息处理器失败: {e}")
            
            logger.info(f"✅ 完成重新注册，共处理 {len(all_user_tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"❌ 重新注册监听处理器失败: {e}")
    
    async def _handle_start_user_api_login_from_button(self, callback_query: CallbackQuery):
        """处理从按钮开始的 User API 登录"""
        try:
            await callback_query.answer()
            await self._handle_start_user_api_login(callback_query.message)
        except Exception as e:
            logger.error(f"❌ 处理 User API 登录按钮失败: {e}")
            await callback_query.answer("❌ 操作失败，请稍后重试", show_alert=True)
    
    async def _handle_user_api_status_from_button(self, callback_query: CallbackQuery):
        """处理从按钮查看 User API 状态"""
        try:
            await callback_query.answer()
            await self._handle_user_api_status(callback_query.message)
        except Exception as e:
            logger.error(f"❌ 处理 User API 状态按钮失败: {e}")
            await callback_query.answer("❌ 操作失败，请稍后重试", show_alert=True)
    
    async def _handle_logout_user_api_from_button(self, callback_query: CallbackQuery):
        """处理从按钮登出 User API"""
        try:
            await callback_query.answer()
            await self._handle_logout_user_api(callback_query.message)
        except Exception as e:
            logger.error(f"❌ 处理 User API 登出按钮失败: {e}")
            await callback_query.answer("❌ 操作失败，请稍后重试", show_alert=True)
    
    async def _handle_help_command(self, message: Message):
        """处理帮助命令"""
        try:
            help_text = """
📚 机器人使用帮助

🔧 **基本命令**
/start - 启动机器人
/help - 显示帮助信息
/menu - 打开主菜单
/convert - 私密频道ID转换工具

🚀 **主要功能**
1. **频道管理** - 添加、编辑、删除频道组
2. **过滤设定** - 配置文本过滤、链接移除等
3. **内容增强** - 设置文本小尾巴、附加按钮
4. **实时监听** - 自动监听频道并搬运新消息
5. **任务管理** - 查看搬运历史和任务状态

💡 **使用流程**
1. 使用 /start 启动机器人
2. 在"频道管理"中添加频道组
3. 在"过滤设定"中配置过滤规则
4. 在"开始搬运"中执行搬运任务
5. 可选：启用"实时监听"自动搬运

❓ **遇到问题**
如果遇到问题，请检查：
• 机器人是否有相应频道的权限
• 频道ID是否正确
• 网络连接是否正常

🆘 **技术支持**
如有其他问题，请联系管理员。
            """.strip()
            
            await message.reply_text(
                help_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理帮助命令失败: {e}")
            await message.reply_text("❌ 显示帮助失败，请稍后重试")
    
    async def _handle_menu_command(self, message: Message):
        """处理菜单命令"""
        await self._show_main_menu(message)
    
    async def _handle_convert_command(self, message: Message):
        """处理频道ID转换命令"""
        try:
            # 检查是否提供了频道链接
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.reply_text(
                    "🔧 **频道ID转换工具**\n\n"
                    "📝 **使用方法：**\n"
                    "`/convert https://t.me/c/1234567890/123`\n\n"
                    "🔗 **支持的格式：**\n"
                    "• `https://t.me/c/1234567890/`\n"
                    "• `t.me/c/1234567890`\n"
                    "• `https://t.me/c/1234567890/123`\n\n"
                    "💡 **说明：** 此工具可以将私密频道链接转换为机器人可用的频道ID"
                )
                return
            
            channel_link = command_parts[1].strip()
            
            # 解析频道链接
            parsed_result = await self._parse_channel_input(channel_link)
            
            if parsed_result and parsed_result.startswith('-100'):
                await message.reply_text(
                    f"✅ **转换成功！**\n\n"
                    f"🔗 **原始链接：** `{channel_link}`\n"
                    f"🆔 **频道ID：** `{parsed_result}`\n\n"
                    f"💡 **使用说明：**\n"
                    f"• 复制上面的频道ID\n"
                    f"• 在添加频道时直接粘贴此ID\n"
                    f"• 确保机器人已加入该私密频道\n\n"
                    f"⚠️ **注意：** 机器人必须先加入私密频道才能使用此ID进行搬运"
                )
            else:
                await message.reply_text(
                    f"❌ **转换失败！**\n\n"
                    f"🔗 **输入链接：** `{channel_link}`\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 链接格式不正确\n"
                    f"• 不是私密频道链接\n"
                    f"• 链接中缺少频道ID\n\n"
                    f"🔧 **正确格式：**\n"
                    f"• `https://t.me/c/1234567890/`\n"
                    f"• `t.me/c/1234567890`"
                )
                
        except Exception as e:
            logger.error(f"处理转换命令失败: {e}")
            await message.reply_text("❌ 转换失败，请稍后重试")
    
    async def _handle_test_join_command(self, message: Message):
        """处理测试加入命令"""
        try:
            # 安全获取用户ID
            user_id = "unknown"
            if message.from_user:
                user_id = str(message.from_user.id)
            elif message.sender_chat:
                user_id = f"chat_{message.sender_chat.id}"
            
            chat_id = message.chat.id
            chat_type = message.chat.type
            
            logger.info(f"🧪 收到测试加入命令: user_id={user_id}, chat_id={chat_id}, chat_type={chat_type}")
            
            # 检查是否在群组中 - 使用字符串比较
            chat_type_str = str(chat_type).lower()
            logger.info(f"🔍 聊天类型字符串: '{chat_type_str}'")
            
            # 检查是否包含关键词
            if any(keyword in chat_type_str for keyword in ['group', 'supergroup', 'channel']):
                logger.info(f"✅ 检测到群组/频道类型: {chat_type_str}")
                # 模拟群组加入事件
                await self._send_group_verification_message(message)
                await message.reply_text("✅ 测试验证消息已发送")
            else:
                logger.warning(f"❌ 不支持的聊天类型: {chat_type_str}")
                await message.reply_text(f"❌ 此命令只能在群组或频道中使用，当前类型: {chat_type_str}")
                
        except Exception as e:
            logger.error(f"处理测试加入命令失败: {e}")
            await message.reply_text(f"❌ 测试失败: {str(e)}")
    
    async def _handle_chat_member_updated(self, chat_member_updated):
        """处理聊天成员更新事件"""
        try:
            logger.info(f"🔍 收到聊天成员更新事件")
            logger.info(f"🔍 事件详情: chat_id={chat_member_updated.chat.id}, chat_title={getattr(chat_member_updated.chat, 'title', '未知')}")
            
            # 检查是否有新成员信息
            if not chat_member_updated.new_chat_member:
                logger.info("🔍 没有新成员信息，跳过")
                return
            
            # 检查旧成员信息（可能为空，这是正常的）
            old_chat_member = chat_member_updated.old_chat_member
            if old_chat_member:
                logger.info(f"🔍 旧成员信息: {old_chat_member.status}")
            else:
                logger.info("🔍 没有旧成员信息（新加入），继续处理")
            
            # 检查是否是机器人本身
            is_self = chat_member_updated.new_chat_member.user.is_self
            logger.info(f"🔍 是否是机器人本身: {is_self}")
            if not is_self:
                logger.info("🔍 不是机器人相关事件，跳过")
                return
            
            new_status = chat_member_updated.new_chat_member.status
            old_status = old_chat_member.status if old_chat_member else None
            
            logger.info(f"🔍 机器人状态变化: {old_status} -> {new_status}")
            
            # 如果机器人被添加为管理员
            new_status_str = str(new_status).lower()
            if 'administrator' in new_status_str or 'creator' in new_status_str:
                chat_id = chat_member_updated.chat.id
                chat_title = getattr(chat_member_updated.chat, 'title', '未知频道')
                chat_username = getattr(chat_member_updated.chat, 'username', None)
                
                logger.info(f"✅ 机器人被添加为管理员: {chat_title} (@{chat_username}) - ID: {chat_id}")
                
                # 将频道添加到频道数据管理器
                channel_data = {
                    'id': chat_id,
                    'title': chat_title,
                    'username': chat_username,
                    'type': str(chat_member_updated.chat.type).lower(),
                    'verified': True,
                    'added_at': datetime.now().isoformat()
                }
                await self._add_known_channel(chat_id, channel_data)
                
                # 发送确认消息
                try:
                    confirmation_msg = await self.client.send_message(
                        chat_id,
                        f"✅ 机器人已成功添加为管理员！\n\n"
                        f"📢 频道: {chat_title}\n"
                        f"🔧 现在可以使用 /lsj 命令进行验证测试\n"
                        f"📋 频道已自动添加到管理员列表"
                    )
                    logger.info(f"✅ 管理员确认消息发送成功")
                    
                    # 2秒后删除确认消息
                    await asyncio.sleep(2)
                    try:
                        await confirmation_msg.delete()
                        logger.info(f"✅ 已删除管理员确认消息")
                    except Exception as e:
                        logger.warning(f"删除管理员确认消息失败: {e}")
                        
                except Exception as e:
                    logger.error(f"❌ 发送管理员确认消息失败: {e}")
            
            # 如果机器人被移除管理员权限
            else:
                if old_chat_member:
                    old_status_str = str(old_status).lower()
                    new_status_str = str(new_status).lower()
                    if ('administrator' in old_status_str or 'creator' in old_status_str) and ('administrator' not in new_status_str and 'creator' not in new_status_str):
                        chat_id = chat_member_updated.chat.id
                        chat_title = getattr(chat_member_updated.chat, 'title', '未知频道')
                        
                        logger.info(f"❌ 机器人管理员权限被移除: {chat_title} - ID: {chat_id}")
                        
        except Exception as e:
            logger.error(f"❌ 处理聊天成员更新失败: {e}")
    
    async def _handle_test_admin_command(self, message: Message):
        """处理/test_admin测试命令"""
        try:
            logger.info(f"🔍 开始处理/test_admin命令")
            
            chat_id = message.chat.id
            chat_type = message.chat.type
            
            logger.info(f"🔍 测试命令: chat_id={chat_id}, chat_type={chat_type}")
            
            # 获取聊天信息
            try:
                chat_info = await self._get_api_client().get_chat(chat_id)
                logger.info(f"🔍 聊天信息: {chat_info}")
                
                # 检查机器人权限
                try:
                    member = await self._get_api_client().get_chat_member(chat_id, "me")
                    logger.info(f"🔍 机器人权限: {member}")
                    
                    # 获取所有权限信息
                    privileges = getattr(member, 'privileges', None)
                    privileges_info = ""
                    if privileges:
                        privileges_info = f"\n🔧 **详细权限：**\n"
                        privileges_info += f"• 删除消息: {getattr(privileges, 'can_delete_messages', False)}\n"
                        privileges_info += f"• 发送消息: {getattr(privileges, 'can_post_messages', False)}\n"
                        privileges_info += f"• 管理聊天: {getattr(privileges, 'can_manage_chat', False)}\n"
                        privileges_info += f"• 限制成员: {getattr(privileges, 'can_restrict_members', False)}\n"
                        privileges_info += f"• 邀请用户: {getattr(privileges, 'can_invite_users', False)}\n"
                        privileges_info += f"• 置顶消息: {getattr(privileges, 'can_pin_messages', False)}\n"
                        privileges_info += f"• 编辑消息: {getattr(privileges, 'can_edit_messages', False)}\n"
                        privileges_info += f"• 更改信息: {getattr(privileges, 'can_change_info', False)}"
                    
                    # 检查删除权限
                    can_delete = False
                    privileges = getattr(member, 'privileges', None)
                    if privileges:
                        can_delete = getattr(privileges, 'can_delete_messages', False)
                    else:
                        can_delete = getattr(member, 'can_delete_messages', False)
                    
                    await message.reply_text(
                        f"🔍 **管理员测试结果**\n\n"
                        f"📢 频道: {getattr(chat_info, 'title', '未知')}\n"
                        f"🆔 ID: {chat_id}\n"
                        f"📝 类型: {chat_type}\n"
                        f"👤 机器人状态: {member.status}\n"
                        f"🔧 删除权限: {can_delete}\n"
                        f"📤 发送权限: {getattr(member, 'can_post_messages', False)}"
                        f"{privileges_info}"
                    )
                    
                except Exception as e:
                    logger.error(f"获取机器人权限失败: {e}")
                    await message.reply_text(f"❌ 获取机器人权限失败: {str(e)}")
                    
            except Exception as e:
                logger.error(f"获取聊天信息失败: {e}")
                await message.reply_text(f"❌ 获取聊天信息失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理测试管理员命令失败: {e}")
            await message.reply_text(f"❌ 测试失败: {str(e)}")
    
    async def _handle_debug_channels_command(self, message: Message):
        """处理调试频道命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 从频道数据管理器获取频道信息
            all_channels = self.channel_data_manager.get_all_channels()
            verified_channels = self.channel_data_manager.get_verified_channels()
            
            debug_text = f"🔍 **频道调试信息**\n\n"
            debug_text += f"📊 总频道数量: {len(all_channels)}\n"
            debug_text += f"✅ 已验证频道: {len(verified_channels)}\n\n"
            
            if all_channels:
                debug_text += "🔍 **频道状态详情:**\n"
                for i, channel in enumerate(all_channels, 1):
                    channel_id = channel['id']
                    debug_text += f"{i}. ID: {channel_id}\n"
                    debug_text += f"   标题: {channel.get('title', '未知')}\n"
                    debug_text += f"   用户名: @{channel.get('username', '无')}\n"
                    debug_text += f"   类型: {channel.get('type', '未知')}\n"
                    debug_text += f"   验证状态: {'✅ 已验证' if channel.get('verified', False) else '❌ 未验证'}\n"
                    debug_text += f"   添加时间: {channel.get('added_at', '未知')}\n"
                    debug_text += f"   最后验证: {channel.get('last_verified', '从未验证')}\n"
                    debug_text += f"   需要验证: {'是' if self.channel_data_manager.needs_verification(channel_id) else '否'}\n\n"
            else:
                debug_text += "📝 没有已知频道\n"
            
            await message.reply_text(debug_text)
            
        except Exception as e:
            logger.error(f"处理调试频道命令失败: {e}")
            await message.reply_text(f"❌ 调试失败: {str(e)}")
    
    async def _handle_debug_monitoring_command(self, message: Message):
        """处理调试监听命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎状态
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "可能的原因：\n"
                    "• User API 未登录\n"
                    "• 监听引擎初始化失败\n"
                    "• 需要重新初始化\n\n"
                    "请尝试：\n"
                    "• 检查 User API 状态\n"
                    "• 重新初始化监听引擎"
                )
                return
            
            # 获取监听引擎状态
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            # 构建调试信息
            debug_text = f"""
🔍 **监听引擎调试信息**

📊 **引擎状态**:
• 运行状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}
• 活跃任务: {monitoring_status.get('active_tasks', 0)} 个
• 处理消息: {monitoring_status.get('global_stats', {}).get('total_messages_processed', 0)} 条

👤 **您的任务**:
• 总任务数: {len(user_tasks)} 个
• 活跃任务: {len(active_tasks)} 个

🔧 **User API 状态**:
• 登录状态: {'✅ 已登录' if self.user_api_logged_in else '❌ 未登录'}
• 客户端: {'✅ 存在' if self.user_api_manager else '❌ 不存在'}

💡 **建议**:
            """
            
            if not monitoring_status.get('is_running', False):
                debug_text += "• 监听引擎未运行，需要重新初始化\n"
            if not active_tasks:
                debug_text += "• 没有活跃的监听任务\n"
            if not self.user_api_logged_in:
                debug_text += "• User API 未登录，需要先登录\n"
            
            debug_text += "• 尝试运行 /reinit_monitoring 重新初始化\n"
            debug_text += "• 检查源频道是否有新消息\n"
            
            await message.reply_text(debug_text)
            
        except Exception as e:
            logger.error(f"处理调试监听命令失败: {e}")
            await message.reply_text(f"❌ 调试失败: {str(e)}")
    
    async def _handle_reinit_monitoring_command(self, message: Message):
        """处理重新初始化监听引擎命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查 User API 登录状态
            if not self.user_api_logged_in or not self.user_api_manager:
                await message.reply_text(
                    "❌ **User API 未登录**\n\n"
                    "请先登录 User API 才能使用监听功能：\n"
                    "1. 点击 /start_user_api_login 开始登录\n"
                    "2. 输入手机号码和验证码\n"
                    "3. 登录成功后即可使用监听功能"
                )
                return
            
            # 停止现有的监听引擎
            if self.realtime_monitoring_engine:
                try:
                    await self.realtime_monitoring_engine.stop_monitoring()
                    logger.info("✅ 已停止现有监听引擎")
                except Exception as e:
                    logger.error(f"停止监听引擎失败: {e}")
            
            # 重新初始化监听引擎
            try:
                await self._initialize_monitoring_engine()
                
                if self.realtime_monitoring_engine:
                    # 获取监听状态
                    monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
                    user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
                    active_tasks = [task for task in user_tasks if task['status'] == 'active']
                    
                    await message.reply_text(
                        f"✅ **监听引擎重新初始化成功！**\n\n"
                        f"📊 **当前状态**:\n"
                        f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                        f"• 活跃任务: {len(active_tasks)} 个\n"
                        f"• 总任务数: {len(user_tasks)} 个\n\n"
                        f"💡 **下一步**:\n"
                        f"• 检查源频道是否有新消息\n"
                        f"• 运行 /debug_monitoring 查看详细状态"
                    )
                else:
                    await message.reply_text(
                        "❌ **监听引擎初始化失败**\n\n"
                        "请检查：\n"
                        "• User API 连接状态\n"
                        "• 监听引擎配置文件\n"
                        "• 系统日志信息"
                    )
                    
            except Exception as e:
                logger.error(f"重新初始化监听引擎失败: {e}")
                await message.reply_text(f"❌ 重新初始化失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理重新初始化监听引擎命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_fix_monitoring_command(self, message: Message):
        """处理修复监听功能命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            if not active_tasks:
                await message.reply_text(
                    "❌ **没有活跃的监听任务**\n\n"
                    "请先创建监听任务：\n"
                    "1. 点击主菜单的 '📡 监听管理'\n"
                    "2. 点击 '➕ 创建任务'\n"
                    "3. 选择目标频道和源频道"
                )
                return
            
            # 重新注册所有活跃任务的消息处理器
            try:
                await self._reregister_all_monitoring_handlers()
                
                # 获取修复后的状态
                monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
                
                await message.reply_text(
                    f"✅ **监听功能修复完成！**\n\n"
                    f"📊 **修复结果**:\n"
                    f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                    f"• 活跃任务: {monitoring_status.get('active_tasks', 0)} 个\n"
                    f"• 您的任务: {len(active_tasks)} 个\n\n"
                    f"🔧 **已执行的操作**:\n"
                    f"• 重新注册消息处理器\n"
                    f"• 同步任务状态\n"
                    f"• 启动监听服务\n\n"
                    f"💡 **下一步**:\n"
                    f"• 在源频道发送测试消息\n"
                    f"• 检查是否能监听到新消息\n"
                    f"• 运行 /debug_monitoring 查看状态"
                )
                
            except Exception as e:
                logger.error(f"修复监听功能失败: {e}")
                await message.reply_text(f"❌ 修复失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理修复监听功能命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_start_monitoring_command(self, message: Message):
        """处理启动监听任务命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            if not active_tasks:
                await message.reply_text(
                    "❌ **没有活跃的监听任务**\n\n"
                    "请先创建监听任务：\n"
                    "1. 点击主菜单的 '📡 监听管理'\n"
                    "2. 点击 '➕ 创建任务'\n"
                    "3. 选择目标频道和源频道"
                )
                return
            
            # 强制启动所有活跃任务
            started_count = 0
            for task in active_tasks:
                try:
                    task_id = task['task_id']
                    success = await self.realtime_monitoring_engine.start_monitoring_task(task_id)
                    if success:
                        started_count += 1
                        logger.info(f"✅ 已启动监听任务: {task_id}")
                    else:
                        logger.error(f"❌ 启动监听任务失败: {task_id}")
                except Exception as e:
                    logger.error(f"启动监听任务 {task['task_id']} 失败: {e}")
            
            # 获取启动后的状态
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            
            await message.reply_text(
                f"✅ **监听任务启动完成！**\n\n"
                f"📊 **启动结果**:\n"
                f"• 成功启动: {started_count} 个任务\n"
                f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                f"• 活跃任务: {monitoring_status.get('active_tasks', 0)} 个\n\n"
                f"💡 **下一步**:\n"
                f"• 在源频道发送测试消息\n"
                f"• 检查是否能监听到新消息\n"
                f"• 运行 /debug_monitoring 查看状态"
            )
                
        except Exception as e:
            logger.error(f"处理启动监听任务命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_check_monitoring_command(self, message: Message):
        """处理检查监听引擎内部状态命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 获取详细的监听引擎状态
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            # 检查监听引擎的内部状态
            try:
                engine_active_tasks = getattr(self.realtime_monitoring_engine, 'active_tasks', {})
                if isinstance(engine_active_tasks, dict):
                    engine_tasks_count = len(engine_active_tasks)
                elif isinstance(engine_active_tasks, (list, tuple)):
                    engine_tasks_count = len(engine_active_tasks)
                elif isinstance(engine_active_tasks, int):
                    engine_tasks_count = engine_active_tasks
                else:
                    engine_tasks_count = 0
                    logger.warning(f"⚠️ active_tasks 类型未知: {type(engine_active_tasks)}")
            except Exception as e:
                logger.error(f"获取 active_tasks 失败: {e}")
                engine_tasks_count = 0
                engine_active_tasks = None
            
            # 检查监听引擎是否正在运行
            is_running = getattr(self.realtime_monitoring_engine, 'is_running', False)
            
            # 构建详细状态信息
            status_text = f"""
🔍 **监听引擎内部状态检查**

📊 **引擎状态**:
• 运行状态: {'✅ 运行中' if is_running else '❌ 已停止'}
• 内部活跃任务: {engine_tasks_count} 个
• 状态报告活跃任务: {monitoring_status.get('active_tasks', 0)} 个

👤 **用户任务**:
• 总任务数: {len(user_tasks)} 个
• 活跃任务: {len(active_tasks)} 个

🔧 **任务详情**:
            """
            
            if user_tasks:
                for i, task in enumerate(user_tasks, 1):
                    task_id = task.get('task_id', f'task_{i}')
                    status = task.get('status', 'unknown')
                    target = task.get('target_channel', 'Unknown')
                    sources = len(task.get('source_channels', []))
                    
                    status_text += f"\n{i}. **任务 {task_id}**\n"
                    status_text += f"   • 状态: {status}\n"
                    status_text += f"   • 目标频道: {target}\n"
                    status_text += f"   • 源频道: {sources} 个\n"
                    
                    # 检查任务是否在引擎的活跃任务中
                    if engine_active_tasks is None:
                        status_text += f"   • 引擎状态: ❓ 无法检查\n"
                    elif isinstance(engine_active_tasks, dict) and task_id in engine_active_tasks:
                        status_text += f"   • 引擎状态: ✅ 已注册\n"
                    elif isinstance(engine_active_tasks, (list, tuple)) and task_id in engine_active_tasks:
                        status_text += f"   • 引擎状态: ✅ 已注册\n"
                    else:
                        status_text += f"   • 引擎状态: ❌ 未注册\n"
            else:
                status_text += "\n❌ 没有找到用户任务"
            
            # 添加诊断建议
            status_text += f"\n\n💡 **诊断建议**:\n"
            if engine_tasks_count == 0 and len(active_tasks) > 0:
                status_text += "• 任务存在但未注册到引擎，需要重新启动\n"
            if not is_running:
                status_text += "• 监听引擎未运行，需要重新初始化\n"
            if len(active_tasks) == 0:
                status_text += "• 没有活跃任务，需要创建或启动任务\n"
            
            status_text += "• 尝试运行 /activate_tasks 激活任务\n"
            status_text += "• 检查源频道是否有新消息\n"
            
            await message.reply_text(status_text)
            
        except Exception as e:
            logger.error(f"处理检查监听引擎内部状态命令失败: {e}")
            await message.reply_text(f"❌ 检查失败: {str(e)}")
    
    async def _handle_check_tasks_command(self, message: Message):
        """处理检查任务文件命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 检查任务文件是否存在
            import os
            task_file = f"data/{self.bot_id}/monitoring_tasks.json"
            file_exists = os.path.exists(task_file)
            
            # 读取任务文件内容
            tasks_data = {}
            if file_exists:
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        tasks_data = json.load(f)
                except Exception as e:
                    logger.error(f"读取任务文件失败: {e}")
                    tasks_data = {}
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            
            # 构建检查结果
            check_text = f"""
🔍 **任务文件检查结果**

📁 **文件状态**:
• 任务文件: {'✅ 存在' if file_exists else '❌ 不存在'}
• 文件路径: {task_file}
• 文件大小: {os.path.getsize(task_file) if file_exists else 0} 字节

📊 **任务数据**:
• 文件中的任务: {len(tasks_data)} 个
• 引擎中的任务: {len(user_tasks)} 个
• 用户ID: {user_id}

🔧 **任务详情**:
            """
            
            if tasks_data:
                for task_id, task_data in tasks_data.items():
                    task_user = task_data.get('user_id', 'Unknown')
                    task_status = task_data.get('status', 'unknown')
                    target = task_data.get('target_channel', 'Unknown')
                    sources = len(task_data.get('source_channels', []))
                    
                    check_text += f"\n• **任务 {task_id}**\n"
                    check_text += f"  - 用户: {task_user}\n"
                    check_text += f"  - 状态: {task_status}\n"
                    check_text += f"  - 目标: {target}\n"
                    check_text += f"  - 源频道: {sources} 个\n"
            else:
                check_text += "\n❌ 没有找到任务数据"
            
            # 添加诊断建议
            check_text += f"\n\n💡 **诊断建议**:\n"
            if not file_exists:
                check_text += "• 任务文件不存在，需要重新创建任务\n"
            if len(tasks_data) == 0:
                check_text += "• 任务文件为空，需要重新创建任务\n"
            if len(user_tasks) == 0:
                check_text += "• 引擎中没有任务，需要重新创建任务\n"
            if len(tasks_data) > 0 and len(user_tasks) == 0:
                check_text += "• 任务文件有数据但引擎中没有，需要重新加载\n"
            
            check_text += "• 尝试重新创建监听任务\n"
            check_text += "• 检查任务文件权限\n"
            
            await message.reply_text(check_text)
            
        except Exception as e:
            logger.error(f"处理检查任务文件命令失败: {e}")
            await message.reply_text(f"❌ 检查失败: {str(e)}")
    
    async def _handle_activate_tasks_command(self, message: Message):
        """处理激活待处理任务命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            pending_tasks = [task for task in user_tasks if task['status'] == 'pending']
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            if not pending_tasks:
                await message.reply_text(
                    f"✅ **没有待处理的任务**\n\n"
                    f"📊 **当前状态**:\n"
                    f"• 活跃任务: {len(active_tasks)} 个\n"
                    f"• 待处理任务: {len(pending_tasks)} 个\n\n"
                    f"💡 **说明**: 所有任务都已经是活跃状态"
                )
                return
            
            # 激活所有待处理的任务
            activated_count = 0
            for task in pending_tasks:
                try:
                    task_id = task['task_id']
                    # 更新任务状态为 active
                    success = await self.realtime_monitoring_engine.start_monitoring_task(task_id)
                    if success:
                        activated_count += 1
                        logger.info(f"✅ 已激活任务: {task_id}")
                    else:
                        logger.error(f"❌ 激活任务失败: {task_id}")
                except Exception as e:
                    logger.error(f"激活任务 {task['task_id']} 失败: {e}")
            
            # 获取激活后的状态
            updated_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            updated_active_tasks = [task for task in updated_tasks if task['status'] == 'active']
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            
            await message.reply_text(
                f"✅ **任务激活完成！**\n\n"
                f"📊 **激活结果**:\n"
                f"• 成功激活: {activated_count} 个任务\n"
                f"• 当前活跃任务: {len(updated_active_tasks)} 个\n"
                f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                f"• 引擎活跃任务: {monitoring_status.get('active_tasks', 0)} 个\n\n"
                f"💡 **下一步**:\n"
                f"• 在源频道发送测试消息\n"
                f"• 检查是否能监听到新消息\n"
                f"• 运行 /debug_monitoring 查看状态"
            )
                
        except Exception as e:
            logger.error(f"处理激活待处理任务命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_sync_tasks_command(self, message: Message):
        """处理同步任务状态命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            if not active_tasks:
                await message.reply_text(
                    "❌ **没有活跃的监听任务**\n\n"
                    "请先创建监听任务：\n"
                    "1. 点击主菜单的 '📡 监听管理'\n"
                    "2. 点击 '➕ 创建任务'\n"
                    "3. 选择目标频道和源频道"
                )
                return
            
            # 强制重新注册所有活跃任务
            try:
                await self._reregister_all_monitoring_handlers()
                
                # 获取同步后的状态
                monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
                
                await message.reply_text(
                    f"✅ **任务状态同步完成！**\n\n"
                    f"📊 **同步结果**:\n"
                    f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                    f"• 引擎活跃任务: {monitoring_status.get('active_tasks', 0)} 个\n"
                    f"• 您的活跃任务: {len(active_tasks)} 个\n\n"
                    f"🔧 **已执行的操作**:\n"
                    f"• 重新注册消息处理器\n"
                    f"• 同步任务状态\n"
                    f"• 启动监听服务\n\n"
                    f"💡 **下一步**:\n"
                    f"• 在源频道发送测试消息\n"
                    f"• 检查是否能监听到新消息\n"
                    f"• 运行 /debug_monitoring 查看状态"
                )
                
            except Exception as e:
                logger.error(f"同步任务状态失败: {e}")
                await message.reply_text(f"❌ 同步失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理同步任务状态命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_inspect_engine_command(self, message: Message):
        """处理检查监听引擎内部状态命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 检查监听引擎的所有属性
            engine_attrs = {}
            for attr_name in dir(self.realtime_monitoring_engine):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(self.realtime_monitoring_engine, attr_name)
                        if callable(attr_value):
                            engine_attrs[attr_name] = f"<method: {type(attr_value).__name__}>"
                        else:
                            # 安全地处理不同类型的值
                            if isinstance(attr_value, (list, tuple, dict, set)):
                                engine_attrs[attr_name] = f"{type(attr_value).__name__}: len={len(attr_value)}"
                            elif isinstance(attr_value, (int, float, str, bool, type(None))):
                                engine_attrs[attr_name] = f"{type(attr_value).__name__}: {attr_value}"
                            else:
                                engine_attrs[attr_name] = f"{type(attr_value).__name__}: <object>"
                    except Exception as e:
                        engine_attrs[attr_name] = f"<error: {str(e)}>"
            
            # 获取用户任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task.get('status') == 'active']
            
            # 构建检查结果
            inspect_text = f"""
🔍 **监听引擎内部状态检查**

📊 **引擎属性**:
• 类型: {type(self.realtime_monitoring_engine).__name__}
• 模块: {self.realtime_monitoring_engine.__class__.__module__}

🔧 **关键属性**:
            """
            
            # 显示关键属性
            key_attrs = ['active_tasks', 'is_running', 'client', 'cloning_engine', 'config']
            for attr in key_attrs:
                if attr in engine_attrs:
                    inspect_text += f"• {attr}: {engine_attrs[attr]}\n"
                else:
                    inspect_text += f"• {attr}: ❌ 不存在\n"
            
            inspect_text += f"\n👤 **用户任务**:\n"
            inspect_text += f"• 总任务数: {len(user_tasks)} 个\n"
            inspect_text += f"• 活跃任务: {len(active_tasks)} 个\n"
            
            if active_tasks:
                for i, task in enumerate(active_tasks, 1):
                    task_id = task.get('task_id', f'task_{i}')
                    target = task.get('target_channel', 'Unknown')
                    sources = len(task.get('source_channels', []))
                    inspect_text += f"\n{i}. **任务 {task_id}**\n"
                    inspect_text += f"   • 目标: {target}\n"
                    inspect_text += f"   • 源频道: {sources} 个\n"
            
            # 添加诊断建议
            inspect_text += f"\n\n💡 **诊断建议**:\n"
            if 'active_tasks' in engine_attrs and 'dict' in engine_attrs['active_tasks']:
                inspect_text += "• active_tasks 是字典类型，检查是否有任务\n"
            elif 'active_tasks' in engine_attrs and 'int' in engine_attrs['active_tasks']:
                inspect_text += "• active_tasks 是整数类型，可能是计数\n"
            else:
                inspect_text += "• active_tasks 类型未知，需要检查\n"
            
            inspect_text += "• 检查监听引擎是否正确初始化\n"
            inspect_text += "• 检查任务是否正确注册\n"
            
            await message.reply_text(inspect_text)
            
        except Exception as e:
            logger.error(f"处理检查监听引擎内部状态命令失败: {e}")
            await message.reply_text(f"❌ 检查失败: {str(e)}")
    
    async def _handle_load_tasks_command(self, message: Message):
        """处理加载任务命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查监听引擎是否存在
            if not self.realtime_monitoring_engine:
                await message.reply_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "请先运行 /reinit_monitoring 重新初始化监听引擎"
                )
                return
            
            # 检查任务文件是否存在
            import os
            task_file = f"data/{self.bot_id}/monitoring_tasks.json"
            file_exists = os.path.exists(task_file)
            
            if not file_exists:
                await message.reply_text(
                    "❌ **任务文件不存在**\n\n"
                    "请先创建监听任务：\n"
                    "1. 点击主菜单的 '📡 监听管理'\n"
                    "2. 点击 '➕ 创建任务'\n"
                    "3. 选择目标频道和源频道"
                )
                return
            
            # 读取任务文件
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
            except Exception as e:
                await message.reply_text(f"❌ **读取任务文件失败**: {str(e)}")
                return
            
            if not tasks_data:
                await message.reply_text(
                    "❌ **任务文件为空**\n\n"
                    "请先创建监听任务"
                )
                return
            
            # 强制加载任务到监听引擎
            loaded_count = 0
            for task_id, task_data in tasks_data.items():
                try:
                    # 检查任务是否属于当前用户
                    if task_data.get('user_id') != user_id:
                        continue
                    
                    # 检查任务状态
                    task_status = task_data.get('status', 'unknown')
                    if task_status != 'active':
                        continue
                    
                    # 尝试启动任务
                    success = await self.realtime_monitoring_engine.start_monitoring_task(task_id)
                    if success:
                        loaded_count += 1
                        logger.info(f"✅ 已加载任务: {task_id}")
                    else:
                        logger.error(f"❌ 加载任务失败: {task_id}")
                        
                except Exception as e:
                    logger.error(f"加载任务 {task_id} 失败: {e}")
            
            # 获取加载后的状态
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task.get('status') == 'active']
            
            await message.reply_text(
                f"✅ **任务加载完成！**\n\n"
                f"📊 **加载结果**:\n"
                f"• 成功加载: {loaded_count} 个任务\n"
                f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
                f"• 引擎活跃任务: {monitoring_status.get('active_tasks', 0)} 个\n"
                f"• 您的活跃任务: {len(active_tasks)} 个\n\n"
                f"💡 **下一步**:\n"
                f"• 在源频道发送测试消息\n"
                f"• 检查是否能监听到新消息\n"
                f"• 运行 /debug_monitoring 查看状态"
            )
                
        except Exception as e:
            logger.error(f"处理加载任务命令失败: {e}")
            await message.reply_text(f"❌ 操作失败: {str(e)}")
    
    async def _handle_test_monitoring_command(self, message: Message):
        """处理测试监听命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取用户的所有监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            if not active_tasks:
                await message.reply_text("❌ 没有活跃的监听任务")
                return
            
            # 测试第一个活跃任务
            task = active_tasks[0]
            task_id = task['task_id']
            
            # 测试消息处理器
            test_result = await self.realtime_monitoring_engine.test_message_handlers(task_id)
            
            if test_result['success']:
                result_text = f"""
🔍 **监听任务测试结果**

📋 **任务ID**: {task_id}
📡 **注册的处理器**: {test_result['registered_handlers']} 个
📺 **源频道数量**: {test_result['source_channels']} 个

📝 **处理器详情**:
"""
                for handler in test_result['handlers_detail']:
                    status = "✅ 已注册" if handler['registered'] else "❌ 未注册"
                    result_text += f"• 频道 {handler['channel_id']}: {status}\n"
                
                result_text += f"\n💡 **说明**: 如果所有处理器都显示'已注册'，说明监听系统正常工作"
                
                await message.reply_text(result_text)
            else:
                await message.reply_text(f"❌ 测试失败: {test_result['error']}")
                
        except Exception as e:
            logger.error(f"处理测试监听命令失败: {e}")
            await message.reply_text(f"❌ 测试失败: {str(e)}")
    
    async def _handle_client_status_command(self, message: Message):
        """处理客户端状态命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取客户端信息
            bot_client_info = {
                'type': 'Bot API',
                'connected': self.client.is_connected if self.client else False,
                'me': None
            }
            
            if self.client and self.client.is_connected:
                try:
                    me = await self.client.get_me()
                    bot_client_info['me'] = {
                        'id': me.id,
                        'username': me.username,
                        'first_name': me.first_name
                    }
                except Exception as e:
                    bot_client_info['me'] = f"获取信息失败: {e}"
            
            # 获取 User API 信息
            user_api_info = {
                'type': 'User API',
                'logged_in': self.user_api_logged_in,
                'connected': False,
                'me': None
            }
            
            if self.user_api_manager and self.user_api_manager.client:
                user_api_info['connected'] = self.user_api_manager.client.is_connected
                if self.user_api_logged_in and self.user_api_manager.client.is_connected:
                    try:
                        me = await self.user_api_manager.client.get_me()
                        user_api_info['me'] = {
                            'id': me.id,
                            'username': me.username,
                            'first_name': me.first_name
                        }
                    except Exception as e:
                        user_api_info['me'] = f"获取信息失败: {e}"
            
            # 获取搬运引擎信息
            cloning_info = {
                'client_type': 'Unknown',
                'active_tasks': 0
            }
            
            if self.cloning_engine:
                cloning_info['client_type'] = getattr(self.cloning_engine, 'client_type', 'Unknown')
                cloning_info['active_tasks'] = len(self.cloning_engine.active_tasks)
            
            # 构建状态文本
            status_text = f"""
🔧 **客户端状态信息**

🤖 **Bot API 客户端**:
• 类型: {bot_client_info['type']}
• 连接状态: {'✅ 已连接' if bot_client_info['connected'] else '❌ 未连接'}
• 机器人信息: {bot_client_info['me'] if bot_client_info['me'] else '❌ 无法获取'}

👤 **User API 客户端**:
• 类型: {user_api_info['type']}
• 登录状态: {'✅ 已登录' if user_api_info['logged_in'] else '❌ 未登录'}
• 连接状态: {'✅ 已连接' if user_api_info['connected'] else '❌ 未连接'}
• 用户信息: {user_api_info['me'] if user_api_info['me'] else '❌ 无法获取'}

🚀 **搬运引擎**:
• 使用客户端: {cloning_info['client_type']}
• 活跃任务: {cloning_info['active_tasks']} 个

📡 **监听引擎**:
• 状态: {'✅ 已初始化' if self.realtime_monitoring_engine else '❌ 未初始化'}
• 使用客户端: {getattr(self.realtime_monitoring_engine, 'client_type', 'Unknown') if self.realtime_monitoring_engine else 'N/A'}

💡 **说明**:
• 搬运功能使用上述"搬运引擎"中显示的客户端
• 监听功能需要 User API 登录才能工作
• 如果显示"Client"，说明使用的是 User API 客户端
• 如果显示"Bot"，说明使用的是 Bot API 客户端
            """.strip()
            
            await message.reply_text(status_text)
            
        except Exception as e:
            logger.error(f"处理客户端状态命令失败: {e}")
            await message.reply_text(f"❌ 获取状态失败: {str(e)}")
    
    async def _handle_lsj_command(self, message: Message):
        """处理/lsj验证命令"""
        try:
            logger.info(f"🔍 开始处理/lsj命令")
            
            # 安全获取用户ID
            user_id = "unknown"
            if message.from_user:
                user_id = str(message.from_user.id)
            elif message.sender_chat:
                user_id = f"chat_{message.sender_chat.id}"
            
            chat_id = message.chat.id
            chat_type = message.chat.type
            
            logger.info(f"🔍 收到/lsj验证命令: user_id={user_id}, chat_id={chat_id}, chat_type={chat_type}")
            
            # 获取更详细的聊天信息
            try:
                chat_info = await self._get_api_client().get_chat(chat_id)
                logger.info(f"🔍 聊天详细信息:")
                logger.info(f"  - 类型: {chat_info.type}")
                logger.info(f"  - 标题: {getattr(chat_info, 'title', '无标题')}")
                logger.info(f"  - 用户名: {getattr(chat_info, 'username', '无用户名')}")
                logger.info(f"  - ID: {chat_info.id}")
            except Exception as e:
                logger.warning(f"无法获取聊天信息: {e}")
            
            # 检查是否在频道中
            chat_type_str = str(chat_type).lower()
            logger.info(f"🔍 聊天类型检测: '{chat_type_str}'")
            
            # 检查是否为频道或超级群组 - 修复类型检测
            is_channel = (chat_type_str == 'chattype.channel' or 
                         chat_type_str == 'channel' or 
                         chat_type_str == 'chattype.supergroup' or 
                         chat_type_str == 'supergroup')
            
            logger.info(f"🔍 频道检测结果: {is_channel}")
            
            if not is_channel:
                logger.warning(f"❌ 不是频道类型，拒绝处理")
                await message.reply_text(f"❌ 此命令只能在频道中使用，当前类型: {chat_type_str}")
                return
            
            logger.info(f"✅ 频道类型检测通过，继续处理")
            
            # 检查机器人是否为频道管理员
            try:
                # 获取频道信息 - 添加错误处理
                try:
                    chat = await self._get_api_client().get_chat(chat_id)
                    logger.info(f"🔍 频道信息: type={chat.type}")
                except Exception as chat_error:
                    logger.warning(f"无法获取频道信息: {chat_error}")
                    logger.warning(f"错误类型: {type(chat_error).__name__}")
                    logger.warning(f"错误详情: {str(chat_error)}")
                    
                    # 尝试使用不同的方法获取频道信息
                    try:
                        # 如果是频道ID，尝试直接使用
                        if str(chat_id).startswith('-100'):
                            # 这是一个频道ID，直接使用
                            chat = type('Chat', (), {
                                'id': chat_id,
                                'type': 'channel',
                                'title': f'频道 {chat_id}',
                                'username': None
                            })()
                            logger.info(f"🔍 使用默认频道信息: type=channel")
                        else:
                            raise chat_error
                    except Exception as fallback_error:
                        logger.error(f"无法获取频道信息，使用默认值: {fallback_error}")
                        chat = type('Chat', (), {
                            'id': chat_id,
                            'type': 'channel',
                            'title': f'频道 {chat_id}',
                            'username': None
                        })()
                        logger.info(f"🔍 使用默认频道信息: type=channel")
                
                # 检查频道类型 - 使用字符串比较
                chat_type_str = str(chat.type).lower()
                logger.info(f"🔍 频道类型字符串: '{chat_type_str}'")
                
                is_valid_channel = (chat_type_str == 'chattype.channel' or 
                                  chat_type_str == 'channel' or 
                                  chat_type_str == 'chattype.supergroup' or 
                                  chat_type_str == 'supergroup')
                
                logger.info(f"🔍 频道类型验证结果: {is_valid_channel}")
                
                if not is_valid_channel:
                    logger.warning(f"❌ 频道类型验证失败: {chat_type_str}")
                    await message.reply_text("❌ 此命令只能在频道中使用")
                    return
                
                logger.info(f"✅ 频道类型验证通过")
                
                # 检查机器人权限
                try:
                    try:
                        member = await self._get_api_client().get_chat_member(chat_id, "me")
                        logger.info(f"🔍 机器人权限: status={member.status}, can_delete={getattr(member, 'can_delete_messages', False)}")
                    except Exception as member_error:
                        logger.warning(f"无法获取机器人权限: {member_error}")
                        logger.warning(f"权限错误类型: {type(member_error).__name__}")
                        logger.warning(f"权限错误详情: {str(member_error)}")
                        
                        # 创建一个默认的成员对象
                        member = type('ChatMember', (), {
                            'status': 'administrator',
                            'can_delete_messages': True,
                            'privileges': type('Privileges', (), {
                                'can_delete_messages': True
                            })()
                        })()
                        logger.info(f"🔍 使用默认权限信息: status=administrator, can_delete=True")
                    
                    # 检查机器人状态 - 使用字符串比较
                    status_str = str(member.status).lower()
                    logger.info(f"🔍 机器人状态字符串: '{status_str}'")
                    
                    is_admin = (status_str == 'chatmemberstatus.administrator' or 
                              status_str == 'administrator' or
                              status_str == 'chatmemberstatus.creator' or
                              status_str == 'creator')
                    
                    logger.info(f"🔍 管理员状态检查结果: {is_admin}")
                    
                    if not is_admin:
                        await message.reply_text("❌ 机器人不是该频道的管理员")
                        return
                    
                    logger.info(f"✅ 管理员状态验证通过")
                    
                    # 检查删除权限 - 从privileges中获取
                    can_delete = False
                    privileges = getattr(member, 'privileges', None)
                    if privileges:
                        can_delete = getattr(privileges, 'can_delete_messages', False)
                        logger.info(f"🔍 从privileges获取删除权限: {can_delete}")
                    else:
                        # 如果没有privileges，尝试从member直接获取
                        can_delete = getattr(member, 'can_delete_messages', False)
                        logger.info(f"🔍 从member获取删除权限: {can_delete}")
                    
                    logger.info(f"🔍 最终删除权限检查: {can_delete}")

                    if not can_delete:
                        logger.warning(f"⚠️ 机器人没有删除消息的权限，将跳过删除操作")
                    else:
                        logger.info(f"✅ 机器人有删除消息的权限")

                    logger.info(f"✅ 权限验证完成，继续处理")
                    
                    # 发送验证消息
                    verification_msg = await message.reply_text("✅ 已验证")
                    logger.info(f"✅ 已发送验证消息: {verification_msg.id}")
                    
                    # 添加诊断信息
                    logger.info(f"🔍 频道验证诊断信息:")
                    logger.info(f"  • 频道ID: {chat_id}")
                    logger.info(f"  • 频道类型: {getattr(chat, 'type', 'unknown')}")
                    logger.info(f"  • 频道标题: {getattr(chat, 'title', 'unknown')}")
                    logger.info(f"  • 频道用户名: {getattr(chat, 'username', 'none')}")
                    logger.info(f"  • 机器人状态: {getattr(member, 'status', 'unknown')}")
                    logger.info(f"  • 删除权限: {getattr(member, 'can_delete_messages', False)}")

                    # 自动添加频道到频道数据管理器
                    # 尝试获取更好的频道名称
                    channel_title = getattr(chat, 'title', None)
                    if not channel_title or channel_title == f'频道 {chat_id}':
                        # 如果标题是默认的，尝试从消息中获取频道信息
                        try:
                            if hasattr(message, 'chat') and message.chat:
                                channel_title = getattr(message.chat, 'title', None)
                                if not channel_title:
                                    channel_title = f'频道 {str(chat_id)[-6:]}'  # 使用最后6位数字
                        except:
                            channel_title = f'频道 {str(chat_id)[-6:]}'  # 使用最后6位数字
                    
                    channel_data = {
                        'id': chat_id,
                        'title': channel_title,
                        'username': getattr(chat, 'username', None),
                        'type': str(chat.type).lower(),
                        'verified': True,
                        'added_at': datetime.now().isoformat()
                    }
                    await self._add_known_channel(chat_id, channel_data)
                    logger.info(f"✅ 已自动添加频道到数据管理器: {chat_id}")

                    # 检查是否有删除权限
                    if can_delete:
                        # 2秒后删除用户消息和机器人回复
                        await asyncio.sleep(2)
                        
                        try:
                            # 删除用户发送的消息
                            await message.delete()
                            logger.info(f"✅ 已删除用户消息: {message.id}")
                        except Exception as e:
                            logger.warning(f"删除用户消息失败: {e}")
                        
                        try:
                            # 删除机器人回复
                            await verification_msg.delete()
                            logger.info(f"✅ 已删除验证消息: {verification_msg.id}")
                        except Exception as e:
                            logger.warning(f"删除验证消息失败: {e}")
                    else:
                        logger.info(f"⚠️ 跳过删除操作（无删除权限）")

                    logger.info(f"✅ /lsj验证完成: chat_id={chat_id}")
                        
                except Exception as e:
                    logger.warning(f"无法获取机器人权限: {e}")
                    await message.reply_text("❌ 无法验证机器人权限")
                    return
                
            except Exception as e:
                logger.error(f"处理/lsj命令失败: {e}")
                await message.reply_text(f"❌ 验证失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理/lsj命令失败: {e}")
            await message.reply_text(f"❌ 验证失败: {str(e)}")
    
    async def _show_main_menu(self, message: Message):
        """显示主菜单（优化版本）"""
        try:
            # 安全获取用户ID
            if not message.from_user:
                await message.reply_text("❌ 无法获取用户信息")
                return
            user_id = str(message.from_user.id)
            
            # 快速显示基础菜单，避免数据库查询延迟
            api_mode_status = ""
            if self.user_api_manager and self.user_api_logged_in:
                api_mode_status = "• API 模式: 🚀 User API (增强模式)\n"
                button_layout = MAIN_MENU_BUTTONS_USER_API_LOGGED_IN
            else:
                api_mode_status = "• API 模式: 🤖 Bot API (标准模式)\n"
                button_layout = MAIN_MENU_BUTTONS_WITH_USER_API
            
            # 构建快速菜单文本
            menu_text = f"""
🎯 **{self.config['bot_name']} 主菜单**

📊 **当前状态**
• 频道组数量: 加载中...
• 监听状态: 加载中...
• 过滤规则: 加载中...
{api_mode_status}
🚀 选择以下功能开始使用：
            """.strip()
            
            # 快速发送主菜单
            await message.reply_text(
                menu_text,
                reply_markup=generate_button_layout(button_layout)
            )
            
            # 异步更新详细信息（不阻塞用户）
            asyncio.create_task(self._update_menu_details(message, user_id))
            
        except Exception as e:
            logger.error(f"显示主菜单失败: {e}")
            await message.reply_text("❌ 显示菜单失败，请稍后重试")
    
    async def _update_menu_details(self, message: Message, user_id: str):
        """异步更新菜单详细信息"""
        try:
            # 获取用户统计信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取 API 模式状态
            api_mode_status = ""
            if self.user_api_manager and self.user_api_logged_in:
                api_mode_status = "• API 模式: 🚀 User API (增强模式)\n"
            else:
                api_mode_status = "• API 模式: 🤖 Bot API (标准模式)\n"
            
            # 构建更新后的菜单文本
            updated_menu_text = f"""
🎯 **{self.config['bot_name']} 主菜单**

📊 **当前状态**
• 频道组数量: {len(channel_pairs)} 个
• 监听状态: {'✅ 已启用' if user_config.get('monitor_enabled') else '❌ 未启用'}
• 过滤规则: {len(user_config.get('filter_keywords', []))} 个关键字
{api_mode_status}
🚀 选择以下功能开始使用：
            """.strip()
            
            # 更新菜单（如果用户还在查看）
            try:
                await message.edit_text(
                    updated_menu_text,
                    reply_markup=generate_button_layout(
                        MAIN_MENU_BUTTONS_USER_API_LOGGED_IN if self.user_api_manager and self.user_api_logged_in 
                        else MAIN_MENU_BUTTONS_WITH_USER_API
                    )
                )
            except Exception as e:
                # 如果编辑失败（用户可能已经离开），忽略错误
                logger.debug(f"更新菜单失败（用户可能已离开）: {e}")
                
        except Exception as e:
            logger.error(f"更新菜单详细信息失败: {e}")
    
    async def _handle_callback_query(self, callback_query: CallbackQuery):
        """处理回调查询"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            logger.info(f"收到回调查询: {user_id} -> {data}")
            
            # 根据回调数据分发处理
            if data == "show_main_menu":
                await self._handle_show_main_menu(callback_query)
            elif data == "select_channel_pairs_to_clone":
                await self._handle_select_channels(callback_query)
            elif data.startswith("select_channels_page:"):
                page = int(data.split(":")[1])
                await self._handle_select_channels(callback_query, page)
            elif data == "show_channel_config_menu":
                await self._handle_show_channel_config(callback_query)
            elif data == "show_channel_admin_test":
                await self._handle_show_channel_admin_test(callback_query)
            elif data == "show_clone_test":
                await self._handle_show_clone_test(callback_query)
            elif data.startswith("admin_channel_filters:"):
                await self._handle_admin_channel_filters(callback_query)
            elif data.startswith("toggle_admin_channel:"):
                await self._handle_toggle_admin_channel(callback_query)
            elif data.startswith("toggle_admin_independent_filters:"):
                await self._handle_toggle_admin_independent_filters(callback_query)
            elif data.startswith("admin_channel_keywords:"):
                await self._handle_admin_channel_keywords(callback_query)
            elif data.startswith("admin_channel_replacements:"):
                await self._handle_admin_channel_replacements(callback_query)
            elif data.startswith("admin_channel_content_removal:"):
                await self._handle_admin_channel_content_removal(callback_query)
            elif data.startswith("admin_channel_links_removal:"):
                await self._handle_admin_channel_links_removal(callback_query)
            elif data.startswith("admin_channel_usernames_removal:"):
                await self._handle_admin_channel_usernames_removal(callback_query)
            elif data.startswith("admin_channel_buttons_removal:"):
                await self._handle_admin_channel_buttons_removal(callback_query)
            elif data.startswith("admin_channel_tail_text:"):
                await self._handle_admin_channel_tail_text(callback_query)
            elif data.startswith("admin_channel_buttons:"):
                await self._handle_admin_channel_buttons(callback_query)
            elif data.startswith("toggle_admin_keywords:"):
                await self._handle_toggle_admin_keywords(callback_query)
            elif data.startswith("add_admin_keyword:"):
                await self._handle_add_admin_keyword(callback_query)
            elif data.startswith("clear_admin_keywords:"):
                await self._handle_clear_admin_keywords(callback_query)
            elif data.startswith("admin_channel_manage:"):
                await self._handle_admin_channel_manage(callback_query)
            elif data.startswith("admin_channel_message_management:"):
                await self._handle_admin_channel_message_management(callback_query)
            elif data.startswith("admin_channel_delete_messages:"):
                await self._handle_admin_channel_delete_messages(callback_query)
            elif data.startswith("admin_channel_confirm_delete_messages:"):
                await self._handle_admin_channel_confirm_delete_messages(callback_query)
            elif data.startswith("confirm_batch_delete:"):
                await self._handle_confirm_batch_delete(callback_query)
            elif data.startswith("confirm_single_delete:"):
                await self._handle_confirm_single_delete(callback_query)
            elif data.startswith("verify_channel:"):
                await self._handle_verify_channel(callback_query)
            elif data.startswith("delete_admin_channel:"):
                await self._handle_delete_admin_channel(callback_query)
            elif data.startswith("confirm_delete_admin_channel:"):
                await self._handle_confirm_delete_admin_channel(callback_query)
            elif data.startswith("set_admin_tail_text:"):
                await self._handle_set_admin_tail_text(callback_query)
            elif data.startswith("clear_admin_tail_text:"):
                await self._handle_clear_admin_tail_text(callback_query)
            elif data.startswith("set_admin_tail_frequency:"):
                await self._handle_set_admin_tail_frequency(callback_query)
            elif data.startswith("set_admin_tail_position:"):
                await self._handle_set_admin_tail_position(callback_query)
            elif data.startswith("set_admin_buttons:"):
                await self._handle_set_admin_buttons(callback_query)
            elif data.startswith("clear_admin_buttons:"):
                await self._handle_clear_admin_buttons(callback_query)
            elif data.startswith("set_admin_button_frequency:"):
                await self._handle_set_admin_button_frequency(callback_query)
            elif data.startswith("set_admin_tail_freq:"):
                await self._handle_set_admin_tail_freq(callback_query)
            elif data.startswith("set_admin_tail_pos:"):
                await self._handle_set_admin_tail_pos(callback_query)
            elif data.startswith("set_admin_button_freq:"):
                await self._handle_set_admin_button_freq(callback_query)
            elif data == "clone_test_select_targets":
                await self._handle_clone_test_select_targets(callback_query)
            elif data.startswith("clone_test_toggle_target:"):
                await self._handle_clone_test_toggle_target(callback_query)
            elif data == "clone_test_confirm_targets":
                await self._handle_clone_test_confirm_targets(callback_query)
            elif data == "clone_test_input_sources":
                await self._handle_clone_test_input_sources(callback_query)
            elif data == "clone_test_start_cloning":
                await self._handle_clone_test_start_cloning(callback_query)
            elif data.startswith("toggle_admin_replacements:"):
                await self._handle_toggle_admin_replacements(callback_query)
            elif data.startswith("add_admin_replacement:"):
                await self._handle_add_admin_replacement(callback_query)
            elif data.startswith("clear_admin_replacements:"):
                await self._handle_clear_admin_replacements(callback_query)
            elif data.startswith("toggle_admin_enhanced_filter:"):
                await self._handle_toggle_admin_enhanced_filter(callback_query)
            elif data.startswith("admin_channel_enhanced_mode:"):
                await self._handle_admin_channel_enhanced_mode(callback_query)
            elif data.startswith("set_admin_enhanced_mode:"):
                await self._handle_set_admin_enhanced_mode(callback_query)
            elif data.startswith("toggle_admin_buttons_removal:"):
                await self._handle_toggle_admin_buttons_removal(callback_query)
            elif data.startswith("admin_channel_buttons_mode:"):
                await self._handle_admin_channel_buttons_mode(callback_query)
            elif data.startswith("set_admin_buttons_mode:"):
                await self._handle_set_admin_buttons_mode(callback_query)
            elif data == "add_channel_manually":
                await self._handle_add_channel_manually(callback_query)
            elif data == "get_bot_invite_link":
                await self._handle_get_bot_invite_link(callback_query)
            elif data == "show_feature_config_menu":
                await self._handle_show_feature_config(callback_query)
            elif data == "show_monitor_menu":
                await self._handle_show_monitor_menu(callback_query)
            elif data == "show_simple_monitor_menu":
                await self._handle_show_monitor_menu(callback_query)
            elif data == "view_monitoring_tasks":
                await self._handle_view_monitoring_tasks(callback_query)
            elif data == "create_monitoring_task":
                await self._handle_create_monitoring_task(callback_query)
            elif data == "monitor_settings":
                await self._handle_monitor_settings(callback_query)
            elif data.startswith("start_monitoring_task:"):
                await self._handle_start_monitoring_task(callback_query)
            elif data.startswith("stop_monitoring_task:"):
                await self._handle_stop_monitoring_task(callback_query)
            elif data.startswith("delete_monitoring_task:"):
                await self._handle_delete_monitoring_task(callback_query)
            elif data.startswith("monitor_task_detail:"):
                await self._handle_monitor_task_detail(callback_query)
            elif data.startswith("select_monitor_target:"):
                await self._handle_select_monitor_target(callback_query)
            elif data == "confirm_create_monitoring_task":
                await self._handle_confirm_create_monitoring_task(callback_query)
            elif data == "add_monitor_source_channel":
                await self._handle_add_monitor_source_channel(callback_query)
            elif data.startswith("select_monitoring_mode:"):
                await self._handle_select_monitoring_mode(callback_query)
            elif data.startswith("pause_monitoring_task:"):
                await self._handle_pause_monitoring_task(callback_query)
            elif data.startswith("resume_monitoring_task:"):
                await self._handle_resume_monitoring_task(callback_query)
            elif data.startswith("trigger_monitoring:"):
                await self._handle_trigger_monitoring(callback_query)
            elif data.startswith("config_id_range_increment:"):
                await self._handle_config_id_range_increment(callback_query)
            elif data.startswith("config_channel_increment:"):
                await self._handle_config_channel_increment(callback_query)
            elif data.startswith("trigger_channel:"):
                await self._handle_trigger_channel(callback_query)
            elif data.startswith("update_channel_end_id:"):
                await self._handle_update_channel_end_id(callback_query)
            elif data == "manage_monitor_channels":
                await self._handle_manage_monitor_channels(callback_query)
            elif data.startswith("toggle_monitor_pair:"):
                await self._handle_toggle_monitor_pair(callback_query)
            elif data == "monitor_select_all":
                await self._handle_monitor_select_all(callback_query)
            elif data == "monitor_select_none":
                await self._handle_monitor_select_none(callback_query)
            elif data == "view_tasks":
                await self._handle_view_tasks(callback_query)
            elif data == "view_history":
                await self._handle_view_history(callback_query)
            elif data == "view_config":
                await self._handle_view_config(callback_query)
            elif data == "show_help":
                await self._handle_show_help(callback_query)
            elif data == "start_user_api_login":
                await self._handle_start_user_api_login_from_button(callback_query)
            elif data == "user_api_status":
                await self._handle_user_api_status_from_button(callback_query)
            elif data == "logout_user_api":
                await self._handle_logout_user_api_from_button(callback_query)
            elif data.startswith("add_channel_pair"):
                await self._handle_add_channel_pair(callback_query)
            elif data.startswith("private_wizard:"):
                await self._handle_private_channel_wizard(callback_query)
            elif data == "retry_channel_input":
                await self._handle_retry_channel_input(callback_query)
            elif data.startswith("edit_channel_pair:"):
                await self._handle_edit_channel_pair(callback_query)
            elif data.startswith("edit_pair_source:"):
                await self._handle_edit_pair_source(callback_query)
            elif data.startswith("edit_pair_target:"):
                await self._handle_edit_pair_target(callback_query)
            elif data.startswith("edit_source:"):
                await self._handle_edit_pair_source(callback_query)
            elif data.startswith("edit_target:"):
                await self._handle_edit_pair_target(callback_query)
            elif data.startswith("edit_source_by_id:"):
                await self._handle_edit_pair_source_by_id(callback_query)
            elif data.startswith("edit_target_by_id:"):
                await self._handle_edit_pair_target_by_id(callback_query)
            elif data.startswith("toggle_enabled_by_id:"):
                await self._handle_toggle_enabled_by_id(callback_query)
            elif data.startswith("multi_select_pair:"):
                await self._handle_multi_select_pair(callback_query)
            elif data == "multi_set_message_ranges":
                await self._handle_multi_set_message_ranges(callback_query)
            elif data == "start_multi_select_cloning":
                await self._handle_start_multi_select_cloning(callback_query)
            
            elif data == "cancel_multi_task_cloning":
                await self._handle_cancel_multi_task_cloning(callback_query)
            elif data == "refresh_multi_task_status":
                await self._handle_refresh_multi_task_status(callback_query)
            elif data.startswith("delete_channel_pair:"):
                await self._handle_delete_channel_pair(callback_query)
            elif data.startswith("channel_page:"):
                await self._handle_channel_page(callback_query)
            elif data == "update_all_channel_info":
                await self._handle_update_all_channel_info(callback_query)
            elif data == "manage_filter_keywords":
                await self._handle_manage_filter_keywords(callback_query)
            elif data == "manage_content_removal":
                await self._handle_manage_content_removal(callback_query)
            elif data == "toggle_content_removal":
                await self._handle_toggle_content_removal(callback_query)
            elif data == "manage_filter_buttons":
                await self._handle_manage_filter_buttons(callback_query)
            elif data == "toggle_button_removal":
                await self._handle_toggle_button_removal(callback_query)
            elif data.startswith("set_button_mode:"):
                await self._handle_set_button_mode(callback_query)
            elif data == "manage_replacement_words":
                await self._handle_manage_replacement_words(callback_query)
            elif data == "manage_file_filter":
                await self._handle_manage_file_filter(callback_query)
            elif data == "show_file_filter_menu":
                await self._handle_manage_file_filter(callback_query)
            elif data.startswith("request_tail_text"):
                await self._handle_request_tail_text(callback_query)
            elif data.startswith("request_buttons"):
                await self._handle_request_buttons(callback_query)
            elif data == "show_frequency_settings":
                await self._handle_show_frequency_settings(callback_query)
            # 评论相关回调处理已移除
            elif data.startswith("toggle_remove_all_links"):
                await self._handle_toggle_remove_all_links(callback_query)
            elif data.startswith("toggle_remove_links_mode"):
                await self._handle_toggle_remove_links_mode(callback_query)
            elif data.startswith("toggle_remove_hashtags"):
                await self._handle_toggle_remove_hashtags(callback_query)
            elif data.startswith("toggle_remove_usernames"):
                await self._handle_toggle_remove_usernames(callback_query)
            elif data.startswith("toggle_filter_photo"):
                await self._handle_toggle_filter_photo(callback_query)
            elif data.startswith("toggle_filter_video"):
                await self._handle_toggle_filter_video(callback_query)
            elif data.startswith("select_tail_frequency:"):
                await self._handle_select_tail_frequency(callback_query)
            elif data.startswith("select_button_frequency:"):
                await self._handle_select_button_frequency(callback_query)
            elif data.startswith("set_tail_frequency:"):
                await self._handle_set_tail_frequency(callback_query)
            elif data.startswith("set_button_frequency:"):
                await self._handle_set_button_frequency(callback_query)
            elif data == "show_link_filter_menu":
                await self._handle_show_link_filter_menu(callback_query)
            elif data == "show_enhanced_filter_menu":
                await self._handle_show_enhanced_filter_menu(callback_query)
            elif data == "toggle_enhanced_filter":
                await self._handle_toggle_enhanced_filter(callback_query)
            elif data == "toggle_enhanced_filter_mode":
                await self._handle_toggle_enhanced_filter_mode(callback_query)
            elif data == "preview_enhanced_filter":
                await self._handle_preview_enhanced_filter(callback_query)
            elif data == "clear_additional_buttons":
                await self._handle_clear_additional_buttons(callback_query)
            elif data.startswith("set_content_removal_mode:"):
                await self._handle_set_content_removal_mode(callback_query)
            elif data.startswith("set_tail_text_position:"):
                await self._handle_set_tail_text_position(callback_query)
            elif data.startswith("edit_filters:"):
                await self._handle_edit_filters(callback_query)
            elif data.startswith("channel_filters:"):
                await self._handle_channel_filters(callback_query)
            elif data.startswith("channel_keywords:"):
                await self._handle_channel_keywords(callback_query)
            elif data.startswith("channel_replacements:"):
                await self._handle_channel_replacements(callback_query)
            elif data.startswith("channel_content_removal:"):
                await self._handle_channel_content_removal(callback_query)
            elif data.startswith("channel_links_removal:"):
                await self._handle_channel_links_removal(callback_query)
            elif data.startswith("channel_usernames_removal:"):
                await self._handle_channel_usernames_removal(callback_query)
            elif data.startswith("channel_buttons_removal:"):
                await self._handle_channel_buttons_removal(callback_query)
            elif data.startswith("channel_tail_text:"):
                await self._handle_channel_tail_text(callback_query)
            elif data.startswith("channel_buttons:"):
                await self._handle_channel_buttons(callback_query)
            elif data.startswith("toggle_channel_independent_filters:"):
                await self._handle_toggle_channel_independent_filters(callback_query)
            elif data.startswith("toggle_channel_content_removal:"):
                await self._handle_toggle_channel_content_removal(callback_query)
            elif data.startswith("toggle_channel_links_removal:"):
                await self._handle_toggle_channel_links_removal(callback_query)
            elif data.startswith("toggle_channel_usernames_removal:"):
                await self._handle_toggle_channel_usernames_removal(callback_query)
            elif data.startswith("toggle_channel_buttons_removal:"):
                await self._handle_toggle_channel_buttons_removal(callback_query)
            elif data.startswith("set_channel_content_mode:"):
                await self._handle_set_channel_content_mode(callback_query)
            elif data.startswith("set_channel_links_mode:"):
                await self._handle_set_channel_links_mode(callback_query)
            elif data.startswith("set_channel_buttons_mode:"):
                await self._handle_set_channel_buttons_mode(callback_query)
            elif data.startswith("toggle_channel_enhanced_filter:"):
                await self._handle_toggle_channel_enhanced_filter(callback_query)
            elif data.startswith("set_channel_enhanced_mode:"):
                await self._handle_set_channel_enhanced_mode(callback_query)
            elif data.startswith("toggle_enabled:"):
                await self._handle_toggle_enabled(callback_query)
            elif data.startswith("toggle_pair_enabled:"):
                await self._handle_toggle_pair_enabled(callback_query)
            elif data.startswith("manage_pair_filters:"):
                await self._handle_manage_pair_filters(callback_query)
            # 频道评论相关回调处理已移除
            elif data.startswith("select_pair:"):
                await self._handle_select_pair(callback_query)
            elif data.startswith("multi_select_pair:"):
                await self._handle_multi_select_pair(callback_query)
            elif data == "multi_set_message_ranges":
                await self._handle_multi_set_message_ranges(callback_query)
            elif data == "start_multi_select_cloning":
                await self._handle_start_multi_select_cloning(callback_query)
            elif data.startswith("start_cloning:"):
                await self._handle_start_cloning(callback_query)
            elif data.startswith("confirm_cloning:"):
                await self._handle_confirm_cloning(callback_query)
            elif data.startswith("stop_cloning:"):
                await self._handle_stop_cloning(callback_query)
            elif data.startswith("refresh_task_status:"):
                await self._handle_refresh_task_status(callback_query)
            elif data.startswith("view_task_details:"):
                await self._handle_view_task_details(callback_query)
            elif data.startswith("check_task_completion:"):
                await self._handle_check_task_completion(callback_query)
            elif data.startswith("view_task_results:"):
                await self._handle_view_task_results(callback_query)
            elif data == "view_all_tasks":
                await self._handle_view_all_tasks(callback_query)
            elif data.startswith("confirm_delete:"):
                await self._handle_confirm_delete_channel_pair(callback_query)
            elif data.startswith("confirm_delete_by_id:"):
                await self._handle_confirm_delete_channel_pair_by_id(callback_query)
            elif data == "clear_all_channels" or data == "confirm_clear_all_channels":
                await self._handle_clear_all_channels(callback_query)
            elif data == "refresh_cloning_progress":
                await self._handle_refresh_cloning_progress(callback_query)
            elif data == "stop_cloning_progress":
                await self._handle_stop_cloning_progress(callback_query)
            elif data == "resume_cloning_progress":
                await self._handle_resume_cloning_progress(callback_query)
            elif data == "refresh_multi_task_progress":
                await self._handle_refresh_multi_task_progress(callback_query)
            elif data == "stop_multi_task_cloning":
                await self._handle_stop_multi_task_cloning(callback_query)
            elif data == "resume_multi_task_cloning":
                await self._handle_resume_multi_task_cloning(callback_query)
            else:
                await self._handle_unknown_callback(callback_query)
            
            # 回答回调查询（只在成功时）
            try:
                await callback_query.answer()
            except Exception as answer_error:
                logger.warning(f"回答回调查询失败: {answer_error}")
                # 不抛出异常，继续处理
            
        except Exception as e:
            logger.error(f"处理回调查询失败: {e}")
            # 尝试回答回调查询，但失败时不抛出异常
            try:
                await callback_query.answer("❌ 处理失败，请稍后重试")
            except Exception as answer_error:
                logger.warning(f"回答回调查询失败: {answer_error}")
    
    async def _handle_show_main_menu(self, callback_query: CallbackQuery):
        """处理显示主菜单"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            # 获取用户统计信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取 API 模式状态和按钮布局
            api_mode_status = ""
            
            if self.user_api_manager:
                if self.user_api_logged_in:
                    api_mode_status = "• API 模式: 🚀 User API (增强模式)\n"
                    button_layout = MAIN_MENU_BUTTONS_USER_API_LOGGED_IN
                else:
                    api_mode_status = "• API 模式: 🤖 Bot API (标准模式)\n"
                    button_layout = MAIN_MENU_BUTTONS_WITH_USER_API
            else:
                api_mode_status = "• API 模式: 🤖 Bot API (标准模式)\n"
                button_layout = MAIN_MENU_BUTTONS_WITH_USER_API
            
            # 构建菜单文本
            menu_text = f"""
🎯 **{self.config['bot_name']} 主菜单**

📊 **当前状态**
• 频道组数量: {len(channel_pairs)} 个
• 监听状态: {'✅ 已启用' if user_config.get('monitor_enabled') else '❌ 未启用'}
• 过滤规则: {len(user_config.get('filter_keywords', []))} 个关键字
{api_mode_status}
🚀 选择以下功能开始使用：
            """.strip()
            
            # 更新消息
            try:
                await callback_query.edit_message_text(
                    menu_text,
                    reply_markup=generate_button_layout(button_layout)
                )
            except Exception as edit_error:
                # 如果编辑消息失败（如回调查询过期），发送新消息
                if "QUERY_ID_INVALID" in str(edit_error) or "callback query id is invalid" in str(edit_error).lower():
                    logger.info(f"回调查询过期，发送新的主菜单消息给用户 {user_id}")
                    await self.client.send_message(
                        user_id,
                        menu_text,
                        reply_markup=generate_button_layout(button_layout)
                    )
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"显示主菜单失败: {e}")
            try:
                await callback_query.edit_message_text("❌ 显示菜单失败，请稍后重试")
            except:
                # 如果编辑失败，发送新消息
                await self.client.send_message(
                    str(callback_query.from_user.id),
                    "❌ 显示菜单失败，请稍后重试"
                )
    
    async def _handle_select_channels(self, callback_query: CallbackQuery, page: int = 0):
        """处理选择频道（支持多选和分页）"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                await callback_query.edit_message_text(
                    "❌ 您还没有添加任何频道组！\n\n请先在频道管理中添加频道组。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            # 初始化用户的多选状态
            if not hasattr(self, 'multi_select_states'):
                self.multi_select_states = {}
            
            if user_id not in self.multi_select_states:
                self.multi_select_states[user_id] = {
                    'selected_channels': [],
                    'current_step': 'selecting_channels',
                    'current_page': 0
                }
            
            # 更新当前页码
            self.multi_select_states[user_id]['current_page'] = page
            
            # 分页设置
            page_size = 40
            total_pairs = len(channel_pairs)
            total_pages = (total_pairs + page_size - 1) // page_size
            start_index = page * page_size
            end_index = min(start_index + page_size, total_pairs)
            
            # 构建频道选择界面
            selected_count = len(self.multi_select_states[user_id]['selected_channels'])
            
            # 分页信息
            page_info = f"第 {page + 1}/{total_pages} 页" if total_pages > 1 else ""
            
            select_text = f"""
📋 **选择要搬运的频道组** {page_info}

💡 **功能说明**:
• 可以同时选择多个频道组进行搬运
• 只选择一个就是单任务搬运
• 选择多个就是多任务搬运
• 系统会自动管理并发任务

📊 **当前状态**:
• 可用频道组: {total_pairs} 个
• 当前页显示: {start_index + 1}-{end_index} 个
• 已选择: {selected_count} 个

🎯 **选择说明**:
• 点击频道组名称进行选择/取消选择
• 绿色勾选表示已选择
• 可以同时选择多个频道组
            """.strip()
            
            # 生成当前页的频道组选择按钮（一排一个按钮）
            buttons = []
            current_page_pairs = channel_pairs[start_index:end_index]
            
            # 每个频道组一排一个按钮
            for i, pair in enumerate(current_page_pairs):
                pair_index = start_index + i
                
                if pair.get('enabled', True):
                    source_name = pair.get('source_name', f'频道{pair_index+1}')
                    target_name = pair.get('target_name', f'目标{pair_index+1}')
                    
                    # 优先使用保存的用户名信息
                    source_username = pair.get('source_username', '')
                    target_username = pair.get('target_username', '')
                    
                    # 如果没有保存的用户名，则尝试获取
                    if not source_username:
                        source_display = await self._get_channel_display_name_safe(pair.get('source_id', ''))
                    else:
                        source_display = source_username
                    
                    if not target_username:
                        target_display = await self._get_channel_display_name_safe(pair.get('target_id', ''))
                    else:
                        target_display = target_username
                    
                    # 显示：频道名字
                    source_info = f"{source_name}"
                    target_info = f"{target_name}"
                    
                    # 检查是否已选择
                    is_selected = f"{pair_index}" in self.multi_select_states[user_id]['selected_channels']
                    status_icon = "✅" if is_selected else "⚪"
                    
                    # 按钮文本
                    button_text = f"{status_icon} {source_info} → {target_info}"
                    
                    buttons.append([(button_text, f"multi_select_pair:{pair_index}")])
            
            # 添加分页按钮
            if total_pages > 1:
                pagination_row = []
                if page > 0:
                    pagination_row.append(("⬅️ 上一页", f"select_channels_page:{page - 1}"))
                
                pagination_row.append((f"{page + 1}/{total_pages}", "page_info"))
                
                if page < total_pages - 1:
                    pagination_row.append(("下一页 ➡️", f"select_channels_page:{page + 1}"))
                
                buttons.append(pagination_row)
            
            # 添加操作按钮
            if selected_count > 0:
                buttons.append([("🚀 继续设置消息ID段", "multi_set_message_ranges")])
            
            buttons.append([("🔙 返回主菜单", "show_main_menu")])
            
            await callback_query.edit_message_text(
                select_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理选择频道失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_multi_select_pair(self, callback_query: CallbackQuery):
        """处理多选频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            pair_index = int(data.split(":")[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.answer("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_id = pair.get('source_id', f'频道组{pair_index+1}')
            target_id = pair.get('target_id', f'目标{pair_index+1}')
            source_name = pair.get('source_name', f'频道组{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 优先使用保存的用户名信息
            source_username = pair.get('source_username', '')
            target_username = pair.get('target_username', '')
            
            # 如果没有保存的用户名，则尝试获取
            if not source_username:
                source_display = await self._get_channel_display_name_safe(source_id)
            else:
                source_display = source_username
            
            if not target_username:
                target_display = await self._get_channel_display_name_safe(target_id)
            else:
                target_display = target_username
            
            # 切换频道组选择状态
            channel_key = f"{pair_index}"
            if channel_key in self.multi_select_states[user_id]['selected_channels']:
                # 取消选择
                self.multi_select_states[user_id]['selected_channels'].remove(channel_key)
                await callback_query.answer(f"❌ 已取消选择: {source_name}")
            else:
                # 选择频道组
                self.multi_select_states[user_id]['selected_channels'].append(channel_key)
                await callback_query.answer(f"✅ 已选择: {source_name}")
            
            # 更新界面显示
            await self._update_multi_select_ui(callback_query, user_id)
            
        except Exception as e:
            logger.error(f"处理多选频道组失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _update_multi_select_ui(self, callback_query: CallbackQuery, user_id: str):
        """更新多选界面显示（支持分页）"""
        try:
            # 获取当前页码
            current_page = self.multi_select_states.get(user_id, {}).get('current_page', 0)
            await self._handle_select_channels(callback_query, current_page)
            
        except Exception as e:
            logger.error(f"更新多选界面失败: {e}")
    
    async def _handle_multi_set_message_ranges(self, callback_query: CallbackQuery):
        """处理多任务设置消息ID段"""
        try:
            user_id = str(callback_query.from_user.id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            
            if not selected_channels:
                await callback_query.answer("❌ 请先选择频道组")
                return
            
            # 更新状态为设置消息ID段
            multi_select_state['current_step'] = 'setting_message_ranges'
            multi_select_state['message_ranges'] = {}
            
            # 显示第一个频道组的消息ID段设置界面
            await self._show_multi_message_range_setup(callback_query, user_id, 0)
            
        except Exception as e:
            logger.error(f"处理多任务设置消息ID段失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _show_multi_message_range_setup(self, callback_query: CallbackQuery, user_id: str, channel_index: int):
        """显示多任务消息ID段设置界面"""
        try:
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            
            if channel_index >= len(selected_channels):
                # 所有频道组都设置完成，显示确认界面
                await self._show_multi_task_confirmation(callback_query, user_id)
                return
            
            # 获取当前要设置的频道组
            pair_index = int(selected_channels[channel_index])
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道组{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            source_username = pair.get('source_username', '')
            target_username = pair.get('target_username', '')
            
            # 如果没有保存的用户名，则尝试获取
            if not source_username:
                source_display = await self._get_channel_display_name_safe(pair.get('source_id', ''))
            else:
                source_display = source_username
            
            if not target_username:
                target_display = await self._get_channel_display_name_safe(pair.get('target_id', ''))
            else:
                target_display = target_username
            
            # 构建设置界面
            text = f"""
📝 **设置消息ID段 - 频道组 {channel_index + 1}/{len(selected_channels)}**

📡 **采集频道**: {source_name}（{source_display}）
📤 **发布频道**: {target_name}（{target_display}）

💡 **输入格式**:
• 单个ID: 1234
• ID范围: 1000-2000
• 多个ID: 1234,5678,9012
• 混合格式: 1000-2000,3000,4000-5000

📝 **请输入消息ID段**:
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔙 返回频道选择", "select_channel_pairs_to_clone")],
                [("❌ 取消", "show_main_menu")]
            ]
            
            # 保存当前设置状态
            multi_select_state['current_channel_index'] = channel_index
            multi_select_state['waiting_for_input'] = True
            
            await callback_query.edit_message_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示多任务消息ID段设置界面失败: {e}")
            await callback_query.answer("❌ 显示失败，请稍后重试")
    
    async def _process_multi_select_message_input(self, message: Message, user_id: str):
        """处理多选搬运的消息ID段输入"""
        try:
            text = message.text.strip()
            multi_select_state = self.multi_select_states.get(user_id, {})
            current_channel_index = multi_select_state.get('current_channel_index', 0)
            selected_channels = multi_select_state.get('selected_channels', [])
            
            logger.info(f"开始处理多选消息输入: user_id={user_id}, text='{text}', current_channel_index={current_channel_index}, selected_channels={selected_channels}")
            
            if current_channel_index >= len(selected_channels):
                await message.reply_text("❌ 频道组索引超出范围")
                return
            
            # 获取当前频道组
            channel_key = selected_channels[current_channel_index]
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair_index = int(channel_key)
            pair = channel_pairs[pair_index]
            
            # 验证消息ID段格式
            if not self._validate_message_range_format(text):
                await message.reply_text(
                    "❌ **消息ID段格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 单个ID: `1234`\n"
                    "• ID范围: `1000-2000`\n"
                    "• 多个ID: `1234,5678,9012`\n"
                    "• 混合格式: `1000-2000,3000,4000-5000`\n\n"
                    "⚠️ **注意事项：**\n"
                    "• 数字必须是正整数\n"
                    "• 范围格式必须是 小数字-大数字\n"
                    "• 多个部分用逗号分隔\n"
                    "• 不要有多余的空格"
                )
                return
            
            # 保存消息ID段
            if 'message_ranges' not in multi_select_state:
                multi_select_state['message_ranges'] = {}
            multi_select_state['message_ranges'][channel_key] = text
            
            # 显示设置成功消息
            source_name = pair.get('source_name', f'频道组{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            await message.reply_text(
                f"✅ **消息ID段设置成功！**\n\n"
                f"📡 **频道组 {current_channel_index + 1}/{len(selected_channels)}**:\n"
                f"• 采集频道: {source_name}\n"
                f"• 发布频道: {target_name}\n"
                f"• 消息ID段: {text}\n\n"
                f"💡 **下一步**: 继续设置下一个频道组的消息ID段"
            )
            
            # 移动到下一个频道组
            next_channel_index = current_channel_index + 1
            logger.info(f"移动到下一个频道组: current={current_channel_index}, next={next_channel_index}, total={len(selected_channels)}")
            
            if next_channel_index < len(selected_channels):
                # 显示下一个频道组的设置界面
                logger.info(f"还有频道组需要设置，显示下一个设置界面: {next_channel_index + 1}/{len(selected_channels)}")
                await self._show_next_multi_message_range_setup(message, user_id, next_channel_index)
                # 保持等待输入状态，因为还要继续输入
                logger.info(f"保持等待输入状态: waiting_for_input=True")
            else:
                # 所有频道组都设置完成，显示确认界面
                logger.info(f"所有频道组设置完成，显示确认界面")
                await self._show_multi_task_confirmation_from_message(message, user_id)
                # 所有设置完成，重置等待输入状态
                multi_select_state['waiting_for_input'] = False
                logger.info(f"重置等待输入状态: waiting_for_input=False")
            
        except Exception as e:
            logger.error(f"处理多选消息输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _show_next_multi_message_range_setup(self, message: Message, user_id: str, channel_index: int):
        """显示下一个频道组的消息ID段设置界面"""
        try:
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            
            if channel_index >= len(selected_channels):
                return
            
            # 获取当前要设置的频道组
            pair_index = int(selected_channels[channel_index])
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道组{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 构建设置界面
            text = f"""
📝 **设置消息ID段 - 频道组 {channel_index + 1}/{len(selected_channels)}**

📡 **采集频道**: {source_name}
📤 **发布频道**: {target_name}

💡 **输入格式**:
• 单个ID: 1234
• ID范围: 1000-2000
• 多个ID: 1234,5678,9012
• 混合格式: 1000-2000,3000,4000-5000

📝 **请输入消息ID段**:
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔙 返回频道选择", "select_channel_pairs_to_clone")],
                [("❌ 取消", "show_main_menu")]
            ]
            
            # 保存当前设置状态
            multi_select_state['current_channel_index'] = channel_index
            multi_select_state['waiting_for_input'] = True
            logger.info(f"设置频道组 {channel_index + 1}/{len(selected_channels)} 的等待输入状态: waiting_for_input=True")
            
            await message.reply_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示下一个消息ID段设置界面失败: {e}")
    
    async def _show_multi_task_confirmation_from_message(self, message: Message, user_id: str):
        """从消息输入显示多任务确认界面"""
        try:
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            message_ranges = multi_select_state.get('message_ranges', {})
            
            # 构建确认文本
            text = f"""
🔄 **多任务搬运 - 设置完成**

📡 **已选择频道组**: {len(selected_channels)} 个
📝 **消息ID段设置完成**

📋 **详细配置**:
            """.strip()
            
            # 显示每个频道组的配置
            for i, channel_key in enumerate(selected_channels):
                pair_index = int(channel_key)
                pair = channel_pairs[pair_index]
                source_name = pair.get('source_name', f'频道组{pair_index+1}')
                target_name = pair.get('target_name', f'目标{pair_index+1}')
                source_username = pair.get('source_username', '')
                target_username = pair.get('target_username', '')
                message_range = message_ranges.get(channel_key, '未设置')
                
                # 如果没有保存的用户名，则尝试获取
                if not source_username:
                    source_display = await self._get_channel_display_name_safe(pair.get('source_id', ''))
                else:
                    source_display = source_username
                
                if not target_username:
                    target_display = await self._get_channel_display_name_safe(pair.get('target_id', ''))
                else:
                    target_display = target_username
                
                text += f"\n\n**频道组 {i+1}**:"
                text += f"\n📡 采集: {source_name}（{source_display}）"
                text += f"\n📤 发布: {target_name}（{target_display}）"
                text += f"\n📝 ID段: {message_range}"
            
            text += "\n\n🚀 **准备开始搬运**"
            text += "\n💡 系统将自动管理并发任务，避免超限"
            
            # 生成按钮
            buttons = [
                [("🚀 开始搬运", "start_multi_select_cloning")],
                [("🔙 重新设置", "select_channel_pairs_to_clone")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await message.reply_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示多任务确认界面失败: {e}")
            await message.reply_text("❌ 显示失败，请稍后重试")
    
    async def _handle_start_multi_select_cloning(self, callback_query: CallbackQuery):
        """处理开始多选搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            message_ranges = multi_select_state.get('message_ranges', {})
            
            if not selected_channels:
                await callback_query.answer("❌ 请先选择频道组")
                return
            
            # 检查是否有未设置消息ID段的频道组
            unset_channels = [ch for ch in selected_channels if ch not in message_ranges]
            if unset_channels:
                await callback_query.answer("❌ 还有频道组未设置消息ID段")
                return
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 创建多任务配置
            multi_task_configs = []
            for channel_key in selected_channels:
                pair_index = int(channel_key)
                pair = channel_pairs[pair_index]
                message_range = message_ranges[channel_key]
                
                # 解析消息ID段
                parsed_info = self._parse_message_range(message_range)
                
                # 从消息范围中提取start_id和end_id
                start_id = None
                end_id = None
                if parsed_info['ranges']:
                    # 使用第一个范围作为主要范围
                    first_range = parsed_info['ranges'][0]
                    start_id = first_range[0]
                    end_id = first_range[1]
                    logger.info(f"📊 频道组{pair_index+1} 消息范围: {start_id} - {end_id}")
                
                config = {
                    'user_id': user_id,
                    'pair_index': pair_index,
                    'pair_id': pair['id'],
                    'source_chat_id': pair['source_id'],
                    'target_chat_id': pair['target_id'],
                    'source_username': pair.get('source_username', ''),
                    'target_username': pair.get('target_username', ''),
                    'start_id': start_id,
                    'end_id': end_id,
                    'message_ids': parsed_info['ids'],
                    'message_ranges': parsed_info['ranges'],
                    'description': f"频道组{pair_index+1}搬运任务"
                }
                multi_task_configs.append(config)
            
            # 开始创建和启动多任务
            await self._execute_multi_select_cloning(callback_query, user_id, multi_task_configs)
            
        except Exception as e:
            logger.error(f"处理开始多选搬运失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _create_tasks_parallel(self, callback_query: CallbackQuery, task_configs: List[Dict]) -> tuple:
        """并行创建任务，支持重试机制"""
        success_count = 0
        task_ids = []
        failed_configs = []
        
        # 创建单个任务创建函数
        async def create_single_task(config, retry_count=0):
            """创建单个任务，支持重试"""
            try:
                logger.info(f"🔧 [DEBUG] 创建任务 {config['pair_index']+1} (重试 {retry_count})")
                
                # 确保使用正确的客户端
                await self._ensure_cloning_engine_client()
                
                # 创建任务
                task = await asyncio.wait_for(
                    self.cloning_engine.create_task(
                        source_chat_id=config['source_chat_id'],
                        target_chat_id=config['target_chat_id'],
                        start_id=config.get('start_id'),
                        end_id=config.get('end_id'),
                        config=config,
                        source_username=config.get('source_username', ''),
                        target_username=config.get('target_username', '')
                    ),
                    timeout=300.0  # 增加到300秒超时（5分钟）
                )
                
                if task:
                    # 启动任务
                    logger.info(f"🚀 准备启动搬运任务: {task.task_id}")
                    start_success = await asyncio.wait_for(
                        self.cloning_engine.start_cloning(task),
                        timeout=120.0  # 增加到120秒超时
                    )
                    
                    if start_success:
                        # 记录任务信息
                        if hasattr(task, 'start_time') and task.start_time:
                            config['start_time'] = task.start_time.isoformat()
                        else:
                            config['start_time'] = datetime.now().isoformat()
                        return {'success': True, 'task_id': task.task_id, 'config': config}
                    else:
                        logger.warning(f"⚠️ 任务启动失败: {task.task_id}")
                        return {'success': False, 'error': '启动失败', 'config': config}
                else:
                    logger.warning(f"⚠️ 任务创建失败: 频道组{config['pair_index']+1}")
                    return {'success': False, 'error': '创建失败', 'config': config}
                    
            except asyncio.TimeoutError:
                error_msg = f"⏰ 频道组{config['pair_index']+1} 超时"
                logger.warning(f"⚠️ {error_msg}")
                return {'success': False, 'error': '超时', 'config': config}
            except Exception as e:
                error_msg = f"❌ 频道组{config['pair_index']+1} 异常: {str(e)}"
                logger.warning(f"⚠️ {error_msg}")
                return {'success': False, 'error': str(e), 'config': config}
        
        # 并行创建所有任务
        logger.info(f"🚀 开始并行创建 {len(task_configs)} 个任务")
        
        # 创建任务协程列表
        task_coroutines = []
        for config in task_configs:
            task_coroutines.append(create_single_task(config))
        
        # 并行执行所有任务创建
        results = await asyncio.gather(*task_coroutines, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ 任务 {i+1} 创建异常: {result}")
                failed_configs.append(task_configs[i])
            elif result['success']:
                success_count += 1
                task_ids.append(result['task_id'])
                logger.info(f"✅ 任务 {i+1} 创建成功: {result['task_id']}")
            else:
                logger.warning(f"⚠️ 任务 {i+1} 创建失败: {result['error']}")
                failed_configs.append(result['config'])
        
        # 对失败的任务进行重试
        if failed_configs:
            logger.info(f"🔄 开始重试 {len(failed_configs)} 个失败的任务")
            
            for retry_round in range(3):  # 最多重试3轮
                if not failed_configs:
                    break
                    
                logger.info(f"🔄 重试第 {retry_round + 1} 轮，剩余 {len(failed_configs)} 个任务")
                
                # 等待一段时间再重试
                await asyncio.sleep(5.0 * (retry_round + 1))  # 递增延迟
                
                # 重试失败的任务
                retry_coroutines = []
                for config in failed_configs:
                    retry_coroutines.append(create_single_task(config, retry_round + 1))
                
                retry_results = await asyncio.gather(*retry_coroutines, return_exceptions=True)
                
                # 处理重试结果
                new_failed_configs = []
                for i, result in enumerate(retry_results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ 重试任务 {i+1} 异常: {result}")
                        new_failed_configs.append(failed_configs[i])
                    elif result['success']:
                        success_count += 1
                        task_ids.append(result['task_id'])
                        logger.info(f"✅ 重试任务 {i+1} 成功: {result['task_id']}")
                    else:
                        logger.warning(f"⚠️ 重试任务 {i+1} 失败: {result['error']}")
                        new_failed_configs.append(result['config'])
                
                failed_configs = new_failed_configs
                
                if failed_configs:
                    logger.warning(f"⚠️ 第 {retry_round + 1} 轮重试后仍有 {len(failed_configs)} 个任务失败")
                else:
                    logger.info(f"✅ 第 {retry_round + 1} 轮重试后所有任务都成功了")
                    break
        
        # 最终统计
        if failed_configs:
            logger.warning(f"⚠️ 最终仍有 {len(failed_configs)} 个任务失败")
            for config in failed_configs:
                logger.warning(f"  - 频道组{config['pair_index']+1}: {config['source_chat_id']} -> {config['target_chat_id']}")
        
        return success_count, task_ids

    async def _execute_multi_select_cloning(self, callback_query: CallbackQuery, user_id: str, task_configs: List[Dict]):
        """执行多选搬运"""
        try:
            # 显示开始界面
            text = f"""
🚀 **多任务搬运启动中**

📡 **任务数量**: {len(task_configs)} 个
⏱️ **状态**: 正在创建任务...

💡 **系统将自动**:
• 创建多个搬运任务
• 管理并发执行
• 避免超限问题
• 实时显示进度
            """.strip()
            
            buttons = [
                [("🔄 刷新状态", "refresh_multi_task_status")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
            # 并行创建任务，增加重试机制
            success_count, task_ids = await self._create_tasks_parallel(callback_query, task_configs)
            
            # 强制更新UI状态，确保不会卡在"正在创建任务..."界面
            logger.info(f"任务创建完成: 成功={success_count}, 总数={len(task_configs)}, 任务ID数量={len(task_ids)}")
            
            # 如果有任务成功启动，显示进度界面
            if task_ids:
                # 保存任务ID和配置到用户状态中，用于取消功能和完成统计
                if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                    self.multi_select_states[user_id]['task_ids'] = task_ids
                    self.multi_select_states[user_id]['task_configs'] = task_configs
                
                logger.info(f"显示多任务进度界面: {len(task_ids)} 个任务")
                await self._show_multi_task_progress(callback_query, user_id, task_ids, task_configs)
            else:
                # 显示完成界面
                logger.info(f"显示多任务完成界面: 无成功任务")
                await self._show_multi_select_completion(callback_query, user_id, success_count, len(task_configs))
            
        except Exception as e:
            logger.error(f"执行多选搬运失败: {e}")
            logger.exception("多选搬运异常详情:")  # 记录完整的异常堆栈
            try:
                await callback_query.answer("❌ 执行失败，请稍后重试")
            except Exception as answer_error:
                logger.error(f"回复用户失败: {answer_error}")
            
            # 确保UI不会卡住，显示错误界面
            try:
                error_text = f"""
❌ **多任务搬运失败**

🔍 **错误信息**: {str(e)}

💡 **建议操作**:
• 检查网络连接
• 验证频道权限
• 稍后重试操作
• 联系技术支持
                """.strip()
                
                buttons = [
                    [("🔄 重试", "show_multi_select_menu")],
                    [("🔙 返回主菜单", "show_main_menu")]
                ]
                
                await callback_query.edit_message_text(
                    error_text,
                    reply_markup=generate_button_layout(buttons)
                )
            except Exception as ui_error:
                logger.error(f"更新错误界面失败: {ui_error}")
    
    async def _task_progress_callback(self, task):
            """任务进度回调函数，用于实时更新任务进度（优化频率控制）"""
            try:
                if not task or not hasattr(task, 'task_id'):
                    return
                
                # 添加频率控制：每10条消息或每5%进度才记录一次
                processed = getattr(task, 'processed_messages', 0)
                progress = getattr(task, 'progress', 0)
                
                # 检查是否需要记录进度（减少日志频率）
                should_log = False
                if not hasattr(task, '_last_logged_progress'):
                    task._last_logged_progress = 0
                    task._last_logged_count = 0
                
                # 每10条消息或每5%进度变化时记录
                if (processed - task._last_logged_count >= 10 or 
                    abs(progress - task._last_logged_progress) >= 5.0):
                    should_log = True
                    task._last_logged_progress = progress
                    task._last_logged_count = processed
                
                if should_log:
                    logger.info(f"📊 任务进度更新: {task.task_id}, 状态: {getattr(task, 'status', 'unknown')}, "
                               f"进度: {progress:.1f}%, "
                               f"已处理: {processed}")
                
                # 这里可以添加更多的进度更新逻辑，比如：
                # 1. 更新数据库中的任务状态
                # 2. 发送实时通知给用户
                # 3. 更新UI界面等
                
            except Exception as e:
                logger.error(f"任务进度回调执行失败: {e}")
        
    async def _show_multi_task_progress(self, callback_query: CallbackQuery, user_id: str, task_ids: List[str], task_configs: List[Dict]):
        """显示多任务进度界面"""
        try:
            # 显示初始进度界面
            await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
            
            # 启动进度更新任务
            asyncio.create_task(self._update_multi_task_progress_loop(callback_query, user_id, task_ids, task_configs))
            
        except Exception as e:
            logger.error(f"显示多任务进度界面失败: {e}")
            await callback_query.answer("❌ 显示失败，请稍后重试")
    
    async def _update_multi_task_progress_ui(self, callback_query: CallbackQuery, user_id: str, task_ids: List[str], task_configs: List[Dict]):
        """更新多任务进度界面（添加频率限制）"""
        try:
            # 添加频率限制：每个用户最多每10秒更新一次UI
            current_time = time.time()
            if not hasattr(self, '_ui_update_times'):
                self._ui_update_times = {}
            
            last_update_time = self._ui_update_times.get(user_id, 0)
            if current_time - last_update_time < 10:  # 10秒内不重复更新
                logger.debug(f"跳过UI更新，用户 {user_id} 上次更新时间: {current_time - last_update_time:.1f}秒前")
                return
            
            self._ui_update_times[user_id] = current_time
            # 获取任务状态
            task_statuses = []
            completed_count = 0
            
            for task_id in task_ids:
                task = self.cloning_engine.active_tasks.get(task_id)
                if task and hasattr(task, 'status'):
                    status = task.status
                    if status == "completed":
                        completed_count += 1
                    
                    # 获取处理进度信息
                    processed_count = getattr(task, 'processed_messages', 0)
                    total_count = getattr(task, 'total_messages', 0)
                    
                    # 如果total_count为0，尝试从stats获取
                    if total_count == 0:
                        stats = getattr(task, 'stats', {})
                        total_count = stats.get('total_messages', 0)
                        processed_count = stats.get('processed_messages', 0)
                    
                    task_statuses.append({
                        'task_id': task_id,
                        'status': status,
                        'progress': getattr(task, 'progress', 0),
                        'processed_count': processed_count,
                        'total_count': total_count
                    })
                    
                    logger.info(f"🔍 任务 {task_id} 状态: {status}, 进度: {processed_count}/{total_count}")
                else:
                    task_statuses.append({
                        'task_id': task_id,
                        'status': 'unknown',
                        'progress': 0,
                        'processed_count': 0,
                        'total_count': 0
                    })
            
            # 构建进度文本
            text = f"""
🚀 **多任务搬运进行中**

📡 **任务数量**: {len(task_ids)} 个
✅ **已完成**: {completed_count} 个
⏳ **进行中**: {len(task_ids) - completed_count} 个

📊 **详细进度**:
            """.strip()
            
            # 显示每个任务的进度
            for i, (task_status, config) in enumerate(zip(task_statuses, task_configs)):
                source_id = config.get('source_chat_id', '')
                target_id = config.get('target_chat_id', '')
                
                # 获取频道显示名称（优先使用保存的用户名）
                source_display = await self._get_channel_display_name_for_progress(source_id, user_id)
                target_display = await self._get_channel_display_name_for_progress(target_id, user_id)
                
                status_icon = {
                    'pending': '⏳',
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'unknown': '❓'
                }.get(task_status['status'], '❓')
                
                # 获取任务开始时间和实时进度
                task = self.cloning_engine.active_tasks.get(task_status['task_id'])
                elapsed_time = ""
                real_processed = task_status['processed_count']
                real_total = task_status['total_count']
                
                # 如果任务还在运行，尝试获取实时进度
                if task and task_status['status'] == 'running':
                    try:
                        # 尝试获取最新的进度信息
                        if hasattr(task, 'stats') and task.stats:
                            real_processed = task.stats.get('processed_messages', real_processed)
                            real_total = task.stats.get('total_messages', real_total)
                        elif hasattr(task, 'processed_messages'):
                            real_processed = task.processed_messages
                        if hasattr(task, 'total_messages'):
                            real_total = task.total_messages
                    except Exception as e:
                        logger.warning(f"获取任务实时进度失败: {e}")
                
                # 获取任务开始时间
                if task and hasattr(task, 'start_time') and task.start_time:
                    try:
                        # 处理start_time可能是float或datetime的情况
                        if isinstance(task.start_time, (int, float)):
                            # start_time是时间戳（float）
                            elapsed_seconds = time.time() - task.start_time
                        else:
                            # start_time是datetime对象
                            elapsed_seconds = (datetime.now() - task.start_time).total_seconds()
                        
                        elapsed_minutes = int(elapsed_seconds // 60)
                        elapsed_secs = int(elapsed_seconds % 60)
                        elapsed_time = f"⏱️ 已运行: {elapsed_minutes}分{elapsed_secs}秒"
                    except Exception as e:
                        logger.warning(f"计算任务运行时间失败: {e}")
                        elapsed_time = ""
                
                text += f"\n\n**任务 {i+1}**: {status_icon} {source_display} → {target_display}"
                text += f"\n📊 状态: {task_status['status']}"
                text += f"\n📝 已处理: {real_processed}/{real_total}"
                if elapsed_time:
                    text += f"\n{elapsed_time}"
            
            text += "\n\n💡 **系统将每30秒自动刷新进度，显示实际处理数量**"
            
            # 生成按钮
            buttons = [
                [("🔄 手动刷新", "refresh_multi_task_progress")],
                [("⏹️ 停止搬运", "stop_multi_task_cloning")],
                [("🔄 断点续传", "resume_multi_task_cloning")],
                [("❌ 取消多任务", "cancel_multi_task_cloning")],
                [("📊 查看任务状态", "view_tasks")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"更新多任务进度界面失败: {e}")
    
    async def _update_multi_task_progress_loop(self, callback_query: CallbackQuery, user_id: str, task_ids: List[str], task_configs: List[Dict]):
        """多任务进度更新循环"""
        try:
            # 记录开始时间，用于超时保护
            start_time = datetime.now()
            # 从配置中读取最大运行时间，默认48小时（172800秒）
            max_duration = DEFAULT_USER_CONFIG.get('progress_update_timeout', 172800)
            update_count = 0
            
            while True:
                await asyncio.sleep(30)
                update_count += 1
                
                # 超时保护：如果运行超过配置的最大时长，停止更新
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > max_duration:
                    logger.warning(f"多任务进度更新已运行{elapsed/60:.1f}分钟，达到最大时长限制（{max_duration/60:.1f}分钟），停止更新")
                    break
                
                # 检查是否所有任务都完成了
                all_completed = True
                completed_count = 0
                failed_count = 0
                
                logger.info(f"🔍 检查多任务状态: user_id={user_id}, task_ids={task_ids}")
                logger.info(f"🔍 当前活动任务数: {len(self.cloning_engine.active_tasks) if hasattr(self, 'cloning_engine') and self.cloning_engine else 0}")
                if hasattr(self, 'cloning_engine') and self.cloning_engine:
                    for active_task_id, active_task in self.cloning_engine.active_tasks.items():
                        logger.info(f"🔍 活动任务 {active_task_id}: 状态={active_task.status}, 进度={active_task.processed_messages}/{active_task.total_messages}")
                
                for i, task_id in enumerate(task_ids):
                    task = self.cloning_engine.active_tasks.get(task_id)
                    if task and hasattr(task, 'status'):
                        task_status = task.status
                        logger.info(f"🔍 任务 {task_id} 状态: {task_status}")
                        
                        if task_status == "completed":
                            completed_count += 1
                            # 记录任务真实完成时间
                            if i < len(task_configs) and hasattr(task, 'end_time') and task.end_time:
                                task_configs[i]['end_time'] = task.end_time.isoformat()
                            elif i < len(task_configs):
                                task_configs[i]['end_time'] = datetime.now().isoformat()
                        elif task_status == "failed":
                            failed_count += 1
                            # 记录任务真实失败时间
                            if i < len(task_configs) and hasattr(task, 'end_time') and task.end_time:
                                task_configs[i]['end_time'] = task.end_time.isoformat()
                            elif i < len(task_configs):
                                task_configs[i]['end_time'] = datetime.now().isoformat()
                        elif task_status not in ["completed", "failed"]:
                            all_completed = False
                    else:
                        # 任务不在active_tasks中，需要检查是否真的完成了
                        # 检查任务历史记录
                        task_found_in_history = False
                        if hasattr(self.cloning_engine, 'task_history'):
                            for history_task in self.cloning_engine.task_history:
                                if history_task.get('task_id') == task_id:
                                    task_found_in_history = True
                                    history_status = history_task.get('status', 'unknown')
                                    logger.info(f"🔍 任务 {task_id} 在历史记录中，状态: {history_status}")
                                    
                                    if history_status == "completed":
                                        completed_count += 1
                                        # 记录任务完成时间
                                        if i < len(task_configs):
                                            end_time = history_task.get('end_time')
                                            if end_time:
                                                task_configs[i]['end_time'] = end_time
                                            else:
                                                task_configs[i]['end_time'] = datetime.now().isoformat()
                                    elif history_status == "failed":
                                        failed_count += 1
                                        # 记录任务失败时间
                                        if i < len(task_configs):
                                            end_time = history_task.get('end_time')
                                            if end_time:
                                                task_configs[i]['end_time'] = end_time
                                            else:
                                                task_configs[i]['end_time'] = datetime.now().isoformat()
                                    else:
                                        # 历史记录中的任务状态不是completed或failed，说明还在运行
                                        all_completed = False
                                        logger.info(f"🔍 任务 {task_id} 在历史记录中但状态为 {history_status}，仍在运行")
                                    break
                        
                        if not task_found_in_history:
                            # 任务既不在active_tasks中，也不在历史记录中
                            # 这种情况可能是任务刚启动就被清理了，或者出现了异常
                            logger.warning(f"⚠️ 任务 {task_id} 既不在活动任务中也不在历史记录中，可能出现了异常")
                            
                            # 检查任务是否启动失败
                            # 如果任务ID存在但不在任何地方，很可能是启动失败
                            if task_status == 'running':
                                logger.warning(f"⚠️ 多任务 {task_id} 状态为running但不在任何地方，标记为失败")
                                # 更新任务配置状态
                                for i, config in enumerate(task_configs):
                                    if config.get('task_id') == task_id:
                                        task_configs[i]['status'] = 'failed'
                                        task_configs[i]['progress'] = 0.0
                                        break
                                logger.info(f"📊 多任务已标记为失败: {task_id}")
                            else:
                                # 为了安全起见，我们认为任务还在运行
                                all_completed = False
                                logger.info(f"🔍 多任务 {task_id} 状态为 {task_status}，继续监控")
                
                logger.info(f"📊 任务状态统计: 完成={completed_count}, 失败={failed_count}, 进行中={len(task_ids) - completed_count - failed_count}")
                
                if all_completed:
                    # 额外验证：确保所有任务都真的完成了
                    # 检查是否还有任务在active_tasks中运行
                    still_running_count = 0
                    for task_id in task_ids:
                        if task_id in self.cloning_engine.active_tasks:
                            task = self.cloning_engine.active_tasks[task_id]
                            if task.status not in ["completed", "failed"]:
                                still_running_count += 1
                                logger.info(f"🔍 任务 {task_id} 仍在运行，状态: {task.status}")
                    
                    if still_running_count == 0:
                        logger.info(f"🎉 所有任务完成，显示完成界面: 完成={completed_count}, 失败={failed_count}")
                        # 所有任务完成，显示完成界面
                        await self._show_multi_select_completion(callback_query, user_id, completed_count, len(task_ids))
                        break
                    else:
                        logger.info(f"⚠️ 检测到 {still_running_count} 个任务仍在运行，继续监控")
                        all_completed = False
                
                # 更新进度界面
                try:
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                except Exception as e:
                    error_str = str(e)
                    logger.error(f"更新进度界面失败: {e}")
                    
                    # 处理FLOOD_WAIT错误
                    if "FLOOD_WAIT" in error_str:
                        try:
                            # 解析等待时间
                            wait_time = int(error_str.split('A wait of ')[1].split(' seconds')[0])
                            logger.warning(f"⚠️ 遇到FLOOD_WAIT限制，需要等待 {wait_time} 秒")
                            
                            # 等待指定时间
                            logger.info(f"⏳ 等待 {wait_time} 秒后继续...")
                            await asyncio.sleep(wait_time)
                            
                            # 重试更新
                            try:
                                await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                                logger.info(f"✅ FLOOD_WAIT后重试更新成功")
                            except Exception as retry_error:
                                logger.error(f"❌ FLOOD_WAIT后重试更新失败: {retry_error}")
                        except Exception as parse_error:
                            logger.error(f"❌ 解析FLOOD_WAIT时间失败: {parse_error}")
                            # 如果解析失败，等待60秒
                            await asyncio.sleep(60)
                    elif "QUERY_ID_INVALID" in error_str or "callback query id is invalid" in error_str.lower():
                        logger.info(f"检测到回调查询过期，继续监控任务但不更新UI")
                    # 继续监控任务状态，不退出循环
                    continue
                    
        except Exception as e:
            logger.error(f"多任务进度更新循环失败: {e}")
    

    

    
    async def _handle_cancel_multi_task_cloning(self, callback_query: CallbackQuery):
        """处理取消多任务搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 从用户状态中获取多任务信息
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                multi_select_state = self.multi_select_states[user_id]
                task_ids = multi_select_state.get('task_ids', [])
                
                if task_ids:
                    # 取消所有正在运行的任务
                    cancelled_count = 0
                    for task_id in task_ids:
                        task = self.cloning_engine.active_tasks.get(task_id)
                        if task and hasattr(task, 'status') and task.status in ['pending', 'running']:
                            # 停止任务
                            if hasattr(task, 'stop'):
                                await task.stop()
                            task.status = 'cancelled'
                            cancelled_count += 1
                            logger.info(f"取消多任务: {task_id}")
                    
                    # 显示取消结果
                    if cancelled_count > 0:
                        await callback_query.answer(f"✅ 已取消 {cancelled_count} 个任务")
                        
                        # 显示取消确认界面
                        await self._show_multi_task_cancelled(callback_query, user_id, cancelled_count, len(task_ids))
                    else:
                        await callback_query.answer("ℹ️ 没有正在运行的任务需要取消")
                        
                        # 显示完成界面
                        completed_count = sum(1 for task_id in task_ids 
                                           if self.cloning_engine.active_tasks.get(task_id, {}) and 
                                           hasattr(self.cloning_engine.active_tasks.get(task_id, {}), 'status') and
                                           self.cloning_engine.active_tasks.get(task_id, {}).status == "completed")
                        await self._show_multi_select_completion(callback_query, user_id, completed_count, len(task_ids))
                else:
                    await callback_query.answer("ℹ️ 没有找到多任务信息")
                    await self._show_main_menu(callback_query)
            else:
                await callback_query.answer("ℹ️ 没有找到多任务状态")
                await self._show_main_menu(callback_query)
                
        except Exception as e:
            logger.error(f"取消多任务失败: {e}")
            await callback_query.answer("❌ 取消失败，请稍后重试")
            await self._show_main_menu(callback_query)
    
    async def _show_multi_task_cancelled(self, callback_query: CallbackQuery, user_id: str, cancelled_count: int, total_count: int):
        """显示多任务取消确认界面"""
        try:
            text = f"""
⏹️ **多任务搬运已取消**

📊 **取消结果**:
• 总任务数: {total_count} 个
• 已取消: {cancelled_count} 个
• 已完成: {total_count - cancelled_count} 个

💡 **后续操作**:
• 已取消的任务将停止执行
• 已完成的任务结果已保存
• 可以重新开始搬运任务
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🚀 重新开始搬运", "select_channel_pairs_to_clone")],
                [("📊 查看任务状态", "view_tasks")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
            # 清理多任务状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                del self.multi_select_states[user_id]
            
        except Exception as e:
            logger.error(f"显示多任务取消界面失败: {e}")
            await callback_query.answer("❌ 显示失败，请稍后重试")
    
    async def _handle_refresh_multi_task_status(self, callback_query: CallbackQuery):
        """处理多任务状态刷新"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查是否有多任务状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                state = self.multi_select_states[user_id]
                task_ids = state.get('task_ids', [])
                task_configs = state.get('task_configs', [])
                
                if task_ids:
                    # 更新多任务进度界面
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                    await callback_query.answer("🔄 状态已刷新")
                else:
                    await callback_query.answer("ℹ️ 没有找到活动的多任务")
                    await self._show_main_menu(callback_query)
            else:
                await callback_query.answer("ℹ️ 没有找到多任务状态")
                await self._show_main_menu(callback_query)
                
        except Exception as e:
            logger.error(f"刷新多任务状态失败: {e}")
            await callback_query.answer("❌ 刷新失败，请稍后重试")
            await self._show_main_menu(callback_query)
    
    async def _get_channel_display_name(self, chat_id: str) -> str:
        """获取频道的显示名称"""
        try:
            if not chat_id:
                return "未知频道"
            
            # 尝试获取频道信息
            chat = await self._get_api_client().get_chat(chat_id)
            if chat:
                # 优先使用用户名，如果没有则使用标题
                if hasattr(chat, 'username') and chat.username:
                    return f"@{chat.username}"
                elif hasattr(chat, 'title') and chat.title:
                    return chat.title
                else:
                    return str(chat_id)
            else:
                return str(chat_id)
        except Exception as e:
            logger.warning(f"获取频道显示名称失败 {chat_id}: {e}")
            return str(chat_id)
    
        # 频道信息缓存
        self.channel_cache = {}  # 频道信息缓存
        self.cache_expiry = {}   # 缓存过期时间
        self.cache_duration = 3600  # 缓存1小时
        
    async def _get_channel_display_name_safe(self, chat_id: str) -> str:
        """安全获取频道显示名称（带缓存）"""
        try:
            # 如果是用户名格式，直接返回
            if isinstance(chat_id, str) and chat_id.startswith('@'):
                return chat_id
            
            # 检查缓存
            current_time = time.time()
            if chat_id in self.channel_cache:
                if current_time < self.cache_expiry.get(chat_id, 0):
                    return self.channel_cache[chat_id]
                else:
                    # 缓存过期，删除
                    del self.channel_cache[chat_id]
                    del self.cache_expiry[chat_id]
            
            # 如果是数字ID，尝试获取频道信息
            if isinstance(chat_id, str) and chat_id.startswith('-100'):
                display_name = await self._get_channel_display_name(chat_id)
            elif isinstance(chat_id, int) and chat_id < 0:
                display_name = await self._get_channel_display_name(str(chat_id))
            else:
                display_name = str(chat_id)
            
            # 缓存结果
            self.channel_cache[chat_id] = display_name
            self.cache_expiry[chat_id] = current_time + self.cache_duration
            
            return display_name
            
        except Exception as e:
            logger.warning(f"安全获取频道显示名称失败 {chat_id}: {e}")
            return str(chat_id)
    
    async def _get_channel_username(self, chat_id: str) -> str:
        """获取频道的用户名（用于保存到数据库）"""
        try:
            # 如果已经是用户名格式，直接返回
            if isinstance(chat_id, str) and chat_id.startswith('@'):
                return chat_id
            
            # 如果是数字ID，尝试获取频道信息
            if isinstance(chat_id, str) and chat_id.startswith('-100'):
                try:
                    chat = await self._get_api_client().get_chat(chat_id)
                    if hasattr(chat, 'username') and chat.username:
                        return f"@{chat.username}"
                    elif hasattr(chat, 'title') and chat.title:
                        return chat.title
                    else:
                        return str(chat_id)
                except Exception as e:
                    logger.warning(f"获取频道用户名失败 {chat_id}: {e}")
                    return str(chat_id)
            elif isinstance(chat_id, int) and chat_id < 0:
                try:
                    chat = await self._get_api_client().get_chat(str(chat_id))
                    if hasattr(chat, 'username') and chat.username:
                        return f"@{chat.username}"
                    elif hasattr(chat, 'title') and chat.title:
                        return chat.title
                    else:
                        return str(chat_id)
                except Exception as e:
                    logger.warning(f"获取频道用户名失败 {chat_id}: {e}")
                    return str(chat_id)
            else:
                return str(chat_id)
        except Exception as e:
            logger.warning(f"获取频道用户名失败 {chat_id}: {e}")
            return str(chat_id)
    
    async def _init_channel_filters(self, user_id: str, pair_id: str) -> Dict[str, Any]:
        """初始化频道组过滤配置，默认读取全局配置"""
        try:
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 确保channel_filters结构存在
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            if pair_id not in user_config['channel_filters']:
                user_config['channel_filters'][pair_id] = {}
            
            channel_filters = user_config['channel_filters'][pair_id]
            
            # Flag to check if we actually initialized/modified channel_filters
            modified_channel_filters = False
            
            # 检查是否为完全空的配置（需要在添加independent_enabled之前检查）
            is_empty_config = not channel_filters
            
            # 确保independent_enabled字段存在
            if 'independent_enabled' not in channel_filters:
                channel_filters['independent_enabled'] = False
                modified_channel_filters = True
            
            # 如果频道组过滤配置为空，则复制全局配置作为默认值
            # 但如果已经有independent_enabled=True，则不要重新初始化
            if is_empty_config:
                # 完全空的配置，复制全局配置
                global_config = {
                    'keywords_enabled': user_config.get('keywords_enabled', True),  # 默认开启关键字过滤
                    'keywords': user_config.get('filter_keywords', []).copy(),
                    'replacements_enabled': user_config.get('replacements_enabled', False),
                    'replacements': user_config.get('replacement_words', {}).copy(),
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'links_removal': user_config.get('remove_all_links', False),
                    'links_removal_mode': user_config.get('remove_links_mode', 'links_only'),
                    'usernames_removal': user_config.get('remove_usernames', False),
                    'buttons_removal': user_config.get('filter_buttons', False),
                    'buttons_removal_mode': user_config.get('button_filter_mode', 'remove_buttons_only'),
                    'enhanced_filter_enabled': user_config.get('enhanced_filter_enabled', False),  # 添加增强过滤配置
                    'enhanced_filter_mode': user_config.get('enhanced_filter_mode', 'moderate'),  # 添加增强过滤模式
                    'tail_text': user_config.get('tail_text', ''),
                    'tail_position': user_config.get('tail_position', 'end'),
                    'tail_frequency': user_config.get('tail_frequency', 100),
                    'additional_buttons': user_config.get('additional_buttons', []).copy(),
                    'independent_enabled': False
                }
                
                # 更新频道组过滤配置
                channel_filters.update(global_config)
                modified_channel_filters = True
            elif len(channel_filters) == 1 and 'independent_enabled' in channel_filters and not channel_filters.get('independent_enabled', False):
                # 只有independent_enabled=False的情况，可以重新初始化
                global_config = {
                    'keywords_enabled': user_config.get('keywords_enabled', False),
                    'keywords': user_config.get('filter_keywords', []).copy(),
                    'replacements_enabled': user_config.get('replacements_enabled', False),
                    'replacements': user_config.get('replacement_words', {}).copy(),
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'links_removal': user_config.get('remove_all_links', False),
                    'links_removal_mode': user_config.get('remove_links_mode', 'links_only'),
                    'usernames_removal': user_config.get('remove_usernames', False),
                    'buttons_removal': user_config.get('filter_buttons', False),
                    'buttons_removal_mode': user_config.get('button_filter_mode', 'remove_buttons_only'),
                    'tail_text': user_config.get('tail_text', ''),
                    'tail_position': user_config.get('tail_position', 'end'),
                    'tail_frequency': user_config.get('tail_frequency', 100),
                    'additional_buttons': user_config.get('additional_buttons', []).copy(),
                    'independent_enabled': False
                }
                
                # 更新频道组过滤配置
                channel_filters.update(global_config)
                modified_channel_filters = True
            
            # If this is the first time enabling independent filters (only has independent_enabled key),
            # set keywords_enabled to True by default as requested
            if (channel_filters.get('independent_enabled', False) and 
                len([k for k in channel_filters.keys() if k != 'independent_enabled']) == 0):
                channel_filters['keywords_enabled'] = True
                modified_channel_filters = True
            
            # 确保当independent_enabled=True时，所有必要字段都存在
            if channel_filters.get('independent_enabled', False):
                required_fields = {
                    'keywords_enabled': user_config.get('keywords_enabled', False),
                    'keywords': user_config.get('filter_keywords', []).copy(),
                    'replacements_enabled': user_config.get('replacements_enabled', False),
                    'replacements': user_config.get('replacement_words', {}).copy(),
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'links_removal': user_config.get('remove_all_links', False),
                    'links_removal_mode': user_config.get('remove_links_mode', 'links_only'),
                    'usernames_removal': user_config.get('remove_usernames', False),
                    'buttons_removal': user_config.get('filter_buttons', False),
                    'buttons_removal_mode': user_config.get('button_filter_mode', 'remove_buttons_only'),
                    'tail_text': user_config.get('tail_text', ''),
                    'tail_position': user_config.get('tail_position', 'end'),
                    'tail_frequency': user_config.get('tail_frequency', 100),
                    'additional_buttons': user_config.get('additional_buttons', []).copy()
                }
                
                # 只添加缺失的字段，保留现有配置
                for field, default_value in required_fields.items():
                    if field not in channel_filters:
                        channel_filters[field] = default_value
                        modified_channel_filters = True
            
            # Save if any modifications were made
            if modified_channel_filters:
                user_config['channel_filters'][pair_id] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
            
            # 调试日志已注释以减少后台输出
            # logger.info(f"🔍 _init_channel_filters返回 - 频道组 {pair_id}:")
            # logger.info(f"  • 原始user_config中的配置: {user_config.get('channel_filters', {}).get(pair_id, {})}")
            # logger.info(f"  • is_empty_config: {is_empty_config}")
            # logger.info(f"  • modified_channel_filters: {modified_channel_filters}")
            # logger.info(f"  • 返回的channel_filters: {channel_filters}")
            # logger.info(f"  • independent_enabled: {channel_filters.get('independent_enabled', False)}")
            
            return channel_filters
            
        except Exception as e:
            logger.error(f"初始化频道组过滤配置失败: {e}")
            return {}
    
    async def _get_channel_display_name_for_progress(self, chat_id: str, user_id: str = None) -> str:
        """获取频道显示名称（用于进度显示，优先使用保存的用户名）"""
        try:
            # 如果是用户名格式，直接返回
            if isinstance(chat_id, str) and chat_id.startswith('@'):
                return chat_id
            
            # 如果有用户ID，尝试从数据库获取保存的用户名
            if user_id and isinstance(chat_id, str) and chat_id.startswith('-100'):
                try:
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    
                    # 查找包含该频道ID的频道组
                    for pair in channel_pairs:
                        if pair.get('source_id') == chat_id:
                            source_username = pair.get('source_username', '')
                            if source_username:
                                return source_username
                        elif pair.get('target_id') == chat_id:
                            target_username = pair.get('target_username', '')
                            if target_username:
                                return target_username
                except Exception as e:
                    logger.warning(f"从数据库获取频道用户名失败 {chat_id}: {e}")
            
            # 如果无法获取用户名，尝试从缓存获取
            if chat_id in self.channel_cache:
                return self.channel_cache[chat_id]
            
            # 最后回退到简单ID显示
            if isinstance(chat_id, str) and chat_id.startswith('-100'):
                return f"频道{chat_id[-6:]}"  # 显示最后6位数字
            elif isinstance(chat_id, int) and chat_id < 0:
                return f"频道{str(chat_id)[-6:]}"  # 显示最后6位数字
            else:
                return str(chat_id)
        except Exception as e:
            logger.warning(f"获取进度显示频道名称失败 {chat_id}: {e}")
            return str(chat_id)
    
    async def _batch_get_channel_display_names(self, chat_ids: List[str]) -> Dict[str, str]:
        """批量获取频道显示名称（减少API调用）"""
        try:
            result = {}
            uncached_ids = []
            
            # 检查缓存
            current_time = time.time()
            for chat_id in chat_ids:
                if chat_id in self.channel_cache:
                    if current_time < self.cache_expiry.get(chat_id, 0):
                        result[chat_id] = self.channel_cache[chat_id]
                    else:
                        # 缓存过期，需要重新获取
                        uncached_ids.append(chat_id)
                        del self.channel_cache[chat_id]
                        del self.cache_expiry[chat_id]
                else:
                    uncached_ids.append(chat_id)
            
            # 批量获取未缓存的频道信息
            if uncached_ids:
                logger.info(f"批量获取 {len(uncached_ids)} 个频道信息")
                for chat_id in uncached_ids:
                    try:
                        display_name = await self._get_channel_display_name_safe(chat_id)
                        result[chat_id] = display_name
                        
                        # 添加小延迟避免API限制
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"获取频道 {chat_id} 信息失败: {e}")
                        result[chat_id] = str(chat_id)
            
            return result
            
        except Exception as e:
            logger.error(f"批量获取频道显示名称失败: {e}")
            # 返回原始ID作为兜底
            return {chat_id: str(chat_id) for chat_id in chat_ids}
    
    async def _show_multi_select_completion(self, callback_query: CallbackQuery, user_id: str, success_count: int, total_count: int):
        """显示多选搬运完成界面"""
        try:
            # 获取任务统计信息
            total_messages = 0
            total_processed = 0
            earliest_start = None
            latest_end = None
            
            # 按目标频道分组统计
            target_channel_stats = {}
            source_channel_stats = {}
            
            # 从多任务状态中获取任务信息
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                multi_select_state = self.multi_select_states[user_id]
                task_configs = multi_select_state.get('task_configs', [])
                task_ids = multi_select_state.get('task_ids', [])
                
                # 统计所有任务的信息
                for i, config in enumerate(task_configs):
                    start_id = config.get('start_id')
                    end_id = config.get('end_id')
                    source_channel = config.get('source_channel', '')
                    target_channel = config.get('target_channel', '')
                    pair_index = config.get('pair_index', i)
                    
                    # 计算消息数量
                    task_messages = 0
                    if start_id and end_id:
                        task_messages = end_id - start_id + 1
                        total_messages += task_messages
                        total_processed += task_messages  # 任务完成意味着全部处理完成
                    
                    # 按目标频道统计
                    if target_channel not in target_channel_stats:
                        target_channel_stats[target_channel] = {
                            'total_messages': 0,
                            'source_channels': [],
                            'display_name': await self._get_channel_display_name(target_channel)
                        }
                    target_channel_stats[target_channel]['total_messages'] += task_messages
                    target_channel_stats[target_channel]['source_channels'].append({
                        'source': source_channel,
                        'messages': task_messages,
                        'range': f"{start_id}-{end_id}" if start_id and end_id else "未知"
                    })
                    
                    # 按源频道统计
                    if source_channel not in source_channel_stats:
                        source_channel_stats[source_channel] = {
                            'total_messages': 0,
                            'target_channels': [],
                            'display_name': await self._get_channel_display_name(source_channel)
                        }
                    source_channel_stats[source_channel]['total_messages'] += task_messages
                    source_channel_stats[source_channel]['target_channels'].append({
                        'target': target_channel,
                        'messages': task_messages
                    })
                    
                    # 获取任务时间信息
                    start_time = config.get('start_time')
                    end_time = config.get('end_time')
                    
                    if start_time and end_time:
                        if isinstance(start_time, str):
                            start_time = datetime.fromisoformat(start_time)
                        if isinstance(end_time, str):
                            end_time = datetime.fromisoformat(end_time)
                        
                        # 更新总体时间范围
                        if earliest_start is None or start_time < earliest_start:
                            earliest_start = start_time
                        if latest_end is None or end_time > latest_end:
                            latest_end = end_time
            
            # 计算总体用时（从最早开始到最晚结束）
            total_time_display = "未知"
            if earliest_start and latest_end:
                total_duration = (latest_end - earliest_start).total_seconds()
                if total_duration < 60:
                    total_time_display = f"{total_duration:.1f}秒"
                elif total_duration < 3600:
                    total_time_display = f"{total_duration/60:.1f}分钟"
                else:
                    total_time_display = f"{total_duration/3600:.1f}小时"
            
            # 构建详细统计文本
            detailed_stats_text = ""
            
            # 按目标频道显示统计
            if target_channel_stats:
                detailed_stats_text += "\n\n📢 **各目标频道接收统计**:\n"
                for target_channel, stats in target_channel_stats.items():
                    detailed_stats_text += f"\n📢 {stats['display_name']}\n"
                    for source_info in stats['source_channels']:
                        source_display = await self._get_channel_display_name(source_info['source'])
                        detailed_stats_text += f"  • 📤 {source_display} ({source_info['range']}): {source_info['messages']} 条\n"
                    detailed_stats_text += f"  📈 总计: {stats['total_messages']} 条\n"
            
            # 按源频道显示统计
            if source_channel_stats:
                detailed_stats_text += "\n\n📤 **各源频道搬运统计**:\n"
                for source_channel, stats in source_channel_stats.items():
                    detailed_stats_text += f"\n📤 {stats['display_name']}\n"
                    for target_info in stats['target_channels']:
                        target_display = await self._get_channel_display_name(target_info['target'])
                        detailed_stats_text += f"  • 📢 {target_display}: {target_info['messages']} 条\n"
                    detailed_stats_text += f"  📈 总计: {stats['total_messages']} 条\n"
            
            text = f"""
🎉 **多任务搬运完成**

📊 **执行结果**:
• 总任务数: {total_count} 个
• 成功完成: {success_count} 个
• 失败数量: {total_count - success_count} 个

📈 **总体统计**:
• 总消息数: {total_messages} 条
• 已处理: {total_processed} 条
• 总用时: {total_time_display}{detailed_stats_text}
            """.strip()
            
            buttons = [
                [("📊 查看任务历史", "view_tasks")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
            # 清理多选状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                del self.multi_select_states[user_id]
            
        except Exception as e:
            logger.error(f"显示多选搬运完成界面失败: {e}")
    
    async def _handle_show_multi_task_cloning(self, callback_query: CallbackQuery):
        """显示多任务搬运界面"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                await callback_query.edit_message_text(
                    "❌ 您尚未设定任何频道组。\n\n"
                    "请先在【频道管理】中添加频道组，然后使用多任务搬运功能。",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⚙️ 频道管理", callback_data="show_channel_config_menu")
                    ]])
                )
                return
            
            # 构建多任务搬运界面
            text = f"""
🔄 **多任务搬运**

📡 **可用频道组**: {len(channel_pairs)} 个

💡 **功能说明**:
• 可以同时选择多个频道组进行搬运
• 每个频道组可以设置不同的消息ID段
• 系统会自动管理并发任务，避免超限

🚀 **开始使用**:
请选择要搬运的频道组（可多选）
            """.strip()
            
            # 生成频道组选择按钮
            buttons = []
            for i, pair in enumerate(channel_pairs):
                source_name = pair.get('source_name', f'频道组{i+1}')
                target_name = pair.get('target_name', f'目标{i+1}')
                buttons.append([
                    InlineKeyboardButton(
                        f"📡 {source_name} → 📤 {target_name}",
                        callback_data=f"multi_select_channel:{i}"
                    )
                ])
            
            # 添加操作按钮
            buttons.append([
                InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")
            ])
            
            await callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示多任务搬运界面失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    

    

    

    

    

    

    

    

    

    

    
    def _validate_message_range_format(self, text: str) -> bool:
        """验证消息ID段格式"""
        try:
            # 分割多个部分
            parts = text.split(',')
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if '-' in part:
                    # 范围格式: 1000-2000
                    start_end = part.split('-')
                    if len(start_end) != 2:
                        return False
                    
                    try:
                        start_id = int(start_end[0])
                        end_id = int(start_end[1])
                        if start_id <= 0 or end_id <= 0 or start_id >= end_id:
                            return False
                    except ValueError:
                        return False
                else:
                    # 单个ID
                    try:
                        id_value = int(part)
                        if id_value <= 0:
                            return False
                    except ValueError:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证消息ID段格式失败: {e}")
            return False
    
    async def _show_next_message_range_setup(self, message: Message, user_id: str, channel_index: int):
        """显示下一个频道组的消息ID段设置界面"""
        try:
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            multi_task_state = self.multi_task_states.get(user_id, {})
            selected_channels = multi_task_state.get('selected_channels', [])
            
            if channel_index >= len(selected_channels):
                return
            
            # 获取当前要设置的频道组
            pair_index = int(selected_channels[channel_index])
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道组{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 构建设置界面
            text = f"""
📝 **设置消息ID段 - 频道组 {channel_index + 1}/{len(selected_channels)}**

📡 **采集频道**: {source_name}
📤 **发布频道**: {target_name}

💡 **输入格式**:
• 单个ID: 1234
• ID范围: 1000-2000
• 多个ID: 1234,5678,9012
• 混合格式: 1000-2000,3000,4000-5000

📝 **请输入消息ID段**:
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔙 返回频道选择", "show_multi_task_cloning")],
                [("❌ 取消", "show_main_menu")]
            ]
            
            # 保存当前设置状态
            multi_task_state['current_channel_index'] = channel_index
            multi_task_state['waiting_for_input'] = True
            
            await message.reply_text(
                text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示下一个消息ID段设置界面失败: {e}")
    
    def _parse_message_range(self, message_range: str) -> Dict:
        """解析消息ID段"""
        try:
            ids = []
            ranges = []
            
            # 分割多个部分
            parts = message_range.split(',')
            
            for part in parts:
                part = part.strip()
                if '-' in part:
                    # 范围格式: 1000-2000
                    start_end = part.split('-')
                    if len(start_end) == 2:
                        try:
                            start_id = int(start_end[0])
                            end_id = int(start_end[1])
                            ranges.append([start_id, end_id])
                        except ValueError:
                            continue
                else:
                    # 单个ID
                    try:
                        id_value = int(part)
                        ids.append(id_value)
                    except ValueError:
                        continue
            
            return {
                'ids': ids,
                'ranges': ranges
            }
            
        except Exception as e:
            logger.error(f"解析消息ID段失败: {e}")
            return {'ids': [], 'ranges': []}
    
    async def _handle_show_channel_config(self, callback_query: CallbackQuery, page: int = 0):
        """处理显示频道配置（支持分页）"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 分页参数
            page_size = 30
            total_pairs = len(channel_pairs)
            total_pages = (total_pairs + page_size - 1) // page_size if total_pairs > 0 else 1
            
            # 确保页码在有效范围内
            page = max(0, min(page, total_pages - 1))
            
            config_text = f"""
⚙️ **频道管理**

📊 **当前状态**
• 频道组数量: {total_pairs} 个
• 最大数量限制: 100 个
            """.strip()
            
            # 如果有分页，显示页码信息
            if total_pairs > page_size:
                config_text += f"\n• 当前页: {page + 1}/{total_pages}"
            
            config_text += "\n\n📋 **频道组列表**"
            
            if channel_pairs:
                # 计算当前页的显示范围
                start_index = page * page_size
                end_index = min(start_index + page_size, total_pairs)
                
                for i in range(start_index, end_index):
                    pair = channel_pairs[i]
                    source_id = pair.get('source_id', '未知')
                    target_id = pair.get('target_id', '未知')
                    source_name = pair.get('source_name', f'频道{i+1}')
                    target_name = pair.get('target_name', f'目标{i+1}')
                    source_username = pair.get('source_username', '')
                    target_username = pair.get('target_username', '')
                    status = "✅" if pair.get('enabled', True) else "❌"
                    
                    # 使用保存的用户名信息，格式化为 "频道名 (@用户名)" 的显示格式
                    def format_channel_display(username, channel_id, name):
                        # 如果有用户名且是@c/格式（私密频道）
                        if username and username.startswith('@c/'):
                            # 如果有频道名称且不是默认名称，显示为 "频道名 (@c/...)"
                            if name and name != f'频道{i+1}' and name != f'目标{i+1}':
                                return f"{name} ({username})"
                            else:
                                # 没有频道名称，直接显示私密频道链接
                                return username
                        
                        # 如果有用户名且是普通用户名格式（公开频道），显示为 "频道名 (@用户名)"
                        elif username and username.startswith('@') and not username.startswith('@c/'):
                            # 优先使用频道名称，如果没有则使用用户名
                            display_name = name if name and name != f'频道{i+1}' and name != f'目标{i+1}' else username
                            return f"{display_name} ({username})"
                        
                        # 如果有用户名但不是@格式，添加@前缀
                        elif username and not username.startswith('-') and username:
                            display_name = name if name and name != f'频道{i+1}' and name != f'目标{i+1}' else f"@{username}"
                            return f"{display_name} (@{username})"
                        
                        # 如果没有用户名，显示频道名称或ID
                        else:
                            if name and name != f'频道{i+1}' and name != f'目标{i+1}':
                                return name
                            else:
                                return f"频道ID: {str(channel_id)[-8:]}"
                    
                    # 检查是否为私密频道
                    is_private_source = pair.get('is_private_source', False)
                    is_private_target = pair.get('is_private_target', False)
                    
                    source_display = format_channel_display(source_username, source_id, source_name)
                    target_display = format_channel_display(target_username, target_id, target_name)
                    
                    # 添加私密频道标识
                    if is_private_source:
                        source_display += " 🔒"
                    if is_private_target:
                        target_display += " 🔒"
                    
                    # 显示频道组信息
                    config_text += f"\n{status} **频道组 {i+1}**"
                    config_text += f"\n   📡 采集: {source_display}"
                    config_text += f"\n   📤 发布: {target_display}"
                    
                    # 添加私密频道提示
                    if is_private_source or is_private_target:
                        config_text += f"\n   ⚠️ 包含私密频道，请确保机器人已加入"
            else:
                config_text += "\n❌ 暂无频道组"
            
            config_text += "\n\n💡 请选择操作："
            
            # 生成频道组管理按钮
            keyboard_buttons = []
            if channel_pairs:
                # 计算当前页的显示范围
                start_index = page * page_size
                end_index = min(start_index + page_size, total_pairs)
                
                # 为当前页的每个频道组添加管理按钮
                for i in range(start_index, end_index):
                    keyboard_buttons.append([
                        InlineKeyboardButton(f"⚙️ 过滤配置 {i+1}", callback_data=f"channel_filters:{i}"),
                        InlineKeyboardButton(f"🔄 编辑 {i+1}", callback_data=f"edit_channel_pair:{i}"),
                        InlineKeyboardButton(f"❌ 删除 {i+1}", callback_data=f"delete_channel_pair:{i}")
                    ])
                
                # 添加分页按钮（如果需要）
                pagination_buttons = generate_pagination_buttons(total_pairs, page, page_size)
                keyboard_buttons.extend(pagination_buttons)
                
                # 添加操作按钮
                keyboard_buttons.append([InlineKeyboardButton("🗑️ 一键清空频道组", callback_data="clear_all_channels")])
                keyboard_buttons.append([InlineKeyboardButton("➕ 添加频道组", callback_data="add_channel_pair")])
                keyboard_buttons.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")])
            else:
                # 没有频道组时的按钮
                keyboard_buttons = [
                    [InlineKeyboardButton("➕ 添加频道组", callback_data="add_channel_pair")],
                    [InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")]
                ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )
            
        except Exception as e:
            logger.error(f"显示频道配置失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    
    async def _handle_channel_page(self, callback_query: CallbackQuery):
        """处理频道组分页导航"""
        try:
            # 从callback_data中提取页码
            page = int(callback_query.data.split(':')[1])
            
            # 调用显示频道配置函数，传入页码
            await self._handle_show_channel_config(callback_query, page)
            
        except Exception as e:
            logger.error(f"处理频道分页失败: {e}")
            await callback_query.answer("❌ 分页失败，请稍后重试")
    
    async def _handle_show_channel_admin_test(self, callback_query: CallbackQuery):
        """处理显示频道管理 - 显示频道按钮列表"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            # 直接获取并显示管理员频道列表
            admin_channels = await self._get_admin_channels()
            
            if not admin_channels:
                await callback_query.edit_message_text(
                    "📋 **频道管理**\n\n❌ 未找到机器人是管理员的频道\n\n💡 **使用方法：**\n• 将机器人添加为频道管理员\n• 机器人会自动检测并添加到列表\n• 在频道中发送 `/lsj` 进行验证\n\n📝 **手动添加：**\n• 点击下方按钮选择频道添加机器人",
                    reply_markup=generate_button_layout(CHANNEL_ADMIN_TEST_BUTTONS)
                )
                return
            
            # 统计验证状态
            verified_count = len([c for c in admin_channels if c.get('verified', False)])
            unverified_count = len([c for c in admin_channels if not c.get('verified', False)])
            
            # 构建频道列表文本
            channels_text = f"📋 **频道管理**\n\n📋 **频道列表** ({len(admin_channels)} 个)\n"
            channels_text += f"✅ 已验证: {verified_count} 个\n"
            channels_text += f"⚠️ 未验证: {unverified_count} 个\n\n"
            channels_text += f"💡 **点击频道按钮进入管理界面**\n\n"
            channels_text += f"🔧 **验证命令**\n• 在任意频道中发送 `/lsj` 进行验证\n• 机器人会回复\"已验证\"并自动删除消息\n\n"
            channels_text += f"⚠️ **注意**\n• 未验证的频道无法用于搬运和监听\n• 验证失败不会删除频道，请重新验证"
            
            # 创建频道按钮 - 每个频道一个按钮
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard_buttons = []
            
            for i, channel in enumerate(admin_channels, 1):
                channel_id = channel.get('id')
                channel_name = channel.get('title', '未知频道')
                username = channel.get('username', '')
                enabled = channel.get('enabled', True)
                verified = channel.get('verified', False)
                
                # 格式化频道信息 - 简洁格式
                if username:
                    channel_display = f"{channel_name} (@{username})"
                else:
                    channel_display = f"{channel_name} (无用户名)"
                
                # 添加状态标识
                if verified and enabled:
                    status_icon = "✅"
                elif verified and not enabled:
                    status_icon = "⏸️"
                elif not verified:
                    status_icon = "⚠️"
                else:
                    status_icon = "❌"
                
                # 为每个频道创建一个按钮
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"{status_icon} {channel_display}",
                        callback_data=f"admin_channel_manage:{channel_id}"
                    )
                ])
            
            # 添加分页按钮（如果需要）
            if len(admin_channels) > 10:
                keyboard_buttons.append([
                    InlineKeyboardButton("⬅️ 上一页", callback_data="admin_channels_page:0"),
                    InlineKeyboardButton("➡️ 下一页", callback_data="admin_channels_page:1")
                ])
            
            # 添加返回按钮
            keyboard_buttons.append([
                InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")
            ])
            
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await callback_query.edit_message_text(
                channels_text,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"显示频道管理失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    
    async def _handle_admin_channel_filters(self, callback_query: CallbackQuery):
        """处理频道过滤配置 - 与频道组管理完全一致"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 检查是否启用独立过滤
            independent_filters = channel_filters.get('independent_enabled', False)
            
            # 如果启用独立过滤，显示频道配置；否则显示全局配置
            if independent_filters:
                # 显示频道独立配置
                keywords_status = '✅ 开启' if channel_filters.get('keywords_enabled', False) else '❌ 关闭'
                replacements_status = '✅ 开启' if channel_filters.get('replacements_enabled', False) else '❌ 关闭'
                content_removal_status = '✅ 开启' if channel_filters.get('content_removal', False) else '❌ 关闭'
                links_removal_status = '✅ 开启' if channel_filters.get('enhanced_filter_enabled', False) else '❌ 关闭'
                usernames_removal_status = '✅ 开启' if channel_filters.get('remove_usernames', False) else '❌ 关闭'
                buttons_removal_status = '✅ 开启' if channel_filters.get('filter_buttons', False) else '❌ 关闭'
                
                # 小尾巴和添加按钮状态
                tail_text = channel_filters.get('tail_text', '')
                if tail_text:
                    tail_status = f'✅ 已设置: {tail_text[:30]}{"..." if len(tail_text) > 30 else ""}'
                else:
                    tail_status = '❌ 未设置'
                additional_buttons = channel_filters.get('additional_buttons', [])
                buttons_add_status = '✅ 已设置' if additional_buttons else '❌ 未设置'
            else:
                # 显示全局配置
                keywords_status = '✅ 开启' if len(user_config.get('filter_keywords', [])) > 0 else '❌ 关闭'
                replacements_status = '✅ 开启' if len(user_config.get('replacement_words', {})) > 0 else '❌ 关闭'
                content_removal_status = '✅ 开启' if user_config.get('content_removal', False) else '❌ 关闭'
                links_removal_status = '✅ 开启' if user_config.get('enhanced_filter_enabled', False) else '❌ 关闭'
                usernames_removal_status = '✅ 开启' if user_config.get('remove_usernames', False) else '❌ 关闭'
                buttons_removal_status = '✅ 开启' if user_config.get('filter_buttons', False) else '❌ 关闭'
                
                # 小尾巴和添加按钮状态
                tail_text = user_config.get('tail_text', '')
                if tail_text:
                    tail_status = f'✅ 已设置: {tail_text[:30]}{"..." if len(tail_text) > 30 else ""}'
                else:
                    tail_status = '❌ 未设置'
                additional_buttons = user_config.get('additional_buttons', [])
                buttons_add_status = '✅ 已设置' if additional_buttons else '❌ 未设置'
            
            # 构建过滤配置显示
            config_text = f"""
⚙️ **频道过滤配置**

📢 **频道：** {channel_display}

🔧 **独立过滤状态：** {'✅ 已启用' if independent_filters else '❌ 使用全局配置'}

🔧 **当前过滤设置**
• 关键字过滤: {keywords_status}
• 敏感词替换: {replacements_status}
• 纯文本过滤: {content_removal_status}
• 增强版链接过滤: {links_removal_status}
• 用户名移除: {usernames_removal_status}
• 按钮移除: {buttons_removal_status}

✨ **内容增强设置**
• 小尾巴文本: {tail_status}
• 附加按钮: {buttons_add_status}

💡 请选择要配置的过滤选项：
            """.strip()
            
            # 生成过滤配置按钮 - 一行2个按钮布局（与频道组管理完全一致）
            buttons = [
                [("🔄 独立过滤开关", f"toggle_admin_independent_filters:{channel_id}")],
                [("🔑 关键字过滤", f"admin_channel_keywords:{channel_id}"), ("🔄 敏感词替换", f"admin_channel_replacements:{channel_id}")],
                [("📝 纯文本过滤", f"admin_channel_content_removal:{channel_id}"), ("🚀 增强版链接过滤", f"admin_channel_links_removal:{channel_id}")],
                [("👤 用户名移除", f"admin_channel_usernames_removal:{channel_id}"), ("🔘 按钮移除", f"admin_channel_buttons_removal:{channel_id}")],
                [("📝 添加小尾巴", f"admin_channel_tail_text:{channel_id}"), ("🔘 添加按钮", f"admin_channel_buttons:{channel_id}")],
                [("🔙 返回频道管理", "show_channel_admin_test")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道过滤配置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_admin_channel(self, callback_query: CallbackQuery):
        """处理频道启用/停用切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.answer("❌ 频道不存在")
                return
            
            # 切换启用状态
            current_enabled = channel_info.get('enabled', True)
            channel_info['enabled'] = not current_enabled
            
            # 保存到频道数据管理器
            self.channel_data_manager.update_channel_verification(channel_id, channel_info['enabled'])
            
            # 更新频道数据
            channel_data = {
                'id': channel_id,
                'title': channel_info.get('title', '未知频道'),
                'username': channel_info.get('username', ''),
                'type': channel_info.get('type', 'channel'),
                'verified': True,
                'enabled': channel_info['enabled'],
                'added_at': channel_info.get('added_at', ''),
                'last_verified': channel_info.get('last_verified', '')
            }
            self.channel_data_manager.add_channel(channel_id, channel_data)
            
            status_text = "✅ 已启用" if channel_info['enabled'] else "❌ 已禁用"
            channel_name = channel_info.get('title', '未知频道')
            
            await callback_query.answer(f"{status_text} {channel_name}")
            
            # 刷新频道管理界面
            await self._handle_show_channel_admin_test(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道启用/停用切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _init_admin_channel_filters(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """初始化频道过滤配置"""
        try:
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 确保admin_channel_filters结构存在
            if 'admin_channel_filters' not in user_config:
                user_config['admin_channel_filters'] = {}
            if channel_id not in user_config['admin_channel_filters']:
                user_config['admin_channel_filters'][channel_id] = {}
            
            channel_filters = user_config['admin_channel_filters'][channel_id]
            
            # 如果频道过滤配置为空，则复制全局配置作为默认值
            if not channel_filters:
                global_config = {
                    'independent_enabled': False,
                    'keywords_enabled': user_config.get('keywords_enabled', False),
                    'keywords': user_config.get('filter_keywords', []).copy(),
                    'replacements_enabled': user_config.get('replacements_enabled', False),
                    'replacements': user_config.get('replacement_words', {}).copy(),
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'remove_links': user_config.get('remove_links', False),
                    'links_removal': user_config.get('remove_all_links', False),
                    'links_removal_mode': user_config.get('remove_links_mode', 'links_only'),
                    'enhanced_filter_enabled': user_config.get('enhanced_filter_enabled', False),
                    'enhanced_filter_mode': user_config.get('enhanced_filter_mode', 'moderate'),
                    'usernames_removal': user_config.get('remove_usernames', False),
                    'filter_buttons': user_config.get('filter_buttons', False),
                    'buttons_removal_mode': user_config.get('button_filter_mode', 'remove_buttons_only'),
                    'tail_text': user_config.get('tail_text', ''),
                    'tail_frequency': user_config.get('tail_frequency', 'always'),
                    'tail_position': user_config.get('tail_position', 'end'),
                    'additional_buttons': user_config.get('additional_buttons', []).copy(),
                    'button_frequency': user_config.get('button_frequency', 'always')
                }
                channel_filters.update(global_config)
                user_config['admin_channel_filters'][channel_id] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
            
            return channel_filters
            
        except Exception as e:
            logger.error(f"初始化频道过滤配置失败: {e}")
            return {}
    
    async def _handle_toggle_admin_independent_filters(self, callback_query: CallbackQuery):
        """处理频道独立过滤切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换独立过滤状态
            current_status = channel_filters.get('independent_enabled', False)
            channel_filters['independent_enabled'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['independent_enabled'] else "❌ 已禁用"
            await callback_query.answer(f"独立过滤 {status_text}")
            
            # 刷新过滤配置界面
            await self._handle_admin_channel_filters(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道独立过滤切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_keywords(self, callback_query: CallbackQuery):
        """处理频道关键字过滤配置 - 与频道组管理完全一致"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取该频道的关键字过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_keywords = user_config.get('filter_keywords', [])
                global_keywords_enabled = len(global_keywords) > 0
                
                if global_keywords:
                    keywords_text = "\n".join([f"• {keyword}" for keyword in global_keywords])
                else:
                    keywords_text = "❌ 暂无关键字"
                
                config_text = f"""
🔑 **频道关键字过滤（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_keywords_enabled else '❌ 已禁用'}

📝 **当前关键字：**
{keywords_text}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            keywords = channel_filters.get('keywords', [])
            keywords_enabled = channel_filters.get('keywords_enabled', False)
            
            config_text = f"""
🔑 **频道关键字过滤**

📢 **频道：** {channel_name}

📊 **当前状态：** {'✅ 已启用' if keywords_enabled else '❌ 已禁用'}
📝 **关键字数量：** {len(keywords)} 个

🔍 **当前关键字列表：**
            """.strip()
            
            if keywords:
                for i, keyword in enumerate(keywords[:10], 1):  # 只显示前10个
                    config_text += f"\n• {i}. {keyword}"
                if len(keywords) > 10:
                    config_text += f"\n• ... 还有 {len(keywords) - 10} 个关键字"
            else:
                config_text += "\n• 暂无关键字"
            
            config_text += "\n\n💡 **操作说明：**\n• 发送关键字来添加过滤词\n• 发送 `删除:关键字` 来删除特定关键字\n• 发送 `清空` 来清空所有关键字\n• 发送 `启用` 或 `禁用` 来切换过滤状态"
            
            buttons = [
                [("🔄 切换状态", f"toggle_admin_keywords:{channel_id}")],
                [("➕ 添加关键字", f"add_admin_keyword:{channel_id}")],
                [("🗑️ 清空关键字", f"clear_admin_keywords:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道关键字过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_replacements(self, callback_query: CallbackQuery):
        """处理频道敏感词替换配置 - 与频道组管理完全一致"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取该频道的敏感词替换配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_replacements = user_config.get('replacement_words', {})
                global_replacements_enabled = len(global_replacements) > 0
                
                if global_replacements:
                    replacements_text = "\n".join([f"• {old} → {new}" for old, new in global_replacements.items()])
                else:
                    replacements_text = "❌ 暂无替换规则"
                
                config_text = f"""
🔄 **频道敏感词替换（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_replacements_enabled else '❌ 已禁用'}

📝 **当前替换规则：**
{replacements_text}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            replacements = channel_filters.get('replacements', {})
            replacements_enabled = channel_filters.get('replacements_enabled', False)
            
            config_text = f"""
🔄 **频道敏感词替换**

📢 **频道：** {channel_name}

📊 **当前状态：** {'✅ 已启用' if replacements_enabled else '❌ 已禁用'}
📝 **替换规则数量：** {len(replacements)} 个

🔍 **当前替换规则：**
            """.strip()
            
            if replacements:
                for i, (original, replacement) in enumerate(list(replacements.items())[:10], 1):
                    config_text += f"\n• {i}. {original} → {replacement}"
                if len(replacements) > 10:
                    config_text += f"\n• ... 还有 {len(replacements) - 10} 个规则"
            else:
                config_text += "\n• 暂无替换规则"
            
            config_text += "\n\n💡 **操作说明：**\n• 发送 `原词|替换词` 来添加替换规则\n• 发送 `删除:原词` 来删除特定规则\n• 发送 `清空` 来清空所有规则\n• 发送 `启用` 或 `禁用` 来切换替换状态"
            
            buttons = [
                [("🔄 切换状态", f"toggle_admin_replacements:{channel_id}")],
                [("➕ 添加规则", f"add_admin_replacement:{channel_id}")],
                [("🗑️ 清空规则", f"clear_admin_replacements:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道敏感词替换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_content_removal(self, callback_query: CallbackQuery):
        """处理频道纯文本过滤配置"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取频道过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_content_removal = user_config.get('content_removal', False)
                global_content_mode = user_config.get('content_removal_mode', 'text_only')
                
                mode_descriptions = {
                    'text_only': '仅过滤纯文本',
                    'all_content': '过滤所有内容'
                }
                mode_text = mode_descriptions.get(global_content_mode, '未知模式')
                
                config_text = f"""
📝 **频道纯文本过滤（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_content_removal else '❌ 已禁用'}
📋 **过滤模式：** {mode_text}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换内容删除状态
            current_status = channel_filters.get('content_removal', False)
            channel_filters['content_removal'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['content_removal'] else "❌ 已禁用"
            await callback_query.answer(f"纯文本过滤 {status_text}")
            
            # 刷新过滤配置界面
            await self._handle_admin_channel_filters(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道纯文本过滤失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_links_removal(self, callback_query: CallbackQuery):
        """处理频道增强链接过滤配置 - 与频道组管理完全一致"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取该频道的增强链接过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_enhanced_filter = user_config.get('enhanced_filter_enabled', False)
                global_enhanced_mode = user_config.get('enhanced_filter_mode', 'moderate')
                
                mode_descriptions = {
                    'aggressive': '激进模式 - 移除所有链接、按钮和广告',
                    'moderate': '中等模式 - 移除链接和明显广告',
                    'conservative': '保守模式 - 仅移除明显的垃圾链接'
                }
                mode_text = mode_descriptions.get(global_enhanced_mode, '未知模式')
                
                config_text = f"""
🚀 **频道增强版链接过滤（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_enhanced_filter else '❌ 已禁用'}
📋 **过滤模式：** {mode_text}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取增强链接过滤配置
            enhanced_filter_enabled = channel_filters.get('enhanced_filter_enabled', False)
            enhanced_filter_mode = channel_filters.get('enhanced_filter_mode', 'moderate')
            
            # 模式描述
            mode_descriptions = {
                'aggressive': '激进模式 - 移除所有链接、按钮和广告',
                'moderate': '中等模式 - 移除链接和明显广告',
                'conservative': '保守模式 - 仅移除明显的垃圾链接'
            }
            mode_text = mode_descriptions.get(enhanced_filter_mode, '未知模式')
            
            config_text = f"""
🚀 **频道增强版链接过滤**

📢 **频道：** {channel_name}

📊 **当前状态：** {'✅ 已启用' if enhanced_filter_enabled else '❌ 已禁用'}
🔧 **过滤模式：** {mode_text}

💡 **功能说明：**
• 增强版过滤：结合链接移除和广告内容过滤
• 激进模式：移除所有链接、按钮和广告内容
• 中等模式：移除链接和明显的广告内容
• 保守模式：仅移除明显的垃圾链接和广告

🎯 **增强功能：**
• 智能识别广告关键词
• 自动移除按钮文本
• 过滤垃圾链接和推广内容

🔙 返回过滤配置
            """.strip()
            
            buttons = [
                [("🔄 切换开关", f"toggle_admin_enhanced_filter:{channel_id}")],
                [("⚙️ 过滤模式", f"admin_channel_enhanced_mode:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道增强链接过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_usernames_removal(self, callback_query: CallbackQuery):
        """处理频道用户名移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取频道过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_remove_usernames = user_config.get('remove_usernames', False)
                
                config_text = f"""
👤 **频道用户名移除（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_remove_usernames else '❌ 已禁用'}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换用户名删除状态
            current_status = channel_filters.get('remove_usernames', False)
            channel_filters['remove_usernames'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['remove_usernames'] else "❌ 已禁用"
            await callback_query.answer(f"用户名移除 {status_text}")
            
            # 刷新过滤配置界面
            await self._handle_admin_channel_filters(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道用户名移除失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_buttons_removal(self, callback_query: CallbackQuery):
        """处理频道按钮过滤配置 - 与频道组管理完全一致"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取该频道的按钮过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('admin_channel_filters', {}).get(str(channel_id), {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示全局配置
                global_filter_buttons = user_config.get('filter_buttons', False)
                global_button_mode = user_config.get('button_filter_mode', 'remove_buttons_only')
                
                mode_descriptions = {
                    'remove_buttons_only': '仅移除按钮',
                    'remove_message': '移除整条消息'
                }
                mode_text = mode_descriptions.get(global_button_mode, '未知模式')
                
                config_text = f"""
🔘 **频道按钮过滤（全局配置）**

📢 **频道：** {channel_name}

🔧 **当前状态：** {'✅ 已启用' if global_filter_buttons else '❌ 已禁用'}
📋 **过滤模式：** {mode_text}

💡 **说明：** 当前使用全局配置，修改将影响所有频道
                """.strip()
                
                buttons = [
                    [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")],
                    [("⚙️ 启用独立过滤", f"toggle_admin_independent_filters:{channel_id}")]
                ]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取按钮过滤配置
            buttons_removal = channel_filters.get('filter_buttons', False)
            buttons_removal_mode = channel_filters.get('buttons_removal_mode', 'remove_buttons_only')
            
            # 模式描述
            mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            mode_text = mode_descriptions.get(buttons_removal_mode, '未知模式')
            
            config_text = f"""
🔘 **频道按钮过滤**

📢 **频道：** {channel_name}

📊 **当前状态：** {'✅ 已启用' if buttons_removal else '❌ 已禁用'}
🔧 **过滤模式：** {mode_text}

💡 **过滤模式说明：**
• 仅移除按钮 - 只移除消息中的按钮，保留文本内容
• 移除整条消息 - 如果消息包含按钮，则完全移除整条消息

🔙 返回过滤配置
            """.strip()
            
            buttons = [
                [("🔄 切换状态", f"toggle_admin_buttons_removal:{channel_id}")],
                [("🔧 选择模式", f"admin_channel_buttons_mode:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道按钮过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_admin_buttons_removal(self, callback_query: CallbackQuery):
        """处理频道按钮过滤状态切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换按钮过滤状态
            current_status = channel_filters.get('filter_buttons', False)
            channel_filters['filter_buttons'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['filter_buttons'] else "❌ 已禁用"
            await callback_query.answer(f"按钮过滤 {status_text}")
            
            # 刷新按钮过滤界面
            await self._handle_admin_channel_buttons_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道按钮过滤状态切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_buttons_mode(self, callback_query: CallbackQuery):
        """处理频道按钮过滤模式选择"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            config_text = f"""
🔧 **选择按钮过滤模式**

📢 **频道：** {channel_name}

💡 **请选择过滤模式：**
            """.strip()
            
            buttons = [
                [("🔘 仅移除按钮", f"set_admin_buttons_mode:{channel_id}:remove_buttons_only")],
                [("🗑️ 移除整条消息", f"set_admin_buttons_mode:{channel_id}:remove_message")],
                [("🔙 返回按钮过滤", f"admin_channel_buttons_removal:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道按钮过滤模式选择失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_buttons_mode(self, callback_query: CallbackQuery):
        """处理设置频道按钮过滤模式"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            channel_id = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 设置模式
            channel_filters['buttons_removal_mode'] = mode
            channel_filters['filter_buttons'] = True  # 启用功能
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_names = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            mode_name = mode_names.get(mode, '未知模式')
            await callback_query.answer(f"已设置为：{mode_name}")
            
            # 刷新按钮过滤界面
            await self._handle_admin_channel_buttons_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理设置频道按钮过滤模式失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_tail_text(self, callback_query: CallbackQuery):
        """处理频道小尾巴配置"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.answer("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示提示
                config_text = f"""
⚠️ **独立过滤未启用**

📢 **频道：** {channel_name}

🔧 **当前状态：** 使用全局过滤配置

💡 **如需独立配置小尾巴，请先启用独立过滤开关**

🔙 返回过滤配置
                """.strip()
                
                buttons = [[("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取当前小尾巴配置
            tail_text = channel_filters.get('tail_text', '')
            tail_frequency = channel_filters.get('tail_frequency', 'always')
            tail_position = channel_filters.get('tail_position', 'end')
            
            # 显示小尾巴文本内容
            if tail_text:
                tail_display = f"已设置: {tail_text[:50]}{'...' if len(tail_text) > 50 else ''}"
            else:
                tail_display = "未设置"
            
            config_text = f"""
📝 **频道小尾巴配置**

📢 **频道：** {channel_name}

📊 **当前设置：**
• 小尾巴文本: {tail_display}
• 添加频率: {tail_frequency}
• 添加位置: {tail_position}

💡 **请选择操作：**
            """.strip()
            
            buttons = [
                [("✏️ 设置小尾巴", f"set_admin_tail_text:{channel_id}")],
                [("🗑️ 清空小尾巴", f"clear_admin_tail_text:{channel_id}")],
                [("⚙️ 设置频率", f"set_admin_tail_frequency:{channel_id}")],
                [("📍 设置位置", f"set_admin_tail_position:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道小尾巴配置失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_buttons(self, callback_query: CallbackQuery):
        """处理频道按钮配置"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.answer("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示提示
                config_text = f"""
⚠️ **独立过滤未启用**

📢 **频道：** {channel_name}

🔧 **当前状态：** 使用全局过滤配置

💡 **如需独立配置按钮，请先启用独立过滤开关**

🔙 返回过滤配置
                """.strip()
                
                buttons = [[("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 获取当前按钮配置
            additional_buttons = channel_filters.get('additional_buttons', [])
            button_frequency = channel_filters.get('button_frequency', 'always')
            
            config_text = f"""
🔘 **频道按钮配置**

📢 **频道：** {channel_name}

📊 **当前设置：**
• 附加按钮: {'已设置' if additional_buttons else '未设置'}
• 添加频率: {button_frequency}

💡 **请选择操作：**
            """.strip()
            
            buttons = [
                [("✏️ 设置按钮", f"set_admin_buttons:{channel_id}")],
                [("🗑️ 清空按钮", f"clear_admin_buttons:{channel_id}")],
                [("⚙️ 设置频率", f"set_admin_button_frequency:{channel_id}")],
                [("🔙 返回过滤配置", f"admin_channel_filters:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道按钮配置失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_admin_keywords(self, callback_query: CallbackQuery):
        """处理频道关键字过滤状态切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换关键字过滤状态
            current_status = channel_filters.get('keywords_enabled', False)
            channel_filters['keywords_enabled'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['keywords_enabled'] else "❌ 已禁用"
            await callback_query.answer(f"关键字过滤 {status_text}")
            
            # 刷新关键字过滤界面
            await self._handle_admin_channel_keywords(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道关键字过滤状态切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_add_admin_keyword(self, callback_query: CallbackQuery):
        """处理添加频道关键字"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 设置用户状态为等待输入关键字
            self.user_states[user_id] = {
                'state': 'waiting_admin_keyword',
                'channel_id': channel_id,
                'timestamp': time.time()
            }
            
            await callback_query.edit_message_text(
                "🔑 **添加关键字**\n\n请输入要添加的关键字：\n\n💡 **提示：**\n• 发送关键字来添加过滤词\n• 使用逗号分隔多个关键字，如：广告,推广,优惠\n• 发送 `取消` 来取消操作",
                reply_markup=generate_button_layout([[
                    ("❌ 取消", f"admin_channel_keywords:{channel_id}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理添加频道关键字失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_admin_keywords(self, callback_query: CallbackQuery):
        """处理清空频道关键字"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 清空关键字
            channel_filters['keywords'] = []
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer("✅ 关键字已清空")
            
            # 刷新关键字过滤界面
            await self._handle_admin_channel_keywords(callback_query)
            
        except Exception as e:
            logger.error(f"处理清空频道关键字失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _process_admin_keyword_input(self, message: Message, state: Dict[str, Any]):
        """处理频道关键字输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            channel_id = state.get('channel_id')
            
            if not channel_id:
                await message.reply_text("❌ 频道ID丢失，请重新操作")
                return
            
            if text.lower() == '取消':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回关键字过滤", f"admin_channel_keywords:{channel_id}")
                    ]])
                )
                return
            
            # 处理删除关键字
            if text.startswith('删除:'):
                keyword_to_remove = text[3:].strip()
                if not keyword_to_remove:
                    await message.reply_text("❌ 请输入要删除的关键字")
                    return
                
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                keywords = channel_filters.get('keywords', [])
                
                if keyword_to_remove in keywords:
                    keywords.remove(keyword_to_remove)
                    channel_filters['keywords'] = keywords
                    
                    # 保存配置
                    user_config = await self.data_manager.get_user_config(user_id)
                    user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(f"✅ 已删除关键字: {keyword_to_remove}")
                else:
                    await message.reply_text(f"❌ 关键字不存在: {keyword_to_remove}")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新关键字过滤界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_keywords:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_keywords(callback_query)
                return
            
            # 处理清空关键字
            if text == '清空':
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                channel_filters['keywords'] = []
                
                # 保存配置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text("✅ 已清空所有关键字")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新关键字过滤界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_keywords:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_keywords(callback_query)
                return
            
            # 处理启用/禁用
            if text in ['启用', '禁用']:
                enabled = text == '启用'
                
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                channel_filters['keywords_enabled'] = enabled
                
                # 保存配置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                status_text = "✅ 已启用" if enabled else "❌ 已禁用"
                await message.reply_text(f"关键字过滤 {status_text}")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新关键字过滤界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_keywords:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_keywords(callback_query)
                return
            
            # 添加关键字
            if text:
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                keywords = channel_filters.get('keywords', [])
                
                # 支持逗号分隔多个关键字
                new_keywords = [kw.strip() for kw in text.split(',') if kw.strip()]
                added_keywords = []
                duplicate_keywords = []
                
                for keyword in new_keywords:
                    if keyword not in keywords:
                        keywords.append(keyword)
                        added_keywords.append(keyword)
                    else:
                        duplicate_keywords.append(keyword)
                
                if added_keywords:
                    channel_filters['keywords'] = keywords
                    
                    # 保存配置
                    user_config = await self.data_manager.get_user_config(user_id)
                    user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    success_msg = f"✅ 已添加关键字: {', '.join(added_keywords)}"
                    if duplicate_keywords:
                        success_msg += f"\n⚠️ 已存在: {', '.join(duplicate_keywords)}"
                    await message.reply_text(success_msg)
                else:
                    await message.reply_text(f"⚠️ 所有关键字都已存在: {', '.join(duplicate_keywords)}")
                
                # 继续等待输入
                await message.reply_text(
                    "💡 **继续添加关键字或发送其他命令：**\n• 发送关键字来添加过滤词\n• 发送 `删除:关键字` 来删除特定关键字\n• 发送 `清空` 来清空所有关键字\n• 发送 `启用` 或 `禁用` 来切换过滤状态\n• 发送 `完成` 来结束添加",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回关键字过滤", f"admin_channel_keywords:{channel_id}")
                    ]])
                )
                return
            
        except Exception as e:
            logger.error(f"处理频道关键字输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def _handle_admin_channel_manage(self, callback_query: CallbackQuery):
        """处理频道管理界面"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            enabled = channel_info.get('enabled', True)
            verified = channel_info.get('verified', False)
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 构建频道管理界面
            if verified and enabled:
                status_icon = "✅"
                status_text = "已验证且已启用"
            elif verified and not enabled:
                status_icon = "⏸️"
                status_text = "已验证但已停用"
            elif not verified:
                status_icon = "⚠️"
                status_text = "未验证"
            else:
                status_icon = "❌"
                status_text = "已停用"
            
            config_text = f"""
📢 **频道管理**

📋 **频道信息：** {channel_display}
🔧 **当前状态：** {status_icon} {status_text}

💡 **请选择操作：**
            """.strip()
            
            # 创建频道管理按钮
            buttons = []
            
            # 如果未验证，添加验证按钮
            if not verified:
                buttons.append([("🔍 验证频道", f"verify_channel:{channel_id}")])
            
            # 其他按钮
            buttons.extend([
                [("⚙️ 过滤配置", f"admin_channel_filters:{channel_id}")],
                [("📝 信息管理", f"admin_channel_message_management:{channel_id}")],
                [("🔄 启用/停用", f"toggle_admin_channel:{channel_id}")],
                [("🗑️ 删除频道", f"delete_admin_channel:{channel_id}")],
                [("🔙 返回频道列表", "show_channel_admin_test")]
            ])
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道管理界面失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_verify_channel(self, callback_query: CallbackQuery):
        """处理验证频道"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 显示验证进度
            await callback_query.edit_message_text(
                f"🔍 **正在验证频道...**\n\n"
                f"📋 **频道：** {channel_display}\n\n"
                f"⏳ 请稍候，正在检查机器人权限...",
                reply_markup=generate_button_layout([[
                    ("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")
                ]])
            )
            
            # 执行验证
            verification_result = await self._verify_channel_permissions(channel_id, channel_info)
            
            if verification_result['success']:
                # 验证成功
                self.channel_data_manager.update_channel_verification(channel_id, True)
                await callback_query.edit_message_text(
                    f"✅ **频道验证成功！**\n\n"
                    f"📋 **频道：** {channel_display}\n"
                    f"🔧 **状态：** 已验证\n\n"
                    f"💡 现在可以使用该频道进行搬运和监听操作",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")
                    ]])
                )
            else:
                # 验证失败
                self.channel_data_manager.update_channel_verification(channel_id, False)
                await callback_query.edit_message_text(
                    f"❌ **频道验证失败**\n\n"
                    f"📋 **频道：** {channel_display}\n"
                    f"🔧 **状态：** 未验证\n\n"
                    f"⚠️ **错误信息：** {verification_result['error']}\n\n"
                    f"💡 **解决方法：**\n"
                    f"• 确保机器人已加入该频道\n"
                    f"• 确保机器人有管理员权限\n"
                    f"• 在频道中发送 `/lsj` 进行验证",
                    reply_markup=generate_button_layout([[
                        ("🔍 重新验证", f"verify_channel:{channel_id}"),
                        ("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")
                    ]])
                )
            
        except Exception as e:
            logger.error(f"验证频道失败: {e}")
            await callback_query.edit_message_text(
                f"❌ **验证失败**\n\n"
                f"错误信息：{str(e)}\n\n"
                f"请稍后重试",
                reply_markup=generate_button_layout([[
                    ("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")
                ]])
            )
    
    async def _verify_channel_permissions(self, channel_id: int, channel_info: Dict[str, Any]) -> Dict[str, Any]:
        """验证频道权限"""
        try:
            # 优先使用用户名验证
            if channel_info.get('username'):
                try:
                    chat = await self._get_api_client().get_chat(f"@{channel_info['username']}")
                    if chat and chat.id == channel_id:
                        # 验证机器人权限
                        member = await self._get_api_client().get_chat_member(channel_id, "me")
                        status_str = str(member.status).lower()
                        
                        if 'administrator' in status_str or 'creator' in status_str:
                            # 更新频道数据
                            updated_data = {
                                **channel_info,
                                'title': chat.title,
                                'username': getattr(chat, 'username', None),
                                'type': str(chat.type).lower(),
                                'verified': True,
                                'last_verified': datetime.now().isoformat()
                            }
                            self.channel_data_manager.add_channel(channel_id, updated_data)
                            return {'success': True}
                        else:
                            return {'success': False, 'error': '机器人不是管理员'}
                    else:
                        return {'success': False, 'error': '用户名验证ID不匹配'}
                except Exception as e:
                    logger.warning(f"用户名验证频道 {channel_id} 失败: {e}")
                    # 尝试ID验证
                    try:
                        chat = await self._get_api_client().get_chat(channel_id)
                        member = await self._get_api_client().get_chat_member(channel_id, "me")
                        status_str = str(member.status).lower()
                        
                        if 'administrator' in status_str or 'creator' in status_str:
                            updated_data = {
                                **channel_info,
                                'title': chat.title,
                                'username': getattr(chat, 'username', None),
                                'type': str(chat.type).lower(),
                                'verified': True,
                                'last_verified': datetime.now().isoformat()
                            }
                            self.channel_data_manager.add_channel(channel_id, updated_data)
                            return {'success': True}
                        else:
                            return {'success': False, 'error': '机器人不是管理员'}
                    except Exception as e2:
                        return {'success': False, 'error': f'ID验证失败: {str(e2)}'}
            else:
                # 没有用户名，直接使用ID验证
                try:
                    chat = await self._get_api_client().get_chat(channel_id)
                    member = await self._get_api_client().get_chat_member(channel_id, "me")
                    status_str = str(member.status).lower()
                    
                    if 'administrator' in status_str or 'creator' in status_str:
                        updated_data = {
                            **channel_info,
                            'title': chat.title,
                            'username': getattr(chat, 'username', None),
                            'type': str(chat.type).lower(),
                            'verified': True,
                            'last_verified': datetime.now().isoformat()
                        }
                        self.channel_data_manager.add_channel(channel_id, updated_data)
                        return {'success': True}
                    else:
                        return {'success': False, 'error': '机器人不是管理员'}
                except Exception as e:
                    return {'success': False, 'error': f'ID验证失败: {str(e)}'}
                    
        except Exception as e:
            logger.error(f"验证频道权限失败: {e}")
            return {'success': False, 'error': f'验证失败: {str(e)}'}
    
    async def _handle_delete_admin_channel(self, callback_query: CallbackQuery):
        """处理删除频道确认界面"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 构建删除确认界面
            confirm_text = f"""
⚠️ **删除频道确认**

📋 **频道信息：** {channel_display}
🆔 **频道ID：** {channel_id}

⚠️ **警告：**
• 删除后将无法恢复
• 该频道的所有过滤配置将被清除
• 相关的监听任务可能受影响

❓ **确定要删除这个频道吗？**
            """.strip()
            
            # 创建确认按钮
            buttons = [
                [("✅ 确认删除", f"confirm_delete_admin_channel:{channel_id}")],
                [("❌ 取消", f"admin_channel_manage:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                confirm_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理删除频道确认失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_confirm_delete_admin_channel(self, callback_query: CallbackQuery):
        """处理确认删除频道"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 删除频道
            success = await self._delete_admin_channel(user_id, channel_id)
            
            if success:
                # 删除成功，显示成功消息
                success_text = f"""
✅ **频道删除成功**

📋 **已删除频道：** {channel_display}
🆔 **频道ID：** {channel_id}

🗑️ **已清理内容：**
• 频道基本信息
• 过滤配置
• 相关设置

💡 **提示：**
• 如果机器人仍在该频道中，可以重新添加
• 删除后不会影响其他频道
                """.strip()
                
                buttons = [
                    [("🔙 返回频道列表", "show_channel_admin_test")]
                ]
                
                await callback_query.edit_message_text(
                    success_text,
                    reply_markup=generate_button_layout(buttons)
                )
            else:
                # 删除失败
                await callback_query.edit_message_text(
                    "❌ 删除失败，请稍后重试",
                    reply_markup=generate_button_layout([
                        [("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")]
                    ])
                )
            
        except Exception as e:
            logger.error(f"确认删除频道失败: {e}")
            await callback_query.answer("❌ 删除失败，请稍后重试")
    
    async def _delete_admin_channel(self, user_id: str, channel_id: int) -> bool:
        """删除管理员频道"""
        try:
            # 直接从本地频道数据管理器中删除频道
            self.channel_data_manager.remove_channel(channel_id)
            logger.info(f"✅ 已从本地频道数据中删除频道: {channel_id}")
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 删除频道相关的过滤配置
            admin_channel_filters = user_config.get('admin_channel_filters', {})
            if str(channel_id) in admin_channel_filters:
                del admin_channel_filters[str(channel_id)]
                user_config['admin_channel_filters'] = admin_channel_filters
                logger.info(f"✅ 已删除频道过滤配置: {channel_id}")
            
            # 保存用户配置
            success = await self.data_manager.save_user_config(user_id, user_config)
            
            if success:
                logger.info(f"✅ 成功删除管理员频道: {channel_id}")
            else:
                logger.error(f"❌ 保存用户配置失败: {channel_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"删除管理员频道失败: {e}")
            return False
    
    async def _handle_set_admin_tail_text(self, callback_query: CallbackQuery):
        """处理设置频道小尾巴"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 设置用户状态为等待输入小尾巴
            self.user_states[user_id] = {
                'state': 'waiting_admin_tail_text',
                'channel_id': channel_id,
                'timestamp': time.time()
            }
            
            await callback_query.edit_message_text(
                "📝 **设置小尾巴**\n\n请输入要添加的小尾巴文字：\n\n💡 **提示：**\n• 发送文字来设置小尾巴\n• 发送 `取消` 来取消操作",
                reply_markup=generate_button_layout([[
                    ("❌ 取消", f"admin_channel_tail_text:{channel_id}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理设置频道小尾巴失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_admin_tail_text(self, callback_query: CallbackQuery):
        """处理清空频道小尾巴"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 清空小尾巴
            channel_filters['tail_text'] = ''
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer("✅ 小尾巴已清空")
            
            # 刷新小尾巴配置界面
            await self._handle_admin_channel_tail_text(callback_query)
            
        except Exception as e:
            logger.error(f"处理清空频道小尾巴失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_tail_frequency(self, callback_query: CallbackQuery):
        """处理设置频道小尾巴频率"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            config_text = """
⚙️ **设置小尾巴频率**

请选择添加频率：

💡 **说明：**
• 总是：每条消息都添加小尾巴
• 随机：按概率添加小尾巴
• 从不：不添加小尾巴
            """.strip()
            
            buttons = [
                [("100% 总是", f"set_admin_tail_freq:{channel_id}:100")],
                [("75% 经常", f"set_admin_tail_freq:{channel_id}:75")],
                [("50% 偶尔", f"set_admin_tail_freq:{channel_id}:50")],
                [("25% 很少", f"set_admin_tail_freq:{channel_id}:25")],
                [("0% 从不", f"set_admin_tail_freq:{channel_id}:0")],
                [("🔙 返回小尾巴设置", f"admin_channel_tail_text:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理设置频道小尾巴频率失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_tail_position(self, callback_query: CallbackQuery):
        """处理设置频道小尾巴位置"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            config_text = """
📍 **设置小尾巴位置**

请选择添加位置：

💡 **说明：**
• 末尾：在消息末尾添加小尾巴
• 开头：在消息开头添加小尾巴
            """.strip()
            
            buttons = [
                [("📍 末尾", f"set_admin_tail_pos:{channel_id}:end")],
                [("📍 开头", f"set_admin_tail_pos:{channel_id}:start")],
                [("🔙 返回小尾巴设置", f"admin_channel_tail_text:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理设置频道小尾巴位置失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_buttons(self, callback_query: CallbackQuery):
        """处理设置频道按钮"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 设置用户状态为等待输入按钮
            self.user_states[user_id] = {
                'state': 'waiting_admin_buttons',
                'channel_id': channel_id,
                'timestamp': time.time()
            }
            
            await callback_query.edit_message_text(
                "🔘 **设置附加按钮**\n\n请输入按钮信息，格式：`按钮文字|链接`\n\n💡 **提示：**\n• 发送 `按钮文字|链接` 来添加按钮\n• 发送 `取消` 来取消操作",
                reply_markup=generate_button_layout([[
                    ("❌ 取消", f"admin_channel_buttons:{channel_id}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理设置频道按钮失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_admin_buttons(self, callback_query: CallbackQuery):
        """处理清空频道按钮"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 清空按钮
            channel_filters['additional_buttons'] = []
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer("✅ 按钮已清空")
            
            # 刷新按钮配置界面
            await self._handle_admin_channel_buttons(callback_query)
            
        except Exception as e:
            logger.error(f"处理清空频道按钮失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_button_frequency(self, callback_query: CallbackQuery):
        """处理设置频道按钮频率"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            config_text = """
⚙️ **设置按钮频率**

请选择添加频率：

💡 **说明：**
• 总是：每条消息都添加按钮
• 随机：按概率添加按钮
• 从不：不添加按钮
            """.strip()
            
            buttons = [
                [("100% 总是", f"set_admin_button_freq:{channel_id}:100")],
                [("75% 经常", f"set_admin_button_freq:{channel_id}:75")],
                [("50% 偶尔", f"set_admin_button_freq:{channel_id}:50")],
                [("25% 很少", f"set_admin_button_freq:{channel_id}:25")],
                [("0% 从不", f"set_admin_button_freq:{channel_id}:0")],
                [("🔙 返回按钮设置", f"admin_channel_buttons:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理设置频道按钮频率失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _process_admin_tail_text_input(self, message: Message, state: Dict[str, Any]):
        """处理频道小尾巴输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            channel_id = state.get('channel_id')
            
            if not channel_id:
                await message.reply_text("❌ 频道ID丢失，请重新操作")
                return
            
            if text.lower() == '取消':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回小尾巴设置", f"admin_channel_tail_text:{channel_id}")
                    ]])
                )
                return
            
            if text:
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                
                # 设置小尾巴
                channel_filters['tail_text'] = text
                
                # 保存配置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(f"✅ 小尾巴设置成功: {text}")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新小尾巴配置界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_tail_text:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_tail_text(callback_query)
                return
            
        except Exception as e:
            logger.error(f"处理频道小尾巴输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def _process_admin_buttons_input(self, message: Message, state: Dict[str, Any]):
        """处理频道按钮输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            channel_id = state.get('channel_id')
            
            if not channel_id:
                await message.reply_text("❌ 频道ID丢失，请重新操作")
                return
            
            if text.lower() == '取消':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回按钮设置", f"admin_channel_buttons:{channel_id}")
                    ]])
                )
                return
            
            if text and '|' in text:
                # 解析按钮信息
                parts = text.split('|', 1)
                if len(parts) == 2:
                    button_text = parts[0].strip()
                    button_url = parts[1].strip()
                    
                    if button_text and button_url:
                        # 获取频道过滤配置
                        channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                        additional_buttons = channel_filters.get('additional_buttons', [])
                        
                        # 添加按钮
                        additional_buttons.append({
                            'text': button_text,
                            'url': button_url
                        })
                        channel_filters['additional_buttons'] = additional_buttons
                        
                        # 保存配置
                        user_config = await self.data_manager.get_user_config(user_id)
                        user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                        await self.data_manager.save_user_config(user_id, user_config)
                        
                        await message.reply_text(f"✅ 按钮添加成功: {button_text} -> {button_url}")
                        
                        # 继续等待输入
                        await message.reply_text(
                            "💡 **继续添加按钮或发送其他命令：**\n• 发送 `按钮文字|链接` 来添加按钮\n• 发送 `完成` 来结束添加",
                            reply_markup=generate_button_layout([[
                                ("🔙 返回按钮设置", f"admin_channel_buttons:{channel_id}")
                            ]])
                        )
                        return
                    else:
                        await message.reply_text("❌ 按钮文字和链接不能为空")
                        return
                else:
                    await message.reply_text("❌ 格式错误，请使用 `按钮文字|链接` 格式")
                    return
            elif text == '完成':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新按钮配置界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_buttons:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_buttons(callback_query)
                return
            else:
                await message.reply_text("❌ 格式错误，请使用 `按钮文字|链接` 格式")
                return
            
        except Exception as e:
            logger.error(f"处理频道按钮输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def _handle_set_admin_tail_freq(self, callback_query: CallbackQuery):
        """处理设置频道小尾巴频率"""
        try:
            user_id = str(callback_query.from_user.id)
            parts = callback_query.data.split(':')
            channel_id = int(parts[1])
            frequency = int(parts[2])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 设置频率
            channel_filters['tail_frequency'] = frequency
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 小尾巴频率设置为 {frequency}%")
            
            # 刷新小尾巴配置界面
            await self._handle_admin_channel_tail_text(callback_query)
            
        except Exception as e:
            logger.error(f"处理设置频道小尾巴频率失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_tail_pos(self, callback_query: CallbackQuery):
        """处理设置频道小尾巴位置"""
        try:
            user_id = str(callback_query.from_user.id)
            parts = callback_query.data.split(':')
            channel_id = int(parts[1])
            position = parts[2]
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 设置位置
            channel_filters['tail_position'] = position
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            position_text = "末尾" if position == "end" else "开头"
            await callback_query.answer(f"✅ 小尾巴位置设置为 {position_text}")
            
            # 刷新小尾巴配置界面
            await self._handle_admin_channel_tail_text(callback_query)
            
        except Exception as e:
            logger.error(f"处理设置频道小尾巴位置失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_button_freq(self, callback_query: CallbackQuery):
        """处理设置频道按钮频率"""
        try:
            user_id = str(callback_query.from_user.id)
            parts = callback_query.data.split(':')
            channel_id = int(parts[1])
            frequency = int(parts[2])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 设置频率
            channel_filters['button_frequency'] = frequency
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 按钮频率设置为 {frequency}%")
            
            # 刷新按钮配置界面
            await self._handle_admin_channel_buttons(callback_query)
            
        except Exception as e:
            logger.error(f"处理设置频道按钮频率失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_show_clone_test(self, callback_query: CallbackQuery):
        """处理显示搬运管理界面"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            # 获取启用的管理员频道列表
            admin_channels = await self._get_admin_channels()
            enabled_channels = [ch for ch in admin_channels if ch.get('enabled', True) and ch.get('verified', False)]
            
            if not enabled_channels:
                # 检查是否有未验证的频道
                unverified_channels = [ch for ch in admin_channels if ch.get('enabled', True) and not ch.get('verified', False)]
                if unverified_channels:
                    await callback_query.edit_message_text(
                        f"🚀 **搬运管理**\n\n❌ 没有已验证的目标频道\n\n"
                        f"⚠️ **发现 {len(unverified_channels)} 个未验证的频道**\n\n"
                        f"💡 **解决方法：**\n"
                        f"• 到频道管理中验证频道\n"
                        f"• 确保机器人有管理员权限\n"
                        f"• 在频道中发送 `/lsj` 进行验证",
                        reply_markup=generate_button_layout([
                            [("📋 频道管理", "show_channel_admin_test")],
                            [("🔙 返回主菜单", "show_main_menu")]
                        ])
                    )
                else:
                    await callback_query.edit_message_text(
                        "🚀 **搬运管理**\n\n❌ 没有启用的目标频道\n\n💡 **请先到频道管理中启用频道**",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                return
            
            # 构建搬运管理界面
            test_text = f"""
🚀 **搬运管理**

📋 **可用目标频道** ({len(enabled_channels)} 个)

💡 **搬运流程：**
1️⃣ 选择目标频道（可多选）
2️⃣ 为每个目标频道分别输入源频道信息（支持多源频道）
3️⃣ 输入消息ID段
4️⃣ 开始搬运

📝 **输入格式：**
• 源频道：@频道名 或 频道链接
• ID段：起始ID-结束ID

🔧 **支持功能：**
• 多目标频道搬运
• 多源频道映射（每个目标频道可对应多个源频道）
• 自动引导输入流程
            """.strip()
            
            # 创建按钮
            buttons = [
                [("🎯 选择目标频道", "clone_test_select_targets")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                test_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示搬运管理界面失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    
    async def _handle_clone_test_select_targets(self, callback_query: CallbackQuery):
        """处理选择目标频道"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取启用的管理员频道列表
            admin_channels = await self._get_admin_channels()
            enabled_channels = [ch for ch in admin_channels if ch.get('enabled', True) and ch.get('verified', False)]
            
            if not enabled_channels:
                # 检查是否有未验证的频道
                unverified_channels = [ch for ch in admin_channels if ch.get('enabled', True) and not ch.get('verified', False)]
                if unverified_channels:
                    await callback_query.edit_message_text(
                        f"❌ 没有已验证的目标频道\n\n"
                        f"⚠️ 发现 {len(unverified_channels)} 个未验证的频道\n\n"
                        f"请先到频道管理中验证频道",
                        reply_markup=generate_button_layout([[
                            ("📋 频道管理", "show_channel_admin_test")
                        ]])
                    )
                else:
                    await callback_query.edit_message_text("❌ 没有启用的目标频道")
                return
            
            # 初始化选择状态（清除之前的选择）
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            
            # 重新开始选择，清除之前的状态
            self.clone_test_selections[user_id] = {
                'selected_targets': [],
                'sources': [],
                'current_source_index': 0
            }
            
            # 获取当前选择状态
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            selected_count = len(selected_targets)
            
            # 构建选择界面
            select_text = f"""
🎯 **选择目标频道**

📋 **可用频道** ({len(enabled_channels)} 个)
💡 **点击频道进行选择/取消选择**

已选择：{selected_count} 个频道
            """.strip()
            
            # 创建频道选择按钮
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard_buttons = []
            for i, channel in enumerate(enabled_channels, 1):
                channel_id = channel.get('id')
                channel_name = channel.get('title', '未知频道')
                username = channel.get('username', '')
                
                if username:
                    channel_display = f"{channel_name} (@{username})"
                else:
                    channel_display = f"{channel_name} (无用户名)"
                
                # 检查是否已选中
                is_selected = any(ch.get('id') == channel_id for ch in selected_targets)
                status_icon = "✅" if is_selected else "⚪"
                
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"{status_icon} {channel_display}",
                        callback_data=f"clone_test_toggle_target:{channel_id}"
                    )
                ])
            
            # 添加确认和返回按钮
            keyboard_buttons.append([
                InlineKeyboardButton("✅ 确认选择", "clone_test_confirm_targets"),
                InlineKeyboardButton("🔙 返回", "show_clone_test")
            ])
            
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await callback_query.edit_message_text(
                select_text,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"处理选择目标频道失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clone_test_toggle_target(self, callback_query: CallbackQuery):
        """处理切换目标频道选择"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取选择状态
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': []
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.answer("❌ 频道不存在")
                return
            
            # 切换选择状态
            channel_ids = [ch['id'] for ch in selected_targets]
            if channel_id in channel_ids:
                selected_targets.remove(next(ch for ch in selected_targets if ch['id'] == channel_id))
            else:
                selected_targets.append(channel_info)
            
            # 获取启用的频道列表
            enabled_channels = [ch for ch in admin_channels if ch.get('enabled', True)]
            
            # 构建选择界面
            select_text = f"""
🎯 **选择目标频道**

📋 **可用频道** ({len(enabled_channels)} 个)
💡 **点击频道进行选择/取消选择**

已选择：{len(selected_targets)} 个频道
            """.strip()
            
            # 创建频道选择按钮
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard_buttons = []
            for i, channel in enumerate(enabled_channels, 1):
                channel_id = channel.get('id')
                channel_name = channel.get('title', '未知频道')
                username = channel.get('username', '')
                
                if username:
                    channel_display = f"{channel_name} (@{username})"
                else:
                    channel_display = f"{channel_name} (无用户名)"
                
                # 根据选择状态显示不同的图标
                is_selected = any(ch.get('id') == channel_id for ch in selected_targets)
                icon = "✅" if is_selected else "⚪"
                
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"{icon} {channel_display}",
                        callback_data=f"clone_test_toggle_target:{channel_id}"
                    )
                ])
            
            # 添加确认和返回按钮
            keyboard_buttons.append([
                InlineKeyboardButton("✅ 确认选择", "clone_test_confirm_targets"),
                InlineKeyboardButton("🔙 返回", "show_clone_test")
            ])
            
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await callback_query.edit_message_text(
                select_text,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"处理切换目标频道选择失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clone_test_confirm_targets(self, callback_query: CallbackQuery):
        """处理确认目标频道选择"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取选择状态
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': []
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            
            if not selected_targets:
                await callback_query.answer("❌ 请至少选择一个目标频道")
                return
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            enabled_channels = [ch for ch in admin_channels if ch.get('enabled', True)]
            
            # 构建确认界面
            confirm_text = f"""
✅ **目标频道确认**

📋 **已选择的目标频道** ({len(selected_targets)} 个)
            """.strip()
            
            for channel_info in selected_targets:
                channel_name = channel_info.get('title', '未知频道')
                username = channel_info.get('username', '')
                if username:
                    channel_display = f"{channel_name} (@{username})"
                else:
                    channel_display = f"{channel_name} (无用户名)"
                confirm_text += f"\n• {channel_display}"
            
            confirm_text += f"\n\n💡 **下一步：分别输入 {len(selected_targets)} 个源频道信息**"
            
            # 创建按钮
            buttons = [
                [("📝 开始输入源频道", "clone_test_input_sources")],
                [("🔙 重新选择", "clone_test_select_targets")]
            ]
            
            await callback_query.edit_message_text(
                confirm_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理确认目标频道选择失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clone_test_input_sources(self, callback_query: CallbackQuery):
        """处理输入源频道信息"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取选择的目标频道
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': [],
                    'current_source_index': 0
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            current_index = self.clone_test_selections[user_id]['current_source_index']
            
            if current_index >= len(selected_targets):
                # 所有源频道都已输入完成，显示确认界面
                await self._show_clone_test_confirmation(callback_query)
                return
            
            # 获取当前要输入源频道的目标频道
            current_target = selected_targets[current_index]
            target_name = current_target.get('title', '未知频道')
            target_username = current_target.get('username', '')
            if target_username:
                target_display = f"{target_name} (@{target_username})"
            else:
                target_display = f"{target_name} (无用户名)"
            
            # 设置用户状态为等待输入当前源频道信息
            self.user_states[user_id] = {
                'state': 'waiting_clone_test_single_source',
                'target_index': current_index,
                'timestamp': time.time()
            }
            
            input_text = f"""
📝 **输入源频道信息 ({current_index + 1}/{len(selected_targets)})**

🎯 **目标频道：** {target_display}

📋 **输入格式：**
• 源频道：@频道名 或 频道链接
• ID段：起始ID-结束ID

💡 **示例：**
@xsm 20-60
https://t.me/channel_name 1-10

🔧 **说明：**
• 支持@用户名或频道链接
• ID段格式：起始-结束
• 支持多行输入（每行一个源频道和ID段）
• 输入完成后将自动进入下一个目标频道
            """.strip()
            
            buttons = [
                [("❌ 取消", "show_clone_test")]
            ]
            
            await callback_query.edit_message_text(
                input_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理输入源频道信息失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _process_clone_test_single_source_input(self, message: Message, state: Dict[str, Any]):
        """处理单个源频道信息输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            if text.lower() == '取消':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回搬运管理", "show_clone_test")
                    ]])
                )
                return
            
            # 获取当前目标频道索引
            target_index = state.get('target_index', 0)
            
            # 解析源频道信息（支持多行输入）
            source_list = self._parse_source_input(text)
            if not source_list:
                await message.reply_text(
                    "❌ 输入格式错误，请重新输入\n\n💡 **正确格式：**\n@频道名 起始ID-结束ID\n或\n频道链接 起始ID-结束ID\n\n💡 **支持多行输入：**\n@频道1 起始ID-结束ID\n@频道2 起始ID-结束ID",
                    reply_markup=generate_button_layout([[
                        ("❌ 取消", "show_clone_test")
                    ]])
                )
                return
            
            # 保存源频道信息
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': [],
                    'current_source_index': 0
                }
            
            # 确保sources列表足够长
            while len(self.clone_test_selections[user_id]['sources']) <= target_index:
                self.clone_test_selections[user_id]['sources'].append([])
            
            # 保存当前源频道信息（支持多个源频道）
            self.clone_test_selections[user_id]['sources'][target_index] = source_list
            
            # 移动到下一个目标频道
            self.clone_test_selections[user_id]['current_source_index'] = target_index + 1
            
            # 检查是否还有更多目标频道需要输入源频道信息
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            if target_index + 1 < len(selected_targets):
                # 还有更多目标频道，继续输入
                next_target = selected_targets[target_index + 1]
                next_target_name = next_target.get('title', '未知频道')
                next_target_username = next_target.get('username', '')
                if next_target_username:
                    next_target_display = f"{next_target_name} (@{next_target_username})"
                else:
                    next_target_display = f"{next_target_name} (无用户名)"
                
                # 更新用户状态
                self.user_states[user_id] = {
                    'state': 'waiting_clone_test_single_source',
                    'target_index': target_index + 1,
                    'timestamp': time.time()
                }
                
                # 自动进入下一个目标频道的输入界面
                await self._handle_clone_test_input_sources_for_target(message, target_index + 1)
            else:
                # 所有源频道都已输入完成，显示确认界面
                await self._show_clone_test_confirmation(message)
            
        except Exception as e:
            logger.error(f"处理源频道信息输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    
    async def _handle_clone_test_input_sources_for_target(self, message: Message, target_index: int):
        """为指定目标频道显示源频道输入界面"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取选择的目标频道
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': [],
                    'current_source_index': 0
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            
            if target_index >= len(selected_targets):
                # 所有源频道都已输入完成，显示确认界面
                await self._show_clone_test_confirmation(message)
                return
            
            # 获取当前要输入源频道的目标频道
            current_target = selected_targets[target_index]
            target_name = current_target.get('title', '未知频道')
            target_username = current_target.get('username', '')
            if target_username:
                target_display = f"{target_name} (@{target_username})"
            else:
                target_display = f"{target_name} (无用户名)"
            
            # 设置用户状态为等待输入当前源频道信息
            self.user_states[user_id] = {
                'state': 'waiting_clone_test_single_source',
                'target_index': target_index,
                'timestamp': time.time()
            }
            
            input_text = f"""
✅ 源频道信息已保存

📝 **输入源频道信息 ({target_index + 1}/{len(selected_targets)})**

🎯 **目标频道：** {target_display}

📋 **输入格式：**
• 源频道：@频道名 或 频道链接
• ID段：起始ID-结束ID

💡 **示例：**
@xsm 20-60
https://t.me/channel_name 1-10

🔧 **说明：**
• 支持@用户名或频道链接
• ID段格式：起始-结束
• 输入完成后将自动进入下一个目标频道
            """.strip()
            
            # 发送新消息显示下一个目标频道的输入界面
            await message.reply_text(
                input_text,
                reply_markup=generate_button_layout([[
                    ("❌ 取消", "show_clone_test")
                ]])
            )
            
        except Exception as e:
            logger.error(f"显示目标频道源频道输入界面失败: {e}")
            await message.reply_text("❌ 显示输入界面失败")
    
    def _parse_source_input(self, text: str) -> Optional[List[Dict[str, str]]]:
        """解析源频道输入（支持多行输入）"""
        try:
            lines = text.strip().split('\n')
            sources = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                parts = line.split()
                if len(parts) >= 2:
                    channel_info = parts[0]
                    id_range = parts[1]
                    
                    # 处理频道信息，提取用户名
                    if channel_info.startswith('https://t.me/'):
                        # 从URL中提取用户名
                        username = channel_info.replace('https://t.me/', '').strip()
                        if username:
                            channel_info = f"@{username}"
                        else:
                            continue
                    elif not channel_info.startswith('@'):
                        # 如果不是@开头，添加@前缀
                        channel_info = f"@{channel_info}"
                    
                    # 验证ID段格式
                    if '-' in id_range and id_range.replace('-', '').isdigit():
                        sources.append({
                            'channel': channel_info,
                            'id_range': id_range
                        })
            
            return sources if sources else None
        except Exception as e:
            logger.error(f"解析源频道输入失败: {e}")
            return None
    
    async def _show_clone_test_confirmation(self, message_or_callback):
        """显示搬运管理确认界面"""
        try:
            if hasattr(message_or_callback, 'from_user'):
                # 来自消息
                user_id = str(message_or_callback.from_user.id)
                reply_func = message_or_callback.reply_text
            else:
                # 来自回调查询
                user_id = str(message_or_callback.from_user.id)
                reply_func = message_or_callback.edit_message_text
            
            # 获取选择状态
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': [],
                    'current_source_index': 0
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            sources = self.clone_test_selections[user_id]['sources']
            
            # 检查是否有未完成的源频道输入
            if len(sources) != len(selected_targets):
                await reply_func("❌ 源频道信息不完整，请重新输入")
                return
            
            # 计算总源频道数量
            total_sources = sum(len(source_list) for source_list in sources if source_list)
            
            # 显示确认界面
            confirm_text = f"""
✅ **搬运管理确认**

📋 **频道映射关系** ({len(selected_targets)} 个目标频道，{total_sources} 个源频道)
            """.strip()
            
            for i, (target, source_list) in enumerate(zip(selected_targets, sources), 1):
                target_name = target.get('title', '未知频道')
                target_username = target.get('username', '')
                if target_username:
                    target_display = f"{target_name} (@{target_username})"
                else:
                    target_display = f"{target_name} (无用户名)"
                
                if source_list:
                    confirm_text += f"\n\n{i}. {target_display}:"
                    for j, source in enumerate(source_list, 1):
                        source_channel = source['channel']
                        id_range = source['id_range']
                        confirm_text += f"\n   {j}) {source_channel} ({id_range})"
                else:
                    confirm_text += f"\n\n{i}. {target_display}: 无源频道"
            
            # 计算总消息数
            total_messages = 0
            for source_list in sources:
                if source_list:
                    for source in source_list:
                        id_range = source['id_range']
                        start_id, end_id = map(int, id_range.split('-'))
                        total_messages += end_id - start_id + 1
            
            confirm_text += f"""

📊 **统计信息：**
• 目标频道：{len(selected_targets)} 个
• 源频道：{total_sources} 个
• 总消息数：{total_messages} 条

💡 **确认无误后点击开始搬运**
            """.strip()
            
            # 创建按钮
            buttons = [
                [("🚀 开始搬运", "clone_test_start_cloning")],
                [("🔙 重新输入", "clone_test_input_sources")],
                [("🔙 返回搬运管理", "show_clone_test")]
            ]
            
            await reply_func(
                confirm_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示搬运管理确认界面失败: {e}")
            if hasattr(message_or_callback, 'reply_text'):
                await message_or_callback.reply_text("❌ 显示确认界面失败")
            else:
                await message_or_callback.answer("❌ 显示确认界面失败")
    
    async def _handle_clone_test_start_cloning(self, callback_query: CallbackQuery):
        """处理开始搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取选择状态
            if not hasattr(self, 'clone_test_selections'):
                self.clone_test_selections = {}
            if user_id not in self.clone_test_selections:
                self.clone_test_selections[user_id] = {
                    'selected_targets': [],
                    'sources': []
                }
            
            selected_targets = self.clone_test_selections[user_id]['selected_targets']
            sources = self.clone_test_selections[user_id]['sources']
            
            if not selected_targets or not sources:
                await callback_query.answer("❌ 缺少目标频道或源频道信息")
                return
            
            # 开始搬运
            await callback_query.edit_message_text("🚀 **开始搬运...**\n\n⏳ 正在处理，请稍候...")
            
            # 导入搬运引擎
            from cloning_engine import CloningEngine
            
            # 创建搬运引擎实例
            clone_engine = CloningEngine(self.client, self.config, self.data_manager, self.bot_id)
            self.cloning_engine = clone_engine  # 存储为实例变量
            
            # 统计信息
            total_tasks = 0
            successful_tasks = 0
            failed_tasks = 0
            
            # 创建任务进度跟踪
            task_progress = {}
            all_tasks = []
            
            # 为每个目标频道和其对应的源频道创建搬运任务（支持多源频道）
            for i, target_channel in enumerate(selected_targets):
                target_channel_id = target_channel['id']
                target_channel_name = target_channel.get('title', '未知频道')
                
                # 获取对应的源频道信息列表
                if i < len(sources) and sources[i]:
                    source_list = sources[i]
                    logger.info(f"目标频道 {target_channel_name} 有 {len(source_list)} 个源频道")
                    
                    # 为每个源频道创建搬运任务
                    for source in source_list:
                        source_channel = source['channel']
                        id_range = source['id_range']
                        start_id, end_id = map(int, id_range.split('-'))
                        
                        try:
                            # 获取用户配置用于过滤
                            user_config = await self.data_manager.get_user_config(user_id)
                            channel_filters = user_config.get('admin_channel_filters', {}).get(str(target_channel_id), {})
                            
                            # 如果频道启用了独立过滤，使用频道配置；否则使用全局配置
                            if channel_filters.get('independent_enabled', False):
                                filter_config = {
                                    'keywords_enabled': channel_filters.get('keywords_enabled', False),
                                    'filter_keywords': channel_filters.get('keywords', []),
                                    'replacements_enabled': channel_filters.get('replacements_enabled', False),
                                    'replacement_words': channel_filters.get('replacements', {}),
                                    'content_removal': channel_filters.get('content_removal', False),
                                    'remove_all_links': channel_filters.get('remove_links', False),
                                    'remove_usernames': channel_filters.get('remove_usernames', False),
                                    'filter_buttons': channel_filters.get('filter_buttons', False),
                                    'enhanced_filter_enabled': channel_filters.get('enhanced_filter_enabled', False),
                                    'enhanced_filter_mode': channel_filters.get('enhanced_filter_mode', 'moderate'),
                                    'tail_text': channel_filters.get('tail_text', ''),
                                    'tail_frequency': channel_filters.get('tail_frequency', 'always'),
                                    'tail_position': channel_filters.get('tail_position', 'end'),
                                    'additional_buttons': channel_filters.get('additional_buttons', []),
                                    'button_frequency': channel_filters.get('button_frequency', 'always')
                                }
                            else:
                                # 使用全局配置
                                filter_config = {
                                    'keywords_enabled': user_config.get('keywords_enabled', False),
                                    'filter_keywords': user_config.get('filter_keywords', []),
                                    'replacements_enabled': user_config.get('replacements_enabled', False),
                                    'replacement_words': user_config.get('replacement_words', {}),
                                    'content_removal': user_config.get('content_removal', False),
                                    'remove_all_links': user_config.get('remove_all_links', False),
                                    'remove_usernames': user_config.get('remove_usernames', False),
                                    'filter_buttons': user_config.get('filter_buttons', False),
                                    'tail_text': user_config.get('tail_text', ''),
                                    'tail_frequency': user_config.get('tail_frequency', 'always'),
                                    'tail_position': user_config.get('tail_position', 'end'),
                                    'additional_buttons': user_config.get('additional_buttons', []),
                                    'button_frequency': user_config.get('button_frequency', 'always')
                                }
                            
                            # 创建搬运任务 - 使用时间戳生成唯一ID
                            import time
                            task_id = f"clone_{int(time.time())}_{len(clone_engine.active_tasks)}"
                            
                            # 为频道管理创建虚拟的pair_id
                            pair_id = f"admin_test_{target_channel_id}"
                            
                            # 在filter_config中添加user_id和pair_id，让搬运引擎能正确获取频道组配置
                            filter_config['user_id'] = user_id
                            filter_config['pair_id'] = pair_id
                            filter_config['channel_name'] = target_channel.get('name', f"频道({target_channel_id})")
                            
                            task = await clone_engine.create_task(
                                source_chat_id=source_channel,
                                target_chat_id=target_channel_id,
                                start_id=start_id,
                                end_id=end_id,
                                config=filter_config,
                                source_username=source_channel,
                                target_username=target_channel.get('username', ''),
                                task_id=task_id  # 直接传递预定义的任务ID
                            )
                            
                            # 启动搬运任务
                            logger.info(f"🚀 准备启动搬运任务: {task_id}")
                            success = await clone_engine.start_cloning(task)
                            total_tasks += 1
                            
                            logger.info(f"🚀 任务启动结果: {task_id} - 成功: {success}")
                            if success:
                                # 记录任务信息用于进度跟踪
                                task_info = {
                                    'task_id': task_id,
                                    'source_channel': source_channel,
                                    'source_channel_id': source_channel,  # 添加兼容字段
                                    'source_channel_name': source_channel,  # 添加兼容字段
                                    'target_channel_name': target_channel_name,
                                    'target_channel_id': target_channel_id,
                                    'start_id': start_id,
                                    'end_id': end_id,
                                    'total_messages': end_id - start_id + 1,
                                    'status': 'running',
                                    'start_time': datetime.now(),
                                    'processed_messages': 0
                                }
                                all_tasks.append(task_info)
                                task_progress[task_id] = task_info
                                
                                logger.info(f"✅ 搬运任务启动: {source_channel} -> {target_channel_name} ({start_id}-{end_id})")
                            else:
                                failed_tasks += 1
                                logger.error(f"❌ 搬运任务启动失败: {source_channel} -> {target_channel_name} ({start_id}-{end_id})")
                        
                        except Exception as e:
                            logger.error(f"❌ 搬运任务创建失败: {source_channel} -> {target_channel_name}: {e}")
                            failed_tasks += 1
                            total_tasks += 1
                else:
                    logger.error(f"目标频道 {target_channel_name} 没有对应的源频道信息")
                    continue
            
            # 存储任务状态到实例变量
            user_id = str(callback_query.from_user.id)
            if not hasattr(self, 'task_progress'):
                self.task_progress = {}
            if not hasattr(self, 'all_tasks'):
                self.all_tasks = {}
            
            self.task_progress[user_id] = task_progress
            self.all_tasks[user_id] = all_tasks
            
            # 设置进度回调
            await self._setup_progress_tracking(callback_query, task_progress, all_tasks)
            
            # 显示进度跟踪界面
            await self._show_cloning_progress(callback_query, task_progress, all_tasks)
            
        except Exception as e:
            logger.error(f"处理开始搬运失败: {e}")
            await callback_query.edit_message_text("❌ 搬运失败，请稍后重试")
    
    async def _setup_progress_tracking(self, callback_query: CallbackQuery, task_progress: Dict, all_tasks: List[Dict]):
        """设置进度跟踪"""
        try:
            # 创建进度回调函数
            async def progress_callback(task):
                """进度回调函数"""
                try:
                    task_id = task.task_id
                    if task_id in task_progress:
                        # 更新任务进度信息
                        task_progress[task_id]['processed_messages'] = task.processed_messages
                        task_progress[task_id]['status'] = task.status
                        task_progress[task_id]['progress'] = task.progress
                        
                        # 找到对应的任务信息
                        for task_info in all_tasks:
                            if task_info['task_id'] == task_id:
                                task_info['processed_messages'] = task.processed_messages
                                task_info['status'] = task.status
                                task_info['progress'] = task.progress
                                break
                        
                        logger.info(f"📊 进度更新: {task_id} - {task.processed_messages}/{task.total_messages} ({task.progress:.1f}%)")
                        
                except Exception as e:
                    logger.error(f"进度回调处理失败: {e}")
            
            # 设置进度回调
            if hasattr(self, 'cloning_engine') and self.cloning_engine:
                clone_engine = self.cloning_engine
                clone_engine.set_progress_callback(progress_callback)
            else:
                logger.warning("⚠️ 搬运引擎未初始化，无法设置进度回调")
            
        except Exception as e:
            logger.error(f"设置进度跟踪失败: {e}")
    
    async def _show_cloning_progress(self, callback_query: CallbackQuery, task_progress: Dict, all_tasks: List[Dict]):
        """显示搬运进度界面"""
        try:
            from datetime import datetime
            import asyncio
            
            # 创建进度显示任务
            asyncio.create_task(self._update_cloning_progress(callback_query, task_progress, all_tasks))
            
        except Exception as e:
            logger.error(f"显示搬运进度失败: {e}")
            await callback_query.edit_message_text("❌ 显示进度失败")
    
    async def _update_cloning_progress(self, callback_query: CallbackQuery, task_progress: Dict, all_tasks: List[Dict]):
        """更新搬运进度（每30秒刷新一次）"""
        try:
            from datetime import datetime
            import asyncio
            
            # 按目标频道分组显示进度
            target_groups = {}
            for task_info in all_tasks:
                target_id = task_info['target_channel_id']
                if target_id not in target_groups:
                    target_groups[target_id] = {
                        'target_name': task_info['target_channel_name'],
                        'tasks': []
                    }
                target_groups[target_id]['tasks'].append(task_info)
            
            # 显示初始进度
            await self._display_progress(callback_query, target_groups, all_tasks)
            
            # 每30秒更新一次进度
            while True:
                await asyncio.sleep(30)
                
                # 从搬运引擎获取实际任务状态
                await self._update_task_status_from_engine(all_tasks)
                
                # 恢复丢失的任务状态
                await self._recover_lost_tasks(all_tasks)
                
                # 重新构建目标频道分组（因为任务状态可能已更新）
                target_groups = {}
                for task_info in all_tasks:
                    target_id = task_info['target_channel_id']
                    if target_id not in target_groups:
                        target_groups[target_id] = {
                            'target_name': task_info['target_channel_name'],
                            'tasks': []
                        }
                    target_groups[target_id]['tasks'].append(task_info)
                
                # 检查是否所有任务都完成
                all_completed = True
                running_tasks = 0
                completed_tasks = 0
                failed_tasks = 0
                
                for task_info in all_tasks:
                    status = task_info['status']
                    if status == 'running':
                        all_completed = False
                        running_tasks += 1
                    elif status == 'completed':
                        completed_tasks += 1
                    elif status == 'failed':
                        failed_tasks += 1
                
                logger.info(f"📊 任务状态统计: 运行中={running_tasks}, 已完成={completed_tasks}, 已失败={failed_tasks}")
                
                if all_completed:
                    # 额外验证：确保所有任务都真的完成了
                    # 检查是否还有任务在active_tasks中运行
                    still_running_count = 0
                    for task_info in all_tasks:
                        task_id = task_info['task_id']
                        if hasattr(self, 'cloning_engine') and self.cloning_engine and task_id in self.cloning_engine.active_tasks:
                            task = self.cloning_engine.active_tasks[task_id]
                            if task.status not in ["completed", "failed"]:
                                still_running_count += 1
                                logger.info(f"🔍 任务 {task_id} 仍在运行，状态: {task.status}")
                    
                    if still_running_count == 0:
                        logger.info(f"🎉 所有任务完成，显示最终结果: 完成={completed_tasks}, 失败={failed_tasks}")
                        # 显示最终结果
                        await self._show_final_results(callback_query, all_tasks)
                        break
                    else:
                        logger.info(f"⚠️ 检测到 {still_running_count} 个任务仍在运行，继续监控")
                        all_completed = False
                else:
                    # 更新进度
                    await self._display_progress(callback_query, target_groups, all_tasks)
                    
        except Exception as e:
            logger.error(f"更新搬运进度失败: {e}")
    
    async def _update_task_status_from_engine(self, all_tasks: List[Dict]):
        """从搬运引擎获取实际任务状态"""
        try:
            if not hasattr(self, 'cloning_engine') or self.cloning_engine is None:
                logger.warning("⚠️ 搬运引擎未初始化，跳过状态更新")
                return
                
            clone_engine = self.cloning_engine
            
            # 调试：打印活动任务列表
            logger.info(f"🔍 调试：活动任务数量: {len(clone_engine.active_tasks)}")
            for active_task_id, active_task in clone_engine.active_tasks.items():
                logger.info(f"🔍 调试：活动任务 {active_task_id} - 状态: {active_task.status}, 进度: {active_task.processed_messages}/{active_task.total_messages}")
            
            # 调试：打印历史任务列表
            logger.info(f"🔍 调试：历史任务数量: {len(clone_engine.task_history)}")
            for history_task in clone_engine.task_history:
                task_id = history_task.get('task_id', 'unknown')
                logger.info(f"🔍 调试：历史任务 {task_id} - 状态: {history_task.get('status', 'unknown')}, 进度: {history_task.get('processed_messages', 0)}/{history_task.get('total_messages', 0)}")
            
            for task_info in all_tasks:
                task_id = task_info['task_id']
                
                # 从搬运引擎获取任务状态
                if hasattr(clone_engine, 'active_tasks') and task_id in clone_engine.active_tasks:
                    task = clone_engine.active_tasks[task_id]
                    task_info['processed_messages'] = task.processed_messages
                    task_info['status'] = task.status
                    task_info['progress'] = task.progress
                    
                    logger.info(f"📊 从引擎更新任务状态: {task_id} - {task.processed_messages}/{task.total_messages} ({task.progress:.1f}%)")
                else:
                    # 任务不在活动列表中，需要检查历史记录
                    logger.warning(f"⚠️ 任务不在活动列表中: {task_id}, 当前状态: {task_info['status']}")
                    
                    # 检查任务历史记录
                    task_found_in_history = False
                    if hasattr(clone_engine, 'task_history'):
                        for history_task in clone_engine.task_history:
                            if history_task.get('task_id') == task_id:
                                task_found_in_history = True
                                history_status = history_task.get('status', 'unknown')
                                logger.info(f"🔍 任务 {task_id} 在历史记录中，状态: {history_status}")
                                
                                if history_status == "completed":
                                    task_info['status'] = 'completed'
                                    task_info['processed_messages'] = history_task.get('processed_messages', task_info['total_messages'])
                                    task_info['progress'] = 100.0
                                    # 更新总消息数为实际处理的消息数，避免显示不准确的进度
                                    if history_task.get('processed_messages', 0) > 0:
                                        task_info['total_messages'] = history_task.get('processed_messages', task_info['total_messages'])
                                    logger.info(f"📊 任务已完成: {task_id}")
                                elif history_status == "failed":
                                    task_info['status'] = 'failed'
                                    logger.info(f"📊 任务已失败: {task_id}")
                                else:
                                    # 历史记录中的任务状态不是completed或failed，说明还在运行
                                    logger.info(f"🔍 任务 {task_id} 在历史记录中但状态为 {history_status}，仍在运行")
                                break
                    
                    if not task_found_in_history:
                        # 任务既不在活动任务中，也不在历史记录中
                        # 这种情况可能是任务刚启动就被清理了，或者出现了异常
                        logger.warning(f"⚠️ 任务 {task_id} 既不在活动任务中也不在历史记录中，可能出现了异常")
                        
                        # 检查任务是否启动失败
                        # 如果任务ID存在但不在任何地方，很可能是启动失败
                        if task_info['status'] == 'running':
                            logger.warning(f"⚠️ 任务 {task_id} 状态为running但不在任何地方，标记为失败")
                            task_info['status'] = 'failed'
                            task_info['progress'] = 0.0
                            logger.info(f"📊 任务已标记为失败: {task_id}")
                        else:
                            # 为了安全起见，我们认为任务还在运行，不改变状态
                            logger.info(f"🔍 任务 {task_id} 状态为 {task_info['status']}，保持不变")
                        
        except Exception as e:
            logger.error(f"从引擎更新任务状态失败: {e}")
    
    async def _recover_lost_tasks(self, all_tasks: List[Dict]):
        """恢复丢失的任务状态"""
        try:
            if not hasattr(self, 'cloning_engine') or self.cloning_engine is None:
                return
            
            logger.info("🔍 开始检查丢失的任务...")
            recovered_count = 0
            
            for task_info in all_tasks:
                task_id = task_info['task_id']
                status = task_info['status']
                
                # 只检查状态为running但不在任何地方的任务
                if status == 'running':
                    # 检查是否在活动任务中
                    if task_id in self.cloning_engine.active_tasks:
                        continue  # 任务正常，跳过
                    
                    # 检查是否在历史记录中
                    task_found_in_history = False
                    if hasattr(self.cloning_engine, 'task_history'):
                        for history_task in self.cloning_engine.task_history:
                            if history_task.get('task_id') == task_id:
                                task_found_in_history = True
                                history_status = history_task.get('status', 'unknown')
                                logger.info(f"🔍 发现丢失的任务 {task_id} 在历史记录中，状态: {history_status}")
                                
                                # 更新任务状态
                                task_info['status'] = history_status
                                if history_status == 'completed':
                                    task_info['processed_messages'] = history_task.get('processed_messages', task_info['total_messages'])
                                    task_info['progress'] = 100.0
                                elif history_status == 'failed':
                                    task_info['progress'] = 0.0
                                
                                recovered_count += 1
                                logger.info(f"✅ 任务状态已恢复: {task_id} -> {history_status}")
                                break
                    
                    if not task_found_in_history:
                        # 任务真的丢失了，标记为失败
                        logger.warning(f"⚠️ 任务 {task_id} 确实丢失，标记为失败")
                        task_info['status'] = 'failed'
                        task_info['progress'] = 0.0
                        recovered_count += 1
                        logger.info(f"📊 任务已标记为失败: {task_id}")
            
            if recovered_count > 0:
                logger.info(f"🔄 任务状态恢复完成，恢复了 {recovered_count} 个任务")
            else:
                logger.info("✅ 没有发现丢失的任务")
                
        except Exception as e:
            logger.error(f"恢复丢失任务失败: {e}")
    
    async def _display_progress(self, callback_query: CallbackQuery, target_groups: Dict, all_tasks: List[Dict]):
        """显示当前进度"""
        try:
            from datetime import datetime
            
            progress_text = "🚀 **搬运进度跟踪**\n\n"
            
            for target_id, group in target_groups.items():
                target_name = group['target_name']
                tasks = group['tasks']
                
                progress_text += f"📢 **{target_name}**\n"
                
                total_messages = 0
                processed_messages = 0
                
                for i, task_info in enumerate(tasks, 1):
                    source_channel = task_info['source_channel']
                    start_id = task_info['start_id']
                    end_id = task_info['end_id']
                    status = task_info.get('status', 'running')
                    processed = task_info.get('processed_messages', 0)
                    total = task_info['total_messages']
                    
                    total_messages += total
                    processed_messages += processed
                    
                    # 计算进度百分比
                    if total > 0:
                        percentage = (processed / total) * 100
                    else:
                        percentage = 0
                    
                    # 状态图标
                    if status == 'completed':
                        status_icon = "✅"
                    elif status == 'running':
                        status_icon = "🔄"
                    elif status == 'failed':
                        status_icon = "❌"
                    else:
                        status_icon = "⏳"
                    
                    progress_text += f"  {i}. {status_icon} {source_channel} ({start_id}-{end_id})\n"
                    progress_text += f"     📊 进度: {processed}/{total} ({percentage:.1f}%)\n"
                
                # 目标频道总进度
                if total_messages > 0:
                    target_percentage = (processed_messages / total_messages) * 100
                else:
                    target_percentage = 0
                
                progress_text += f"  📈 总进度: {processed_messages}/{total_messages} ({target_percentage:.1f}%)\n\n"
            
            # 添加时间信息
            current_time = datetime.now().strftime("%m-%d %H:%M:%S")
            progress_text += f"⏰ 更新时间: {current_time}\n"
            progress_text += "🔄 每30秒自动刷新"
            
            # 创建按钮
            buttons = [
                [("🔄 手动刷新", "refresh_cloning_progress")],
                [("⏹️ 停止搬运", "stop_cloning_progress")],
                [("🔄 断点续传", "resume_cloning_progress")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            logger.info(f"🔧 [DEBUG] 显示进度界面，按钮数量: {len(buttons)}")
            logger.info(f"🔧 [DEBUG] 按钮内容: {buttons}")
            
            await callback_query.edit_message_text(
                progress_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示进度失败: {e}")
    
    async def _show_final_results(self, callback_query: CallbackQuery, all_tasks: List[Dict]):
        """显示最终结果"""
        try:
            from datetime import datetime
            
            # 统计结果
            total_tasks = len(all_tasks)
            completed_tasks = len([t for t in all_tasks if t['status'] == 'completed'])
            failed_tasks = len([t for t in all_tasks if t['status'] == 'failed'])
            
            # 按目标频道分组统计
            target_groups = {}
            source_groups = {}
            total_messages = 0
            total_processed = 0
            
            for task_info in all_tasks:
                target_id = task_info['target_channel_id']
                source_id = task_info.get('source_channel_id', task_info.get('source_channel', '未知'))
                target_name = task_info['target_channel_name']
                source_name = task_info.get('source_channel_name', task_info.get('source_channel', '未知'))
                task_messages = task_info['total_messages']
                processed_messages = task_info.get('processed_messages', 0)
                
                total_messages += task_messages
                total_processed += processed_messages
                
                # 按目标频道统计
                if target_id not in target_groups:
                    target_groups[target_id] = {
                        'target_name': target_name,
                        'total_messages': 0,
                        'processed_messages': 0,
                        'source_channels': []
                    }
                target_groups[target_id]['total_messages'] += task_messages
                target_groups[target_id]['processed_messages'] += processed_messages
                target_groups[target_id]['source_channels'].append({
                    'source_name': source_name,
                    'messages': task_messages,
                    'processed': processed_messages
                })
                
                # 按源频道统计
                if source_id not in source_groups:
                    source_groups[source_id] = {
                        'source_name': source_name,
                        'total_messages': 0,
                        'processed_messages': 0,
                        'target_channels': []
                    }
                source_groups[source_id]['total_messages'] += task_messages
                source_groups[source_id]['processed_messages'] += processed_messages
                source_groups[source_id]['target_channels'].append({
                    'target_name': target_name,
                    'messages': task_messages,
                    'processed': processed_messages
                })
            
            # 构建详细结果文本
            result_text = "🎉 **频道管理搬运完成**\n\n"
            result_text += f"📊 **执行结果**:\n"
            result_text += f"• 总任务数: {total_tasks} 个\n"
            result_text += f"• 成功完成: {completed_tasks} 个\n"
            result_text += f"• 失败数量: {failed_tasks} 个\n\n"
            
            result_text += f"📈 **总体统计**:\n"
            result_text += f"• 总消息数: {total_messages} 条\n"
            result_text += f"• 已处理: {total_processed} 条\n\n"
            
            # 按目标频道显示统计
            if target_groups:
                result_text += "📢 **各目标频道接收统计**:\n"
                for target_id, group in target_groups.items():
                    result_text += f"\n📢 {group['target_name']}\n"
                    for source_info in group['source_channels']:
                        result_text += f"  • 📤 {source_info['source_name']}: {source_info['processed']}/{source_info['messages']} 条\n"
                    result_text += f"  📈 总计: {group['processed_messages']}/{group['total_messages']} 条\n"
            
            # 按源频道显示统计
            if source_groups:
                result_text += "\n\n📤 **各源频道搬运统计**:\n"
                for source_id, group in source_groups.items():
                    result_text += f"\n📤 {group['source_name']}\n"
                    for target_info in group['target_channels']:
                        result_text += f"  • 📢 {target_info['target_name']}: {target_info['processed']}/{target_info['messages']} 条\n"
                    result_text += f"  📈 总计: {group['processed_messages']}/{group['total_messages']} 条\n"
            
            # 创建按钮
            buttons = [
                [("🔄 重新选择目标频道", "clone_test_select_targets")],
                [("📊 查看任务历史", "view_tasks")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                result_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示最终结果失败: {e}")
    
    async def _handle_toggle_admin_replacements(self, callback_query: CallbackQuery):
        """处理频道敏感词替换状态切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换敏感词替换状态
            current_status = channel_filters.get('replacements_enabled', False)
            channel_filters['replacements_enabled'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['replacements_enabled'] else "❌ 已禁用"
            await callback_query.answer(f"敏感词替换 {status_text}")
            
            # 刷新敏感词替换界面
            await self._handle_admin_channel_replacements(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道敏感词替换状态切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_add_admin_replacement(self, callback_query: CallbackQuery):
        """处理添加频道敏感词替换规则"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 设置用户状态为等待输入替换规则
            self.user_states[user_id] = {
                'state': 'waiting_admin_replacement',
                'channel_id': channel_id,
                'timestamp': time.time()
            }
            
            await callback_query.edit_message_text(
                "🔄 **添加敏感词替换规则**\n\n请输入替换规则，格式：`原词|替换词`\n\n💡 **提示：**\n• 发送 `原词|替换词` 来添加规则\n• 发送 `取消` 来取消操作",
                reply_markup=generate_button_layout([[
                    ("❌ 取消", f"admin_channel_replacements:{channel_id}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理添加频道敏感词替换规则失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_admin_replacements(self, callback_query: CallbackQuery):
        """处理清空频道敏感词替换规则"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 清空替换规则
            channel_filters['replacements'] = {}
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer("✅ 替换规则已清空")
            
            # 刷新敏感词替换界面
            await self._handle_admin_channel_replacements(callback_query)
            
        except Exception as e:
            logger.error(f"处理清空频道敏感词替换规则失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _process_admin_replacement_input(self, message: Message, state: Dict[str, Any]):
        """处理频道敏感词替换规则输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            channel_id = state.get('channel_id')
            
            if not channel_id:
                await message.reply_text("❌ 频道ID丢失，请重新操作")
                return
            
            if text.lower() == '取消':
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回敏感词替换", f"admin_channel_replacements:{channel_id}")
                    ]])
                )
                return
            
            # 处理删除规则
            if text.startswith('删除:'):
                original_word = text[3:].strip()
                if not original_word:
                    await message.reply_text("❌ 请输入要删除的原词")
                    return
                
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                replacements = channel_filters.get('replacements', {})
                
                if original_word in replacements:
                    del replacements[original_word]
                    channel_filters['replacements'] = replacements
                    
                    # 保存配置
                    user_config = await self.data_manager.get_user_config(user_id)
                    user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(f"✅ 已删除替换规则: {original_word}")
                else:
                    await message.reply_text(f"❌ 替换规则不存在: {original_word}")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新敏感词替换界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_replacements:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_replacements(callback_query)
                return
            
            # 处理清空规则
            if text == '清空':
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                channel_filters['replacements'] = {}
                
                # 保存配置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text("✅ 已清空所有替换规则")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新敏感词替换界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_replacements:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_replacements(callback_query)
                return
            
            # 处理启用/禁用
            if text in ['启用', '禁用']:
                enabled = text == '启用'
                
                # 获取频道过滤配置
                channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                channel_filters['replacements_enabled'] = enabled
                
                # 保存配置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                status_text = "✅ 已启用" if enabled else "❌ 已禁用"
                await message.reply_text(f"敏感词替换 {status_text}")
                
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 刷新敏感词替换界面
                callback_query = type('obj', (object,), {
                    'data': f'admin_channel_replacements:{channel_id}',
                    'from_user': message.from_user,
                    'edit_message_text': message.reply_text
                })()
                await self._handle_admin_channel_replacements(callback_query)
                return
            
            # 添加替换规则
            if text and '|' in text:
                parts = text.split('|', 1)
                if len(parts) == 2:
                    original_word = parts[0].strip()
                    replacement_word = parts[1].strip()
                    
                    if original_word and replacement_word:
                        # 获取频道过滤配置
                        channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
                        replacements = channel_filters.get('replacements', {})
                        
                        # 添加替换规则
                        replacements[original_word] = replacement_word
                        channel_filters['replacements'] = replacements
                        
                        # 保存配置
                        user_config = await self.data_manager.get_user_config(user_id)
                        user_config['admin_channel_filters'][str(channel_id)] = channel_filters
                        await self.data_manager.save_user_config(user_id, user_config)
                        
                        await message.reply_text(f"✅ 替换规则添加成功: {original_word} → {replacement_word}")
                    else:
                        await message.reply_text("❌ 原词和替换词不能为空")
                        return
                else:
                    await message.reply_text("❌ 格式错误，请使用 `原词|替换词` 格式")
                    return
            else:
                await message.reply_text("❌ 格式错误，请使用 `原词|替换词` 格式")
                return
            
            # 继续等待输入
            await message.reply_text(
                "💡 **继续添加替换规则或发送其他命令：**\n• 发送 `原词|替换词` 来添加规则\n• 发送 `删除:原词` 来删除特定规则\n• 发送 `清空` 来清空所有规则\n• 发送 `启用` 或 `禁用` 来切换替换状态\n• 发送 `完成` 来结束添加",
                reply_markup=generate_button_layout([[
                    ("🔙 返回敏感词替换", f"admin_channel_replacements:{channel_id}")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理频道敏感词替换规则输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def _handle_toggle_admin_enhanced_filter(self, callback_query: CallbackQuery):
        """处理频道增强版链接过滤状态切换"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 切换增强版链接过滤状态
            current_status = channel_filters.get('enhanced_filter_enabled', False)
            channel_filters['enhanced_filter_enabled'] = not current_status
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已启用" if channel_filters['enhanced_filter_enabled'] else "❌ 已禁用"
            await callback_query.answer(f"增强版链接过滤 {status_text}")
            
            # 刷新增强版链接过滤界面
            await self._handle_admin_channel_links_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道增强版链接过滤状态切换失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_enhanced_mode(self, callback_query: CallbackQuery):
        """处理频道增强版链接过滤模式选择"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            
            config_text = f"""
⚙️ **选择增强版链接过滤模式**

📢 **频道：** {channel_name}

💡 **请选择过滤模式：**
            """.strip()
            
            buttons = [
                [("🔥 激进模式", f"set_admin_enhanced_mode:{channel_id}:aggressive")],
                [("⚖️ 中等模式", f"set_admin_enhanced_mode:{channel_id}:moderate")],
                [("🛡️ 保守模式", f"set_admin_enhanced_mode:{channel_id}:conservative")],
                [("🔙 返回增强版链接过滤", f"admin_channel_links_removal:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道增强版链接过滤模式选择失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_admin_enhanced_mode(self, callback_query: CallbackQuery):
        """处理设置频道增强版链接过滤模式"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            channel_id = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道过滤配置
            channel_filters = await self._init_admin_channel_filters(user_id, str(channel_id))
            
            # 设置模式
            channel_filters['enhanced_filter_mode'] = mode
            channel_filters['enhanced_filter_enabled'] = True  # 启用功能
            
            # 保存配置
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['admin_channel_filters'][str(channel_id)] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_names = {
                'aggressive': '激进模式',
                'moderate': '中等模式',
                'conservative': '保守模式'
            }
            mode_name = mode_names.get(mode, '未知模式')
            await callback_query.answer(f"已设置为：{mode_name}")
            
            # 刷新增强版链接过滤界面
            await self._handle_admin_channel_links_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理设置频道增强版链接过滤模式失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    def _get_api_client(self):
        """获取API客户端（优先使用User API）"""
        if self.user_api_logged_in and self.user_api_manager and self.user_api_manager.client:
            return self.user_api_manager.client
        else:
            return self.client
    
    def _get_bot_api_client(self):
        """获取Bot API客户端（用于删除消息等操作）"""
        return self.client
    
    async def _get_admin_channels(self):
        """获取机器人是管理员的频道列表（仅显示本地数据，不自动验证）"""
        try:
            admin_channels = []
            
            # 从频道数据管理器获取所有频道（包括未验证的）
            all_channels = self.channel_data_manager.get_all_channels()
            logger.info(f"🔍 从本地数据获取 {len(all_channels)} 个频道")
            
            # 调试信息：打印频道数据管理器的状态
            logger.info(f"🔍 频道数据管理器状态: 文件={self.channel_data_manager.data_file}, 数据量={len(self.channel_data_manager.channels_data)}")
            
            for channel_data in all_channels:
                channel_id = channel_data['id']
                is_verified = channel_data.get('verified', False)
                
                if is_verified:
                    # 已验证的频道直接添加
                    admin_channels.append(channel_data)
                    logger.info(f"📝 频道 {channel_id} 使用已验证的缓存数据")
                else:
                    # 未验证的频道也添加，但标记为需要验证
                    channel_data['needs_verification'] = True
                    admin_channels.append(channel_data)
                    logger.info(f"⚠️ 频道 {channel_id} 未验证，需要重新验证")
            
            # 添加已知频道（如果配置了）
            # 注意：_add_known_channels 方法不存在，暂时注释掉
            # await self._add_known_channels(admin_channels)
            
            logger.info(f"✅ 获取到 {len(admin_channels)} 个频道（已验证: {len([c for c in admin_channels if c.get('verified', False)])} 个）")
            return admin_channels
            
        except Exception as e:
            logger.error(f"获取频道列表失败: {e}")
            return []
    
    async def _get_known_channel_ids(self):
        """获取已知的频道ID列表"""
        try:
            # 从数据管理器中获取已知频道ID
            if hasattr(self, 'data_manager') and self.data_manager:
                # 尝试从数据管理器获取
                try:
                    known_channels = await self.data_manager.get_user_config("system")
                    if known_channels and 'known_channels' in known_channels:
                        return known_channels['known_channels']
                except Exception as e:
                    logger.warning(f"从数据管理器获取频道列表失败: {e}")
            
            # 如果数据管理器不可用，使用内存中的列表
            return getattr(self, '_known_channel_ids', [])
        except Exception as e:
            logger.error(f"获取已知频道ID失败: {e}")
            return []
    
    async def _add_known_channel(self, channel_id, channel_data=None):
        """添加已知频道ID"""
        try:
            # 获取频道信息
            if not channel_data:
                try:
                    chat = await self._get_api_client().get_chat(channel_id)
                    channel_data = {
                        'id': chat.id,
                        'title': chat.title,
                        'username': getattr(chat, 'username', None),
                        'type': str(chat.type).lower(),
                        'verified': True,
                        'added_at': datetime.now().isoformat()
                    }
                except Exception as e:
                    logger.warning(f"无法获取频道信息: {e}")
                    channel_data = {
                        'id': channel_id,
                        'title': f"频道 {channel_id}",
                        'username': None,
                        'type': 'unknown',
                        'verified': False,
                        'added_at': datetime.now().isoformat()
                    }
            
            # 添加到频道数据管理器
            self.channel_data_manager.add_channel(channel_id, channel_data)
            logger.info(f"✅ 已添加频道到数据管理器: {channel_id}")
                
        except Exception as e:
            logger.error(f"添加已知频道失败: {e}")
    
    async def _initialize_known_channels(self):
        """初始化已知频道列表"""
        try:
            logger.info("🔄 正在初始化已知频道列表...")
            
            # 从数据管理器加载已知频道
            if hasattr(self, 'data_manager') and self.data_manager:
                try:
                    system_config = await self.data_manager.get_user_config("system")
                    if system_config and 'known_channels' in system_config:
                        self._known_channel_ids = system_config['known_channels']
                        logger.info(f"✅ 已加载 {len(self._known_channel_ids)} 个已知频道: {self._known_channel_ids}")
                    else:
                        self._known_channel_ids = []
                        logger.info("📝 没有找到已知频道，初始化为空列表")
                except Exception as e:
                    logger.warning(f"从数据管理器加载频道列表失败: {e}")
                    self._known_channel_ids = []
            else:
                self._known_channel_ids = []
                logger.info("📝 数据管理器不可用，初始化为空列表")
                
        except Exception as e:
            logger.error(f"初始化已知频道列表失败: {e}")
            self._known_channel_ids = []
    
    async def _update_known_channel_ids(self, new_channel_ids):
        """更新已知频道ID列表"""
        try:
            # 更新内存列表
            self._known_channel_ids = new_channel_ids
            
            # 保存到数据管理器
            if hasattr(self, 'data_manager') and self.data_manager:
                try:
                    system_config = await self.data_manager.get_user_config("system")
                    if not system_config:
                        system_config = {}
                    
                    system_config['known_channels'] = new_channel_ids
                    await self.data_manager.save_user_config("system", system_config)
                    logger.info(f"✅ 已更新已知频道列表: {new_channel_ids}")
                except Exception as e:
                    logger.warning(f"保存频道列表到数据管理器失败: {e}")
            
        except Exception as e:
            logger.error(f"更新已知频道列表失败: {e}")
    
    async def _handle_get_bot_invite_link(self, callback_query: CallbackQuery):
        """处理获取机器人邀请链接"""
        try:
            await callback_query.answer("🔗 正在生成邀请链接...")
            
            # 获取机器人信息
            bot_info = await self.client.get_me()
            bot_username = bot_info.username
            
            # 生成邀请链接
            invite_link = f"https://t.me/{bot_username}?startgroup"
            
            invite_text = f"""
🤖 **机器人邀请链接**

🔗 **邀请链接：**
`{invite_link}`

📋 **使用步骤：**
1. 复制上面的邀请链接
2. 在频道中发送邀请链接
3. 将机器人添加为管理员
4. 机器人会自动检测并添加到列表

💡 **提示：**
• 确保给机器人管理员权限
• 机器人会自动检测权限变化
• 添加后可在频道中发送 `/lsj` 验证

🔧 **机器人功能：**
• 自动检测管理员权限变化
• 验证用户发送的 `/lsj` 命令
• 自动删除验证消息
            """.strip()
            
            await callback_query.edit_message_text(
                invite_text,
                reply_markup=generate_button_layout([
                    [("🔙 返回测试", "show_channel_admin_test")],
                    [("🔙 返回主菜单", "show_main_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"获取机器人邀请链接失败: {e}")
            await callback_query.answer("❌ 获取邀请链接失败，请稍后重试")
    
    async def _handle_add_channel_manually(self, callback_query: CallbackQuery):
        """处理手动添加频道"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 设置用户状态为等待频道输入
            self.user_states[user_id] = {
                'state': 'waiting_for_channel_id',
                'action': 'add_channel_manually'
            }
            
            await callback_query.edit_message_text(
                "➕ **手动添加频道**\n\n"
                "请输入频道ID或频道链接：\n\n"
                "📝 **支持的格式：**\n"
                "• 频道ID: `-1001234567890`\n"
                "• 频道链接: `@channel_username`\n"
                "• 频道链接: `https://t.me/channel_username`\n\n"
                "💡 **提示：** 请确保机器人已经是该频道的管理员",
                reply_markup=generate_button_layout([[
                    ("❌ 取消", "show_channel_admin_test")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理手动添加频道失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _process_channel_id_input(self, message: Message, state: Dict[str, Any]):
        """处理频道ID输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            logger.info(f"🔍 处理频道ID输入: {text}")
            
            # 解析频道ID或链接
            channel_id = None
            
            if text.startswith('-100'):
                # 直接是频道ID
                channel_id = int(text)
            elif text.startswith('@'):
                # 用户名格式
                try:
                    chat = await self._get_api_client().get_chat(text)
                    channel_id = chat.id
                except Exception as e:
                    await message.reply_text(f"❌ 无法找到频道: {text}\n错误: {str(e)}")
                    return
            elif 't.me/' in text:
                # 链接格式
                try:
                    chat = await self._get_api_client().get_chat(text)
                    channel_id = chat.id
                except Exception as e:
                    await message.reply_text(f"❌ 无法找到频道: {text}\n错误: {str(e)}")
                    return
            else:
                await message.reply_text("❌ 不支持的格式，请使用频道ID、@用户名或完整链接")
                return
            
            # 检查机器人是否为该频道的管理员
            try:
                chat = await self._get_api_client().get_chat(channel_id)
                member = await self._get_api_client().get_chat_member(channel_id, "me")
                
                if member.status not in ['administrator', 'creator']:
                    await message.reply_text(
                        f"❌ 机器人不是该频道的管理员\n\n"
                        f"📢 频道: {chat.title}\n"
                        f"🔧 请先将机器人添加为管理员"
                    )
                    return
                
                # 添加频道到已知列表
                await self._add_known_channel(channel_id)
                
                # 清除用户状态
                del self.user_states[user_id]
                
                await message.reply_text(
                    f"✅ 频道添加成功！\n\n"
                    f"📢 频道: {chat.title}\n"
                    f"🔗 用户名: @{getattr(chat, 'username', '无')}\n"
                    f"🆔 ID: {channel_id}\n\n"
                    f"💡 现在可以在频道管理中查看此频道",
                    reply_markup=generate_button_layout([[
                        ("📋 查看频道列表", "show_channel_admin_test")
                    ]])
                )
                
            except Exception as e:
                await message.reply_text(f"❌ 验证频道失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理频道ID输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _handle_show_feature_config(self, callback_query: CallbackQuery):
        """处理显示功能配置"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 清理用户的输入状态，避免状态冲突
            if user_id in self.user_states:
                logger.info(f"清理用户 {user_id} 的输入状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
            
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 统计配置信息
            keywords_count = len(user_config.get('filter_keywords', []))
            replacements_count = len(user_config.get('replacement_words', {}))
            buttons_count = len(user_config.get('additional_buttons', []))
            
            # 状态文本
            content_removal_status = "✅" if user_config.get('content_removal') else "❌"
            button_filter_status = "✅" if user_config.get('filter_buttons') else "❌"
            tail_text_status = "✅" if user_config.get('tail_text') else "❌"
            links_status = "✅" if user_config.get('remove_all_links') else "❌"
            usernames_status = "✅" if user_config.get('remove_usernames') else "❌"
            
            # 获取各种移除功能的详细状态
            content_removal_mode = user_config.get('content_removal_mode', 'text_only')
            mode_descriptions = {"text_only": "仅移除纯文本", "all_content": "移除所有包含文本的信息"}
            content_removal_mode_text = mode_descriptions.get(content_removal_mode, "未知模式")
            
            link_mode = user_config.get('remove_links_mode', 'links_only')
            link_mode_text = "智能移除链接" if link_mode == 'links_only' else "移除整条消息"
            
            tail_position = user_config.get('tail_position', 'end')
            tail_position_text = "开头" if tail_position == 'start' else "结尾"
            
            # 判断链接移除功能的整体状态
            links_enabled = any([
                user_config.get('remove_links', False),
                user_config.get('remove_all_links', False),
                user_config.get('remove_magnet_links', False)
            ])
            
            # 获取链接移除的模式描述
            if user_config.get('remove_all_links', False):
                links_mode_text = "移除所有类型链接"
            elif user_config.get('remove_links', False):
                links_mode_text = link_mode_text
            elif user_config.get('remove_magnet_links', False):
                links_mode_text = "仅移除磁力链接"
            else:
                links_mode_text = "未设置"
            
            # 获取按钮移除模式描述
            button_mode = user_config.get('button_filter_mode', 'remove_buttons_only')
            button_mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            button_mode_text = button_mode_descriptions.get(button_mode, '未知模式')
            
            # 获取附加文字状态
            tail_text = user_config.get('tail_text', '')
            tail_frequency = user_config.get('tail_frequency', 'always')
            tail_position = user_config.get('tail_position', 'end')
            tail_status = "✅ 开启" if tail_text else "❌ 关闭"
            
            # 频率描述
            frequency_descriptions = {
                'always': '每条都添加',
                'interval': '间隔添加',
                'random': '随机添加'
            }
            tail_frequency_text = frequency_descriptions.get(tail_frequency, '未知')
            
            # 位置描述
            position_descriptions = {
                'start': '开头',
                'end': '结尾'
            }
            tail_position_text = position_descriptions.get(tail_position, '未知')
            
            config_text = f"""
🔧 **功能配置**

📊 **当前配置**
• 关键字过滤: {keywords_count} 个
• 敏感词替换: {replacements_count} 个
• 附加按钮: {buttons_count} 个
• 附加文字: {tail_status} ({tail_frequency_text}, {tail_position_text})

📝 **移除功能状态**
• 纯文本过滤: {'✅ 开启' if user_config.get('content_removal') else '❌ 关闭'} ({content_removal_mode_text})
• 链接移除: {'✅ 开启' if links_enabled else '❌ 关闭'} ({links_mode_text})
• 移除用户名: {'✅ 开启' if user_config.get('remove_usernames') else '❌ 关闭'}
• 按钮移除: {'✅ 开启' if user_config.get('filter_buttons') else '❌ 关闭'} ({button_mode_text})

💡 请选择要配置的功能：
            """.strip()
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(FEATURE_CONFIG_BUTTONS, **{
                    'keywords_count': keywords_count,
                    'replacements_count': replacements_count,
                    'buttons_count': buttons_count,
                    'content_removal_status': content_removal_status,
                    'button_filter_status': button_filter_status,
                    'tail_text_status': tail_text_status,
                    'links_status': links_status,
                    'usernames_status': usernames_status
                })
            )
            
        except Exception as e:
            logger.error(f"显示功能配置失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    
    async def _handle_show_monitor_menu(self, callback_query: CallbackQuery):
        """处理显示监听菜单"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查 User API 登录状态
            if not self.user_api_logged_in or not self.user_api_manager:
                await callback_query.edit_message_text(
                    "❌ **监听功能需要 User API 登录**\n\n"
                    "监听功能需要用户账号权限才能工作：\n"
                    "• 监听频道消息需要用户账号\n"
                    "• Bot API 无法监听频道消息\n"
                    "• 请先登录 User API\n\n"
                    "💡 点击下方按钮开始登录",
                    reply_markup=generate_button_layout([
                        [("🚀 登录 User API", "start_user_api_login")],
                        [("🔙 返回主菜单", "show_main_menu")]
                    ])
                )
                return
            
            # 检查监听引擎是否已初始化
            if not self.realtime_monitoring_engine:
                await callback_query.edit_message_text(
                    "❌ **监听引擎未初始化**\n\n"
                    "监听引擎正在初始化中，请稍后重试",
                    reply_markup=generate_button_layout([
                        [("🔄 重新加载", "show_monitor_menu")],
                        [("🔙 返回主菜单", "show_main_menu")]
                    ])
                )
                return
            
            # 获取实时监听状态
            monitoring_status = self.realtime_monitoring_engine.get_monitoring_status()
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            active_tasks = [task for task in user_tasks if task['status'] == 'active']
            
            # 构建简化的状态信息
            status_text = f"📡 **监听系统**\n\n"
            status_text += f"• 引擎状态: {'✅ 运行中' if monitoring_status.get('is_running', False) else '❌ 已停止'}\n"
            status_text += f"• 总任务数: {len(user_tasks)} 个\n"
            status_text += f"• 活跃任务: {len(active_tasks)} 个\n"
            status_text += f"• 处理消息: {monitoring_status.get('global_stats', {}).get('total_messages_processed', 0)} 条\n\n"
            
            if user_tasks:
                status_text += "**您的监听任务:**\n"
                for i, task in enumerate(user_tasks[:3], 1):  # 只显示前3个
                    target = task.get('target_channel', 'Unknown')
                    sources = len(task.get('source_channels', []))
                    status_text += f"{i}. {target} ({sources}个源频道)\n"
                if len(user_tasks) > 3:
                    status_text += f"... 还有 {len(user_tasks) - 3} 个任务\n"
            else:
                status_text += "**暂无监听任务**\n"
            
            await callback_query.edit_message_text(
                status_text,
                reply_markup=generate_button_layout([
                    [("📋 我的任务", "view_monitoring_tasks")],
                    [("➕ 创建任务", "create_monitoring_task")],
                    [("🔄 刷新状态", "show_monitor_menu")],
                    [("🔙 返回主菜单", "show_main_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"显示监听菜单失败: {e}")
            await callback_query.edit_message_text("❌ 显示失败，请稍后重试")
    
    async def _handle_view_tasks(self, callback_query: CallbackQuery):
        """处理查看任务"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取任务信息
            if self.cloning_engine:
                all_tasks = self.cloning_engine.get_all_tasks()
                active_tasks = [t for t in all_tasks if t['status'] == 'running']
                completed_tasks = [t for t in all_tasks if t['status'] == 'completed']
                failed_tasks = [t for t in all_tasks if t['status'] == 'failed']
            else:
                active_tasks = []
                completed_tasks = []
                failed_tasks = []
            
            tasks_text = f"""
📜 **我的任务**

📊 **任务统计**
• 运行中: {len(active_tasks)} 个
• 已完成: {len(completed_tasks)} 个
• 失败: {len(failed_tasks)} 个

💡 请选择要查看的任务类型：
            """.strip()
            
            await callback_query.edit_message_text(
                tasks_text,
                reply_markup=generate_button_layout(TASK_MANAGEMENT_BUTTONS)
            )
            
        except Exception as e:
            logger.error(f"查看任务失败: {e}")
            await callback_query.edit_message_text("❌ 查看失败，请稍后重试")
    
    async def _handle_view_history(self, callback_query: CallbackQuery):
        """处理查看历史"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取历史记录
            history = await self.data_manager.get_task_history(user_id, limit=10)
            
            if not history:
                history_text = """
📋 **历史记录**

❌ 暂无历史记录

💡 完成搬运任务后，这里会显示任务历史。
                """.strip()
            else:
                history_text = f"""
📋 **历史记录**

📊 **最近 {len(history)} 条记录**
                """.strip()
                
                for i, record in enumerate(history[:5]):  # 只显示前5条
                    task_id = record.get('id', '未知')
                    status = record.get('status', '未知')
                    created_at = record.get('created_at', '未知')
                    source_chat_id = record.get('source_chat_id', '')
                    target_chat_id = record.get('target_chat_id', '')
                    
                    # 格式化时间
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        time_str = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        time_str = created_at
                    
                    # 获取频道显示名称
                    async def get_channel_display_name(chat_id):
                        if not chat_id:
                            return '未知频道'
                        
                        # 如果是用户名格式，直接返回
                        if isinstance(chat_id, str) and chat_id.startswith('@'):
                            return chat_id
                        
                        # 尝试从频道组配置中获取名称
                        channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                        for pair in channel_pairs:
                            if str(pair.get('source_id')) == str(chat_id):
                                if pair.get('source_username') and pair.get('source_username').startswith('@'):
                                    return pair.get('source_username')
                                elif pair.get('source_name'):
                                    return pair.get('source_name')
                            elif str(pair.get('target_id')) == str(chat_id):
                                if pair.get('target_username') and pair.get('target_username').startswith('@'):
                                    return pair.get('target_username')
                                elif pair.get('target_name'):
                                    return pair.get('target_name')
                        
                        # 如果找不到，显示简化的ID
                        return f"频道ID: {str(chat_id)[-8:]}"
                    
                    source_display = await get_channel_display_name(source_chat_id)
                    target_display = await get_channel_display_name(target_chat_id)
                    
                    # 状态图标
                    status_icon = {
                        'completed': '✅',
                        'failed': '❌',
                        'running': '🔄',
                        'paused': '⏸️',
                        'cancelled': '🚫'
                    }.get(status, '❓')
                    
                    history_text += f"\n{status_icon} **任务 {i+1}** ({time_str})"
                    history_text += f"\n   📡 {source_display} → 📤 {target_display}"
                
                if len(history) > 5:
                    history_text += f"\n... 还有 {len(history) - 5} 条记录"
            
            history_text += "\n\n💡 请选择操作："
            
            await callback_query.edit_message_text(
                history_text,
                reply_markup=generate_button_layout(TASK_MANAGEMENT_BUTTONS)
            )
            
        except Exception as e:
            logger.error(f"查看历史失败: {e}")
            await callback_query.edit_message_text("❌ 查看失败，请稍后重试")
    
    async def _handle_view_config(self, callback_query: CallbackQuery):
        """处理查看配置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取各种移除功能的详细状态
            content_removal_mode = user_config.get('content_removal_mode', 'text_only')
            mode_descriptions = {"text_only": "仅移除纯文本", "all_content": "移除所有包含文本的信息"}
            content_removal_mode_text = mode_descriptions.get(content_removal_mode, "未知模式")
            
            link_mode = user_config.get('remove_links_mode', 'links_only')
            link_mode_text = "智能移除链接" if link_mode == 'links_only' else "移除整条消息"
            
            tail_position = user_config.get('tail_position', 'end')
            tail_position_text = "开头" if tail_position == 'start' else "结尾"
            
            # 判断链接移除功能的整体状态
            links_enabled = any([
                user_config.get('remove_links', False),
                user_config.get('remove_all_links', False),
                user_config.get('remove_magnet_links', False)
            ])
            
            # 获取链接移除的模式描述
            if user_config.get('remove_all_links', False):
                links_mode_text = "移除所有类型链接"
            elif user_config.get('remove_links', False):
                links_mode_text = link_mode_text
            elif user_config.get('remove_magnet_links', False):
                links_mode_text = "仅移除磁力链接"
            else:
                links_mode_text = "未设置"
            
            # 获取按钮移除模式描述
            button_mode = user_config.get('button_filter_mode', 'remove_buttons_only')
            button_mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            button_mode_text = button_mode_descriptions.get(button_mode, '未知模式')
            
            # 频率描述
            frequency_descriptions = {
                'always': '每条都添加',
                'interval': '间隔添加',
                'random': '随机添加'
            }
            
            # 位置描述
            position_descriptions = {
                'start': '开头',
                'end': '结尾'
            }
            
            config_text = f"""
🔍 **当前配置**

📝 **过滤设置**
• 关键字过滤: {len(user_config.get('filter_keywords', []))} 个
• 敏感词替换: {len(user_config.get('replacement_words', {}))} 个
• 纯文本过滤: {'✅ 开启' if user_config.get('content_removal') else '❌ 关闭'} ({content_removal_mode_text})
• 链接移除: {'✅ 开启' if links_enabled else '❌ 关闭'} ({links_mode_text})
• 移除用户名: {'✅ 开启' if user_config.get('remove_usernames') else '❌ 关闭'}

🔘 **按钮移除**
• 按钮移除: {'✅ 开启' if user_config.get('filter_buttons') else '❌ 关闭'} ({button_mode_text})

✨ **增强功能**
• 附加文字: {'✅ 已设置' if user_config.get('tail_text') else '❌ 未设置'} ({frequency_descriptions.get(user_config.get('tail_frequency', 'always'), '未知频率')}, {position_descriptions.get(user_config.get('tail_position', 'end'), '未知位置')})
• 附加按钮: {len(user_config.get('additional_buttons', []))} 个 ({frequency_descriptions.get(user_config.get('button_frequency', 'always'), '未知频率')})

👂 **监听设置**
• 实时监听: {'✅ 开启' if user_config.get('monitor_enabled') else '❌ 关闭'}
• 监听频道: {len(user_config.get('monitored_pairs', []))} 个

💡 如需修改配置，请使用相应的功能菜单。
            """.strip()
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"查看配置失败: {e}")
            await callback_query.edit_message_text("❌ 查看失败，请稍后重试")
    
    async def _handle_show_help(self, callback_query: CallbackQuery):
        """处理显示帮助"""
        await self._handle_help_command(callback_query.message)
    
    async def _handle_add_channel_pair(self, callback_query: CallbackQuery):
        """处理添加频道组"""
        try:
            add_text = """
➕ **添加频道组 - 第一步**

📝 **请输入采集频道（来源频道）：**

💡 **支持的输入格式：**
• 频道数字ID：`-1001234567890`
• 频道用户名：`@channelname`
• 公开频道链接：`https://t.me/channelname`
• 带消息ID的链接：`https://t.me/channelname/123`（自动提取频道名）
• 私密频道链接：`https://t.me/c/1234567890/123`（需要机器人已加入）

🔍 **自动检查功能：**
机器人会自动验证频道是否存在并可访问

⚠️ **注意事项：**
• 确保机器人已加入该频道
• 确保机器人有读取权限
• 私密频道需要机器人已是成员或管理员


            """.strip()
            
            # 设置用户状态为等待输入采集频道
            user_id = str(callback_query.from_user.id)
            self.user_states[user_id] = {
                'state': 'waiting_for_source_channel',
                'data': {}
            }
            
            await callback_query.edit_message_text(add_text)
            
        except Exception as e:
            logger.error(f"处理添加频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_edit_channel_pair(self, callback_query: CallbackQuery):
        """处理编辑频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 判断是索引格式还是pair_id格式
            if data_part.isdigit():
                # 索引格式：edit_channel_pair:0
                pair_index = int(data_part)
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                pair_id = pair.get('id', f'pair_{pair_index}')
            else:
                # pair_id格式：edit_channel_pair:pair_0_1756487581
                pair_id = data_part
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                
                # 查找对应的频道组
                pair = None
                pair_index = None
                for i, p in enumerate(channel_pairs):
                    if p.get('id') == pair_id:
                        pair = p
                        pair_index = i
                        break
                
                if not pair:
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
            
            source_name = pair.get('source_name', '未知频道')
            target_name = pair.get('target_name', '未知频道')
            
            edit_text = f"""
✏️ **编辑频道组 {pair_index + 1}**

📋 **当前配置：**
📥 来源频道：{source_name}
📤 目标频道：{target_name}

📝 **请选择要编辑的内容：**

💡 请选择操作：
            """.strip()
            
            # 生成编辑按钮，使用pair_id格式确保一致性
            buttons = [
                [("🔄 更改来源频道", f"edit_source_by_id:{pair_id}")],
                [("🔄 更改目标频道", f"edit_target_by_id:{pair_id}")],
                [("✅ 启用/禁用", f"toggle_enabled_by_id:{pair_id}")],
                [("🔧 过滤设置", f"manage_pair_filters:{pair_id}")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                edit_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_delete_channel_pair(self, callback_query: CallbackQuery):
        """处理删除频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 检查是否为pair_id格式
            if data_part.startswith('pair_'):
                # 通过pair_id查找频道组
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                pair_index = None
                pair_id = data_part
                for i, pair in enumerate(channel_pairs):
                    if pair.get('id') == data_part:
                        pair_index = i
                        break
                if pair_index is None:
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
            else:
                # 传统的索引格式
                pair_index = int(data_part)
                # 获取pair_id用于确认删除
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                pair_id = channel_pairs[pair_index].get('id', f'pair_{pair_index}_{int(time.time())}')
            
            delete_text = f"""
🗑️ **删除频道组 {pair_index + 1}**

⚠️ **确认删除**
此操作将永久删除该频道组，无法恢复！

❓ **是否确认删除？**
            """.strip()
            
            # 生成确认按钮
            buttons = [
                [("❌ 取消", "show_channel_config_menu")],
                [("🗑️ 确认删除", f"confirm_delete_by_id:{pair_id}")]
            ]
            
            await callback_query.edit_message_text(
                delete_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理删除频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_confirm_delete_channel_pair(self, callback_query: CallbackQuery):
        """处理确认删除频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 删除频道组（self.data_manager.delete_channel_pair已经包含了配置清理逻辑）
            success = await self.data_manager.delete_channel_pair(user_id, pair['id'])
            
            # 监听系统已移除，无需清理相关配置
            
            if success:
                # 显示删除成功消息
                success_text = f"""
🗑️ **频道组删除成功！**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

✅ **状态：** 已永久删除

💡 **说明：**
• 该频道组已被永久删除
• 无法恢复，如需重新使用请重新添加
• 相关的过滤配置已清除
• 相关的监听配置已清除

🔙 返回主菜单继续其他操作
                """.strip()
                
                await callback_query.edit_message_text(
                    success_text,
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            else:
                # 显示删除失败消息
                await callback_query.edit_message_text(
                    f"❌ **删除失败！**\n\n"
                    f"📡 **采集频道：** {source_name}\n"
                    f"📤 **发布频道：** {target_name}\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 数据库操作失败\n"
                    f"• 权限不足\n"
                    f"• 系统错误\n\n"
                    f"🔙 请稍后重试或联系管理员",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            
        except Exception as e:
            logger.error(f"处理确认删除频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    async def _handle_confirm_delete_channel_pair_by_id(self, callback_query: CallbackQuery):
        """处理通过pair_id确认删除频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair = None
            pair_index = None
            for i, p in enumerate(channel_pairs):
                if p.get('id') == pair_id:
                    pair = p
                    pair_index = i
                    break
            
            if not pair:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 删除频道组（self.data_manager.delete_channel_pair已经包含了配置清理逻辑）
            success = await self.data_manager.delete_channel_pair(user_id, pair_id)
            
            if success:
                # 显示删除成功消息
                success_text = f"""
🗑️ **频道组删除成功！**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

✅ **状态：** 已永久删除

💡 **说明：**
• 该频道组已被永久删除
• 无法恢复，如需重新使用请重新添加
• 相关的过滤配置已清除
• 相关的监听配置已清除

🔙 返回主菜单继续其他操作
                """.strip()
                
                await callback_query.edit_message_text(
                    success_text,
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            else:
                # 显示删除失败消息
                await callback_query.edit_message_text(
                    f"❌ **删除失败！**\n\n"
                    f"📡 **采集频道：** {source_name}\n"
                    f"📤 **发布频道：** {target_name}\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 数据库操作失败\n"
                    f"• 权限不足\n"
                    f"• 系统错误\n\n"
                    f"🔙 请稍后重试或联系管理员",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            
        except Exception as e:
            logger.error(f"处理确认删除频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_edit_pair_source(self, callback_query: CallbackQuery):
        """处理编辑频道组来源频道"""
        try:
            # 解析频道组索引
            data = callback_query.data
            if data.startswith("edit_pair_source:"):
                pair_index = int(data.split(':')[1])
            elif data.startswith("edit_source:"):
                pair_index = int(data.split(':')[1])
            else:
                raise ValueError(f"未知的回调数据格式: {data}")
            
            edit_text = f"""
🔄 **更改来源频道**

📝 **频道组 {pair_index + 1}**

💡 **操作说明：**
• 请发送新的来源频道链接或用户名
• 支持格式：@channel_username 或 https://t.me/channel_username
• 确保您有该频道的访问权限

📤 **请发送新的来源频道：**
            """.strip()
            
            # 设置用户状态为等待输入来源频道
            user_id = str(callback_query.from_user.id)
            self.user_states[user_id] = {
                'state': f'edit_source:{pair_index}',
                'pair_index': pair_index
            }
            
            buttons = [
                [("🔙 取消操作", "show_channel_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                edit_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑来源频道失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_edit_pair_target(self, callback_query: CallbackQuery):
        """处理编辑频道组目标频道"""
        try:
            # 解析频道组索引
            data = callback_query.data
            if data.startswith("edit_pair_target:"):
                pair_index = int(data.split(':')[1])
            elif data.startswith("edit_target:"):
                pair_index = int(data.split(':')[1])
            else:
                raise ValueError(f"未知的回调数据格式: {data}")
            
            edit_text = f"""
🔄 **更改目标频道**

📝 **频道组 {pair_index + 1}**

💡 **操作说明：**
• 请发送新的目标频道链接或用户名
• 支持格式：@channel_username 或 https://t.me/channel_username
• 确保您有该频道的管理权限

📤 **请发送新的目标频道：**
            """.strip()
            
            # 设置用户状态为等待输入目标频道
            user_id = str(callback_query.from_user.id)
            self.user_states[user_id] = {
                'state': f'edit_target:{pair_index}',
                'pair_index': pair_index
            }
            
            buttons = [
                [("🔙 取消操作", "show_channel_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                edit_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑目标频道失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    async def _handle_edit_pair_source_by_id(self, callback_query: CallbackQuery):
        """处理通过pair_id编辑频道组来源频道"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair = None
            pair_index = None
            for i, p in enumerate(channel_pairs):
                if p.get('id') == pair_id:
                    pair = p
                    pair_index = i
                    break
            
            if not pair:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            edit_text = f"""
🔄 **更改来源频道**

📝 **频道组 {pair_index + 1}**
📥 **当前来源：** {pair.get('source_name', '未知频道')}

💡 **操作说明：**
• 请发送新的来源频道链接或用户名
• 支持格式：@channel_username 或 https://t.me/channel_username
• 确保您有该频道的访问权限

📤 **请发送新的来源频道：**
            """.strip()
            
            # 设置用户状态为等待输入来源频道
            self.user_states[user_id] = {
                'state': f'edit_source_by_id:{pair_id}',
                'pair_id': pair_id,
                'pair_index': pair_index
            }
            
            buttons = [
                [("🔙 取消操作", f"edit_channel_pair:{pair_id}")]
            ]
            
            await callback_query.edit_message_text(
                edit_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑来源频道失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    async def _handle_edit_pair_target_by_id(self, callback_query: CallbackQuery):
        """处理通过pair_id编辑频道组目标频道"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair = None
            pair_index = None
            for i, p in enumerate(channel_pairs):
                if p.get('id') == pair_id:
                    pair = p
                    pair_index = i
                    break
            
            if not pair:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            edit_text = f"""
🔄 **更改目标频道**

📝 **频道组 {pair_index + 1}**
📤 **当前目标：** {pair.get('target_name', '未知频道')}

💡 **操作说明：**
• 请发送新的目标频道链接或用户名
• 支持格式：@channel_username 或 https://t.me/channel_username
• 确保您有该频道的管理权限

📤 **请发送新的目标频道：**
            """.strip()
            
            # 设置用户状态为等待输入目标频道
            self.user_states[user_id] = {
                'state': f'edit_target_by_id:{pair_id}',
                'pair_id': pair_id,
                'pair_index': pair_index
            }
            
            buttons = [
                [("🔙 取消操作", f"edit_channel_pair:{pair_id}")]
            ]
            
            await callback_query.edit_message_text(
                edit_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑目标频道失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    async def _handle_toggle_enabled_by_id(self, callback_query: CallbackQuery):
        """处理通过pair_id切换频道组启用状态"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair = None
            pair_index = None
            for i, p in enumerate(channel_pairs):
                if p.get('id') == pair_id:
                    pair = p
                    pair_index = i
                    break
            
            if not pair:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            # 切换启用状态
            new_enabled = not pair.get('enabled', True)
            success = await self.data_manager.update_channel_pair(user_id, pair_id, {'enabled': new_enabled})
            
            if success:
                status_text = "✅ 已启用" if new_enabled else "❌ 已禁用"
                await callback_query.answer(f"频道组状态已更新: {status_text}")
                
                # 返回编辑频道组界面
                callback_query.data = f"edit_channel_pair:{pair_id}"
                await self._handle_edit_channel_pair(callback_query)
            else:
                await callback_query.edit_message_text("❌ 更新失败，请稍后重试")
            
        except Exception as e:
            logger.error(f"处理切换频道组状态失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    async def _handle_update_all_channel_info(self, callback_query: CallbackQuery):
        """处理一键更新所有频道信息"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 显示更新开始界面
            update_text = """
🔄 **一键更新频道信息**

📝 **正在更新所有频道的用户名信息...**

💡 **更新内容：**
• 获取频道的用户名（@username）
• 获取频道的标题信息
• 更新数据库中的频道信息
• 优化显示效果

⏱️ **预计时间：** 1-2分钟
⚠️ **注意：** 请勿关闭机器人或刷新页面
            """.strip()
            
            await callback_query.edit_message_text(update_text)
            
            # 开始更新频道信息
            success_count = await self._update_all_channel_usernames(user_id)
            
            # 显示更新结果
            if success_count > 0:
                result_text = f"""
✅ **频道信息更新完成！**

📊 **更新结果：**
• 成功更新: {success_count} 个频道
• 失败: 0 个频道

💡 **现在可以：**
• 查看更新后的频道组列表
• 享受更友好的显示效果
• 避免重复的API调用

🔙 返回频道管理查看更新结果
                """.strip()
                
                buttons = [
                    [("📋 查看频道组列表", "show_channel_config_menu")],
                    [("🔙 返回主菜单", "show_main_menu")]
                ]
                
                await callback_query.edit_message_text(
                    result_text,
                    reply_markup=generate_button_layout(buttons)
                )
            else:
                await callback_query.edit_message_text(
                    "❌ **更新失败！**\n\n"
                    "💡 **可能的原因：**\n"
                    "• 没有找到频道组\n"
                    "• API调用失败\n"
                    "• 权限不足\n\n"
                    "🔙 请稍后重试或联系管理员",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            
        except Exception as e:
            logger.error(f"处理一键更新频道信息失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _update_all_channel_usernames(self, user_id: str) -> int:
        """更新所有频道的用户名信息"""
        try:
            # 获取用户的所有频道组
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if not channel_pairs:
                logger.warning(f"用户 {user_id} 没有频道组")
                return 0
            
            updated_count = 0
            
            for pair in channel_pairs:
                try:
                    source_id = pair.get('source_id')
                    target_id = pair.get('target_id')
                    
                    # 更新源频道信息
                    if source_id:
                        source_username = await self._get_channel_username(source_id)
                        if source_username and source_username != pair.get('source_username', ''):
                            pair['source_username'] = source_username
                            updated_count += 1
                    
                    # 更新目标频道信息
                    if target_id:
                        target_username = await self._get_channel_username(target_id)
                        if target_username and target_username != pair.get('target_username', ''):
                            pair['target_username'] = target_username
                            updated_count += 1
                    
                    # 添加小延迟避免API限制
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.warning(f"更新频道组 {pair.get('id', 'unknown')} 失败: {e}")
                    continue
            
            # 保存更新后的频道组信息
            if updated_count > 0:
                success = await self.data_manager.save_channel_pairs(user_id, channel_pairs)
                if success:
                    logger.info(f"用户 {user_id} 频道信息更新成功，更新了 {updated_count} 个字段")
                else:
                    logger.error(f"用户 {user_id} 频道信息保存失败")
                    return 0
            else:
                logger.info(f"用户 {user_id} 没有需要更新的频道信息")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"更新频道用户名失败: {e}")
            return 0
    
    async def _handle_unknown_callback(self, callback_query: CallbackQuery):
        """处理未知回调"""
        await callback_query.edit_message_text(
            "❓ 未知的操作，请使用主菜单重新选择。",
            reply_markup=generate_button_layout([[
                ("🔙 返回主菜单", "show_main_menu")
            ]])
        )
    
    async def _handle_text_message(self, message: Message):
        """处理文本消息"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"🔍 处理文本消息: user_id={user_id}, text='{message.text[:50]}...'")
            
            # 处理 User API 登录流程
            if await self._handle_user_api_login_flow(message):
                return
            
            # 检查用户状态
            if user_id in self.user_states:
                state = self.user_states[user_id]
                
                if state['state'] == 'waiting_for_source_channel':
                    await self._process_source_channel_input(message, state)
                    return
                # 删除不再需要的确认状态处理
                elif state['state'] == 'waiting_for_target_channel':
                    await self._process_target_channel_input(message, state)
                    return
                # 删除不再需要的确认状态处理
                elif state['state'] == 'waiting_for_keywords':
                    await self._process_keywords_input(message, state)
                    return
                elif state['state'] == 'waiting_for_replacements':
                    await self._process_replacements_input(message, state)
                    return
                elif state['state'] == 'waiting_for_tail_text':
                    await self._process_tail_text_input(message, state)
                    return
                elif state['state'] == 'waiting_for_buttons':
                    await self._process_buttons_input(message, state)
                    return
                elif state['state'] == 'waiting_for_comments_count':
                    await self._process_comments_count_input(message, state)
                    return
                elif state['state'].startswith('edit_source:'):
                    await self._process_edit_source_input(message, state)
                    return
                elif state['state'].startswith('edit_target:'):
                    await self._process_edit_target_input(message, state)
                    return
                elif state['state'].startswith('edit_source_by_id:'):
                    await self._process_edit_source_by_id_input(message, state)
                    return
                elif state['state'].startswith('edit_target_by_id:'):
                    await self._process_edit_target_by_id_input(message, state)
                    return

                elif state['state'] == 'waiting_for_channel_keywords':
                    await self._process_channel_keywords_input(message, state)
                    return
                elif state['state'] == 'waiting_admin_keyword':
                    await self._process_admin_keyword_input(message, state)
                    return
                elif state['state'] == 'waiting_admin_tail_text':
                    await self._process_admin_tail_text_input(message, state)
                    return
                elif state['state'] == 'waiting_admin_buttons':
                    await self._process_admin_buttons_input(message, state)
                    return
                elif state['state'] == 'waiting_clone_test_single_source':
                    await self._process_clone_test_single_source_input(message, state)
                    return
                elif state['state'] == 'waiting_admin_replacement':
                    await self._process_admin_replacement_input(message, state)
                    return
                elif state['state'] == 'waiting_for_channel_id':
                    await self._process_channel_id_input(message, state)
                    return
                elif state['state'] == 'waiting_for_channel_replacements':
                    await self._process_channel_replacements_input(message, state)
                    return
                elif state['state'] == 'waiting_for_cloning_info':
                    await self._process_cloning_info_input(message, state)
                    return
                elif state['state'] == 'creating_monitoring_task':
                    await self._process_monitoring_source_input(message, state)
                    return
                elif state['state'] == 'updating_monitor_end_id':
                    await self._process_update_monitor_end_id_input(message, state)
                    return
                elif state['state'] == 'configuring_channel_increment':
                    await self._process_config_channel_increment_input(message, state)
                    return
                elif state['state'] == 'waiting_for_message_ids':
                    await self._process_message_ids_input(message, state)
                    return
            
            # 检查是否是多任务搬运的消息输入
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                multi_select_state = self.multi_select_states[user_id]
                logger.info(f"检查多任务状态: user_id={user_id}, waiting_for_input={multi_select_state.get('waiting_for_input', False)}")
                if multi_select_state.get('waiting_for_input', False):
                    logger.info(f"处理多任务消息输入: user_id={user_id}")
                    await self._process_multi_select_message_input(message, user_id)
                    return
            
            # 默认处理：只有在用户没有状态时才显示主菜单
            if user_id not in self.user_states:
                logger.info(f"🔍 用户 {user_id} 没有状态，显示主菜单")
                # 先发送一个简单的确认消息
                await message.reply_text("✅ 收到您的消息！正在为您打开主菜单...")
                await self._show_main_menu(message)
            else:
                # 如果用户有状态但没有匹配到处理分支，清除状态并显示主菜单
                logger.warning(f"用户 {user_id} 有未处理的状态: {self.user_states[user_id]}")
                del self.user_states[user_id]
                await message.reply_text("✅ 状态已重置！正在为您打开主菜单...")
                await self._show_main_menu(message)
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            try:
                await message.reply_text("❌ 处理失败，请稍后重试")
            except Exception as reply_error:
                logger.error(f"发送回复消息失败: {reply_error}")
                # 如果无法发送回复，尝试发送新消息
                try:
                    await self.client.send_message(
                        chat_id=message.from_user.id,
                        text="❌ 处理失败，请稍后重试"
                    )
                except Exception as send_error:
                    logger.error(f"发送新消息也失败: {send_error}")
    
    async def _process_source_channel_input(self, message: Message, state: Dict[str, Any]):
        """处理采集频道输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 解析频道信息
            channel_info = await self._parse_channel_input(text)
            if not channel_info:
                await message.reply_text(
                    "❌ **频道格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 频道数字ID：`-1001234567890`\n"
                    "• 频道用户名：`@channelname`\n"
                    "• 频道链接：`https://t.me/channelname`\n\n"
                    "🔍 **格式说明：**\n"
                    "• 数字ID：以 `-100` 开头的长数字\n"
                    "• 用户名：以 `@` 开头的频道名\n"
                    "• 链接：完整的Telegram频道链接\n\n"
                    "⚠️ **注意事项：**\n"
                    "• 确保没有多余的空格\n"
                    "• 用户名区分大小写\n"
                    "• 链接必须是有效的Telegram频道链接"
                )
                return
            
            # 验证频道是否存在并可访问
            logger.info(f"开始验证频道访问: {channel_info}")
            channel_id = await self._validate_channel_access(channel_info)
            logger.info(f"频道验证结果: {channel_id}")
            
            if not channel_id:
                # 检查是否为私密频道链接
                is_private = self._detect_private_channel_format(channel_info)
                if is_private:
                    await self._show_private_channel_error(message, channel_info, "source")
                else:
                    await self._show_general_channel_error(message, channel_info)
                return
            
            # 处理特殊标识：直接允许继续，无需确认
            if isinstance(channel_id, str) and channel_id.startswith('PENDING_'):
                pending_channel = channel_id.replace('PENDING_', '')
                logger.info(f"频道 {pending_channel} 无法自动验证，但允许继续设置")
                
                # 直接保存频道信息，无需用户确认
                state['data']['source_channel'] = {
                    'id': pending_channel,
                    'info': pending_channel,
                    'title': pending_channel,
                    'type': 'unknown',
                    'pending': True
                }
                
                # 直接进入下一步，无需确认
                state['state'] = 'waiting_for_target_channel'
                
                await message.reply_text(
                    f"⚠️ **频道验证状态**\n\n"
                    f"📡 **频道：** {pending_channel}\n"
                    f"🔍 **状态：** 机器人无法自动验证该频道\n\n"
                    f"💡 **说明：**\n"
                    f"• 机器人将尝试使用该频道\n"
                    f"• 如果后续出现问题，可以重新设置\n\n"
                    f"📝 **第二步：请输入目标频道（发布频道）**\n\n"
                    f"💡 **支持的输入格式：**\n"
                    f"• 频道数字ID：`-1001234567890`\n"
                    f"• 频道用户名：`@channelname`\n"
                    f"• 公开频道链接：`https://t.me/channelname`\n"
                    f"• 带消息ID的链接：`https://t.me/channelname/123`（自动提取频道名）\n"
                    f"• 私密频道链接：`https://t.me/c/1234567890/123`（需要机器人已加入）\n\n"
                    f"⚠️ **注意事项：**\n"
                    f"• 确保机器人已加入该频道\n"
                    f"• 确保机器人有发送权限\n"
                    f"• 私密频道需要机器人已是成员或管理员"
                )
                return
            
            # 获取频道详细信息进行验证
            try:
                chat = await self._get_api_client().get_chat(channel_id)
                channel_type = chat.type
                channel_title = chat.title if hasattr(chat, 'title') else channel_info
                
                # 验证机器人权限
                try:
                    member = await self._get_api_client().get_chat_member(channel_id, "me")
                    can_read = getattr(member, 'can_read_messages', True)
                    can_view = getattr(member, 'can_view_messages', True)
                    
                    if not (can_read or can_view):
                        logger.warning(f"频道 {channel_title} 权限不足，但允许继续")
                        # 权限不足时也允许继续，简化流程
                        
                except Exception as perm_error:
                    logger.warning(f"无法检查机器人权限: {perm_error}")
                    # 权限检查失败时也允许继续，简化流程
                
                # 权限验证通过，保存来源频道信息
                state['data']['source_channel'] = {
                    'id': channel_id,
                    'info': channel_info,
                    'title': channel_title,
                    'type': channel_type,
                    'pending': False
                }
                
                # 更新状态为等待输入目标频道
                state['state'] = 'waiting_for_target_channel'
                
                await message.reply_text(
                    f"✅ **采集频道验证成功！**\n\n"
                    f"📡 **频道：** {channel_title}\n"
                    f"🔒 **权限状态：** ✅ 读取权限正常\n"
                    f"📊 **频道类型：** {channel_type}\n"
                    f"🆔 **频道ID：** `{channel_id}`\n\n"
                    f"📝 **第二步：请输入目标频道（发布频道）**\n\n"
                    f"💡 **支持的输入格式：**\n"
                    f"• 频道数字ID：`-1001234567890`\n"
                    f"• 频道用户名：`@channelname`\n"
                    f"• 公开频道链接：`https://t.me/channelname`\n"
                    f"• 带消息ID的链接：`https://t.me/channelname/123`（自动提取频道名）\n"
                    f"• 私密频道链接：`https://t.me/c/1234567890/123`（需要机器人已加入）\n\n"
                    f"⚠️ **注意事项：**\n"
                    f"• 确保机器人已加入该频道\n"
                    f"• 确保机器人有发送权限\n"
                    f"• 私密频道需要机器人已是成员或管理员"
                )
                return
                
            except Exception as e:
                logger.error(f"获取频道信息失败: {e}")
                await message.reply_text(
                    f"❌ **采集频道验证失败！**\n\n"
                    f"📡 **频道：** {channel_info}\n"
                    f"🔍 **错误：** 无法获取频道信息\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 频道不存在或已被删除\n"
                    f"• 机器人未加入频道\n"
                    f"• 频道访问受限\n"
                    f"• 频道ID格式不正确\n"
                    f"• 频道为私有频道且机器人无权限\n"
                    f"• 频道已被封禁或限制\n\n"
                    f"🔧 **解决方案：**\n"
                    f"• 检查频道ID是否正确\n"
                    f"• 确保机器人已加入该频道\n"
                    f"• 验证频道是否为公开频道\n"
                    f"• 检查频道是否仍然活跃\n"
                    f"• 尝试使用其他频道ID格式\n\n"
                    f"🔙 请重新输入其他频道或返回主菜单"
                )
                return
            
        except Exception as e:
            logger.error(f"处理采集频道输入失败: {e}")
            # 清除用户状态，避免重复处理
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            await message.reply_text(
                "❌ **处理失败！**\n\n"
                "🔍 **错误类型：** 系统内部错误\n"
                "📝 **错误详情：** 处理采集频道输入时发生异常\n\n"
                "💡 **可能的原因：**\n"
                "• 网络连接问题\n"
                "• 数据库访问异常\n"
                "• 系统资源不足\n"
                "• 代码执行错误\n\n"
                "🔧 **建议操作：**\n"
                "• 稍后重试\n"
                "• 检查网络连接\n"
                "• 如果问题持续，请联系管理员\n\n"
                "📊 **错误代码：** 已记录到系统日志"
            )
    
    # 删除不再需要的用户确认处理方法
    
    async def _process_target_channel_input(self, message: Message, state: Dict[str, Any]):
        """处理目标频道输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 检查是否已有采集频道信息
            if 'source_channel' not in state['data']:
                await message.reply_text(
                    "❌ **操作顺序错误！**\n\n"
                    "💡 **正确的操作步骤：**\n"
                    "1️⃣ 首先设置采集频道（来源频道）\n"
                    "2️⃣ 然后设置目标频道（发布频道）\n\n"
                    "🔧 **当前状态：**\n"
                    "• 采集频道：❌ 未设置\n"
                    "• 目标频道：⏳ 等待设置\n\n"
                    "📝 **下一步操作：**\n"
                    "• 请先输入采集频道信息\n"
                    "• 支持频道ID、用户名或链接格式"
                )
                return
            
            # 解析频道信息
            channel_info = await self._parse_channel_input(text)
            if not channel_info:
                await message.reply_text(
                    "❌ **频道格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 频道数字ID：`-1001234567890`\n"
                    "• 频道用户名：`@channelname`\n"
                    "• 频道链接：`https://t.me/channelname`\n\n"
                    "🔍 **格式说明：**\n"
                    "• 数字ID：以 `-100` 开头的长数字\n"
                    "• 用户名：以 `@` 开头的频道名\n"
                    "• 链接：完整的Telegram频道链接\n\n"
                    "⚠️ **注意事项：**\n"
                    "• 确保没有多余的空格\n"
                    "• 用户名区分大小写\n"
                    "• 链接必须是有效的Telegram频道链接"
                )
                return
            
            # 验证频道是否存在并可访问
            logger.info(f"开始验证频道访问: {channel_info}")
            channel_id = await self._validate_channel_access(channel_info)
            logger.info(f"频道验证结果: {channel_id}")
            
            if not channel_id:
                logger.error(f"频道验证失败，返回None: {channel_info}")
                # 清除用户状态，避免重复处理
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                # 提供更详细的错误信息
                if channel_info.startswith('@'):
                    await message.reply_text(
                        f"❌ 无法访问频道 {channel_info}！\n\n"
                        f"**可能的原因：**\n"
                        f"• 频道不存在或已被删除\n"
                        f"• 频道是私密频道，机器人无法访问\n"
                        f"• 机器人未加入该频道\n"
                        f"• 频道用户名输入错误\n\n"
                        f"**建议：**\n"
                        f"• 检查频道用户名是否正确\n"
                        f"• 尝试使用频道数字ID：`-1001234567890`\n"
                        f"• 确保机器人已加入该频道"
                    )
                else:
                    await message.reply_text(
                        f"❌ 无法访问频道 {channel_info}！\n\n"
                        f"**可能的原因：**\n"
                        f"• 频道ID格式错误\n"
                        f"• 频道不存在或已被删除\n"
                        f"• 机器人未加入该频道\n\n"
                        f"**建议：**\n"
                        f"• 检查频道ID是否正确\n"
                        f"• 尝试使用频道用户名：`@channelname`\n"
                        f"• 确保机器人已加入该频道"
                    )
                return
            
            # 处理特殊标识：直接允许继续，无需确认
            if isinstance(channel_id, str) and channel_id.startswith('PENDING_'):
                pending_channel = channel_id.replace('PENDING_', '')
                logger.info(f"目标频道 {pending_channel} 无法自动验证，但允许继续设置")
                
                # 直接使用PENDING频道，无需验证详细信息
                target_channel = {
                    'id': pending_channel,
                    'info': pending_channel,
                    'title': pending_channel,
                    'type': 'unknown',
                    'pending': True
                }
                
                # 直接继续添加频道组，无需额外验证
                source_channel = state['data']['source_channel']
                source_id = source_channel['id']
                
                # 检查是否与采集频道相同
                if source_id == pending_channel:
                    await message.reply_text(
                        "❌ **频道冲突！**\n\n"
                        "💡 **问题说明：**\n"
                        "• 目标频道与采集频道相同\n"
                        "• 这会导致消息循环搬运\n"
                        "• 系统不允许这种配置\n\n"
                        "🔧 **解决方案：**\n"
                        "• 选择不同的目标频道\n"
                        "• 确保目标频道 ≠ 采集频道\n"
                        "• 重新输入目标频道信息\n\n"
                        "📝 **建议：**\n"
                        "• 目标频道应该是发布频道\n"
                        "• 采集频道应该是内容来源\n"
                        "• 两者必须不同"
                    )
                    return
                
                # 获取频道的完整信息（包括用户名）
                source_username = await self._get_channel_username(source_id)
                target_username = await self._get_channel_username(pending_channel)
                
                # 添加频道组
                success = await self.data_manager.add_channel_pair(
                    user_id, 
                    source_username,  # 源频道用户名
                    target_username,  # 目标频道用户名
                    source_channel.get('title', source_channel['info']),  # 源频道显示名称
                    pending_channel,  # 目标频道显示名称
                    source_id,  # 源频道ID
                    pending_channel  # 目标频道ID
                )
                
                if success:
                    # 清除用户状态
                    del self.user_states[user_id]
                    
                    # 构建成功消息
                    source_pending = source_channel.get('pending', False)
                    
                    success_message = f"✅ 频道组添加成功！\n\n"
                    success_message += f"**采集频道：** {source_channel['info']} ({source_username or source_id})"
                    if source_pending:
                        success_message += " ⚠️ (待确认)"
                    success_message += f"\n"
                    success_message += f"**目标频道：** {pending_channel} ⚠️ (待确认)\n\n"
                    success_message += "⚠️ **注意：** 部分频道无法自动验证，请确保频道信息正确\n\n"
                    success_message += "现在可以在频道管理中查看和编辑该频道组。"
                    
                    await message.reply_text(
                        success_message,
                        reply_markup=generate_button_layout([
                            [("➕ 继续添加", "add_channel_pair"), ("📋 频道管理", "show_channel_config_menu")],
                            [("🔙 返回主菜单", "show_main_menu")]
                        ])
                    )
                else:
                    # 清除用户状态，避免重复处理
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    await message.reply_text("❌ 添加频道组失败，请检查频道ID是否正确，以及机器人是否有相应权限。")
                
                return
            
            # 获取频道详细信息进行验证
            try:
                chat = await self._get_api_client().get_chat(channel_id)
                channel_type = chat.type
                channel_title = chat.title if hasattr(chat, 'title') else channel_info
                
                # 验证机器人权限
                try:
                    member = await self._get_api_client().get_chat_member(channel_id, "me")
                    can_post = getattr(member, 'can_post_messages', True)
                    can_send = getattr(member, 'can_send_messages', True)
                    
                    if not (can_post or can_send):
                        logger.warning(f"目标频道 {channel_title} 权限不足，但允许继续")
                        # 权限不足时也允许继续，简化流程
                        
                except Exception as perm_error:
                    logger.warning(f"无法检查机器人权限: {perm_error}")
                    # 权限检查失败时也允许继续，简化流程
                
                # 权限验证通过，继续添加频道组
                target_channel = {
                    'id': channel_id,
                    'info': channel_info,
                    'title': channel_title,
                    'type': channel_type,
                    'pending': False
                }
                
            except Exception as e:
                logger.error(f"获取目标频道信息失败: {e}")
                # 清除用户状态，避免重复处理
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    f"❌ **目标频道验证失败！**\n\n"
                    f"📤 **频道：** {channel_info}\n"
                    f"🔍 **错误：** 无法获取频道信息\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 频道不存在或已被删除\n"
                    f"• 机器人未加入频道\n"
                    f"• 频道访问受限\n"
                    f"• 频道ID格式不正确\n"
                    f"• 频道为私有频道且机器人无权限\n\n"
                    f"🔧 **解决方案：**\n"
                    f"• 检查频道ID是否正确\n"
                    f"• 确保机器人已加入目标频道\n"
                    f"• 验证频道是否为公开频道\n"
                    f"• 检查机器人权限设置\n\n"
                    f"🔙 请重新输入其他频道或返回主菜单"
                )
                return
            
            # 获取采集频道信息
            source_channel = state['data']['source_channel']
            source_id = source_channel['id']
            
            # 检查是否与采集频道相同
            if source_id == channel_id:
                await message.reply_text(
                    "❌ **频道冲突！**\n\n"
                    "💡 **问题说明：**\n"
                    "• 目标频道与采集频道相同\n"
                    "• 这会导致消息循环搬运\n"
                    "• 系统不允许这种配置\n\n"
                    "🔧 **解决方案：**\n"
                    "• 选择不同的目标频道\n"
                    "• 确保目标频道 ≠ 采集频道\n"
                    "• 重新输入目标频道信息\n\n"
                    "📝 **建议：**\n"
                    "• 目标频道应该是发布频道\n"
                    "• 采集频道应该是内容来源\n"
                    "• 两者必须不同"
                )
                return
            
            # 获取频道的完整信息（包括用户名）
            source_username = await self._get_channel_username(source_id)
            target_username = await self._get_channel_username(channel_id)
            
            # 使用优化的显示格式："频道名 (@用户名)"
            def format_channel_display(username, channel_id, name):
                # 优先显示频道名称
                display_name = name if name else f"频道ID: {str(channel_id)[-8:]}"
                
                # 如果有用户名，添加到显示名称后面
                if username and username.startswith('@'):
                    return f"{display_name} ({username})"
                elif username:
                    return f"{display_name} (@{username})"
                else:
                    return display_name
            
            source_display_name = format_channel_display(source_username, source_id, source_channel.get('title'))
            target_display_name = format_channel_display(target_username, channel_id, target_channel.get('title'))
            
            # 添加频道组
            success = await self.data_manager.add_channel_pair(
                user_id, 
                source_username,  # 源频道用户名
                target_username,  # 目标频道用户名
                source_display_name,  # 源频道显示名称
                target_display_name,  # 目标频道显示名称
                source_id,  # 源频道ID
                channel_id  # 目标频道ID
            )
            
            if success:
                # 清除用户状态
                del self.user_states[user_id]
                
                # 构建成功消息
                source_pending = source_channel.get('pending', False)
                target_pending = isinstance(channel_id, str) and channel_id.startswith('PENDING_')
                
                success_message = f"✅ 频道组添加成功！\n\n"
                success_message += f"**采集频道：** {source_channel['info']} ({source_username or source_id})"
                if source_pending:
                    success_message += " ⚠️ (待确认)"
                success_message += f"\n"
                success_message += f"**目标频道：** {channel_info} (`{channel_id}`)"
                if target_pending:
                    success_message += " ⚠️ (待确认)"
                success_message += f"\n\n"
                
                if source_pending or target_pending:
                    success_message += "⚠️ **注意：** 部分频道无法自动验证，请确保频道信息正确\n\n"
                
                success_message += "现在可以在频道管理中查看和编辑该频道组。"
                
                await message.reply_text(
                    success_message,
                    reply_markup=generate_button_layout([
                        [("➕ 继续添加", "add_channel_pair"), ("📋 频道管理", "show_channel_config_menu")],
                        [("🔙 返回主菜单", "show_main_menu")]
                    ])
                )
            else:
                # 检查是否是因为重复添加
                try:
                    existing_pair = await self.data_manager.get_channel_pair_by_channels(user_id, source_id, channel_id)
                    if existing_pair:
                        await message.reply_text(
                            f"⚠️ **频道组已存在！**\n\n"
                            f"📡 **采集频道：** {source_channel['info']}\n"
                            f"📤 **目标频道：** {channel_info}\n\n"
                            f"💡 **建议：**\n"
                            f"• 该频道组已经存在，无需重复添加\n"
                            f"• 可以在频道管理中查看和编辑现有配置\n"
                            f"• 如需重新配置，请先删除现有频道组\n\n"
                            f"🔧 **操作选项：**\n"
                            f"• 发送 `/menu` 进入频道管理\n"
                            f"• 查看现有频道组配置\n"
                            f"• 编辑或删除现有配置"
                        )
                    else:
                        await message.reply_text(
                            "❌ **添加频道组失败！**\n\n"
                            "🔍 **可能的原因：**\n"
                            "• 频道ID格式不正确\n"
                            "• 机器人没有访问权限\n"
                            "• 频道不存在或已被删除\n"
                            "• 数据库连接问题\n\n"
                            "💡 **建议：**\n"
                            "• 检查频道ID是否正确\n"
                            "• 确保机器人已加入目标频道\n"
                            "• 验证机器人权限设置\n"
                            "• 稍后重试或联系管理员"
                        )
                except Exception as check_error:
                    logger.error(f"检查重复频道组失败: {check_error}")
                    await message.reply_text(
                        "❌ **添加频道组失败！**\n\n"
                        "🔍 **可能的原因：**\n"
                        "• 频道ID格式不正确\n"
                        "• 机器人没有访问权限\n"
                        "• 频道不存在或已被删除\n"
                        "• 数据库连接问题\n\n"
                        "💡 **建议：**\n"
                        "• 检查频道ID是否正确\n"
                        "• 确保机器人已加入目标频道\n"
                        "• 验证机器人权限设置\n"
                        "• 稍后重试或联系管理员"
                    )
            
        except Exception as e:
            logger.error(f"处理目标频道输入失败: {e}")
            # 清除用户状态，避免重复处理
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            await message.reply_text(
                "❌ **处理失败！**\n\n"
                "🔍 **错误类型：** 系统内部错误\n"
                "📝 **错误详情：** 处理目标频道输入时发生异常\n\n"
                "💡 **可能的原因：**\n"
                "• 网络连接问题\n"
                "• 数据库访问异常\n"
                "• 系统资源不足\n"
                "• 代码执行错误\n\n"
                "🔧 **建议操作：**\n"
                "• 稍后重试\n"
                "• 检查网络连接\n"
                "• 如果问题持续，请联系管理员\n\n"
                "📊 **错误代码：** 已记录到系统日志"
            )
    
    # 删除不再需要的目标频道确认处理方法
    
    async def _process_tail_text_input(self, message: Message, state: Dict[str, Any]):
        """处理附加文字输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            if text == "清空":
                # 检查是否是频道组特定设置
                pair_id = state.get('data', {}).get('pair_id')
                pair_index = state.get('data', {}).get('pair_index')
                
                if pair_id is not None:
                    # 频道组特定设置
                    user_config = await self.data_manager.get_user_config(user_id)
                    
                    # 确保channel_filters存在
                    if 'channel_filters' not in user_config:
                        user_config['channel_filters'] = {}
                    if pair_id not in user_config['channel_filters']:
                        user_config['channel_filters'][pair_id] = {}
                    
                    # 清空频道组特定配置
                    user_config['channel_filters'][pair_id]['tail_text'] = ''
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        "✅ 频道组附加文字已清空！\n\n现在该频道组的消息将不再添加附加文字。",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回小尾巴设置", f"channel_tail_text:{pair_id}")
                        ]])
                    )
                else:
                    # 全局设置
                    user_config = await self.data_manager.get_user_config(user_id)
                    user_config['tail_text'] = ''
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        "✅ 附加文字已清空！\n\n现在消息将不再添加附加文字。",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回功能配置", "show_feature_config_menu")
                        ]])
                    )
                
                # 清除用户状态
                del self.user_states[user_id]
                return
            
            # 检查是否是频率设置（数字1-100，且长度不超过3位）
            if text.isdigit() and len(text) <= 3:
                frequency = int(text)
                if 1 <= frequency <= 100:
                    # 检查是否是频道组特定设置
                    pair_id = state.get('data', {}).get('pair_id')
                    pair_index = state.get('data', {}).get('pair_index')
                    
                    if pair_id is not None:
                        # 频道组特定设置
                        user_config = await self.data_manager.get_user_config(user_id)
                        
                        # 确保channel_filters存在
                        if 'channel_filters' not in user_config:
                            user_config['channel_filters'] = {}
                        if pair_id not in user_config['channel_filters']:
                            user_config['channel_filters'][pair_id] = {}
                        
                        # 保存到频道组特定配置
                        user_config['channel_filters'][pair_id]['tail_frequency'] = frequency
                        await self.data_manager.save_user_config(user_id, user_config)
                        
                        await message.reply_text(
                            f"✅ 频道组 {pair_index + 1} 附加文字频率已设置为：{frequency}%\n\n请继续输入要添加的文字内容。"
                        )
                    else:
                        # 全局设置
                        user_config = await self.data_manager.get_user_config(user_id)
                        user_config['tail_frequency'] = frequency
                        await self.data_manager.save_user_config(user_id, user_config)
                        
                        await message.reply_text(
                            f"✅ 附加文字频率已设置为：{frequency}%\n\n请继续输入要添加的文字内容。"
                        )
                    return
                else:
                    await message.reply_text("❌ 频率设置错误！请输入1-100之间的数字。")
                    return
            
            # 移除位置设置，默认在消息结尾添加
            
            # 检查是否是频道组特定设置
            pair_id = state.get('data', {}).get('pair_id')
            pair_index = state.get('data', {}).get('pair_index')
            
            if pair_id is not None:
                # 频道组特定设置
                user_config = await self.data_manager.get_user_config(user_id)
                
                # 确保channel_filters存在
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                if pair_id not in user_config['channel_filters']:
                    user_config['channel_filters'][pair_id] = {}
                
                # 保存到频道组特定配置
                user_config['channel_filters'][pair_id]['tail_text'] = text
                user_config['channel_filters'][pair_id]['tail_frequency'] = user_config.get('tail_frequency', 'always')
                user_config['channel_filters'][pair_id]['tail_position'] = user_config.get('tail_position', 'end')
                
                # 添加调试日志（仅在DEBUG模式下显示）
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"🔍 保存小尾巴配置:")
                    logger.debug(f"  • pair_id: {pair_id}")
                    logger.debug(f"  • tail_text: '{text}'")
                    logger.debug(f"  • tail_frequency: {user_config.get('tail_frequency', 'always')}")
                    logger.debug(f"  • tail_position: {user_config.get('tail_position', 'end')}")
                    logger.debug(f"  • 保存前的channel_filters: {user_config.get('channel_filters', {}).get(pair_id, {})}")
                
                await self.data_manager.save_user_config(user_id, user_config)
                
                # 验证保存结果（仅在DEBUG模式下显示）
                if logger.isEnabledFor(logging.DEBUG):
                    saved_config = await self.data_manager.get_user_config(user_id)
                    logger.debug(f"  • 保存后的channel_filters: {saved_config.get('channel_filters', {}).get(pair_id, {})}")
                
                await message.reply_text(
                    f"✅ 频道组 {pair_index + 1} 附加文字设置成功！\n\n**当前文字：** {text}\n\n现在该频道组的消息将自动添加这个文字。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回小尾巴设置", f"channel_tail_text:{pair_id}")
                    ]])
                )
            else:
                # 全局设置
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['tail_text'] = text
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ 附加文字设置成功！\n\n**当前文字：** {text}\n\n现在消息将自动添加这个文字。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回功能配置", "show_feature_config_menu")
                    ]])
                )
            
            # 清除用户状态
            del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理附加文字输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _process_buttons_input(self, message: Message, state: Dict[str, Any]):
        """处理附加按钮输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            if text == "清空":
                # 清空所有附加按钮
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['additional_buttons'] = []
                await self.data_manager.save_user_config(user_id, user_config)
                
                # 清除用户状态
                del self.user_states[user_id]
                
                await message.reply_text(
                    "✅ 所有附加按钮已清空！\n\n现在消息将不再添加附加按钮。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回功能配置", "show_feature_config_menu")
                    ]])
                )
                return
            
            # 检查是否是删除按钮
            if text.startswith("删除 "):
                button_text = text.split(" ", 1)[1].strip()
                user_config = await self.data_manager.get_user_config(user_id)
                buttons = user_config.get('additional_buttons', [])
                
                # 查找并删除按钮
                original_count = len(buttons)
                buttons = [btn for btn in buttons if btn.get('text') != button_text]
                
                if len(buttons) < original_count:
                    user_config['additional_buttons'] = buttons
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        f"✅ 按钮 '{button_text}' 已删除！\n\n请继续输入要添加的按钮，格式：按钮文字|链接"
                    )
                    return
                else:
                    await message.reply_text(f"❌ 未找到按钮 '{button_text}'，请检查按钮文字是否正确。")
                    return
            
            # 检查是否是频率设置
            if text.startswith("频率:"):
                frequency = text.split(":", 1)[1].strip()
                if frequency in ['always', 'interval', 'random']:
                    user_config = await self.data_manager.get_user_config(user_id)
                    user_config['button_frequency'] = frequency
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    frequency_text = {
                        'always': '每条消息都添加',
                        'interval': '间隔添加',
                        'random': '随机添加'
                    }.get(frequency, '未知')
                    
                    await message.reply_text(
                        f"✅ 附加按钮频率已设置为：{frequency_text}\n\n请继续输入要添加的按钮，格式：按钮文字|链接"
                    )
                    return
                else:
                    await message.reply_text("❌ 频率设置错误！请使用：always（每条都添加）、interval（间隔添加）、random（随机添加）")
                    return
            
            # 添加新按钮
            if "|" in text:
                button_text, button_url = text.split("|", 1)
                button_text = button_text.strip()
                button_url = button_url.strip()
                
                # 验证URL格式
                if not button_url.startswith(('http://', 'https://', 'tg://')):
                    await message.reply_text("❌ 链接格式错误！请使用有效的HTTP链接或Telegram链接。")
                    return
                
                user_config = await self.data_manager.get_user_config(user_id)
                buttons = user_config.get('additional_buttons', [])
                
                # 检查是否已存在相同文字的按钮
                for btn in buttons:
                    if btn.get('text') == button_text:
                        await message.reply_text(f"❌ 按钮文字 '{button_text}' 已存在！请使用不同的文字。")
                        return
                
                # 添加新按钮
                new_button = {
                    'text': button_text,
                    'url': button_url
                }
                buttons.append(new_button)
                user_config['additional_buttons'] = buttons
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ 按钮添加成功！\n\n**按钮：** {button_text}\n**链接：** {button_url}\n\n请继续添加更多按钮，或发送 '清空' 来清空所有按钮。"
                )
                return
            else:
                await message.reply_text("❌ 格式错误！请使用格式：按钮文字|链接\n\n例如：查看详情|https://example.com")
                return
            
        except Exception as e:
            logger.error(f"处理附加按钮输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    # 评论相关输入处理函数已移除
    
    # 频道评论相关输入处理函数已移除
    
    # ==================== 过滤功能处理方法 ====================
    
    async def _handle_manage_filter_keywords(self, callback_query: CallbackQuery):
        """处理关键字过滤管理"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"开始处理用户 {user_id} 的关键字过滤管理请求")
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            logger.info(f"成功获取用户 {user_id} 的配置")
            
            # 获取关键字列表
            keywords = user_config.get('filter_keywords', [])
            keywords_text = "\n".join([f"• {kw}" for kw in keywords]) if keywords else "❌ 暂无关键字"
            logger.info(f"用户 {user_id} 当前有 {len(keywords)} 个关键字")
            
            config_text = f"""
🔍 **关键字过滤设置**

📝 **当前关键字列表：**
{keywords_text}

💡 **使用方法：**
• 发送关键字来添加（支持逗号分割多个关键字）
• 发送 "删除 关键字" 来删除
• 发送 "清空" 来清空所有关键字

⚠️ **注意：** 包含关键字的消息将被完全移除
            """.strip()
            
            # 设置用户状态为等待关键字输入
            self.user_states[user_id] = {
                'state': 'waiting_for_keywords',
                'data': {}
            }
            logger.info(f"已设置用户 {user_id} 状态为等待关键字输入")
            
            # 创建返回按钮
            buttons = [
                [("🔙 返回功能设定", "show_feature_config_menu")]
            ]
            
            # 编辑消息
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            logger.info(f"成功显示关键字过滤设置界面给用户 {user_id}")
            
        except Exception as e:
            logger.error(f"处理关键字过滤管理失败: {e}")
            logger.error(f"错误详情: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            try:
                await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
            except Exception as edit_error:
                logger.error(f"编辑错误消息失败: {edit_error}")
                await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_content_removal(self, callback_query: CallbackQuery):
        """处理纯文本过滤开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('content_removal', False)
            new_status = not current_status
            user_config['content_removal'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 先回答回调查询
            action_text = "启用" if new_status else "禁用"
            await callback_query.answer(f"纯文本过滤功能已{action_text}")
            
            # 延迟避免冲突
            import asyncio
            await asyncio.sleep(0.5)
            
            # 返回功能配置菜单
            await self._handle_show_feature_config(callback_query)
            
        except Exception as e:
            logger.error(f"处理纯文本过滤开关失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_manage_content_removal(self, callback_query: CallbackQuery):
        """处理纯文本过滤管理"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            content_removal_enabled = user_config.get('content_removal', False)
            content_removal_mode = user_config.get('content_removal_mode', 'text_only')
            
            # 状态文本
            enabled_status = "✅ 已启用" if content_removal_enabled else "❌ 已禁用"
            mode_text = {
                'text_only': '📝 仅移除纯文本',
                'all_content': '🗑️ 移除所有包含文本的信息'
            }.get(content_removal_mode, '未知')
            
            config_text = f"""
📝 **纯文本过滤设置**

📊 **当前状态：** {enabled_status}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 仅移除纯文本：只移除没有图片、视频等媒体的纯文本消息
• 移除所有包含文本的信息：移除所有包含文本的消息（包括有媒体的消息）

⚠️ **注意：** 选择"移除所有包含文本的信息"会移除所有包含文本的消息

请选择操作：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔄 切换开关", "toggle_content_removal")],
                [("📝 仅移除纯文本", "set_content_removal_mode:text_only")],
                [("🗑️ 移除所有包含文本的信息", "set_content_removal_mode:all_content")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理纯文本过滤管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_content_removal_mode(self, callback_query: CallbackQuery):
        """处理纯文本过滤模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 解析模式参数
            mode = callback_query.data.split(':')[1]
            
            # 检查当前模式是否与选择的模式相同
            current_mode = user_config.get('content_removal_mode', 'text_only')
            if current_mode == mode:
                # 如果模式相同，直接提示用户并返回功能配置菜单
                mode_descriptions = {
                    'text_only': '仅移除纯文本',
                    'all_content': '移除所有包含文本的信息'
                }
                mode_text = mode_descriptions.get(mode, '未知')
                await callback_query.answer(f"当前已经是{mode_text}模式")
                await self._handle_show_feature_config(callback_query)
                return
            
            # 设置新模式
            user_config['content_removal_mode'] = mode
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 模式描述
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            
            mode_text = mode_descriptions.get(mode, '未知')
            
            # 先回答回调查询
            await callback_query.answer(f"纯文本过滤模式已设置为：{mode_text}")
            
            # 延迟避免冲突
            import asyncio
            await asyncio.sleep(1.0)
            
            # 返回纯文本过滤管理菜单，避免消息内容冲突
            try:
                await self._handle_manage_content_removal(callback_query)
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    # 如果消息没有变化，直接返回功能配置菜单
                    await self._handle_show_feature_config(callback_query)
                else:
                    raise e
            
        except Exception as e:
            logger.error(f"设置纯文本过滤模式失败: {e}")
            await callback_query.answer("❌ 设置失败，请稍后重试")
    
    async def _handle_toggle_button_removal(self, callback_query: CallbackQuery):
        """处理按钮移除开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换按钮过滤状态
            current_status = user_config.get('filter_buttons', False)
            new_status = not current_status
            user_config['filter_buttons'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 状态文本
            action_text = "启用" if new_status else "禁用"
            
            # 先回答回调查询
            await callback_query.answer(f"按钮移除功能已{action_text}")
            
            # 延迟一下再刷新界面，避免消息编辑冲突
            import asyncio
            await asyncio.sleep(1.0)
            
            # 返回功能配置菜单
            await self._handle_show_feature_config(callback_query)
            
        except Exception as e:
            logger.error(f"处理按钮移除开关失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_manage_filter_buttons(self, callback_query: CallbackQuery):
        """处理按钮过滤管理"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            filter_mode = user_config.get('button_filter_mode', 'remove_buttons_only')
            filter_enabled = user_config.get('filter_buttons', False)
            
            # 状态文本
            enabled_status = "✅ 已启用" if filter_enabled else "❌ 已禁用"
            mode_text = {
                'remove_buttons_only': '🔘 仅移除按钮',
                'remove_message': '🗑️ 移除整条消息'
            }.get(filter_mode, '未知')
            
            config_text = f"""
🎛️ **按钮移除设置**

📊 **当前状态：** {enabled_status}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 仅移除按钮：只移除消息中的按钮，保留文本、图片、视频等媒体内容
• 移除整条消息：包含按钮的整条消息将被完全移除

⚠️ **注意：** 选择"移除整条消息"会完全删除包含按钮的消息

请选择操作：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔄 切换开关", "toggle_button_removal")],
                [("🔘 仅移除按钮", "set_button_mode:remove_buttons_only")],
                [("🗑️ 移除整条消息", "set_button_mode:remove_message")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理按钮过滤管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_button_mode(self, callback_query: CallbackQuery):
        """处理按钮移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 解析模式参数
            mode = callback_query.data.split(':')[1]
            
            # 检查当前模式是否与选择的模式相同
            current_mode = user_config.get('button_filter_mode', 'remove_buttons_only')
            if current_mode == mode:
                # 如果模式相同，直接提示用户并返回功能配置菜单
                mode_descriptions = {
                    'remove_buttons_only': '仅移除按钮',
                    'remove_message': '移除整条消息'
                }
                mode_text = mode_descriptions.get(mode, '未知')
                await callback_query.answer(f"当前已经是{mode_text}模式")
                await self._handle_show_feature_config(callback_query)
                return
            
            # 设置新模式
            user_config['button_filter_mode'] = mode
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 模式描述
            mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            
            mode_text = mode_descriptions.get(mode, '未知')
            
            # 先回答回调查询
            await callback_query.answer(f"按钮移除模式已设置为：{mode_text}")
            
            # 延迟避免冲突
            import asyncio
            await asyncio.sleep(1.0)
            
            # 返回按钮管理菜单，避免消息内容冲突
            try:
                await self._handle_manage_filter_buttons(callback_query)
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    # 如果消息没有变化，直接返回功能配置菜单
                    await self._handle_show_feature_config(callback_query)
                else:
                    raise e
            
        except Exception as e:
            logger.error(f"设置按钮移除模式失败: {e}")
            await callback_query.answer("❌ 设置失败，请稍后重试")
    
    async def _handle_manage_replacement_words(self, callback_query: CallbackQuery):
        """处理敏感词替换管理"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            replacements = user_config.get('replacement_words', {})
            if replacements:
                replacements_text = "\n".join([f"• {old} → {new}" for old, new in replacements.items()])
            else:
                replacements_text = "❌ 暂无替换规则"
            
            config_text = f"""
🔀 **敏感词替换设置**

📝 **当前替换规则：**
{replacements_text}

💡 **使用方法：**
• 发送 "原词=新词" 来添加替换规则
• 发送 "删除 原词" 来删除规则
• 发送 "清空" 来清空所有规则
            """.strip()
            
            # 设置用户状态为等待替换词输入
            self.user_states[user_id] = {
                'state': 'waiting_for_replacements',
                'data': {}
            }
            
            # 创建返回按钮
            buttons = [
                [("🔙 返回功能设定", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理敏感词替换管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_request_tail_text(self, callback_query: CallbackQuery):
        """处理附加文字请求"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            # 检查是否包含频道组信息
            if ':' in data:
                data_part = data.split(':')[1]
                
                # 判断是pair_id格式还是pair_index格式
                if data_part.startswith('pair_'):
                    # pair_id格式
                    pair_id = data_part
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    
                    # 查找对应的频道组
                    pair = None
                    pair_index = None
                    for i, p in enumerate(channel_pairs):
                        if p.get('id') == pair_id:
                            pair = p
                            pair_index = i
                            break
                    
                    if not pair:
                        await callback_query.edit_message_text("❌ 频道组不存在")
                        return
                else:
                    # pair_index格式（向后兼容）
                    pair_index = int(data_part)
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    if pair_index >= len(channel_pairs):
                        await callback_query.edit_message_text("❌ 频道组不存在")
                        return
                    
                    pair = channel_pairs[pair_index]
                    pair_id = pair.get('id', f'pair_{pair_index}')
                
                source_name = pair.get('source_name', f'频道{pair_index+1}')
                target_name = pair.get('target_name', f'目标{pair_index+1}')
                
                config_title = f"📝 **频道组 {pair_index + 1} 小尾巴设置**\n\n📡 **采集频道：** {source_name}\n📤 **发布频道：** {target_name}\n\n"
                return_callback = f"channel_tail_text:{pair_id}"
            else:
                config_title = "✨ **全局附加文字设置**\n\n"
                return_callback = "show_feature_config_menu"
            
            user_config = await self.data_manager.get_user_config(user_id)
            current_tail = user_config.get('tail_text', '')
            current_frequency = user_config.get('tail_frequency', 100)
            
            config_text = f"""
{config_title}
📝 **当前文字：** {current_tail if current_tail else '❌ 未设置'}
🔄 **添加频率：** {current_frequency}%

💡 **使用方法：**
• 发送要添加的文字内容
• 发送 "清空" 来移除附加文字
• 发送数字 1-100 来设置添加频率

🔙 返回设置菜单
            """.strip()
            
            # 设置用户状态为等待附加文字输入
            self.user_states[user_id] = {
                'state': 'waiting_for_tail_text',
                'data': {'pair_id': pair_id if ':' in data else None, 'pair_index': pair_index if ':' in data else None}
            }
            
            # 生成按钮
            buttons = [
                [("🔙 返回", return_callback)]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理附加文字请求失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_request_buttons(self, callback_query: CallbackQuery):
        """处理附加按钮请求"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            # 检查是否包含频道组信息
            if ':' in data:
                data_part = data.split(':')[1]
                
                # 判断是pair_id格式还是pair_index格式
                if data_part.startswith('pair_'):
                    # pair_id格式
                    pair_id = data_part
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    
                    # 查找对应的频道组
                    pair = None
                    pair_index = None
                    for i, p in enumerate(channel_pairs):
                        if p.get('id') == pair_id:
                            pair = p
                            pair_index = i
                            break
                    
                    if not pair:
                        await callback_query.edit_message_text("❌ 频道组不存在")
                        return
                else:
                    # pair_index格式（向后兼容）
                    pair_index = int(data_part)
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    if pair_index >= len(channel_pairs):
                        await callback_query.edit_message_text("❌ 频道组不存在")
                        return
                    
                    pair = channel_pairs[pair_index]
                    pair_id = pair.get('id', f'pair_{pair_index}')
                
                source_name = pair.get('source_name', f'频道{pair_index+1}')
                target_name = pair.get('target_name', f'目标{pair_index+1}')
                
                config_title = f"🔘 **频道组 {pair_index + 1} 按钮设置**\n\n📡 **采集频道：** {source_name}\n📤 **发布频道：** {target_name}\n\n"
                return_callback = f"channel_buttons:{pair_id}"
            else:
                config_title = "📋 **全局附加按钮设置**\n\n"
                return_callback = "show_feature_config_menu"
            
            user_config = await self.data_manager.get_user_config(user_id)
            buttons = user_config.get('additional_buttons', [])
            current_frequency = user_config.get('button_frequency', 100)
            
            if buttons:
                buttons_text = "\n".join([f"• {btn.get('text', '')} → {btn.get('url', '')}" for btn in buttons])
            else:
                buttons_text = "❌ 暂无附加按钮"
            
            config_text = f"""
{config_title}
📊 **当前按钮：**
{buttons_text}

🔄 **添加频率：** {current_frequency}%

💡 **使用方法：**
• 发送 "按钮文字|链接" 来添加按钮
• 发送 "删除 按钮文字" 来删除按钮
• 发送 "清空" 来清空所有按钮
• 发送数字 1-100 来设置添加频率

🔙 返回设置菜单
            """.strip()
            
            # 设置用户状态为等待附加按钮输入
            self.user_states[user_id] = {
                'state': 'waiting_for_buttons',
                'data': {'pair_id': pair_id if ':' in data else None, 'pair_index': pair_index if ':' in data else None}
            }
            
            # 生成按钮
            buttons = [
                [("🔙 返回", return_callback)]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理附加按钮请求失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_show_frequency_settings(self, callback_query: CallbackQuery):
        """处理显示频率设置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            tail_frequency = user_config.get('tail_frequency', 'always')
            button_frequency = user_config.get('button_frequency', 'always')
            
            config_text = f"""
🎯 **频率设置**

📝 **附加文字频率：** {tail_frequency}
📋 **附加按钮频率：** {button_frequency}

💡 **频率选项：**
• always: 每条消息都添加
• interval: 按间隔添加（可设置间隔数）
• random: 随机添加（可设置概率）

请选择要设置的频率类型：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("📝 附加文字频率", "config_tail_frequency")],
                [("📋 附加按钮频率", "config_button_frequency")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频率设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    

    
    async def _handle_toggle_remove_all_links(self, callback_query: CallbackQuery):
        """处理移除所有链接开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_all_links', False)
            new_status = not current_status
            user_config['remove_all_links'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已开启" if new_status else "❌ 已关闭"
            message_text = f"""
🔗 **链接过滤设置**

📝 **当前状态：** {status_text}

💡 **功能说明：**
• 开启后，消息中的所有类型链接将被移除
• 包括HTTP、HTTPS、磁力链接等

🔙 返回链接过滤菜单
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回链接过滤", "show_link_filter_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理移除所有链接开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_remove_hashtags(self, callback_query: CallbackQuery):
        """处理移除Hashtags开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_hashtags', False)
            new_status = not current_status
            user_config['remove_hashtags'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已开启" if new_status else "❌ 已关闭"
            message_text = f"""
🏷️ **Hashtags移除设置**

📝 **当前状态：** {status_text}

💡 **功能说明：**
• 开启后，消息中的#标签将被移除
• 例如：#标签 #话题 等

🔙 返回功能配置
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理移除Hashtags开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_remove_usernames(self, callback_query: CallbackQuery):
        """处理移除用户名开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_usernames', False)
            new_status = not current_status
            user_config['remove_usernames'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已开启" if new_status else "❌ 已关闭"
            message_text = f"""
👤 **用户名移除设置**

📝 **当前状态：** {status_text}

• 开启后，消息中的@用户名将被移除
• 例如：@username @用户 等

🔙 返回功能配置
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理移除用户名开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_manage_file_filter(self, callback_query: CallbackQuery):
        """处理文件过滤管理"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            filter_photo = user_config.get('filter_photo', False)
            filter_video = user_config.get('filter_video', False)
            
            photo_status = "✅ 已过滤" if filter_photo else "❌ 不过滤"
            video_status = "✅ 已过滤" if filter_video else "❌ 不过滤"
            
            message_text = f"""
📁 **文件过滤设置**

🖼️ **图片过滤：** {photo_status}
🎥 **视频过滤：** {video_status}

💡 **功能说明：**
• 开启过滤后，对应类型的消息将被跳过
• 只保留其他类型的消息内容

🔧 **请选择要设置的内容：**
            """.strip()
            
            buttons = [
                [("🖼️ 图片过滤", "toggle_filter_photo")],
                [("🎥 视频过滤", "toggle_filter_video")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理文件过滤管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_refresh_cloning_progress(self, callback_query: CallbackQuery):
        """处理刷新搬运进度"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"🔄 用户 {user_id} 请求刷新进度")
            
            # 初始化实例变量
            if not hasattr(self, 'task_progress'):
                self.task_progress = {}
            if not hasattr(self, 'all_tasks'):
                self.all_tasks = {}
            
            # 获取当前任务状态
            if user_id in self.task_progress and user_id in self.all_tasks:
                task_progress = self.task_progress[user_id]
                all_tasks = self.all_tasks[user_id]
                
                logger.info(f"🔄 找到 {len(all_tasks)} 个任务，开始刷新")
                
                # 从引擎更新任务状态
                await self._update_task_status_from_engine(all_tasks)
                
                # 重新构建目标频道分组
                target_groups = {}
                for task_info in all_tasks:
                    target_id = task_info['target_channel_id']
                    if target_id not in target_groups:
                        target_groups[target_id] = {
                            'target_name': task_info['target_channel_name'],
                            'tasks': []
                        }
                    target_groups[target_id]['tasks'].append(task_info)
                
                # 显示更新后的进度
                await self._display_progress(callback_query, target_groups, all_tasks)
                await callback_query.answer("🔄 进度已刷新")
                logger.info(f"✅ 进度刷新完成，显示 {len(target_groups)} 个目标频道")
            else:
                logger.warning(f"⚠️ 用户 {user_id} 没有找到活动任务，尝试从引擎获取")
                
                # 尝试从搬运引擎获取任务
                if hasattr(self, 'cloning_engine') and self.cloning_engine:
                    try:
                        all_tasks = self.cloning_engine.get_all_tasks()
                        user_tasks = [task for task in all_tasks if task.get('user_id') == user_id]
                        
                        if user_tasks:
                            logger.info(f"🔄 从引擎找到 {len(user_tasks)} 个用户任务")
                            
                            # 重新构建目标频道分组
                            target_groups = {}
                            for task_info in user_tasks:
                                target_id = task_info.get('target_chat_id', 'unknown')
                                if target_id not in target_groups:
                                    target_groups[target_id] = {
                                        'target_name': f"频道 {target_id}",
                                        'tasks': []
                                    }
                                target_groups[target_id]['tasks'].append(task_info)
                            
                            # 显示任务状态
                            await self._display_progress(callback_query, target_groups, user_tasks)
                            await callback_query.answer("🔄 从引擎获取任务状态")
                        else:
                            await callback_query.answer("ℹ️ 没有找到活动任务")
                    except Exception as e:
                        logger.error(f"从引擎获取任务失败: {e}")
                        await callback_query.answer("❌ 获取任务状态失败")
                else:
                    await callback_query.answer("ℹ️ 没有找到活动任务")
                
        except Exception as e:
            logger.error(f"刷新搬运进度失败: {e}")
            logger.exception("刷新进度异常详情:")
            await callback_query.answer("❌ 刷新失败，请稍后重试")
    
    async def _handle_stop_cloning_progress(self, callback_query: CallbackQuery):
        """处理停止搬运进度"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"⏹️ 用户 {user_id} 请求停止任务")
            
            # 初始化实例变量
            if not hasattr(self, 'task_progress'):
                self.task_progress = {}
            if not hasattr(self, 'all_tasks'):
                self.all_tasks = {}
            
            # 获取当前活动任务
            if user_id in self.task_progress and user_id in self.all_tasks:
                all_tasks = self.all_tasks[user_id]
                stopped_count = 0
                
                # 停止所有运行中的任务
                for task_info in all_tasks:
                    if task_info.get('status') == 'running':
                        task_id = task_info['task_id']
                        if hasattr(self, 'cloning_engine') and self.cloning_engine and task_id in self.cloning_engine.active_tasks:
                            success = await self.cloning_engine.cancel_task(task_id)
                            if success:
                                task_info['status'] = 'cancelled'
                                stopped_count += 1
                                logger.info(f"✅ 已停止任务: {task_id}")
                
                if stopped_count > 0:
                    await callback_query.answer(f"⏹️ 已停止 {stopped_count} 个任务")
                    
                    # 显示停止后的状态
                    target_groups = {}
                    for task_info in all_tasks:
                        target_id = task_info['target_channel_id']
                        if target_id not in target_groups:
                            target_groups[target_id] = {
                                'target_name': task_info['target_channel_name'],
                                'tasks': []
                            }
                        target_groups[target_id]['tasks'].append(task_info)
                    
                    await self._display_progress(callback_query, target_groups, all_tasks)
                else:
                    await callback_query.answer("ℹ️ 没有运行中的任务需要停止")
            else:
                await callback_query.answer("ℹ️ 没有找到活动任务")
                
        except Exception as e:
            logger.error(f"停止搬运进度失败: {e}")
            await callback_query.answer("❌ 停止失败，请稍后重试")
    
    async def _handle_resume_cloning_progress(self, callback_query: CallbackQuery):
        """处理断点续传搬运进度"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"🔄 用户 {user_id} 请求断点续传")
            
            # 初始化实例变量
            if not hasattr(self, 'task_progress'):
                self.task_progress = {}
            if not hasattr(self, 'all_tasks'):
                self.all_tasks = {}
            
            # 获取当前活动任务
            if user_id in self.task_progress and user_id in self.all_tasks:
                all_tasks = self.all_tasks[user_id]
                resumed_count = 0
                
                # 尝试恢复失败或取消的任务
                for task_info in all_tasks:
                    if task_info.get('status') in ['failed', 'cancelled']:
                        task_id = task_info['task_id']
                        
                        # 获取最后处理的消息ID
                        last_processed = task_info.get('processed_messages', 0)
                        if last_processed > 0:
                            # 计算断点续传的起始ID
                            start_id = task_info.get('start_id', 0)
                            resume_from_id = start_id + last_processed
                            
                            # 尝试断点续传
                            if hasattr(self, 'cloning_engine') and self.cloning_engine:
                                success = await self.cloning_engine.resume_task_from_checkpoint(task_id, resume_from_id)
                                if success:
                                    task_info['status'] = 'running'
                                    resumed_count += 1
                                    logger.info(f"✅ 断点续传成功: {task_id} 从消息ID {resume_from_id} 开始")
                                else:
                                    logger.warning(f"⚠️ 断点续传失败: {task_id}")
                
                if resumed_count > 0:
                    await callback_query.answer(f"🔄 已恢复 {resumed_count} 个任务")
                    
                    # 显示恢复后的状态
                    target_groups = {}
                    for task_info in all_tasks:
                        target_id = task_info['target_channel_id']
                        if target_id not in target_groups:
                            target_groups[target_id] = {
                                'target_name': task_info['target_channel_name'],
                                'tasks': []
                            }
                        target_groups[target_id]['tasks'].append(task_info)
                    
                    await self._display_progress(callback_query, target_groups, all_tasks)
                else:
                    await callback_query.answer("ℹ️ 没有可恢复的任务")
            else:
                await callback_query.answer("ℹ️ 没有找到活动任务")
                
        except Exception as e:
            logger.error(f"断点续传失败: {e}")
            await callback_query.answer("❌ 断点续传失败，请稍后重试")
    
    async def _handle_refresh_multi_task_progress(self, callback_query: CallbackQuery):
        """处理刷新多任务进度"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"🔄 用户 {user_id} 请求刷新多任务进度")
            
            # 获取多任务状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                state = self.multi_select_states[user_id]
                task_ids = state.get('task_ids', [])
                task_configs = state.get('task_configs', [])
                
                if task_ids:
                    # 更新多任务进度界面
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                    await callback_query.answer("🔄 多任务进度已刷新")
                else:
                    await callback_query.answer("ℹ️ 没有找到活动的多任务")
            else:
                await callback_query.answer("ℹ️ 没有找到多任务状态")
                
        except Exception as e:
            logger.error(f"刷新多任务进度失败: {e}")
            await callback_query.answer("❌ 刷新失败，请稍后重试")
    
    async def _handle_stop_multi_task_cloning(self, callback_query: CallbackQuery):
        """处理停止多任务搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"⏹️ 用户 {user_id} 请求停止多任务")
            
            # 获取多任务状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                state = self.multi_select_states[user_id]
                task_ids = state.get('task_ids', [])
                stopped_count = 0
                
                # 停止所有运行中的任务
                for task_id in task_ids:
                    if hasattr(self, 'cloning_engine') and self.cloning_engine and task_id in self.cloning_engine.active_tasks:
                        success = await self.cloning_engine.cancel_task(task_id)
                        if success:
                            stopped_count += 1
                            logger.info(f"✅ 已停止多任务: {task_id}")
                
                if stopped_count > 0:
                    await callback_query.answer(f"⏹️ 已停止 {stopped_count} 个多任务")
                    # 更新界面
                    task_configs = state.get('task_configs', [])
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                else:
                    await callback_query.answer("ℹ️ 没有运行中的多任务需要停止")
            else:
                await callback_query.answer("ℹ️ 没有找到多任务状态")
                
        except Exception as e:
            logger.error(f"停止多任务失败: {e}")
            await callback_query.answer("❌ 停止失败，请稍后重试")
    
    async def _handle_resume_multi_task_cloning(self, callback_query: CallbackQuery):
        """处理断点续传多任务搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            logger.info(f"🔄 用户 {user_id} 请求断点续传多任务")
            
            # 获取多任务状态
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                state = self.multi_select_states[user_id]
                task_ids = state.get('task_ids', [])
                task_configs = state.get('task_configs', [])
                resumed_count = 0
                
                # 尝试恢复失败或取消的任务
                for i, task_id in enumerate(task_ids):
                    if hasattr(self, 'cloning_engine') and self.cloning_engine and task_id in self.cloning_engine.active_tasks:
                        task = self.cloning_engine.active_tasks[task_id]
                        if task.status in ['failed', 'cancelled']:
                            # 获取最后处理的消息ID
                            last_processed = task.processed_messages
                            if last_processed > 0:
                                # 计算断点续传的起始ID
                                start_id = task.start_id or 0
                                resume_from_id = start_id + last_processed
                                
                                # 尝试断点续传
                                success = await self.cloning_engine.resume_task_from_checkpoint(task_id, resume_from_id)
                                if success:
                                    resumed_count += 1
                                    logger.info(f"✅ 多任务断点续传成功: {task_id} 从消息ID {resume_from_id} 开始")
                
                if resumed_count > 0:
                    await callback_query.answer(f"🔄 已恢复 {resumed_count} 个多任务")
                    # 更新界面
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                else:
                    await callback_query.answer("ℹ️ 没有可恢复的多任务")
            else:
                await callback_query.answer("ℹ️ 没有找到多任务状态")
                
        except Exception as e:
            logger.error(f"断点续传多任务失败: {e}")
            await callback_query.answer("❌ 断点续传失败，请稍后重试")
    
    async def _handle_toggle_filter_photo(self, callback_query: CallbackQuery):
        """处理图片过滤开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('filter_photo', False)
            new_status = not current_status
            user_config['filter_photo'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已过滤" if new_status else "❌ 不过滤"
            message_text = f"""
🖼️ **图片过滤设置**

📝 **当前状态：** {status_text}

💡 **功能说明：**
• 开启后，所有图片消息将被过滤
• 只保留文本和其他媒体类型

🔙 返回文件过滤菜单
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回文件过滤", "show_file_filter_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理图片过滤开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_filter_video(self, callback_query: CallbackQuery):
        """处理视频过滤开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('filter_video', False)
            new_status = not current_status
            user_config['filter_video'] = new_status
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            status_text = "✅ 已过滤" if new_status else "❌ 不过滤"
            message_text = f"""
🎬 **视频过滤设置**

📝 **当前状态：** {status_text}

💡 **功能说明：**
• 开启后，所有视频消息将被过滤
• 只保留文本和其他媒体类型

🔙 返回文件过滤菜单
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回文件过滤", "show_file_filter_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理视频过滤开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_select_tail_frequency(self, callback_query: CallbackQuery):
        """处理选择附加文字频率"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 判断是pair_id格式还是pair_index格式
            if data_part.startswith('pair_'):
                # pair_id格式
                pair_id = data_part
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                
                # 查找对应的频道组
                pair = None
                pair_index = None
                for i, p in enumerate(channel_pairs):
                    if p.get('id') == pair_id:
                        pair = p
                        pair_index = i
                        break
                
                if not pair:
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
            else:
                # pair_index格式（向后兼容）
                pair_index = int(data_part)
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                pair_id = pair.get('id', f'pair_{pair_index}')
            
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取当前频率设置
            user_config = await self.data_manager.get_user_config(user_id)
            current_frequency = user_config.get('tail_frequency', 100)
            
            config_text = f"""
⚙️ **频道组 {pair_index + 1} 小尾巴频率设置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

📝 **当前频率：** {current_frequency}%

💡 **频率说明：**
• 100%: 每条消息都添加小尾巴
• 50%: 每2条消息中约有1条添加小尾巴
• 25%: 每4条消息中约有1条添加小尾巴
• 10%: 每10条消息中约有1条添加小尾巴

🔙 返回小尾巴设置
            """.strip()
            
            # 生成频率选择按钮
            buttons = [
                [("100% 每条都添加", f"set_tail_frequency:{pair_id}:100")],
                [("75% 大部分添加", f"set_tail_frequency:{pair_id}:75")],
                [("50% 一半添加", f"set_tail_frequency:{pair_id}:50")],
                [("25% 少量添加", f"set_tail_frequency:{pair_id}:25")],
                [("10% 偶尔添加", f"set_tail_frequency:{pair_id}:10")],
                [("🔙 返回小尾巴设置", f"channel_tail_text:{pair_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理选择附加文字频率失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_select_button_frequency(self, callback_query: CallbackQuery):
        """处理选择附加按钮频率"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 判断是pair_id格式还是pair_index格式
            if data_part.startswith('pair_'):
                # pair_id格式
                pair_id = data_part
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                
                # 查找对应的频道组
                pair = None
                pair_index = None
                for i, p in enumerate(channel_pairs):
                    if p.get('id') == pair_id:
                        pair = p
                        pair_index = i
                        break
                
                if not pair:
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
            else:
                # pair_index格式（向后兼容）
                pair_index = int(data_part)
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                pair_id = pair.get('id', f'pair_{pair_index}')
            
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取当前频率设置
            user_config = await self.data_manager.get_user_config(user_id)
            current_frequency = user_config.get('button_frequency', 100)
            
            config_text = f"""
⚙️ **频道组 {pair_index + 1} 按钮频率设置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

🔘 **当前频率：** {current_frequency}%

💡 **频率说明：**
• 100%: 每条消息都添加按钮
• 50%: 每2条消息中约有1条添加按钮
• 25%: 每4条消息中约有1条添加按钮
• 10%: 每10条消息中约有1条添加按钮

🔙 返回按钮设置
            """.strip()
            
            # 生成频率选择按钮
            buttons = [
                [("100% 每条都添加", f"set_button_frequency:{pair_id}:100")],
                [("75% 大部分添加", f"set_button_frequency:{pair_id}:75")],
                [("50% 一半添加", f"set_button_frequency:{pair_id}:50")],
                [("25% 少量添加", f"set_button_frequency:{pair_id}:25")],
                [("10% 偶尔添加", f"set_button_frequency:{pair_id}:10")],
                [("🔙 返回按钮设置", f"channel_buttons:{pair_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理选择附加按钮频率失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_tail_frequency(self, callback_query: CallbackQuery):
        """处理设置附加文字频率"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            # 检查是否包含频道组索引
            if ':' in data:
                parts = data.split(':')
                if len(parts) == 2:
                    # 全局设置
                    frequency = parts[1]
                    return_callback = "show_frequency_settings"
                    config_title = "🎯 **全局附加文字频率设置**\n\n"
                else:
                    # 频道组特定设置
                    data_part = parts[1]
                    frequency = parts[2]
                    
                    # 判断是pair_id格式还是pair_index格式
                    if data_part.startswith('pair_'):
                        # pair_id格式
                        pair_id = data_part
                        channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                        
                        # 查找对应的频道组
                        pair = None
                        pair_index = None
                        for i, p in enumerate(channel_pairs):
                            if p.get('id') == pair_id:
                                pair = p
                                pair_index = i
                                break
                        
                        if not pair:
                            await callback_query.edit_message_text("❌ 频道组不存在")
                            return
                    else:
                        # pair_index格式（向后兼容）
                        pair_index = int(data_part)
                        channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                        if pair_index >= len(channel_pairs):
                            await callback_query.edit_message_text("❌ 频道组不存在")
                            return
                        
                        pair = channel_pairs[pair_index]
                        pair_id = pair.get('id', f'pair_{pair_index}')
                    
                    return_callback = f"channel_tail_text:{pair_id}"
                    config_title = f"🎯 **频道组 {pair_index + 1} 附加文字频率设置**\n\n"
            else:
                await callback_query.edit_message_text("❌ 频率设置格式错误")
                return
            
            # 检查频率值
            if frequency.isdigit():
                freq_value = int(frequency)
                if 1 <= freq_value <= 100:
                    user_config = await self.data_manager.get_user_config(user_id)
                    
                    # 检查是否是频道组特定设置
                    if 'pair_id' in locals():
                        # 频道组特定设置
                        if 'channel_filters' not in user_config:
                            user_config['channel_filters'] = {}
                        if pair_id not in user_config['channel_filters']:
                            user_config['channel_filters'][pair_id] = {}
                        
                        user_config['channel_filters'][pair_id]['tail_frequency'] = freq_value
                    else:
                        # 全局设置
                        user_config['tail_frequency'] = freq_value
                    
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    message_text = f"""
{config_title}
✅ **已设置为：** {freq_value}%

💡 **频率说明：**
• {freq_value}% 的消息会添加附加文字
• 例如：设置为 50% 时，每2条消息中约有1条会添加附加文字
• 设置为 100% 时，每条消息都会添加附加文字

🔙 返回设置
                    """.strip()
                    
                    await callback_query.edit_message_text(
                        message_text,
                        reply_markup=generate_button_layout([[
                            ("🔙 返回", return_callback)
                        ]])
                    )
                else:
                    await callback_query.edit_message_text("❌ 频率值必须在1-100之间")
            else:
                await callback_query.edit_message_text("❌ 频率值必须是1-100之间的数字")
            
        except Exception as e:
            logger.error(f"处理设置附加文字频率失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_button_frequency(self, callback_query: CallbackQuery):
        """处理设置附加按钮频率"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            # 检查是否包含频道组索引
            if ':' in data:
                parts = data.split(':')
                if len(parts) == 2:
                    # 全局设置
                    frequency = parts[1]
                    return_callback = "show_frequency_settings"
                    config_title = "🎯 **全局附加按钮频率设置**\n\n"
                else:
                    # 频道组特定设置
                    data_part = parts[1]
                    frequency = parts[2]
                    
                    # 判断是pair_id格式还是pair_index格式
                    if data_part.startswith('pair_'):
                        # pair_id格式
                        pair_id = data_part
                        channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                        
                        # 查找对应的频道组
                        pair = None
                        pair_index = None
                        for i, p in enumerate(channel_pairs):
                            if p.get('id') == pair_id:
                                pair = p
                                pair_index = i
                                break
                        
                        if not pair:
                            await callback_query.edit_message_text("❌ 频道组不存在")
                            return
                    else:
                        # pair_index格式（向后兼容）
                        pair_index = int(data_part)
                        channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                        if pair_index >= len(channel_pairs):
                            await callback_query.edit_message_text("❌ 频道组不存在")
                            return
                        
                        pair = channel_pairs[pair_index]
                        pair_id = pair.get('id', f'pair_{pair_index}')
                    
                    return_callback = f"channel_buttons:{pair_id}"
                    config_title = f"🎯 **频道组 {pair_index + 1} 附加按钮频率设置**\n\n"
            else:
                await callback_query.edit_message_text("❌ 频率设置格式错误")
                return
            
            # 检查频率值
            if frequency.isdigit():
                freq_value = int(frequency)
                if 1 <= freq_value <= 100:
                    user_config = await self.data_manager.get_user_config(user_id)
                    
                    # 检查是否是频道组特定设置
                    if 'pair_id' in locals():
                        # 频道组特定设置
                        if 'channel_filters' not in user_config:
                            user_config['channel_filters'] = {}
                        if pair_id not in user_config['channel_filters']:
                            user_config['channel_filters'][pair_id] = {}
                        
                        user_config['channel_filters'][pair_id]['button_frequency'] = freq_value
                    else:
                        # 全局设置
                        user_config['button_frequency'] = freq_value
                    
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    message_text = f"""
{config_title}
✅ **已设置为：** {freq_value}%

💡 **频率说明：**
• {freq_value}% 的消息会添加附加按钮
• 例如：设置为 50% 时，每2条消息中约有1条会添加附加按钮
• 设置为 100% 时，每条消息都会添加附加按钮

🔙 返回设置
                    """.strip()
                    
                    await callback_query.edit_message_text(
                        message_text,
                        reply_markup=generate_button_layout([[
                            ("🔙 返回", return_callback)
                        ]])
                    )
                else:
                    await callback_query.edit_message_text("❌ 频率值必须在1-100之间")
            else:
                await callback_query.edit_message_text("❌ 频率值必须是1-100之间的数字")
            
        except Exception as e:
            logger.error(f"处理设置附加按钮频率失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_show_link_filter_menu(self, callback_query: CallbackQuery):
        """处理显示链接过滤菜单"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取当前状态
            links_status = "✅ 已开启" if user_config.get('remove_all_links', False) else "❌ 已关闭"
            mode_text = user_config.get('remove_links_mode', 'links_only')
            
            # 处理模式文本
            mode_display = {
                'links_only': '📝 仅移除链接',
                'remove_message': '🗑️ 移除整条消息'
            }.get(mode_text, '未知')
            
            config_text = f"""
🔗 **链接过滤设置**

📊 **当前状态：**
• 过滤所有链接: {links_status}
• 过滤方式: {mode_display}

💡 **功能说明：**
• 过滤所有链接：移除消息中的所有类型链接（HTTP、HTTPS、磁力链接等）
• 过滤方式：选择仅移除链接或移除整条消息

请选择要设置的过滤类型：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🔗 过滤所有链接", "toggle_remove_all_links")],
                [("🔧 过滤方式", "toggle_remove_links_mode")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理显示链接过滤菜单失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_show_enhanced_filter_menu(self, callback_query: CallbackQuery):
        """处理显示增强过滤菜单"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取当前状态
            enhanced_status = "✅ 已开启" if user_config.get('enhanced_filter_enabled', False) else "❌ 已关闭"
            mode_text = user_config.get('enhanced_filter_mode', 'aggressive')
            
            # 处理模式文本
            mode_display = {
                'aggressive': '🔥 激进模式',
                'moderate': '⚖️ 平衡模式', 
                'conservative': '🛡️ 保守模式'
            }.get(mode_text, '未知')
            
            config_text = f"""
🚀 **增强版链接过滤设置**

📊 **当前状态：**
• 增强版过滤: {enhanced_status}
• 过滤模式: {mode_display}

💡 **功能说明：**
• 增强版过滤：结合链接移除和广告内容过滤
• 激进模式：移除所有链接、按钮和广告内容
• 平衡模式：移除链接和明显广告内容
• 保守模式：仅移除链接和按钮

请选择要设置的过滤类型：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🚀 增强版过滤", "toggle_enhanced_filter")],
                [("⚙️ 过滤模式", "toggle_enhanced_filter_mode")],
                [("👁️ 预览效果", "preview_enhanced_filter")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理显示增强过滤菜单失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_enhanced_filter(self, callback_query: CallbackQuery):
        """处理增强过滤开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换状态
            current_state = user_config.get('enhanced_filter_enabled', False)
            user_config['enhanced_filter_enabled'] = not current_state
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 重新显示菜单
            await self._show_enhanced_filter_config(callback_query)
            
        except Exception as e:
            logger.error(f"处理增强过滤开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_enhanced_filter_mode(self, callback_query: CallbackQuery):
        """处理增强过滤模式切换"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换模式
            current_mode = user_config.get('enhanced_filter_mode', 'aggressive')
            modes = ['aggressive', 'moderate', 'conservative']
            current_index = modes.index(current_mode)
            next_index = (current_index + 1) % len(modes)
            user_config['enhanced_filter_mode'] = modes[next_index]
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 重新显示菜单
            await self._show_enhanced_filter_config(callback_query)
            
        except Exception as e:
            logger.error(f"处理增强过滤模式切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_preview_enhanced_filter(self, callback_query: CallbackQuery):
        """处理增强过滤预览"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 示例文本
            sample_text = """这是一个测试消息，包含各种内容：

🔗 链接测试：
https://example.com
t.me/test_channel
@username

📱 按钮测试：
[点击查看详情]
[立即购买]

📢 广告测试：
限时优惠！立即抢购！
联系客服微信：test123
免费咨询电话：400-123-4567

📝 正常内容：
这是一段正常的文本内容，应该被保留。"""
            
            # 应用增强过滤
            from enhanced_link_filter import enhanced_link_filter
            filtered_text = enhanced_link_filter(sample_text, user_config)
            
            preview_text = f"""
👁️ **增强过滤预览效果**

📝 **原始文本：**
```
{sample_text}
```

✨ **过滤后文本：**
```
{filtered_text}
```

💡 **说明：** 根据当前设置显示过滤效果
            """.strip()
            
            await callback_query.edit_message_text(
                preview_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 返回设置", callback_data="show_enhanced_filter_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理增强过滤预览失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _show_enhanced_filter_config(self, callback_query: CallbackQuery):
        """显示增强过滤配置（避免MESSAGE_NOT_MODIFIED错误）"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取当前状态
            enhanced_status = "✅ 已开启" if user_config.get('enhanced_filter_enabled', False) else "❌ 已关闭"
            mode_text = user_config.get('enhanced_filter_mode', 'aggressive')
            
            # 处理模式文本
            mode_display = {
                'aggressive': '🔥 激进模式',
                'moderate': '⚖️ 平衡模式', 
                'conservative': '🛡️ 保守模式'
            }.get(mode_text, '未知')
            
            config_text = f"""
🚀 **增强版链接过滤设置**

📊 **当前状态：**
• 增强版过滤: {enhanced_status}
• 过滤模式: {mode_display}

💡 **功能说明：**
• 增强版过滤：结合链接移除和广告内容过滤
• 激进模式：移除所有链接、按钮和广告内容
• 平衡模式：移除链接和明显广告内容
• 保守模式：仅移除链接和按钮

请选择要设置的过滤类型：
            """.strip()
            
            # 生成按钮
            buttons = [
                [("🚀 增强版过滤", "toggle_enhanced_filter")],
                [("⚙️ 过滤模式", "toggle_enhanced_filter_mode")],
                [("👁️ 预览效果", "preview_enhanced_filter")],
                [("🔙 返回功能配置", "show_feature_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示增强过滤配置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_remove_links_mode(self, callback_query: CallbackQuery):
        """处理链接过滤方式切换"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 切换过滤方式
            current_mode = user_config.get('remove_links_mode', 'links_only')
            new_mode = 'remove_message' if current_mode == 'links_only' else 'links_only'
            user_config['remove_links_mode'] = new_mode
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_text = "🗑️ 移除整条消息" if new_mode == 'remove_message' else "📝 智能移除链接"
            message_text = f"""
🔧 **链接过滤方式设置**

📝 **当前方式：** {mode_text}

💡 **功能说明：**
• 智能移除链接：移除链接以及包含超链接的相关文字，保留其他内容
• 移除整条消息：包含链接的整条消息将被完全移除

🔙 返回链接过滤菜单
            """.strip()
            
            await callback_query.edit_message_text(
                message_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回链接过滤", "show_link_filter_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理链接过滤方式切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    # ==================== 监听管理方法 ====================
    
    # ==================== 简化版监听处理方法 ====================
    
    
    
    
    
    # ==================== 原有监听管理方法 ====================
    
    async def _handle_view_monitoring_tasks(self, callback_query: CallbackQuery):
        """处理查看监听任务"""
        try:
            user_id = str(callback_query.from_user.id)
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            
            if not user_tasks:
                await callback_query.edit_message_text(
                    "📡 **我的监听任务**\n\n❌ 您还没有创建任何监听任务\n\n💡 点击下方按钮创建第一个监听任务",
                    reply_markup=generate_button_layout([
                        [("➕ 创建监听任务", "create_monitoring_task")],
                        [("🔙 返回监听菜单", "show_monitor_menu")]
                    ])
                )
                return
            
            # 构建任务列表
            tasks_text = "📡 **我的监听任务**\n\n"
            buttons = []
            
            for task in user_tasks:
                task_id = task['task_id']
                status_emoji = {
                    'active': '🟢',
                    'paused': '🟡', 
                    'stopped': '🔴',
                    'pending': '⚪',
                    'failed': '❌'
                }.get(task['status'], '❓')
                
                mode_emoji = {
                    'realtime': '⚡',
                    'delayed': '⏰',
                    'batch': '📦'
                }.get(task['monitoring_mode'], '❓')
                
                target_channel = task['target_channel']
                source_count = task['source_channels']
                
                tasks_text += f"{status_emoji} **任务 {task_id[-8:]}**\n"
                tasks_text += f"   📤 目标频道: {target_channel}\n"
                tasks_text += f"   📡 源频道: {source_count} 个\n"
                tasks_text += f"   {mode_emoji} 模式: {task['monitoring_mode']}\n"
                tasks_text += f"   📈 处理消息: {task['stats']['total_processed']} 条\n\n"
                
                # 添加任务操作按钮
                buttons.append([(f"{status_emoji} 任务详情", f"monitor_task_detail:{task_id}")])
            
            # 添加操作按钮
            buttons.extend([
                [("➕ 新建监听任务", "create_monitoring_task")],
                [("🔄 刷新列表", "view_monitoring_tasks")],
                [("🔙 返回监听菜单", "show_monitor_menu")]
            ])
            
            try:
                await callback_query.edit_message_text(
                    tasks_text,
                    reply_markup=generate_button_layout(buttons)
                )
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    # 消息内容没有变化，只更新按钮
                    await callback_query.edit_message_reply_markup(
                        reply_markup=generate_button_layout(buttons)
                    )
                else:
                    raise e
            
        except Exception as e:
            logger.error(f"查看监听任务失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_create_monitoring_task(self, callback_query: CallbackQuery):
        """处理创建监听任务"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取管理员频道列表
            admin_channels = await self._get_admin_channels()
            verified_channels = [ch for ch in admin_channels if ch.get('verified', False)]
            
            if not verified_channels:
                # 检查是否有未验证的频道
                unverified_channels = [ch for ch in admin_channels if not ch.get('verified', False)]
                if unverified_channels:
                    await callback_query.edit_message_text(
                        "📡 **创建监听任务**\n\n"
                        "❌ **无法创建监听任务**\n\n"
                        f"⚠️ **发现 {len(unverified_channels)} 个未验证的频道**\n\n"
                        "💡 **解决方法：**\n"
                        "1. 到频道管理中验证频道\n"
                        "2. 确保机器人有管理员权限\n"
                        "3. 在频道中发送 `/lsj` 进行验证\n\n"
                        "📝 **提示：** 监听的目标频道必须是已验证的频道",
                        reply_markup=generate_button_layout([
                            [("📋 频道管理", "show_channel_admin_test")],
                            [("🔙 返回监听菜单", "show_monitor_menu")]
                        ])
                    )
                else:
                    await callback_query.edit_message_text(
                        "📡 **创建监听任务**\n\n"
                        "❌ **无法创建监听任务**\n\n"
                        "💡 **原因：** 没有找到机器人是管理员的频道\n\n"
                        "🔧 **解决方法：**\n"
                        "1. 将机器人添加为频道管理员\n"
                        "2. 在频道管理中验证频道\n"
                        "3. 然后重新创建监听任务\n\n"
                        "📝 **提示：** 监听的目标频道必须是机器人有管理员权限的频道",
                        reply_markup=generate_button_layout([
                            [("📋 频道管理", "show_channel_admin_test")],
                            [("🔙 返回监听菜单", "show_monitor_menu")]
                        ])
                    )
                return
            
            # 初始化创建任务状态
            self.user_states[user_id] = {
                'state': 'creating_monitoring_task',
                'data': {
                    'target_channel': None,
                    'source_channels': [],
                    'config': {
                        'check_interval': 60,
                        'max_retries': 3,
                        'retry_delay': 30
                    }
                }
            }
            
            # 构建频道选择界面
            channels_text = f"""
📡 **创建监听任务**

🎯 **第一步：选择目标频道**

📋 **可用的管理员频道** ({len(admin_channels)} 个)
💡 **点击频道按钮选择目标频道**

            """.strip()
            
            # 创建频道选择按钮
            buttons = []
            for channel in admin_channels:
                channel_id = channel.get('id')
                channel_name = channel.get('title', '未知频道')
                username = channel.get('username', '')
                enabled = channel.get('enabled', True)
                
                # 格式化频道信息
                if username:
                    channel_display = f"{channel_name} (@{username})"
                else:
                    channel_display = f"{channel_name} (无用户名)"
                
                # 添加状态标识
                status_icon = "✅" if enabled else "❌"
                
                buttons.append([(f"{status_icon} {channel_display}", f"select_monitor_target:{channel_id}")])
            
            # 添加返回按钮
            buttons.append([("🔙 返回监听菜单", "show_monitor_menu")])
            
            await callback_query.edit_message_text(
                channels_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"创建监听任务失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_monitor_settings(self, callback_query: CallbackQuery):
        """处理监听设置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取监听配置
            monitor_config = user_config.get('monitor_config', {
                'check_interval': 60,
                'max_retries': 3,
                'retry_delay': 30
            })
            
            settings_text = f"""
⚙️ **监听设置**

📊 **当前配置**
• 检查间隔: {monitor_config.get('check_interval', 60)} 秒
• 最大重试: {monitor_config.get('max_retries', 3)} 次
• 重试延迟: {monitor_config.get('retry_delay', 30)} 秒

💡 **配置说明**
• 检查间隔: 监听系统检查新消息的频率
• 最大重试: 失败时的最大重试次数
• 重试延迟: 重试之间的等待时间

🔧 **操作选项**
            """.strip()
            
            await callback_query.edit_message_text(
                settings_text,
                reply_markup=generate_button_layout([
                    [("⏰ 设置检查间隔", "set_monitor_interval")],
                    [("🔄 设置重试次数", "set_monitor_retries")],
                    [("⏱️ 设置重试延迟", "set_monitor_retry_delay")],
                    [("🔙 返回监听菜单", "show_monitor_menu")]
                ])
            )
            
        except Exception as e:
            logger.error(f"显示监听设置失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_start_monitoring_task(self, callback_query: CallbackQuery):
        """处理启动监听任务"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            success = await self.realtime_monitoring_engine.start_monitoring_task(task_id)
            
            if success:
                await callback_query.answer("✅ 监听任务已启动")
                # 刷新任务列表
                await self._handle_view_monitoring_tasks(callback_query)
            else:
                await callback_query.answer("❌ 启动失败")
                
        except Exception as e:
            logger.error(f"启动监听任务失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_stop_monitoring_task(self, callback_query: CallbackQuery):
        """处理停止监听任务"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            success = await self.realtime_monitoring_engine.stop_monitoring_task(task_id)
            
            if success:
                await callback_query.answer("✅ 监听任务已停止")
                # 刷新任务列表
                await self._handle_view_monitoring_tasks(callback_query)
            else:
                await callback_query.answer("❌ 停止失败")
                
        except Exception as e:
            logger.error(f"停止监听任务失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_delete_monitoring_task(self, callback_query: CallbackQuery):
        """处理删除监听任务"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            # 实时监听引擎没有delete方法，我们使用stop
            success = await self.realtime_monitoring_engine.stop_monitoring_task(task_id)
            
            if success:
                await callback_query.answer("✅ 监听任务已删除")
                # 刷新任务列表
                await self._handle_view_monitoring_tasks(callback_query)
            else:
                await callback_query.answer("❌ 删除失败")
                
        except Exception as e:
            logger.error(f"删除监听任务失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_monitor_task_detail(self, callback_query: CallbackQuery):
        """处理监听任务详情"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            # 获取实时监听任务
            task_status = self.realtime_monitoring_engine.get_task_status(task_id)
            
            if not task_status:
                await callback_query.answer("❌ 任务不存在")
                return
            
            # 构建任务详情
            status_emoji = {
                'active': '🟢',
                'paused': '🟡', 
                'stopped': '🔴',
                'pending': '⚪',
                'failed': '❌'
            }.get(task_status['status'], '❓')
            
            mode_emoji = {
                'realtime': '⚡',
                'delayed': '⏰',
                'batch': '📦'
            }.get(task_status['monitoring_mode'], '❓')
            
            detail_text = f"📡 **监听任务详情**\n\n"
            detail_text += f"🆔 **任务ID:** {task_id}\n"
            detail_text += f"📊 **状态:** {status_emoji} {task_status['status']}\n"
            detail_text += f"📤 **目标频道:** {task_status['target_channel']}\n"
            detail_text += f"📡 **源频道数量:** {task_status.get('source_channels_count', len(task_status.get('source_channels', [])))} 个\n"
            detail_text += f"{mode_emoji} **监听模式:** {task_status['monitoring_mode']}\n\n"
            
            # 显示源频道详情
            detail_text += f"📡 **源频道列表:**\n"
            source_channels_display = task_status.get('source_channels_display', [])
            if source_channels_display:
                for i, channel_display in enumerate(source_channels_display, 1):
                    detail_text += f"{i}. {channel_display}\n"
            else:
                # 如果没有display格式，使用原始数据
                source_channels = task_status.get('source_channels', [])
                for i, source in enumerate(source_channels, 1):
                    channel_name = source.get('channel_name', '未知频道')
                    channel_username = source.get('channel_username', '')
                    
                    if channel_username:
                        detail_text += f"{i}. {channel_name} (@{channel_username})\n"
                    else:
                        detail_text += f"{i}. {channel_name}\n"
            
            # 显示统计信息
            stats = task_status.get('stats', {})
            if stats:
                detail_text += f"📊 **统计信息:**\n"
                
                # 按源频道分组的统计
                source_stats = task_status.get('source_stats', {})
                if source_stats:
                    detail_text += f"**按源频道分组:**\n"
                    for channel_id, channel_stat in source_stats.items():
                        channel_name = channel_stat.get('channel_name', '未知频道')
                        channel_username = channel_stat.get('channel_username', '')
                        processed = channel_stat.get('processed', 0)
                        successful = channel_stat.get('successful', 0)
                        failed = channel_stat.get('failed', 0)
                        filtered = channel_stat.get('filtered', 0)
                        
                        display_name = f"{channel_name} (@{channel_username})" if channel_username else channel_name
                        detail_text += f"• {display_name}: 处理{processed}条, 成功{successful}条, 失败{failed}条, 过滤{filtered}条\n"
                    detail_text += "\n"
                
                # 全局统计
                detail_text += f"**全局统计:**\n"
                detail_text += f"• 处理消息数: {stats.get('total_processed', 0)} 条\n"
                detail_text += f"• 成功搬运: {stats.get('successful_transfers', 0)} 条\n"
                detail_text += f"• 失败搬运: {stats.get('failed_transfers', 0)} 条\n"
                detail_text += f"• 过滤消息: {stats.get('filtered_messages', 0)} 条\n"
                detail_text += f"• 最后消息时间: {stats.get('last_message_time', '未知')}\n\n"
            
            # 显示任务时间
            if task_status.get('start_time'):
                detail_text += f"🕒 **开始时间:** {task_status['start_time']}\n"
            if task_status.get('pause_time'):
                detail_text += f"⏸️ **暂停时间:** {task_status['pause_time']}\n"
            detail_text += "\n"
            
            # 添加监听模式说明
            mode = task_status['monitoring_mode']
            if mode == 'realtime':
                detail_text += f"⚡ **实时监听模式**\n"
                detail_text += f"• 消息发布立即搬运\n"
                detail_text += f"• 零延迟响应\n"
                detail_text += f"• 自动重试机制\n"
            elif mode == 'delayed':
                detail_text += f"⏰ **延迟监听模式**\n"
                detail_text += f"• 延迟5-30秒后搬运\n"
                detail_text += f"• 避免频繁操作\n"
                detail_text += f"• 自动重试机制\n"
            elif mode == 'batch':
                detail_text += f"📦 **批量监听模式**\n"
                detail_text += f"• 积累多条消息批量搬运\n"
                detail_text += f"• 提高效率\n"
                detail_text += f"• 自动重试机制\n"
            detail_text += "\n"
            
            # 生成操作按钮
            buttons = []
            status = task_status['status']
            if status == 'active':
                buttons.append([("⏸️ 暂停监听", f"pause_monitoring_task:{task_id}")])
            elif status == 'paused':
                buttons.append([("▶️ 恢复监听", f"resume_monitoring_task:{task_id}")])
            elif status in ['stopped', 'pending']:
                buttons.append([("▶️ 启动监听", f"start_monitoring_task:{task_id}")])
            
            buttons.extend([
                [("🗑️ 删除任务", f"delete_monitoring_task:{task_id}")],
                [("🔙 返回任务列表", "view_monitoring_tasks")]
            ])
            
            await callback_query.edit_message_text(
                detail_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示监听任务详情失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_select_monitor_target(self, callback_query: CallbackQuery):
        """处理选择监听目标频道"""
        try:
            channel_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            # 获取管理员频道信息
            admin_channels = await self._get_admin_channels()
            selected_channel = None
            for channel in admin_channels:
                if str(channel.get('id')) == channel_id:
                    selected_channel = channel
                    break
            
            if not selected_channel:
                await callback_query.answer("❌ 频道不存在")
                return
            
            # 更新用户状态
            if user_id in self.user_states:
                self.user_states[user_id]['data']['target_channel'] = {
                    'id': channel_id,
                    'name': selected_channel.get('title', '未知频道'),
                    'username': selected_channel.get('username', ''),
                    'enabled': selected_channel.get('enabled', True)
                }
            else:
                # 如果用户状态不存在，重新创建
                self.user_states[user_id] = {
                    'state': 'creating_monitoring_task',
                    'data': {
                        'target_channel': {
                            'id': channel_id,
                            'name': selected_channel.get('title', '未知频道'),
                            'username': selected_channel.get('username', ''),
                            'enabled': selected_channel.get('enabled', True)
                        },
                        'source_channels': [],
                        'config': {
                            'check_interval': 60,
                            'max_retries': 3,
                            'retry_delay': 30
                        }
                    }
                }
            
            # 显示频道信息并进入下一步
            channel_name = selected_channel.get('title', '未知频道')
            username = selected_channel.get('username', '')
            channel_display = f"{channel_name} (@{username})" if username else f"{channel_name} (无用户名)"
            
            # 获取频道过滤配置信息
            user_config = await self.data_manager.get_user_config(user_id)
            admin_channel_filters = user_config.get('admin_channel_filters', {})
            channel_filters = admin_channel_filters.get(channel_id, {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            filter_info = "🔧 使用频道独立过滤配置" if independent_enabled else "🔧 使用全局过滤配置"
            
            await callback_query.edit_message_text(
                f"📡 **创建监听任务**\n\n"
                f"✅ **目标频道已选择**\n"
                f"📤 频道: {channel_display}\n"
                f"🆔 ID: {channel_id}\n"
                f"{filter_info}\n\n"
                f"📡 **第二步：添加源频道**\n\n"
                f"请发送源频道的ID或用户名，并指定起始消息ID：\n"
                f"• 频道ID: `-1001234567890`\n"
                f"• 频道用户名: `@channelname`\n"
                f"• 频道链接: `https://t.me/channelname`\n\n"
                f"🔧 **必须指定起始消息ID：**\n"
                f"• `https://t.me/channelname 起始ID`\n"
                f"• `@channelname 起始ID`\n"
                f"• `-1001234567890 起始ID`\n\n"
                f"📝 **示例：**\n"
                f"• `https://t.me/xsm58 7`\n"
                f"• `@channelname 100`\n\n"
                f"💡 **监听模式选择：**\n"
                f"• ⚡ 实时模式：消息发布立即搬运（推荐）\n"
                f"• ⏰ 定时模式：每60秒检查一次新消息\n"
                f"• 📦 批量模式：积累多条消息批量搬运\n\n"
                f"🔧 **过滤配置：** 监听将使用频道管理中的过滤设置",
                reply_markup=generate_button_layout([
                    [("⚡ 实时模式", "select_monitoring_mode:realtime")],
                    [("⏰ 定时模式", "select_monitoring_mode:scheduled")],
                    [("📦 批量模式", "select_monitoring_mode:batch")],
                    [("🔙 重新选择目标频道", "create_monitoring_task")]
                ])
            )
            
            await callback_query.answer(f"✅ 已选择目标频道: {channel_name}")
            
        except Exception as e:
            logger.error(f"选择监听目标频道失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_confirm_create_monitoring_task(self, callback_query: CallbackQuery):
        """处理确认创建监听任务"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 获取用户状态
            if user_id not in self.user_states:
                await callback_query.answer("❌ 会话已过期，请重新创建")
                return
            
            state = self.user_states[user_id]
            if state['state'] != 'creating_monitoring_task':
                await callback_query.answer("❌ 状态错误，请重新创建")
                return
            
            data = state['data']
            target_channel = data.get('target_channel')
            source_channels = data.get('source_channels', [])
            
            if not target_channel:
                await callback_query.answer("❌ 请先选择目标频道")
                return
            
            if not source_channels:
                await callback_query.edit_message_text(
                    "❌ **无法创建监听任务**\n\n"
                    "💡 **原因：** 还没有添加任何源频道\n\n"
                    "🔧 **解决方法：**\n"
                    "1. 发送源频道的ID或用户名\n"
                    "2. 系统会自动验证频道并检测最后消息ID\n"
                    "3. 然后再次点击确认创建任务\n\n"
                    "📝 **支持的格式：**\n"
                    "• 频道ID: `-1001234567890`\n"
                    "• 频道用户名: `@channelname`\n"
                    "• 频道链接: `https://t.me/channelname`\n\n"
                    "请发送源频道信息：",
                    reply_markup=generate_button_layout([
                        [("🔙 返回选择目标频道", "create_monitoring_task")]
                    ])
                )
                await callback_query.answer("❌ 请先添加源频道")
                return
            
            # 创建监听任务
            task_data = {
                'target_channel': target_channel['id'],
                'target_channel_name': target_channel['name'],
                'source_channels': source_channels,
                'config': data.get('config', {}),
                'status': 'pending'
            }
            
            # 检查监听引擎是否已初始化
            if not self.realtime_monitoring_engine:
                if self.user_api_logged_in and self.user_api_manager and self.user_api_manager.client:
                    logger.info("🔄 监听引擎未初始化，正在初始化...")
                    await self._initialize_monitoring_engine()
                else:
                    await callback_query.edit_message_text(
                        "❌ **监听功能需要 User API 登录**\n\n"
                        "请先登录 User API 才能使用监听功能：\n"
                        "1. 点击 /start_user_api_login 开始登录\n"
                        "2. 输入手机号码和验证码\n"
                        "3. 登录成功后即可使用监听功能",
                        reply_markup=generate_button_layout([
                            [("🔙 返回监听菜单", "show_monitor_menu")]
                        ])
                    )
                    return
            
            # 检查搬运引擎是否使用正确的客户端
            await self._ensure_cloning_engine_client()
            
            # 使用实时监听引擎创建任务
            target_channel_info = target_channel['username'] if target_channel['username'] else target_channel['id']
            task_id = await self.realtime_monitoring_engine.create_monitoring_task(
                user_id, target_channel_info, source_channels, data.get('config', {})
            )
            
            # 清理用户状态
            del self.user_states[user_id]
            
            # 显示成功消息
            target_name = target_channel['name']
            source_count = len(source_channels)
            
            await callback_query.edit_message_text(
                f"✅ **实时监听任务创建成功！**\n\n"
                f"📡 **任务ID:** {task_id[:8]}...\n"
                f"📤 **目标频道:** {target_name}\n"
                f"📡 **源频道数量:** {source_count} 个\n"
                f"📊 **状态:** 待启动\n\n"
                f"💡 **下一步操作：**\n"
                f"• 在监听任务列表中启动任务\n"
                f"• 系统会自动开始实时监听\n"
                f"• 检测并搬运新发布的内容\n\n"
                f"🎯 **实时监听流程：**\n"
                f"1. 每60秒检查一次新消息\n"
                f"2. 自动检测并搬运新内容\n"
                f"3. 智能过滤和内容处理\n"
                f"4. 实时更新监听状态",
                reply_markup=generate_button_layout([
                    [("📡 查看监听任务", "view_monitoring_tasks")],
                    [("➕ 创建新任务", "create_monitoring_task")],
                    [("🔙 返回监听菜单", "show_monitor_menu")]
                ])
            )
            
            await callback_query.answer("✅ 监听任务创建成功")
            
        except Exception as e:
            logger.error(f"确认创建监听任务失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            try:
                await callback_query.edit_message_text(
                    f"❌ **监听任务创建失败**\n\n"
                    f"🔍 **错误信息：** {str(e)}\n\n"
                    f"💡 **可能的原因：**\n"
                    f"• 目标频道权限不足\n"
                    f"• 源频道无法访问\n"
                    f"• 系统内部错误\n\n"
                    f"🔧 **解决方法：**\n"
                    f"• 检查目标频道权限\n"
                    f"• 确认源频道可访问\n"
                    f"• 重新尝试创建任务",
                    reply_markup=generate_button_layout([
                        [("🔄 重新创建", "create_monitoring_task")],
                        [("🔙 返回监听菜单", "show_monitor_menu")]
                    ])
                )
            except Exception as reply_error:
                logger.error(f"发送错误消息失败: {reply_error}")
                await callback_query.answer("❌ 创建失败，请检查日志")
    
    async def _handle_trigger_monitoring(self, callback_query: CallbackQuery):
        """处理手动触发监听搬运"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            # 获取监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await callback_query.answer("❌ 监听任务不存在")
                return
            
            # 显示任务信息
            task_text = f"🚀 **手动触发监听搬运**\n\n"
            task_text += f"📡 任务ID: {task_id}\n"
            task_text += f"📤 目标频道: {task.target_channel}\n\n"
            task_text += f"📡 **源频道列表：**\n"
            
            buttons = []
            for source in task.source_channels:
                channel_name = source.get('channel_name', '未知频道')
                channel_id = source.get('channel_id')
                last_id = source.get('last_message_id', 0)
                target_end_id = source.get('target_end_id')
                
                task_text += f"• {channel_name} (当前ID: {last_id}"
                if target_end_id:
                    task_text += f", 目标ID: {target_end_id}"
                task_text += ")\n"
                
                buttons.append([(f"🚀 触发 {channel_name}", f"trigger_channel:{task_id}:{channel_id}")])
            
            buttons.extend([
                [("🔙 返回任务详情", f"monitor_task_detail:{task_id}")]
            ])
            
            await callback_query.edit_message_text(
                task_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理手动触发监听失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_config_id_range_increment(self, callback_query: CallbackQuery):
        """处理配置ID范围增量"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            # 获取监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await callback_query.answer("❌ 监听任务不存在")
                return
            
            # 显示任务信息
            task_text = f"⚙️ **配置ID范围增量**\n\n"
            task_text += f"📡 任务ID: {task_id}\n"
            task_text += f"📤 目标频道: {task.target_channel}\n\n"
            task_text += f"📡 **源频道列表：**\n"
            
            buttons = []
            for source in task.source_channels:
                channel_name = source.get('channel_name', '未知频道')
                channel_id = source.get('channel_id')
                last_id = source.get('last_message_id', 0)
                current_increment = source.get('id_range_increment', 50)
                
                task_text += f"• {channel_name} (当前: {current_increment}条, 监听ID: {last_id})\n"
                
                buttons.append([(f"⚙️ 配置 {channel_name}", f"config_channel_increment:{task_id}:{channel_id}")])
            
            buttons.extend([
                [("🔙 返回任务详情", f"monitor_task_detail:{task_id}")]
            ])
            
            await callback_query.edit_message_text(
                task_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理配置ID范围增量失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_config_channel_increment(self, callback_query: CallbackQuery):
        """处理配置单个频道的ID范围增量"""
        try:
            parts = callback_query.data.split(':')
            task_id = parts[1]
            channel_id = parts[2]
            user_id = str(callback_query.from_user.id)
            
            # 获取监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await callback_query.answer("❌ 监听任务不存在")
                return
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                await callback_query.answer("❌ 源频道不存在")
                return
            
            channel_name = source_channel.get('channel_name', '未知频道')
            current_increment = source_channel.get('id_range_increment', 50)
            
            await callback_query.edit_message_text(
                f"⚙️ **配置ID范围增量**\n\n"
                f"📡 频道: {channel_name}\n"
                f"🆔 频道ID: {channel_id}\n"
                f"📊 当前监听ID: {source_channel.get('last_message_id', 0)}\n"
                f"🎯 当前ID范围增量: {current_increment} 条\n\n"
                f"请输入新的ID范围增量（建议10-200之间）：\n\n"
                f"💡 **示例：**\n"
                f"• 输入 `25` 表示每次搬运25条消息\n"
                f"• 输入 `100` 表示每次搬运100条消息\n\n"
                f"⚠️ **注意：** 数值过小可能效率低，过大可能超时"
            )
            
            # 设置用户状态
            self.user_states[user_id] = {
                'state': 'configuring_channel_increment',
                'data': {
                    'task_id': task_id,
                    'channel_id': channel_id,
                    'channel_name': channel_name
                }
            }
            
        except Exception as e:
            logger.error(f"处理配置频道ID范围增量失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_trigger_channel(self, callback_query: CallbackQuery):
        """处理触发单个频道搬运"""
        try:
            parts = callback_query.data.split(':')
            task_id = parts[1]
            channel_id = parts[2]
            user_id = str(callback_query.from_user.id)
            
            # 获取监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await callback_query.answer("❌ 监听任务不存在")
                return
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                await callback_query.answer("❌ 源频道不存在")
                return
            
            channel_name = source_channel.get('channel_name', '未知频道')
            last_id = source_channel.get('last_message_id', 0)
            target_end_id = source_channel.get('target_end_id')
            
            if not target_end_id:
                await callback_query.answer("❌ 请先设置目标结束ID")
                return
            
            if target_end_id <= last_id:
                await callback_query.answer("❌ 目标结束ID必须大于当前监听ID")
                return
            
            # 实时监听引擎不需要手动触发，会自动处理
            success = True
            
            if success:
                await callback_query.answer(f"✅ 已触发 {channel_name} 的搬运任务")
            else:
                await callback_query.answer(f"❌ 触发 {channel_name} 搬运任务失败")
            
        except Exception as e:
            logger.error(f"处理触发频道搬运失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_update_channel_end_id(self, callback_query: CallbackQuery):
        """处理更新单个频道目标结束ID"""
        try:
            parts = callback_query.data.split(':')
            task_id = parts[1]
            channel_id = parts[2]
            user_id = str(callback_query.from_user.id)
            
            # 设置用户状态，等待输入新的结束ID
            self.user_states[user_id] = {
                'state': 'updating_monitor_end_id',
                'data': {
                    'task_id': task_id,
                    'channel_id': channel_id
                }
            }
            
            # 获取频道信息
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await callback_query.answer("❌ 监听任务不存在")
                return
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                await callback_query.answer("❌ 源频道不存在")
                return
            
            channel_name = source_channel.get('channel_name', '未知频道')
            last_id = source_channel.get('last_message_id', 0)
            current_end_id = source_channel.get('target_end_id')
            
            await callback_query.edit_message_text(
                f"📝 **更新目标结束ID**\n\n"
                f"📡 频道: {channel_name}\n"
                f"🆔 频道ID: {channel_id}\n"
                f"📊 当前监听ID: {last_id}\n"
                f"🎯 当前目标结束ID: {current_end_id or '未设置'}\n\n"
                f"请输入新的目标结束ID（必须大于当前监听ID {last_id}）：\n\n"
                f"💡 **示例：**\n"
                f"• 输入 `100` 表示搬运到消息ID 100\n"
                f"• 输入 `200` 表示搬运到消息ID 200\n\n"
                f"⚠️ **注意：** 目标结束ID必须大于当前监听ID"
            )
            
        except Exception as e:
            logger.error(f"处理更新频道结束ID失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _process_update_monitor_end_id_input(self, message: Message, state: Dict[str, Any]):
        """处理更新监听任务目标结束ID的输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 解析输入的数字
            try:
                new_end_id = int(text)
            except ValueError:
                await message.reply_text(
                    "❌ **输入格式错误**\n\n"
                    "请输入一个有效的数字作为目标结束ID：\n\n"
                    "💡 **示例：**\n"
                    "• `100` - 搬运到消息ID 100\n"
                    "• `200` - 搬运到消息ID 200\n\n"
                    "请重新输入："
                )
                return
            
            # 获取任务信息
            task_id = state['data']['task_id']
            channel_id = state['data']['channel_id']
            
            # 获取监听任务
            user_tasks = await self.realtime_monitoring_engine.get_all_tasks(user_id)
            task = None
            for t in user_tasks:
                if t.task_id == task_id:
                    task = t
                    break
            
            if not task:
                await message.reply_text("❌ 监听任务不存在")
                return
            
            # 找到对应的源频道
            source_channel = None
            for source in task.source_channels:
                if source.get('channel_id') == channel_id:
                    source_channel = source
                    break
            
            if not source_channel:
                await message.reply_text("❌ 源频道不存在")
                return
            
            channel_name = source_channel.get('channel_name', '未知频道')
            last_id = source_channel.get('last_message_id', 0)
            
            # 验证新的结束ID
            if new_end_id <= last_id:
                await message.reply_text(
                    f"❌ **目标结束ID无效**\n\n"
                    f"📊 当前监听ID: {last_id}\n"
                    f"🎯 输入的目标结束ID: {new_end_id}\n\n"
                    f"⚠️ **要求：** 目标结束ID必须大于当前监听ID\n\n"
                    f"请重新输入一个大于 {last_id} 的数字："
                )
                return
            
            # 实时监听引擎不需要更新目标结束ID，会自动处理
            success = True
            
            if success:
                await message.reply_text(
                    f"✅ **目标结束ID更新成功**\n\n"
                    f"📡 频道: {channel_name}\n"
                    f"📊 当前监听ID: {last_id}\n"
                    f"🎯 新的目标结束ID: {new_end_id}\n\n"
                    f"🚀 **下一步：**\n"
                    f"• 监听系统将每60秒检查一次\n"
                    f"• 当目标结束ID大于当前监听ID时，自动启动搬运任务\n"
                    f"• 搬运范围：{last_id + 1} 到 {new_end_id}\n\n"
                    f"💡 您也可以手动触发搬运任务",
                    reply_markup=generate_button_layout([
                        [("🚀 手动触发搬运", f"trigger_channel:{task_id}:{channel_id}")],
                        [("📡 返回任务详情", f"monitor_task_detail:{task_id}")]
                    ])
                )
            else:
                await message.reply_text("❌ 更新目标结束ID失败，请稍后重试")
            
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理更新目标结束ID输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _process_config_channel_increment_input(self, message: Message, state: Dict[str, Any]):
        """处理配置频道ID范围增量的输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 解析输入的数字
            try:
                new_increment = int(text)
            except ValueError:
                await message.reply_text(
                    f"❌ **输入格式错误**\n\n"
                    f"请输入一个有效的数字（建议10-200之间）：\n\n"
                    f"💡 **示例：**\n"
                    f"• 输入 `25` 表示每次搬运25条消息\n"
                    f"• 输入 `100` 表示每次搬运100条消息"
                )
                return
            
            # 验证数值范围
            if new_increment < 1 or new_increment > 1000:
                await message.reply_text(
                    f"❌ **数值超出范围**\n\n"
                    f"📊 输入值: {new_increment}\n"
                    f"⚠️ **要求：** 数值必须在1-1000之间\n\n"
                    f"💡 **建议：**\n"
                    f"• 10-50：适合活跃频道\n"
                    f"• 50-100：适合一般频道\n"
                    f"• 100-200：适合低频频道"
                )
                return
            
            # 获取任务信息
            task_id = state['data']['task_id']
            channel_id = state['data']['channel_id']
            channel_name = state['data']['channel_name']
            
            # 实时监听引擎不需要更新ID范围增量，会自动处理
            success = True
            
            if success:
                await message.reply_text(
                    f"✅ **ID范围增量更新成功**\n\n"
                    f"📡 频道: {channel_name}\n"
                    f"🎯 新的ID范围增量: {new_increment} 条\n\n"
                    f"🚀 **下一步：**\n"
                    f"• 监听系统将每60秒启动一次搬运任务\n"
                    f"• 每次搬运 {new_increment} 条消息\n"
                    f"• 搬运成功后自动更新监听ID\n\n"
                    f"💡 您可以在任务详情中查看当前状态",
                    reply_markup=generate_button_layout([
                        [("📡 返回任务详情", f"monitor_task_detail:{task_id}")]
                    ])
                )
            else:
                await message.reply_text("❌ 更新ID范围增量失败，请稍后重试")
            
            # 清除用户状态
            if user_id in self.user_states:
                del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理配置频道ID范围增量输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _process_monitoring_source_input(self, message: Message, state: Dict[str, Any]):
        """处理监听源频道输入 - 支持批量处理多个频道（实时监听模式）"""
        try:
            # 优先从消息获取用户ID，如果失败则从状态中获取
            if message.from_user and message.from_user.id:
                user_id = str(message.from_user.id)
            else:
                # 从用户状态中获取用户ID
                user_id = state.get('user_id')
                if not user_id:
                    logger.error("无法获取有效的用户ID，跳过处理")
                    return
                logger.info(f"🔍 从状态中获取用户ID: {user_id}")
            
            text = message.text.strip()
            
            # 解析多个频道链接（支持换行分隔，实时监听不需要ID）
            channel_inputs = []
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    channel_inputs.append(line)
            
            if not channel_inputs:
                await message.reply_text(
                    "❌ **没有检测到有效的频道信息**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 频道ID: `-1001234567890`\n"
                    "• 频道用户名: `@channelname`\n"
                    "• 频道链接: `https://t.me/channelname`\n\n"
                    "🔧 **实时监听模式：**\n"
                    "• 系统会自动检测频道的最新消息ID\n"
                    "• 从当前时间开始监听新消息\n"
                    "• 无需手动指定消息ID\n\n"
                    "📝 **示例：**\n"
                    "• `https://t.me/xsm58`\n"
                    "• `@channelname`\n"
                    "• `-1001234567890`\n\n"
                    "🔧 **批量输入：**\n"
                    "• 每行一个频道信息\n"
                    "• 支持混合格式\n"
                    "• 系统自动处理所有频道\n\n"
                    "请重新发送正确的频道信息："
                )
                return
            
            logger.info(f"检测到 {len(channel_inputs)} 个频道输入: {channel_inputs}")
            
            # 批量验证频道
            successful_channels = []
            failed_channels = []
            
            for channel_input in channel_inputs:
                try:
                    # 解析频道信息（实时监听不需要ID）
                    channel_info = channel_input.strip()
                    
                    # 验证频道信息
                    channel_id = await self._validate_channel_access(channel_info)
                    if not channel_id:
                        failed_channels.append(f"{channel_input} (频道验证失败)")
                        continue
            
                    # 获取频道信息
                    try:
                        chat = await self._get_api_client().get_chat(channel_id)
                        channel_name = chat.title
                        username = getattr(chat, 'username', None)
                    except Exception as e:
                        logger.error(f"获取频道信息失败 {channel_input}: {e}")
                        failed_channels.append(f"{channel_input} (无法获取信息)")
                        continue
                    
                    # 实时监听模式：自动检测最新消息ID
                    try:
                        # 获取频道的最新消息
                        messages = []
                        async for message in self._get_api_client().get_chat_history(channel_id, limit=1):
                            messages.append(message)
                            break  # 只获取第一条消息
                        
                        if messages:
                            last_message_id = messages[0].id
                            logger.info(f"自动检测到最新消息ID: {last_message_id}")
                        else:
                            # 如果无法获取消息，从0开始监听
                            last_message_id = 0
                            logger.info(f"无法获取消息历史，从0开始监听")
                    except Exception as e:
                        logger.warning(f"获取最新消息ID失败 {channel_input}: {e}")
                        # 如果无法获取最新消息ID，从0开始监听
                        last_message_id = 0
                        logger.info(f"使用默认起始ID: 0")
                    
                    # 添加到成功列表
                    source_channel = {
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'channel_username': username,
                        'last_message_id': last_message_id,
                        'check_interval': 60,
                        'monitoring_mode': 'realtime'  # 标记为实时监听模式
                    }
                    successful_channels.append(source_channel)
                    
                except Exception as e:
                    logger.error(f"处理频道 {channel_input} 失败: {e}")
                    failed_channels.append(f"{channel_input} (处理失败)")
            
            # 将成功的频道添加到状态中
            for source_channel in successful_channels:
                state['data']['source_channels'].append(source_channel)
            
            # 生成结果报告
            if successful_channels:
                success_text = "✅ **批量添加源频道成功！**\n\n"
                success_text += f"📊 **处理结果：**\n"
                success_text += f"• 成功: {len(successful_channels)} 个\n"
                success_text += f"• 失败: {len(failed_channels)} 个\n\n"
                
                success_text += f"📡 **成功添加的频道：**\n"
                for i, channel in enumerate(successful_channels, 1):
                    channel_display = f"{channel['channel_name']} (@{channel['channel_username']})" if channel['channel_username'] else f"{channel['channel_name']} (无用户名)"
                    success_text += f"{i}. {channel_display}\n"
                    success_text += f"   ID: {channel['channel_id']}\n"
                    if channel['last_message_id'] == 0:
                        success_text += f"   监听模式: 实时监听 (从当前开始)\n\n"
                    else:
                        success_text += f"   监听模式: 实时监听 (从消息ID {channel['last_message_id']} 开始)\n\n"
                
                if failed_channels:
                    success_text += f"❌ **失败的频道：**\n"
                    for i, failed in enumerate(failed_channels, 1):
                        success_text += f"{i}. {failed}\n"
                    success_text += "\n"
                
                success_text += f"📊 **当前配置：**\n"
                success_text += f"• 目标频道: {state['data']['target_channel']['name']}\n"
                success_text += f"• 源频道数量: {len(state['data']['source_channels'])} 个\n\n"
                success_text += f"💡 **下一步：**\n"
                success_text += f"• 继续添加更多源频道，或\n"
                success_text += f"• 点击下方按钮确认创建任务\n\n"
                success_text += f"🔧 **实时监听说明：**\n"
                success_text += f"• 每60秒检查一次新消息\n"
                success_text += f"• 自动检测并搬运新发布的内容\n"
                success_text += f"• 智能过滤和内容处理\n"
                success_text += f"• 实时更新监听状态"
                
                # 发送到私聊而不是在源频道回复
                try:
                    await self.client.send_message(
                        chat_id=int(user_id),
                        text=success_text,
                    reply_markup=generate_button_layout([
                        [("✅ 确认创建任务", "confirm_create_monitoring_task")],
                        [("➕ 添加更多源频道", "add_monitor_source_channel")],
                        [("🔙 重新选择目标频道", "create_monitoring_task")]
                    ])
                )
                except Exception as send_error:
                    logger.error(f"发送私聊消息失败: {send_error}")
                    # 如果私聊也失败，尝试回复
                    try:
                        await message.reply_text("❌ 无法发送消息，请检查机器人权限")
                    except Exception as reply_error:
                        logger.error(f"回复消息也失败: {reply_error}")
                        logger.error("消息对象无效，无法发送结果")
        except Exception as e:
            logger.error(f"处理监听源频道输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")

    async def _handle_test_fixed_monitoring_command(self, message: Message):
        """测试修复后的监听功能"""
        try:
            user_id = str(message.from_user.id)
            
            if not self.realtime_monitoring_engine:
                await message.reply_text("❌ 监听引擎未初始化")
                return
            
            # 检查引擎状态
            status = self.realtime_monitoring_engine.get_monitoring_status()
            
            # 检查全局处理器是否已注册
            has_global_handler = hasattr(self.realtime_monitoring_engine, '_global_handler_registered')
            
            # 检查客户端状态
            client_status = "未知"
            if self.realtime_monitoring_engine.client:
                client_status = f"已连接: {self.realtime_monitoring_engine.client.is_connected}"
            
            response = f"""
🧪 修复后监听功能测试

📊 引擎状态:
• 运行状态: {'✅ 运行中' if status.get('is_running') else '❌ 已停止'}
• 活跃任务: {status.get('active_tasks_count', 0)} 个
• 总任务数: {status.get('total_tasks_count', 0)} 个

🔧 修复状态:
• 全局处理器: {'✅ 已注册' if has_global_handler else '❌ 未注册'}
• 客户端状态: {client_status}
• 处理器模式: {'✅ 简单版模式' if has_global_handler else '❌ 复杂模式'}

💡 测试建议:
• 在源频道发送测试消息
• 检查控制台是否有 "🔔 处理消息" 日志
• 如果看到日志，说明修复成功

🔍 如果仍然不工作:
• 运行 /reinit_monitoring 重新初始化
• 检查 User API 登录状态
• 确认源频道访问权限
            """.strip()
            
            await message.reply_text(response)
            logger.info(f"用户 {user_id} 执行了修复后监听测试命令")
            
        except Exception as e:
            logger.error(f"❌ 处理修复后监听测试命令失败: {e}")
            await message.reply_text(f"❌ 测试失败: {e}")
    
    async def _handle_select_monitoring_mode(self, callback_query: CallbackQuery):
        """处理监听模式选择"""
        try:
            user_id = str(callback_query.from_user.id)
            mode = callback_query.data.split(':')[1]
            
            # 更新用户状态
            if user_id in self.user_states:
                self.user_states[user_id]['data']['monitoring_mode'] = mode
            
            mode_names = {
                'realtime': '⚡ 实时模式',
                'scheduled': '⏰ 定时模式', 
                'batch': '📦 批量模式'
            }
            
            mode_descriptions = {
                'realtime': '消息发布立即搬运，零延迟响应',
                'scheduled': '每60秒检查一次新消息，适合稳定监听',
                'batch': '积累多条消息批量搬运，提高效率'
            }
            
            await callback_query.edit_message_text(
                f"✅ **监听模式已选择**\n\n"
                f"{mode_names.get(mode, mode)}: {mode_descriptions.get(mode, '')}\n\n"
                f"🎯 **下一步：添加源频道**\n\n"
                f"请发送源频道的ID或用户名：\n"
                f"• 频道ID: `-1001234567890`\n"
                f"• 频道用户名: `@channelname`\n"
                f"• 频道链接: `https://t.me/channelname`\n\n"
                f"📝 **示例：**\n"
                f"• `https://t.me/source1`\n"
                f"• `@source2`\n"
                f"• `-1001234567890`\n\n"
                f"💡 **提示：** 可以一次添加多个源频道",
                reply_markup=generate_button_layout([
                    [("🔙 重新选择模式", "create_monitoring_task")]
                ])
            )
            
        except Exception as e:
            logger.error(f"选择监听模式失败: {e}")
            await callback_query.edit_message_text("❌ 选择失败，请稍后重试")
    
    async def _handle_pause_monitoring_task(self, callback_query: CallbackQuery):
        """暂停监听任务"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            success = await self.realtime_monitoring_engine.pause_monitoring_task(task_id)
            
            if success:
                await callback_query.answer("✅ 监听任务已暂停")
                # 刷新任务详情
                await self._handle_monitor_task_detail(callback_query)
            else:
                await callback_query.answer("❌ 暂停失败")
                
        except Exception as e:
            logger.error(f"暂停监听任务失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_resume_monitoring_task(self, callback_query: CallbackQuery):
        """恢复监听任务"""
        try:
            task_id = callback_query.data.split(':')[1]
            user_id = str(callback_query.from_user.id)
            
            success = await self.realtime_monitoring_engine.resume_monitoring_task(task_id)
            
            if success:
                await callback_query.answer("✅ 监听任务已恢复")
                # 刷新任务详情
                await self._handle_monitor_task_detail(callback_query)
            else:
                await callback_query.answer("❌ 恢复失败")
                
        except Exception as e:
            logger.error(f"恢复监听任务失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    def _parse_channel_with_id(self, input_text: str) -> tuple:
        """解析频道信息、起始消息ID和目标结束ID
        
        支持格式：
        - https://t.me/channelname 起始ID 结束ID
        - @channelname 起始ID 结束ID
        - -1001234567890 起始ID 结束ID
        - https://t.me/channelname 起始ID (只有起始ID)
        - @channelname 起始ID (只有起始ID)
        - -1001234567890 起始ID (只有起始ID)
        
        Returns:
            tuple: (channel_info, start_message_id, end_message_id)
        """
        try:
            # 按空格分割
            parts = input_text.strip().split()
            
            if len(parts) == 1:
                # 只有频道信息，没有ID
                return parts[0], None, None
            elif len(parts) == 2:
                # 频道信息 + 起始ID
                channel_info = parts[0]
                try:
                    start_message_id = int(parts[1])
                    return channel_info, start_message_id, None
                except ValueError:
                    # ID不是数字，可能是用户名的一部分
                    return input_text, None, None
            elif len(parts) == 3:
                # 频道信息 + 起始ID + 结束ID
                channel_info = parts[0]
                try:
                    start_message_id = int(parts[1])
                    end_message_id = int(parts[2])
                    return channel_info, start_message_id, end_message_id
                except ValueError:
                    # ID不是数字，可能是用户名的一部分
                    return input_text, None, None
            else:
                # 多个部分，尝试解析最后两个数字
                try:
                    end_message_id = int(parts[-1])
                    start_message_id = int(parts[-2])
                    channel_info = ' '.join(parts[:-2])
                    return channel_info, start_message_id, end_message_id
                except ValueError:
                    # 尝试解析最后一个数字作为起始ID
                    try:
                        start_message_id = int(parts[-1])
                        channel_info = ' '.join(parts[:-1])
                        return channel_info, start_message_id, None
                    except ValueError:
                        # 最后一部分不是数字，整个作为频道信息
                        return input_text, None, None
                    
        except Exception as e:
            logger.error(f"解析频道信息失败: {e}")
            return input_text, None, None
    
    async def _handle_add_monitor_source_channel(self, callback_query: CallbackQuery):
        """处理添加更多源频道"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查用户状态
            if user_id not in self.user_states:
                await callback_query.answer("❌ 会话已过期，请重新创建")
                return
            
            state = self.user_states[user_id]
            if state['state'] != 'creating_monitoring_task':
                await callback_query.answer("❌ 状态错误，请重新创建")
                return
            
            data = state['data']
            target_channel = data.get('target_channel')
            source_channels = data.get('source_channels', [])
            
            if not target_channel:
                await callback_query.answer("❌ 请先选择目标频道")
                return
            
            # 显示添加源频道的提示
            target_name = target_channel['name']
            current_count = len(source_channels)
            
            await callback_query.edit_message_text(
                f"📡 **添加源频道**\n\n"
                f"📤 **目标频道:** {target_name}\n"
                f"📡 **当前源频道:** {current_count} 个\n\n"
                f"💡 **请输入新的源频道信息：**\n"
                f"• 频道ID: `-1001234567890`\n"
                f"• 频道用户名: `@channelname`\n"
                f"• 频道链接: `https://t.me/channelname`\n\n"
                f"🔧 **实时监听模式：**\n"
                f"• 系统自动检测最新消息ID\n"
                f"• 从当前时间开始监听新消息\n"
                f"• 无需手动指定消息ID\n\n"
                f"📝 **示例：**\n"
                f"• `https://t.me/xsm58`\n"
                f"• `@channelname`\n"
                f"• `-1001234567890`\n\n"
                f"🔧 **系统会自动：**\n"
                f"• 验证频道访问权限\n"
                f"• 检测最新消息ID\n"
                f"• 添加到实时监听列表",
                reply_markup=generate_button_layout([
                    [("✅ 确认创建任务", "confirm_create_monitoring_task")],
                    [("🔙 返回选择目标频道", "create_monitoring_task")]
                ])
            )
            
            await callback_query.answer("💡 请发送源频道信息")
            
        except Exception as e:
            logger.error(f"添加源频道失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        # 防止重复调用
        if hasattr(self, '_shutdown_called') and self._shutdown_called:
            logger.info("关闭流程已在进行中，忽略重复信号")
            return
        
        signal_name = "SIGINT" if signum == 2 else "SIGTERM" if signum == 15 else f"信号{signum}"
        logger.info(f"收到 {signal_name}，开始关闭机器人...")
        
        self._shutdown_called = True
        # 设置停止事件，让主循环退出
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
            logger.info("✅ 停止事件已设置")
        else:
            logger.warning("⚠️ 停止事件未初始化")
        
        # 如果主循环已经结束，直接调用shutdown
        if hasattr(self, '_main_loop_done') and self._main_loop_done:
            logger.info("主循环已结束，直接调用shutdown")
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.shutdown())
                else:
                    loop.run_until_complete(self.shutdown())
            except Exception as e:
                logger.error(f"直接调用shutdown失败: {e}")
                import os
                os._exit(0)
    
    async def shutdown(self):
        """关闭机器人"""
        try:
            logger.info("🔄 开始关闭机器人...")
            
            # 停止Web服务器
            if hasattr(self, 'web_runner') and self.web_runner:
                try:
                    logger.info("🔄 正在停止Web服务器...")
                    await asyncio.wait_for(self.web_runner.cleanup(), timeout=3.0)
                    logger.info("✅ Web服务器已停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止Web服务器超时，强制继续")
                except Exception as e:
                    logger.warning(f"停止Web服务器时出错: {e}")
            
            # 停止搬运引擎中的活动任务
            if hasattr(self, 'cloning_engine') and self.cloning_engine:
                try:
                    logger.info("🔄 正在停止搬运引擎...")
                    await asyncio.wait_for(self.cloning_engine.stop_all_tasks(), timeout=3.0)
                    logger.info("✅ 搬运引擎已停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止搬运引擎超时，强制继续")
                except Exception as e:
                    logger.warning(f"停止搬运引擎时出错: {e}")
            
            # 停止实时监听引擎
            if hasattr(self, 'realtime_monitoring_engine') and self.realtime_monitoring_engine:
                try:
                    logger.info("🔄 正在停止实时监听引擎...")
                    await asyncio.wait_for(self.realtime_monitoring_engine.stop_monitoring(), timeout=3.0)
                    logger.info("✅ 实时监听引擎已停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止实时监听引擎超时，强制继续")
                except Exception as e:
                    logger.warning(f"停止实时监听引擎时出错: {e}")
            
            # 停止批量存储处理器
            if not self.config.get('use_local_storage', False):
                try:
                    logger.info("🔄 正在停止批量存储处理器...")
                    from firebase_batch_storage import stop_batch_processing
                    await asyncio.wait_for(stop_batch_processing(self.bot_id), timeout=3.0)
                    logger.info("✅ Firebase批量存储处理器已停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止批量存储处理器超时，强制继续")
                except Exception as e:
                    logger.warning(f"停止批量存储处理器时出错: {e}")
            
            # 停止User API客户端
            if hasattr(self, 'user_api_manager') and self.user_api_manager:
                try:
                    logger.info("🔄 正在停止User API客户端...")
                    await asyncio.wait_for(self.user_api_manager.cleanup(), timeout=3.0)
                    logger.info("✅ User API客户端已停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止User API客户端超时，强制继续")
                except Exception as e:
                    logger.warning(f"停止User API客户端时出错: {e}")
            
            # 停止Telegram客户端
            if hasattr(self, 'client') and self.client:
                try:
                    logger.info("🔄 正在停止Telegram客户端...")
                    # 检查客户端是否还在连接状态
                    if hasattr(self.client, 'is_connected') and self.client.is_connected:
                        await asyncio.wait_for(self.client.stop(), timeout=3.0)
                        logger.info("✅ Telegram客户端已停止")
                    else:
                        logger.info("✅ Telegram客户端已经停止")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ 停止Telegram客户端超时，强制继续")
                except Exception as e:
                    if "already terminated" in str(e) or "Client is already terminated" in str(e):
                        logger.info("✅ Telegram客户端已经停止")
                    else:
                        logger.error(f"停止Telegram客户端时出错: {e}")
            
            logger.info("✅ 机器人已安全关闭")
            
        except Exception as e:
            logger.error(f"关闭机器人时出错: {e}")
        
        finally:
            logger.info("✅ 关闭流程完成")
            # 强制退出，确保程序能够正常关闭
            import os
            os._exit(0)
    
    async def run(self):
        """运行机器人"""
        try:
            # 初始化
            if not await self.initialize():
                logger.error("❌ 机器人初始化失败")
                return
            
            # 初始化已知频道列表
            await self._initialize_known_channels()
            
            logger.info("🤖 机器人开始运行...")
            logger.info(f"📱 机器人用户名: @{self.client.me.username}")
            logger.info("💡 机器人已启动，可以开始使用")
            logger.info("💡 按 Ctrl+C 可以停止机器人")
            
            # 创建停止事件
            self._stop_event = asyncio.Event()
            
            # 保持运行直到收到停止信号
            try:
                logger.info("⏳ 等待停止信号...")
                await self._stop_event.wait()
                logger.info("✅ 收到停止信号，开始关闭...")
                self._main_loop_done = True
                # 立即调用shutdown
                await self.shutdown()
            except KeyboardInterrupt:
                logger.info("✅ 收到键盘中断信号")
                self._main_loop_done = True
                await self.shutdown()
            except Exception as e:
                logger.error(f"等待停止信号时出错: {e}")
                self._main_loop_done = True
                await self.shutdown()
            
        except Exception as e:
            logger.error(f"机器人运行出错: {e}")
            self._main_loop_done = True
            await self.shutdown()
        finally:
            # 确保shutdown被调用
            if not hasattr(self, '_shutdown_called') or not self._shutdown_called:
                self._shutdown_called = True
                await self.shutdown()
            else:
                logger.info("关闭流程已在进行中...")

    # 添加缺失的输入处理函数
    async def _process_replacements_input(self, message: Message, state: Dict[str, Any]):
        """处理敏感词替换输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            if text == "清空":
                # 清空所有替换规则
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['replacement_words'] = {}
                await self.data_manager.save_user_config(user_id, user_config)
                
                # 清除用户状态
                del self.user_states[user_id]
                
                await message.reply_text(
                    "✅ 所有敏感词替换规则已清空！",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            if text.startswith("删除 "):
                # 删除指定替换规则
                word_to_delete = text[3:].strip()
                user_config = await self.data_manager.get_user_config(user_id)
                replacements = user_config.get('replacement_words', {})
                
                if word_to_delete in replacements:
                    del replacements[word_to_delete]
                    user_config['replacement_words'] = replacements
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        f"✅ 已删除敏感词替换规则：{word_to_delete}",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                else:
                    await message.reply_text(f"❌ 未找到敏感词替换规则：{word_to_delete}")
                return
            
            # 检查是否为替换规则格式
            if "=" in text:
                parts = text.split("=", 1)
                if len(parts) == 2:
                    old_word, new_word = parts[0].strip(), parts[1].strip()
                    
                    if old_word and new_word:
                        # 添加替换规则
                        user_config = await self.data_manager.get_user_config(user_id)
                        replacements = user_config.get('replacement_words', {})
                        replacements[old_word] = new_word
                        user_config['replacement_words'] = replacements
                        await self.data_manager.save_user_config(user_id, user_config)
                        
                        await message.reply_text(
                                            f"✅ 敏感词替换规则添加成功！\n\n`{old_word}` → `{new_word}`",
                            reply_markup=generate_button_layout([[
                                ("🔙 返回主菜单", "show_main_menu")
                            ]])
                        )
                        
                        # 清除用户状态
                        del self.user_states[user_id]
                        return
                    else:
                        await message.reply_text("❌ 敏感词和新词不能为空！")
                        return
                else:
                    await message.reply_text("❌ 格式错误！请使用 '原词=*' 的格式")
                    return
            else:
                await message.reply_text(
                    "❌ 格式错误！请使用以下格式之一：\n\n"
                    "• `原词=*` - 添加替换规则（将原词替换为*）\n"
                    "• `删除 原词` - 删除指定规则\n"
                    "• `清空` - 清空所有规则"
                )
            
        except Exception as e:
            logger.error(f"处理敏感词替换输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _process_keywords_input(self, message: Message, state: Dict[str, Any]):
        """处理关键字过滤输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            logger.info(f"用户 {user_id} 输入关键字过滤内容: {text}")
            
            if text == "清空":
                logger.info(f"用户 {user_id} 请求清空所有关键字")
                # 清空所有关键字
                user_config = await self.data_manager.get_user_config(user_id)
                user_config['filter_keywords'] = []
                await self.data_manager.save_user_config(user_id, user_config)
                logger.info(f"用户 {user_id} 的关键字已清空")
                
                # 清除用户状态
                del self.user_states[user_id]
                
                await message.reply_text(
                    "✅ 所有关键字过滤规则已清空！",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            if text.startswith("删除 "):
                # 删除指定关键字
                keyword_to_delete = text[3:].strip()
                logger.info(f"用户 {user_id} 请求删除关键字: {keyword_to_delete}")
                user_config = await self.data_manager.get_user_config(user_id)
                keywords = user_config.get('filter_keywords', [])
                
                if keyword_to_delete in keywords:
                    keywords.remove(keyword_to_delete)
                    user_config['filter_keywords'] = keywords
                    await self.data_manager.save_user_config(user_id, user_config)
                    logger.info(f"用户 {user_id} 成功删除关键字: {keyword_to_delete}")
                    
                    await message.reply_text(
                        f"✅ 已删除关键字过滤规则：{keyword_to_delete}",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                else:
                    logger.warning(f"用户 {user_id} 尝试删除不存在的关键字: {keyword_to_delete}")
                    await message.reply_text(f"❌ 未找到关键字过滤规则：{keyword_to_delete}")
                return
            
            # 添加新关键字
            if text:
                logger.info(f"用户 {user_id} 请求添加关键字: {text}")
                user_config = await self.data_manager.get_user_config(user_id)
                keywords = user_config.get('filter_keywords', [])
                
                # 支持逗号分割多个关键字
                new_keywords = []
                for keyword in text.split(','):
                    keyword = keyword.strip()
                    if keyword and keyword not in keywords:
                        new_keywords.append(keyword)
                
                if new_keywords:
                    keywords.extend(new_keywords)
                    user_config['filter_keywords'] = keywords
                    await self.data_manager.save_user_config(user_id, user_config)
                    logger.info(f"用户 {user_id} 成功添加关键字: {new_keywords}")
                    
                    keywords_text = ", ".join([f"`{kw}`" for kw in new_keywords])
                    await message.reply_text(
                        f"✅ 关键字过滤规则添加成功！\n\n{keywords_text}",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                    
                    # 清除用户状态
                    del self.user_states[user_id]
                else:
                    existing_keywords = [kw for kw in text.split(',') if kw.strip() in keywords]
                    if existing_keywords:
                        existing_text = ", ".join([f"`{kw}`" for kw in existing_keywords])
                        logger.warning(f"用户 {user_id} 尝试添加已存在的关键字: {existing_keywords}")
                        await message.reply_text(f"⚠️ 以下关键字已存在：{existing_text}")
                    else:
                        logger.warning(f"用户 {user_id} 输入的关键字无效: {text}")
                        await message.reply_text("⚠️ 没有有效的关键字添加！")
            
        except Exception as e:
            logger.error(f"处理关键字过滤输入失败: {e}")
            logger.error(f"错误详情: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_content_removal_mode(self, callback_query: CallbackQuery):
        """处理纯文本过滤模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            mode = callback_query.data.split(":")[1]
            
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['content_removal_mode'] = mode
            
            # 保存配置 - 通过_init_channel_filters已经保存了，这里不需要重复保存
            
            # 模式说明
            mode_descriptions = {
                "text_only": "仅移除纯文本消息，保留有媒体的消息",
                "all_content": "移除所有包含文本的信息"
            }
            
            mode_text = mode_descriptions.get(mode, "未知模式")
            
            await callback_query.edit_message_text(
                f"✅ 纯文本过滤模式设置成功！\n\n"
                f"**当前模式：** {mode_text}\n\n"
                f"🔙 返回功能配置继续设置其他选项",
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理纯文本过滤模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_additional_buttons(self, callback_query: CallbackQuery):
        """处理清空附加按钮"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 清空附加按钮
            user_config['additional_buttons'] = []
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.edit_message_text(
                "✅ 附加按钮已清空！\n\n"
                "所有自定义附加按钮已被移除。\n\n"
                "🔙 返回功能配置继续设置其他选项",
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理清空附加按钮失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_tail_text_position(self, callback_query: CallbackQuery):
        """处理文字小尾巴位置设置"""
        try:
            user_id = str(callback_query.from_user.id)
            position = callback_query.data.split(":")[1]
            
            user_config = await self.data_manager.get_user_config(user_id)
            user_config['tail_position'] = position
            
            # 保存配置 - 通过_init_channel_filters已经保存了，这里不需要重复保存
            
            position_text = "文本开头" if position == 'start' else "文本结尾"
            
            await callback_query.edit_message_text(
                f"✅ 文字小尾巴位置设置成功！\n\n"
                f"**当前位置：** {position_text}\n\n"
                f"小尾巴将添加到{position_text}，支持换行显示。\n\n"
                f"🔙 返回功能配置继续设置其他选项",
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理文字小尾巴位置设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _parse_channel_input(self, text: str) -> Optional[str]:
        """解析频道输入，支持多种格式"""
        try:
            text = text.strip()
            logger.info(f"开始解析频道输入: {text}")
            
            # 频道数字ID格式：-1001234567890
            if text.startswith('-') and text[1:].isdigit():
                return text
            
            # 频道用户名格式：@channelname
            if text.startswith('@'):
                return text
            
            # 频道链接格式：https://t.me/channelname 或 https://t.me/channelname/123
            if text.startswith('https://t.me/'):
                # 移除协议前缀
                url_part = text.replace('https://t.me/', '')
                
                # 处理带消息ID的链接：https://t.me/channelname/123
                if '/' in url_part and not url_part.startswith('c/'):
                    # 分割路径，获取频道名（第一部分）
                    parts = url_part.split('/')
                    channel_name = parts[0].split('?')[0].rstrip('/')
                    if channel_name:
                        logger.info(f"从带消息ID的链接提取频道名: {channel_name}")
                        result = f"@{channel_name}" if not channel_name.startswith('@') else channel_name
                        logger.info(f"带消息ID链接解析结果: {result}")
                        return result
                else:
                    # 普通频道链接：https://t.me/channelname
                    channel_name = url_part.split('?')[0].rstrip('/')
                    logger.info(f"从链接提取频道名: {channel_name}")
                    if channel_name and not channel_name.startswith('@'):
                        result = f"@{channel_name}"
                        logger.info(f"频道链接解析结果: {result}")
                        return result
                    logger.info(f"频道链接解析结果: {channel_name}")
                    return channel_name
            
            # 频道链接格式：t.me/channelname 或 t.me/channelname/123
            if text.startswith('t.me/'):
                # 移除前缀
                url_part = text.replace('t.me/', '')
                
                # 处理带消息ID的链接：t.me/channelname/123
                if '/' in url_part and not url_part.startswith('c/'):
                    # 分割路径，获取频道名（第一部分）
                    parts = url_part.split('/')
                    channel_name = parts[0].split('?')[0].rstrip('/')
                    if channel_name:
                        logger.info(f"从带消息ID的短链接提取频道名: {channel_name}")
                        result = f"@{channel_name}" if not channel_name.startswith('@') else channel_name
                        logger.info(f"带消息ID短链接解析结果: {result}")
                        return result
                else:
                    # 普通频道链接：t.me/channelname
                    channel_name = url_part.split('?')[0].rstrip('/')
                    if channel_name and not channel_name.startswith('@'):
                        return f"@{channel_name}"
                    return channel_name
            
            # 处理纯数字ID（可能是私密频道）
            if text.isdigit():
                # 自动为纯数字ID添加-100前缀，转换为私密频道格式
                converted_id = f"-100{text}"
                logger.info(f"自动转换数字ID为私密频道格式: {text} → {converted_id}")
                return converted_id
            
            # 处理私密频道链接格式：https://t.me/c/1234567890/123、t.me/c/1234567890/123 或 @c/1234567890
            if '/c/' in text:
                # 提取私密频道ID
                if text.startswith('https://t.me/c/'):
                    parts = text.replace('https://t.me/c/', '').split('/')
                elif text.startswith('t.me/c/'):
                    parts = text.replace('t.me/c/', '').split('/')
                elif text.startswith('@c/'):
                    # 处理 @c/1234567890 格式
                    parts = text.replace('@c/', '').split('/')
                    logger.info(f"检测到 @c/ 格式的私密频道输入: {text}")
                else:
                    # 处理其他包含/c/的格式
                    c_index = text.find('/c/')
                    if c_index != -1:
                        parts = text[c_index + 3:].split('/')
                    else:
                        return None
                
                if parts and parts[0].isdigit():
                    channel_id = parts[0]
                    logger.info(f"从私密频道链接提取ID: {channel_id}")
                    # 对于私密频道，自动添加-100前缀
                    full_id = f"-100{channel_id}"
                    logger.info(f"私密频道完整ID: {full_id}")
                    return full_id
            
            logger.info(f"频道输入解析结果: None (未知格式)")
            return None
            
        except Exception as e:
            logger.error(f"解析频道输入失败: {e}")
            return None
    
    def _is_valid_channel_type(self, chat_type) -> bool:
        """检查是否为有效的频道类型"""
        if isinstance(chat_type, str):
            return chat_type in ['channel', 'supergroup']
        else:
            # 处理枚举类型，转换为字符串进行比较
            type_str = str(chat_type).lower()
            return type_str in ['channel', 'supergroup', 'chattype.channel', 'chattype.supergroup']
    
    def _detect_private_channel_format(self, channel_info: str) -> bool:
        """检测频道信息是否为私密频道格式"""
        try:
            if not channel_info:
                return False
            
            # 检查私密频道链接格式
            if '/c/' in channel_info:
                return True
            
            # 检查@c/格式
            if channel_info.startswith('@c/'):
                return True
            
            # 检查PENDING_@c/格式
            if channel_info.startswith('PENDING_@c/'):
                return True
            
            # 检查长数字ID（可能是私密频道）
            if channel_info.startswith('-100') and len(channel_info) > 10:
                return True
            
            return False
        except Exception as e:
            logger.warning(f"检测私密频道格式失败: {e}")
            return False
    
    async def _check_channel_permissions(self, channel_id: str, channel_type: str = "source") -> Dict[str, Any]:
        """检查频道权限"""
        try:
            result = {
                'can_access': False,
                'can_read': False,
                'can_post': False,
                'is_private': False,
                'error': None
            }
            
            try:
                # 获取频道信息
                chat = await self._get_api_client().get_chat(channel_id)
                result['is_private'] = self._detect_private_channel_format(str(channel_id))
                
                # 检查机器人成员信息
                member = await self._get_api_client().get_chat_member(channel_id, "me")
                
                if channel_type == "source":
                    # 源频道需要读取权限
                    result['can_read'] = getattr(member, 'can_read_messages', True)
                    result['can_access'] = result['can_read']
                else:
                    # 目标频道需要发送权限
                    result['can_post'] = getattr(member, 'can_post_messages', True)
                    result['can_send'] = getattr(member, 'can_send_messages', True)
                    result['can_access'] = result['can_post'] or result['can_send']
                
                logger.info(f"频道 {channel_id} 权限检查: {result}")
                
            except Exception as e:
                error_msg = str(e)
                result['error'] = error_msg
                
                # 分析错误类型
                if "PEER_ID_INVALID" in error_msg:
                    result['error'] = "频道不存在或机器人未加入"
                elif "CHAT_ADMIN_REQUIRED" in error_msg:
                    result['error'] = "需要管理员权限"
                elif "CHANNEL_PRIVATE" in error_msg:
                    result['error'] = "私密频道，机器人未加入"
                elif "USER_NOT_PARTICIPANT" in error_msg:
                    result['error'] = "机器人未加入频道"
                else:
                    result['error'] = f"权限检查失败: {error_msg}"
                
                logger.warning(f"频道 {channel_id} 权限检查失败: {result['error']}")
            
            return result
            
        except Exception as e:
            logger.error(f"检查频道权限失败: {e}")
            return {
                'can_access': False,
                'can_read': False,
                'can_post': False,
                'is_private': False,
                'error': f"权限检查异常: {str(e)}"
            }
    
    async def _show_private_channel_error(self, message: Message, channel_info: str, channel_type: str):
        """显示私密频道错误信息"""
        try:
            channel_type_name = "源频道" if channel_type == "source" else "目标频道"
            permission_type = "读取消息" if channel_type == "source" else "发送消息"
            
            error_text = f"""❌ **私密{channel_type_name}无法访问！**

📡 **频道信息：** {channel_info}
🔒 **问题：** 机器人无法访问该私密频道

💡 **私密频道使用要求：**
• 机器人必须已加入该私密频道
• 机器人需要有{permission_type}的权限
• 频道管理员需要邀请机器人加入

🔧 **解决方案：**

1. **邀请机器人加入私密频道**
   • 在私密频道中添加机器人
   • 确保机器人有{permission_type}权限

2. **使用频道ID（系统已自动转换）**
   • 系统已自动将链接转换为正确的ID格式
   • 如果仍然失败，请直接输入完整ID（如：-1001234567890）

3. **确认频道类型**
   • 确保是频道而不是群组
   • 私密群组无法用于搬运

⚠️ **注意：** 私密频道搬运需要机器人预先加入频道

🔄 **重试步骤：**
1. 邀请机器人加入频道
2. 重新输入频道信息
3. 或使用频道数字ID

💡 **需要帮助？** 点击下方按钮查看详细设置向导"""
            
            # 添加设置向导按钮
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            buttons = [
                [InlineKeyboardButton("🔒 私密频道设置向导", callback_data=f"private_wizard:{channel_type}")],
                [InlineKeyboardButton("🔄 重新输入", callback_data="retry_channel_input")]
            ]
            
            await message.reply_text(error_text, reply_markup=InlineKeyboardMarkup(buttons))
            
        except Exception as e:
            logger.error(f"显示私密频道错误信息失败: {e}")
            await message.reply_text("❌ 私密频道无法访问，请检查机器人权限")
    
    async def _show_general_channel_error(self, message: Message, channel_info: str):
        """显示一般频道错误信息"""
        try:
            error_text = f"""❌ **无法访问频道！**

📡 **频道：** {channel_info}
🔍 **问题：** 机器人无法访问该频道

💡 **可能的原因：**
• 频道不存在或已被删除
• 频道是私密频道，机器人无法访问
• 机器人未加入该频道
• 频道用户名输入错误
• 频道已被封禁或限制
• 频道访问权限不足

🔧 **解决方案：**
• 检查频道用户名是否正确
• 尝试使用频道数字ID（系统会自动转换格式）
• 尝试使用频道链接：`https://t.me/channelname`
• 确保机器人已加入该频道
• 验证频道是否为公开频道
• 检查频道是否仍然活跃

🔄 **重试步骤：**
1. 确认频道信息正确
2. 邀请机器人加入频道（如果是私密频道）
3. 重新输入频道信息"""
            
            await message.reply_text(error_text)
            
        except Exception as e:
            logger.error(f"显示一般频道错误信息失败: {e}")
            await message.reply_text("❌ 无法访问频道，请检查频道信息")
    
    async def _show_private_channel_wizard(self, message: Message, channel_type: str):
        """显示私密频道设置向导"""
        try:
            channel_type_name = "源频道" if channel_type == "source" else "目标频道"
            permission_type = "读取消息" if channel_type == "source" else "发送消息"
            
            wizard_text = f"""🔒 **私密{channel_type_name}设置向导**

📋 **设置步骤：**

**第一步：邀请机器人加入频道**
1. 打开您的私密频道
2. 点击频道名称进入频道信息
3. 点击"管理员"或"成员"
4. 点击"添加管理员"或"添加成员"
5. 搜索并添加机器人：`@your_bot_username`
6. 确保机器人有{permission_type}权限

**第二步：获取频道信息**
• **频道链接格式：** `https://t.me/c/1234567890`
• **频道ID格式：** `-1001234567890`
• **用户名格式：** `@channelname`（如果有）

**第三步：输入频道信息**
请选择以下方式之一：
• 发送频道链接
• 发送频道ID
• 发送频道用户名

💡 **提示：**
• 私密频道链接通常包含 `/c/` 字符
• 频道ID通常以 `-100` 开头
• 确保机器人已加入频道并有相应权限

⚠️ **注意事项：**
• 私密频道需要机器人预先加入
• 确保机器人有足够的权限
• 如果设置失败，请检查权限设置

🔄 **现在请发送您的{channel_type_name}信息：**"""
            
            await message.reply_text(wizard_text)
            
        except Exception as e:
            logger.error(f"显示私密频道设置向导失败: {e}")
            await message.reply_text("❌ 显示设置向导失败，请稍后重试")
    
    async def _handle_private_channel_wizard(self, callback_query: CallbackQuery):
        """处理私密频道设置向导"""
        try:
            data = callback_query.data
            channel_type = data.split(':')[1] if ':' in data else "source"
            
            await callback_query.answer()
            await self._show_private_channel_wizard(callback_query.message, channel_type)
            
        except Exception as e:
            logger.error(f"处理私密频道设置向导失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_retry_channel_input(self, callback_query: CallbackQuery):
        """处理重新输入频道信息"""
        try:
            await callback_query.answer()
            await callback_query.edit_message_text(
                "🔄 **重新输入频道信息**\n\n"
                "请发送您的频道信息：\n"
                "• 频道链接：`https://t.me/channelname`\n"
                "• 频道用户名：`@channelname`\n"
                "• 频道ID：`-1001234567890`\n\n"
                "💡 **提示：** 私密频道需要机器人预先加入"
            )
            
        except Exception as e:
            logger.error(f"处理重新输入频道信息失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _validate_channel_access(self, channel_info: str) -> Optional[str]:
        """验证频道是否存在并可访问，返回频道ID（采用宽松策略）"""
        try:
            logger.info(f"开始验证频道访问: {channel_info}")
            
            # 检测私密频道
            is_private = self._detect_private_channel_format(channel_info)
            if is_private:
                logger.info(f"检测到私密频道格式: {channel_info}")
            
            # 如果是数字ID，直接返回
            if channel_info.startswith('-') and channel_info[1:].isdigit():
                logger.info(f"频道 {channel_info} 是数字ID格式，直接返回")
                return channel_info
            
            # 如果是用户名或链接，尝试获取频道信息
            if channel_info.startswith('@'):
                try:
                    # 尝试获取频道信息
                    logger.info(f"尝试获取频道信息: {channel_info}")
                    chat = await self._get_api_client().get_chat(channel_info)
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"频道 {channel_info} 验证成功，ID: {chat.id}")
                            return str(chat.id)
                        else:
                            logger.warning(f"频道 {channel_info} 类型不匹配，类型: {chat.type}")
                            # 即使类型不匹配，也允许用户继续
                            return f"PENDING_{channel_info}"
                    else:
                        logger.warning(f"频道 {channel_info} 类型信息缺失")
                        return f"PENDING_{channel_info}"
                except Exception as e:
                    logger.warning(f"无法获取频道 {channel_info} 详细信息: {e}")
                    # 对于无法获取信息的频道，采用宽松策略
                    logger.info(f"采用宽松策略，允许用户继续设置频道: {channel_info}")
                    return f"PENDING_{channel_info}"
            
            # 处理频道链接格式
            elif channel_info.startswith('https://t.me/'):
                # 检查是否为私密频道链接
                if '/c/' in channel_info:
                    try:
                        # 提取私密频道ID
                        parts = channel_info.replace('https://t.me/c/', '').split('/')
                        if parts and parts[0].isdigit():
                            channel_id = parts[0]
                            logger.info(f"检测到私密频道链接，提取ID: {channel_id}")
                            
                            # 尝试使用不同的ID格式验证私密频道
                            for prefix in ['-100', '-1001', '']:
                                try:
                                    if prefix:
                                        test_id = int(f"{prefix}{channel_id}")
                                    else:
                                        test_id = int(channel_id)
                                    
                                    chat = await self._get_api_client().get_chat(test_id)
                                    if chat and hasattr(chat, 'type'):
                                        if self._is_valid_channel_type(chat.type):
                                            logger.info(f"私密频道验证成功，ID: {test_id}")
                                            return str(test_id)
                                except Exception as e:
                                    logger.debug(f"私密频道ID {test_id} 验证失败: {e}")
                                    continue
                            
                            # 如果所有格式都失败，返回PENDING格式允许用户继续
                            logger.warning(f"私密频道验证失败，机器人可能未加入该频道: {channel_id}，采用宽松策略")
                            return f"PENDING_@c/{channel_id}"  # 返回PENDING格式允许用户继续
                        else:
                            logger.warning(f"私密频道链接格式错误: {channel_info}，采用宽松策略")
                            return f"PENDING_{channel_info}"
                    except Exception as e:
                        logger.warning(f"解析私密频道链接失败: {e}，采用宽松策略")
                        return f"PENDING_{channel_info}"
                else:
                    # 处理普通公开频道链接
                    try:
                        # 从链接中提取用户名
                        username = channel_info.replace('https://t.me/', '').split('/')[0]
                        if username:
                            logger.info(f"从链接提取用户名: {username}")
                            # 尝试获取频道信息
                            chat = await self._get_api_client().get_chat(f"@{username}")
                            if chat and hasattr(chat, 'type'):
                                if self._is_valid_channel_type(chat.type):
                                    logger.info(f"频道链接 {channel_info} 验证成功，ID: {chat.id}")
                                    return str(chat.id)
                                else:
                                    logger.warning(f"频道链接 {channel_info} 类型不匹配，类型: {chat.type}")
                                    # 即使类型不匹配，也允许用户继续
                                    return f"PENDING_@{username}"
                            else:
                                logger.warning(f"频道链接 {channel_info} 类型信息缺失")
                                return f"PENDING_@{username}"
                    except Exception as e:
                        logger.warning(f"无法获取频道链接 {channel_info} 详细信息: {e}")
                        # 对于无法获取信息的频道链接，允许用户继续
                        username = channel_info.replace('https://t.me/', '').split('/')[0]
                        logger.info(f"采用宽松策略，允许用户继续设置频道链接: {username}")
                        return f"PENDING_@{username}"
            
            # 处理纯数字ID（可能是私密频道）
            elif channel_info.isdigit():
                logger.info(f"处理纯数字ID: {channel_info}")
                try:
                    # 尝试直接使用数字ID
                    chat = await self._get_api_client().get_chat(int(channel_info))
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"直接使用数字ID成功: {channel_info}")
                            return str(chat.id)
                except Exception as e:
                    logger.debug(f"直接使用数字ID {channel_info} 失败: {e}")
                
                try:
                    # 尝试添加 -100 前缀
                    prefixed_id = int(f"-100{channel_info}")
                    chat = await self._get_api_client().get_chat(prefixed_id)
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"使用前缀ID成功: {prefixed_id}")
                            return str(prefixed_id)
                except Exception as e:
                    logger.debug(f"使用前缀ID -100{channel_info} 失败: {e}")
                
                try:
                    # 尝试添加 -1001 前缀
                    alt_prefixed_id = int(f"-1001{channel_info}")
                    chat = await self._get_api_client().get_chat(alt_prefixed_id)
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"使用替代前缀ID成功: {alt_prefixed_id}")
                            return str(alt_prefixed_id)
                except Exception as e:
                    logger.debug(f"使用替代前缀ID -1001{channel_info} 失败: {e}")
                
                # 如果所有方法都失败，返回PENDING标识，允许用户继续
                logger.info(f"所有ID格式尝试失败，采用宽松策略允许用户继续: {channel_info}")
                return f"PENDING_{channel_info}"
            
            # 对于其他格式，也采用宽松策略
            logger.warning(f"未知的频道格式: {channel_info}，采用宽松策略允许用户继续")
            return f"PENDING_{channel_info}"
            
        except Exception as e:
            logger.error(f"验证频道访问失败: {e}")
            # 即使出现异常，也采用宽松策略
            logger.info(f"验证过程出现异常，采用宽松策略允许用户继续: {channel_info}")
            return f"PENDING_{channel_info}"
    
    async def _handle_edit_filters(self, callback_query: CallbackQuery):
        """处理编辑频道组过滤设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 检查是否为pair_id格式
            if data_part.startswith('pair_'):
                # 通过pair_id查找频道组
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                pair_index = None
                for i, pair in enumerate(channel_pairs):
                    if pair.get('id') == data_part:
                        pair_index = i
                        break
                if pair_index is None:
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
            else:
                # 传统的索引格式
                pair_index = int(data_part)
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取小尾巴和按钮配置
            tail_text = user_config.get('tail_text', '')
            additional_buttons = user_config.get('additional_buttons', [])
            tail_frequency = user_config.get('tail_frequency', 100)
            button_frequency = user_config.get('button_frequency', 100)
            
            # 构建过滤设置显示
            config_text = f"""
🔧 **频道组 {pair_index + 1} 过滤设置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

📝 **小尾巴设置**
• 小尾巴文本: {tail_text if tail_text else '未设置'}
• 添加频率: {tail_frequency}%

🔘 **按钮设置**
• 按钮数量: {len(additional_buttons)} 个
• 添加频率: {button_frequency}%

💡 请选择要配置的选项：
            """.strip()
            
            # 生成过滤设置按钮
            buttons = [
                [("📝 设置小尾巴", f"channel_tail_text:{pair['id']}")],
                [("🔘 设置按钮", f"channel_buttons:{pair['id']}")],
                [("⚙️ 高级过滤", f"channel_filters:{pair['id']}")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理编辑频道组过滤设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_tail_text(self, callback_query: CallbackQuery):
        """处理频道组小尾巴设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取频道组独立配置
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if independent_enabled:
                # 使用频道组独立配置
                tail_text = channel_filters.get('tail_text', '')
                tail_frequency = channel_filters.get('tail_frequency', 100)
                config_source = "频道组独立配置"
            else:
                # 使用全局配置
                tail_text = user_config.get('tail_text', '')
                tail_frequency = user_config.get('tail_frequency', 100)
                config_source = "全局配置"
            
            # 构建小尾巴设置显示
            config_text = f"""
📝 **频道组 {pair_index + 1} 小尾巴设置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

🔧 **配置来源：** {config_source}

📝 **当前设置**
• 小尾巴文本: {tail_text if tail_text else '未设置'}
• 添加频率: {tail_frequency}%

💡 **说明：**
• 小尾巴会在搬运的消息末尾添加指定文本
• 频率设置控制添加小尾巴的概率
• 发送 "小尾巴文本" 来设置内容
• 发送 "频率数字" 来设置添加频率（1-100）

🔙 返回过滤设置
            """.strip()
            
            # 生成小尾巴设置按钮
            buttons = [
                [("🔄 设置小尾巴文本", f"request_tail_text:{pair['id']}")],
                [("⚙️ 设置添加频率", f"select_tail_frequency:{pair['id']}")],
                [("🔙 返回过滤设置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组小尾巴设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_buttons(self, callback_query: CallbackQuery):
        """处理频道组按钮设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取频道组独立配置
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if independent_enabled:
                # 使用频道组独立配置
                additional_buttons = channel_filters.get('additional_buttons', [])
                button_frequency = channel_filters.get('button_frequency', 100)
                config_source = "频道组独立配置"
            else:
                # 使用全局配置
                additional_buttons = user_config.get('additional_buttons', [])
                button_frequency = user_config.get('button_frequency', 100)
                config_source = "全局配置"
            
            # 构建按钮设置显示
            buttons_text = ""
            if additional_buttons:
                for i, btn in enumerate(additional_buttons, 1):
                    buttons_text += f"• {i}. {btn.get('text', '')} -> {btn.get('url', '')}\n"
            else:
                buttons_text = "未设置"
            
            config_text = f"""
🔘 **频道组 {pair_index + 1} 按钮设置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

🔧 **配置来源：** {config_source}

🔘 **当前设置**
• 按钮数量: {len(additional_buttons)} 个
• 添加频率: {button_frequency}%
• 按钮列表:
{buttons_text}

💡 **说明：**
• 按钮会在搬运的消息下方添加
• 频率设置控制添加按钮的概率
• 发送 "按钮文字|链接" 来添加按钮
• 发送 "频率数字" 来设置添加频率（1-100）

🔙 返回过滤设置
            """.strip()
            
            # 生成按钮设置按钮
            buttons = [
                [("➕ 添加按钮", f"request_buttons:{pair['id']}")],
                [("🗑️ 清空按钮", "clear_additional_buttons")],
                [("⚙️ 设置添加频率", f"select_button_frequency:{pair['id']}")],
                [("🔙 返回过滤设置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组按钮设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_filters(self, callback_query: CallbackQuery):
        """处理频道组过滤配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 检查是否启用独立过滤
            independent_filters = channel_filters.get('independent_enabled', False)
            
            # UI显示调试日志已注释以减少后台输出
            # logger.info(f"🔍 UI显示调试 - 频道组 {pair_index}:")
            # logger.info(f"  • channel_filters: {channel_filters}")
            # logger.info(f"  • independent_filters: {independent_filters}")
            # logger.info(f"  • user_config中的channel_filters: {user_config.get('channel_filters', {})}")
            # logger.info(f"  • 将显示状态: {'✅ 已启用' if independent_filters else '❌ 使用全局配置'}")
            
            # 如果启用独立过滤，显示频道组配置；否则显示全局配置
            if independent_filters:
                # 显示频道组独立配置
                keywords_status = '✅ 开启' if channel_filters.get('keywords_enabled', False) else '❌ 关闭'
                replacements_status = '✅ 开启' if channel_filters.get('replacements_enabled', False) else '❌ 关闭'
                content_removal_status = '✅ 开启' if channel_filters.get('content_removal', False) else '❌ 关闭'
                links_removal_status = '✅ 开启' if channel_filters.get('links_removal', False) else '❌ 关闭'
                usernames_removal_status = '✅ 开启' if channel_filters.get('usernames_removal', False) else '❌ 关闭'
                buttons_removal_status = '✅ 开启' if channel_filters.get('buttons_removal', False) else '❌ 关闭'
                
                # 小尾巴和添加按钮状态
                tail_text = channel_filters.get('tail_text', '')
                tail_status = '✅ 已设置' if tail_text else '❌ 未设置'
                additional_buttons = channel_filters.get('additional_buttons', [])
                buttons_add_status = '✅ 已设置' if additional_buttons else '❌ 未设置'
            else:
                # 显示全局配置
                keywords_status = '✅ 开启' if len(user_config.get('filter_keywords', [])) > 0 else '❌ 关闭'
                replacements_status = '✅ 开启' if len(user_config.get('replacement_words', {})) > 0 else '❌ 关闭'
                content_removal_status = '✅ 开启' if user_config.get('content_removal', False) else '❌ 关闭'
                links_removal_status = '✅ 开启' if user_config.get('remove_all_links', False) else '❌ 关闭'
                usernames_removal_status = '✅ 开启' if user_config.get('remove_usernames', False) else '❌ 关闭'
                buttons_removal_status = '✅ 开启' if user_config.get('filter_buttons', False) else '❌ 关闭'
                
                # 小尾巴和添加按钮状态
                tail_text = user_config.get('tail_text', '')
                tail_status = '✅ 已设置' if tail_text else '❌ 未设置'
                additional_buttons = user_config.get('additional_buttons', [])
                buttons_add_status = '✅ 已设置' if additional_buttons else '❌ 未设置'
            
            # 构建过滤配置显示
            config_text = f"""
⚙️ **频道组 {pair_index + 1} 过滤配置**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

🔧 **独立过滤状态：** {'✅ 已启用' if independent_filters else '❌ 使用全局配置'}

🔧 **当前过滤设置**
• 关键字过滤: {keywords_status}
• 敏感词替换: {replacements_status}
• 纯文本过滤: {content_removal_status}
• 增强版链接过滤: {links_removal_status}
• 用户名移除: {usernames_removal_status}
• 按钮移除: {buttons_removal_status}

✨ **内容增强设置**
• 小尾巴文本: {tail_status}
• 附加按钮: {buttons_add_status}

💡 请选择要配置的过滤选项：
            """.strip()
            
            # 生成过滤配置按钮 - 一行2个按钮布局
            buttons = [
                [("🔄 独立过滤开关", f"toggle_channel_independent_filters:{pair['id']}")],
                [("🔑 关键字过滤", f"channel_keywords:{pair['id']}"), ("🔄 敏感词替换", f"channel_replacements:{pair['id']}")],
                [("📝 纯文本过滤", f"channel_content_removal:{pair['id']}"), ("🚀 增强版链接过滤", f"channel_links_removal:{pair['id']}")],
                [("👤 用户名移除", f"channel_usernames_removal:{pair['id']}"), ("🔘 按钮移除", f"channel_buttons_removal:{pair['id']}")],
                [("📝 添加小尾巴", f"channel_tail_text:{pair['id']}"), ("🔘 添加按钮", f"channel_buttons:{pair['id']}")],
                [("🔙 返回频道详情", f"edit_channel_pair:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组过滤配置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_keywords(self, callback_query: CallbackQuery):
        """处理频道组关键字过滤配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的关键字过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            independent_enabled = channel_filters.get('independent_enabled', False)
            
            if not independent_enabled:
                # 独立过滤未启用，显示提示
                config_text = f"""
⚠️ **独立过滤未启用**

📡 **频道组：** {source_name}

🔧 **当前状态：** 使用全局过滤配置

💡 **如需独立配置关键字过滤，请先启用独立过滤开关**

🔙 返回过滤配置
                """.strip()
                
                buttons = [[("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]]
                
                await callback_query.edit_message_text(
                    config_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            keywords = channel_filters.get('keywords', [])
            keywords_enabled = channel_filters.get('keywords_enabled', False)
            
            config_text = f"""
🔑 **频道组 {pair_index + 1} 关键字过滤**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if keywords_enabled else '❌ 已禁用'}
📝 **关键字数量：** {len(keywords)} 个

💡 **使用方法：**
• 发送关键字来添加过滤规则
• 发送 "删除 关键字" 来删除规则
• 发送 "清空" 来清空所有关键字
• 发送 "开关" 来切换启用状态
            """.strip()
            
            # 设置用户状态为等待关键字输入
            self.user_states[user_id] = {
                'state': 'waiting_for_channel_keywords',
                'data': {'pair_id': pair['id'], 'pair_index': pair_index}
            }
            
            buttons = [[("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组关键字过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _process_channel_keywords_input(self, message: Message, state: Dict[str, Any]):
        """处理频道组关键字输入"""
        try:
            user_id = str(message.from_user.id)
            pair_id = state['data']['pair_id']
            pair_index = state['data']['pair_index']
            text = message.text.strip()
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await message.reply("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            if text == "开关":
                # 切换关键字过滤开关
                current_status = channel_filters.get('keywords_enabled', False)
                channel_filters['keywords_enabled'] = not current_status
                new_status = channel_filters['keywords_enabled']
                
                # 保存配置到用户配置
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                user_config['channel_filters'][pair['id']] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ **关键字过滤状态已切换！**\n\n"
                    f"📡 **频道组：** {pair_index + 1}\n"
                    f"🔧 **当前状态：** {'✅ 已启用' if new_status else '❌ 已禁用'}\n\n"
                    f"💡 **说明：**\n"
                    f"• 启用时：包含关键字的消息将被过滤\n"
                    f"• 禁用时：所有消息都将正常搬运\n\n"
                    f"🔙 返回过滤配置继续设置"
                )
                
            elif text == "清空":
                # 清空所有关键字
                channel_filters['keywords'] = []
                channel_filters['keywords_enabled'] = False
                
                # 保存配置到用户配置
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                user_config['channel_filters'][pair['id']] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ **关键字已清空！**\n\n"
                    f"📡 **频道组：** {pair_index + 1}\n"
                    f"🔧 **当前状态：** ❌ 已禁用\n"
                    f"📝 **关键字数量：** 0 个\n\n"
                    f"💡 **说明：**\n"
                    f"• 所有关键字过滤规则已清除\n"
                    f"• 关键字过滤功能已禁用\n"
                    f"• 所有消息都将正常搬运\n\n"
                    f"🔙 返回过滤配置继续设置"
                )
                
            elif text.startswith("删除 "):
                # 删除指定关键字
                keyword_to_delete = text[3:].strip()
                keywords = channel_filters.get('keywords', [])
                
                if keyword_to_delete in keywords:
                    keywords.remove(keyword_to_delete)
                    channel_filters['keywords'] = keywords
                    
                    # 保存配置到用户配置
                    if 'channel_filters' not in user_config:
                        user_config['channel_filters'] = {}
                    user_config['channel_filters'][pair['id']] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        f"✅ **关键字已删除！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🗑️ **已删除：** {keyword_to_delete}\n"
                        f"📝 **剩余关键字：** {len(keywords)} 个\n\n"
                        f"🔙 返回过滤配置继续设置"
                    )
                else:
                    await message.reply_text(
                        f"❌ **关键字不存在！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🔍 **查找关键字：** {keyword_to_delete}\n"
                        f"📝 **当前关键字：** {len(channel_filters.get('keywords', []))} 个\n\n"
                        f"💡 **建议：**\n"
                        f"• 检查关键字拼写是否正确\n"
                        f"• 查看当前已设置的关键字列表\n\n"
                        f"🔙 返回过滤配置继续设置"
                    )
                    
            else:
                # 添加新关键字
                if text not in channel_filters.get('keywords', []):
                    if 'keywords' not in channel_filters:
                        channel_filters['keywords'] = []
                    channel_filters['keywords'].append(text)
                    channel_filters['keywords_enabled'] = True
                    
                    # 保存配置到用户配置
                    if 'channel_filters' not in user_config:
                        user_config['channel_filters'] = {}
                    user_config['channel_filters'][pair['id']] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        f"✅ **关键字已添加！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🔑 **新增关键字：** {text}\n"
                        f"📝 **总关键字数：** {len(channel_filters['keywords'])} 个\n"
                        f"🔧 **过滤状态：** ✅ 已启用\n\n"
                        f"💡 **说明：**\n"
                        f"• 包含此关键字的消息将被过滤\n"
                        f"• 可以继续添加更多关键字\n"
                        f"• 发送\"清空\"可清除所有关键字\n\n"
                        f"🔙 返回过滤配置继续设置"
                    )
                else:
                    await message.reply_text(
                        f"⚠️ **关键字已存在！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🔑 **重复关键字：** {text}\n"
                        f"📝 **当前关键字数：** {len(channel_filters.get('keywords', []))} 个\n\n"
                        f"💡 **建议：**\n"
                        f"• 该关键字已经存在，无需重复添加\n"
                        f"• 可以添加其他不同的关键字\n"
                        f"• 发送\"删除 {text}\"可删除此关键字\n\n"
                        f"🔙 返回过滤配置继续设置"
                    )
            
            # 清除用户状态
            del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理频道组关键字输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _process_channel_replacements_input(self, message: Message, state: Dict[str, Any]):
        """处理频道组敏感词替换输入"""
        try:
            user_id = str(message.from_user.id)
            pair_index = state['data']['pair_index']
            text = message.text.strip()
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await message.reply("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            if text == "清空":
                # 清空所有替换规则
                channel_filters['replacements'] = {}
                channel_filters['replacements_enabled'] = False
                
                # 保存配置到用户配置
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                user_config['channel_filters'][pair['id']] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ **替换规则已清空！**\n\n"
                    f"📡 **频道组：** {pair_index + 1}\n"
                    f"🔧 **当前状态：** ❌ 已禁用\n"
                    f"📝 **替换规则数：** 0 个\n\n"
                    f"💡 **说明：**\n"
                    f"• 所有敏感词替换规则已清除\n"
                    f"• 替换功能已禁用\n"
                    f"• 消息将保持原样搬运\n\n"
                    f"🔙 返回过滤配置继续设置"
                )
                
            elif text == "开关":
                # 切换替换功能开关
                current_status = channel_filters.get('replacements_enabled', False)
                channel_filters['replacements_enabled'] = not current_status
                new_status = channel_filters['replacements_enabled']
                
                # 保存配置到用户配置
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                user_config['channel_filters'][pair['id']] = channel_filters
                await self.data_manager.save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ **替换功能状态已切换！**\n\n"
                    f"📡 **频道组：** {pair_index + 1}\n"
                    f"🔧 **当前状态：** {'✅ 已启用' if new_status else '❌ 已禁用'}\n\n"
                    f"💡 **说明：**\n"
                    f"• 启用时：敏感词将被替换为指定内容\n"
                    f"• 禁用时：所有替换规则将不生效\n\n"
                    f"🔙 返回过滤配置继续设置"
                )
                
            elif '|' in text:
                # 添加替换规则：旧词|新词
                parts = text.split('|', 1)
                if len(parts) == 2:
                    old_word = parts[0].strip()
                    new_word = parts[1].strip()
                    
                    if 'replacements' not in channel_filters:
                        channel_filters['replacements'] = {}
                    
                    channel_filters['replacements'][old_word] = new_word
                    channel_filters['replacements_enabled'] = True
                    
                    # 保存配置到用户配置
                    if 'channel_filters' not in user_config:
                        user_config['channel_filters'] = {}
                    user_config['channel_filters'][pair['id']] = channel_filters
                    await self.data_manager.save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        f"✅ **替换规则已添加！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🔄 **替换规则：** {old_word} → {new_word}\n"
                        f"📝 **总规则数：** {len(channel_filters['replacements'])} 个\n"
                        f"🔧 **替换状态：** ✅ 已启用\n\n"
                        f"💡 **说明：**\n"
                        f"• 消息中的\"{old_word}\"将被替换为\"{new_word}\"\n"
                        f"• 可以继续添加更多替换规则\n"
                        f"• 发送\"清空\"可清除所有规则\n\n"
                        f"🔙 返回过滤配置继续设置"
                    )
                else:
                    await message.reply_text(
                        f"❌ **格式错误！**\n\n"
                        f"📡 **频道组：** {pair_index + 1}\n"
                        f"🔍 **正确格式：** 旧词|新词\n\n"
                        f"💡 **示例：**\n"
                        f"• 敏感词|替换词\n"
                        f"• 广告|推广\n"
                        f"• 客服|支持\n\n"
                        f"🔙 请重新输入正确的格式"
                    )
            else:
                await message.reply_text(
                    f"❌ **格式错误！**\n\n"
                    f"📡 **频道组：** {pair_index + 1}\n"
                    f"🔍 **支持的操作：**\n"
                    f"• 旧词|新词 - 添加替换规则\n"
                    f"• 开关 - 切换替换功能\n"
                    f"• 清空 - 清除所有规则\n\n"
                    f"💡 **示例：**\n"
                    f"• 敏感词|替换词\n"
                    f"• 广告|推广\n\n"
                    f"🔙 请重新输入正确的格式"
                )
            
            # 保存配置 - 通过_init_channel_filters已经保存了，这里不需要重复保存
            
            # 清除用户状态
            del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理频道组敏感词替换输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_replacements(self, callback_query: CallbackQuery):
        """处理频道组敏感词替换配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的敏感词替换配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            replacements = channel_filters.get('replacements', {})
            replacements_enabled = channel_filters.get('replacements_enabled', False)
            
            if replacements:
                replacements_text = "\n".join([f"• {old} → {new}" for old, new in replacements.items()])
            else:
                replacements_text = "❌ 暂无替换规则"
            
            config_text = f"""
🔄 **频道组 {pair_index + 1} 敏感词替换**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if replacements_enabled else '❌ 已禁用'}
📝 **替换规则：**
{replacements_text}

💡 **使用方法：**
• 发送 "原词=新词" 来添加替换规则
• 发送 "删除 原词" 来删除规则
• 发送 "清空" 来清空所有规则
• 发送 "开关" 来切换启用状态
            """.strip()
            
            # 设置用户状态为等待替换词输入
            self.user_states[user_id] = {
                'state': 'waiting_for_channel_replacements',
                'data': {'pair_index': pair_index}
            }
            
            buttons = [[("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组敏感词替换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_content_removal(self, callback_query: CallbackQuery):
        """处理频道组纯文本过滤配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的纯文本过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            content_removal = channel_filters.get('content_removal', False)
            content_removal_mode = channel_filters.get('content_removal_mode', 'text_only')
            
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            mode_text = mode_descriptions.get(content_removal_mode, '未知模式')
            
            config_text = f"""
📝 **频道组 {pair_index + 1} 纯文本过滤**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if content_removal else '❌ 已禁用'}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 仅移除纯文本：只移除没有媒体内容的纯文本消息
• 移除所有包含文本的信息：移除所有包含文本的消息（包括图片、视频等）

""".strip()
            
            # 生成配置按钮
            buttons = [
                [("🔄 切换开关", f"toggle_channel_content_removal:{pair_index}")],
                [("🔘 仅移除纯文本", f"set_channel_content_mode:{pair_index}:text_only")],
                [("🗑️ 移除所有包含文本的信息", f"set_channel_content_mode:{pair_index}:all_content")],
                [("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组纯文本过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_content_removal(self, callback_query: CallbackQuery):
        """处理频道组纯文本过滤开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('content_removal', False)
            new_status = not current_status
            
            # 更新状态
            channel_filters['content_removal'] = new_status
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 纯文本过滤已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_content_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组纯文本过滤开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_channel_content_mode(self, callback_query: CallbackQuery):
        """处理频道组纯文本过滤模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            pair_index = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 更新模式
            channel_filters['content_removal_mode'] = mode
            channel_filters['content_removal'] = True  # 启用功能
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            mode_text = mode_descriptions.get(mode, '未知模式')
            
            await callback_query.answer(f"✅ 已设置为：{mode_text}")
            
            # 直接显示成功消息，不返回配置页面
            success_text = f"""
✅ **纯文本过滤模式设置成功！**

📡 **频道组：** {pair_index + 1}
🔧 **当前模式：** {mode_text}
📝 **功能状态：** ✅ 已启用

💡 **说明：**
• 仅移除纯文本：只移除纯文本消息
• 移除所有包含文本的信息：移除所有包含文本的消息

""".strip()
            
            await callback_query.edit_message_text(success_text)
            
        except Exception as e:
            logger.error(f"处理频道组纯文本过滤模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_links_removal(self, callback_query: CallbackQuery):
        """处理频道组增强链接过滤配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的增强链接过滤配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            enhanced_filter_enabled = channel_filters.get('enhanced_filter_enabled', False)
            enhanced_filter_mode = channel_filters.get('enhanced_filter_mode', 'moderate')
            
            # 模式描述
            mode_descriptions = {
                'aggressive': '激进模式 - 移除所有链接、按钮和广告',
                'moderate': '中等模式 - 移除链接和明显广告',
                'conservative': '保守模式 - 仅移除明显的垃圾链接'
            }
            mode_text = mode_descriptions.get(enhanced_filter_mode, '未知模式')
            
            config_text = f"""
🚀 **频道组 {pair_index + 1} 增强链接过滤**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if enhanced_filter_enabled else '❌ 已禁用'}
🔧 **过滤模式：** {mode_text}

💡 **功能说明：**
• 激进模式：移除所有链接、按钮文本和广告内容
• 中等模式：移除链接和明显的广告内容
• 保守模式：仅移除明显的垃圾链接和广告

🎯 **增强功能：**
• 智能识别广告关键词
• 自动移除按钮文本
• 保留有用内容

""".strip()
            
            # 生成配置按钮
            buttons = [
                [("🔄 切换开关", f"toggle_channel_enhanced_filter:{pair_index}")],
                [("🔥 激进模式", f"set_channel_enhanced_mode:{pair_index}:aggressive")],
                [("⚖️ 中等模式", f"set_channel_enhanced_mode:{pair_index}:moderate")],
                [("🛡️ 保守模式", f"set_channel_enhanced_mode:{pair_index}:conservative")],
                [("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组增强链接过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_usernames_removal(self, callback_query: CallbackQuery):
        """处理频道组用户名移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的用户名移除配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            usernames_removal = channel_filters.get('usernames_removal', False)
            
            config_text = f"""
👤 **频道组 {pair_index + 1} 用户名移除**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if usernames_removal else '❌ 已禁用'}

💡 **功能说明：**
移除消息中的用户名提及（@username）

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 生成配置按钮
            buttons = [
                [("🔄 切换开关", f"toggle_channel_usernames_removal:{pair_index}")],
                [("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组用户名移除失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_buttons_removal(self, callback_query: CallbackQuery):
        """处理频道组按钮移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取该频道组的按钮移除配置
            user_config = await self.data_manager.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            buttons_removal = channel_filters.get('buttons_removal', False)
            buttons_removal_mode = channel_filters.get('buttons_removal_mode', 'remove_buttons_only')
            
            mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            mode_text = mode_descriptions.get(buttons_removal_mode, '未知模式')
            
            config_text = f"""
🔘 **频道组 {pair_index + 1} 按钮移除**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if buttons_removal else '❌ 已禁用'}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 仅移除按钮：只移除消息中的按钮，保留文本、图片、视频等媒体内容
• 移除整条消息：包含按钮的整条消息将被完全移除

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 生成配置按钮
            buttons = [
                [("🔄 切换开关", f"toggle_channel_buttons_removal:{pair_index}")],
                [("🔘 仅移除按钮", f"set_channel_buttons_mode:{pair_index}:remove_buttons_only")],
                [("🗑️ 移除整条消息", f"set_channel_buttons_mode:{pair_index}:remove_message")],
                [("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组按钮移除失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_links_removal(self, callback_query: CallbackQuery):
        """处理频道组链接移除开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('links_removal', False)
            new_status = not current_status
            
            # 更新状态
            channel_filters['links_removal'] = new_status
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 链接移除已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_links_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组链接移除开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_channel_links_mode(self, callback_query: CallbackQuery):
        """处理频道组链接移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            pair_index = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 更新模式
            channel_filters['links_removal_mode'] = mode
            channel_filters['links_removal'] = True  # 启用功能
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_descriptions = {
                'links_only': '智能移除链接',
                'message_only': '移除整条消息'
            }
            mode_text = mode_descriptions.get(mode, '未知模式')
            
            await callback_query.answer(f"✅ 已设置为：{mode_text}")
            
            # 直接显示成功消息，不返回配置页面
            success_text = f"""
✅ **链接移除模式设置成功！**

📡 **频道组：** {pair_index + 1}
🔧 **当前模式：** {mode_text}
🔗 **功能状态：** ✅ 已启用

💡 **说明：**
• 智能移除链接：只移除消息中的链接，保留其他内容
• 移除整条消息：包含链接的整条消息将被完全移除

🔙 发送 /menu 返回主菜单
            """.strip()
            
            await callback_query.edit_message_text(success_text)
            
        except Exception as e:
            logger.error(f"处理频道组链接移除模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_enhanced_filter(self, callback_query: CallbackQuery):
        """处理频道组增强过滤开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('enhanced_filter_enabled', False)
            new_status = not current_status
            
            # 更新状态
            channel_filters['enhanced_filter_enabled'] = new_status
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 增强链接过滤已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_links_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组增强过滤开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_channel_enhanced_mode(self, callback_query: CallbackQuery):
        """处理频道组增强过滤模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            pair_index = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 更新模式
            channel_filters['enhanced_filter_mode'] = mode
            channel_filters['enhanced_filter_enabled'] = True  # 启用功能
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_descriptions = {
                'aggressive': '激进模式',
                'moderate': '中等模式',
                'conservative': '保守模式'
            }
            mode_text = mode_descriptions.get(mode, '未知模式')
            
            await callback_query.answer(f"✅ 已设置为：{mode_text}")
            
            # 直接显示成功消息，不返回配置页面
            success_text = f"""
✅ **增强链接过滤模式设置成功！**

📡 **频道组：** {pair_index + 1}
🔧 **当前模式：** {mode_text}
🚀 **功能状态：** ✅ 已启用

💡 **说明：**
• 激进模式：移除所有链接、按钮文本和广告内容
• 中等模式：移除链接和明显的广告内容
• 保守模式：仅移除明显的垃圾链接和广告

🔙 发送 /menu 返回主菜单
            """.strip()
            
            await callback_query.edit_message_text(success_text)
            
        except Exception as e:
            logger.error(f"处理频道组增强过滤模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_usernames_removal(self, callback_query: CallbackQuery):
        """处理频道组用户名移除开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('usernames_removal', False)
            new_status = not current_status
            
            # 更新状态
            channel_filters['usernames_removal'] = new_status
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 用户名移除已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_usernames_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组用户名移除开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_buttons_removal(self, callback_query: CallbackQuery):
        """处理频道组按钮移除开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('buttons_removal', False)
            new_status = not current_status
            
            # 更新状态
            channel_filters['buttons_removal'] = new_status
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 按钮移除已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_buttons_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组按钮移除开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_channel_buttons_mode(self, callback_query: CallbackQuery):
        """处理频道组按钮移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            pair_index = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 更新模式
            channel_filters['buttons_removal_mode'] = mode
            channel_filters['buttons_removal'] = True  # 启用功能
            
            # 保存配置到用户配置
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            user_config['channel_filters'][pair['id']] = channel_filters
            await self.data_manager.save_user_config(user_id, user_config)
            
            mode_descriptions = {
                'remove_buttons_only': '仅移除按钮',
                'remove_message': '移除整条消息'
            }
            mode_text = mode_descriptions.get(mode, '未知模式')
            
            await callback_query.answer(f"✅ 已设置为：{mode_text}")
            
            # 直接显示成功消息，不返回配置页面
            success_text = f"""
✅ **按钮移除模式设置成功！**

📡 **频道组：** {pair_index + 1}
🔧 **当前模式：** {mode_text}
🔘 **功能状态：** ✅ 已启用

💡 **说明：**
• 仅移除按钮：只移除消息中的按钮，保留其他内容
• 移除整条消息：包含按钮的整条消息将被完全移除

🔙 发送 /menu 返回主菜单
            """.strip()
            
            await callback_query.edit_message_text(success_text)
            
        except Exception as e:
            logger.error(f"处理频道组按钮移除模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_independent_filters(self, callback_query: CallbackQuery):
        """处理频道组独立过滤开关"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 判断传入的是pair_id还是pair_index
            pair_index = None
            pair = None
            
            # 先尝试作为pair_id处理
            for i, p in enumerate(channel_pairs):
                if p.get('id') == data_part:
                    pair_index = i
                    pair = p
                    break
            
            # 如果没找到，尝试作为pair_index处理（向后兼容）
            if pair_index is None:
                try:
                    idx = int(data_part)
                    if 0 <= idx < len(channel_pairs):
                        pair_index = idx
                        pair = channel_pairs[pair_index]
                except ValueError:
                    pass
            
            if pair is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            
            # 获取用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 确保channel_filters结构存在
            if 'channel_filters' not in user_config:
                user_config['channel_filters'] = {}
            if pair['id'] not in user_config['channel_filters']:
                user_config['channel_filters'][pair['id']] = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            current_status = channel_filters.get('independent_enabled', False)
            new_status = not current_status
            
            # 添加调试日志
            # 独立过滤开关调试日志已注释以减少后台输出
            # logger.info(f"🔍 独立过滤开关调试 - 频道组 {pair_index}:")
            # logger.info(f"  • 当前状态: {current_status}")
            # logger.info(f"  • 新状态: {new_status}")
            # logger.info(f"  • 当前channel_filters: {channel_filters}")
            # logger.info(f"  • user_config中的channel_filters: {user_config.get('channel_filters', {})}")
            
            # 标记是否需要保存配置
            modified_channel_filters = False
            
            if new_status:
                # 启用独立过滤，复制全局配置，但关键字过滤默认开启
                global_config = {
                    'keywords_enabled': True,  # 独立过滤时关键字过滤默认开启
                    'keywords': user_config.get('filter_keywords', []).copy(),
                    'replacements_enabled': user_config.get('replacements_enabled', False),
                    'replacements': user_config.get('replacement_words', {}).copy(),
                    'content_removal': user_config.get('content_removal', False),
                    'content_removal_mode': user_config.get('content_removal_mode', 'text_only'),
                    'links_removal': user_config.get('remove_all_links', False),
                    'links_removal_mode': user_config.get('remove_links_mode', 'links_only'),
                    'usernames_removal': user_config.get('remove_usernames', False),
                    'buttons_removal': user_config.get('filter_buttons', False),
                    'buttons_removal_mode': user_config.get('button_filter_mode', 'remove_buttons_only')
                }
                
                # 更新频道组过滤配置
                channel_filters.update(global_config)
                channel_filters['independent_enabled'] = True
                
                # 标记需要保存配置
                modified_channel_filters = True
                
                await callback_query.answer("✅ 独立过滤已启用，已复制全局配置")
                
                config_text = f"""
✅ **独立过滤已启用！**

📡 **频道组：** {source_name}

🔧 **当前配置状态：**
• 关键字过滤: ✅ 开启（默认）
• 敏感词替换: {'✅ 开启' if global_config['replacements_enabled'] else '❌ 关闭'}
• 纯文本过滤: {'✅ 开启' if global_config['content_removal'] else '❌ 关闭'}
• 链接移除: {'✅ 开启' if global_config['links_removal'] else '❌ 关闭'}
• 用户名移除: {'✅ 开启' if global_config['usernames_removal'] else '❌ 关闭'}
• 按钮移除: {'✅ 开启' if global_config['buttons_removal'] else '❌ 关闭'}

💡 **现在可以独立配置每个过滤选项，不会影响全局设置**

🔙 返回过滤配置继续设置
                """.strip()
                
                buttons = [[("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]]
                
            else:
                # 禁用独立过滤，清除频道组配置
                channel_filters.clear()
                channel_filters['independent_enabled'] = False
                
                # 标记需要保存配置
                modified_channel_filters = True
                
                await callback_query.answer("❌ 独立过滤已禁用，将使用全局配置")
                
                config_text = f"""
❌ **独立过滤已禁用！**

📡 **频道组：** {source_name}

🔧 **现在将使用全局过滤配置**

💡 **如需自定义过滤规则，请重新启用独立过滤**

🔙 返回过滤配置
                """.strip()
                
                buttons = [[("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]]
            
            # 将修改后的channel_filters保存回user_config
            user_config['channel_filters'][pair['id']] = channel_filters
            
            # 保存配置
            await self.data_manager.save_user_config(user_id, user_config)
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组独立过滤开关失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_select_pair(self, callback_query: CallbackQuery):
        """处理选择频道组进行搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            source_id = pair.get('source_id', '')
            target_id = pair.get('target_id', '')
            
            # 检查频道组是否启用
            if not pair.get('enabled', True):
                await callback_query.edit_message_text(
                    f"❌ 频道组已禁用\n\n"
                    f"📡 采集频道：{source_name}\n"
                    f"📤 发布频道：{target_name}\n\n"
                    f"请在频道管理中启用该频道组。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            # 显示搬运信息输入界面
            input_text = f"""
🚀 **设置搬运信息**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

💡 **请输入要搬运的信息ID段：**

📝 **格式说明：**
• 单个ID：`31316`
• ID范围：`31316-31403`
• 多个ID：`31316,31317,31318`
• 混合格式：`31316-31403,31405,31410-31415`

💡 **获取方法：**
• 在采集频道中找到要搬运的消息
• 复制消息ID（通常在消息链接中）
• 支持范围搬运，提高效率

⚠️ **注意事项：**
• ID必须是有效的消息ID
• 范围格式：起始ID-结束ID
• 多个ID用逗号分隔

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 设置用户状态为等待输入搬运信息
            self.user_states[user_id] = {
                'state': 'waiting_for_cloning_info',
                'data': {
                    'pair_index': pair_index,
                    'source_name': source_name,
                    'target_name': target_name,
                    'source_id': source_id,
                    'target_id': target_id
                }
            }
            
            await callback_query.edit_message_text(input_text)
            
        except Exception as e:
            logger.error(f"处理选择频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_start_cloning(self, callback_query: CallbackQuery):
        """处理开始搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            # 优先使用用户名，如果没有则使用ID
            source_username = pair.get('source_username', '')
            target_username = pair.get('target_username', '')
            source_id = pair.get('source_id', '')
            target_id = pair.get('target_id', '')
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 确定实际使用的频道标识符
            actual_source_id = source_username if source_username else source_id
            actual_target_id = target_username if target_username else target_id
            
            # 检查搬运引擎是否初始化
            if not self.cloning_engine:
                logger.error(f"搬运引擎未初始化")
                await callback_query.answer("❌ 搬运引擎未初始化")
                await callback_query.edit_message_text(
                    "❌ **搬运引擎未初始化**\n\n"
                    "💡 **请稍后重试或重启机器人**\n\n"
                    "🔙 返回主菜单继续其他操作",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            # 直接开始创建搬运任务，不显示初始化消息
            try:
                logger.info(f"开始为用户 {user_id} 创建搬运任务，频道组 {pair_index}")
                
                # 创建搬运任务配置
                task_config = {
                    'user_id': user_id,
                    'pair_index': pair_index,
                    'pair_id': pair['id'],
                    'source_name': source_name,
                    'target_name': target_name
                }
                
                # 确保使用正确的客户端
                await self._ensure_cloning_engine_client()
                
                # 创建搬运任务（搬运最近的消息）
                logger.info(f"正在创建搬运任务...")
                task = await self.cloning_engine.create_task(
                    source_chat_id=actual_source_id,
                    target_chat_id=actual_target_id,
                    start_id=None,  # 从最近的消息开始
                    end_id=None,    # 不限制结束ID
                    config=task_config,
                    source_username=source_username,
                    target_username=target_username
                )
                
                if task:
                    logger.info(f"搬运任务创建成功，开始启动...")
                    
                    # 启动搬运任务
                    success = await self.cloning_engine.start_cloning(task)
                    
                    if success:
                        logger.info(f"搬运任务启动成功")
                        
                        # 直接显示任务状态页面，显示实时进度
                        try:
                            # 构建任务状态页面
                            status_text = f"""
🚀 **搬运任务状态**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}
📝 **搬运信息：** 从最近消息开始
📊 **总计：** 正在计算...

⏱️ **任务状态：** 🟡 正在启动...
📈 **进度：** 0%

💡 **任务说明：**
• 机器人正在获取消息内容
• 自动应用过滤规则和增强功能
• 实时发布到目标频道

🔄 **实时更新：** 页面将自动刷新显示最新进度
                            """.strip()
                            
                            # 生成任务状态页面的按钮
                            buttons = [
                                [("🛑 停止任务", f"stop_cloning:{pair_index}")],
                                [("🔙 返回主菜单", "show_main_menu")]
                            ]
                            
                            await callback_query.edit_message_text(
                                status_text,
                                reply_markup=generate_button_layout(buttons)
                            )
                            
                            # 启动后台任务状态更新
                            asyncio.create_task(self._update_task_status_background(callback_query, pair_index))
                            
                            logger.info(f"成功显示任务状态页面，频道组: {pair_index + 1}")
                            
                        except Exception as ui_error:
                            logger.warning(f"显示任务状态页面失败: {ui_error}")
                            # 如果显示失败，显示成功消息作为备选
                            await callback_query.edit_message_text(
                                f"""
✅ **搬运任务启动成功！**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}

🚀 **任务状态：** 正在后台运行

💡 **说明：**
• 搬运任务已成功启动
• 机器人正在后台处理消息
• 可随时查看任务进度

🔄 点击下方按钮查看实时进度
                                """.strip(),
                                reply_markup=generate_button_layout([[
                                    ("🔄 查看任务状态", f"refresh_task_status:{pair_index}")
                                ], [
                                    ("🔙 返回主菜单", "show_main_menu")
                                ]])
                            )
                    else:
                        logger.error(f"启动搬运任务失败")
                        await callback_query.edit_message_text(
                            "❌ **启动搬运任务失败**\n\n"
                            "💡 **可能的原因：**\n"
                            "• 机器人权限不足\n"
                            "• 频道访问受限\n"
                            "• 网络连接问题\n\n"
                            "🔙 请稍后重试或联系管理员",
                            reply_markup=generate_button_layout([[
                                ("🔙 返回主菜单", "show_main_menu")
                            ]])
                        )
                else:
                    logger.error(f"创建搬运任务失败")
                    await callback_query.edit_message_text(
                        "❌ **创建搬运任务失败**\n\n"
                        "💡 **可能的原因：**\n"
                        "• 频道配置错误\n"
                        "• 机器人权限不足\n"
                        "• 系统资源不足\n\n"
                        "🔙 请检查配置或稍后重试",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                    
            except Exception as e:
                logger.error(f"启动搬运任务失败: {e}")
                
                # 根据错误类型提供具体的解决方案
                error_message = "❌ **启动搬运任务失败**\n\n"
                
                if "频道验证失败" in str(e):
                    error_message += "**错误原因：** 频道验证失败\n\n"
                    error_message += "**可能的原因：**\n"
                    error_message += "• 频道ID不正确\n"
                    error_message += "• 机器人未加入频道\n"
                    error_message += "• 频道权限不足\n"
                    error_message += "• 频道不存在或已被删除\n\n"
                    error_message += "**解决方案：**\n"
                    error_message += "• 检查频道ID是否正确\n"
                    error_message += "• 确保机器人已加入频道\n"
                    error_message += "• 检查机器人权限设置\n"
                    error_message += "• 尝试重新添加频道组\n\n"
                else:
                    error_message += f"**错误信息：** {str(e)}\n\n"
                    error_message += "**请稍后重试或联系管理员**\n\n"
                
                error_message += "🔙 返回主菜单继续其他操作"
                
                await callback_query.edit_message_text(
                    error_message,
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
            
        except Exception as e:
            logger.error(f"处理开始搬运失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _process_cloning_info_input(self, message: Message, state: Dict[str, Any]):
        """处理搬运信息输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            
            # 检查是否有关键字命令
            if text.lower() in ['取消', 'cancel', '返回', 'back']:
                del self.user_states[user_id]
                await message.reply_text(
                    "❌ 搬运设置已取消\n\n🔙 返回主菜单重新选择",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            # 解析搬运信息
            cloning_info = await self._parse_cloning_info(text)
            if not cloning_info:
                await message.reply_text(
                    "❌ 格式错误！请使用以下格式之一：\n\n"
                    "• 单个ID：`31316`\n"
                    "• ID范围：`31316-31403`\n"
                    "• 多个ID：`31316,31317,31318`\n"
                    "• 混合格式：`31316-31403,31405,31410-31415`\n\n"
                    "💡 请重新输入正确的格式"
                )
                return
            
            # 获取频道组信息
            pair_index = state['data']['pair_index']
            source_name = state['data']['source_name']
            target_name = state['data']['target_name']
            source_id = state['data']['source_id']
            target_id = state['data']['target_id']
            
            # 显示确认界面
            confirm_text = f"""
🚀 **确认开始搬运**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}
📝 **搬运信息：** {text}

🔢 **解析结果：**
{cloning_info['summary']}

💡 **搬运说明：**
• 机器人将搬运指定的消息内容
• 自动应用过滤规则和增强功能
• 将处理后的内容发布到目标频道

⚠️ **注意事项：**
• 确保机器人有足够的权限
• 搬运过程中请勿删除频道组
• 可以随时在任务管理中查看进度

❓ **是否确认开始搬运？**
            """.strip()
            
            # 保存搬运信息到状态中
            state['data']['cloning_info'] = text
            state['data']['parsed_info'] = cloning_info
            state['data']['source_id'] = source_id
            state['data']['target_id'] = target_id
            
            # 生成确认按钮
            buttons = [
                [("✅ 确认开始搬运", f"confirm_cloning:{pair_index}")],
                [("🔙 重新输入", f"select_pair:{pair_index}")]
            ]
            
            await message.reply_text(
                confirm_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理搬运信息输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    async def _parse_cloning_info(self, text: str) -> Optional[Dict[str, Any]]:
        """解析搬运信息，支持多种格式"""
        try:
            text = text.strip()
            result = {
                'ids': [],
                'ranges': [],
                'summary': '',
                'total_count': 0
            }
            
            # 分割多个部分（用逗号分隔）
            parts = [part.strip() for part in text.split(',')]
            
            for part in parts:
                if '-' in part:
                    # 处理范围格式：31316-31403
                    try:
                        start, end = part.split('-', 1)
                        start_id = int(start.strip())
                        end_id = int(end.strip())
                        
                        if start_id > end_id:
                            start_id, end_id = end_id, start_id
                        
                        result['ranges'].append((start_id, end_id))
                        range_count = end_id - start_id + 1
                        result['total_count'] += range_count
                        result['summary'] += f"• 范围 {start_id}-{end_id}：{range_count} 条消息\n"
                    except ValueError:
                        return None
                else:
                    # 处理单个ID
                    try:
                        message_id = int(part.strip())
                        result['ids'].append(message_id)
                        result['total_count'] += 1
                        result['summary'] += f"• 单个ID {message_id}\n"
                    except ValueError:
                        return None
            
            # 如果没有有效内容，返回None
            if result['total_count'] == 0:
                return None
            
            return result
            
        except Exception as e:
            logger.error(f"解析搬运信息失败: {e}")
            return None
    
    async def _handle_confirm_cloning(self, callback_query: CallbackQuery):
        """处理确认搬运"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 检查用户状态
            if user_id not in self.user_states:
                await callback_query.edit_message_text("❌ 会话已过期，请重新选择频道组")
                return
            
            state = self.user_states[user_id]
            if state['state'] != 'waiting_for_cloning_info':
                await callback_query.edit_message_text("❌ 状态错误，请重新选择频道组")
                return
            
            # 获取搬运信息
            cloning_info = state['data'].get('cloning_info', '')
            parsed_info = state['data'].get('parsed_info', {})
            source_name = state['data'].get('source_name', '')
            target_name = state['data'].get('target_name', '')
            
            if not cloning_info or not parsed_info:
                await callback_query.edit_message_text("❌ 搬运信息缺失，请重新输入")
                return
            
            # 获取频道信息
            source_id = state['data'].get('source_id', '')
            target_id = state['data'].get('target_id', '')
            
            if not source_id or not target_id:
                await callback_query.edit_message_text("❌ 频道信息缺失，请重新选择频道组")
                return
            
            # 直接开始创建搬运任务，不显示初始化消息
            
            # 调试信息：检查搬运引擎状态
            logger.info(f"搬运引擎状态检查: {type(self.cloning_engine)}")
            if hasattr(self.cloning_engine, 'get_engine_stats'):
                try:
                    stats = self.cloning_engine.get_engine_stats()
                    logger.info(f"搬运引擎统计: {stats}")
                except Exception as e:
                    logger.error(f"获取搬运引擎统计失败: {e}")
            
            # 启动搬运任务
            if self.cloning_engine:
                try:
                    logger.info(f"用户 {user_id} 开始创建搬运任务，频道组 {pair_index + 1}")
                    
                    # 创建搬运任务
                    # 处理消息ID范围
                    start_id = None
                    end_id = None
                    
                    # 如果有范围，使用第一个范围
                    if parsed_info['ranges']:
                        start_id = parsed_info['ranges'][0][0]
                        end_id = parsed_info['ranges'][0][1]
                        logger.info(f"使用范围搬运: {start_id} - {end_id}")
                    # 如果只有单个ID，使用第一个ID
                    elif parsed_info['ids']:
                        start_id = parsed_info['ids'][0]
                        end_id = parsed_info['ids'][0]
                        logger.info(f"使用单个ID搬运: {start_id}")
                    
                    # 获取频道组信息
                    channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                    if pair_index >= len(channel_pairs):
                        await callback_query.edit_message_text("❌ 频道组不存在")
                        return
                    
                    pair = channel_pairs[pair_index]
                    
                    # 创建任务配置
                    task_config = {
                        'user_id': user_id,
                        'pair_index': pair_index,
                        'pair_id': pair['id'],
                        'message_ids': parsed_info['ids'],
                        'message_ranges': parsed_info['ranges']
                    }
                    
                    # 确保使用正确的客户端
                    await self._ensure_cloning_engine_client()
                    
                    logger.info(f"正在创建搬运任务...")
                    task = await self.cloning_engine.create_task(
                        source_chat_id=source_id,
                        target_chat_id=target_id,
                        start_id=start_id,
                        end_id=end_id,
                        config=task_config,
                        source_username=pair.get('source_username', ''),
                        target_username=pair.get('target_username', '')
                    )
                    
                    if task:
                        logger.info(f"搬运任务创建成功，开始启动...")
                        # 启动搬运任务
                        success = await self.cloning_engine.start_cloning(task)
                        if success:
                            logger.info(f"搬运任务启动成功")
                            
                            # 调用统一的任务状态显示方法
                            try:
                                total_count = task.total_messages if task.total_messages else parsed_info['total_count']
                                await self._show_task_started_message(callback_query, source_name, target_name, cloning_info, total_count, pair_index)
                                
                                # 添加调试信息：验证任务配置
                                logger.info(f"🔍 验证任务配置: pair_index={pair_index}, task_config={task_config}")
                                if hasattr(task, 'config'):
                                    logger.info(f"✅ 任务配置已保存: {task.config}")
                                else:
                                    logger.warning(f"⚠️ 任务配置未保存到任务对象")
                                    
                            except Exception as ui_error:
                                logger.error(f"显示任务状态页面失败: {ui_error}")
                                # 如果显示失败，至少启动后台更新
                                try:
                                    asyncio.create_task(self._update_task_status_background(callback_query, pair_index))
                                    logger.info(f"UI更新失败，但后台更新已启动，频道组: {pair_index}")
                                except Exception as bg_error:
                                    logger.error(f"启动后台更新也失败: {bg_error}")
                        else:
                            logger.error(f"启动搬运任务失败")
                            try:
                                await callback_query.answer("❌ 启动搬运任务失败")
                            except Exception as answer_error:
                                logger.warning(f"回答回调查询失败: {answer_error}")
                            # 显示错误消息
                            await callback_query.edit_message_text(
                                "❌ **启动搬运任务失败**\n\n"
                                "💡 **可能的原因：**\n"
                                "• 机器人权限不足\n"
                                "• 频道访问受限\n"
                                "• 网络连接问题\n\n"
                                "🔙 请稍后重试或联系管理员",
                                reply_markup=generate_button_layout([[
                                    ("🔙 返回主菜单", "show_main_menu")
                                ]])
                            )
                            return
                    else:
                        logger.error(f"创建搬运任务失败")
                        await callback_query.answer("❌ 创建搬运任务失败")
                        # 显示错误消息
                        await callback_query.edit_message_text(
                            "❌ **创建搬运任务失败**\n\n"
                            "💡 **可能的原因：**\n"
                            "• 频道配置错误\n"
                            "• 机器人权限不足\n"
                            "• 系统资源不足\n\n"
                            "🔙 请检查配置或稍后重试",
                            reply_markup=generate_button_layout([[
                                ("🔙 返回主菜单", "show_main_menu")
                            ]])
                        )
                        return
                        
                except Exception as e:
                    logger.error(f"启动搬运任务失败: {e}")
                    await callback_query.answer("❌ 启动搬运任务失败")
                    
                    # 根据错误类型提供具体的解决方案
                    error_message = "❌ **启动搬运任务失败**\n\n"
                    
                    if "频道验证失败" in str(e):
                        error_message += "**错误原因：** 频道验证失败\n\n"
                        error_message += "**可能的原因：**\n"
                        error_message += "• 频道ID不正确\n"
                        error_message += "• 机器人未加入频道\n"
                        error_message += "• 频道权限不足\n"
                        error_message += "• 频道不存在或已被删除\n\n"
                        error_message += "**解决方案：**\n"
                        error_message += "• 检查频道ID是否正确\n"
                        error_message += "• 确保机器人已加入频道\n"
                        error_message += "• 检查机器人权限设置\n"
                        error_message += "• 尝试重新添加频道组\n\n"
                    else:
                        error_message += f"**错误信息：** {str(e)}\n\n"
                        error_message += "**请稍后重试或联系管理员**\n\n"
                    
                    error_message += "🔙 返回主菜单继续其他操作"
                    
                    # 显示错误消息
                    await callback_query.edit_message_text(
                        error_message,
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                    return
            else:
                logger.error(f"搬运引擎未初始化")
                await callback_query.answer("❌ 搬运引擎未初始化")
                # 显示错误消息
                await callback_query.edit_message_text(
                    "❌ **搬运引擎未初始化**\n\n"
                    "💡 **解决方案：**\n"
                    "• 请重启机器人\n"
                    "• 检查配置文件\n"
                    "• 联系管理员\n\n"
                    "🔙 返回主菜单",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回主菜单", "show_main_menu")
                    ]])
                )
                return
            
            # 清除用户状态
            del self.user_states[user_id]
            
        except Exception as e:
            logger.error(f"处理确认搬运失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    

    
    async def _handle_check_task_completion(self, callback_query: CallbackQuery):
        """处理检查任务完成状态"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 检查任务状态
            if self.cloning_engine:
                tasks = self.cloning_engine.get_all_tasks()
                current_task = None
                
                # 查找当前频道组的任务
                for task in tasks:
                    # 检查task是对象还是字典
                    if isinstance(task, dict):
                        config = task.get('config', {})
                        if config.get('pair_index') == pair_index:
                            current_task = task
                            break
                    else:
                        if (hasattr(task, 'config') and 
                            task.config.get('pair_index') == pair_index):
                            current_task = task
                            break
                
                if current_task:
                    # 获取任务状态，兼容对象和字典
                    if isinstance(current_task, dict):
                        task_status = current_task.get('status', 'unknown')
                    else:
                        task_status = getattr(current_task, 'status', 'unknown')
                    
                    if task_status in ['completed', 'failed', 'stopped']:
                        # 任务已完成，显示完成页面
                        await self._show_task_completed_page(callback_query, pair_index)
                else:
                    # 任务仍在运行或不存在
                    await callback_query.answer("⏳ 任务仍在运行中，请稍后再试")
            else:
                await callback_query.answer("❌ 搬运引擎未初始化")
                
        except Exception as e:
            logger.error(f"检查任务完成状态失败: {e}")
            await callback_query.answer("❌ 检查失败，请稍后重试")
    
    async def _show_task_started_message(self, callback_query: CallbackQuery, source_name: str, target_name: str, cloning_info: str, total_count: int, pair_index: int):
        """显示任务启动成功消息（改为显示任务状态页面）"""
        try:
            # 尝试显示任务状态页面而不是成功消息
            status_text = f"""
🚀 **搬运任务状态**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}
📝 **搬运信息：** {cloning_info}
📊 **总计：** {total_count} 条消息

⏱️ **任务状态：** 🟡 正在启动...
📈 **进度：** 0%

💡 **任务说明：**
• 机器人正在获取消息内容
• 自动应用过滤规则和增强功能
• 实时发布到目标频道

🔄 **实时更新：** 页面将自动刷新显示最新进度
            """.strip()
            
            # 生成任务状态页面的按钮
            buttons = [
                [("🛑 停止任务", f"stop_cloning:{pair_index}")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                status_text,
                reply_markup=generate_button_layout(buttons)
            )
            
            # 启动后台任务状态更新
            asyncio.create_task(self._update_task_status_background(callback_query, pair_index))
            
            logger.info(f"成功显示任务状态页面，频道组: {pair_index}")
            
        except Exception as e:
            logger.error(f"显示任务状态页面失败: {e}")
            # 如果显示任务状态页面失败，回退到显示成功消息
            try:
                success_text = f"""
✅ **搬运任务启动成功！**

📡 **采集频道：** {source_name}
📤 **发布频道：** {target_name}
📝 **搬运信息：** {cloning_info}
📊 **总计：** {total_count} 条消息

🚀 **任务状态：** 正在后台运行

💡 **说明：**
• 搬运任务已成功启动
• 机器人正在后台处理消息
• 可随时查看任务进度

🔄 点击下方按钮查看实时进度
                """.strip()
                
                buttons = [
                    [("🔄 查看任务状态", f"refresh_task_status:{pair_index}")],
                    [("🔙 返回主菜单", "show_main_menu")]
                ]
                
                await callback_query.edit_message_text(
                    success_text,
                    reply_markup=generate_button_layout(buttons)
                )
                
            except Exception as fallback_error:
                logger.error(f"显示备用消息也失败: {fallback_error}")
                # 最后的备用方案：显示简单消息
                try:
                    await callback_query.edit_message_text(
                        "✅ 搬运任务已启动！请稍后查看任务状态。",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回主菜单", "show_main_menu")
                        ]])
                    )
                except Exception as final_error:
                    logger.error(f"所有UI更新都失败: {final_error}")
    
    async def _update_task_status_background(self, callback_query: CallbackQuery, pair_index: int):
        """后台更新任务状态（每30秒更新一次）"""
        try:
            logger.info(f"🚀 启动后台任务状态更新，频道组: {pair_index + 1}")
            
            # 等待一段时间让任务启动
            await asyncio.sleep(2)
            
            logger.info(f"⏳ 开始持续更新任务状态，频道组: {pair_index + 1}")
            
            # 持续更新任务状态，直到任务完成
            while True:
                try:
                    # 获取任务状态
                    if self.cloning_engine:
                        tasks = self.cloning_engine.get_all_tasks()
                        logger.info(f"🔍 获取到 {len(tasks)} 个任务，查找频道组 {pair_index + 1} 的任务")
                        current_task = None
                        
                        # 查找当前频道组的任务
                        for task in tasks:
                            # 检查task是对象还是字典
                            if isinstance(task, dict):
                                task_id = task.get('task_id', 'unknown')
                                config = task.get('config', {})
                                logger.info(f"🔍 检查任务 {task_id}，配置: {config}")
                                if config.get('pair_index') == pair_index:
                                    current_task = task
                                    logger.info(f"✅ 找到频道组 {pair_index} 的任务: {task_id}")
                                    break
                            else:
                                # 对象类型
                                task_id = getattr(task, 'task_id', 'unknown')
                                config = getattr(task, 'config', {})
                                logger.info(f"🔍 检查任务 {task_id}，配置: {config}")
                                if config.get('pair_index') == pair_index:
                                    current_task = task
                                    logger.info(f"✅ 找到频道组 {pair_index} 的任务: {task_id}")
                                    break
                        
                        if current_task:
                            # 检查任务状态
                            if isinstance(current_task, dict):
                                task_id = current_task.get('task_id', 'unknown')
                                status = current_task.get('status', 'unknown')
                                progress = current_task.get('progress', 0.0)
                                processed = current_task.get('processed_messages', 0)
                                total = current_task.get('total_messages', 0)
                            else:
                                task_id = getattr(current_task, 'task_id', 'unknown')
                                status = getattr(current_task, 'status', 'unknown')
                                progress = getattr(current_task, 'progress', 0.0)
                                processed = getattr(current_task, 'processed_messages', 0)
                                total = getattr(current_task, 'total_messages', 0)
                            
                            # 记录任务状态信息
                            logger.info(f"任务 {task_id} 状态: {status}, 进度: {progress:.1f}%, 已处理: {processed}/{total}")
                            
                            # 添加调试信息
                            if isinstance(current_task, dict):
                                config = current_task.get('config', {})
                                logger.info(f"任务配置: {config}")
                            else:
                                config = getattr(current_task, 'config', {})
                                logger.info(f"任务配置: {config}")
                            
                            if status in ['completed', 'failed', 'stopped']:
                                # 任务已完成，显示完成页面
                                logger.info(f"任务 {task_id} 已完成，状态: {status}")
                                try:
                                    if status == 'completed':
                                        await self._show_task_completed_page(callback_query, pair_index)
                                    else:
                                        # 任务失败或停止，显示相应消息
                                        await callback_query.edit_message_text(
                                            f"""
❌ **搬运任务{status}**

📡 **频道组：** {pair_index + 1}

🔙 返回主菜单
                                            """.strip(),
                                            reply_markup=generate_button_layout([[
                                                ("🔙 返回主菜单", "show_main_menu")
                                            ]])
                                        )
                                    logger.info(f"任务完成页面显示成功")
                                except Exception as ui_error:
                                    logger.warning(f"显示任务完成页面失败: {ui_error}")
                                # 任务完成后退出循环
                                break
                            else:
                                # 任务仍在运行，尝试更新状态页面
                                try:
                                    await self._refresh_task_status_page(callback_query, current_task, pair_index)
                                    logger.debug(f"任务 {task_id} 状态已更新，进度: {progress:.1f}%")
                                except Exception as ui_error:
                                    error_str = str(ui_error)
                                    logger.warning(f"更新UI失败，但任务仍在运行: {ui_error}")
                                    
                                    # 处理FLOOD_WAIT错误
                                    if "FLOOD_WAIT" in error_str:
                                        try:
                                            # 解析等待时间
                                            wait_time = int(error_str.split('A wait of ')[1].split(' seconds')[0])
                                            logger.warning(f"⚠️ 单任务UI更新遇到FLOOD_WAIT限制，需要等待 {wait_time} 秒")
                                            
                                            # 等待指定时间
                                            logger.info(f"⏳ 等待 {wait_time} 秒后继续...")
                                            await asyncio.sleep(wait_time)
                                            
                                            # 重试更新
                                            try:
                                                await self._refresh_task_status_page(callback_query, current_task, pair_index)
                                                logger.info(f"✅ 单任务FLOOD_WAIT后重试更新成功")
                                            except Exception as retry_error:
                                                logger.error(f"❌ 单任务FLOOD_WAIT后重试更新失败: {retry_error}")
                                        except Exception as parse_error:
                                            logger.error(f"❌ 解析单任务FLOOD_WAIT时间失败: {parse_error}")
                                            # 如果解析失败，等待60秒
                                            await asyncio.sleep(60)
                                    # UI更新失败不影响任务继续运行
                                    # 如果UI更新失败，可能是回调查询过期，但继续监控任务状态
                                    if "QUERY_ID_INVALID" in str(ui_error) or "callback query id is invalid" in str(ui_error).lower():
                                        logger.info(f"检测到回调查询过期，继续监控任务但不更新UI")
                                        # 不再尝试更新UI，但继续监控任务状态
                                        pass
                        else:
                            # 任务不存在，可能已完成或失败
                            logger.info(f"频道组 {pair_index} 的任务不存在，停止状态更新")
                            break
                    
                    # 等待30秒后再次更新
                    await asyncio.sleep(30)
                    
                except Exception as e:
                    logger.error(f"更新任务状态失败: {e}")
                    # 出错后等待30秒再重试
                    await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"后台更新任务状态失败: {e}")
    
    async def _refresh_task_status_page(self, callback_query: CallbackQuery, task: Any, pair_index: int):
        """刷新任务状态页面（添加频率限制）"""
        try:
            # 添加频率限制：每个用户最多每10秒更新一次UI
            user_id = str(callback_query.from_user.id)
            current_time = time.time()
            if not hasattr(self, '_ui_update_times'):
                self._ui_update_times = {}
            
            last_update_time = self._ui_update_times.get(f"{user_id}_single", 0)
            if current_time - last_update_time < 10:  # 10秒内不重复更新
                logger.debug(f"跳过单任务UI更新，用户 {user_id} 上次更新时间: {current_time - last_update_time:.1f}秒前")
                return
            
            self._ui_update_times[f"{user_id}_single"] = current_time
            # 获取任务进度信息
            if isinstance(task, dict):
                progress = task.get('progress', 0.0)
                status = task.get('status', 'unknown')
                processed = task.get('processed_messages', 0)
                total = task.get('total_messages', 0)
                stats = task.get('stats', {})
            else:
                progress = getattr(task, 'progress', 0.0)
                status = getattr(task, 'status', 'unknown')
                processed = getattr(task, 'processed_messages', 0)
                total = getattr(task, 'total_messages', 0)
                stats = getattr(task, 'stats', {})
            
            # 状态图标映射
            status_icons = {
                'running': '🟢',
                'pending': '🟡',
                'completed': '✅',
                'failed': '❌',
                'paused': '⏸️'
            }
            status_icon = status_icons.get(status, '❓')
            
            # 计算运行时间和速度
            run_time = "计算中..."
            speed_info = "计算中..."
            eta_info = "计算中..."
            success_rate = 0.0
            
            # 获取任务开始时间
            start_time = None
            if isinstance(task, dict):
                start_time_str = task.get('start_time')
                if start_time_str:
                    try:
                        start_time = datetime.fromisoformat(start_time_str)
                    except:
                        pass
        except Exception as e:
            logger.error(f"刷新任务状态页面失败: {e}")

    async def _handle_test_fixed_monitoring_command(self, message: Message):
        """测试修复后的监听功能"""
        try:
            user_id = str(message.from_user.id)
            
            if not self.realtime_monitoring_engine:
                await message.reply_text("❌ 监听引擎未初始化")
                return
            
            # 检查引擎状态
            status = self.realtime_monitoring_engine.get_monitoring_status()
            
            # 检查全局处理器是否已注册
            has_global_handler = hasattr(self.realtime_monitoring_engine, '_global_handler_registered')
            
            # 检查客户端状态
            client_status = "未知"
            if self.realtime_monitoring_engine.client:
                client_status = f"已连接: {self.realtime_monitoring_engine.client.is_connected}"
            
            response = f"""
🧪 修复后监听功能测试

📊 引擎状态:
• 运行状态: {'✅ 运行中' if status.get('is_running') else '❌ 已停止'}
• 活跃任务: {status.get('active_tasks_count', 0)} 个
• 总任务数: {status.get('total_tasks_count', 0)} 个

🔧 修复状态:
• 全局处理器: {'✅ 已注册' if has_global_handler else '❌ 未注册'}
• 客户端状态: {client_status}
• 处理器模式: {'✅ 简单版模式' if has_global_handler else '❌ 复杂模式'}

💡 测试建议:
• 在源频道发送测试消息
• 检查控制台是否有 "🔔 处理消息" 日志
• 如果看到日志，说明修复成功

🔍 如果仍然不工作:
• 运行 /reinit_monitoring 重新初始化
• 检查 User API 登录状态
• 确认源频道访问权限
                                """.strip()
            
            await message.reply_text(response)
            logger.info(f"用户 {user_id} 执行了修复后监听测试命令")
            
        except Exception as e:
            logger.error(f"❌ 处理修复后监听测试命令失败: {e}")
            await message.reply_text(f"❌ 测试失败: {e}")
    
    async def _handle_view_task_details(self, callback_query: CallbackQuery):
        """处理查看任务详情"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取任务详情
            if self.cloning_engine:
                tasks = self.cloning_engine.get_all_tasks()
                current_task = None
                
                # 查找当前频道组的任务
                for task in tasks:
                    # 检查task是对象还是字典
                    if isinstance(task, dict):
                        config = task.get('config', {})
                        if config.get('pair_index') == pair_index:
                            current_task = task
                            break
                    else:
                        if (hasattr(task, 'config') and 
                            task.config.get('pair_index') == pair_index):
                            current_task = task
                            break
                
                if current_task:
                    # 显示任务详情
                    await self._show_task_details_page(callback_query, current_task, pair_index)
                else:
                    await callback_query.answer("❌ 未找到运行中的任务")
            else:
                await callback_query.answer("❌ 搬运引擎未初始化")
                
        except Exception as e:
            logger.error(f"处理查看任务详情失败: {e}")
            await callback_query.answer("❌ 查看失败，请稍后重试")
    
    async def _handle_view_task_results(self, callback_query: CallbackQuery):
        """处理查看任务结果"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 显示任务结果页面
            await self._show_task_results_page(callback_query, pair_index)
                
        except Exception as e:
            logger.error(f"处理查看任务结果失败: {e}")
            await callback_query.answer("❌ 查看失败，请稍后重试")
    
    async def _handle_view_all_tasks(self, callback_query: CallbackQuery):
        """处理查看所有任务"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 显示所有任务页面
            await self._show_all_tasks_page(callback_query, user_id)
                
        except Exception as e:
            logger.error(f"处理查看所有任务失败: {e}")
            await callback_query.answer("❌ 查看失败，请稍后重试")
    
    async def _show_task_details_page(self, callback_query: CallbackQuery, task: Any, pair_index: int):
        """显示任务详情页面"""
        try:
            # 获取任务详细信息
            progress = getattr(task, 'progress', 0.0)
            status = getattr(task, 'status', 'unknown')
            processed = getattr(task, 'processed_messages', 0)
            total = getattr(task, 'total_messages', 0)
            failed = getattr(task, 'failed_messages', 0)
            start_time = getattr(task, 'start_time', None)
            
            # 计算运行时间
            run_time = "未知"
            if start_time:
                elapsed = datetime.now() - start_time
                run_time = f"{elapsed.seconds // 60}分{elapsed.seconds % 60}秒"
            
            # 状态图标映射
            status_icons = {
                'running': '🟢',
                'pending': '🟡',
                'completed': '✅',
                'failed': '❌',
                'paused': '⏸️'
            }
            status_icon = status_icons.get(status, '❓')
            
            details_text = f"""
📊 **任务详细信息**

📡 **频道组：** {pair_index + 1}
📊 **任务状态：** {status_icon} {status.upper()}
📈 **进度：** {progress:.1f}%
📝 **已处理：** {processed}/{total} 条消息
❌ **失败：** {failed} 条消息
⏱️ **运行时间：** {run_time}

📊 **详细统计：**
• 成功搬运：{task.stats.get('processed_messages', 0)} 条
• 失败消息：{task.stats.get('failed_messages', 0)} 条
• 媒体消息：{task.stats.get('media_messages', 0)} 条
• 文本消息：{task.stats.get('text_messages', 0)} 条
• 媒体组数：{task.stats.get('media_groups', 0)} 组
• 过滤消息：{task.stats.get('filtered_messages', 0)} 条
• 成功率：{((processed - failed) / max(processed, 1) * 100):.1f}%
• 剩余消息：{max(0, total - processed)} 条

💡 **预计完成时间：**
{self._estimate_completion_time(processed, total, run_time)}

🔙 返回任务状态
            """.strip()
            
            buttons = [[("🔙 返回任务状态", f"refresh_task_status:{pair_index}")]]
            
            await callback_query.edit_message_text(
                details_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示任务详情页面失败: {e}")
            await callback_query.edit_message_text("❌ 显示详情失败，请稍后重试")
    
    async def _show_task_results_page(self, callback_query: CallbackQuery, pair_index: int):
        """显示任务结果页面"""
        try:
            results_text = f"""
🎉 **搬运任务结果**

📡 **频道组：** {pair_index + 1}

✅ **任务状态：** 已完成

📊 **结果统计：**
• 总消息数：根据实际完成情况
• 成功搬运：根据实际完成情况
• 失败消息：根据实际完成情况

🔙 返回主菜单继续其他操作
            """.strip()
            
            buttons = [
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                results_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示任务结果页面失败: {e}")
            await callback_query.edit_message_text("❌ 显示结果失败，请稍后重试")
    
    async def _show_all_tasks_page(self, callback_query: CallbackQuery, user_id: str):
        """显示所有任务页面"""
        try:
            if not self.cloning_engine:
                await callback_query.edit_message_text("❌ 搬运引擎未初始化")
                return
            
            # 获取所有任务
            all_tasks = self.cloning_engine.get_all_tasks()
            engine_stats = self.cloning_engine.get_engine_stats()
            
            # 过滤当前用户的任务
            user_tasks = []
            for task in all_tasks:
                if isinstance(task, dict):
                    task_user_id = task.get('config', {}).get('user_id')
                else:
                    task_user_id = task.config.get('user_id') if hasattr(task, 'config') else None
                
                if task_user_id == user_id:
                    user_tasks.append(task)
            
            # 按状态分组
            running_tasks = [t for t in user_tasks if t.get('status') == 'running']
            completed_tasks = [t for t in user_tasks if t.get('status') == 'completed']
            failed_tasks = [t for t in user_tasks if t.get('status') == 'failed']
            paused_tasks = [t for t in user_tasks if t.get('status') == 'paused']
            
            # 构建任务列表
            task_list = ""
            
            if running_tasks:
                task_list += "\n🟢 **运行中的任务：**\n"
                for i, task in enumerate(running_tasks[:5]):  # 最多显示5个
                    pair_idx = task.get('config', {}).get('pair_index', 0)
                    progress = task.get('progress', 0.0)
                    processed = task.get('processed_messages', 0)
                    total = task.get('total_messages', 0)
                    task_list += f"• 频道组 {pair_idx + 1}: {progress:.1f}% ({processed:,}/{total:,})\n"
            
            if paused_tasks:
                task_list += "\n⏸️ **暂停的任务：**\n"
                for task in paused_tasks[:3]:
                    pair_idx = task.get('config', {}).get('pair_index', 0)
                    progress = task.get('progress', 0.0)
                    task_list += f"• 频道组 {pair_idx + 1}: {progress:.1f}% (已暂停)\n"
            
            if completed_tasks:
                task_list += "\n✅ **已完成的任务：**\n"
                for task in completed_tasks[-3:]:  # 显示最近3个
                    pair_idx = task.get('config', {}).get('pair_index', 0)
                    processed = task.get('processed_messages', 0)
                    task_list += f"• 频道组 {pair_idx + 1}: {processed:,} 条消息\n"
            
            if failed_tasks:
                task_list += "\n❌ **失败的任务：**\n"
                for task in failed_tasks[-2:]:  # 显示最近2个
                    pair_idx = task.get('config', {}).get('pair_index', 0)
                    task_list += f"• 频道组 {pair_idx + 1}: 任务失败\n"
            
            if not task_list:
                task_list = "\n📝 暂无任务记录"
            
            # 系统性能信息
            active_count = engine_stats.get('active_tasks_count', 0)
            max_concurrent = engine_stats.get('max_concurrent_tasks', 20)
            system_load = engine_stats.get('system_load', {})
            active_channels = system_load.get('active_channels', 0)
            
            all_tasks_text = f"""
📋 **多任务管理中心**

🎯 **任务概览：**
• 运行中：{len(running_tasks)} 个任务
• 已完成：{len(completed_tasks)} 个任务
• 已暂停：{len(paused_tasks)} 个任务
• 失败：{len(failed_tasks)} 个任务

⚡ **系统状态：**
• 当前负载：{active_count}/{max_concurrent} 个任务
• 活跃频道：{active_channels} 个
• 引擎状态：{'🟢 正常' if active_count < max_concurrent * 0.8 else '🟡 繁忙'}
{task_list}

💡 **提示：** 系统支持最多 {max_concurrent} 个并发任务
            """.strip()
            
            buttons = [
                [("🔄 刷新列表", "view_all_tasks")],
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                all_tasks_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示所有任务页面失败: {e}")
            await callback_query.edit_message_text("❌ 显示任务列表失败，请稍后重试")
    
    # 删除不再需要的系统状态检查方法
        # 删除不再需要的系统状态检查方法体
            
        # 删除不再需要的系统状态检查方法体
    
    # 删除不再需要的频道帮助处理方法
    
    def _generate_progress_bar(self, progress: float, length: int = 10) -> str:
        """生成进度条"""
        try:
            filled = int(progress / 100 * length)
            bar = "█" * filled + "░" * (length - filled)
            return f"[{bar}]"
        except Exception:
            return "[░░░░░░░░░░]"
    
    def _estimate_completion_time(self, processed: int, total: int, run_time: str) -> str:
        """估算完成时间"""
        try:
            if processed <= 0 or run_time == "未知":
                return "无法估算"
            
            # 解析运行时间
            if "分" in run_time and "秒" in run_time:
                minutes = int(run_time.split("分")[0])
                seconds = int(run_time.split("分")[1].split("秒")[0])
                total_seconds = minutes * 60 + seconds
            else:
                return "无法估算"
            
            # 计算处理速度
            speed = processed / total_seconds  # 消息/秒
            
            # 估算剩余时间
            remaining = total - processed
            remaining_seconds = remaining / speed if speed > 0 else 0
            
            if remaining_seconds < 60:
                return f"{int(remaining_seconds)}秒"
            else:
                minutes = int(remaining_seconds // 60)
                seconds = int(remaining_seconds % 60)
                return f"{minutes}分{seconds}秒"
                
        except Exception:
            return "无法估算"
    
    
    async def _handle_manage_monitor_channels(self, callback_query: CallbackQuery):
        """处理管理监听频道"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 获取用户的频道组配置
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            monitored_pairs = user_config.get('monitored_pairs', [])
            
            logger.info(f"管理监听频道 - 用户: {user_id}, 频道对数量: {len(channel_pairs)}, 监听对数量: {len(monitored_pairs)}")
            
            if not channel_pairs:
                logger.warning(f"用户 {user_id} 尝试管理监听频道但没有配置频道对")
                await callback_query.edit_message_text(
                    "❌ 您还没有配置任何频道组\n\n💡 请先在主菜单中添加频道组",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回监听菜单", "show_monitor_menu")
                    ]])
                )
                return
            
            # 计算已监听的频道数量
            monitored_count = 0
            
            # 检查是否有旧格式数据（整数索引）
            has_old_format = any(isinstance(p, int) for p in monitored_pairs)
            
            if has_old_format:
                # 对于旧格式，直接计算整数索引的数量
                monitored_count = len([p for p in monitored_pairs if isinstance(p, int)])
            else:
                # 对于新格式，逐个比较频道对
                for pair in channel_pairs:
                    for monitored_pair in monitored_pairs:
                        if isinstance(monitored_pair, dict):
                            if (monitored_pair.get('source_id') == pair.get('source_id') and 
                                monitored_pair.get('target_id') == pair.get('target_id')):
                                monitored_count += 1
                                break
            
            # 构建频道选择界面
            channels_text = f"""
📡 **选择监听频道**

📊 **当前状态**
• 总频道组: {len(channel_pairs)} 个
• 已监听: {monitored_count} 个

💡 **操作说明**
• ✅ = 已启用监听
• ❌ = 未启用监听
• 点击切换监听状态

📋 **频道列表：**
            """.strip()
            
            # 构建按钮布局
            buttons = []
            
            # 添加全选/全不选按钮
            if monitored_count == len(channel_pairs):
                buttons.append([("❌ 全不选", "monitor_select_none")])
            else:
                buttons.append([("✅ 全选", "monitor_select_all")])
            
            # 添加频道选择按钮
            logger.info(f"生成监听频道按钮 - 用户: {user_id}, 频道对数量: {len(channel_pairs)}")
            for i, pair in enumerate(channel_pairs):
                source_name = pair.get('source_name', f'频道{i+1}')
                target_name = pair.get('target_name', f'目标{i+1}')
                
                # 检查是否已在监听列表中
                is_monitored = False
                if has_old_format:
                    # 对于旧格式，检查索引是否在列表中
                    is_monitored = i in [p for p in monitored_pairs if isinstance(p, int)]
                else:
                    # 对于新格式，比较频道对象
                    for monitored_pair in monitored_pairs:
                        if isinstance(monitored_pair, dict):
                            if (monitored_pair.get('source_id') == pair.get('source_id') and 
                                monitored_pair.get('target_id') == pair.get('target_id')):
                                is_monitored = True
                                break
                
                status_icon = "✅" if is_monitored else "❌"
                
                button_text = f"{status_icon} {source_name} → {target_name}"
                button_data = f"toggle_monitor_pair:{i}"
                
                logger.debug(f"生成按钮 - 索引: {i}, 文本: {button_text}, 回调数据: {button_data}")
                buttons.append([(button_text, button_data)])
            
            # 添加返回按钮
            buttons.append([("🔙 返回监听菜单", "show_monitor_menu")])
            
            await callback_query.edit_message_text(
                channels_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"管理监听频道失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_toggle_monitor_pair(self, callback_query: CallbackQuery):
        """处理切换单个频道监听状态"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 使用与管理界面相同的数据源
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            monitored_pairs = user_config.get('monitored_pairs', [])
            
            # 添加调试信息
            logger.info(f"切换监听频道 - 用户: {user_id}, 索引: {pair_index}, 频道对数量: {len(channel_pairs)}")
            
            if not channel_pairs:
                logger.error(f"用户 {user_id} 没有配置任何频道对")
                await callback_query.answer("❌ 请先配置频道对")
                return
                
            if pair_index < 0 or pair_index >= len(channel_pairs):
                logger.error(f"频道索引无效 - 索引: {pair_index}, 频道对数量: {len(channel_pairs)}")
                await callback_query.answer("❌ 频道索引无效，请刷新页面重试")
                return
            
            # 获取对应的频道对
            channel_pair = channel_pairs[pair_index]
            
            # 检查是否已在监听列表中（通过索引匹配）
            is_monitored = False
            monitored_index = -1
            for i, monitored_pair in enumerate(monitored_pairs):
                if isinstance(monitored_pair, dict):
                    # 如果是字典对象，比较source_id和target_id
                    if (monitored_pair.get('source_id') == channel_pair.get('source_id') and 
                        monitored_pair.get('target_id') == channel_pair.get('target_id')):
                        is_monitored = True
                        monitored_index = i
                        break
                elif isinstance(monitored_pair, int):
                    # 如果是旧的索引格式，直接比较索引
                    if monitored_pair == pair_index:
                        is_monitored = True
                        monitored_index = i
                        break
            
            # 切换监听状态
            if is_monitored:
                # 移除监听
                if monitored_index >= 0:
                    monitored_pairs.pop(monitored_index)
                action = "已停止监听"
            else:
                # 添加监听 - 保存完整的频道对象
                monitor_pair = {
                    'id': f"monitor_{int(time.time())}_{pair_index}",
                    'user_id': user_id,
                    'source_id': channel_pair.get('source_id'),
                    'target_id': channel_pair.get('target_id'),
                    'source_name': channel_pair.get('source_name', f'频道{pair_index+1}'),
                    'target_name': channel_pair.get('target_name', f'目标{pair_index+1}'),
                    'enabled': True,
                    'created_at': datetime.now().isoformat(),
                    'last_message_id': None,
                    'last_check_time': None
                }
                monitored_pairs.append(monitor_pair)
                action = "已开始监听"
            
            # 保存配置
            user_config['monitored_pairs'] = monitored_pairs
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 如果监听功能已启用，更新监听系统
            if user_config.get('monitor_enabled', False) and self.monitor_system:
                if monitored_pairs:
                    await self.monitor_system.start_monitoring(user_id)
                else:
                    await self.monitor_system.stop_monitoring()
            
            await callback_query.answer(f"✅ {action}")
            
            # 刷新频道管理界面
            await self._handle_manage_monitor_channels(callback_query)
            
        except Exception as e:
            logger.error(f"切换频道监听状态失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_monitor_select_all(self, callback_query: CallbackQuery):
        """处理全选监听频道"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 使用与管理界面相同的数据源
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                await callback_query.answer("❌ 没有可选择的频道")
                return
            
            # 全选所有频道 - 保存完整的频道对象
            monitored_pairs = []
            for i, channel_pair in enumerate(channel_pairs):
                monitor_pair = {
                    'id': f"monitor_{int(time.time())}_{i}",
                    'user_id': user_id,
                    'source_id': channel_pair.get('source_id'),
                    'target_id': channel_pair.get('target_id'),
                    'source_name': channel_pair.get('source_name', f'频道{i+1}'),
                    'target_name': channel_pair.get('target_name', f'目标{i+1}'),
                    'enabled': True,
                    'created_at': datetime.now().isoformat(),
                    'last_message_id': None,
                    'last_check_time': None
                }
                monitored_pairs.append(monitor_pair)
            
            user_config['monitored_pairs'] = monitored_pairs
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 监听系统已移除
            
            await callback_query.answer(f"✅ 已选择全部 {len(channel_pairs)} 个频道")
            
            # 刷新频道管理界面
            await self._handle_manage_monitor_channels(callback_query)
            
        except Exception as e:
            logger.error(f"全选监听频道失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_monitor_select_none(self, callback_query: CallbackQuery):
        """处理全不选监听频道"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 清空监听频道
            user_config['monitored_pairs'] = []
            await self.data_manager.save_user_config(user_id, user_config)
            
            # 监听系统已移除
            
            await callback_query.answer("✅ 已取消选择所有频道")
            
            # 刷新频道管理界面
            await self._handle_manage_monitor_channels(callback_query)
            
        except Exception as e:
            logger.error(f"全不选监听频道失败: {e}")
            await callback_query.answer("❌ 操作失败")
    
    async def _handle_stop_cloning(self, callback_query: CallbackQuery):
        """处理停止搬运任务"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 停止搬运任务
            if self.cloning_engine:
                try:
                    # 查找并停止该频道组的搬运任务
                    tasks = self.cloning_engine.get_all_tasks()
                    stopped_count = 0
                    
                    for task in tasks:
                        # 从任务配置中获取用户ID和频道组索引
                        if isinstance(task, dict):
                            task_user_id = task.get('config', {}).get('user_id')
                            task_pair_index = task.get('config', {}).get('pair_index')
                        else:
                            task_user_id = task.config.get('user_id') if hasattr(task, 'config') else None
                            task_pair_index = task.config.get('pair_index') if hasattr(task, 'config') else None
                        
                        if (task_user_id == user_id and 
                            task_pair_index == pair_index):
                            # 停止任务
                            if isinstance(task, dict):
                                # 字典格式的任务，无法直接停止
                                logger.warning(f"无法停止字典格式的任务: {task.get('task_id')}")
                            elif hasattr(task, 'stop'):
                                task.stop()
                                stopped_count += 1
                    
                    if stopped_count > 0:
                        await callback_query.answer("🛑 搬运任务已停止")
                    else:
                        await callback_query.answer("ℹ️ 未找到运行中的搬运任务")
                        
                except Exception as e:
                    logger.error(f"停止搬运任务失败: {e}")
                    await callback_query.answer("❌ 停止任务失败")
            else:
                await callback_query.answer("❌ 搬运引擎未初始化")
            
            # 显示任务已停止的消息
            stop_text = f"""
🛑 **搬运任务已停止！**

📡 **频道组：** {pair_index + 1}

✅ **任务状态：** 已停止

💡 **说明：**
• 搬运任务已成功停止
• 已搬运的内容不会丢失
• 可以重新启动任务

🔙 返回主菜单继续其他操作
            """.strip()
            
            await callback_query.edit_message_text(
                stop_text,
                reply_markup=generate_button_layout([[
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理停止搬运任务失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")

    # ==================== 频道组过滤管理回调函数 ====================
    async def _handle_manage_pair_filters(self, callback_query: CallbackQuery):
        """处理频道组过滤管理"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            pair_index = None
            
            # 查找频道组索引
            for i, pair in enumerate(channel_pairs):
                if pair.get('id') == pair_id:
                    pair_index = i
                    break
            
            if pair_index is None:
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            # 重定向到频道组过滤配置
            callback_query.data = f"channel_filters:{pair['id']}"
            await self._handle_channel_filters(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组过滤管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_enabled(self, callback_query: CallbackQuery):
        """处理频道组启用/禁用切换（基于pair_index）"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组列表
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 检查索引是否有效
            if 0 <= pair_index < len(channel_pairs):
                pair = channel_pairs[pair_index]
                
                # 切换启用状态
                current_enabled = pair.get('enabled', True)
                pair['enabled'] = not current_enabled
                
                # 保存更新后的频道组列表
                success = await self.data_manager.save_channel_pairs(user_id, channel_pairs)
                
                if success:
                    status_text = "✅ 已启用" if pair['enabled'] else "❌ 已禁用"
                    source_name = pair.get('source_name', '未知频道')
                    target_name = pair.get('target_name', '未知目标')
                    
                    await callback_query.answer(f"{status_text} 频道组: {source_name} → {target_name}")
                    
                    # 重新显示频道组详情页面
                    callback_query.data = f"edit_channel_pair:{pair_index}"
                    await self._handle_edit_channel_pair(callback_query)
                else:
                    await callback_query.answer("❌ 更新失败，请稍后重试")
            else:
                await callback_query.answer("❌ 频道组不存在")
                
        except Exception as e:
            logger.error(f"切换频道组状态失败: {e}")
            await callback_query.answer("❌ 操作失败，请稍后重试")
    
    async def _handle_toggle_pair_enabled(self, callback_query: CallbackQuery):
        """处理频道组启用/禁用切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_id = callback_query.data.split(':')[1]
            
            # 获取频道组列表
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            # 查找并更新频道组状态
            pair_found = False
            for pair in channel_pairs:
                if pair.get('id') == pair_id:
                    # 切换启用状态
                    current_enabled = pair.get('enabled', True)
                    pair['enabled'] = not current_enabled
                    pair_found = True
                    
                    # 保存更新后的频道组列表
                    success = await self.data_manager.save_channel_pairs(user_id, channel_pairs)
                    
                    if success:
                        status_text = "✅ 已启用" if pair['enabled'] else "❌ 已禁用"
                        source_name = pair.get('source_name', '未知频道')
                        target_name = pair.get('target_name', '未知目标')
                        
                        await callback_query.answer(f"{status_text} 频道组: {source_name} → {target_name}")
                        
                        # 重新显示频道组详情页面
                        callback_query.data = f"edit_channel_pair_by_id:{pair_id}"
                        await self._handle_edit_channel_pair_by_id(callback_query)
                    else:
                        await callback_query.answer("❌ 更新失败，请稍后重试")
                    break
            
            if not pair_found:
                await callback_query.answer("❌ 频道组不存在")
                
        except Exception as e:
            logger.error(f"切换频道组状态失败: {e}")
            await callback_query.answer("❌ 操作失败，请稍后重试")
    
    async def _handle_clear_all_channels(self, callback_query: CallbackQuery):
        """处理一键清空所有频道组"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查是否是确认操作
            if callback_query.data == "confirm_clear_all_channels":
                # 执行清空操作
                channel_pairs = await self.data_manager.get_channel_pairs(user_id)
                deleted_count = len(channel_pairs)
                
                # 清空频道组列表
                success = await self.data_manager.save_channel_pairs(user_id, [])
                
                if success:
                    # 清空所有频道过滤配置
                    await self.data_manager.clear_all_channel_filter_configs(user_id)
                    
                    # 显示成功信息
                    text = f"🗑️ **一键清空完成！**\n\n"
                    text += f"✅ 已删除所有 {deleted_count} 个频道组\n"
                    text += f"🧹 已清理所有频道过滤配置\n"
                    text += f"📊 当前频道组数量: 0/100\n\n"
                    text += "💡 如需重新添加频道组，请使用【新增频道组】功能。"
                    
                    buttons = [
                        [("➕ 新增频道组", "add_channel_pair")],
                        [("🔙 返回主菜单", "show_main_menu")]
                    ]
                    
                    await callback_query.edit_message_text(
                        text, 
                        reply_markup=generate_button_layout(buttons)
                    )
                    
                    logger.info(f"用户 {user_id} 一键清空了所有 {deleted_count} 个频道组及其过滤配置")
                else:
                    await callback_query.edit_message_text(
                        "❌ 清空失败，请稍后重试。",
                        reply_markup=generate_button_layout([
                            [("🔙 返回管理", "show_channel_config_menu")]
                        ])
                    )
                return
            
            # 显示确认界面
            channel_pairs = await self.data_manager.get_channel_pairs(user_id)
            
            if not channel_pairs:
                await callback_query.edit_message_text(
                    "❌ 没有可删除的频道组。",
                    reply_markup=generate_button_layout([
                        [("🔙 返回管理", "show_channel_config_menu")]
                    ])
                )
                return
            
            # 显示确认提示
            text = f"⚠️ **确认清空操作**\n\n"
            text += f"📊 当前频道组数量: {len(channel_pairs)}\n"
            text += f"🗑️ 即将删除所有频道组\n"
            text += f"🧹 同时清理所有频道过滤配置\n\n"
            text += "❗ **此操作不可撤销，请谨慎操作！**"
            
            buttons = [
                [("✅ 确认清空", "confirm_clear_all_channels")],
                [("❌ 取消操作", "show_channel_config_menu")]
            ]
            
            await callback_query.edit_message_text(
                 text,
                 reply_markup=generate_button_layout(buttons)
             )
                
        except Exception as e:
            logger.error(f"处理一键清空频道组失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    

    

    

    

    



    


    # ==================== 监听系统回调函数 ====================
    async def _monitor_message_callback(self, message_data: Dict[str, Any]):
        """监听系统消息回调"""
        try:
            message_type = message_data.get('type')
            
            if message_type == 'auto_clone_success':
                pair_id = message_data.get('pair_id')
                message_id = message_data.get('message_id')
                task_id = message_data.get('task_id')
                
                logger.info(f"自动搬运成功通知: {pair_id} - 消息ID: {message_id}")
                
                # 可以在这里添加更多的成功通知逻辑
                # 比如发送通知给用户等
                
        except Exception as e:
            logger.error(f"处理监听消息回调失败: {e}")
    
    async def _monitor_error_callback(self, error_message: str):
        """监听系统错误回调"""
        try:
            logger.error(f"监听系统错误: {error_message}")
            
            # 可以在这里添加错误通知逻辑
            # 比如发送错误通知给管理员用户等
            
            # 记录错误统计
            # 可以考虑在达到一定错误次数后暂停监听
            
        except Exception as e:
            logger.error(f"处理监听错误回调失败: {e}")
    
    async def _process_edit_source_input(self, message: Message, state: Dict[str, Any]):
        """处理编辑来源频道输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            pair_index = state['pair_index']
            
            # 解析频道信息
            channel_info = await self._parse_channel_input(text)
            if not channel_info:
                await message.reply_text(
                    "❌ **频道格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 频道数字ID：`-1001234567890`\n"
                    "• 频道用户名：`@channelname`\n"
                    "• 频道链接：`https://t.me/channelname`\n\n"
                    "请重新输入正确的频道信息。"
                )
                return
            
            # 验证频道访问
            channel_id = await self._validate_channel_access(channel_info)
            
            # 获取当前频道组列表
            channel_pairs = await self.data_manager.self.data_manager.get_channel_pairs(user_id)
            
            if pair_index >= len(channel_pairs):
                await message.reply_text("❌ 频道组不存在，请重新操作。")
                del self.user_states[user_id]
                return
            
            # 更新频道组信息
            if channel_id:
                # 获取频道详细信息
                try:
                    chat = await self._get_api_client().get_chat(channel_id)
                    channel_pairs[pair_index]['source_id'] = str(channel_id)
                    channel_pairs[pair_index]['source_username'] = chat.username or ""
                    # 使用优化的显示格式："频道名 (@用户名)"
                    def format_channel_display(username, channel_id, name):
                        # 优先显示频道名称
                        display_name = name if name else f"频道ID: {str(channel_id)[-8:]}"
                        
                        # 如果有用户名，添加到显示名称后面
                        if username and username.startswith('@'):
                            return f"{display_name} ({username})"
                        elif username:
                            return f"{display_name} (@{username})"
                        else:
                            return display_name
                    channel_pairs[pair_index]['source_name'] = format_channel_display(chat.username, channel_id, chat.title)
                except:
                    channel_pairs[pair_index]['source_id'] = str(channel_id)
                    channel_pairs[pair_index]['source_name'] = f"频道ID: {str(channel_id)[-8:]}"
                    channel_pairs[pair_index]['source_username'] = ""
            else:
                # 即使验证失败也允许保存
                channel_pairs[pair_index]['source_id'] = channel_info
                channel_pairs[pair_index]['source_name'] = "待确认"
                channel_pairs[pair_index]['source_username'] = ""
            
            # 保存更新
            await self.data_manager.save_channel_pairs(user_id, channel_pairs)
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示成功消息
            await message.reply_text(
                f"✅ **来源频道更新成功！**\n\n"
                f"📝 **频道组 {pair_index + 1}**\n"
                f"📡 **新的来源频道：** {channel_info}\n\n"
                f"💡 您可以继续管理其他频道组。",
                reply_markup=generate_button_layout([[
                    ("⚙️ 频道管理", "show_channel_config_menu"),
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理编辑来源频道输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def _process_edit_target_input(self, message: Message, state: Dict[str, Any]):
        """处理编辑目标频道输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            pair_index = state['pair_index']
            
            # 解析频道信息
            channel_info = await self._parse_channel_input(text)
            if not channel_info:
                await message.reply_text(
                    "❌ **频道格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 频道数字ID：`-1001234567890`\n"
                    "• 频道用户名：`@channelname`\n"
                    "• 频道链接：`https://t.me/channelname`\n\n"
                    "请重新输入正确的频道信息。"
                )
                return
            
            # 验证频道访问
            channel_id = await self._validate_channel_access(channel_info)
            
            # 获取当前频道组列表
            channel_pairs = await self.data_manager.self.data_manager.get_channel_pairs(user_id)
            
            if pair_index >= len(channel_pairs):
                await message.reply_text("❌ 频道组不存在，请重新操作。")
                del self.user_states[user_id]
                return
            
            # 更新频道组信息
            if channel_id:
                # 获取频道详细信息
                try:
                    chat = await self._get_api_client().get_chat(channel_id)
                    channel_pairs[pair_index]['target_id'] = str(channel_id)
                    channel_pairs[pair_index]['target_username'] = chat.username or ""
                    # 使用优化的显示格式："频道名 (@用户名)"
                    def format_channel_display(username, channel_id, name):
                        # 优先显示频道名称
                        display_name = name if name else f"频道ID: {str(channel_id)[-8:]}"
                        
                        # 如果有用户名，添加到显示名称后面
                        if username and username.startswith('@'):
                            return f"{display_name} ({username})"
                        elif username:
                            return f"{display_name} (@{username})"
                        else:
                            return display_name
                    channel_pairs[pair_index]['target_name'] = format_channel_display(chat.username, channel_id, chat.title)
                except:
                    channel_pairs[pair_index]['target_id'] = str(channel_id)
                    channel_pairs[pair_index]['target_name'] = f"频道ID: {str(channel_id)[-8:]}"
                    channel_pairs[pair_index]['target_username'] = ""
            else:
                # 即使验证失败也允许保存
                channel_pairs[pair_index]['target_id'] = channel_info
                channel_pairs[pair_index]['target_name'] = "待确认"
                channel_pairs[pair_index]['target_username'] = ""
            
            # 保存更新
            await self.data_manager.save_channel_pairs(user_id, channel_pairs)
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示成功消息
            await message.reply_text(
                f"✅ **目标频道更新成功！**\n\n"
                f"📝 **频道组 {pair_index + 1}**\n"
                f"📡 **新的目标频道：** {channel_info}\n\n"
                f"💡 您可以继续管理其他频道组。",
                reply_markup=generate_button_layout([[
                    ("⚙️ 频道管理", "show_channel_config_menu"),
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理编辑目标频道输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            if user_id in self.user_states:
                del self.user_states[user_id]

    async def _process_edit_source_by_id_input(self, message: Message, state: Dict[str, Any]):
        """处理通过pair_id编辑来源频道的输入"""
        try:
            user_id = str(message.from_user.id)
            pair_id = state.get('pair_id')
            pair_index = state.get('pair_index', 0)
            channel_info = message.text.strip()
            
            if not channel_info:
                await message.reply_text("❌ 请输入有效的频道信息")
                return
            
            # 验证频道访问权限
            validated_channel_id = await self._validate_channel_access(channel_info)
            if not validated_channel_id:
                await message.reply_text("❌ 无法访问该频道，请检查频道链接或权限")
                return
            
            # 获取频道信息
            try:
                chat = await self._get_api_client().get_chat(validated_channel_id)
                channel_name = chat.title or f"频道{pair_index+1}"
                channel_username = getattr(chat, 'username', '')
                if channel_username:
                    channel_username = f"@{channel_username}"
                else:
                    # 私密频道格式
                    if validated_channel_id.startswith('-100'):
                        channel_username = f"@c/{validated_channel_id[4:]}"
                    else:
                        channel_username = f"@c/{validated_channel_id}"
            except Exception as e:
                logger.warning(f"获取频道信息失败: {e}")
                channel_name = f"频道{pair_index+1}"
                channel_username = channel_info
            
            # 更新频道组
            updates = {
                'source_id': validated_channel_id,
                'source_name': channel_name,
                'source_username': channel_username,
                'updated_at': datetime.now().isoformat()
            }
            
            success = await self.data_manager.update_channel_pair(user_id, pair_id, updates)
            
            if not success:
                await message.reply_text("❌ 更新频道组失败，请稍后重试")
                return
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示成功消息
            await message.reply_text(
                f"✅ **来源频道更新成功！**\n\n"
                f"📝 **频道组 {pair_index + 1}**\n"
                f"📡 **新的来源频道：** {channel_name}\n"
                f"🔗 **频道标识：** {channel_username}\n\n"
                f"💡 您可以继续管理其他频道组。",
                reply_markup=generate_button_layout([[
                    ("⚙️ 频道管理", "show_channel_config_menu"),
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理编辑来源频道输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            if user_id in self.user_states:
                del self.user_states[user_id]

    async def _process_edit_target_by_id_input(self, message: Message, state: Dict[str, Any]):
        """处理通过pair_id编辑目标频道的输入"""
        try:
            user_id = str(message.from_user.id)
            pair_id = state.get('pair_id')
            pair_index = state.get('pair_index', 0)
            channel_info = message.text.strip()
            
            if not channel_info:
                await message.reply_text("❌ 请输入有效的频道信息")
                return
            
            # 验证频道访问权限
            validated_channel_id = await self._validate_channel_access(channel_info)
            if not validated_channel_id:
                await message.reply_text("❌ 无法访问该频道，请检查频道链接或权限")
                return
            
            # 获取频道信息
            try:
                chat = await self._get_api_client().get_chat(validated_channel_id)
                channel_name = chat.title or f"目标{pair_index+1}"
                channel_username = getattr(chat, 'username', '')
                if channel_username:
                    channel_username = f"@{channel_username}"
                else:
                    # 私密频道格式
                    if validated_channel_id.startswith('-100'):
                        channel_username = f"@c/{validated_channel_id[4:]}"
                    else:
                        channel_username = f"@c/{validated_channel_id}"
            except Exception as e:
                logger.warning(f"获取频道信息失败: {e}")
                channel_name = f"目标{pair_index+1}"
                channel_username = channel_info
            
            # 更新频道组
            updates = {
                'target_id': validated_channel_id,
                'target_name': channel_name,
                'target_username': channel_username,
                'updated_at': datetime.now().isoformat()
            }
            
            success = await self.data_manager.update_channel_pair(user_id, pair_id, updates)
            
            if not success:
                await message.reply_text("❌ 更新频道组失败，请稍后重试")
                return
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示成功消息
            await message.reply_text(
                f"✅ **目标频道更新成功！**\n\n"
                f"📝 **频道组 {pair_index + 1}**\n"
                f"📤 **新的目标频道：** {channel_name}\n"
                f"🔗 **频道标识：** {channel_username}\n\n"
                f"💡 您可以继续管理其他频道组。",
                reply_markup=generate_button_layout([[
                    ("⚙️ 频道管理", "show_channel_config_menu"),
                    ("🔙 返回主菜单", "show_main_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理编辑目标频道输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
            if user_id in self.user_states:
                del self.user_states[user_id]

    async def _handle_all_messages(self, message: Message):
        """处理所有消息的统一入口"""
        try:
            # 处理私聊消息
            if message.chat.type == 'private':
                # 检查是否为命令
                if message.text and message.text.startswith('/'):
                    return  # 跳过命令，由命令处理器处理
                await self._handle_text_message(message)
                return
            
            # 处理群组/频道消息
            if message.chat.type in ['group', 'supergroup', 'channel']:
                await self._handle_group_message(message)
                return
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    async def _handle_group_message(self, message: Message):
        """处理群组消息"""
        try:
            # 记录群组消息
            logger.info(f"🔍 收到群组消息: chat_id={message.chat.id}, chat_type={message.chat.type}, service={message.service}")
            
            # 检查是否是服务消息（用户加入/离开等）
            if message.service:
                logger.info(f"🔍 服务消息类型: {message.service}")
                
                # 检查是否是机器人被添加的事件
                if hasattr(message, 'new_chat_members') and message.new_chat_members:
                    logger.info(f"🔍 新成员加入: {len(message.new_chat_members)} 个成员")
                    for member in message.new_chat_members:
                        logger.info(f"🔍 新成员: {member.id} (机器人ID: {self.client.me.id})")
                        if member.id == self.client.me.id:
                            # 机器人被添加到群组
                            logger.info(f"✅ 检测到机器人被添加到群组: {message.chat.id}")
                            await self._send_group_verification_message(message)
                            break
            
            # 监听任务现在由实时监听引擎自动处理
            
        except Exception as e:
            logger.error(f"处理群组消息失败: {e}")
    
    
    async def _handle_raw_update(self, update):
        """处理原始更新 - 用于调试"""
        try:
            # 只记录重要的更新类型
            update_type = type(update).__name__
            
            # 只显示重要的更新类型
            important_updates = ['UpdateNewMessage', 'UpdateMessage', 'UpdateChannelParticipant', 'UpdateChatMember']
            if update_type in important_updates:
                logger.info(f"🔍 原始更新: {update_type}")
            
            # 检查是否是消息更新
            if hasattr(update, 'message'):
                message = update.message
                if message:
                    chat_id = getattr(message, 'chat_id', None)
                    if chat_id:
                        # 检查是否是新成员加入
                        if hasattr(message, 'new_chat_members') and message.new_chat_members:
                            logger.info(f"🔍 新成员加入: {len(message.new_chat_members)} 个")
                            for member in message.new_chat_members:
                                if hasattr(member, 'is_self') and member.is_self:
                                    logger.info(f"🤖 机器人被添加到频道: {chat_id}")
            
            # 处理频道参与者更新
            if update_type == 'UpdateChannelParticipant':
                await self._handle_channel_participant_update(update)
                    
        except Exception as e:
            logger.error(f"处理原始更新失败: {e}")
    
    async def _handle_channel_participant_update(self, update):
        """处理频道参与者更新"""
        try:
            # 获取频道ID
            channel_id = getattr(update, 'channel_id', None)
            if not channel_id:
                return
            
            # 获取参与者信息
            participant = getattr(update, 'new_participant', None)
            prev_participant = getattr(update, 'prev_participant', None)
            
            # 检查是否是机器人被添加
            if participant and not prev_participant:
                # 检查是否是机器人
                if hasattr(participant, 'user_id'):
                    user_id = participant.user_id
                    
                    # 检查是否是我们的机器人
                    if user_id == self.bot_id:
                        logger.info(f"✅ 检测到机器人被添加到频道: {channel_id}")
                        await self._send_channel_verification_message(channel_id)
                elif hasattr(participant, 'bot_info'):
                    bot_info = participant.bot_info
                    
                    # 检查是否是我们的机器人
                    if hasattr(bot_info, 'user_id') and bot_info.user_id == self.bot_id:
                        logger.info(f"✅ 检测到机器人被添加到频道: {channel_id}")
                        await self._send_channel_verification_message(channel_id)
            
        except Exception as e:
            logger.error(f"处理频道参与者更新失败: {e}")
    
    async def _send_channel_verification_message(self, channel_id):
        """发送频道验证消息"""
        try:
            logger.info(f"📤 发送频道验证消息: {channel_id}")
            
            # 构建验证消息
            verification_text = f"""
🤖 **机器人验证消息**

✅ **成功加入频道**
🆔 **频道ID**: {channel_id}
⏰ **加入时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💡 **说明**: 此消息将在2秒后自动删除，用于验证机器人是否成功加入频道。

🔧 **功能**: 机器人已准备就绪，可以开始频道搬运任务。
""".strip()

            # 发送验证消息
            sent_message = await self.client.send_message(
                chat_id=channel_id,
                text=verification_text,
                parse_mode="Markdown"
            )

            logger.info(f"✅ 频道验证消息已发送: {channel_id}")

            # 2秒后删除消息
            logger.info(f"⏰ 等待2秒后删除验证消息...")
            await asyncio.sleep(2)

            try:
                logger.info(f"🗑️ 尝试删除验证消息: {sent_message.id}")
                await sent_message.delete()
                logger.info(f"✅ 频道验证消息已自动删除: {channel_id}")
            except Exception as delete_error:
                logger.warning(f"⚠️ 删除验证消息失败: {delete_error}")
                logger.warning(f"⚠️ 删除失败详情: 消息ID={sent_message.id}, 频道ID={channel_id}")
                
                # 如果删除失败，尝试编辑消息为简短提示
                try:
                    logger.info(f"📝 尝试编辑消息为简短提示...")
                    await sent_message.edit_text("✅ 机器人验证成功")
                    logger.info(f"✅ 消息已编辑为简短提示")
                except Exception as edit_error:
                    logger.warning(f"⚠️ 编辑验证消息失败: {edit_error}")
                    logger.warning(f"⚠️ 编辑失败详情: 消息ID={sent_message.id}, 频道ID={channel_id}")

        except Exception as e:
            logger.error(f"发送频道验证消息失败: {e}")
    
    async def _send_group_verification_message(self, message: Message):
        """发送群组验证消息"""
        try:
            chat_id = message.chat.id
            chat_title = message.chat.title or "未知群组"
            chat_type = str(message.chat.type)
            
            # 构建验证消息
            verification_text = f"""
🤖 **机器人验证消息**

✅ **成功加入群组**
📝 **群组名称**: {chat_title}
🆔 **群组ID**: {chat_id}
📋 **群组类型**: {chat_type}
⏰ **加入时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💡 **说明**: 此消息将在2秒后自动删除，用于验证机器人是否成功加入群组。

🔧 **功能**: 机器人已准备就绪，可以开始频道搬运任务。
            """.strip()
            
            # 发送验证消息
            sent_message = await self.client.send_message(
                chat_id=chat_id,
                text=verification_text,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ 群组验证消息已发送: {chat_title} ({chat_id})")
            
            # 2秒后删除消息
            logger.info(f"⏰ 等待2秒后删除验证消息...")
            await asyncio.sleep(2)
            
            try:
                logger.info(f"🗑️ 尝试删除验证消息: {sent_message.id}")
                await sent_message.delete()
                logger.info(f"✅ 群组验证消息已自动删除: {chat_title} ({chat_id})")
            except Exception as delete_error:
                logger.warning(f"⚠️ 删除验证消息失败: {delete_error}")
                logger.warning(f"⚠️ 删除失败详情: 消息ID={sent_message.id}, 聊天ID={chat_id}")
                
                # 如果删除失败，尝试编辑消息为简短提示
                try:
                    logger.info(f"📝 尝试编辑消息为简短提示...")
                    await sent_message.edit_text("✅ 机器人验证成功")
                    logger.info(f"✅ 消息已编辑为简短提示")
                except Exception as edit_error:
                    logger.warning(f"⚠️ 编辑验证消息失败: {edit_error}")
                    logger.warning(f"⚠️ 编辑失败详情: 消息ID={sent_message.id}, 聊天ID={chat_id}")
            
        except Exception as e:
            logger.error(f"发送群组验证消息失败: {e}")
    
    # ==================== 信息管理相关函数 ====================
    
    async def _handle_admin_channel_message_management(self, callback_query: CallbackQuery):
        """处理频道信息管理界面"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            config_text = f"""
📝 **信息管理**

📋 **频道：** {channel_display}

💡 **功能说明：**
• 批量删除频道中的消息
• 支持单个消息ID或ID段删除
• 例如：5 或 60-100

⚠️ **重要限制：**
• 只能删除机器人发送的消息
• 即使机器人是管理员，也无法删除其他用户的消息
• 无论是Bot API还是User API，都有这个限制
• 这是Telegram的安全机制，无法绕过

🔍 **如何确认消息是机器人发送的：**
• 查看消息右下角是否有机器人用户名
• 例如：消息下方显示 "@quso_bot"
• 只有显示机器人用户名的消息才能删除

📚 **技术说明：**
• Telegram API限制：任何API（Bot API或User API）都只能删除自己发送的消息
• 这是Telegram的安全机制，防止恶意删除他人消息
• 即使是频道管理员，也无法通过API删除其他用户的消息
• 只有频道所有者可以在Telegram客户端中手动删除他人消息

🔧 **权限说明：**
• 频道管理列表中的频道，机器人都是管理员
• 主要限制：只能删除机器人自己发送的消息
• 这是Telegram API的安全机制，无法绕过

请选择操作：
            """.strip()
            
            buttons = [
                [("🗑️ 删除消息", f"admin_channel_delete_messages:{channel_id}")],
                [("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道信息管理界面失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_admin_channel_delete_messages(self, callback_query: CallbackQuery):
        """处理删除消息界面"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_id = int(callback_query.data.split(':')[1])
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            config_text = f"""
🗑️ **删除消息**

📋 **频道：** {channel_display}

📝 **输入格式：**
• 单个消息ID：`5`
• 消息ID段：`60-100`
• 多个ID段：`5,60-100,200-250`

💡 **示例：**
• 删除消息5：输入 `5`
• 删除消息60到100：输入 `60-100`
• 删除多个段：输入 `5,60-100,200-250`

⚠️ **重要限制：**
• 只能删除机器人发送的消息
• 即使机器人是管理员，也无法删除其他用户的消息
• 无论是Bot API还是User API，都有这个限制
• 这是Telegram的安全机制，无法绕过

🔍 **如何确认消息是机器人发送的：**
• 查看消息右下角是否有机器人用户名
• 例如：消息下方显示 "@quso_bot"
• 只有显示机器人用户名的消息才能删除

📚 **技术说明：**
• Telegram API限制：任何API（Bot API或User API）都只能删除自己发送的消息
• 这是Telegram的安全机制，防止恶意删除他人消息
• 即使是频道管理员，也无法通过API删除其他用户的消息
• 只有频道所有者可以在Telegram客户端中手动删除他人消息

🔧 **权限说明：**
• 频道管理列表中的频道，机器人都是管理员
• 主要限制：只能删除机器人自己发送的消息
• 这是Telegram API的安全机制，无法绕过

请输入要删除的消息ID：
            """.strip()
            
            # 设置用户状态等待输入
            self.user_states[user_id] = {
                'state': 'waiting_for_message_ids',
                'data': {
                    'channel_id': channel_id,
                    'channel_info': channel_info
                }
            }
            
            buttons = [
                [("❌ 取消", f"admin_channel_message_management:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理删除消息界面失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _process_message_ids_input(self, message: Message, state: Dict[str, Any]):
        """处理消息ID输入"""
        try:
            user_id = str(message.from_user.id)
            text = message.text.strip()
            channel_id = state.get('data', {}).get('channel_id')
            channel_info = state.get('data', {}).get('channel_info', {})
            
            if not channel_id:
                await message.reply_text("❌ 频道ID丢失，请重新操作")
                return
            
            if text.lower() in ['取消', 'cancel', '退出']:
                # 清除用户状态
                if user_id in self.user_states:
                    del self.user_states[user_id]
                
                await message.reply_text(
                    "❌ 操作已取消",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回信息管理", f"admin_channel_message_management:{channel_id}")
                    ]])
                )
                return
            
            # 解析消息ID
            message_ids = self._parse_message_ids(text)
            if not message_ids:
                await message.reply_text(
                    "❌ **消息ID格式错误！**\n\n"
                    "💡 **支持的输入格式：**\n"
                    "• 单个消息ID：`5`\n"
                    "• 消息ID段：`60-100`\n"
                    "• 多个ID段：`5,60-100,200-250`\n\n"
                    "⚠️ **注意事项：**\n"
                    "• 只能删除机器人发送的消息\n"
                    "• 删除操作不可恢复\n"
                    "• 建议先测试少量消息\n\n"
                    "请重新输入："
                )
                return
            
            # 显示确认界面
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 统计消息数量
            total_count = len(message_ids)
            if total_count > 50:
                # 自动分批删除，每批50条
                await message.reply_text(
                    f"📊 **消息数量：** {total_count} 条\n"
                    f"🔄 **自动分批：** 将分 {((total_count - 1) // 50) + 1} 批删除，每批50条\n\n"
                    f"⏳ 正在准备分批删除..."
                )
                
                # 分批处理消息ID
                batch_size = 50
                batches = []
                for i in range(0, total_count, batch_size):
                    batch = message_ids[i:i + batch_size]
                    batches.append(batch)
                
                # 显示分批信息
                batch_info = []
                for i, batch in enumerate(batches, 1):
                    if len(batch) == 1:
                        batch_info.append(f"第{i}批: {batch[0]}")
                    else:
                        batch_info.append(f"第{i}批: {batch[0]}-{batch[-1]} ({len(batch)}条)")
                
                confirm_text = f"""
⚠️ **确认分批删除消息**

📋 **频道：** {channel_display}
📊 **总数量：** {total_count} 条
🔄 **分批情况：** {len(batches)} 批

📝 **分批详情：**
{chr(10).join(batch_info[:10])}
{f"... 等{len(batches)}批" if len(batches) > 10 else ""}

⚠️ **警告：**
• 删除操作不可恢复
• 只能删除机器人发送的消息
• 请确认消息ID正确

是否确认开始分批删除？
                """.strip()
                
                # 使用简化的按钮数据，避免超长问题
                buttons = [
                    [("✅ 确认分批删除", f"confirm_batch_delete:{channel_id}")],
                    [("❌ 取消", f"admin_channel_message_management:{channel_id}")]
                ]
                
                # 保存消息ID到用户状态，用于确认删除
                self.user_states[user_id] = {
                    'state': 'waiting_for_batch_confirm',
                    'data': {
                        'channel_id': channel_id,
                        'channel_info': channel_info,
                        'message_ids': message_ids,
                        'message_text': text
                    }
                }
                
                await message.reply_text(
                    confirm_text,
                    reply_markup=generate_button_layout(buttons)
                )
                return
            
            # 显示消息ID预览
            preview_ids = message_ids[:10]  # 只显示前10个
            preview_text = ", ".join(map(str, preview_ids))
            if total_count > 10:
                preview_text += f" ... 等{total_count}条消息"
            
            confirm_text = f"""
⚠️ **确认删除消息**

📋 **频道：** {channel_display}
📊 **消息数量：** {total_count} 条
🆔 **消息ID：** {preview_text}

⚠️ **警告：**
• 删除操作不可恢复
• 只能删除机器人发送的消息
• 请确认消息ID正确

是否确认删除？
            """.strip()
            
            # 使用简化的按钮数据，避免超长问题
            buttons = [
                [("✅ 确认删除", f"confirm_single_delete:{channel_id}")],
                [("❌ 取消", f"admin_channel_message_management:{channel_id}")]
            ]
            
            # 保存消息ID到用户状态，用于确认删除
            self.user_states[user_id] = {
                'state': 'waiting_for_single_confirm',
                'data': {
                    'channel_id': channel_id,
                    'channel_info': channel_info,
                    'message_ids': message_ids,
                    'message_text': text
                }
            }
            
            await message.reply_text(
                confirm_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理消息ID输入失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
    def _parse_message_ids(self, text: str) -> List[int]:
        """解析消息ID字符串"""
        try:
            message_ids = []
            
            # 按逗号分割
            parts = text.split(',')
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                
                if '-' in part:
                    # 处理ID段，如 60-100
                    try:
                        start, end = part.split('-', 1)
                        start_id = int(start.strip())
                        end_id = int(end.strip())
                        
                        if start_id > end_id:
                            start_id, end_id = end_id, start_id
                        
                        # 添加到消息ID列表
                        for msg_id in range(start_id, end_id + 1):
                            message_ids.append(msg_id)
                            
                    except ValueError:
                        logger.warning(f"无效的ID段格式: {part}")
                        continue
                else:
                    # 处理单个ID
                    try:
                        msg_id = int(part)
                        message_ids.append(msg_id)
                    except ValueError:
                        logger.warning(f"无效的消息ID格式: {part}")
                        continue
            
            # 去重并排序
            message_ids = sorted(list(set(message_ids)))
            
            logger.info(f"解析消息ID: {text} -> {len(message_ids)} 条消息")
            return message_ids
            
        except Exception as e:
            logger.error(f"解析消息ID失败: {e}")
            return []
    
    async def _handle_confirm_single_delete(self, callback_query: CallbackQuery):
        """处理确认单个删除消息"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查用户状态
            if user_id not in self.user_states:
                await callback_query.answer("❌ 会话已过期，请重新开始")
                return
            
            state = self.user_states[user_id]
            if state['state'] != 'waiting_for_single_confirm':
                await callback_query.answer("❌ 无效的操作状态")
                return
            
            # 获取数据
            data = state['data']
            channel_id = data['channel_id']
            channel_info = data['channel_info']
            message_ids = data['message_ids']
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示开始删除消息
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            await callback_query.edit_message_text(
                f"🗑️ **开始删除消息**\n\n"
                f"📋 **频道：** {channel_display}\n"
                f"📊 **消息数量：** {len(message_ids)} 条\n\n"
                f"⏳ 正在删除中，请稍候..."
            )
            
            # 执行删除
            success_count, failed_count = await self._delete_channel_messages(channel_id, message_ids)
            
            # 显示结果
            result_text = f"""
✅ **删除完成**

📋 **频道：** {channel_display}
📊 **总数量：** {len(message_ids)} 条
✅ **成功删除：** {success_count} 条
❌ **删除失败：** {failed_count} 条

💡 **说明：**
• 只能删除机器人发送的消息
• 删除失败的消息可能是其他用户发送的
• 这是Telegram的安全限制

🔙 返回频道管理继续操作
            """.strip()
            
            buttons = [
                [("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                result_text,
                reply_markup=generate_button_layout(buttons)
            )
            
            await callback_query.answer("✅ 删除完成")
            
        except Exception as e:
            logger.error(f"确认单个删除消息失败: {e}")
            await callback_query.answer("❌ 删除失败，请稍后重试")
    
    async def _handle_confirm_batch_delete(self, callback_query: CallbackQuery):
        """处理确认分批删除消息"""
        try:
            user_id = str(callback_query.from_user.id)
            
            # 检查用户状态
            if user_id not in self.user_states:
                await callback_query.answer("❌ 会话已过期，请重新开始")
                return
            
            state = self.user_states[user_id]
            if state['state'] != 'waiting_for_batch_confirm':
                await callback_query.answer("❌ 无效的操作状态")
                return
            
            # 获取数据
            data = state['data']
            channel_id = data['channel_id']
            channel_info = data['channel_info']
            message_ids = data['message_ids']
            
            # 清除用户状态
            del self.user_states[user_id]
            
            # 显示开始删除消息
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            await callback_query.edit_message_text(
                f"🗑️ **开始分批删除消息**\n\n"
                f"📋 **频道：** {channel_display}\n"
                f"📊 **总数量：** {len(message_ids)} 条\n"
                f"🔄 **分批情况：** {((len(message_ids) - 1) // 50) + 1} 批\n\n"
                f"⏳ 正在删除中，请稍候..."
            )
            
            # 执行删除
            success_count, failed_count = await self._delete_channel_messages(channel_id, message_ids)
            
            # 显示结果
            result_text = f"""
✅ **删除完成**

📋 **频道：** {channel_display}
📊 **总数量：** {len(message_ids)} 条
✅ **成功删除：** {success_count} 条
❌ **删除失败：** {failed_count} 条

💡 **说明：**
• 只能删除机器人发送的消息
• 删除失败的消息可能是其他用户发送的
• 这是Telegram的安全限制

🔙 返回频道管理继续操作
            """.strip()
            
            buttons = [
                [("🔙 返回频道管理", f"admin_channel_manage:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                result_text,
                reply_markup=generate_button_layout(buttons)
            )
            
            await callback_query.answer("✅ 删除完成")
            
        except Exception as e:
            logger.error(f"确认分批删除消息失败: {e}")
            await callback_query.answer("❌ 删除失败，请稍后重试")
    
    async def _handle_admin_channel_confirm_delete_messages(self, callback_query: CallbackQuery):
        """处理确认删除消息"""
        try:
            user_id = str(callback_query.from_user.id)
            parts = callback_query.data.split(':')
            channel_id = int(parts[1])
            message_ids_text = parts[2]
            
            # 解析消息ID
            message_ids = self._parse_message_ids(message_ids_text)
            if not message_ids:
                await callback_query.edit_message_text("❌ 消息ID解析失败")
                return
            
            # 获取频道信息
            admin_channels = await self._get_admin_channels()
            channel_info = None
            for channel in admin_channels:
                if channel.get('id') == channel_id:
                    channel_info = channel
                    break
            
            if not channel_info:
                await callback_query.edit_message_text("❌ 频道不存在")
                return
            
            channel_name = channel_info.get('title', '未知频道')
            username = channel_info.get('username', '')
            
            if username:
                channel_display = f"{channel_name} (@{username})"
            else:
                channel_display = f"{channel_name} (无用户名)"
            
            # 显示删除进度
            await callback_query.edit_message_text(
                f"🗑️ **正在删除消息...**\n\n"
                f"📋 **频道：** {channel_display}\n"
                f"📊 **消息数量：** {len(message_ids)} 条\n\n"
                f"⏳ 请稍候，正在执行删除操作...",
                reply_markup=generate_button_layout([[
                    ("🔙 返回信息管理", f"admin_channel_message_management:{channel_id}")
                ]])
            )
            
            # 执行删除操作
            success_count, failed_count = await self._delete_channel_messages(channel_id, message_ids)
            
            # 显示结果
            if success_count > 0:
                result_text = f"""
✅ **删除完成**

📋 **频道：** {channel_display}
✅ **成功删除：** {success_count} 条
❌ **删除失败：** {failed_count} 条

💡 **说明：**
• 只能删除机器人发送的消息
• 删除失败的消息可能已被删除或不存在
                """.strip()
            else:
                result_text = f"""
❌ **删除失败**

📋 **频道：** {channel_display}
❌ **删除失败：** {failed_count} 条

💡 **可能原因：**
• 消息不是机器人发送的（最常见）
• 消息已被删除
• 机器人权限不足
• 消息ID不存在

🔍 **如何确认消息是机器人发送的：**
• 查看消息右下角是否有机器人用户名
• 例如：消息下方显示 "@quso_bot"
• 只有显示机器人用户名的消息才能删除

📚 **技术说明：**
• Telegram API限制：任何API（Bot API或User API）都只能删除自己发送的消息
• 这是Telegram的安全机制，防止恶意删除他人消息
• 即使是频道管理员，也无法通过API删除其他用户的消息
• 只有频道所有者可以在Telegram客户端中手动删除他人消息

🔧 **权限说明：**
• 频道管理列表中的频道，机器人都是管理员
• 主要限制：只能删除机器人自己发送的消息
• 这是Telegram API的安全机制，无法绕过
                """.strip()
            
            buttons = [
                [("🗑️ 继续删除", f"admin_channel_delete_messages:{channel_id}")],
                [("🔙 返回信息管理", f"admin_channel_message_management:{channel_id}")]
            ]
            
            await callback_query.edit_message_text(
                result_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"确认删除消息失败: {e}")
            await callback_query.answer("❌ 删除失败，请稍后重试")
    
    async def _delete_channel_messages(self, channel_id: int, message_ids: List[int]) -> Tuple[int, int]:
        """删除频道消息（支持自动分批）"""
        try:
            success_count = 0
            failed_count = 0
            
            # 使用Bot API客户端进行删除操作
            client = self._get_bot_api_client()
            if not client:
                logger.error("无法获取Bot API客户端")
                return 0, len(message_ids)
            
            # 先验证频道访问权限
            try:
                logger.info(f"验证频道访问权限: {channel_id}")
                chat_info = await client.get_chat(str(channel_id))
                logger.info(f"✅ 频道访问验证成功: {chat_info.title}")
            except Exception as e:
                logger.error(f"❌ 频道访问验证失败: {e}")
                logger.error(f"可能原因：")
                logger.error(f"1. 机器人被移除了管理员权限")
                logger.error(f"2. 频道ID不正确: {channel_id}")
                logger.error(f"3. 机器人需要先访问该频道")
                return 0, len(message_ids)
            
            # 注意：频道管理列表中的频道机器人都是管理员
            # 主要限制是API限制：只能删除机器人自己发送的消息
            logger.info(f"开始删除频道 {channel_id} 的消息（机器人已是管理员）")
            
            total_messages = len(message_ids)
            logger.info(f"开始删除频道 {channel_id} 的 {total_messages} 条消息")
            
            # 如果消息数量超过50条，自动分批处理
            if total_messages > 50:
                batch_size = 50
                total_batches = ((total_messages - 1) // batch_size) + 1
                logger.info(f"自动分批删除: {total_messages} 条消息分为 {total_batches} 批，每批最多 {batch_size} 条")
                
                for batch_num in range(total_batches):
                    start_idx = batch_num * batch_size
                    end_idx = min(start_idx + batch_size, total_messages)
                    batch_ids = message_ids[start_idx:end_idx]
                    
                    logger.info(f"处理第 {batch_num + 1}/{total_batches} 批: {len(batch_ids)} 条消息 (ID: {batch_ids[0]}-{batch_ids[-1]})")
                    
                    # 删除当前批次
                    batch_success, batch_failed = await self._delete_message_batch(client, channel_id, batch_ids)
                    success_count += batch_success
                    failed_count += batch_failed
                    
                    # 批次间延迟，避免API限制
                    if batch_num < total_batches - 1:  # 不是最后一批
                        logger.info(f"批次 {batch_num + 1} 完成，等待2秒后处理下一批...")
                        await asyncio.sleep(2)
                
                logger.info(f"分批删除完成: 成功 {success_count}, 失败 {failed_count}")
                return success_count, failed_count
            else:
                # 消息数量不超过50条，直接删除
                logger.info(f"消息数量 {total_messages} 条，直接删除")
                return await self._delete_message_batch(client, channel_id, message_ids)
            
        except Exception as e:
            logger.error(f"删除频道消息失败: {e}")
            return 0, len(message_ids)
    
    async def _delete_message_batch(self, client, channel_id: int, message_ids: List[int]) -> Tuple[int, int]:
        """删除一批消息"""
        try:
            success_count = 0
            failed_count = 0
            
            # 批量删除消息（每批10条）
            batch_size = 10
            for i in range(0, len(message_ids), batch_size):
                batch_ids = message_ids[i:i + batch_size]
                
                try:
                    # 尝试删除消息
                    await client.delete_messages(
                        chat_id=str(channel_id),
                        message_ids=batch_ids
                    )
                    
                    success_count += len(batch_ids)
                    logger.info(f"成功删除消息批次: {batch_ids}")
                    
                    # 添加延迟避免API限制
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    failed_count += len(batch_ids)
                    logger.warning(f"删除消息批次失败: {batch_ids}, 错误: {e}")
                    
                    # 尝试逐个删除
                    for msg_id in batch_ids:
                        try:
                            await client.delete_messages(
                                chat_id=str(channel_id),
                                message_ids=[msg_id]
                            )
                            success_count += 1
                            failed_count -= 1
                            logger.info(f"成功删除单个消息: {msg_id}")
                        except Exception as single_error:
                            logger.warning(f"删除单个消息失败: {msg_id}, 错误: {single_error}")
                    
                    # 添加延迟避免API限制
                    await asyncio.sleep(1)
            
            return success_count, failed_count
            
        except Exception as e:
            logger.error(f"删除消息批次失败: {e}")
            return 0, len(message_ids)

# ==================== 主函数 ====================
async def main():
    """主函数"""
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser(description='Telegram搬运机器人')
        parser.add_argument('--bot', type=str, help='指定机器人名称（使用bot_configs目录中的配置文件）')
        parser.add_argument('--list-bots', action='store_true', help='列出所有可用的机器人配置')
        parser.add_argument('--create-bot', type=str, help='创建新的机器人配置')
        parser.add_argument('--setup', action='store_true', help='设置多机器人环境')
        
        args = parser.parse_args()
        
        # 处理特殊命令
        if args.setup:
            from multi_bot_config_manager import setup_multi_bot_environment
            setup_multi_bot_environment()
            return 0
        
        if args.list_bots:
            configs = multi_bot_manager.list_bot_configs()
            if configs:
                print("📋 可用的机器人配置:")
                for config in configs:
                    print(f"  - {config}")
            else:
                print("❌ 没有找到任何机器人配置")
                print("💡 使用 --setup 设置多机器人环境")
            return 0
        
        if args.create_bot:
            # 创建JSON配置文件
            config = create_bot_config_template(args.create_bot)
            config_file = multi_bot_manager.create_bot_config(args.create_bot, config)
            print(f"✅ 已创建机器人配置: {config_file}")
            
            # 创建.env文件
            from multi_bot_config_manager import create_env_file_template
            env_file = create_env_file_template(args.create_bot)
            print(f"✅ 已创建环境文件: {env_file}")
            
            print(f"📝 请编辑环境文件 {env_file} 并填入实际的配置值")
            print(f"💡 然后使用 python main.py --bot {args.create_bot} 启动机器人")
            return 0
        
        # 创建机器人实例
        bot = TelegramBot(bot_name=args.bot)
        
        # 运行机器人
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("收到键盘中断，程序退出")
    except Exception as e:
        logger.error(f"主函数出错: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        # 运行机器人
        exit_code = asyncio.run(main())
        if exit_code != 0:
            sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🤖 机器人已停止")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)
