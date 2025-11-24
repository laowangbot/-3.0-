# ==================== 主机器人文件 ====================
"""
主机器人文件
集成Telegram Bot API、命令处理器、回调查询处理和用户会话管理
"""

import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
import argparse
import random
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入多机器人配置管理器
# TODO: 需要实现多机器人配置管理器
# from multi_bot_config_manager import multi_bot_manager, create_bot_config_template

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError

# 导入自定义模块
from core.config_manager import get_config, validate_config, DEFAULT_USER_CONFIG
from modules.data_management.local_manager import create_local_data_manager
# TODO: 需要实现多机器人数据管理器
# from multi_bot_data_manager import create_multi_bot_data_manager
from modules.data_management.channel_manager import ChannelDataManager
from modules.utils.message_engine import create_message_engine
from modules.cloning.engine import create_cloning_engine, CloneTask
from modules.cloning.integration import CommentCloningIntegration
# TODO: 需要实现任务状态管理器
# from task_state_manager import start_task_state_manager, stop_task_state_manager
from web.server import create_web_server
from modules.user_api.manager import get_user_api_manager, UserAPIManager

# 配置日志 - 使用优化的日志配置
from core.logger import setup_bot_logging, get_logger

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
            logger.debug("🔧 使用本地存储模式")
            self.data_manager = create_local_data_manager(self.bot_id)
        else:
            logger.info("🔧 使用本地存储模式（Firebase已移除）")
            self.data_manager = create_local_data_manager(self.bot_id)
            
        # 初始化频道数据管理器（每个机器人使用独立的数据文件）
        channel_data_file = f"data/{self.bot_id}/channel_data.json"
        os.makedirs(os.path.dirname(channel_data_file), exist_ok=True)
        self.channel_data_manager = ChannelDataManager(data_file=channel_data_file)
        
        # 初始化搬运引擎（延迟初始化）
        self.cloning_engine = None
        
        # 初始化评论搬运功能（延迟初始化）
        self.comment_cloning_integration = None
        
        # 初始化监听引擎（延迟初始化）
        self.realtime_monitoring_engine = None
        
        # 监听任务持久化文件
        self.monitoring_tasks_file = f"data/{self.bot_id}/monitoring_tasks.json"
        
        # 初始化用户API管理器
        self.user_api_manager = get_user_api_manager()
        
        # 初始化Web服务器
        self.web_server = None
        self.web_runner = None
        
        # 初始化客户端
        self.client = None
        self._setup_client()
        
        # 任务管理
        self.running_tasks = set()
        self.shutdown_event = asyncio.Event()
        
        # 注册信号处理器
        self._setup_signal_handlers()
        
        logger.info(f"🤖 机器人初始化完成: {self.bot_name}")
    
    def _load_bot_specific_config(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """加载特定机器人的配置"""
        # TODO: 实现多机器人配置加载
        return get_config()
    
    def _setup_client(self):
        """设置Pyrogram客户端"""
        try:
            # 从配置中获取API凭证
            api_id = self.config.get('api_id')
            api_hash = self.config.get('api_hash')
            bot_token = self.config.get('bot_token')
            
            if not all([api_id, api_hash, bot_token]):
                raise ValueError("缺少必要的API凭证，请检查配置")
            
            # 创建客户端
            self.client = Client(
                f"bot_{self.bot_id}",
                api_id=api_id,
                api_hash=api_hash,
                bot_token=bot_token,
                workdir=f"data/{self.bot_id}"
            )
            
            # 注册处理器
            self._register_handlers()
            
            logger.info("✅ Pyrogram客户端设置完成")
            
        except Exception as e:
            logger.error(f"❌ Pyrogram客户端设置失败: {e}")
            raise
    
    def _register_handlers(self):
        """注册消息和回调处理器"""
        if not self.client:
            return
        
        # 注册命令处理器
        self.client.add_handler(filters.command("start")(self._handle_start_command))
        self.client.add_handler(filters.command("help")(self._handle_help_command))
        self.client.add_handler(filters.command("settings")(self._handle_settings_command))
        # TODO: 注册更多命令处理器
        
        # 注册回调查询处理器
        self.client.add_handler(filters.regex(r'^.*$')(self._handle_callback_query))
        
        # 注册消息处理器
        self.client.add_handler(filters.text(self._handle_text_message))
        # TODO: 注册更多消息处理器
        
        logger.debug("✅ 消息处理器注册完成")
    
    async def _handle_start_command(self, client: Client, message: Message):
        """处理 /start 命令"""
        try:
            user_id = str(message.from_user.id)
            logger.info(f"👤 用户 {user_id} 启动机器人")
            
            # 获取或创建用户配置
            user_config = await self.data_manager.get_user_config(user_id)
            
            # 发送欢迎消息
            welcome_text = (
                "🤖 欢迎使用BTbot搬运机器人！\n\n"
                "我可以帮助您在Telegram频道之间搬运内容，"
                "支持AI改写、反检测等多种功能。\n\n"
                "请使用 /help 查看帮助信息，"
                "使用 /settings 配置机器人参数。"
            )
            
            await message.reply_text(welcome_text)
            
        except Exception as e:
            logger.error(f"处理 /start 命令时出错: {e}")
            await message.reply_text("❌ 处理命令时出错，请稍后重试")
    
    async def _handle_help_command(self, client: Client, message: Message):
        """处理 /help 命令"""
        try:
            help_text = (
                "📚 BTbot 帮助文档\n\n"
                "📌 基本命令:\n"
                "/start - 启动机器人\n"
                "/help - 显示帮助信息\n"
                "/settings - 配置机器人参数\n"
                "/clone - 开始内容搬运\n"
                "/monitor - 管理监听任务\n"
                "/ai_settings - 配置AI改写参数\n\n"
                "📌 功能说明:\n"
                "• 支持频道间内容搬运\n"
                "• 支持AI智能改写\n"
                "• 支持反检测处理\n"
                "• 支持多任务并发执行\n\n"
                "如需更多帮助，请联系管理员。"
            )
            
            await message.reply_text(help_text)
            
        except Exception as e:
            logger.error(f"处理 /help 命令时出错: {e}")
            await message.reply_text("❌ 处理命令时出错，请稍后重试")
    
    async def _handle_settings_command(self, client: Client, message: Message):
        """处理 /settings 命令"""
        try:
            # TODO: 实现设置命令处理逻辑
            await message.reply_text("🔧 设置功能正在开发中...")
            
        except Exception as e:
            logger.error(f"处理 /settings 命令时出错: {e}")
            await message.reply_text("❌ 处理命令时出错，请稍后重试")
    
    async def _handle_callback_query(self, client: Client, callback_query: CallbackQuery):
        """处理回调查询"""
        try:
            # TODO: 实现回调查询处理逻辑
            await callback_query.answer("功能正在开发中...")
            
        except Exception as e:
            logger.error(f"处理回调查询时出错: {e}")
            await callback_query.answer("❌ 处理出错，请稍后重试", show_alert=True)
    
    async def _handle_text_message(self, client: Client, message: Message):
        """处理文本消息"""
        try:
            # TODO: 实现文本消息处理逻辑
            pass
            
        except Exception as e:
            logger.error(f"处理文本消息时出错: {e}")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，准备关闭机器人...")
            self.shutdown_event.set()
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _start_web_server(self):
        """启动Web服务器"""
        try:
            self.web_server = await create_web_server(self)
            self.web_runner = await self.web_server.start_server()
            logger.info("🌐 Web服务器启动完成")
        except Exception as e:
            logger.error(f"启动Web服务器失败: {e}")
    
    async def _stop_web_server(self):
        """停止Web服务器"""
        try:
            if self.web_runner:
                await self.web_runner.cleanup()
                logger.info("🌐 Web服务器已停止")
        except Exception as e:
            logger.error(f"停止Web服务器失败: {e}")
    
    async def run(self):
        """运行机器人"""
        try:
            logger.info("🚀 正在启动机器人...")
            
            # 启动Web服务器
            await self._start_web_server()
            
            # 启动Pyrogram客户端
            if self.client:
                await self.client.start()
                logger.info("✅ Pyrogram客户端启动完成")
            
            # 启动任务状态管理器
            # TODO: 实现任务状态管理器
            # await start_task_state_manager()
            
            # 主循环
            logger.info("🤖 机器人已启动，等待消息...")
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"运行机器人时出错: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止机器人"""
        logger.info("🛑 正在停止机器人...")
        
        # 停止Web服务器
        await self._stop_web_server()
        
        # 停止Pyrogram客户端
        if self.client and self.client.is_connected:
            await self.client.stop()
            logger.info("✅ Pyrogram客户端已停止")
        
        # 停止任务状态管理器
        # TODO: 实现任务状态管理器
        # await stop_task_state_manager()
        
        logger.info("👋 机器人已停止")

# ==================== 主函数 ====================
async def main():
    """主函数"""
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser(description='Telegram搬运机器人')
        parser.add_argument('--bot', type=str, help='指定机器人名称（使用bot_configs目录中的配置文件）')
        # TODO: 实现更多命令行参数
        
        args = parser.parse_args()
        
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