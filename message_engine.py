# ==================== 消息处理引擎 ====================
"""
消息处理引擎
负责文本过滤、媒体处理、按钮过滤和内容增强功能
"""

import re
import logging
import random
from typing import Dict, List, Any, Optional, Tuple
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# 配置日志 - 显示详细状态信息
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageEngine:
    """消息处理引擎类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化消息处理引擎"""
        self.config = config
        self.message_counter = 0
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化正则表达式模式"""
        # HTTP链接模式
        self.http_pattern = re.compile(
            r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?',
            re.IGNORECASE
        )
        
        # 磁力链接模式
        self.magnet_pattern = re.compile(
            r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}.*',
            re.IGNORECASE
        )
        
        # Hashtag模式
        self.hashtag_pattern = re.compile(r'#\w+')
        
        # 用户名模式
        self.username_pattern = re.compile(r'@\w+')
    
    def _remove_links_with_context(self, text: str) -> str:
        """智能移除链接和包含超链接的文字"""
        if not text:
            return text
        
        # 查找所有链接
        links = list(self.http_pattern.finditer(text))
        if not links:
            return text
        
        # 从后往前处理，避免位置偏移
        links.reverse()
        
        for match in links:
            start, end = match.span()
            
            # 向前查找包含链接的文字（最多20个字符）
            context_start = max(0, start - 20)
            context_text = text[context_start:start]
            
            # 向后查找包含链接的文字（最多20个字符）
            context_end = min(len(text), end + 20)
            context_text_after = text[end:context_end]
            
            # 判断是否需要移除上下文
            should_remove_before = self._should_remove_context_before(context_text)
            should_remove_after = self._should_remove_context_after(context_text_after)
            
            # 计算实际需要移除的范围
            actual_start = start
            actual_end = end
            
            if should_remove_before:
                # 向前查找合适的断句点
                actual_start = self._find_sentence_boundary_before(text, start)
            
            if should_remove_after:
                # 向后查找合适的断句点
                actual_end = self._find_sentence_boundary_after(text, end)
            
            # 移除链接和上下文
            text = text[:actual_start] + text[actual_end:]
        
        return text
    
    def _should_remove_context_before(self, context: str) -> bool:
        """判断是否应该移除链接前的上下文"""
        if not context:
            return False
        
        # 如果前面是标点符号或空格，不需要移除
        if context[-1] in '.,!?;: \n\t':
            return False
        
        # 如果前面是完整的词，需要移除
        return True
    
    def _should_remove_context_after(self, context: str) -> bool:
        """判断是否应该移除链接后的上下文"""
        if not context:
            return False
        
        # 如果后面是标点符号或空格，不需要移除
        if context[0] in '.,!?;: \n\t':
            return False
        
        # 如果后面是完整的词，需要移除
        return True
    
    def _find_sentence_boundary_before(self, text: str, position: int) -> int:
        """向前查找句子边界"""
        if position <= 0:
            return 0
        
        # 查找最近的标点符号或换行
        for i in range(position - 1, -1, -1):
            if text[i] in '.,!?;:\n':
                return i + 1
        
        return 0
    
    def _find_sentence_boundary_after(self, text: str, position: int) -> int:
        """向后查找句子边界"""
        if position >= len(text):
            return len(text)
        
        # 查找最近的标点符号或换行
        for i in range(position, len(text)):
            if text[i] in '.,!?;:\n':
                return i + 1
        
        return len(text)
    
    def _remove_magnet_links_with_context(self, text: str) -> str:
        """智能移除磁力链接和包含磁力链接的文字"""
        if not text:
            return text
        
        # 查找所有磁力链接
        links = list(self.magnet_pattern.finditer(text))
        if not links:
            return text
        
        # 从后往前处理，避免位置偏移
        links.reverse()
        
        for match in links:
            start, end = match.span()
            
            # 向前查找包含链接的文字（最多20个字符）
            context_start = max(0, start - 20)
            context_text = text[context_start:start]
            
            # 向后查找包含链接的文字（最多20个字符）
            context_end = min(len(text), end + 20)
            context_text_after = text[end:context_end]
            
            # 判断是否需要移除上下文
            should_remove_before = self._should_remove_context_before(context_text)
            should_remove_after = self._should_remove_context_after(context_text_after)
            
            # 计算实际需要移除的范围
            actual_start = start
            actual_end = end
            
            if should_remove_before:
                # 向前查找合适的断句点
                actual_start = self._find_sentence_boundary_before(text, start)
            
            if should_remove_after:
                # 向后查找合适的断句点
                actual_end = self._find_sentence_boundary_after(text, end)
            
            # 移除链接和上下文
            text = text[:actual_start] + text[actual_end:]
        
        return text
    
    def _remove_all_links_with_context(self, text: str) -> str:
        """智能移除所有类型链接和包含链接的文字"""
        if not text:
            return text
        
        # 先处理HTTP链接
        text = self._remove_links_with_context(text)
        
        # 再处理磁力链接
        text = self._remove_magnet_links_with_context(text)
        
        return text
    
    def should_process_message(self, message: Message, config: Optional[Dict[str, Any]] = None) -> bool:
        """判断是否应该处理该消息"""
        # 使用指定的配置或全局配置
        effective_config = config or self.config
        
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        
        # 检查消息类型（包括caption和媒体）
        has_text = bool(message.text and message.text.strip())
        has_caption = bool(message.caption and message.caption.strip())
        has_media = bool(message.media)
        
        # 添加更详细的调试信息
        logger.info(f"🔍 消息类型检查: media={has_media}, text={has_text}, caption={has_caption}")
        logger.info(f"🔍 消息原始属性: message.text={message.text is not None}, message.caption={message.caption is not None}, message.media={message.media is not None}")
        logger.info(f"🔍 消息类型: {type(message).__name__}, message_id={message.id}")
        
        # 显示消息内容（限制长度避免日志过长）
        text_preview = (message.text or '')[:100] + ('...' if len(message.text or '') > 100 else '')
        caption_preview = (message.caption or '')[:100] + ('...' if len(message.caption or '') > 100 else '')
        logger.info(f"🔍 消息内容: text='{text_preview}', caption='{caption_preview}'")
        
        # 检查是否是特殊消息类型
        if hasattr(message, 'service') and message.service:
            logger.info(f"🔍 检测到服务消息: {message.service}")
        if hasattr(message, 'empty') and message.empty:
            logger.info(f"🔍 检测到空消息")
        
        # 如果消息没有任何内容，跳过处理
        if not has_text and not has_caption and not has_media:
            logger.warning("❌ 消息没有文本内容、caption和媒体，跳过处理")
            return False
        
        # 如果是媒体消息，即使没有文本也应该处理
        if has_media:
            logger.info("✅ 消息包含媒体内容，继续处理")
            return True
        
        # 检查是否被过滤
        if effective_config.get('content_removal', False):
            content_removal_mode = effective_config.get('content_removal_mode', 'text_only')
            logger.info(f"🔍 内容移除模式: {content_removal_mode}")
            
            if content_removal_mode == 'text_only':
                # 仅移除纯文本：如果消息有媒体内容，则不应该跳过
                if message.media:
                    logger.info("✅ 消息有媒体内容，不跳过（仅移除纯文本模式）")
                    pass  # 继续处理
                else:
                    # 即使是纯文本消息，也应该处理，让后续的过滤逻辑决定是否跳过
                    logger.info("✅ 纯文本消息，继续处理（让过滤逻辑决定）")
                    pass  # 继续处理
            elif content_removal_mode == 'all_content':
                # 移除所有包含文本的信息：跳过所有消息
                logger.warning("❌ 移除所有内容模式，跳过处理")
                return False
            else:
                logger.warning(f"❌ 未知的内容移除模式: {content_removal_mode}，跳过处理")
                return False
        
        # 对于媒体组消息，即使没有文本也应该继续处理
        if message.media:
            logger.info("✅ 媒体消息通过过滤检查，继续处理")
            return True
        
        logger.info("✅ 消息通过类型检查，继续处理")
        return True
    
    def process_text(self, text: str, config: Optional[Dict[str, Any]] = None, message_type: str = "text") -> Tuple[str, bool]:
        """处理文本内容"""
        if not text:
            return "", False
        
        # 使用指定的配置或全局配置
        effective_config = config or self.config
        
        original_text = text
        processed_text = text
        modified = False
        
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 开始处理文本: '{text[:100]}...' (长度: {len(text)})")
        logger.info(f"🔍 过滤配置: keywords={effective_config.get('filter_keywords', [])}, links_removal={effective_config.get('remove_links', False)}")
        
        # 关键字过滤
        if effective_config.get('filter_keywords'):
            logger.info(f"🔍 检查关键字过滤: {effective_config['filter_keywords']}")
            for keyword in effective_config['filter_keywords']:
                if keyword.lower() in processed_text.lower():
                    logger.info(f"❌ 发现关键字: {keyword}，移除整条消息")
                    return "", True  # 完全移除消息
            logger.info("✅ 关键字过滤检查通过")
        else:
            logger.info("✅ 关键字过滤未启用")
        
        # 敏感词替换
        if effective_config.get('replacement_words'):
            for old_word, new_word in effective_config['replacement_words'].items():
                if old_word.lower() in processed_text.lower():
                    processed_text = re.sub(
                        re.escape(old_word), 
                        new_word, 
                        processed_text, 
                        flags=re.IGNORECASE
                    )
                    modified = True
        
        # 链接处理
        if effective_config.get('remove_links', False):
            logger.info(f"🔍 检查链接过滤: mode={effective_config.get('remove_links_mode')}")
            if effective_config.get('remove_links_mode') == 'remove_message':
                # 移除整条消息
                if self.http_pattern.search(processed_text):
                    logger.info("❌ 发现HTTP链接，移除整条消息")
                    return "", True
                logger.info("✅ 链接过滤检查通过")
            else:
                # 移除链接和包含超链接的文字
                logger.info("🔧 智能移除链接和上下文")
                processed_text = self._remove_links_with_context(processed_text)
                modified = True
                logger.info(f"🔧 链接移除后文本: '{processed_text[:100]}...' (长度: {len(processed_text)})")
        else:
            logger.info("✅ 链接过滤未启用")
        
        # 磁力链接处理
        if effective_config.get('remove_magnet_links', False):
            if effective_config.get('remove_links_mode') == 'remove_message':
                if self.magnet_pattern.search(processed_text):
                    logger.info("发现磁力链接，移除整条消息")
                    return "", True
            else:
                processed_text = self._remove_magnet_links_with_context(processed_text)
                modified = True
        
        # 移除所有链接
        if effective_config.get('remove_all_links', False):
            if effective_config.get('remove_links_mode') == 'remove_message':
                if (self.http_pattern.search(processed_text) or 
                    self.magnet_pattern.search(processed_text)):
                    logger.info("发现链接，移除整条消息")
                    return "", True
            else:
                # 使用智能移除方法处理所有类型的链接
                processed_text = self._remove_all_links_with_context(processed_text)
                modified = True
        
        # Hashtag处理
        if effective_config.get('remove_hashtags', False):
            processed_text = self.hashtag_pattern.sub('', processed_text)
            modified = True
        
        # 用户名处理
        if effective_config.get('remove_usernames', False):
            processed_text = self.username_pattern.sub('', processed_text)
            modified = True
        
        # 清理多余空白，但保留换行符
        if modified:
            # 保留换行符，只清理多余的空格和制表符
            processed_text = re.sub(r'[ \t]+', ' ', processed_text)  # 只替换空格和制表符
            processed_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', processed_text)  # 最多保留两个连续换行
            processed_text = processed_text.strip()
        
        # 添加最终调试日志
        logger.info(f"🔍 文本处理完成: '{processed_text[:100]}...' (长度: {len(processed_text)}, 修改: {modified})")
        
        return processed_text, modified
    
    def should_add_tail_text(self, message_type: str = "text") -> bool:
        """判断是否应该添加文本小尾巴"""
        frequency = self.config.get('tail_frequency', 'always')
        
        if frequency == 'always':
            return True
        elif frequency == 'interval':
            interval = self.config.get('tail_interval', 5)
            return (self.message_counter % interval) == 0
        elif frequency == 'random':
            probability = self.config.get('tail_probability', 0.3)
            return random.random() < probability
        
        return False
    
    def should_add_buttons(self, message_type: str = "text") -> bool:
        """判断是否应该添加按钮"""
        frequency = self.config.get('button_frequency', 'always')
        
        if frequency == 'always':
            return True
        elif frequency == 'interval':
            interval = self.config.get('button_interval', 5)
            return (self.message_counter % interval) == 0
        elif frequency == 'random':
            probability = self.config.get('button_probability', 0.3)
            return random.random() < probability
        
        return False
    
    def add_tail_text(self, text: str) -> str:
        """添加文本小尾巴"""
        tail_text = self.config.get('tail_text', '').strip()
        if not tail_text:
            return text
        
        if text:
            return f"{text}\n\n{tail_text}"
        else:
            return tail_text
    
    def add_additional_buttons(self, original_buttons: Optional[InlineKeyboardMarkup] = None, config: Optional[Dict[str, Any]] = None) -> Optional[InlineKeyboardMarkup]:
        """添加附加按钮"""
        # 使用指定的配置或全局配置
        effective_config = config or self.config
        
        additional_buttons = effective_config.get('additional_buttons', [])
        if not additional_buttons:
            return original_buttons
        
        # 检查是否应该添加按钮（频率控制）
        if not self._should_add_additional_buttons(effective_config):
            return original_buttons
        
        # 转换附加按钮配置为按钮对象
        new_buttons = []
        for button_config in additional_buttons:
            if isinstance(button_config, dict):
                text = button_config.get('text', '')
                url = button_config.get('url', '')
                if text and url:
                    new_buttons.append([InlineKeyboardButton(text, url=url)])
        
        # 合并原有按钮和附加按钮
        if original_buttons and original_buttons.inline_keyboard:
            combined_buttons = original_buttons.inline_keyboard + new_buttons
        else:
            combined_buttons = new_buttons
        
        return InlineKeyboardMarkup(combined_buttons)
    
    def _should_add_additional_buttons(self, config: Dict[str, Any]) -> bool:
        """检查是否应该添加附加按钮（频率控制）"""
        # 检查频率设置（支持数字百分比）
        frequency = config.get('button_frequency', 100)
        
        # 如果是数字，按百分比处理
        if isinstance(frequency, (int, float)):
            if frequency >= 100:
                return True
            elif frequency <= 0:
                return False
            else:
                # 按百分比概率添加
                import random
                return random.random() < (frequency / 100.0)
        
        # 兼容旧的文本模式
        if frequency == 'always':
            return True
        elif frequency == 'interval':
            # 间隔添加，每N条消息添加一次
            interval = config.get('button_interval', 5)
            return self.message_counter % interval == 0
        elif frequency == 'random':
            # 随机添加，50%概率
            import random
            return random.random() < 0.5
        
        return False
    
    def filter_buttons(self, buttons: InlineKeyboardMarkup, config: Optional[Dict[str, Any]] = None) -> InlineKeyboardMarkup:
        """过滤按钮"""
        # 使用指定的配置或全局配置
        effective_config = config or self.config
        
        if not effective_config.get('filter_buttons', False):
            return buttons
        
        if not buttons or not buttons.inline_keyboard:
            return buttons
        
        filter_mode = effective_config.get('button_filter_mode', 'remove_buttons_only')
        
        # 兼容新的配置模式
        if filter_mode in ['remove_all', 'remove_buttons_only']:
            # 移除所有按钮
            return InlineKeyboardMarkup([])
        
        elif filter_mode == 'remove_message':
            # 如果是移除整条消息模式，这里仍然移除按钮，消息的移除在process_message中处理
            return InlineKeyboardMarkup([])
        
        elif filter_mode == 'keep_safe':
            # 保留安全按钮（需要定义安全按钮列表）
            safe_buttons = []
            for row in buttons.inline_keyboard:
                safe_row = []
                for button in row:
                    # 这里可以定义安全按钮的判断逻辑
                    if self._is_safe_button(button):
                        safe_row.append(button)
                if safe_row:
                    safe_buttons.append(safe_row)
            return InlineKeyboardMarkup(safe_buttons)
        
        elif filter_mode == 'custom':
            # 自定义过滤逻辑
            return self._custom_button_filter(buttons)
        
        return buttons
    
    def _is_safe_button(self, button: InlineKeyboardButton) -> bool:
        """判断按钮是否安全"""
        # 这里可以定义安全按钮的判断逻辑
        # 例如：只保留特定文本的按钮
        safe_texts = ['返回', '确认', '取消', '帮助']
        return any(safe_text in button.text for safe_text in safe_texts)
    
    def _custom_button_filter(self, buttons: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
        """自定义按钮过滤"""
        # 这里可以实现自定义的按钮过滤逻辑
        # 例如：根据按钮文本、URL等进行过滤
        return buttons
    
    def process_message(self, message: Message, channel_config: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
        """处理完整消息"""
        self.message_counter += 1
        
        # 使用频道组配置或全局配置
        effective_config = channel_config or self.config
        
        # 检查是否应该处理
        if not self.should_process_message(message, effective_config):
            return {}, False
        
        # 处理文本（包括caption）
        text = message.text or message.caption or ""
        
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 开始处理消息: text='{message.text or ''}', caption='{message.caption or ''}', 合并后='{text[:100]}...'")
        
        processed_text, text_modified = self.process_text(text, effective_config)
        
        # 如果文本被完全移除，跳过该消息
        if processed_text == "" and text_modified:
            logger.warning("❌ 文本被完全移除，跳过消息")
            return {}, True
        
        logger.info(f"🔍 文本处理完成: processed='{processed_text[:100]}...', 修改: {text_modified}")
        logger.info(f"🔍 消息处理: text='{message.text or ''}', caption='{message.caption or ''}', processed='{processed_text[:100]}...'")
        
        # 检查按钮移除模式
        original_buttons = message.reply_markup
        
        # 如果设置为移除整条消息且消息包含按钮，则跳过该消息
        if (effective_config.get('filter_buttons', False) and 
            effective_config.get('button_filter_mode') == 'remove_message' and 
            original_buttons and original_buttons.inline_keyboard):
            logger.info("❌ 消息包含按钮且设置为移除整条消息，跳过该消息")
            return {}, True
        
        # 处理按钮
        filtered_buttons = self.filter_buttons(original_buttons, effective_config)
        
        # 添加文本小尾巴
        logger.info(f"🔍 检查小尾巴添加: tail_text='{effective_config.get('tail_text', '')}', frequency={effective_config.get('tail_frequency', 'always')}")
        
        # 添加详细的调试信息
        should_add = self._should_add_tail_text(effective_config)
        logger.info(f"🔍 小尾巴添加决策: should_add={should_add}")
        
        if should_add:
            logger.info("✅ 添加小尾巴")
            processed_text = self._add_tail_text(processed_text, effective_config)
            logger.info(f"🔍 添加小尾巴后: '{processed_text[:100]}...'")
        else:
            logger.info("❌ 不添加小尾巴")
            logger.info(f"🔍 小尾巴添加被拒绝，原因可能是:")
            logger.info(f"  • tail_text为空: {not effective_config.get('tail_text', '').strip()}")
            logger.info(f"  • frequency设置: {effective_config.get('tail_frequency', 'always')}")
            logger.info(f"  • 随机数检查失败")
        
        # 检查并截断过长的文本以防止MEDIA_CAPTION_TOO_LONG错误
        max_text_length = 4096  # Telegram消息文本最大长度
        if len(processed_text) > max_text_length:
            logger.warning(f"⚠️ 文本过长 ({len(processed_text)} > {max_text_length})，进行截断")
            processed_text = processed_text[:max_text_length-3] + "..."
            logger.info(f"🔧 文本截断后长度: {len(processed_text)}")
        
        # 添加附加按钮
        final_buttons = self.add_additional_buttons(filtered_buttons, effective_config)
        
        # 构建处理结果
        result = {
            'text': processed_text,
            'buttons': final_buttons,
            'original_text': text,
            'text_modified': text_modified,
            'buttons_modified': filtered_buttons != original_buttons,
            'tail_added': self._should_add_tail_text(effective_config),
            'additional_buttons_added': bool(effective_config.get('additional_buttons')),
            'original_message': message  # 添加原始消息对象，用于转发模式
        }
        
        return result, False
    
    def process_media_group(self, messages: List[Message], channel_config: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
        """处理媒体组消息"""
        self.message_counter += 1
        
        if not messages:
            return {}, False
        
        # 使用频道组配置或全局配置
        effective_config = channel_config or self.config
        
        # 获取并合并所有caption
        all_captions = []
        for msg in messages:
            if msg.caption and msg.caption.strip():
                all_captions.append(msg.caption.strip())
        
        # 合并caption
        if all_captions:
            if len(all_captions) == 1:
                # 只有一个caption，直接使用
                caption = all_captions[0]
            else:
                # 多个caption，合并它们
                caption = "\n\n".join([f"📱 {i+1}. {cap}" for i, cap in enumerate(all_captions)])
        else:
            caption = ""
        
        # 处理caption
        processed_caption, text_modified = self.process_text(caption, effective_config)
        
        # 如果caption被完全移除，保持为空（不添加默认标签）
        # 用户不希望自动添加媒体组标签
        if processed_caption == "" and text_modified:
            processed_caption = ""  # 保持为空
        
        # 添加文本小尾巴
        logger.info(f"🔍 检查小尾巴添加: tail_text='{effective_config.get('tail_text', '')}', frequency={effective_config.get('tail_frequency', 'always')}")
        
        # 添加详细的调试信息
        should_add = self._should_add_tail_text(effective_config)
        logger.info(f"🔍 小尾巴添加决策: should_add={should_add}")
        
        if should_add:
            logger.info("✅ 添加小尾巴")
            processed_caption = self._add_tail_text(processed_caption, effective_config)
            logger.info(f"🔍 添加小尾巴后: '{processed_caption[:100]}...'")
        else:
            logger.info("❌ 不添加小尾巴")
            logger.info(f"🔍 小尾巴添加被拒绝，原因可能是:")
        
        # 检查并截断过长的caption以防止MEDIA_CAPTION_TOO_LONG错误
        max_caption_length = 1024  # Telegram媒体caption最大长度
        if len(processed_caption) > max_caption_length:
            logger.warning(f"⚠️ Caption过长 ({len(processed_caption)} > {max_caption_length})，进行截断")
            processed_caption = processed_caption[:max_caption_length-3] + "..."
            logger.info(f"🔧 Caption截断后长度: {len(processed_caption)}")
            logger.info(f"  • tail_text为空: {not effective_config.get('tail_text', '').strip()}")
            logger.info(f"  • frequency设置: {effective_config.get('tail_frequency', 'always')}")
            logger.info(f"  • 随机数检查失败")
        
        # 处理按钮（使用第一条消息的按钮）
        original_buttons = messages[0].reply_markup if messages else None
        filtered_buttons = self.filter_buttons(original_buttons, effective_config)
        final_buttons = self.add_additional_buttons(filtered_buttons, effective_config)
        
        # 构建处理结果
        result = {
            'caption': processed_caption,
            'buttons': final_buttons,
            'media_count': len(messages),
            'original_caption': caption,
            'text_modified': text_modified,
            'buttons_modified': filtered_buttons != original_buttons,
            'tail_added': self._should_add_tail_text(effective_config),
            'additional_buttons_added': bool(effective_config.get('additional_buttons'))
        }
        
        return result, False
    
    def _should_add_tail_text(self, config: Dict[str, Any]) -> bool:
        """检查是否应该添加小尾巴文本（使用指定配置）"""
        tail_text = config.get('tail_text', '').strip()
        if not tail_text:
            return False
        
        # 检查频率设置（支持数字百分比）
        frequency = config.get('tail_frequency', 100)
        
        # 如果是数字，按百分比处理
        if isinstance(frequency, (int, float)):
            # 确保频率值在有效范围内
            frequency = float(frequency)
            if frequency >= 100.0:
                return True
            elif frequency <= 0.0:
                return False
            else:
                # 按百分比概率添加
                import random
                # 使用更精确的随机数生成
                random_value = random.random()
                should_add = random_value < (frequency / 100.0)
                logger.debug(f"🔍 小尾巴频率检查: frequency={frequency}%, random_value={random_value:.3f}, should_add={should_add}")
                return should_add
        
        # 兼容旧的文本模式
        if frequency == 'always':
            return True
        elif frequency == 'interval':
            # 间隔添加，每N条消息添加一次
            interval = config.get('tail_interval', 5)
            return self.message_counter % interval == 0
        elif frequency == 'random':
            # 随机添加，50%概率
            import random
            return random.random() < 0.5
        
        return False
    
    def _add_tail_text(self, text: str, config: Dict[str, Any]) -> str:
        """添加小尾巴文本（使用指定配置）"""
        tail_text = config.get('tail_text', '').strip()
        if not tail_text:
            return text
        
        position = config.get('tail_position', 'end')
        
        if position == 'start':
            return f"{tail_text}\n\n{text}"
        else:  # end
            return f"{text}\n\n{tail_text}"
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return {
            'total_messages_processed': self.message_counter,
            'tail_text': self.config.get('tail_text', ''),
            'tail_frequency': self.config.get('tail_frequency', 'always'),
            'button_frequency': self.config.get('button_frequency', 'always'),
            'filter_keywords_count': len(self.config.get('filter_keywords', [])),
            'replacement_words_count': len(self.config.get('replacement_words', {})),
            'additional_buttons_count': len(self.config.get('additional_buttons', []))
        }

# ==================== 导出函数 ====================
def create_message_engine(config: Dict[str, Any]) -> MessageEngine:
    """创建消息处理引擎实例"""
    return MessageEngine(config)

__all__ = [
    "MessageEngine", "create_message_engine"
]


