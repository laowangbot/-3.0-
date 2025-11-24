    async def _handle_text_messages(self, client, message: Message):
        """处理文本消息"""
        try:
            # 只处理来自私聊的消息
            if not message.chat or message.chat.type != "private":
                return
            
            user_id = str(message.from_user.id)
            
            # 检查用户是否在等待输入API密钥
            if (user_id in self.user_states and 
                self.user_states[user_id].get('step') == 'waiting_for_api_key'):
                # 处理AI API密钥输入
                try:
                    from ai_rewrite_commands import AIRewriteCommands
                    ai_commands = AIRewriteCommands(self)
                    await ai_commands._handle_api_key_input(message)
                except Exception as e:
                    logger.error(f"处理AI API密钥输入失败: {e}")
                    await message.reply("❌ 处理失败，请稍后重试")
                return
                
            # 处理用户状态消息
            elif user_id in self.user_states:
                state = self.user_states[user_id]
                step = state.get('step', '')
                
                # 处理各种等待状态
                if step == 'waiting_for_source_channel':
                    await self._handle_source_channel_input(message)
                elif step == 'waiting_for_target_channel':
                    await self._handle_target_channel_input(message)
                elif step == 'waiting_for_keywords':
                    await self._handle_keywords_input(message)
                elif step == 'waiting_for_replacements':
                    await self._handle_replacements_input(message)
                elif step == 'waiting_for_tail_text':
                    await self._handle_tail_text_input(message)
                elif step == 'waiting_for_buttons':
                    await self._handle_buttons_input(message)
                elif step == 'waiting_for_comments_count':
                    await self._handle_comments_count_input(message)
                elif step == 'waiting_for_comment_limit':
                    await self._handle_comment_limit_input(message)
                elif step == 'waiting_for_admin_comment_limit':
                    await self._handle_admin_comment_limit_input(message)
                elif step.startswith('edit_source:'):
                    await self._handle_source_channel_input(message)
                elif step.startswith('edit_target:'):
                    await self._handle_target_channel_input(message)
                elif step.startswith('edit_source_by_id:'):
                    await self._handle_source_channel_id_input(message)
                elif step.startswith('edit_target_by_id:'):
                    await self._handle_target_channel_id_input(message)
                elif step == 'waiting_for_channel_keywords':
                    await self._handle_channel_filter_keywords_input(message)
                elif step == 'waiting_admin_keyword':
                    await self._handle_admin_keyword_input(message)
                elif step == 'waiting_admin_tail_text':
                    await self._handle_admin_tail_text_input(message)
                elif step == 'waiting_admin_buttons':
                    await self._handle_admin_buttons_input(message)
                elif step == 'waiting_clone_test_single_source':
                    await self._handle_clone_test_single_source_input(message)
                elif step == 'waiting_clone_test_discussion_username':
                    await self._handle_clone_test_discussion_username_input(message)
                elif step == 'waiting_for_discussion_username':
                    await self._handle_discussion_username_input_message(message)
                elif step == 'waiting_admin_replacement':
                    await self._handle_admin_replacement_input(message)
                elif step == 'waiting_for_channel_id':
                    await self._handle_channel_id_input(message)
                elif step == 'waiting_for_channel_replacements':
                    await self._handle_channel_replacement_words_input(message)
                elif step == 'waiting_for_cloning_info':
                    await self._handle_cloning_info_input(message)
                elif step == 'creating_monitoring_task':
                    await self._handle_monitoring_task_input(message)
                elif step == 'waiting_for_api_key':
                    # 处理AI API密钥输入
                    try:
                        from ai_rewrite_commands import AIRewriteCommands
                        ai_commands = AIRewriteCommands(self)
                        await ai_commands._handle_api_key_input(message)
                    except Exception as e:
                        logger.error(f"处理AI API密钥输入失败: {e}")
                        await message.reply("❌ 处理失败，请稍后重试")
                else:
                    # 未知状态，清除用户状态
                    logger.warning(f"未知用户状态: {step}")
                    del self.user_states[user_id]
                    await message.reply("❌ 状态错误，请重新开始操作")
                    
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            # 不向用户发送错误消息，避免刷屏

            
            # 显示成功消息
            pair_index = state.get('pair_index', 0) if 'state' in locals() else 0
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
            logger.error(f"处理文本消息失败: {e}")
            # 不向用户发送错误消息，避免刷屏