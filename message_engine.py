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

# 导入AI文本改写模块
try:
    from ai_text_rewriter import create_ai_rewriter
    AI_REWRITER_AVAILABLE = True
except ImportError:
    AI_REWRITER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("AI文本改写模块不可用，请检查ai_text_rewriter.py文件")

# 导入增强过滤功能
# 配置日志 - 使用优化的日志配置
from log_config import get_logger
logger = get_logger(__name__)

try:
    from enhanced_link_filter import enhanced_link_filter
    ENHANCED_FILTER_AVAILABLE = True
except ImportError:
    ENHANCED_FILTER_AVAILABLE = False
    logger.warning("增强过滤功能不可用，请检查enhanced_link_filter.py文件")

class MessageEngine:
    """消息处理引擎类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化消息处理引擎"""
        self.config = config
        self.message_counter = 0
        self._init_patterns()
        
        # 初始化AI文本改写器
        self.ai_rewriter = None
        if AI_REWRITER_AVAILABLE and config.get('ai_rewrite_enabled', False):
            try:
                self.ai_rewriter = create_ai_rewriter(config)
                logger.info("✅ AI文本改写器初始化成功")
            except Exception as e:
                logger.error(f"❌ AI文本改写器初始化失败: {e}")
    
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
    
    def _safe_encode_text(self, text: str) -> str:
        """安全编码文本，处理UTF-16编码错误"""
        if not text or not isinstance(text, str):
            return text
        
        try:
            # 尝试正常处理
            return text
        except UnicodeDecodeError:
            try:
                # 尝试UTF-8编码
                return text.encode('utf-8', errors='ignore').decode('utf-8')
            except:
                # 最后尝试ASCII编码
                return text.encode('ascii', errors='ignore').decode('ascii')
        except Exception as e:
            logger.warning(f"文本编码处理失败: {e}")
            # 返回安全的文本
            return ''.join(char for char in text if ord(char) < 128)
    
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
    
    def _is_blank_message(self, message: Message) -> bool:
        """智能检测空白消息"""
        logger = logging.getLogger(__name__)
        
        # 检查消息是否为空
        if hasattr(message, 'empty') and message.empty:
            logger.debug("🔍 检测到空消息属性")
            return True
        
        # 检查是否是服务消息
        if hasattr(message, 'service') and message.service:
            logger.debug("🔍 检测到服务消息")
            return True
        
        # 检查文本内容
        text_content = message.text
        caption_content = message.caption
        has_media = bool(message.media)
        
        # 如果没有媒体，且文本内容为空，则认为是空白消息
        if not has_media and (text_content is None or text_content == ""):
            logger.debug("🔍 检测到无媒体的空文本消息")
            return True
        
        # 检查文本内容是否只有空白字符
        if text_content and not text_content.strip():
            logger.debug("🔍 检测到空白文本消息")
            return True
        
        if caption_content and not caption_content.strip():
            logger.debug("🔍 检测到空白标题消息")
            return True
        
        # 检查是否只包含特殊字符（如空格、制表符、换行符等）
        if text_content:
            stripped_text = text_content.strip()
            if not stripped_text or all(c in ' \t\n\r\f\v' for c in stripped_text):
                logger.debug("🔍 检测到只包含空白字符的文本消息")
                return True
        
        if caption_content:
            stripped_caption = caption_content.strip()
            if not stripped_caption or all(c in ' \t\n\r\f\v' for c in stripped_caption):
                logger.debug("🔍 检测到只包含空白字符的标题消息")
                return True
        
        # 检查是否只包含重复字符（至少3个字符才认为是重复）
        if text_content and len(text_content.strip()) >= 3:
            unique_chars = set(text_content.strip())
            if len(unique_chars) == 1:
                logger.debug("🔍 检测到只包含重复字符的文本消息")
                return True
        
        # 检查是否只包含数字或特殊符号（至少5个字符才认为是无意义）
        if text_content:
            clean_text = text_content.strip()
            if len(clean_text) >= 5 and all(c.isdigit() or c in '.,!?;:()[]{}@#$%^&*' for c in clean_text):
                logger.debug("🔍 检测到过短的数字/符号消息")
                return True
        
        # 检查是否只包含链接但没有其他内容
        if text_content:
            import re
            # 简单的链接检测
            url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            urls = re.findall(url_pattern, text_content)
            if urls and len(text_content.strip()) == len(' '.join(urls)):
                logger.debug("🔍 检测到只包含链接的文本消息")
                return True
        
        # 检查是否只包含表情符号（至少3个字符才认为是无意义）
        if text_content:
            clean_text = ''.join(text_content.split())
            if len(clean_text) >= 3 and all(ord(c) > 127 for c in clean_text):
                logger.debug("🔍 检测到只包含表情符号的文本消息")
                return True
        
        return False
    
    def should_process_message(self, message: Message, config: Optional[Dict[str, Any]] = None) -> bool:
        """判断是否应该处理该消息 - 智能跳过空白信息"""
        # 使用指定的配置或全局配置
        effective_config = config or self.config
        
        # 添加调试日志
        import logging
        logger = logging.getLogger(__name__)
        
        # 智能空白消息检测
        if self._is_blank_message(message):
            logger.info("⏭️ 智能跳过空白消息")
            return False
        
        # 检查消息类型（包括caption和媒体）
        has_text = bool(message.text and message.text.strip())
        has_caption = bool(message.caption and message.caption.strip())
        has_media = bool(message.media)
        
        # 简化的调试信息
        logger.info(f"🔍 消息类型检查: media={has_media}, text={has_text}, caption={has_caption}")
        logger.info(f"🔍 消息类型: {type(message).__name__}, message_id={message.id}")
        logger.info(f"🔍 消息内容预览: text='{(message.text or '')[:50]}...', caption='{(message.caption or '')[:50]}...'")
        
        # 只在debug模式下显示消息内容
        if logger.isEnabledFor(logging.DEBUG):
            text_preview = (message.text or '')[:50] + ('...' if len(message.text or '') > 50 else '')
            caption_preview = (message.caption or '')[:50] + ('...' if len(message.caption or '') > 50 else '')
            logger.debug(f"🔍 消息内容: text='{text_preview}', caption='{caption_preview}'")
        
        # 检查是否是特殊消息类型（仅在DEBUG模式下显示）
        if logger.isEnabledFor(logging.DEBUG):
            if hasattr(message, 'service') and message.service:
                logger.debug(f"🔍 检测到服务消息: {message.service}")
            if hasattr(message, 'empty') and message.empty:
                logger.debug(f"🔍 检测到空消息")
        
        # 详细的消息属性检查（仅在DEBUG模式下显示）
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"🔍 消息详细属性:")
            logger.debug(f"  • message.text: {repr(message.text)}")
            logger.debug(f"  • message.caption: {repr(message.caption)}")
            logger.debug(f"  • message.media: {message.media}")
            logger.debug(f"  • message.photo: {getattr(message, 'photo', None)}")
            logger.debug(f"  • message.video: {getattr(message, 'video', None)}")
            logger.debug(f"  • message.document: {getattr(message, 'document', None)}")
            logger.debug(f"  • message.audio: {getattr(message, 'audio', None)}")
            logger.debug(f"  • message.voice: {getattr(message, 'voice', None)}")
            logger.debug(f"  • message.sticker: {getattr(message, 'sticker', None)}")
            logger.debug(f"  • message.animation: {getattr(message, 'animation', None)}")
            logger.debug(f"  • message.video_note: {getattr(message, 'video_note', None)}")
            logger.debug(f"  • message.contact: {getattr(message, 'contact', None)}")
            logger.debug(f"  • message.location: {getattr(message, 'location', None)}")
            logger.debug(f"  • message.venue: {getattr(message, 'venue', None)}")
            logger.debug(f"  • message.poll: {getattr(message, 'poll', None)}")
            logger.debug(f"  • message.dice: {getattr(message, 'dice', None)}")
            logger.debug(f"  • message.game: {getattr(message, 'game', None)}")
            logger.debug(f"  • message.web_page: {getattr(message, 'web_page', None)}")
            logger.debug(f"  • message.forward_from: {getattr(message, 'forward_from', None)}")
            logger.debug(f"  • message.forward_from_chat: {getattr(message, 'forward_from_chat', None)}")
            logger.debug(f"  • message.reply_to_message: {getattr(message, 'reply_to_message', None)}")
            logger.debug(f"  • message.media_group_id: {getattr(message, 'media_group_id', None)}")
            logger.debug(f"  • message.views: {getattr(message, 'views', None)}")
            logger.debug(f"  • message.edit_date: {getattr(message, 'edit_date', None)}")
            logger.debug(f"  • message.author_signature: {getattr(message, 'author_signature', None)}")
            logger.debug(f"  • message.entities: {getattr(message, 'entities', None)}")
            logger.debug(f"  • message.caption_entities: {getattr(message, 'caption_entities', None)}")
            logger.debug(f"  • message.reply_markup: {getattr(message, 'reply_markup', None)}")
            logger.debug(f"  • message.via_bot: {getattr(message, 'via_bot', None)}")
            logger.debug(f"  • message.sender_chat: {getattr(message, 'sender_chat', None)}")
            logger.debug(f"  • message.chat: {getattr(message, 'chat', None)}")
            logger.debug(f"  • message.date: {getattr(message, 'date', None)}")
            logger.debug(f"  • message.message_thread_id: {getattr(message, 'message_thread_id', None)}")
            logger.debug(f"  • message.effective_attachment: {getattr(message, 'effective_attachment', None)}")
        
        # 如果消息没有任何内容，跳过处理
        logger.info(f"🔍 内容检查结果: has_text={has_text}, has_caption={has_caption}, has_media={has_media}")
        if not has_text and not has_caption and not has_media:
            logger.warning("❌ 消息没有文本内容、caption和媒体，跳过处理")
            return False
        
        # 如果是媒体消息，即使没有文本也应该处理
        if has_media:
            logger.info("✅ 消息包含媒体内容，继续处理")
            return True
        
        # 检查是否被过滤
        logger.info(f"🔍 检查内容移除设置: content_removal={effective_config.get('content_removal', False)}")
        if effective_config.get('content_removal', False):
            content_removal_mode = effective_config.get('content_removal_mode', 'text_only')
            logger.info(f"🔍 内容移除模式: {content_removal_mode}")
            
            if content_removal_mode == 'text_only':
                # 仅移除纯文本：如果消息有媒体内容，则不应该跳过
                if message.media:
                    logger.debug("✅ 消息有媒体内容，不跳过（仅移除纯文本模式）")
                    return True  # 继续处理
                else:
                    # 纯文本消息且没有媒体，应该跳过
                    logger.info("❌ 纯文本消息且没有媒体，跳过处理（仅移除纯文本模式）")
                    return False  # 跳过纯文本消息
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
        logger.info(f"🔍 should_process_message 返回: True")
        return True
    
    def process_text(self, text: str, config: Optional[Dict[str, Any]] = None, message_type: str = "text") -> Tuple[Optional[str], bool]:
        """处理文本内容"""
        if not text:
            return "", False
        
        # 安全编码处理，防止UTF-16编码错误
        text = self._safe_encode_text(text)
        
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
        logger.info(f"🔍 增强过滤配置: enabled={effective_config.get('enhanced_filter_enabled', False)}, mode={effective_config.get('enhanced_filter_mode', 'N/A')}, available={ENHANCED_FILTER_AVAILABLE}")
        logger.info(f"🔍 调试信息: _debug_enhanced_filter_enabled={effective_config.get('_debug_enhanced_filter_enabled')}, _debug_links_removal={effective_config.get('_debug_links_removal')}")
        logger.info(f"🔍 完整过滤配置: {effective_config}")
        
        # 关键字过滤（兼容两种配置键名：'filter_keywords' 和 'keywords'）
        keywords_list = None
        if effective_config.get('filter_keywords'):
            keywords_list = effective_config.get('filter_keywords')
            logger.info("🔍 使用键 'filter_keywords' 进行关键字过滤")
        elif effective_config.get('keywords'):
            # 兼容旧/频道级配置中使用的 'keywords' 键名
            keywords_list = effective_config.get('keywords')
            logger.info("🔍 使用键 'keywords' 进行关键字过滤（兼容模式）")
        else:
            keywords_list = []

        if keywords_list:
            logger.info(f"🔍 检查关键字过滤: {keywords_list}")
            lower_text = processed_text.lower()
            for keyword in keywords_list:
                try:
                    if keyword and keyword.lower() in lower_text:
                        logger.info(f"❌ 发现关键字: {keyword}，移除整条消息")
                        return None, True  # 完全移除消息
                except Exception:
                    # 单个关键字出错时继续检查其他关键字
                    logger.exception(f"关键字检查时出错，跳过关键字: {keyword}")
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
        
        # 增强过滤处理
        # 只要开启了增强过滤 OR 开启了移除链接，就应用增强过滤器
        should_apply_enhanced_filter = (
            (effective_config.get('enhanced_filter_enabled', False) or 
             effective_config.get('remove_links', False)) and 
            ENHANCED_FILTER_AVAILABLE
        )
        
        if should_apply_enhanced_filter:
            logger.info(f"🔍 应用增强过滤: mode={effective_config.get('enhanced_filter_mode', 'aggressive')}, remove_links={effective_config.get('remove_links', False)}")
            logger.info(f"🔍 增强过滤前文本: {repr(processed_text[:100])}...")
            try:
                # 构建增强过滤器专用配置
                enhanced_config = {
                    "remove_links": effective_config.get('remove_links', True), # 优先使用配置中的remove_links
                    "remove_buttons": True,
                    "remove_ads": True,
                    "remove_usernames": effective_config.get('remove_usernames', False),
                    "ad_keywords": [
                        "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
                        "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
                        "QQ", "电话", "客服", "代理", "加盟", "投资", "理财",
                        "解锁", "福利", "新增", "合集", "完整", "全套", "打包"
                    ]
                }
                
                # 根据过滤模式调整配置
                filter_mode = effective_config.get('enhanced_filter_mode', 'moderate')
                if filter_mode == 'conservative':
                    enhanced_config["remove_ads"] = False
                    enhanced_config["ad_keywords"] = enhanced_config["ad_keywords"][:8]  # 只保留基础广告词
                elif filter_mode == 'aggressive':
                    enhanced_config["remove_ads"] = True
                    # 使用完整的广告词列表
                
                logger.info(f"🔍 增强过滤配置: {enhanced_config}")
                
                # 应用增强过滤
                filtered_text = enhanced_link_filter(processed_text, enhanced_config)
                logger.info(f"🔍 增强过滤后文本: {repr(filtered_text[:100])}...")
                if filtered_text != processed_text:
                    original_length = len(processed_text)
                    processed_text = filtered_text
                    modified = True
                    logger.info(f"✅ 增强过滤应用成功: 原始长度={original_length}, 过滤后长度={len(filtered_text)}")
                else:
                    logger.info("✅ 增强过滤检查通过，无需修改")
            except Exception as e:
                logger.error(f"❌ 增强过滤处理失败: {e}")
                # 继续使用原始文本，不中断处理流程
        
        # 链接处理
        # 如果增强过滤已经处理了链接，这里可以跳过，或者作为备用
        if effective_config.get('remove_links', False) and not should_apply_enhanced_filter: # Only run if enhanced filter didn't run for links
            logger.info(f"🔍 检查链接过滤: mode={effective_config.get('remove_links_mode')}")
            if effective_config.get('remove_links_mode') == 'remove_message':
                # 移除整条消息
                if self.http_pattern.search(processed_text):
                    logger.info("❌ 发现HTTP链接，移除整条消息")
                    return None, True
                logger.info("✅ 链接过滤检查通过")
            else:
                # 移除链接和包含超链接的文字
                logger.info("🔧 智能移除链接和上下文")
                processed_text = self._remove_links_with_context(processed_text)
                modified = True
                logger.info(f"🔧 链接移除后文本: '{processed_text[:100]}...' (长度: {len(processed_text)})")
        else:
            logger.info("✅ 链接过滤未启用或已由增强过滤处理")
        
        # 磁力链接处理
        if effective_config.get('remove_magnet_links', False):
            if effective_config.get('remove_links_mode') == 'remove_message':
                if self.magnet_pattern.search(processed_text):
                    logger.info("发现磁力链接，移除整条消息")
                    return None, True
            else:
                processed_text = self._remove_magnet_links_with_context(processed_text)
                modified = True
        
        # 移除所有链接
        if effective_config.get('remove_all_links', False):
            if effective_config.get('remove_links_mode') == 'remove_message':
                if (self.http_pattern.search(processed_text) or 
                    self.magnet_pattern.search(processed_text)):
                    logger.info("发现链接，移除整条消息")
                    return None, True
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
    
    async def process_text_with_ai(self, text: str, user_id: str = None) -> Tuple[str, bool]:
        """
        使用AI处理文本
        
        Args:
            text: 原始文本
            user_id: 用户ID，用于获取个性化配置
            
        Returns:
            Tuple[str, bool]: (处理后的文本, 是否进行了AI处理)
        """
        # 如果没有AI处理器，尝试动态创建
        if not self.ai_rewriter:
            # 尝试从用户配置获取AI设置
            if user_id:
                try:
                    from data_manager import DataManager
                    # 这里需要获取data_manager，但MessageEngine没有直接访问
                    # 所以我们需要通过其他方式获取配置
                    logger.warning("⚠️ AI改写器未初始化，需要用户配置来创建")
                    return text, False
                except Exception as e:
                    logger.error(f"❌ 获取用户AI配置失败: {e}")
                    return text, False
            else:
                # 如果没有user_id，检查全局配置
                if self.config.get('ai_rewrite_enabled', False):
                    try:
                        self.ai_rewriter = create_ai_rewriter(self.config)
                        logger.info("✅ AI文本改写器动态创建成功")
                    except Exception as e:
                        logger.error(f"❌ AI文本改写器动态创建失败: {e}")
                        return text, False
                else:
                    return text, False
        
        # 检查是否启用AI
        if not self.config.get('ai_rewrite_enabled', False):
            return text, False
        
        # 检查AI改写模式
        mode = self.config.get('ai_rewrite_mode', 'auto')
        
        # 自动模式下检查额度
        if mode == 'auto' and not self.ai_rewriter.has_quota():
            logger.info("🚫 AI额度不足，使用原文")
            return text, False
        
        # 强制模式下额度用尽则抛出异常
        if mode == 'on' and not self.ai_rewriter.has_quota():
            logger.warning("🚫 AI额度已用尽且处于强制模式")
            # 这里可以根据需求决定是抛出异常还是返回原文
            return text, False
        
        # 执行AI改写
        try:
            rewritten_text, was_rewritten = await self.ai_rewriter.rewrite_text(text)
            if was_rewritten:
                logger.info("✨ 文本已通过AI改写")
            return rewritten_text, was_rewritten
        except Exception as e:
            logger.error(f"❌ AI文本处理失败: {e}")
            return text, False
    
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
    
    def add_tail_text(self, text: str, has_media: bool = False) -> str:
        """添加文本小尾巴"""
        tail_text = self.config.get('tail_text', '').strip()
        if not tail_text:
            return text
        
        # 如果原文本为空且没有媒体内容，不添加小尾巴，避免发送只包含小尾巴的空消息
        if not text and not has_media:
            return text
        
        # 如果原文本为空但有媒体内容，只返回小尾巴
        if not text and has_media:
            return tail_text
        
        return f"{text}\n\n{tail_text}"
    
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
        
        # 如果没有按钮，返回None而不是空的InlineKeyboardMarkup
        if not combined_buttons:
            return None
        
        # 过滤掉空的按钮行
        filtered_buttons = [row for row in combined_buttons if row]
        
        # 如果过滤后没有按钮，返回None
        if not filtered_buttons:
            return None
        
        return InlineKeyboardMarkup(filtered_buttons)
    
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
            return None
        
        elif filter_mode == 'remove_message':
            # 如果是移除整条消息模式，这里仍然移除按钮，消息的移除在process_message中处理
            return None
        
        elif filter_mode == 'keep_safe':
            # 保留安全按钮（需要定义安全按钮列表）
            safe_buttons = []
            for row in buttons.inline_keyboard:
                safe_row = []
                for button in button:
                    # 这里可以定义安全按钮的判断逻辑
                    if self._is_safe_button(button):
                        safe_row.append(button)
                if safe_row:
                    safe_buttons.append(safe_row)
            
            # 如果没有安全按钮，返回None
            if not safe_buttons:
                return None
            
            # 过滤掉空的按钮行
            filtered_buttons = [row for row in safe_buttons if row]
            
            # 如果过滤后没有按钮，返回None
            if not filtered_buttons:
                return None
            
            return InlineKeyboardMarkup(filtered_buttons)
        
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
    
    async def process_message(self, message: Message, channel_config: Optional[Dict[str, Any]] = None, skip_blank_check: bool = False) -> Tuple[Dict[str, Any], bool]:
        """处理完整消息"""
        self.message_counter += 1
        
        # 使用频道组配置或全局配置
        effective_config = channel_config or self.config
        
        # 检查是否应该处理
        if skip_blank_check:
            # 跳过空白检查，直接处理消息
            should_process = True
            logger.info("🔧 跳过空白检查，直接处理消息")
        else:
            # 正常调用should_process_message检查消息是否应该处理
            should_process = self.should_process_message(message, effective_config)
            logger.info(f"🔍 should_process_message 结果: {should_process}")
        
        # 如果消息不应该被处理，直接返回
        if not should_process:
            logger.info("❌ 消息不应该被处理，跳过")
            return {}, False
        
        # 处理文本（包括caption）
        text = message.text or message.caption or ""
        
        # 简化的处理日志
        logger.debug(f"🔍 开始处理消息: text='{message.text or ''}', caption='{message.caption or ''}', 合并后='{text[:50]}...'")
        
        # 检查AI配置
        ai_enabled = effective_config.get('ai_rewrite_enabled', False)
        logger.info(f"🔍 AI改写配置检查: enabled={ai_enabled}, text_length={len(text)}, has_text={bool(text)}")
        if ai_enabled:
            logger.info(f"🔍 AI配置详情: mode={effective_config.get('ai_rewrite_mode', 'N/A')}, intensity={effective_config.get('ai_rewrite_intensity', 'N/A')}, user_id={effective_config.get('user_id', 'N/A')}")
        
        # 如果启用了AI改写，先进行AI处理
        if text and ai_enabled:
            logger.info(f"🤖 开始AI文本改写: message_id={message.id}, text_length={len(text)}")
            try:
                # 获取用户ID（如果配置中有）
                user_id = effective_config.get('user_id')
                
                # 如果AI改写器未初始化，尝试动态创建
                if not self.ai_rewriter:
                    # 使用effective_config创建AI改写器
                    ai_config = {
                        'ai_rewrite_enabled': effective_config.get('ai_rewrite_enabled', False),
                        'ai_rewrite_mode': effective_config.get('ai_rewrite_mode', 'auto'),
                        'ai_rewrite_intensity': effective_config.get('ai_rewrite_intensity', 'medium'),
                    }
                    try:
                        self.ai_rewriter = create_ai_rewriter(ai_config)
                        logger.info("✅ AI文本改写器动态创建成功")
                    except Exception as e:
                        logger.error(f"❌ AI文本改写器动态创建失败: {e}")
                        # 继续使用原文
                
                # 如果AI改写器已创建，使用它进行改写
                if self.ai_rewriter:
                    # 更新AI改写器的配置
                    self.ai_rewriter.enabled = effective_config.get('ai_rewrite_enabled', False)
                    self.ai_rewriter.intensity = effective_config.get('ai_rewrite_intensity', 'medium')
                    
                    text, was_rewritten = await self.ai_rewriter.rewrite_text(text)
                    if was_rewritten:
                        logger.info(f"✅ 消息 {message.id} 已AI改写")
                    else:
                        logger.info(f"ℹ️ 消息 {message.id} 未进行AI改写（可能额度不足或文本无需改写）")
                else:
                    logger.warning(f"⚠️ AI改写器未创建，跳过AI改写")
            except Exception as e:
                logger.error(f"❌ AI文本改写失败: {e}，使用原文", exc_info=True)
                # AI改写失败时继续使用原文
        
        processed_text, text_modified = self.process_text(text, effective_config)
    
        # 如果processed_text为None，说明消息被完全过滤（如关键字过滤）
        if processed_text is None:
            logger.info("❌ 消息被完全过滤（关键字等），跳过消息")
            return {}, False

        # 如果文本被完全移除，检查是否有媒体内容
        if processed_text == "" and text_modified:
            # 如果有媒体内容，仍然应该处理消息（只移除文本，保留媒体）
            if message.media:
                logger.debug("✅ 文本被移除但消息包含媒体，继续处理（保留媒体）")
                processed_text = ""  # 保持文本为空，但继续处理
            else:
                logger.warning("❌ 文本被完全移除且无媒体内容，跳过消息")
                return {}, False  # False表示应该跳过消息
        
        logger.debug(f"🔍 文本处理完成: processed='{processed_text[:50]}...', 修改: {text_modified}")
        
        # 检查按钮移除模式
        original_buttons = message.reply_markup
        
        # 如果设置为移除整条消息且消息包含按钮，则跳过该消息
        if (effective_config.get('filter_buttons', False) and 
            effective_config.get('button_filter_mode') == 'remove_message' and 
            original_buttons and original_buttons.inline_keyboard):
            logger.info("❌ 消息包含按钮且设置为移除整条消息，跳过该消息")
            return {}, False  # False表示应该跳过消息
        
        # 处理按钮
        filtered_buttons = self.filter_buttons(original_buttons, effective_config)
        
        # 添加文本小尾巴
        should_add = self._should_add_tail_text(effective_config)
        
        if should_add:
            logger.debug("✅ 添加小尾巴")
            # 检查是否有媒体内容
            has_media = bool(message.media)
            processed_text = self._add_tail_text(processed_text, effective_config, has_media)
            logger.debug(f"🔍 添加小尾巴后: '{processed_text[:50]}...'")
        else:
            logger.debug("❌ 不添加小尾巴")
        
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
        
        # 检查是否是媒体组消息
        if hasattr(message, 'media_group_id') and message.media_group_id:
            result['media_group'] = True
            result['media_group_id'] = message.media_group_id
            logger.info(f"🔍 检测到媒体组消息: media_group_id={message.media_group_id}")
            
            # 添加媒体组完整性信息
            result['media_group_info'] = {
                'group_id': message.media_group_id,
                'message_id': message.id,
                'has_caption': bool(message.caption),
                'has_text': bool(message.text),
                'media_type': self._get_media_type(message)
            }
        
        # 添加媒体信息
        if message.photo:
            result['photo'] = message.photo
        elif message.video:
            result['video'] = message.video
        elif message.document:
            result['document'] = message.document
        elif message.audio:
            result['audio'] = message.audio
        elif message.voice:
            result['voice'] = message.voice
        elif message.sticker:
            result['sticker'] = message.sticker
        elif message.animation:
            result['animation'] = message.animation
        elif message.video_note:
            result['video_note'] = message.video_note
        
        return result, True  # True表示应该处理消息
    
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
                # 安全编码处理
                safe_caption = self._safe_encode_text(msg.caption.strip())
                all_captions.append(safe_caption)
        
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
    
        # 如果processed_caption为None，说明消息被完全过滤
        if processed_caption is None:
            logger.info("❌ 媒体组被完全过滤（关键字等），跳过")
            return {}, False
        
        # 如果caption被完全移除，保持为空（不添加默认标签）
        # 用户不希望自动添加媒体组标签
        if processed_caption == "" and text_modified:
            processed_caption = ""  # 保持为空
        
        # 添加文本小尾巴
        should_add = self._should_add_tail_text(effective_config)
        
        if should_add:
            logger.debug("✅ 添加小尾巴")
            # 媒体组消息肯定有媒体内容
            has_media = True
            processed_caption = self._add_tail_text(processed_caption, effective_config, has_media)
            logger.debug(f"🔍 添加小尾巴后: '{processed_caption[:50]}...'")
        else:
            logger.debug("❌ 不添加小尾巴")
        
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
        
        return result, True  # True表示应该处理消息
    
    def _should_add_tail_text(self, config: Dict[str, Any]) -> bool:
        """检查是否应该添加小尾巴文本（使用指定配置）"""
        tail_text = config.get('tail_text', '').strip()
        
        # 简化的调试信息
        logger.debug(f"🔍 _should_add_tail_text 检查: tail_text='{tail_text}', 长度={len(tail_text)}")
        
        if not tail_text:
            logger.debug(f"  • 结果: False (tail_text为空)")
            return False
        
        # 检查频率设置（支持数字百分比）
        frequency = config.get('tail_frequency', 100)
        logger.debug(f"  • frequency: {frequency} (类型: {type(frequency)})")
        
        # 如果是数字，按百分比处理
        if isinstance(frequency, (int, float)):
            # 确保频率值在有效范围内
            frequency = float(frequency)
            logger.debug(f"  • 数字频率处理: {frequency}")
            
            if frequency >= 100.0:
                logger.debug(f"  • 结果: True (频率 >= 100%)")
                return True
            elif frequency <= 0.0:
                logger.debug(f"  • 结果: False (频率 <= 0%)")
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
            logger.info(f"  • 结果: True (频率 = 'always')")
            return True
        elif frequency == 'interval':
            # 间隔添加，每N条消息添加一次
            interval = config.get('tail_interval', 5)
            should_add = self.message_counter % interval == 0
            logger.info(f"  • 间隔模式: interval={interval}, message_counter={self.message_counter}, should_add={should_add}")
            return should_add
        elif frequency == 'random':
            # 随机添加，50%概率
            import random
            should_add = random.random() < 0.5
            logger.info(f"  • 随机模式: should_add={should_add}")
            return should_add
        
        logger.info(f"  • 结果: False (未知频率模式: {frequency})")
        return False
    
    def _add_tail_text(self, text: str, config: Dict[str, Any], has_media: bool = False) -> str:
        """添加小尾巴文本（使用指定配置）"""
        tail_text = config.get('tail_text', '').strip()
        if not tail_text:
            return text
        
        # 如果原文本为空且没有媒体内容，不添加小尾巴，避免发送只包含小尾巴的空消息
        if not text and not has_media:
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
    
    def _get_media_type(self, message: Message) -> str:
        """获取消息的媒体类型"""
        if message.photo:
            return "photo"
        elif message.video:
            return "video"
        elif message.document:
            return "document"
        elif message.audio:
            return "audio"
        elif message.voice:
            return "voice"
        elif message.sticker:
            return "sticker"
        elif message.animation:
            return "animation"
        elif message.video_note:
            return "video_note"
        elif message.contact:
            return "contact"
        elif message.location:
            return "location"
        elif message.venue:
            return "venue"
        elif message.poll:
            return "poll"
        elif message.dice:
            return "dice"
        elif message.game:
            return "game"
        elif message.web_page:
            return "web_page"
        else:
            return "unknown"

    def get_ai_quota_status(self) -> Optional[Dict[str, Any]]:
        """获取AI额度状态"""
        if self.ai_rewriter:
            return self.ai_rewriter.get_quota_status()
        return None

# ==================== 导出函数 ====================
def create_message_engine(config: Dict[str, Any]) -> MessageEngine:
    """创建消息处理引擎实例"""
    return MessageEngine(config)

__all__ = [
    "MessageEngine", "create_message_engine"
]


