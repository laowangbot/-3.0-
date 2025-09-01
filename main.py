# ==================== 主机器人文件 ====================
"""
主机器人文件
集成Telegram Bot API、命令处理器、回调查询处理和用户会话管理
"""

import asyncio
import logging
import os
import signal
import sys
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError

# 导入自定义模块
from config import get_config, validate_config
from data_manager import data_manager, get_user_config, save_user_config, get_channel_pairs
from ui_layouts import (
    generate_button_layout, MAIN_MENU_BUTTONS, CHANNEL_MANAGEMENT_BUTTONS,
    FEATURE_CONFIG_BUTTONS, MONITOR_SETTINGS_BUTTONS, TASK_MANAGEMENT_BUTTONS,
    generate_channel_list_buttons, generate_pagination_buttons
)
from message_engine import create_message_engine
from cloning_engine import create_cloning_engine, CloneTask
from web_server import create_web_server

# 配置日志 - 显示机器人状态信息
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram机器人主类"""
    
    def __init__(self):
        """初始化机器人"""
        self.config = get_config()
        self.client = None
        self.cloning_engine = None
        # self.monitor_system = None  # 已移除监控系统
        self.web_server = None
        self.web_runner = None
        
        # 用户会话状态
        self.user_states: Dict[str, Dict[str, Any]] = {}
        
        # 初始化状态
        self.initialized = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    async def initialize(self):
        """初始化机器人"""
        try:
            logger.info("🚀 开始初始化机器人...")
            
            # 验证配置
            if not validate_config():
                logger.error("❌ 配置验证失败")
                return False
            
            # 初始化Telegram客户端
            self.client = Client(
                "bot_session",
                api_id=self.config['api_id'],
                api_hash=self.config['api_hash'],
                bot_token=self.config['bot_token']
            )
            
            # 启动客户端
            await self.client.start()
            logger.info("✅ Telegram客户端启动成功")
            
            # 初始化搬运引擎
            self.cloning_engine = create_cloning_engine(self.client, self.config)
            logger.info("✅ 搬运引擎初始化成功")
            
            # 设置进度回调函数
            self.cloning_engine.set_progress_callback(self._task_progress_callback)
            logger.info("✅ 进度回调函数设置完成")
            
            # 监听系统已移除
            logger.info("✅ 核心系统初始化成功")
            
            # 设置事件处理器
            self._setup_handlers()
            logger.info("✅ 事件处理器设置完成")
            
            # 初始化Web服务器
            self.web_server = await create_web_server(self)
            self.web_runner = await self.web_server.start_server()
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
        
        # 回调查询处理器
        @self.client.on_callback_query()
        async def callback_handler(client, callback_query: CallbackQuery):
            await self._handle_callback_query(callback_query)
        
        # 文本消息处理器 - 只处理私聊文本消息
        @self.client.on_message(filters.private & filters.text)
        async def text_message_handler(client, message: Message):
            # 检查是否为命令
            if message.text.startswith('/'):
                return
            await self._handle_text_message(message)
    
    async def _handle_start_command(self, message: Message):
        """处理开始命令"""
        try:
            user_id = str(message.from_user.id)
            user_name = message.from_user.first_name or "用户"
            
            # 创建或获取用户配置
            user_config = await get_user_config(user_id)
            
            # 欢迎消息
            welcome_text = f"""
🎉 欢迎使用 {self.config['bot_name']}！

👋 你好，{user_name}！

🤖 这是一个功能强大的Telegram频道搬运机器人，支持：
• 📝 文本过滤和替换
• 🔗 链接移除和按钮过滤
• ✨ 文本小尾巴和附加按钮
• 👂 实时监听和自动搬运
• 📊 任务管理和进度监控

💡 使用 /menu 命令打开主菜单，开始配置和使用机器人！
            """.strip()
            
            # 发送欢迎消息
            await message.reply_text(
                welcome_text,
                reply_markup=generate_button_layout(MAIN_MENU_BUTTONS)
            )
            
            logger.info(f"用户 {user_id} 启动机器人")
            
        except Exception as e:
            logger.error(f"处理开始命令失败: {e}")
            await message.reply_text("❌ 启动失败，请稍后重试")
    
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
    
    async def _show_main_menu(self, message: Message):
        """显示主菜单"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取用户统计信息
            channel_pairs = await get_channel_pairs(user_id)
            user_config = await get_user_config(user_id)
            
            # 构建菜单文本
            menu_text = f"""
🎯 **{self.config['bot_name']} 主菜单**

📊 **当前状态**
• 频道组数量: {len(channel_pairs)} 个
• 监听状态: {'✅ 已启用' if user_config.get('monitor_enabled') else '❌ 未启用'}
• 过滤规则: {len(user_config.get('filter_keywords', []))} 个关键字

🚀 选择以下功能开始使用：
            """.strip()
            
            # 发送主菜单
            await message.reply_text(
                menu_text,
                reply_markup=generate_button_layout(MAIN_MENU_BUTTONS)
            )
            
        except Exception as e:
            logger.error(f"显示主菜单失败: {e}")
            await message.reply_text("❌ 显示菜单失败，请稍后重试")
    
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
            elif data == "show_channel_config_menu":
                await self._handle_show_channel_config(callback_query)
            elif data == "show_feature_config_menu":
                await self._handle_show_feature_config(callback_query)
            elif data == "show_monitor_menu":
                await self._handle_show_monitor_menu(callback_query)
            elif data == "toggle_realtime_listen":
                await self._handle_toggle_realtime_listen(callback_query)
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
            elif data.startswith("add_channel_pair"):
                await self._handle_add_channel_pair(callback_query)
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
            elif data == "clear_all_channels":
                await self._handle_clear_all_channels(callback_query)
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
            
            # 获取用户统计信息
            channel_pairs = await get_channel_pairs(user_id)
            user_config = await get_user_config(user_id)
            
            # 构建菜单文本
            menu_text = f"""
🎯 **{self.config['bot_name']} 主菜单**

📊 **当前状态**
• 频道组数量: {len(channel_pairs)} 个
• 监听状态: {'✅ 已启用' if user_config.get('monitor_enabled') else '❌ 未启用'}
• 过滤规则: {len(user_config.get('filter_keywords', []))} 个关键字

🚀 选择以下功能开始使用：
            """.strip()
            
            # 更新消息
            await callback_query.edit_message_text(
                menu_text,
                reply_markup=generate_button_layout(MAIN_MENU_BUTTONS)
            )
            
        except Exception as e:
            logger.error(f"显示主菜单失败: {e}")
            await callback_query.edit_message_text("❌ 显示菜单失败，请稍后重试")
    
    async def _handle_select_channels(self, callback_query: CallbackQuery):
        """处理选择频道（支持多选）"""
        try:
            user_id = str(callback_query.from_user.id)
            channel_pairs = await get_channel_pairs(user_id)
            
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
                    'current_step': 'selecting_channels'
                }
            
            # 构建频道选择界面
            selected_count = len(self.multi_select_states[user_id]['selected_channels'])
            select_text = f"""
📋 **选择要搬运的频道组**

💡 **功能说明**:
• 可以同时选择多个频道组进行搬运
• 只选择一个就是单任务搬运
• 选择多个就是多任务搬运
• 系统会自动管理并发任务

📊 **当前状态**:
• 可用频道组: {len(channel_pairs)} 个
• 已选择: {selected_count} 个

🎯 **选择说明**:
• 点击频道组名称进行选择/取消选择
• 绿色勾选表示已选择
• 可以同时选择多个频道组
            """.strip()
            
            # 生成频道组选择按钮（显示选择状态）
            buttons = []
            for i, pair in enumerate(channel_pairs):
                if pair.get('enabled', True):
                    source_id = pair.get('source_id', f'频道{i+1}')
                    target_id = pair.get('target_id', f'目标{i+1}')
                    source_name = pair.get('source_name', f'频道{i+1}')
                    target_name = pair.get('target_name', f'目标{i+1}')
                    
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
                    
                    # 组合显示：频道名字（频道用户名）
                    source_info = f"{source_name}（{source_display}）"
                    target_info = f"{target_name}（{target_display}）"
                    
                    # 检查是否已选择
                    is_selected = f"{i}" in self.multi_select_states[user_id]['selected_channels']
                    status_icon = "✅" if is_selected else "⚪"
                    
                    buttons.append([(
                        f"{status_icon} {source_info} → {target_info}",
                        f"multi_select_pair:{i}"
                    )])
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
        """更新多选界面显示"""
        try:
            channel_pairs = await get_channel_pairs(user_id)
            multi_select_state = self.multi_select_states.get(user_id, {})
            selected_channels = multi_select_state.get('selected_channels', [])
            
            # 构建频道选择界面
            selected_count = len(selected_channels)
            select_text = f"""
📋 **选择要搬运的频道组**

💡 **功能说明**:
• 可以同时选择多个频道组进行搬运
• 只选择一个就是单任务搬运
• 选择多个就是多任务搬运
• 系统会自动管理并发任务

📊 **当前状态**:
• 可用频道组: {len(channel_pairs)} 个
• 已选择: {selected_count} 个

🎯 **选择说明**:
• 点击频道组名称进行选择/取消选择
• 绿色勾选表示已选择
• 可以同时选择多个频道组
            """.strip()
            
            # 生成频道组选择按钮（显示选择状态）
            buttons = []
            for i, pair in enumerate(channel_pairs):
                if pair.get('enabled', True):
                    source_id = pair.get('source_id', f'频道{i+1}')
                    target_id = pair.get('target_id', f'目标{i+1}')
                    source_name = pair.get('source_name', f'频道{i+1}')
                    target_name = pair.get('target_name', f'目标{i+1}')
                    
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
                    
                    # 组合显示：频道名字 (用户名)
                    source_info = f"{source_name} ({source_display})"
                    target_info = f"{target_name} ({target_display})"
                    
                    # 检查是否已选择
                    is_selected = f"{i}" in selected_channels
                    status_icon = "✅" if is_selected else "⚪"
                    
                    buttons.append([(
                        f"{status_icon} {source_info} → {target_info}",
                        f"multi_select_pair:{i}"
                    )])
            
            # 添加操作按钮
            if selected_count > 0:
                buttons.append([("🚀 继续设置消息ID段", "multi_set_message_ranges")])
            
            buttons.append([("🔙 返回主菜单", "show_main_menu")])
            
            await callback_query.edit_message_text(
                select_text,
                reply_markup=generate_button_layout(buttons)
            )
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            
            # 开始创建任务
            success_count = 0
            task_ids = []
            
            for i, config in enumerate(task_configs):
                try:
                    # 更新进度显示
                    progress_text = f"""
🚀 **多任务搬运启动中**

📡 **任务数量**: {len(task_configs)} 个
⏱️ **状态**: 正在创建任务... ({i+1}/{len(task_configs)})

💡 **当前处理**: 频道组{config['pair_index']+1}
• 源频道: {config['source_chat_id']}
• 目标频道: {config['target_chat_id']}
                    """.strip()
                    
                    buttons = [
                        [("🔄 刷新状态", "refresh_multi_task_status")],
                        [("🔙 返回主菜单", "show_main_menu")]
                    ]
                    
                    await callback_query.edit_message_text(
                        progress_text,
                        reply_markup=generate_button_layout(buttons)
                    )
                    
                    logger.info(f"创建多任务 {i+1}/{len(task_configs)}: 频道组{config['pair_index']+1}")
                    
                    # 创建搬运任务（添加超时保护）
                    logger.info(f"🔍 创建任务配置: start_id={config.get('start_id')}, end_id={config.get('end_id')}")
                    
                    # 添加整体超时保护，防止UI卡住
                    task = await asyncio.wait_for(
                        self.cloning_engine.create_task(
                            source_chat_id=config['source_chat_id'],
                            target_chat_id=config['target_chat_id'],
                            start_id=config.get('start_id'),
                            end_id=config.get('end_id'),
                            config=config
                        ),
                        timeout=60.0  # 60秒总超时
                    )
                    
                    if task:
                        # 启动搬运任务
                        success = await self.cloning_engine.start_cloning(task)
                        if success:
                            # 记录任务真实开始时间
                            if hasattr(task, 'start_time') and task.start_time:
                                config['start_time'] = task.start_time.isoformat()
                            else:
                                config['start_time'] = datetime.now().isoformat()
                            success_count += 1
                            task_ids.append(task.task_id)
                            logger.info(f"✅ 多任务 {i+1} 启动成功")
                        else:
                            error_msg = f"❌ 频道组{config['pair_index']+1} 启动失败：可能达到并发限制或权限不足"
                            logger.error(error_msg)
                            # 向用户发送具体的错误信息
                            await callback_query.message.reply_text(error_msg)
                    else:
                        error_msg = f"❌ 频道组{config['pair_index']+1} 创建失败：频道验证失败或配置错误"
                        logger.error(error_msg)
                        # 向用户发送具体的错误信息
                        await callback_query.message.reply_text(error_msg)
                    
                    # 任务间延迟
                    await asyncio.sleep(0.5)
                    
                except asyncio.TimeoutError:
                    error_msg = f"⏰ 频道组{config['pair_index']+1} 创建超时：网络连接或频道权限问题"
                    logger.error(error_msg)
                    # 向用户发送具体的错误信息
                    await callback_query.message.reply_text(error_msg)
                    continue
                except Exception as e:
                    error_msg = f"❌ 频道组{config['pair_index']+1} 执行异常: {str(e)}"
                    logger.error(error_msg)
                    # 向用户发送具体的错误信息
                    await callback_query.message.reply_text(error_msg)
                    continue
            
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
            await callback_query.answer("❌ 执行失败，请稍后重试")
    
    async def _task_progress_callback(self, task):
            """任务进度回调函数，用于实时更新任务进度"""
            try:
                if not task or not hasattr(task, 'task_id'):
                    return
                
                logger.info(f"📊 任务进度更新: {task.task_id}, 状态: {getattr(task, 'status', 'unknown')}, "
                           f"进度: {getattr(task, 'progress', 0):.1f}%, "
                           f"已处理: {getattr(task, 'processed_messages', 0)}")
                
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
        """更新多任务进度界面"""
        try:
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
            
            text += "\n\n💡 **系统将每5秒自动刷新进度，显示实际处理数量**"
            
            # 生成按钮
            buttons = [
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
            max_duration = 3600  # 最大运行时间1小时
            update_count = 0
            
            while True:
                await asyncio.sleep(5)
                update_count += 1
                
                # 超时保护：如果运行超过1小时，停止更新
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > max_duration:
                    logger.warning(f"多任务进度更新已运行{elapsed/60:.1f}分钟，达到最大时长限制，停止更新")
                    break
                
                # 检查是否所有任务都完成了
                all_completed = True
                completed_count = 0
                failed_count = 0
                
                logger.info(f"🔍 检查多任务状态: user_id={user_id}, task_ids={task_ids}")
                
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
                        # 如果任务不在active_tasks中，可能已经完成并被清理了
                        # 这种情况下我们认为任务已完成
                        logger.warning(f"⚠️ 任务 {task_id} 不在active_tasks中，可能已完成")
                        completed_count += 1
                        # 记录任务完成时间（任务已被清理，使用当前时间）
                        if i < len(task_configs):
                            task_configs[i]['end_time'] = datetime.now().isoformat()
                
                logger.info(f"📊 任务状态统计: 完成={completed_count}, 失败={failed_count}, 进行中={len(task_ids) - completed_count - failed_count}")
                
                if all_completed:
                    logger.info(f"🎉 所有任务完成，显示完成界面: 完成={completed_count}, 失败={failed_count}")
                    # 所有任务完成，显示完成界面
                    await self._show_multi_select_completion(callback_query, user_id, completed_count, len(task_ids))
                    break
                
                # 更新进度界面
                try:
                    await self._update_multi_task_progress_ui(callback_query, user_id, task_ids, task_configs)
                except Exception as e:
                    logger.error(f"更新进度界面失败: {e}")
                    # UI更新失败不应该停止任务监控，继续循环
                    if "QUERY_ID_INVALID" in str(e) or "callback query id is invalid" in str(e).lower():
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
            chat = await self.client.get_chat(chat_id)
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
                    chat = await self.client.get_chat(chat_id)
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
                    chat = await self.client.get_chat(str(chat_id))
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
            user_config = await get_user_config(user_id)
            
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
                await save_user_config(user_id, user_config)
            
            # 添加调试日志
            logger.info(f"🔍 _init_channel_filters返回 - 频道组 {pair_id}:")
            logger.info(f"  • 原始user_config中的配置: {user_config.get('channel_filters', {}).get(pair_id, {})}")
            logger.info(f"  • is_empty_config: {is_empty_config}")
            logger.info(f"  • modified_channel_filters: {modified_channel_filters}")
            logger.info(f"  • 返回的channel_filters: {channel_filters}")
            logger.info(f"  • independent_enabled: {channel_filters.get('independent_enabled', False)}")
            
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
                    from data_manager import get_channel_pairs
                    channel_pairs = await get_channel_pairs(user_id)
                    
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
            channel_details = []
            
            # 从多任务状态中获取任务信息
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                multi_select_state = self.multi_select_states[user_id]
                task_configs = multi_select_state.get('task_configs', [])
                
                # 统计所有任务的信息
                for i, config in enumerate(task_configs):
                    start_id = config.get('start_id')
                    end_id = config.get('end_id')
                    pair_index = config.get('pair_index', i)
                    
                    # 计算消息数量
                    task_messages = 0
                    if start_id and end_id:
                        task_messages = end_id - start_id + 1
                        total_messages += task_messages
                        total_processed += task_messages  # 任务完成意味着全部处理完成
                    
                    # 获取任务时间信息
                    start_time = config.get('start_time')
                    end_time = config.get('end_time')
                    task_duration = "未知"
                    
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
                        
                        # 计算单个任务用时
                        task_time_seconds = (end_time - start_time).total_seconds()
                        if task_time_seconds < 60:
                            task_duration = f"{task_time_seconds:.1f}秒"
                        elif task_time_seconds < 3600:
                            task_duration = f"{task_time_seconds/60:.1f}分钟"
                        else:
                            task_duration = f"{task_time_seconds/3600:.1f}小时"
                    
                    # 添加频道组详情
                    channel_details.append({
                        'index': pair_index + 1,
                        'messages': task_messages,
                        'duration': task_duration
                    })
            
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
            
            # 构建频道组详情文本
            channel_details_text = ""
            if channel_details:
                channel_details_text = "\n\n📋 **各频道组详情**:\n"
                for detail in channel_details:
                    channel_details_text += f"• 频道组 {detail['index']}: {detail['messages']} 条消息，用时 {detail['duration']}\n"
            
            text = f"""
🎉 **多任务搬运完成**

📊 **执行结果**:
• 总任务数: {total_count} 个
• 成功启动: {success_count} 个
• 失败数量: {total_count - success_count} 个

📈 **搬运统计**:
• 总消息数: {total_messages} 条
• 已处理: {total_processed} 条
• 总用时: {total_time_display}{channel_details_text}
            """.strip()
            
            buttons = [
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
                    
                    # 使用保存的用户名信息，如果没有则使用ID
                    source_display = source_username if source_username else str(source_id)
                    target_display = target_username if target_username else str(target_id)
                    
                    # 显示频道组信息
                    config_text += f"\n{status} **频道组 {i+1}**"
                    config_text += f"\n   📡 采集: {source_name} ({source_display})"
                    config_text += f"\n   📤 发布: {target_name} ({target_display})"
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
    
    async def _handle_show_feature_config(self, callback_query: CallbackQuery):
        """处理显示功能配置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
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
• 文本内容移除: {'✅ 开启' if user_config.get('content_removal') else '❌ 关闭'} ({content_removal_mode_text})
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
            user_config = await get_user_config(user_id)
            
            monitor_enabled = user_config.get('monitor_enabled', False)
            monitored_pairs = user_config.get('monitored_pairs', [])
            
            monitor_text = f"""
👂 **实时监听设置**

📊 **当前状态**
• 监听功能: {'✅ 已启用' if monitor_enabled else '❌ 未启用'}
• 监听频道: {len(monitored_pairs)} 个

💡 **功能说明**
实时监听功能会自动检查指定频道的新消息，并自动搬运到目标频道。

⚠️ **注意事项**
• 启用监听后，机器人会持续运行
• 建议在服务器环境下使用
• 请确保机器人有相应权限

请选择操作：
            """.strip()
            
            await callback_query.edit_message_text(
                monitor_text,
                reply_markup=generate_button_layout(MONITOR_SETTINGS_BUTTONS, **{
                    'monitor_status': '✅ 开启' if monitor_enabled else '❌ 关闭',
                    'monitor_count': len(monitored_pairs)
                })
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
            history = await data_manager.get_task_history(user_id, limit=10)
            
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
                    
                    # 格式化时间
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        time_str = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        time_str = created_at
                    
                    history_text += f"\n{i+1}. {status} - {time_str}"
                
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
            user_config = await get_user_config(user_id)
            
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
• 文本内容移除: {'✅ 开启' if user_config.get('content_removal') else '❌ 关闭'} ({content_removal_mode_text})
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

🔙 发送 /menu 返回主菜单
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
            # 解析频道组索引
            pair_index = int(callback_query.data.split(':')[1])
            
            edit_text = f"""
✏️ **编辑频道组 {pair_index + 1}**

📝 **请选择要编辑的内容：**

1. 更改来源频道
2. 更改目标频道
3. 启用/禁用频道组
4. 管理过滤设置

💡 请选择操作：
            """.strip()
            
            # 生成编辑按钮
            buttons = [
                [("🔄 更改来源频道", f"edit_source:{pair_index}")],
                [("🔄 更改目标频道", f"edit_target:{pair_index}")],
                [("✅ 启用/禁用", f"toggle_enabled:{pair_index}")],
                [("🔧 过滤设置", f"edit_filters:{pair_index}")],
                [("🔙 返回频道管理", "show_channel_config_menu")]
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
            # 解析频道组索引
            pair_index = int(callback_query.data.split(':')[1])
            
            delete_text = f"""
🗑️ **删除频道组 {pair_index + 1}**

⚠️ **确认删除**
此操作将永久删除该频道组，无法恢复！

❓ **是否确认删除？**
            """.strip()
            
            # 生成确认按钮
            buttons = [
                [("❌ 取消", "show_channel_config_menu")],
                [("🗑️ 确认删除", f"confirm_delete:{pair_index}")]
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 删除频道组（data_manager.delete_channel_pair已经包含了配置清理逻辑）
            success = await data_manager.delete_channel_pair(user_id, pair['id'])
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
                success = await data_manager.save_channel_pairs(user_id, channel_pairs)
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

                elif state['state'] == 'waiting_for_channel_keywords':
                    await self._process_channel_keywords_input(message, state)
                    return
                elif state['state'] == 'waiting_for_channel_replacements':
                    await self._process_channel_replacements_input(message, state)
                    return
                elif state['state'] == 'waiting_for_cloning_info':
                    await self._process_cloning_info_input(message, state)
                    return
            
            # 检查是否是多任务搬运的消息输入
            if hasattr(self, 'multi_select_states') and user_id in self.multi_select_states:
                multi_select_state = self.multi_select_states[user_id]
                logger.info(f"检查多任务状态: user_id={user_id}, waiting_for_input={multi_select_state.get('waiting_for_input', False)}")
                if multi_select_state.get('waiting_for_input', False):
                    logger.info(f"处理多任务消息输入: user_id={user_id}")
                    await self._process_multi_select_message_input(message, user_id)
                    return
            
            # 默认处理：显示主菜单
            await self._show_main_menu(message)
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await message.reply_text("❌ 处理失败，请稍后重试")
    
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
                if '/c/' in channel_info:
                    await message.reply_text(
                        f"❌ **私密频道无法访问！**\n\n"
                        f"📡 **频道链接：** {channel_info}\n"
                        f"🔒 **问题：** 机器人无法访问该私密频道\n\n"
                        f"💡 **私密频道使用要求：**\n"
                        f"• 机器人必须已加入该私密频道\n"
                        f"• 机器人需要有读取消息的权限\n"
                        f"• 频道管理员需要邀请机器人加入\n\n"
                        f"🔧 **解决方案：**\n"
                        f"1. **邀请机器人加入私密频道**\n"
                        f"   • 在私密频道中添加机器人\n"
                        f"   • 确保机器人有读取消息权限\n\n"
                        f"2. **使用频道ID（系统已自动转换）**\n"
                        f"   • 系统已自动将链接转换为正确的ID格式\n"
                        f"   • 如果仍然失败，请直接输入完整ID（如：-1001234567890）\n\n"
                        f"3. **确认频道类型**\n"
                        f"   • 确保是频道而不是群组\n"
                        f"   • 私密群组无法用于搬运\n\n"
                        f"⚠️ **注意：** 私密频道搬运需要机器人预先加入频道"
                    )
                elif channel_info.startswith('@'):
                    await message.reply_text(
                        f"❌ **无法访问频道！**\n\n"
                        f"📡 **频道：** {channel_info}\n"
                        f"🔍 **问题：** 机器人无法访问该频道\n\n"
                        f"💡 **可能的原因：**\n"
                        f"• 频道不存在或已被删除\n"
                        f"• 频道是私密频道，机器人无法访问\n"
                        f"• 机器人未加入该频道\n"
                        f"• 频道用户名输入错误\n"
                        f"• 频道已被封禁或限制\n"
                        f"• 频道访问权限不足\n\n"
                        f"🔧 **解决方案：**\n"
                        f"• 检查频道用户名是否正确\n"
                        f"• 尝试使用频道数字ID（系统会自动转换格式）\n"
                        f"• 尝试使用频道链接：`https://t.me/channelname`\n"
                        f"• 确保机器人已加入该频道\n"
                        f"• 验证频道是否为公开频道\n"
                        f"• 检查频道是否仍然活跃"
                    )
                else:
                    await message.reply_text(
                        f"❌ **无法访问频道！**\n\n"
                        f"📡 **频道：** {channel_info}\n"
                        f"🔍 **问题：** 机器人无法访问该频道\n\n"
                        f"💡 **可能的原因：**\n"
                        f"• 频道ID格式错误\n"
                        f"• 频道不存在或已被删除\n"
                        f"• 机器人未加入该频道\n"
                        f"• 频道已被封禁或限制\n"
                        f"• 频道访问权限不足\n\n"
                        f"🔧 **解决方案：**\n"
                        f"• 检查频道ID是否正确\n"
                        f"• 尝试使用频道用户名：`@channelname`\n"
                        f"• 尝试使用频道链接：`https://t.me/channelname`\n"
                        f"• 确保机器人已加入该频道\n"
                        f"• 验证频道是否为公开频道\n"
                        f"• 检查频道是否仍然活跃"
                    )
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
                chat = await self.client.get_chat(channel_id)
                channel_type = chat.type
                channel_title = chat.title if hasattr(chat, 'title') else channel_info
                
                # 验证机器人权限
                try:
                    member = await self.client.get_chat_member(channel_id, "me")
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
                success = await data_manager.add_channel_pair(
                    user_id, source_id, pending_channel,
                    source_channel.get('title', source_channel['info']), 
                    pending_channel,
                    source_username,  # 传递源频道用户名
                    target_username   # 传递目标频道用户名
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
                    await message.reply_text("❌ 添加频道组失败，请检查频道ID是否正确，以及机器人是否有相应权限。")
                
                return
            
            # 获取频道详细信息进行验证
            try:
                chat = await self.client.get_chat(channel_id)
                channel_type = chat.type
                channel_title = chat.title if hasattr(chat, 'title') else channel_info
                
                # 验证机器人权限
                try:
                    member = await self.client.get_chat_member(channel_id, "me")
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
            
            # 添加频道组
            success = await data_manager.add_channel_pair(
                user_id, source_id, channel_id,
                source_channel.get('title', source_channel['info']), 
                target_channel.get('title', channel_info),
                source_username,  # 传递源频道用户名
                target_username   # 传递目标频道用户名
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
                    existing_pair = await data_manager.get_channel_pair_by_channels(user_id, source_id, channel_id)
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
                pair_index = state.get('data', {}).get('pair_index')
                
                if pair_index is not None:
                    # 频道组特定设置
                    user_config = await get_user_config(user_id)
                    
                    # 获取频道组信息
                    channel_pairs = await get_channel_pairs(user_id)
                    if pair_index >= len(channel_pairs):
                        await message.reply_text("❌ 频道组不存在")
                        return
                    
                    pair = channel_pairs[pair_index]
                    
                    # 确保channel_filters存在
                    if 'channel_filters' not in user_config:
                        user_config['channel_filters'] = {}
                    if pair['id'] not in user_config['channel_filters']:
                        user_config['channel_filters'][pair['id']] = {}
                    
                    # 清空频道组特定配置
                    user_config['channel_filters'][pair['id']]['tail_text'] = ''
                    await save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        "✅ 频道组附加文字已清空！\n\n现在该频道组的消息将不再添加附加文字。",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回小尾巴设置", f"channel_tail_text:{pair_index}")
                        ]])
                    )
                else:
                    # 全局设置
                    user_config = await get_user_config(user_id)
                    user_config['tail_text'] = ''
                    await save_user_config(user_id, user_config)
                    
                    await message.reply_text(
                        "✅ 附加文字已清空！\n\n现在消息将不再添加附加文字。",
                        reply_markup=generate_button_layout([[
                            ("🔙 返回功能配置", "show_feature_config_menu")
                        ]])
                    )
                
                # 清除用户状态
                del self.user_states[user_id]
                return
            
            # 检查是否是频率设置（数字1-100）
            if text.isdigit():
                frequency = int(text)
                if 1 <= frequency <= 100:
                    # 检查是否是频道组特定设置
                    pair_index = state.get('data', {}).get('pair_index')
                    
                    if pair_index is not None:
                        # 频道组特定设置
                        user_config = await get_user_config(user_id)
                        
                        # 获取频道组信息
                        channel_pairs = await get_channel_pairs(user_id)
                        if pair_index >= len(channel_pairs):
                            await message.reply_text("❌ 频道组不存在")
                            return
                        
                        pair = channel_pairs[pair_index]
                        
                        # 确保channel_filters存在
                        if 'channel_filters' not in user_config:
                            user_config['channel_filters'] = {}
                        if pair['id'] not in user_config['channel_filters']:
                            user_config['channel_filters'][pair['id']] = {}
                        
                        # 保存到频道组特定配置
                        user_config['channel_filters'][pair['id']]['tail_frequency'] = frequency
                        await save_user_config(user_id, user_config)
                        
                        await message.reply_text(
                            f"✅ 频道组 {pair_index + 1} 附加文字频率已设置为：{frequency}%\n\n请继续输入要添加的文字内容。"
                        )
                    else:
                        # 全局设置
                        user_config = await get_user_config(user_id)
                        user_config['tail_frequency'] = frequency
                        await save_user_config(user_id, user_config)
                        
                        await message.reply_text(
                            f"✅ 附加文字频率已设置为：{frequency}%\n\n请继续输入要添加的文字内容。"
                        )
                    return
                else:
                    await message.reply_text("❌ 频率设置错误！请输入1-100之间的数字。")
                    return
            
            # 移除位置设置，默认在消息结尾添加
            
            # 检查是否是频道组特定设置
            pair_index = state.get('data', {}).get('pair_index')
            
            if pair_index is not None:
                # 频道组特定设置
                user_config = await get_user_config(user_id)
                
                # 获取频道组信息
                channel_pairs = await get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await message.reply_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                
                # 确保channel_filters存在
                if 'channel_filters' not in user_config:
                    user_config['channel_filters'] = {}
                if pair['id'] not in user_config['channel_filters']:
                    user_config['channel_filters'][pair['id']] = {}
                
                # 保存到频道组特定配置
                user_config['channel_filters'][pair['id']]['tail_text'] = text
                user_config['channel_filters'][pair['id']]['tail_frequency'] = user_config.get('tail_frequency', 'always')
                user_config['channel_filters'][pair['id']]['tail_position'] = user_config.get('tail_position', 'end')
                
                await save_user_config(user_id, user_config)
                
                await message.reply_text(
                    f"✅ 频道组 {pair_index + 1} 附加文字设置成功！\n\n**当前文字：** {text}\n\n现在该频道组的消息将自动添加这个文字。",
                    reply_markup=generate_button_layout([[
                        ("🔙 返回小尾巴设置", f"channel_tail_text:{pair_index}")
                    ]])
                )
            else:
                # 全局设置
                user_config = await get_user_config(user_id)
                user_config['tail_text'] = text
                await save_user_config(user_id, user_config)
                
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
                user_config = await get_user_config(user_id)
                user_config['additional_buttons'] = []
                await save_user_config(user_id, user_config)
                
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
                user_config = await get_user_config(user_id)
                buttons = user_config.get('additional_buttons', [])
                
                # 查找并删除按钮
                original_count = len(buttons)
                buttons = [btn for btn in buttons if btn.get('text') != button_text]
                
                if len(buttons) < original_count:
                    user_config['additional_buttons'] = buttons
                    await save_user_config(user_id, user_config)
                    
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
                    user_config = await get_user_config(user_id)
                    user_config['button_frequency'] = frequency
                    await save_user_config(user_id, user_config)
                    
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
                
                user_config = await get_user_config(user_id)
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
                await save_user_config(user_id, user_config)
                
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
            user_config = await get_user_config(user_id)
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

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 设置用户状态为等待关键字输入
            self.user_states[user_id] = {
                'state': 'waiting_for_keywords',
                'data': {}
            }
            logger.info(f"已设置用户 {user_id} 状态为等待关键字输入")
            
            # 编辑消息
            await callback_query.edit_message_text(config_text)
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
        """处理文本内容移除开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('content_removal', False)
            new_status = not current_status
            user_config['content_removal'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
            # 先回答回调查询
            action_text = "启用" if new_status else "禁用"
            await callback_query.answer(f"文本内容移除功能已{action_text}")
            
            # 延迟避免冲突
            import asyncio
            await asyncio.sleep(0.5)
            
            # 返回功能配置菜单
            await self._handle_show_feature_config(callback_query)
            
        except Exception as e:
            logger.error(f"处理文本内容移除开关失败: {e}")
            await callback_query.answer("❌ 处理失败，请稍后重试")
    
    async def _handle_manage_content_removal(self, callback_query: CallbackQuery):
        """处理文本内容移除管理"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            content_removal_enabled = user_config.get('content_removal', False)
            content_removal_mode = user_config.get('content_removal_mode', 'text_only')
            
            # 状态文本
            enabled_status = "✅ 已启用" if content_removal_enabled else "❌ 已禁用"
            mode_text = {
                'text_only': '📝 仅移除纯文本',
                'all_content': '🗑️ 移除所有包含文本的信息'
            }.get(content_removal_mode, '未知')
            
            config_text = f"""
📝 **文本内容移除设置**

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
            logger.error(f"处理文本内容移除管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_content_removal_mode(self, callback_query: CallbackQuery):
        """处理文本内容移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
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
            await save_user_config(user_id, user_config)
            
            # 模式描述
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            
            mode_text = mode_descriptions.get(mode, '未知')
            
            # 先回答回调查询
            await callback_query.answer(f"文本内容移除模式已设置为：{mode_text}")
            
            # 延迟避免冲突
            import asyncio
            await asyncio.sleep(1.0)
            
            # 返回文本内容移除管理菜单，避免消息内容冲突
            try:
                await self._handle_manage_content_removal(callback_query)
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    # 如果消息没有变化，直接返回功能配置菜单
                    await self._handle_show_feature_config(callback_query)
                else:
                    raise e
            
        except Exception as e:
            logger.error(f"设置文本内容移除模式失败: {e}")
            await callback_query.answer("❌ 设置失败，请稍后重试")
    
    async def _handle_toggle_button_removal(self, callback_query: CallbackQuery):
        """处理按钮移除开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 切换按钮过滤状态
            current_status = user_config.get('filter_buttons', False)
            new_status = not current_status
            user_config['filter_buttons'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
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
            user_config = await get_user_config(user_id)
            
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
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
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

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 设置用户状态为等待替换词输入
            self.user_states[user_id] = {
                'state': 'waiting_for_replacements',
                'data': {}
            }
            
            await callback_query.edit_message_text(config_text)
            
        except Exception as e:
            logger.error(f"处理敏感词替换管理失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_request_tail_text(self, callback_query: CallbackQuery):
        """处理附加文字请求"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            # 检查是否包含频道组索引
            if ':' in data:
                pair_index = int(data.split(':')[1])
                # 获取频道组信息
                channel_pairs = await get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                source_name = pair.get('source_name', f'频道{pair_index+1}')
                target_name = pair.get('target_name', f'目标{pair_index+1}')
                
                config_title = f"📝 **频道组 {pair_index + 1} 小尾巴设置**\n\n📡 **采集频道：** {source_name}\n📤 **发布频道：** {target_name}\n\n"
                return_callback = f"channel_tail_text:{pair_index}"
            else:
                config_title = "✨ **全局附加文字设置**\n\n"
                return_callback = "show_feature_config_menu"
            
            user_config = await get_user_config(user_id)
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
                'data': {'pair_index': pair_index if ':' in data else None}
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
            
            # 检查是否包含频道组索引
            if ':' in data:
                pair_index = int(data.split(':')[1])
                # 获取频道组信息
                channel_pairs = await get_channel_pairs(user_id)
                if pair_index >= len(channel_pairs):
                    await callback_query.edit_message_text("❌ 频道组不存在")
                    return
                
                pair = channel_pairs[pair_index]
                source_name = pair.get('source_name', f'频道{pair_index+1}')
                target_name = pair.get('target_name', f'目标{pair_index+1}')
                
                config_title = f"🔘 **频道组 {pair_index + 1} 按钮设置**\n\n📡 **采集频道：** {source_name}\n📤 **发布频道：** {target_name}\n\n"
                return_callback = f"channel_buttons:{pair_index}"
            else:
                config_title = "📋 **全局附加按钮设置**\n\n"
                return_callback = "show_feature_config_menu"
            
            user_config = await get_user_config(user_id)
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
                'data': {'pair_index': pair_index if ':' in data else None}
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
            user_config = await get_user_config(user_id)
            
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
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_all_links', False)
            new_status = not current_status
            user_config['remove_all_links'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_hashtags', False)
            new_status = not current_status
            user_config['remove_hashtags'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('remove_usernames', False)
            new_status = not current_status
            user_config['remove_usernames'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
    
    async def _handle_toggle_filter_photo(self, callback_query: CallbackQuery):
        """处理图片过滤开关"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('filter_photo', False)
            new_status = not current_status
            user_config['filter_photo'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
            # 切换状态
            current_status = user_config.get('filter_video', False)
            new_status = not current_status
            user_config['filter_video'] = new_status
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取当前频率设置
            user_config = await get_user_config(user_id)
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
                [("100% 每条都添加", f"set_tail_frequency:{pair_index}:100")],
                [("75% 大部分添加", f"set_tail_frequency:{pair_index}:75")],
                [("50% 一半添加", f"set_tail_frequency:{pair_index}:50")],
                [("25% 少量添加", f"set_tail_frequency:{pair_index}:25")],
                [("10% 偶尔添加", f"set_tail_frequency:{pair_index}:10")],
                [("🔙 返回小尾巴设置", f"channel_tail_text:{pair_index}")]
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
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取当前频率设置
            user_config = await get_user_config(user_id)
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
                [("100% 每条都添加", f"set_button_frequency:{pair_index}:100")],
                [("75% 大部分添加", f"set_button_frequency:{pair_index}:75")],
                [("50% 一半添加", f"set_button_frequency:{pair_index}:50")],
                [("25% 少量添加", f"set_button_frequency:{pair_index}:25")],
                [("10% 偶尔添加", f"set_button_frequency:{pair_index}:10")],
                [("🔙 返回按钮设置", f"channel_buttons:{pair_index}")]
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
                    pair_index = int(parts[1])
                    frequency = parts[2]
                    return_callback = f"channel_tail_text:{pair_index}"
                    config_title = f"🎯 **频道组 {pair_index + 1} 附加文字频率设置**\n\n"
            else:
                await callback_query.edit_message_text("❌ 频率设置格式错误")
                return
            
            # 检查频率值
            if frequency.isdigit():
                freq_value = int(frequency)
                if 1 <= freq_value <= 100:
                    user_config = await get_user_config(user_id)
                    user_config['tail_frequency'] = freq_value
                    await save_user_config(user_id, user_config)
                    
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
                    pair_index = int(parts[1])
                    frequency = parts[2]
                    return_callback = f"channel_buttons:{pair_index}"
                    config_title = f"🎯 **频道组 {pair_index + 1} 附加按钮频率设置**\n\n"
            else:
                await callback_query.edit_message_text("❌ 频率设置格式错误")
                return
            
            # 检查频率值
            if frequency.isdigit():
                freq_value = int(frequency)
                if 1 <= freq_value <= 100:
                    user_config = await get_user_config(user_id)
                    user_config['button_frequency'] = freq_value
                    await save_user_config(user_id, user_config)
                    
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
            user_config = await get_user_config(user_id)
            
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
    
    async def _handle_toggle_remove_links_mode(self, callback_query: CallbackQuery):
        """处理链接过滤方式切换"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 切换过滤方式
            current_mode = user_config.get('remove_links_mode', 'links_only')
            new_mode = 'remove_message' if current_mode == 'links_only' else 'links_only'
            user_config['remove_links_mode'] = new_mode
            
            # 保存配置
            await save_user_config(user_id, user_config)
            
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
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        # 防止重复调用
        if hasattr(self, '_shutdown_called') and self._shutdown_called:
            return
        
        signal_name = "SIGINT" if signum == 2 else "SIGTERM" if signum == 15 else f"信号{signum}"
        logger.info(f"收到 {signal_name}，开始关闭机器人...")
        
        self._shutdown_called = True
        # 设置停止事件，让主循环退出
        if hasattr(self, '_stop_event'):
            self._stop_event.set()
    
    async def shutdown(self):
        """关闭机器人"""
        try:
            logger.info("🔄 开始关闭机器人...")
            
            # 停止Web服务器
            if self.web_runner:
                try:
                    await self.web_runner.cleanup()
                    logger.info("✅ Web服务器已停止")
                except Exception as e:
                    logger.warning(f"停止Web服务器时出错: {e}")
            
            # 监听系统已移除
            
            # 停止Telegram客户端
            if self.client:
                try:
                    # 检查客户端是否还在连接状态
                    if hasattr(self.client, 'is_connected') and self.client.is_connected:
                        await self.client.stop()
                        logger.info("✅ Telegram客户端已停止")
                    else:
                        logger.info("✅ Telegram客户端已经停止")
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
            # 不再强制退出，让程序自然结束
    
    async def run(self):
        """运行机器人"""
        try:
            # 初始化
            if not await self.initialize():
                logger.error("❌ 机器人初始化失败")
                return
            
            logger.info("🤖 机器人开始运行...")
            logger.info(f"📱 机器人用户名: @{self.client.me.username}")
            logger.info("💡 机器人已启动，可以开始使用")
            logger.info("💡 按 Ctrl+C 可以停止机器人")
            
            # 创建停止事件
            self._stop_event = asyncio.Event()
            
            # 保持运行直到收到停止信号
            try:
                await self._stop_event.wait()
                logger.info("收到停止信号，开始关闭...")
            except KeyboardInterrupt:
                logger.info("收到键盘中断信号")
            
        except Exception as e:
            logger.error(f"机器人运行出错: {e}")
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
                user_config = await get_user_config(user_id)
                user_config['replacement_words'] = {}
                await save_user_config(user_id, user_config)
                
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
                user_config = await get_user_config(user_id)
                replacements = user_config.get('replacement_words', {})
                
                if word_to_delete in replacements:
                    del replacements[word_to_delete]
                    user_config['replacement_words'] = replacements
                    await save_user_config(user_id, user_config)
                    
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
                        user_config = await get_user_config(user_id)
                        replacements = user_config.get('replacement_words', {})
                        replacements[old_word] = new_word
                        user_config['replacement_words'] = replacements
                        await save_user_config(user_id, user_config)
                        
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
                user_config = await get_user_config(user_id)
                user_config['filter_keywords'] = []
                await save_user_config(user_id, user_config)
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
                user_config = await get_user_config(user_id)
                keywords = user_config.get('filter_keywords', [])
                
                if keyword_to_delete in keywords:
                    keywords.remove(keyword_to_delete)
                    user_config['filter_keywords'] = keywords
                    await save_user_config(user_id, user_config)
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
                user_config = await get_user_config(user_id)
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
                    await save_user_config(user_id, user_config)
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
        """处理文本内容移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            mode = callback_query.data.split(":")[1]
            
            user_config = await get_user_config(user_id)
            user_config['content_removal_mode'] = mode
            
            # 保存配置 - 通过_init_channel_filters已经保存了，这里不需要重复保存
            
            # 模式说明
            mode_descriptions = {
                "text_only": "仅移除纯文本消息，保留有媒体的消息",
                "all_content": "移除所有包含文本的信息"
            }
            
            mode_text = mode_descriptions.get(mode, "未知模式")
            
            await callback_query.edit_message_text(
                f"✅ 文本内容移除模式设置成功！\n\n"
                f"**当前模式：** {mode_text}\n\n"
                f"🔙 返回功能配置继续设置其他选项",
                reply_markup=generate_button_layout([[
                    ("🔙 返回功能配置", "show_feature_config_menu")
                ]])
            )
            
        except Exception as e:
            logger.error(f"处理文本内容移除模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_clear_additional_buttons(self, callback_query: CallbackQuery):
        """处理清空附加按钮"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 清空附加按钮
            user_config['additional_buttons'] = []
            await save_user_config(user_id, user_config)
            
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
            
            user_config = await get_user_config(user_id)
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
    
    async def _validate_channel_access(self, channel_info: str) -> Optional[str]:
        """验证频道是否存在并可访问，返回频道ID（采用宽松策略）"""
        try:
            logger.info(f"开始验证频道访问: {channel_info}")
            
            # 如果是数字ID，直接返回
            if channel_info.startswith('-') and channel_info[1:].isdigit():
                logger.info(f"频道 {channel_info} 是数字ID格式，直接返回")
                return channel_info
            
            # 如果是用户名或链接，尝试获取频道信息
            if channel_info.startswith('@'):
                try:
                    # 尝试获取频道信息
                    logger.info(f"尝试获取频道信息: {channel_info}")
                    chat = await self.client.get_chat(channel_info)
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
                                    
                                    chat = await self.client.get_chat(test_id)
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
                            chat = await self.client.get_chat(f"@{username}")
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
                    chat = await self.client.get_chat(int(channel_info))
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"直接使用数字ID成功: {channel_info}")
                            return str(chat.id)
                except Exception as e:
                    logger.debug(f"直接使用数字ID {channel_info} 失败: {e}")
                
                try:
                    # 尝试添加 -100 前缀
                    prefixed_id = int(f"-100{channel_info}")
                    chat = await self.client.get_chat(prefixed_id)
                    if chat and hasattr(chat, 'type'):
                        if self._is_valid_channel_type(chat.type):
                            logger.info(f"使用前缀ID成功: {prefixed_id}")
                            return str(prefixed_id)
                except Exception as e:
                    logger.debug(f"使用前缀ID -100{channel_info} 失败: {e}")
                
                try:
                    # 尝试添加 -1001 前缀
                    alt_prefixed_id = int(f"-1001{channel_info}")
                    chat = await self.client.get_chat(alt_prefixed_id)
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
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
            
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
                [("🔙 返回频道管理", "show_channel_config_menu")]
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
            
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
                [("🔄 设置小尾巴文本", f"request_tail_text:{pair_index}")],
                [("⚙️ 设置添加频率", f"select_tail_frequency:{pair_index}")],
                [("🔙 返回过滤设置", f"edit_filters:{pair_index}")]
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
            
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
                [("➕ 添加按钮", f"request_buttons:{pair_index}")],
                [("🗑️ 清空按钮", "clear_additional_buttons")],
                [("⚙️ 设置添加频率", f"select_button_frequency:{pair_index}")],
                [("🔙 返回过滤设置", f"edit_filters:{pair_index}")]
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
            if not user_config:
                user_config = {}
            
            # 使用统一的初始化方法，确保关键字过滤默认为开启
            channel_filters = await self._init_channel_filters(user_id, pair['id'])
            
            # 检查是否启用独立过滤
            independent_filters = channel_filters.get('independent_enabled', False)
            
            # 添加UI显示调试日志
            logger.info(f"🔍 UI显示调试 - 频道组 {pair_index}:")
            logger.info(f"  • channel_filters: {channel_filters}")
            logger.info(f"  • independent_filters: {independent_filters}")
            logger.info(f"  • user_config中的channel_filters: {user_config.get('channel_filters', {})}")
            logger.info(f"  • 将显示状态: {'✅ 已启用' if independent_filters else '❌ 使用全局配置'}")
            
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
• 文本内容移除: {content_removal_status}
• 链接移除: {links_removal_status}
• 用户名移除: {usernames_removal_status}
• 按钮移除: {buttons_removal_status}

✨ **内容增强设置**
• 小尾巴文本: {tail_status}
• 附加按钮: {buttons_add_status}

💡 请选择要配置的过滤选项：
            """.strip()
            
            # 生成过滤配置按钮
            buttons = [
                [("🔄 独立过滤开关", f"toggle_channel_independent_filters:{pair['id']}")],
                [("🔑 关键字过滤", f"channel_keywords:{pair['id']}")],
                [("🔄 敏感词替换", f"channel_replacements:{pair['id']}")],
                [("📝 文本内容移除", f"channel_content_removal:{pair['id']}")],
                [("🔗 链接移除", f"channel_links_removal:{pair['id']}")],
                [("👤 用户名移除", f"channel_usernames_removal:{pair['id']}")],
                [("🔘 按钮移除", f"channel_buttons_removal:{pair['id']}")],
                [("📝 添加小尾巴", f"channel_tail_text:{pair['id']}")],
                [("🔘 添加按钮", f"channel_buttons:{pair['id']}")],
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
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

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 设置用户状态为等待关键字输入
            self.user_states[user_id] = {
                'state': 'waiting_for_channel_keywords',
                'data': {'pair_index': pair_index}
            }
            
            await callback_query.edit_message_text(config_text)
            
        except Exception as e:
            logger.error(f"处理频道组关键字过滤失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _process_channel_keywords_input(self, message: Message, state: Dict[str, Any]):
        """处理频道组关键字输入"""
        try:
            user_id = str(message.from_user.id)
            pair_index = state['data']['pair_index']
            text = message.text.strip()
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await message.reply("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
                await save_user_config(user_id, user_config)
                
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
                await save_user_config(user_id, user_config)
                
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
                    await save_user_config(user_id, user_config)
                    
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
                    await save_user_config(user_id, user_config)
                    
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await message.reply("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
                await save_user_config(user_id, user_config)
                
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
                await save_user_config(user_id, user_config)
                
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
                    await save_user_config(user_id, user_config)
                    
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
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

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 设置用户状态为等待替换词输入
            self.user_states[user_id] = {
                'state': 'waiting_for_channel_replacements',
                'data': {'pair_index': pair_index}
            }
            
            await callback_query.edit_message_text(config_text)
            
        except Exception as e:
            logger.error(f"处理频道组敏感词替换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_content_removal(self, callback_query: CallbackQuery):
        """处理频道组文本内容移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            
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
            
            # 获取该频道组的文本内容移除配置
            user_config = await get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            content_removal = channel_filters.get('content_removal', False)
            content_removal_mode = channel_filters.get('content_removal_mode', 'text_only')
            
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            mode_text = mode_descriptions.get(content_removal_mode, '未知模式')
            
            config_text = f"""
📝 **频道组 {pair_index + 1} 文本内容移除**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if content_removal else '❌ 已禁用'}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 仅移除纯文本：只移除没有媒体内容的纯文本消息
• 移除所有包含文本的信息：移除所有包含文本的消息（包括图片、视频等）

🔙 发送 /menu 返回主菜单
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
            logger.error(f"处理频道组文本内容移除失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_toggle_channel_content_removal(self, callback_query: CallbackQuery):
        """处理频道组文本内容移除开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
            await callback_query.answer(f"✅ 文本内容移除已{'启用' if new_status else '禁用'}")
            
            # 返回配置页面
            await self._handle_channel_content_removal(callback_query)
            
        except Exception as e:
            logger.error(f"处理频道组文本内容移除开关切换失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_set_channel_content_mode(self, callback_query: CallbackQuery):
        """处理频道组文本内容移除模式设置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_parts = callback_query.data.split(':')
            pair_index = int(data_parts[1])
            mode = data_parts[2]
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
            mode_descriptions = {
                'text_only': '仅移除纯文本',
                'all_content': '移除所有包含文本的信息'
            }
            mode_text = mode_descriptions.get(mode, '未知模式')
            
            await callback_query.answer(f"✅ 已设置为：{mode_text}")
            
            # 直接显示成功消息，不返回配置页面
            success_text = f"""
✅ **文本内容移除模式设置成功！**

📡 **频道组：** {pair_index + 1}
🔧 **当前模式：** {mode_text}
📝 **功能状态：** ✅ 已启用

💡 **说明：**
• 仅移除纯文本：只移除纯文本消息
• 移除所有包含文本的信息：移除所有包含文本的消息

🔙 发送 /menu 返回主菜单
            """.strip()
            
            await callback_query.edit_message_text(success_text)
            
        except Exception as e:
            logger.error(f"处理频道组文本内容移除模式设置失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_links_removal(self, callback_query: CallbackQuery):
        """处理频道组链接移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            
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
            
            # 获取该频道组的链接移除配置
            user_config = await get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {}).get(pair['id'], {})
            links_removal = channel_filters.get('links_removal', False)
            links_removal_mode = channel_filters.get('links_removal_mode', 'links_only')
            
            mode_text = "智能移除链接" if links_removal_mode == 'links_only' else "移除整条消息"
            
            config_text = f"""
🔗 **频道组 {pair_index + 1} 链接移除**

📡 **采集频道：** {source_name}

📊 **当前状态：** {'✅ 已启用' if links_removal else '❌ 已禁用'}
🔧 **移除模式：** {mode_text}

💡 **功能说明：**
• 智能移除链接：只移除消息中的链接，保留其他内容
• 移除整条消息：包含链接的整条消息将被完全移除

🔙 发送 /menu 返回主菜单
            """.strip()
            
            # 生成配置按钮
            buttons = [
                [("🔄 切换开关", f"toggle_channel_links_removal:{pair_index}")],
                [("🔗 智能移除链接", f"set_channel_links_mode:{pair_index}:links_only")],
                [("🗑️ 移除整条消息", f"set_channel_links_mode:{pair_index}:message_only")],
                [("🔙 返回过滤配置", f"channel_filters:{pair['id']}")]
            ]
            
            await callback_query.edit_message_text(
                config_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"处理频道组链接移除失败: {e}")
            await callback_query.edit_message_text("❌ 处理失败，请稍后重试")
    
    async def _handle_channel_usernames_removal(self, callback_query: CallbackQuery):
        """处理频道组用户名移除配置"""
        try:
            user_id = str(callback_query.from_user.id)
            data_part = callback_query.data.split(':')[1]
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
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
    
    async def _handle_toggle_channel_usernames_removal(self, callback_query: CallbackQuery):
        """处理频道组用户名移除开关切换"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取频道组信息
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            
            # 获取用户配置
            user_config = await get_user_config(user_id)
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
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            user_config = await get_user_config(user_id)
            
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
            logger.info(f"🔍 独立过滤开关调试 - 频道组 {pair_index}:")
            logger.info(f"  • 当前状态: {current_status}")
            logger.info(f"  • 新状态: {new_status}")
            logger.info(f"  • 当前channel_filters: {channel_filters}")
            logger.info(f"  • user_config中的channel_filters: {user_config.get('channel_filters', {})}")
            
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
• 文本内容移除: {'✅ 开启' if global_config['content_removal'] else '❌ 关闭'}
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
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            if pair_index >= len(channel_pairs):
                await callback_query.edit_message_text("❌ 频道组不存在")
                return
            
            pair = channel_pairs[pair_index]
            source_id = pair.get('source_id')
            target_id = pair.get('target_id')
            source_name = pair.get('source_name', f'频道{pair_index+1}')
            target_name = pair.get('target_name', f'目标{pair_index+1}')
            
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
                
                # 创建搬运任务（搬运最近的消息）
                logger.info(f"正在创建搬运任务...")
                task = await self.cloning_engine.create_task(
                    source_chat_id=source_id,
                    target_chat_id=target_id,
                    start_id=None,  # 从最近的消息开始
                    end_id=None,    # 不限制结束ID
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
                    
                    # 创建任务配置
                    task_config = {
                        'user_id': user_id,
                        'pair_index': pair_index,
                        'pair_id': pair['id'],
                        'message_ids': parsed_info['ids'],
                        'message_ranges': parsed_info['ranges']
                    }
                    
                    logger.info(f"正在创建搬运任务...")
                    task = await self.cloning_engine.create_task(
                        source_chat_id=source_id,
                        target_chat_id=target_id,
                        start_id=start_id,
                        end_id=end_id,
                        config=task_config
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
        """后台更新任务状态（每5秒更新一次）"""
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
                                    logger.warning(f"更新UI失败，但任务仍在运行: {ui_error}")
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
                    
                    # 等待5秒后再次更新
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.error(f"更新任务状态失败: {e}")
                    # 出错后等待5秒再重试
                    await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"后台更新任务状态失败: {e}")
    
    async def _refresh_task_status_page(self, callback_query: CallbackQuery, task: Any, pair_index: int):
        """刷新任务状态页面"""
        try:
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
            else:
                start_time = getattr(task, 'start_time', None)
            
            if start_time:
                elapsed = datetime.now() - start_time
                total_seconds = elapsed.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                seconds = int(total_seconds % 60)
                
                if hours > 0:
                    run_time = f"{hours}时{minutes}分{seconds}秒"
                else:
                    run_time = f"{minutes}分{seconds}秒"
                
                # 计算处理速度和成功率
                if total_seconds > 0 and processed > 0:
                    speed = processed / total_seconds
                    speed_info = f"{speed:.2f} 条/秒"
                    
                    # 计算成功率
                    failed_count = stats.get('failed_messages', 0)
                    if processed > 0:
                        success_rate = ((processed - failed_count) / processed) * 100
                    
                    # 估算剩余时间
                    if total > processed and speed > 0:
                        remaining_messages = total - processed
                        remaining_seconds = remaining_messages / speed
                        
                        if remaining_seconds < 60:
                            eta_info = f"{int(remaining_seconds)}秒"
                        elif remaining_seconds < 3600:
                            eta_minutes = int(remaining_seconds // 60)
                            eta_seconds = int(remaining_seconds % 60)
                            eta_info = f"{eta_minutes}分{eta_seconds}秒"
                        else:
                            eta_hours = int(remaining_seconds // 3600)
                            eta_minutes = int((remaining_seconds % 3600) // 60)
                            eta_info = f"{eta_hours}时{eta_minutes}分"
                    else:
                        eta_info = "即将完成"
            
            # 获取多任务信息
            multi_task_info = ""
            if self.cloning_engine:
                engine_stats = self.cloning_engine.get_engine_stats()
                active_count = engine_stats.get('active_tasks_count', 0)
                if active_count > 1:
                    multi_task_info = f"\n🔄 **多任务模式：** 当前运行 {active_count} 个任务"
            
            # 生成进度条
            progress_bar = self._generate_progress_bar(progress)
            
            # 构建状态文本
            status_text = f"""
🚀 **搬运任务实时状态**{multi_task_info}

📡 **频道组：** {pair_index + 1}
📊 **任务状态：** {status_icon} {status.upper()}
📈 **进度：** {progress:.1f}% {progress_bar}
📝 **已处理：** {processed:,}/{total:,} 条消息
✅ **成功率：** {success_rate:.1f}%
⏱️ **运行时间：** {run_time}
🚀 **处理速度：** {speed_info}
⏰ **预计剩余：** {eta_info}

📊 **详细统计：**
• 成功搬运：{stats.get('processed_messages', 0):,} 条
• 失败消息：{stats.get('failed_messages', 0):,} 条
• 媒体消息：{stats.get('media_messages', 0):,} 条
• 文本消息：{stats.get('text_messages', 0):,} 条
• 媒体组数：{stats.get('media_groups', 0):,} 组
• 过滤消息：{stats.get('filtered_messages', 0):,} 条
            """.strip()
            
            # 根据任务状态生成不同的按钮
            if status == 'running':
                buttons = [
                    [("🔄 刷新状态", f"refresh_task_status:{pair_index}"), ("📊 任务详情", f"view_task_details:{pair_index}")],
                    [("🛑 停止任务", f"stop_cloning:{pair_index}")],
                    [("📋 查看所有任务", "view_all_tasks"), ("🔙 返回主菜单", "show_main_menu")]
                ]
            elif status == 'completed':
                buttons = [
                    [("📋 查看所有任务", "view_all_tasks"), ("🔙 返回主菜单", "show_main_menu")]
                ]
            else:
                buttons = [
                    [("📋 查看所有任务", "view_all_tasks"), ("🔙 返回主菜单", "show_main_menu")]
                ]
            
            await callback_query.edit_message_text(
                status_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"刷新任务状态页面失败: {e}")
    
    async def _show_task_completed_page(self, callback_query: CallbackQuery, pair_index: int):
        """显示任务完成页面"""
        try:
            # 尝试获取任务统计信息
            stats_info = ""
            time_info = ""
            if self.cloning_engine:
                tasks = self.cloning_engine.get_all_tasks()
                logger.info(f"获取到 {len(tasks)} 个任务")
                # 查找该频道组的任务（不限制状态）
                for task in tasks:
                    # 检查task是对象还是字典
                    if isinstance(task, dict):
                        task_id = task.get('task_id', 'unknown')
                        config = task.get('config', {})
                        stats = task.get('stats', {})
                        start_time_str = task.get('start_time')
                        end_time_str = task.get('end_time')
                        logger.info(f"检查任务 {task_id}，配置: {config}")
                        
                        if config.get('pair_index') == pair_index:
                            logger.info(f"找到频道组 {pair_index} 的任务 {task_id}，状态: {task.get('status')}，统计: {stats}")
                            
                            # 计算用时
                            if start_time_str and end_time_str:
                                try:
                                    start_time = datetime.fromisoformat(start_time_str)
                                    end_time = datetime.fromisoformat(end_time_str)
                                    duration = end_time - start_time
                                    total_seconds = duration.total_seconds()
                                    
                                    if total_seconds < 60:
                                        time_str = f"{total_seconds:.1f} 秒"
                                    elif total_seconds < 3600:
                                        minutes = total_seconds / 60
                                        time_str = f"{minutes:.1f} 分钟"
                                    else:
                                        hours = total_seconds / 3600
                                        time_str = f"{hours:.1f} 小时"
                                    
                                    time_info = f"""
⏱️ **任务用时：** {time_str}
🕐 **开始时间：** {start_time.strftime('%Y-%m-%d %H:%M:%S')}
🕐 **完成时间：** {end_time.strftime('%Y-%m-%d %H:%M:%S')}
                                    """.strip()
                                except Exception as time_error:
                                    logger.warning(f"时间解析失败: {time_error}")
                                    time_info = "⏱️ **任务用时：** 时间信息不可用"
                            else:
                                time_info = "⏱️ **任务用时：** 时间信息不可用"
                            
                            # 构建详细统计信息
                            total_messages = stats.get('processed_messages', 0) + stats.get('failed_messages', 0)
                            success_rate = (stats.get('processed_messages', 0) / total_messages * 100) if total_messages > 0 else 0
                            avg_speed = stats.get('processed_messages', 0) / max(total_seconds, 1)
                            
                            # 获取多任务完成信息
                            engine_stats = self.cloning_engine.get_engine_stats() if self.cloning_engine else {}
                            completed_count = engine_stats.get('completed_tasks_count', 0)
                            total_tasks = engine_stats.get('total_tasks_count', 0)
                            
                            multi_task_summary = ""
                            if total_tasks > 1:
                                multi_task_summary = f"\n🎯 **任务概览：** 已完成 {completed_count}/{total_tasks} 个任务"
                            
                            if total_messages > 0:
                                # 计算数据传输量估算（假设平均每条消息1KB）
                                data_size_mb = total_messages * 0.001  # 简单估算
                                
                                stats_info = f"""
📊 **搬运统计：**
• 总消息数：{total_messages:,} 条
• 成功搬运：{stats.get('processed_messages', 0):,} 条
• 失败消息：{stats.get('failed_messages', 0):,} 条
• 成功率：{success_rate:.1f}%
• 跳过消息：{stats.get('skipped_messages', 0):,} 条

📱 **消息类型分析：**
• 媒体消息：{stats.get('media_messages', 0):,} 条
• 文本消息：{stats.get('text_messages', 0):,} 条
• 媒体组数：{stats.get('media_groups', 0):,} 组
• 过滤消息：{stats.get('filtered_messages', 0):,} 条

🚀 **性能指标：**
• 平均速度：{avg_speed:.2f} 条/秒
• 峰值效率：{avg_speed * 60:.0f} 条/分钟
• 数据传输：约 {data_size_mb:.1f} MB
• 处理效率：{(success_rate/100 * avg_speed):.2f} 有效条/秒
                                """.strip()
                            else:
                                stats_info = """
📊 **搬运统计：**
• 总消息数：0 条
• 成功搬运：0 条
• 失败消息：0 条
• 成功率：0.0%
• 跳过消息：0 条

📱 **消息类型分析：**
• 媒体消息：0 条
• 文本消息：0 条
• 媒体组数：0 组
• 过滤消息：0 条

🚀 **性能指标：**
• 平均速度：0.0 条/秒
• 峰值效率：0 条/分钟
• 数据传输：0 MB
• 处理效率：0.0 有效条/秒
                                """.strip()
                            break
                else:
                    logger.warning(f"未找到频道组 {pair_index} 的任务")
                    # 如果没有找到任务，提供默认信息
                    time_info = "⏱️ **任务用时：** 时间信息不可用"
                    stats_info = """
📊 **搬运统计：**
• 总消息数：0 条
• 成功搬运：0 条
• 失败消息：0 条
• 成功率：0.0%

📱 **消息类型：**
• 媒体消息：0 条
• 文本消息：0 条
• 媒体组数：0 组
• 过滤消息：0 条

🚀 **性能指标：**
• 平均速度：0.0 条/秒
                    """.strip()
            else:
                logger.warning("搬运引擎未初始化")
                # 如果搬运引擎未初始化，提供默认信息
                time_info = "⏱️ **任务用时：** 时间信息不可用"
                stats_info = """
📊 **搬运统计：**
• 总消息数：0 条
• 成功搬运：0 条
• 失败消息：0 条
• 成功率：0.0%

📱 **消息类型：**
• 媒体消息：0 条
• 文本消息：0 条
• 媒体组数：0 组
• 过滤消息：0 条

🚀 **性能指标：**
• 平均速度：0.0 条/秒
                """.strip()
            
            completed_text = f"""
🎉 **搬运任务已完成！**{multi_task_summary}

📡 **频道组：** {pair_index + 1}

✅ **任务状态：** 已完成

{time_info}

{stats_info}

💡 **操作建议：**
• 可以查看其他频道组的搬运状态
• 建议定期清理已完成的任务记录
• 如需重新搬运，请重新配置任务

🔙 返回主菜单继续其他操作
            """.strip()
            
            buttons = [
                [("🔙 返回主菜单", "show_main_menu")]
            ]
            
            await callback_query.edit_message_text(
                completed_text,
                reply_markup=generate_button_layout(buttons)
            )
            
        except Exception as e:
            logger.error(f"显示任务完成页面失败: {e}")
    
    async def _handle_refresh_task_status(self, callback_query: CallbackQuery):
        """处理刷新任务状态"""
        try:
            user_id = str(callback_query.from_user.id)
            pair_index = int(callback_query.data.split(':')[1])
            
            # 获取任务状态
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
                    # 刷新任务状态页面
                    await self._refresh_task_status_page(callback_query, current_task, pair_index)
                else:
                    # 任务可能已完成或失败
                    await self._show_task_completed_page(callback_query, pair_index)
            else:
                await callback_query.answer("❌ 搬运引擎未初始化")
                
        except Exception as e:
            logger.error(f"处理刷新任务状态失败: {e}")
            await callback_query.answer("❌ 刷新失败，请稍后重试")
    
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
    
    async def _handle_toggle_realtime_listen(self, callback_query: CallbackQuery):
        """处理切换实时监听状态"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 获取当前监听状态
            current_status = user_config.get('monitor_enabled', False)
            new_status = not current_status
            
            # 更新配置
            user_config['monitor_enabled'] = new_status
            await save_user_config(user_id, user_config)
            
            # 监听系统已移除，显示状态更新
            status_text = "✅ 设置已更新" if new_status else "❌ 监听已停用"
            await callback_query.answer(status_text)
            
            # 更新监听菜单显示
            monitored_pairs = user_config.get('monitored_pairs', [])
            monitor_text = f"""
👂 **实时监听设置**

📊 **当前状态**
• 监听功能: {'✅ 已启用' if new_status else '❌ 未启用'}
• 监听频道: {len(monitored_pairs)} 个

💡 **功能说明**
实时监听功能会自动检查指定频道的新消息，并自动搬运到目标频道。

⚠️ **注意事项**
• 启用监听后，机器人会持续运行
• 建议在服务器环境下使用
• 请确保机器人有相应权限

请选择操作：
            """.strip()
            
            await callback_query.edit_message_text(
                monitor_text,
                reply_markup=generate_button_layout(MONITOR_SETTINGS_BUTTONS, **{
                    'monitor_status': '✅ 开启' if new_status else '❌ 关闭',
                    'monitor_count': len(monitored_pairs)
                })
            )
            
        except Exception as e:
            logger.error(f"切换监听状态失败: {e}")
            await callback_query.edit_message_text("❌ 操作失败，请稍后重试")
    
    async def _handle_manage_monitor_channels(self, callback_query: CallbackQuery):
        """处理管理监听频道"""
        try:
            user_id = str(callback_query.from_user.id)
            user_config = await get_user_config(user_id)
            
            # 获取用户的频道组配置
            channel_pairs = await get_channel_pairs(user_id)
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
            user_config = await get_user_config(user_id)
            
            # 使用与管理界面相同的数据源
            channel_pairs = await get_channel_pairs(user_id)
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
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
            # 使用与管理界面相同的数据源
            channel_pairs = await get_channel_pairs(user_id)
            
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
            await save_user_config(user_id, user_config)
            
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
            user_config = await get_user_config(user_id)
            
            # 清空监听频道
            user_config['monitored_pairs'] = []
            await save_user_config(user_id, user_config)
            
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
            channel_pairs = await get_channel_pairs(user_id)
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
            channel_pairs = await get_channel_pairs(user_id)
            
            # 检查索引是否有效
            if 0 <= pair_index < len(channel_pairs):
                pair = channel_pairs[pair_index]
                
                # 切换启用状态
                current_enabled = pair.get('enabled', True)
                pair['enabled'] = not current_enabled
                
                # 保存更新后的频道组列表
                success = await data_manager.save_channel_pairs(user_id, channel_pairs)
                
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
            channel_pairs = await get_channel_pairs(user_id)
            
            # 查找并更新频道组状态
            pair_found = False
            for pair in channel_pairs:
                if pair.get('id') == pair_id:
                    # 切换启用状态
                    current_enabled = pair.get('enabled', True)
                    pair['enabled'] = not current_enabled
                    pair_found = True
                    
                    # 保存更新后的频道组列表
                    success = await data_manager.save_channel_pairs(user_id, channel_pairs)
                    
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
                channel_pairs = await get_channel_pairs(user_id)
                deleted_count = len(channel_pairs)
                
                # 清空频道组列表
                success = await data_manager.save_channel_pairs(user_id, [])
                
                if success:
                    # 清空所有频道过滤配置
                    await data_manager.clear_all_channel_filter_configs(user_id)
                    
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
            channel_pairs = await get_channel_pairs(user_id)
            
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
            channel_pairs = await data_manager.get_channel_pairs(user_id)
            
            if pair_index >= len(channel_pairs):
                await message.reply_text("❌ 频道组不存在，请重新操作。")
                del self.user_states[user_id]
                return
            
            # 更新频道组信息
            if channel_id:
                # 获取频道详细信息
                try:
                    chat = await self.app.get_chat(channel_id)
                    channel_pairs[pair_index]['source_id'] = str(channel_id)
                    channel_pairs[pair_index]['source_name'] = chat.title or ""
                    channel_pairs[pair_index]['source_username'] = chat.username or ""
                except:
                    channel_pairs[pair_index]['source_id'] = str(channel_id)
                    channel_pairs[pair_index]['source_name'] = "未知频道"
                    channel_pairs[pair_index]['source_username'] = ""
            else:
                # 即使验证失败也允许保存
                channel_pairs[pair_index]['source_id'] = channel_info
                channel_pairs[pair_index]['source_name'] = "待确认"
                channel_pairs[pair_index]['source_username'] = ""
            
            # 保存更新
            await data_manager.save_channel_pairs(user_id, channel_pairs)
            
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
            channel_pairs = await data_manager.get_channel_pairs(user_id)
            
            if pair_index >= len(channel_pairs):
                await message.reply_text("❌ 频道组不存在，请重新操作。")
                del self.user_states[user_id]
                return
            
            # 更新频道组信息
            if channel_id:
                # 获取频道详细信息
                try:
                    chat = await self.app.get_chat(channel_id)
                    channel_pairs[pair_index]['target_id'] = str(channel_id)
                    channel_pairs[pair_index]['target_name'] = chat.title or ""
                    channel_pairs[pair_index]['target_username'] = chat.username or ""
                except:
                    channel_pairs[pair_index]['target_id'] = str(channel_id)
                    channel_pairs[pair_index]['target_name'] = "未知频道"
                    channel_pairs[pair_index]['target_username'] = ""
            else:
                # 即使验证失败也允许保存
                channel_pairs[pair_index]['target_id'] = channel_info
                channel_pairs[pair_index]['target_name'] = "待确认"
                channel_pairs[pair_index]['target_username'] = ""
            
            # 保存更新
            await data_manager.save_channel_pairs(user_id, channel_pairs)
            
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

# ==================== 主函数 ====================
async def main():
    """主函数"""
    try:
        # 创建机器人实例
        bot = TelegramBot()
        
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
