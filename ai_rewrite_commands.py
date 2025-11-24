# ==================== AI文本改写命令处理器 ====================
"""
AI文本改写命令处理器
处理与AI文本改写功能相关的用户命令
"""

import logging
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
    
    def register_commands(self):
        """注册AI文本改写相关命令"""
        logger.info("📝 注册AI文本改写命令")
        
        @self.client.on_message(filters.command("ai_settings"))
        async def ai_settings_command(client, message: Message):
            await self._handle_ai_settings_command(message)
        
        @self.client.on_message(filters.command("ai_status"))
        async def ai_status_command(client, message: Message):
            await self._handle_ai_status_command(message)
        
        @self.client.on_message(filters.command("ai_preview"))
        async def ai_preview_command(client, message: Message):
            await self._handle_ai_preview_command(message)
        
        @self.client.on_callback_query(filters.regex(r"^ai_"))
        async def ai_callback_handler(client, callback_query: CallbackQuery):
            await self._handle_ai_callback(callback_query)
    
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
            quota_status = await self._get_quota_status(user_id)
            if quota_status:
                text += f"\n📊 额度状态:\n"
                text += f"  总计: {quota_status.get('total_used', 0):,}/{quota_status.get('total_limit', 5000):,} 次 "
                text += f"({quota_status.get('total_percent', 0):.1f}%)\n"
                text += f"  剩余: {quota_status.get('total_remaining', 5000):,} 次\n"
                text += f"  (5个密钥独立额度，每个1000次/天)\n"
            
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
                    InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")
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
            quota_status = await self._get_quota_status(user_id)
            if quota_status:
                status_text += f"\n📊 当前额度使用情况:\n"
                status_text += f"  总计: {quota_status.get('total_used', 0):,}/{quota_status.get('total_limit', 5000):,} 次 "
                status_text += f"({quota_status.get('total_percent', 0):.1f}%)\n"
                status_text += f"  剩余: {quota_status.get('total_remaining', 5000):,} 次\n"
                status_text += f"  (5个密钥独立额度，每个1000次/天)\n\n"
                
                # 显示每个密钥的额度
                if quota_status.get('keys'):
                    status_text += "📋 各密钥额度:\n"
                    for key_info in quota_status['keys']:
                        status_text += f"  密钥{key_info['key_index']}: {key_info['used']}/{key_info['limit']} "
                        status_text += f"({key_info['percent']:.1f}%)\n"
                
                # 额度提醒
                if quota_status.get('total_percent', 0) > 90:
                    status_text += "\n⚠️ 注意: 总额度即将用尽!\n"
                elif quota_status.get('total_percent', 0) > 70:
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
            config['gemini_api_key'] = ai_config.get('api_key', '')
            
            from ai_text_rewriter import AITextRewriter
            ai_rewriter = AITextRewriter(config)
            
            if not ai_rewriter.model:
                await message.reply("❌ AI模型初始化失败，请检查配置。")
                return
            
            # 执行预览
            preview_text, was_rewritten = await ai_rewriter.preview_rewrite(text)
            
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
            
            # 处理从主菜单进入的设置
            if data == "ai_settings":
                await callback_query.answer()
                # 创建一个临时Message对象来调用设置命令
                from pyrogram.types import Message
                temp_message = callback_query.message
                temp_message.from_user = callback_query.from_user
                await self._handle_ai_settings_command(temp_message)
                return
            
            if data == "ai_toggle_on":
                # 开启AI改写
                await self._update_ai_config(user_id, {'enabled': True})
                await callback_query.answer("✅ AI文本改写已开启")
                await self._refresh_ai_settings_menu(callback_query.message, user_id)
                
            elif data == "ai_toggle_off":
                # 关闭AI改写
                await self._update_ai_config(user_id, {'enabled': False})
                await callback_query.answer("❌ AI文本改写已关闭")
                await self._refresh_ai_settings_menu(callback_query.message, user_id)
                
            elif data == "ai_mode_menu":
                # 显示模式选择菜单
                await self._show_mode_menu(callback_query)
                
            elif data.startswith("ai_set_mode_"):
                # 设置模式
                mode = data.replace("ai_set_mode_", "")
                # 如果模式是off（原文模式），改为auto（自动模式）
                if mode == 'off':
                    mode = 'auto'
                await self._update_ai_config(user_id, {'mode': mode})
                await callback_query.answer(f"✅ 模式已设置为: {self._get_mode_display(mode)}")
                await self._refresh_ai_settings_menu(callback_query.message, user_id)
                
            elif data == "ai_intensity_menu":
                # 显示强度选择菜单
                await self._show_intensity_menu(callback_query)
                
            elif data.startswith("ai_set_intensity_"):
                # 设置强度
                intensity = data.replace("ai_set_intensity_", "")
                await self._update_ai_config(user_id, {'intensity': intensity})
                await callback_query.answer(f"✅ 强度已设置为: {self._get_intensity_display(intensity)}")
                await self._refresh_ai_settings_menu(callback_query.message, user_id)
                
            elif data == "ai_tag_menu":
                # 显示标签处理选择菜单
                await self._show_tag_menu(callback_query)
                
            elif data.startswith("ai_set_tag_"):
                # 设置标签处理方式
                tag_handling = data.replace("ai_set_tag_", "")
                await self._update_ai_config(user_id, {'tag_handling': tag_handling})
                await callback_query.answer(f"✅ 标签处理已设置为: {self._get_tag_handling_display(tag_handling)}")
                await self._refresh_ai_settings_menu(callback_query.message, user_id)
                
            elif data == "ai_quota_detail":
                # 显示额度详情
                await self._show_quota_detail(callback_query, user_id)
                
            elif data == "ai_api_key":
                # 显示API密钥信息
                await self._show_api_key_info(callback_query, user_id)
                
            else:
                await callback_query.answer("未知操作")
                
        except Exception as e:
            logger.error(f"处理AI回调失败: {e}")
            await callback_query.answer("❌ 处理失败")
    
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
            quota_status = await self._get_quota_status(user_id)
            if quota_status:
                text += f"\n📊 额度状态:\n"
                text += f"  总计: {quota_status.get('total_used', 0):,}/{quota_status.get('total_limit', 5000):,} 次 "
                text += f"({quota_status.get('total_percent', 0):.1f}%)\n"
                text += f"  剩余: {quota_status.get('total_remaining', 5000):,} 次\n"
                text += f"  (5个密钥独立额度，每个1000次/天)\n"
            
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
                    InlineKeyboardButton("🔙 返回主菜单", callback_data="show_main_menu")
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
            "⚡ 强制 - 必须改写(额度用尽时会失败)",
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
            quota_status = await self._get_quota_status(user_id)
            
            text = "📊 Gemini 2.5 Flash Lite 额度详情\n\n"
            text += "📈 每日额度限制（每个密钥）\n"
            text += "• RPD (每日请求数): 1,000 次/天\n"
            text += "• RPM (每分钟请求数): 15 次/分钟\n"
            text += "• TPM (每分钟tokens数): 250,000 tokens/分钟\n\n"
            
            if quota_status:
                text += f"📊 当前使用情况（总计）\n"
                text += f"• 今日已使用: {quota_status.get('total_used', 0):,} 次\n"
                text += f"• 今日剩余: {quota_status.get('total_remaining', 5000):,} 次\n"
                text += f"• 使用率: {quota_status.get('total_percent', 0):.1f}%\n\n"
                
                # 显示每个密钥的详细额度
                if quota_status.get('keys'):
                    text += "🔑 各密钥额度详情:\n"
                    for key_info in quota_status['keys']:
                        text += f"  密钥{key_info['key_index']}: "
                        text += f"{key_info['used']}/{key_info['limit']} 次 "
                        text += f"({key_info['percent']:.1f}%) "
                        text += f"剩余 {key_info['remaining']} 次\n"
                    text += "\n"
            
            text += "⏰ 重置时间: UTC+8 00:00\n"
            text += "💡 提示: 每个密钥额度独立，自动轮询使用。额度用尽时，自动模式会降级为原文搬运"
            
            keyboard = [
                [InlineKeyboardButton("🔙 返回", callback_data="ai_settings")]
            ]
            
            # 移除 Markdown 语法，使用纯文本
            text = text.replace("**", "")
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"显示额度详情失败: {e}")
            await callback_query.answer("❌ 显示失败")
    
    async def _show_api_key_info(self, callback_query: CallbackQuery, user_id: str):
        """显示API密钥信息"""
        try:
            from ai_text_rewriter import AITextRewriter
            from config import DEFAULT_USER_CONFIG
            
            # 获取用户配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 创建配置字典
            config = DEFAULT_USER_CONFIG.copy()
            config['ai_rewrite_enabled'] = ai_config.get('enabled', False)
            config['ai_rewrite_mode'] = ai_config.get('mode', 'auto')
            config['ai_rewrite_intensity'] = ai_config.get('intensity', 'medium')
            
            # 创建AI改写器实例以获取密钥信息
            ai_rewriter = AITextRewriter(config)
            
            text = "🔑 Gemini API 密钥信息\n\n"
            text += f"📊 已配置密钥数量: {len(ai_rewriter.api_keys)} 个\n\n"
            text += "🔄 使用方式: 轮询使用\n"
            text += "• 每次请求自动切换到下一个密钥\n"
            text += "• 如果当前密钥失败或额度用尽，自动尝试下一个\n"
            text += "• 每个密钥有独立的额度池（1000次/天）\n\n"
            text += "💡 优势:\n"
            text += "• 分散API调用压力\n"
            text += "• 提高系统稳定性\n"
            text += "• 单个密钥故障或额度用尽不影响使用\n"
            text += "• 总可用额度: 5000次/天（5个密钥 × 1000次）\n\n"
            text += "📝 当前密钥索引: " + str(ai_rewriter.current_key_index + 1) + f"/{len(ai_rewriter.api_keys)}\n"
            text += "✅ 所有密钥状态: 已初始化并可用"
            
            keyboard = [
                [InlineKeyboardButton("🔙 返回", callback_data="ai_settings")]
            ]
            
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"显示API密钥信息失败: {e}")
            await callback_query.answer("❌ 显示失败")
    
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
            if 'api_key' in updates:
                full_config['api_key'] = updates['api_key']
            
            await self.data_manager.set_ai_rewrite_config(user_id, full_config)
            
        except Exception as e:
            logger.error(f"更新AI配置失败: {e}")
            raise
    
    def _get_mode_display(self, mode: str) -> str:
        """获取模式显示文本"""
        modes = {
            'auto': '🔄 自动',
            'on': '⚡ 强制'
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
    
    async def _get_quota_status(self, user_id: str) -> Dict[str, Any]:
        """获取额度状态"""
        try:
            # 从AI改写器获取实际的额度状态
            from ai_text_rewriter import AITextRewriter
            from config import DEFAULT_USER_CONFIG
            
            # 获取用户配置
            ai_config = await self.data_manager.get_ai_rewrite_config(user_id)
            
            # 创建配置字典
            config = DEFAULT_USER_CONFIG.copy()
            config['ai_rewrite_enabled'] = ai_config.get('enabled', False)
            config['ai_rewrite_mode'] = ai_config.get('mode', 'auto')
            config['ai_rewrite_intensity'] = ai_config.get('intensity', 'medium')
            
            # 创建AI改写器实例以获取额度状态
            ai_rewriter = AITextRewriter(config)
            
            # 获取额度状态
            quota_status = ai_rewriter.get_quota_status()
            
            if quota_status:
                return {
                    'used': quota_status.get('used', 0),
                    'limit': quota_status.get('limit', 1000),
                    'remaining': quota_status.get('remaining', 1000),
                    'percent': quota_status.get('percent', 0.0)
                }
            else:
                return None
        except Exception as e:
            logger.error(f"获取额度状态失败: {e}")
            return None

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