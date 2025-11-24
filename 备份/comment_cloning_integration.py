# ==================== 评论搬运功能集成 ====================
"""
评论搬运功能集成到现有机器人系统
提供完整的评论搬运命令和用户界面
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from pyrogram.client import Client
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from comment_cloning_engine import CommentCloningEngine, CommentCloneTask

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

class CommentCloningIntegration:
    """评论搬运功能集成类"""
    
    def __init__(self, bot_instance):
        """初始化集成"""
        self.bot = bot_instance
        self.client = bot_instance.client
        self.comment_engine = None
        self.user_states = {}  # 存储用户状态
        
        logger.info("🚀 评论搬运功能集成初始化")
    
    async def initialize(self):
        """初始化评论搬运引擎"""
        try:
            # 创建评论搬运引擎
            # 获取默认用户配置，如果data_manager需要user_id参数
            try:
                # 尝试获取默认用户配置
                user_config = self.bot.data_manager.get_user_config('default_user')
            except TypeError:
                # 如果get_user_config不需要参数，直接调用
                try:
                    user_config = self.bot.data_manager.get_user_config()
                except Exception:
                    # 如果都失败，使用默认配置
                    from config import DEFAULT_USER_CONFIG
                    user_config = DEFAULT_USER_CONFIG
            
            config = {
                'retry_attempts': 3,
                'retry_delay': 2.0,
                'comment_delay': 1.0,
                'max_comments_per_message': 10,
                'media_group_search_range': 50,
                'media_group_timeout': 30.0,
                'continue_on_error': True,
                'max_consecutive_errors': 5,
                'user_config': user_config
            }
            
            self.comment_engine = CommentCloningEngine(self.client, config)
            logger.info("✅ 评论搬运引擎初始化成功")
            
        except Exception as e:
            logger.error(f"❌ 评论搬运引擎初始化失败: {e}")
            raise
    
    def register_commands(self):
        """注册评论搬运相关命令"""
        logger.info("📝 注册评论搬运命令")
        
        # 评论搬运命令
        @self.client.on_message(filters.command("comment_clone"))
        async def comment_clone_command(client, message: Message):
            await self._handle_comment_clone_command(message)
        
        @self.client.on_message(filters.command("comment_tasks"))
        async def comment_tasks_command(client, message: Message):
            await self._handle_comment_tasks_command(message)
        
        @self.client.on_message(filters.command("comment_status"))
        async def comment_status_command(client, message: Message):
            await self._handle_comment_status_command(message)
        
        @self.client.on_message(filters.command("comment_cancel"))
        async def comment_cancel_command(client, message: Message):
            await self._handle_comment_cancel_command(message)
        
        @self.client.on_message(filters.command("comment_pause"))
        async def comment_pause_command(client, message: Message):
            await self._handle_comment_pause_command(message)
        
        @self.client.on_message(filters.command("comment_resume"))
        async def comment_resume_command(client, message: Message):
            await self._handle_comment_resume_command(message)
        
        # 回调查询处理器
        @self.client.on_callback_query()
        async def comment_callback_handler(client, callback_query: CallbackQuery):
            await self._handle_comment_callback(callback_query)
    
    async def _handle_comment_clone_command(self, message: Message):
        """处理评论搬运命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 检查用户权限
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            # 解析命令参数
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if len(args) < 4:
                await self._show_comment_clone_help(message)
                return
            
            # 解析参数
            source_channel = args[0]
            target_channel = args[1]
            target_message_id = int(args[2])
            message_ids = [int(msg_id) for msg_id in args[3:]]
            
            # 检查是否有AI改写相关的参数
            ai_rewrite_enabled = False
            for arg in args:
                if arg.startswith("--ai-rewrite="):
                    mode = arg.split("=")[1]
                    if mode in ["on", "off", "auto"]:
                        ai_rewrite_enabled = mode != "off"
            
            # 获取用户配置
            user_config = self.bot.data_manager.get_user_config(user_id)
            
            # 创建任务配置
            task_config = {
                'retry_attempts': 3,
                'retry_delay': 2.0,
                'comment_delay': 1.0,
                'max_comments_per_message': 10,
                'media_group_search_range': 50,
                'media_group_timeout': 30.0,
                'continue_on_error': True,
                'max_consecutive_errors': 5,
                'user_config': user_config,
                'ai_rewrite_enabled': ai_rewrite_enabled,
                'ai_rewrite_mode': user_config.get('ai_rewrite_mode', 'auto'),
                'ai_rewrite_intensity': user_config.get('ai_rewrite_intensity', 'medium')
            }
            
            # 创建任务
            task_id = await self.comment_engine.create_comment_clone_task(
                source_chat_id=source_channel,
                target_chat_id=target_channel,
                target_message_id=target_message_id,
                message_ids=message_ids,
                config=task_config,
                user_id=user_id
            )
            
            # 启动任务
            success = await self.comment_engine.start_comment_clone_task(task_id)
            
            if success:
                await message.reply(f"✅ 评论搬运任务创建成功！\n任务ID: `{task_id}`")
            else:
                await message.reply("❌ 评论搬运任务创建失败")
                
        except ValueError as e:
            await message.reply(f"❌ 参数错误: {e}")
        except Exception as e:
            logger.error(f"❌ 处理评论搬运命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_tasks_command(self, message: Message):
        """处理评论任务列表命令"""
        try:
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            tasks = self.comment_engine.get_all_tasks()
            
            if not tasks:
                await message.reply("📭 当前没有活跃的评论搬运任务")
                return
            
            # 创建任务列表消息
            text = "📋 当前评论搬运任务:\n\n"
            buttons = []
            
            for i, (task_id, task_info) in enumerate(tasks.items(), 1):
                status_emoji = {
                    'pending': '⏳',
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'paused': '⏸️',
                    'cancelled': '🛑'
                }.get(task_info['status'], '❓')
                
                text += f"{i}. {status_emoji} {task_info['status']}\n"
                text += f"   • 进度: {task_info['progress']:.1f}%\n"
                text += f"   • 成功: {task_info['processed_messages']}\n"
                text += f"   • 失败: {task_info['failed_messages']}\n\n"
                
                # 添加控制按钮
                if task_info['status'] == 'running':
                    buttons.append([
                        InlineKeyboardButton(f"暂停 {i}", callback_data=f"comment_pause_{task_id}"),
                        InlineKeyboardButton(f"取消 {i}", callback_data=f"comment_cancel_{task_id}")
                    ])
                elif task_info['status'] == 'paused':
                    buttons.append([
                        InlineKeyboardButton(f"恢复 {i}", callback_data=f"comment_resume_{task_id}"),
                        InlineKeyboardButton(f"取消 {i}", callback_data=f"comment_cancel_{task_id}")
                    ])
            
            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
            
            await message.reply(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ 处理评论任务列表命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_status_command(self, message: Message):
        """处理评论任务状态命令"""
        try:
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if not args:
                await message.reply("❌ 请提供任务ID\n用法: `/comment_status <task_id>`")
                return
            
            task_id = args[0]
            status = await self.comment_engine.get_task_status(task_id)
            
            if not status:
                await message.reply("❌ 任务不存在")
                return
            
            # 创建状态消息
            text = f"📊 任务状态: `{task_id}`\n\n"
            text += f"状态: {status['status']}\n"
            text += f"进度: {status['progress']:.1f}%\n"
            text += f"已处理: {status['processed_messages']}\n"
            text += f"失败: {status['failed_messages']}\n"
            text += f"源频道: {status['source_channel_name']}\n"
            text += f"目标频道: {status['target_channel_name']}\n"
            text += f"目标消息ID: {status['target_message_id']}\n"
            
            if status['start_time']:
                text += f"开始时间: {status['start_time']}\n"
            if status['end_time']:
                text += f"结束时间: {status['end_time']}\n"
            
            await message.reply(text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"❌ 处理评论状态命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_cancel_command(self, message: Message):
        """处理取消评论任务命令"""
        try:
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if not args:
                await message.reply("❌ 请提供任务ID\n用法: `/comment_cancel <task_id>`", parse_mode="Markdown")
                return
            
            task_id = args[0]
            success = await self.comment_engine.cancel_task(task_id)
            
            if success:
                await message.reply(f"✅ 任务 `{task_id}` 已取消", parse_mode="Markdown")
            else:
                await message.reply("❌ 取消任务失败")
                
        except Exception as e:
            logger.error(f"❌ 处理取消评论任务命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_pause_command(self, message: Message):
        """处理暂停评论任务命令"""
        try:
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if not args:
                await message.reply("❌ 请提供任务ID\n用法: `/comment_pause <task_id>`", parse_mode="Markdown")
                return
            
            task_id = args[0]
            success = await self.comment_engine.pause_task(task_id)
            
            if success:
                await message.reply(f"✅ 任务 `{task_id}` 已暂停", parse_mode="Markdown")
            else:
                await message.reply("❌ 暂停任务失败")
                
        except Exception as e:
            logger.error(f"❌ 处理暂停评论任务命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_resume_command(self, message: Message):
        """处理恢复评论任务命令"""
        try:
            if not await self._check_user_permission(message):
                await message.reply("❌ 您没有权限使用此功能")
                return
            
            args = message.text.split()[1:] if len(message.text.split()) > 1 else []
            
            if not args:
                await message.reply("❌ 请提供任务ID\n用法: `/comment_resume <task_id>`", parse_mode="Markdown")
                return
            
            task_id = args[0]
            # 显示恢复预览，提供确认按钮
            task = None
            if task_id in self.comment_engine.active_tasks:
                task = self.comment_engine.active_tasks[task_id]
            else:
                # 尝试通过状态接口获取（如果实现）
                try:
                    task = await self.comment_engine.get_task_status(task_id)
                except Exception:
                    task = None

            if not task:
                await message.reply(f"❌ 未找到任务 `{task_id}`（可能已完成或不在活动列表中）", parse_mode="Markdown")
                return

            # task 可能是字典或对象
            if isinstance(task, dict):
                processed = task.get('processed_messages', 0)
                total = task.get('total_messages', 0)
                message_ids = task.get('message_ids', [])
                processed_ids = set(task.get('processed_message_ids', []))
            else:
                processed = getattr(task, 'processed_messages', 0)
                total = getattr(task, 'total_messages', 0)
                message_ids = getattr(task, 'message_ids', [])
                processed_ids = getattr(task, 'processed_message_ids', set())

            # 计算断点起始ID（第一个未处理的消息ID）
            resume_from_id = None
            for mid in message_ids:
                if mid not in processed_ids:
                    resume_from_id = mid
                    break

            text = f"🔄 恢复预览: `{task_id}`\n\n"
            text += f"状态: {getattr(task, 'status', task.get('status') if isinstance(task, dict) else 'unknown')}\n"
            text += f"已处理: {processed}/{total}\n"
            if resume_from_id:
                text += f"下次开始消息ID: {resume_from_id}\n"
            else:
                text += "所有消息均已处理或无法确定下一起始ID\n"

            # 按钮：确认恢复、查看详情、取消
            buttons = [
                [
                    InlineKeyboardButton("✅ 确认恢复", callback_data=f"comment_confirm_resume_{task_id}_{resume_from_id or 0}"),
                    InlineKeyboardButton("✖ 取消", callback_data=f"comment_cancel_{task_id}")
                ],
                [InlineKeyboardButton("🔍 详细", callback_data=f"comment_preview_{task_id}")]
            ]

            keyboard = InlineKeyboardMarkup(buttons)
            await message.reply(text, reply_markup=keyboard, parse_mode="Markdown")
                
        except Exception as e:
            logger.error(f"❌ 处理恢复评论任务命令失败: {e}")
            await message.reply(f"❌ 处理失败: {e}")
    
    async def _handle_comment_callback(self, callback_query: CallbackQuery):
        """处理评论搬运相关的回调查询"""
        try:
            data = callback_query.data
            
            if str(data).startswith("comment_pause_"):
                task_id = str(data).replace("comment_pause_", "")
                success = await self.comment_engine.pause_task(str(task_id))
                
                if success:
                    await callback_query.answer("✅ 任务已暂停")
                else:
                    await callback_query.answer("❌ 暂停失败")
                    
            elif str(data).startswith("comment_cancel_"):
                task_id = str(data).replace("comment_cancel_", "")
                success = await self.comment_engine.cancel_task(str(task_id))
                
                if success:
                    await callback_query.answer("✅ 任务已取消")
                else:
                    await callback_query.answer("❌ 取消失败")
                    
            elif str(data).startswith("comment_resume_"):
                # 显示恢复预览（从回调触发）
                task_id = str(data).replace("comment_resume_", "")
                # 重用命令逻辑 by creating a fake Message-like reply
                try:
                    # Build preview similar to _handle_comment_resume_command
                    task = None
                    if str(task_id) in self.comment_engine.active_tasks:
                        task = self.comment_engine.active_tasks[str(task_id)]
                    else:
                        try:
                            task = await self.comment_engine.get_task_status(str(task_id))
                        except Exception:
                            task = None

                    if not task:
                        await callback_query.answer("❌ 未找到任务或任务不在活动列表中")
                    else:
                        if isinstance(task, dict):
                            processed = task.get('processed_messages', 0)
                            total = task.get('total_messages', 0)
                            message_ids = task.get('message_ids', [])
                            processed_ids = set(task.get('processed_message_ids', []))
                        else:
                            processed = getattr(task, 'processed_messages', 0)
                            total = getattr(task, 'total_messages', 0)
                            message_ids = getattr(task, 'message_ids', [])
                            processed_ids = getattr(task, 'processed_message_ids', set())

                        resume_from_id = None
                        for mid in message_ids:
                            if mid not in processed_ids:
                                resume_from_id = mid
                                break

                        text = f"🔄 恢复预览: `{task_id}`\n\n"
                        text += f"状态: {getattr(task, 'status', task.get('status') if isinstance(task, dict) else 'unknown')}\n"
                        text += f"已处理: {processed}/{total}\n"
                        if resume_from_id:
                            text += f"下次开始消息ID: {resume_from_id}\n"
                        else:
                            text += "所有消息均已处理或无法确定下一起始ID\n"

                        buttons = [
                            [InlineKeyboardButton("✅ 确认恢复", callback_data=f"comment_confirm_resume_{task_id}_{resume_from_id or 0}"),
                             InlineKeyboardButton("✖ 取消", callback_data=f"comment_cancel_{task_id}")],
                            [InlineKeyboardButton("🔍 详细", callback_data=f"comment_preview_{task_id}")]
                        ]

                        await callback_query.message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
                        await callback_query.answer()
                except Exception as e:
                    logger.error(f"处理恢复回调失败: {e}")
                    await callback_query.answer("❌ 处理失败")
            elif str(data).startswith("comment_confirm_resume_"):
                # 确认恢复：格式 comment_confirm_resume_<task_id>_<resume_from>
                try:
                    payload = str(data)[len("comment_confirm_resume_"):]
                    # task_id 可能包含下划线，右分割一次获取 resume_from
                    if '_' in str(payload):
                        task_id, resume_from_str = str(payload).rsplit('_', 1)
                    else:
                        task_id = payload
                        resume_from_str = '0'

                    resume_from = int(resume_from_str) if resume_from_str.isdigit() else None

                    # 尝试恢复（CommentCloningEngine 目前只实现 resume_task）
                    success = await self.comment_engine.resume_task(str(task_id))
                    if success:
                        await callback_query.answer("✅ 任务已开始恢复")
                        await callback_query.message.reply(f"🔄 任务 `{task_id}` 已开始恢复（从 {resume_from or '上次断点'} 开始）。")
                    else:
                        await callback_query.answer("❌ 恢复失败")
                except Exception as e:
                    logger.error(f"处理确认恢复失败: {e}")
                    await callback_query.answer("❌ 处理失败")

            elif str(data).startswith("comment_preview_"):
                try:
                    task_id = str(data).replace("comment_preview_", "")
                    task = None
                    if str(task_id) in self.comment_engine.active_tasks:
                        task = self.comment_engine.active_tasks[str(task_id)]
                    else:
                        try:
                            task = await self.comment_engine.get_task_status(str(task_id))
                        except Exception:
                            task = None

                    if not task:
                        await callback_query.answer("❌ 未找到任务详情")
                        return

                    if isinstance(task, dict):
                        processed = task.get('processed_messages', 0)
                        total = task.get('total_messages', 0)
                        message_ids = task.get('message_ids', [])
                        processed_ids = list(task.get('processed_message_ids', []))
                    else:
                        processed = getattr(task, 'processed_messages', 0)
                        total = getattr(task, 'total_messages', 0)
                        message_ids = getattr(task, 'message_ids', [])
                        processed_ids = list(getattr(task, 'processed_message_ids', []))

                    # 构建详细文本（简要）
                    preview_text = f"🔎 任务详细: `{task_id}`\n\n"
                    preview_text += f"已处理: {processed}/{total}\n"
                    preview_text += f"已处理ID (示例前10): {processed_ids[:10]}\n"
                    preview_text += f"全部消息总数: {len(message_ids)}\n"
                    preview_text += f"消息ID范围示例: {message_ids[:10]}{'...' if len(message_ids)>10 else ''}\n"

                    await callback_query.message.reply(preview_text, parse_mode="Markdown")
                    await callback_query.answer()
                except Exception as e:
                    logger.error(f"处理详细预览失败: {e}")
                    await callback_query.answer("❌ 处理失败")
            
            # 更新消息
            await callback_query.message.edit_reply_markup(reply_markup=None)
            
        except Exception as e:
            logger.error(f"❌ 处理评论回调查询失败: {e}")
            await callback_query.answer("❌ 处理失败")
    
    async def _show_comment_clone_help(self, message: Message):
        """显示评论搬运帮助信息"""
        help_text = """
🤖 评论搬运功能帮助

📝 基本用法:
`/comment_clone <源频道> <目标频道> <目标消息ID> <消息ID1> [消息ID2] ...`

📋 示例:
`/comment_clone @source_channel @target_channel 12345 12346 12347 12348`

📊 其他命令:
• `/comment_tasks` - 查看所有任务
• `/comment_status <task_id>` - 查看任务状态
• `/comment_cancel <task_id>` - 取消任务
• `/comment_pause <task_id>` - 暂停任务
• `/comment_resume <task_id>` - 恢复任务

🔧 AI文本改写选项:
• `--ai-rewrite=on` - 强制启用AI改写
• `--ai-rewrite=off` - 禁用AI改写
• `--ai-rewrite=auto` - 自动模式(默认)

💡 说明:
• 源频道: 要搬运消息的频道
• 目标频道: 要发送评论的频道
• 目标消息ID: 将在此消息下评论
• 消息ID: 要搬运的消息ID列表

⚠️ 注意:
• 需要相应的频道访问权限
• 支持文本和媒体消息搬运
• 支持媒体组消息搬运
        """
        
        await message.reply(help_text, parse_mode="Markdown")
    
    async def _check_user_permission(self, message: Message) -> bool:
        """检查用户权限"""
        try:
            # 这里可以添加权限检查逻辑
            # 例如检查用户是否为管理员、是否有特定权限等
            user_id = str(message.from_user.id)
            
            # 简单的权限检查示例
            # 可以根据实际需求修改
            return True
            
        except Exception as e:
            logger.error(f"❌ 检查用户权限失败: {e}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.comment_engine:
                # 清理已完成的任务
                self.comment_engine.clear_completed_tasks()
                logger.info("🧹 评论搬运引擎清理完成")
        except Exception as e:
            logger.error(f"❌ 清理评论搬运引擎失败: {e}")

# 集成到现有机器人的函数
def integrate_comment_cloning(bot_instance):
    """将评论搬运功能集成到现有机器人"""
    try:
        # 创建集成实例
        integration = CommentCloningIntegration(bot_instance)
        
        # 初始化
        asyncio.create_task(integration.initialize())
        
        # 注册命令
        integration.register_commands()
        
        # 将集成实例添加到机器人
        bot_instance.comment_cloning_integration = integration
        
        logger.info("✅ 评论搬运功能集成成功")
        return integration
        
    except Exception as e:
        logger.error(f"❌ 评论搬运功能集成失败: {e}")
        return None
