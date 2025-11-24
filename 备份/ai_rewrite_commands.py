# ==================== AI文本改写命令处理器 ====================
"""
AI文本改写命令处理器
处理与AI文本改写功能相关的用户命令
"""

import logging
from typing import Dict, Any
from pyrogram.client import Client
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler
from log_config import get_logger
from data_manager import DataManager

logger = get_logger(__name__)

class AIRewriteCommands:
    """AI文本改写命令处理器"""
    
    def __init__(self, bot_instance):
        """初始化AI文本改写命令处理器"""
        self.bot = bot_instance
        self.client = bot_instance.client
        self.data_manager = bot_instance.data_manager
        logger.info("🚀 AI文本改写命令处理器初始化")
        
        # 初始化API密钥
        self._initialize_api_keys()
    
    def _initialize_api_keys(self):
        """初始化默认API密钥"""
        try:
            # 用户提供的5个API密钥
            default_api_keys = [
                "AIzaSyBLK34oMuDToBAy7o7Z_MSK361koIgcdk4",
                "AIzaSyBhLYU-baLvUYggS5HGWQPzpWx8tgdmg9k",
                "AIzaSyDRj8eWYEZtS-dPGi4XHHQSe-QgXMPYSsQ",
                "AIzaSyAhJrHMwalCtuZft7gg2YozKCDaGnY4K9A",
                "AIzaSyDPb7uRprSGw_iwTIsexYy5u5cz9brigFE"
            ]
            
            # 这里可以添加初始化逻辑，但实际的密钥存储应该在用户配置中处理
            logger.info(f"默认API密钥已加载: {len(default_api_keys)} 个密钥")
            
        except Exception as e:
            logger.error(f"初始化API密钥失败: {e}")
    
    def register_commands(self):
        """注册AI文本改写相关命令"""
        logger.info("📝 注册AI文本改写命令")
        
        # 定义并注册处理私聊消息的处理器（如API密钥输入）
        async def handle_ai_messages(client, message: Message):
            """处理AI相关私聊消息"""
            try:
                # 只处理来自私聊的消息
                if not message.chat or message.chat.type != "private":
                    return
                
                user_id = str(message.from_user.id)
                
                # 检查用户是否在等待输入API密钥
                if (user_id in self.bot.user_states and 
                    self.bot.user_states[user_id].get('step') == 'waiting_for_api_key'):
                    await self._handle_api_key_input(message)
                    return
                
                # 处理 /cancel 命令
                if message.command and message.command[0] == "cancel":
                    if user_id in self.bot.user_states:
                        del self.bot.user_states[user_id]
                        await message.reply("操作已取消")
                    else:
                        await message.reply("没有正在进行的操作")
                    return
                    
            except Exception as e:
                logger.error(f"处理AI消息失败: {e}")

        # 注册消息处理器
        self.client.add_handler(MessageHandler(handle_ai_messages, filters.private))
        self.client.add_handler(MessageHandler(self._handle_ai_settings_command, filters.command("ai_settings")))
        self.client.add_handler(MessageHandler(self._handle_ai_status_command, filters.command("ai_status")))
        self.client.add_handler(MessageHandler(self._handle_ai_preview_command, filters.command("ai_preview")))
        
        # 注册回调查询处理器
        self.client.add_handler(CallbackQueryHandler(self._handle_ai_callback, filters.regex(r"^ai_")))
    
    async def _handle_ai_settings_command(self, message: Message):
        """处理AI设置命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取当前AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 构建设置界面
            text = "🤖 AI文本改写设置\n\n"
            text += f"开关状态: {'🟢 开启' if ai_config['enabled'] else '🔴 关闭'}\n"
            text += f"处理模式: {self._get_mode_display(ai_config['mode'])}\n"
            text += f"改写强度: {self._get_intensity_display(ai_config['intensity'])}\n"
            text += f"标签处理: {self._get_tag_handling_display(ai_config['tag_handling'])}\n"
            
            # 获取额度状态
            quota_status = self._get_quota_status(user_id)
            if quota_status:
                text += f"\n📊 额度状态:\n"
                text += f"  输入: {quota_status['input_used']:,}/{quota_status['input_limit']:,} "
                text += f"({quota_status['input_percent']:.1f}%)\n"
                text += f"  输出: {quota_status['output_used']:,}/{quota_status['output_limit']:,} "
                text += f"({quota_status['output_percent']:.1f}%)\n"
            
            # 构建按钮
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🟢 开启" if not ai_config['enabled'] else "🔴 关闭", 
                        callback_data=f"ai_toggle_{'off' if ai_config['enabled'] else 'on'}"
                    ),
                    InlineKeyboardButton("⚙️ 模式", callback_data="ai_mode_menu")
                ],
                [
                    InlineKeyboardButton("💪 强度", callback_data="ai_intensity_menu"),
                    InlineKeyboardButton("🏷️ 标签", callback_data="ai_tag_menu")
                ],
                [
                    InlineKeyboardButton("🔑 API密钥", callback_data="ai_api_key"),
                    InlineKeyboardButton("📊 额度详情", callback_data="ai_quota_detail")
                ],
                [
                    InlineKeyboardButton("🔙 返回", callback_data="main_menu")
                ]
            ]
            
            await message.reply(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"处理AI设置命令失败: {e}")
            await message.reply("❌ 处理失败")
    
    async def _handle_ai_status_command(self, message: Message):
        """处理AI状态命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 构建状态信息
            status_text = "🤖 AI文本改写状态\n\n"
            status_text += f"功能状态: {'🟢 已启用' if ai_config['enabled'] else '🔴 已禁用'}\n"
            status_text += f"处理模式: {self._get_mode_display(ai_config['mode'])}\n"
            status_text += f"改写强度: {self._get_intensity_display(ai_config['intensity'])}\n"
            
            # 获取额度状态
            quota_status = self._get_quota_status(user_id)
            if quota_status:
                status_text += f"\n📊 当前额度使用情况:\n"
                status_text += f"  输入tokens: {quota_status['input_used']:,}/{quota_status['input_limit']:,} "
                status_text += f"({quota_status['input_percent']:.1f}%)\n"
                status_text += f"  输出tokens: {quota_status['output_used']:,}/{quota_status['output_limit']:,} "
                status_text += f"({quota_status['output_percent']:.1f}%)\n"
                
                # 额度提醒
                if quota_status['input_percent'] > 90 or quota_status['output_percent'] > 90:
                    status_text += "\n⚠️ 注意: 额度即将用尽!\n"
                elif quota_status['input_percent'] > 70 or quota_status['output_percent'] > 70:
                    status_text += "\n💡 提示: 额度使用较多，请注意控制。\n"
            
            await message.reply(status_text)
            
        except Exception as e:
            logger.error(f"处理AI状态命令失败: {e}")
            await message.reply("❌ 处理失败")
    
    async def _handle_ai_preview_command(self, message: Message):
        """处理AI预览命令"""
        try:
            user_id = str(message.from_user.id)
            
            # 获取用户输入的文本
            text = message.text[len("/ai_preview"):].strip()
            
            if not text:
                help_text = (
                    "🤖 AI文本改写预览功能\n\n"
                    "使用方法:\n"
                    "/ai_preview <要预览的文本>\n\n"
                    "示例:\n"
                    "/ai_preview 今天天气很好，适合外出游玩。#天气 #美好时光\n\n"
                    "发送此命令后，系统将返回AI改写预览结果。"
                )
                await message.reply(help_text)
                return
            
            # 获取AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 检查AI功能是否启用
            if not ai_config.get('enabled', False):
                await message.reply("❌ AI文本改写功能未启用，请先使用 /ai_settings 命令启用功能。")
                return
            
            # 创建AI改写器进行预览
            from config import DEFAULT_USER_CONFIG
            config = DEFAULT_USER_CONFIG.copy()
            config['ai_rewrite_enabled'] = True
            config['ai_rewrite_mode'] = ai_config.get('mode', 'auto')
            config['ai_rewrite_intensity'] = ai_config.get('intensity', 'medium')
            
            # 创建获取当前API密钥的回调函数
            def get_current_api_key():
                api_keys = ai_config.get('api_keys', [])
                if not api_keys:
                    return ""
                current_index = ai_config.get('current_key_index', 0)
                current_index = current_index % len(api_keys)
                return api_keys[current_index]
            
            from ai_text_rewriter import AITextRewriter
            ai_rewriter = AITextRewriter(config, get_current_api_key)
            
            if not ai_rewriter.model:
                await message.reply("❌ AI模型初始化失败，请检查配置。")
                return
            
            # 执行预览
            preview_text, was_rewritten = await ai_rewriter.rewrite_text(text)
            
            # 构建回复
            if was_rewritten:
                response = "👀 AI文本改写预览结果:\n\n"
                response += "原文:\n"
                response += f"```\n{text}\n```\n\n"
                response += "改写预览:\n"
                response += f"```\n{preview_text}\n```\n\n"
                response += "💡 提示: 这只是预览效果，实际搬运时会应用相同规则。"
            else:
                response = "ℹ️ 文本无需改写或预览失败。\n\n"
                response += "原文本:\n"
                response += f"```\n{text}\n```"
            
            await message.reply(response)
            
        except Exception as e:
            logger.error(f"处理AI预览命令失败: {e}")
            await message.reply("❌ 处理失败，请稍后重试。")
    
    async def _handle_ai_callback(self, callback_query: CallbackQuery):
        """处理AI相关回调"""
        try:
            user_id = str(callback_query.from_user.id)
            data = callback_query.data
            
            if data == "ai_toggle_on":
                # 开启AI改写
                await self.data_manager.set_ai_rewrite_enabled(True)
                await callback_query.answer("✅ AI文本改写已开启")
            elif data == "ai_toggle_off":
                # 关闭AI改写
                await self.data_manager.set_ai_rewrite_enabled(False)
                await callback_query.answer("❌ AI文本改写已关闭")
            elif str(data).startswith("ai_set_mode_"):
                mode = str(data).replace("ai_set_mode_", "")
                await self.data_manager.set_ai_rewrite_mode(mode)
                await callback_query.answer(f"✅ 模式已设置为: {self._get_mode_display(str(mode))}")
            elif str(data).startswith("ai_set_intensity_"):
                intensity = str(data).replace("ai_set_intensity_", "")
                await self.data_manager.set_ai_rewrite_intensity(intensity)
                await callback_query.answer(f"✅ 强度已设置为: {self._get_intensity_display(str(intensity))}")
            elif str(data).startswith("ai_set_tag_"):
                tag_handling = str(data).replace("ai_set_tag_", "")
                await self.data_manager.set_ai_tag_handling(tag_handling)
                await callback_query.answer(f"✅ 标签处理已设置为: {self._get_tag_handling_display(str(tag_handling))}")
            elif data == "ai_quota_detail":
                # 显示额度详情
                await self._show_quota_detail(callback_query, user_id)
                
            elif data == "ai_api_key":
                # 显示API密钥设置
                await self._show_api_key_setting(callback_query, user_id)
                
            elif data == "ai_add_api_key":
                # 设置用户状态以便接收API密钥输入
                self.bot.user_states[user_id] = {
                    'step': 'waiting_for_api_key',
                    'data': {}
                }
                
                # 提示用户输入API密钥
                keyboard = [
                    [InlineKeyboardButton("🔙 返回", callback_data="ai_api_key")]
                ]
                
                await callback_query.message.edit_text(
                    "📝 请输入您的Gemini API密钥:\n\n"
                    "🔹 支持一次添加多个密钥，每行一个\n"
                    "🔹 密钥将以明文形式传输，请确保在安全环境下操作\n"
                    "🔹 输入完成后将自动保存并生效\n"
                    "🔹 输入 /cancel 可取消操作",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await callback_query.answer()
                
            elif data == "ai_test_key_rotation":
                # 测试API密钥轮询
                await self._test_api_key_rotation(callback_query, user_id)
                
            else:
                await callback_query.answer("未知操作")
                
        except Exception as e:
            logger.error(f"处理AI回调失败: {e}")
            await callback_query.answer("❌ 处理失败")
    
    async def _handle_api_key_input(self, message: Message):
        """处理用户输入的API密钥"""
        try:
            user_id = str(message.from_user.id)
            # 支持一次添加多个API密钥，按行分割
            api_keys_input = message.text.strip()
            new_api_keys = [key.strip() for key in api_keys_input.split('\n') if key.strip()]
            
            if not new_api_keys:
                await message.reply("❌ 未检测到有效的API密钥，请重新输入")
                return
            
            # 获取当前AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            existing_api_keys = ai_config.get('api_keys', [])
            
            # 添加新API密钥（避免重复添加）
            added_keys = []
            for key in new_api_keys:
                if key not in existing_api_keys:
                    existing_api_keys.append(key)
                    added_keys.append(key)
            
            if not added_keys:
                await message.reply("❌ 所有输入的API密钥已存在，无需重复添加")
                return
            
            # 更新API密钥配置
            await self._update_ai_config(user_id, {'api_keys': existing_api_keys})
            
            # 清除用户状态
            if user_id in self.bot.user_states:
                del self.bot.user_states[user_id]
            
            # 创建一个fake callback_query用于显示API密钥设置界面
            from pyrogram.types import CallbackQuery
            fake_callback = CallbackQuery(
                id="",
                from_user=message.from_user,
                chat_instance="",
                message=message
            )
            fake_callback.data = "ai_api_key"
            
            # 显示API密钥设置界面
            try:
                await self._show_api_key_setting(fake_callback, user_id)
                await message.delete()
            except Exception as e:
                logger.error(f"显示API密钥设置界面失败: {e}")
                # 如果无法编辑消息，发送新消息
                await message.reply("✅ API密钥已成功保存！")
            
            # 提示添加成功的密钥数量（如果前面的消息发送失败，则在这里提示）
            if added_keys:
                await message.reply(f"✅ 成功添加 {len(added_keys)} 个API密钥")
            
        except Exception as e:
            logger.error(f"处理API密钥输入失败: {e}")
            await message.reply("❌ 保存失败，请稍后重试")
    
    async def _refresh_ai_settings_menu(self, message: Message, user_id: str):
        """刷新AI设置菜单"""
        try:
            # 获取当前AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 构建设置界面
            text = "🤖 AI文本改写设置\n\n"
            text += f"开关状态: {'🟢 开启' if ai_config['enabled'] else '🔴 关闭'}\n"
            text += f"处理模式: {self._get_mode_display(ai_config['mode'])}\n"
            text += f"改写强度: {self._get_intensity_display(ai_config['intensity'])}\n"
            text += f"标签处理: {self._get_tag_handling_display(ai_config['tag_handling'])}\n"
            
            # 获取额度状态
            quota_status = self._get_quota_status(user_id)
            if quota_status:
                text += f"\n📊 额度状态:\n"
                text += f"  输入: {quota_status['input_used']:,}/{quota_status['input_limit']:,} "
                text += f"({quota_status['input_percent']:.1f}%)\n"
                text += f"  输出: {quota_status['output_used']:,}/{quota_status['output_limit']:,} "
                text += f"({quota_status['output_percent']:.1f}%)\n"
            
            # 构建按钮
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🟢 开启" if not ai_config['enabled'] else "🔴 关闭", 
                        callback_data=f"ai_toggle_{'off' if ai_config['enabled'] else 'on'}"
                    ),
                    InlineKeyboardButton("⚙️ 模式", callback_data="ai_mode_menu")
                ],
                [
                    InlineKeyboardButton("💪 强度", callback_data="ai_intensity_menu"),
                    InlineKeyboardButton("🏷️ 标签", callback_data="ai_tag_menu")
                ],
                [
                    InlineKeyboardButton("🔑 API密钥", callback_data="ai_api_key"),
                    InlineKeyboardButton("📊 额度详情", callback_data="ai_quota_detail")
                ],
                [
                    InlineKeyboardButton("🔙 返回", callback_data="main_menu")
                ]
            ]
            
            await message.edit_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"刷新AI设置菜单失败: {e}")
    
    async def _show_mode_menu(self, callback_query: CallbackQuery):
        """显示模式选择菜单"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 自动", callback_data="ai_set_mode_auto"),
                InlineKeyboardButton("⚡ 强制", callback_data="ai_set_mode_on")
            ],
            [
                InlineKeyboardButton("🔙 返回", callback_data="ai_settings")
            ]
        ]
        
        await callback_query.message.edit_text(
            "⚙️ 选择AI处理模式\n\n"
            "🔄 自动 - 有额度时改写，无额度时原文搬运\n"
            "⚡ 强制 - 必须改写(额度用尽时会失败)\n",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await callback_query.answer()
    
    async def _show_intensity_menu(self, callback_query: CallbackQuery):
        """显示强度选择菜单"""
        keyboard = [
            [
                InlineKeyboardButton("⚪ 轻微", callback_data="ai_set_intensity_light"),
                InlineKeyboardButton("⚫ 中等", callback_data="ai_set_intensity_medium")
            ],
            [
                InlineKeyboardButton("⚪ 强烈", callback_data="ai_set_intensity_heavy")
            ],
            [
                InlineKeyboardButton("🔙 返回", callback_data="ai_settings")
            ]
        ]
        
        await callback_query.message.edit_text(
            "💪 选择改写强度\n\n"
            "⚪ 轻微 - 最小化改动\n"
            "⚫ 中等 - 适度改写\n"
            "⚪ 强烈 - 大幅重写",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await callback_query.answer()
    
    async def _show_tag_menu(self, callback_query: CallbackQuery):
        """显示标签处理选择菜单"""
        keyboard = [
            [
                InlineKeyboardButton("🔖 优化", callback_data="ai_set_tag_optimize"),
                InlineKeyboardButton("🔄 替换", callback_data="ai_set_tag_replace")
            ],
            [
                InlineKeyboardButton("➕ 扩展", callback_data="ai_set_tag_extend"),
                InlineKeyboardButton("🔒 保留", callback_data="ai_set_tag_keep")
            ],
            [
                InlineKeyboardButton("🔙 返回", callback_data="ai_settings")
            ]
        ]
        
        await callback_query.message.edit_text(
            "🏷️ 选择标签处理方式\n\n"
            "🔖 优化 - 智能优化标签\n"
            "🔄 替换 - 替换为相关标签\n"
            "➕ 扩展 - 在原有基础上增加标签\n"
            "🔒 保留 - 保留原始标签",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await callback_query.answer()
    
    async def _show_quota_detail(self, callback_query: CallbackQuery, user_id: str):
        """显示额度详情"""
        try:
            # 获取当前API密钥
            current_api_key = await self._get_current_api_key(user_id)
            
            if not current_api_key:
                await callback_query.answer("❌ 未设置API密钥")
                return
            
            # 获取额度信息
            quota_status = self._get_quota_status(user_id)
            
            text = "📊 Gemini API 额度详情\n\n"
            text += f"🔤 请求次数:\n"
            text += f"  已使用: {quota_status['used']:,}\n"
            text += f"  总额度: {quota_status['limit']:,}\n"
            text += f"  剩余: {quota_status['remaining']:,}\n"
            text += f"  使用率: {quota_status['percent']:.1f}%\n\n"
            
            text += f"🔤 输入tokens:\n"
            text += f"  已使用: {quota_status['input_used']:,}\n"
            text += f"  总额度: {quota_status['input_limit']:,}\n"
            text += f"  剩余: {quota_status['input_remaining']:,}\n"
            text += f"  使用率: {quota_status['input_percent']:.1f}%\n\n"
            
            text += f"📥 输出tokens:\n"
            text += f"  已使用: {quota_status['output_used']:,}\n"
            text += f"  总额度: {quota_status['output_limit']:,}\n"
            text += f"  剩余: {quota_status['output_remaining']:,}\n"
            text += f"  使用率: {quota_status['output_percent']:.1f}%\n\n"
            
            # 显示API密钥信息
            displayed_key = f"{current_api_key[:8]}****{current_api_key[-4:]}" if len(current_api_key) > 12 else "****"
            text += f"🔑 当前密钥: {displayed_key}\n\n"
            
            text += "📌 额度说明:\n"
            text += "  • 每个API密钥每日限制1,000次调用\n"
            text += "  • RPM: 15 (每分钟请求)\n"
            text += "  • TPM: 250k (每分钟token)\n"
            text += "  • RPD: 1k (每日请求)\n\n"
            text += f"⏰ 重置时间: UTC+8 00:00\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 返回", callback_data="ai_settings")]
            ]
            
            # 检查callback_query是否有效
            if callback_query and callback_query.message:
                try:
                    await callback_query.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    await callback_query.answer()
                except Exception as edit_error:
                    # 处理消息未修改的错误
                    error_msg = str(edit_error)
                    if "MESSAGE_NOT_MODIFIED" in error_msg:
                        # 消息内容未改变，直接应答回调
                        await callback_query.answer()
                    elif "MESSAGE_ID_INVALID" in error_msg:
                        # 消息ID无效，尝试发送新消息
                        await callback_query.answer("正在重新加载界面...")
                        
                        # 尝试通过bot发送新消息
                        await self.bot.client.send_message(
                            chat_id=user_id,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        # 其他错误，重新抛出
                        raise edit_error
            else:
                # 如果callback_query无效，尝试通过bot发送新消息
                await self.bot.client.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
        except Exception as e:
            logger.error(f"显示额度详情失败: {e}")
            # 尝试通过其他方式通知用户
            try:
                if callback_query and hasattr(callback_query, 'answer') and callback_query.answer:
                    await callback_query.answer("❌ 显示失败")
                else:
                    # 如果callback_query.answer不可用，通过bot发送消息
                    await self.bot.client.send_message(
                        chat_id=user_id,
                        text="❌ 显示额度详情失败"
                    )
            except Exception as inner_e:
                logger.error(f"无法通知用户错误: {inner_e}")
    
    async def _show_api_key_setting(self, callback_query: CallbackQuery, user_id: str):
        """显示API密钥设置界面"""
        try:
            # 获取当前AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            api_keys = ai_config.get('api_keys', [])
            
            text = "🔐 Gemini API 密钥设置\n\n"
            
            if api_keys:
                text += f"已设置 {len(api_keys)} 个API密钥:\n"
                for i, key in enumerate(api_keys):
                    # 隙API密钥中间部分以保护隐私
                    displayed_key = f"{key[:8]}****{key[-4:]}" if len(key) > 12 else "****"
                    text += f"{i+1}. `{displayed_key}`\n"
            else:
                text += "未设置API密钥\n\n"
            
            text += "\n💡 获取密钥步骤:\n"
            text += "1. 访问 https://aistudio.google.com/\n"
            text += "2. 登录或注册Google账号\n"
            text += "3. 进入API密钥管理页面\n"
            text += "4. 创建新的API密钥\n"
            text += "5. 复制密钥并添加到下方\n\n"
            text += "📌 支持一次添加多个密钥，每行一个"
            
            keyboard = [
                [
                    InlineKeyboardButton("➕ 添加密钥", callback_data="ai_add_api_key")
                ]
            ]
            
            # 如果已有密钥，提供管理选项
            if api_keys:
                keyboard.insert(0, [InlineKeyboardButton("🔄 轮询测试", callback_data="ai_test_key_rotation")])
            
            keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="ai_settings")])
            
            # 检查callback_query是否有效
            if callback_query and callback_query.message:
                try:
                    await callback_query.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    if callback_query.answer:
                        await callback_query.answer()
                except Exception as edit_error:
                    # 处理消息未修改的错误
                    error_msg = str(edit_error)
                    if "MESSAGE_NOT_MODIFIED" in error_msg:
                        # 消息内容未改变，直接应答回调
                        if callback_query.answer:
                            await callback_query.answer()
                    elif "MESSAGE_ID_INVALID" in error_msg:
                        # 消息ID无效，尝试发送新消息
                        if callback_query.answer:
                            await callback_query.answer("正在重新加载界面...")
                        
                        # 尝试通过bot发送新消息
                        sent_message = await self.bot.client.send_message(
                            chat_id=user_id,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        # 如果需要，可以保存新消息的引用以供后续编辑
                    else:
                        # 其他错误，重新抛出
                        raise edit_error
            else:
                # 如果callback_query无效，尝试通过bot发送新消息
                sent_message = await self.bot.client.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
        except Exception as e:
            logger.error(f"显示API密钥设置失败: {e}")
            # 尝试通过其他方式通知用户
            try:
                if callback_query and hasattr(callback_query, 'answer') and callback_query.answer:
                    await callback_query.answer("❌ 显示失败")
                else:
                    # 如果callback_query.answer不可用，通过bot发送消息
                    await self.bot.client.send_message(
                        chat_id=user_id,
                        text="❌ 显示API密钥设置界面失败"
                    )
            except Exception as inner_e:
                logger.error(f"无法通知用户错误: {inner_e}")
    
    async def _update_ai_config(self, user_id: str, updates: Dict[str, Any]):
        """更新AI配置"""
        try:
            current_config = await self.data_manager.get_ai_rewrite_config(user_id)
            current_config.update(updates)
            
            # 构造完整的配置更新
            full_config = {
                'enabled': current_config['enabled'],
                'mode': current_config['mode'],
                'intensity': current_config['intensity'],
                'tag_handling': current_config['tag_handling']
            }
            
            # 如果有API密钥更新
            if 'api_keys' in updates:
                full_config['api_keys'] = updates['api_keys']
                
            # 如果有current_key_index更新
            if 'current_key_index' in updates:
                full_config['current_key_index'] = updates['current_key_index']
            
            await self.data_manager.set_ai_rewrite_config(user_id, full_config)
            
        except Exception as e:
            logger.error(f"更新AI配置失败: {e}")
            raise
    
    def _get_mode_display(self, mode: str) -> str:
        """获取模式显示文本"""
        modes = {
            'auto': '🔄 自动',
            'on': '⚡ 强制',
            'off': '📄 原文'
        }
        return modes.get(mode, mode)
    
    def _get_intensity_display(self, intensity: str) -> str:
        """获取强度显示文本"""
        intensities = {
            'light': '⚪ 轻微',
            'medium': '⚫ 中等',
            'heavy': '⚪ 强烈'
        }
        return intensities.get(intensity, intensity)
    
    def _get_tag_handling_display(self, tag_handling: str) -> str:
        """获取标签处理显示文本"""
        tag_handlers = {
            'optimize': '🔖 优化',
            'replace': '🔄 替换',
            'extend': '➕ 扩展',
            'keep': '🔒 保留'
        }
        return tag_handlers.get(tag_handling, tag_handling)
    
    def _get_quota_status(self, user_id: str) -> Dict[str, Any]:
        """获取额度状态"""
        try:
            # 从AI改写器获取实际的额度状态
            if (hasattr(self.bot, 'cloning_engine') and 
                self.bot.cloning_engine and 
                hasattr(self.bot.cloning_engine, 'ai_rewriter')):
                
                ai_rewriter = self.bot.cloning_engine.ai_rewriter
                if ai_rewriter:
                    quota_status = ai_rewriter.get_quota_status()
                    if quota_status:
                        # 根据规范，每个密钥每日限制1000次调用
                        return {
                            'used': quota_status['used'],
                            'limit': quota_status['limit'],
                            'remaining': quota_status['remaining'],
                            'percent': quota_status['percent'],
                            'input_used': quota_status['used'] * 1000,  # 估算输入tokens
                            'input_limit': 1000000,
                            'input_remaining': 1000000 - quota_status['used'] * 1000,
                            'input_percent': quota_status['percent'],
                            'output_used': quota_status['used'] * 200,  # 估算输出tokens
                            'output_limit': 200000,
                            'output_remaining': 200000 - quota_status['used'] * 200,
                            'output_percent': quota_status['percent']
                        }
            
            # 如果无法获取实际额度，返回默认值
            return {
                'used': 0,
                'limit': 1000,
                'remaining': 1000,
                'percent': 0,
                'input_used': 0,
                'input_limit': 1000000,
                'input_remaining': 1000000,
                'input_percent': 0,
                'output_used': 0,
                'output_limit': 200000,
                'output_remaining': 200000,
                'output_percent': 0
            }
        except Exception as e:
            logger.error(f"获取额度状态失败: {e}")
            # 返回默认值
            return {
                'used': 0,
                'limit': 1000,
                'remaining': 1000,
                'percent': 0,
                'input_used': 0,
                'input_limit': 1000000,
                'input_remaining': 1000000,
                'input_percent': 0,
                'output_used': 0,
                'output_limit': 200000,
                'output_remaining': 200000,
                'output_percent': 0
            }
    
    async def _get_current_api_key(self, user_id: str) -> str:
        """获取当前应该使用的API密钥"""
        try:
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            api_keys = ai_config.get('api_keys', [])
            
            if not api_keys:
                return ""
            
            current_index = ai_config.get('current_key_index', 0)
            # 确保索引在有效范围内
            current_index = current_index % len(api_keys)
            return api_keys[current_index]
        except Exception as e:
            logger.error(f"获取当前API密钥失败: {e}")
            return ""
    
    async def _rotate_to_next_api_key(self, user_id: str):
        """轮询到下一个API密钥"""
        try:
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            api_keys = ai_config.get('api_keys', [])
            
            if not api_keys or len(api_keys) <= 1:
                return  # 只有一个或没有密钥，无需轮询
            
            current_index = ai_config.get('current_key_index', 0)
            next_index = (current_index + 1) % len(api_keys)
            
            # 更新索引
            await self._update_ai_config(user_id, {'current_key_index': next_index})
            logger.info(f"API密钥轮询: 用户 {user_id} 从密钥 {current_index + 1} 切换到密钥 {next_index + 1}")
            
        except Exception as e:
            logger.error(f"轮询到下一个API密钥失败: {e}")
    
    async def _test_api_key_rotation(self, callback_query: CallbackQuery, user_id: str):
        """测试API密钥轮询"""
        try:
            # 获取当前AI配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            api_keys = ai_config.get('api_keys', [])
            
            if not api_keys:
                if callback_query and hasattr(callback_query, 'answer'):
                    await callback_query.answer("❌ 未设置API密钥")
                else:
                    await self.bot.client.send_message(
                        chat_id=user_id,
                        text="❌ 未设置API密钥"
                    )
                return
            
            # 获取当前索引
            current_index = ai_config.get('current_key_index', 0)
            
            # 轮询到下一个密钥
            next_index = (current_index + 1) % len(api_keys)
            
            # 更新配置
            await self._update_ai_config(user_id, {'current_key_index': next_index})
            
            # 显示结果
            displayed_key = f"{api_keys[next_index][:8]}****{api_keys[next_index][-4:]}" if len(api_keys[next_index]) > 12 else "****"
            
            # 刷新界面
            await self._show_api_key_setting(callback_query, user_id)
            
            # 显示切换结果
            if callback_query and hasattr(callback_query, 'answer'):
                await callback_query.answer(f"✅ 已切换到密钥 {next_index + 1}: {displayed_key}")
            else:
                await self.bot.client.send_message(
                    chat_id=user_id,
                    text=f"✅ 已切换到密钥 {next_index + 1}: {displayed_key}"
                )
            
        except Exception as e:
            logger.error(f"测试API密钥轮询失败: {e}")
            # 尝试通过其他方式通知用户
            try:
                if callback_query and hasattr(callback_query, 'answer') and callback_query.answer:
                    await callback_query.answer("❌ 测试失败")
                else:
                    # 如果callback_query.answer不可用，通过bot发送消息
                    await self.bot.client.send_message(
                        chat_id=user_id,
                        text="❌ 测试API密钥轮询失败"
                    )
            except Exception as inner_e:
                logger.error(f"无法通知用户错误: {inner_e}")
    # 集成到现有机器人的函数
def integrate_ai_rewrite_commands(bot_instance):
    """将AI文本改写命令集成到现有机器人"""
    try:
        # 创建集成实例
        integration = AIRewriteCommands(bot_instance)
        
        # 注册命令
        integration.register_commands()
        
        # 将集成实例添加到机器人
        bot_instance.ai_rewrite_commands = integration
        
        logger.info("✅ AI文本改写命令集成成功")
        return integration
        
    except Exception as e:
        logger.error(f"❌ AI文本改写命令集成失败: {e}")
        return None