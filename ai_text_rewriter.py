# ==================== AI文本改写模块 ====================
"""
AI文本改写模块
在搬运过程中自动修改文本内容，避免被查重
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime, date
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from log_config import get_logger

logger = get_logger(__name__)

@dataclass
class QuotaInfo:
    """额度信息"""
    # Gemini 2.5 Flash Lite 每日额度
    # RPM: 15 (每分钟请求数)
    # TPM: 250k (每分钟tokens数)
    # RPD: 1k (每日请求数)
    used: int = 0
    limit: int = 1000  # RPD: 1K requests per day
    rpm_limit: int = 15  # RPM: 15 requests per minute
    tpm_limit: int = 250000  # TPM: 250k tokens per minute
    last_reset: date = None
    
    def __post_init__(self):
        if self.last_reset is None:
            self.last_reset = date.today()

class QuotaManager:
    """额度管理器"""
    
    def __init__(self):
        self.quota_info = QuotaInfo(last_reset=date.today())
        self._reset_if_new_day()
    
    def _reset_if_new_day(self):
        """如果是新的一天，重置额度"""
        today = date.today()
        if self.quota_info.last_reset != today:
            self.quota_info.used = 0
            self.quota_info.last_reset = today
            logger.info("📅 额度已重置")
    
    def has_quota(self) -> bool:
        """检查是否有额度"""
        self._reset_if_new_day()
        return self.quota_info.used < self.quota_info.limit
    
    def record_usage(self):
        """记录使用量"""
        self._reset_if_new_day()
        self.quota_info.used += 1
        logger.debug(f"📊 额度使用: {self.quota_info.used}/{self.quota_info.limit}")
    
    def get_usage_percentage(self) -> float:
        """获取使用百分比"""
        self._reset_if_new_day()
        return (self.quota_info.used / self.quota_info.limit) * 100
    
    def get_remaining_quota(self) -> Dict[str, Any]:
        """获取剩余额度信息"""
        self._reset_if_new_day()
        return {
            'used': self.quota_info.used,
            'limit': self.quota_info.limit,
            'remaining': self.quota_info.limit - self.quota_info.used,
            'percent': (self.quota_info.used / self.quota_info.limit) * 100
        }

class AITextRewriter:
    """AI文本改写器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化AI文本改写器"""
        self.config = config or {}
        self.models: List[Any] = []  # 存储多个模型实例
        self.api_keys = [
            'AIzaSyBLK34oMuDToBAy7o7Z_MSK361koIgcdk4',
            'AIzaSyBhLYU-baLvUYggS5HGWQPzpWx8tgdmg9k',
            'AIzaSyDRj8eWYEZtS-dPGi4XHHQSe-QgXMPYSsQ',
            'AIzaSyAhJrHMwalCtuZft7gg2YozKCDaGnY4K9A',
            'AIzaSyDPb7uRprSGw_iwTIsexYy5u5cz9brigFE'
        ]
        # 为每个API密钥创建独立的额度管理器
        self.quota_managers: Dict[str, QuotaManager] = {}
        for api_key in self.api_keys:
            self.quota_managers[api_key] = QuotaManager()
        self.current_key_index = 0
        self.enabled = self.config.get('ai_rewrite_enabled', False)
        self.intensity = self.config.get('ai_rewrite_intensity', 'medium')
        
        # 初始化所有API密钥对应的模型
        self._initialize_models()
    
    def _initialize_models(self):
        """初始化所有API密钥对应的模型"""
        self.models = []
        for i, api_key in enumerate(self.api_keys):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-2.5-flash-lite')
                self.models.append(model)
                logger.info(f"🤖 Gemini API 密钥 {i+1} 初始化成功")
            except Exception as e:
                logger.warning(f"⚠️ Gemini API 密钥 {i+1} 初始化失败: {e}")
        
        if not self.models:
            logger.error("❌ 所有Gemini API密钥初始化失败")
        else:
            logger.info(f"✅ 成功初始化 {len(self.models)} 个Gemini API密钥")
    
    def _get_next_model(self):
        """获取下一个可用的模型"""
        if not self.models:
            return None
        
        # 尝试当前模型
        model = self.models[self.current_key_index]
        
        # 更新索引，准备下次使用下一个密钥
        self.current_key_index = (self.current_key_index + 1) % len(self.models)
        
        return model
    
    async def rewrite_text(self, text: str) -> Tuple[str, bool]:
        """
        改写文本内容
        
        Args:
            text: 原始文本
            
        Returns:
            Tuple[str, bool]: (改写后的文本, 是否进行了改写)
        """
        if not self.enabled or not text.strip():
            return text, False
        
        # 检查是否有任何密钥有额度
        has_any_quota = any(
            quota_manager.has_quota() 
            for quota_manager in self.quota_managers.values()
        )
        if not has_any_quota:
            logger.warning("🚫 所有Gemini API密钥额度已用尽，使用原文")
            return text, False
        
        # 尝试使用各个API密钥
        for i in range(len(self.models)):
            # 获取当前使用的API密钥索引（在调用_get_next_model之前）
            current_key_index = self.current_key_index
            model = self._get_next_model()
            if not model:
                continue
            
            # 获取当前使用的API密钥
            current_key = self.api_keys[current_key_index]
            quota_manager = self.quota_managers[current_key]
            
            # 检查当前密钥的额度
            if not quota_manager.has_quota():
                logger.warning(f"🚫 API密钥 {i+1} 额度已用尽，尝试下一个")
                continue
                
            try:
                # 构造提示词
                prompt = self._build_prompt(text)
                
                # 调用Gemini API
                response = await asyncio.wait_for(
                    self._call_gemini_api(prompt, model),
                    timeout=30.0
                )
                
                rewritten_text = response.text.strip() if response and response.text else text
                
                # 记录当前密钥的实际使用量
                quota_manager.record_usage()
                
                # 如果文本没有实质性改变，则不标记为已改写
                if rewritten_text.strip() == text.strip():
                    return text, False
                
                logger.debug(f"🔄 AI文本改写成功 (密钥 {i+1}): '{text[:50]}...' -> '{rewritten_text[:50]}...'")
                return rewritten_text, True
                
            except asyncio.TimeoutError:
                logger.error(f"❌ AI文本改写超时 (API密钥 {i+1})")
                continue
            except Exception as e:
                logger.error(f"❌ AI文本改写失败 (API密钥 {i+1}): {e}")
                continue
        
        # 所有API密钥都失败
        logger.error("❌ 所有Gemini API密钥都无法使用")
        return text, False
    
    def _build_prompt(self, text: str) -> str:
        """构建提示词"""
        intensity_instructions = {
            'light': "请对以下文本进行轻微改写，保持原意不变，只做少量词汇替换和句式调整：",
            'medium': "请对以下文本进行适度改写，保持原意不变，可以调整句式结构和替换同义词：",
            'heavy': "请对以下文本进行较大幅度改写，保持原意不变，可以重新组织内容结构："
        }
        
        instruction = intensity_instructions.get(self.intensity, intensity_instructions['medium'])
        
        return f"""
{instruction}

{text}

改写要求：
1. 保持原文的核心信息和观点不变
2. 必须修改超过50%的内容以避免查重，包括词汇替换、句式调整、段落重组等
3. 保持原始语种，不要翻译成其他语言
4. 保护专有名词，包括人名、地名、品牌名等不得修改
5. 对于话题标签（以#开头的词汇），也需要进行适当修改，如替换为同义标签或相关标签
6. 可以重新组织内容结构和逻辑顺序
7. 保持语言自然流畅，易于理解
8. 如果文本包含标签，请将标签保留在第一行，并对标签进行适当改写
9. 文本内容从第二行开始

改写结果请按照以下格式：
#改写后的标签1 #改写后的标签2 #改写后的标签3
改写后的文本内容...

如果原文没有标签，请保持原文格式。

改写结果：
"""
    
    async def _call_gemini_api(self, prompt: str, model):
        """调用Gemini API"""
        try:
            response = await model.generate_content_async(
                prompt,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                }
            )
            return response
        except Exception as e:
            logger.error(f"❌ 调用Gemini API失败: {e}")
            raise
    
    def has_quota(self) -> bool:
        """检查是否有任何密钥有额度"""
        return any(
            quota_manager.has_quota() 
            for quota_manager in self.quota_managers.values()
        )
    
    def get_quota_status(self) -> Dict[str, Any]:
        """获取所有密钥的额度状态"""
        total_used = 0
        total_limit = 0
        key_statuses = []
        
        for i, (api_key, quota_manager) in enumerate(self.quota_managers.items()):
            quota_info = quota_manager.get_remaining_quota()
            total_used += quota_info['used']
            total_limit += quota_info['limit']
            key_statuses.append({
                'key_index': i + 1,
                'used': quota_info['used'],
                'limit': quota_info['limit'],
                'remaining': quota_info['remaining'],
                'percent': quota_info['percent']
            })
        
        return {
            'total_used': total_used,
            'total_limit': total_limit,
            'total_remaining': total_limit - total_used,
            'total_percent': (total_used / total_limit * 100) if total_limit > 0 else 0,
            'keys': key_statuses
        }
    
    async def preview_rewrite(self, text: str) -> Tuple[str, bool]:
        """
        预览文本改写效果
        
        Args:
            text: 原始文本
            
        Returns:
            Tuple[str, bool]: (预览改写后的文本, 是否进行了改写)
        """
        if not self.enabled or not text.strip():
            return text, False
        
        # 尝试使用各个API密钥
        for i in range(len(self.models)):
            model = self._get_next_model()
            if not model:
                continue
                
            try:
                # 构造预览提示词
                prompt = self._build_preview_prompt(text)
                
                # 调用Gemini API
                response = await asyncio.wait_for(
                    self._call_gemini_api(prompt, model),
                    timeout=30.0
                )
                
                preview_text = response.text.strip() if response and response.text else text
                
                # 如果文本没有实质性改变，则不标记为已改写
                if preview_text.strip() == text.strip():
                    return text, False
                
                logger.debug(f"👀 AI文本改写预览: '{text[:50]}...' -> '{preview_text[:50]}...'")
                return preview_text, True
                
            except asyncio.TimeoutError:
                logger.error(f"❌ AI文本改写预览超时 (API密钥 {i+1})")
                continue
            except Exception as e:
                logger.error(f"❌ AI文本改写预览失败 (API密钥 {i+1}): {e}")
                continue
        
        # 所有API密钥都失败
        logger.error("❌ 所有Gemini API密钥都无法使用")
        return text, False
    
    def _build_preview_prompt(self, text: str) -> str:
        """构建预览提示词"""
        return f"""
请对以下文本进行改写预览，保持原意不变，但必须修改超过50%的内容：

{text}

预览改写要求：
1. 保持原文的核心信息和观点不变
2. 必须修改超过50%的内容以避免查重，包括词汇替换、句式调整、段落重组等
3. 保持原始语种，不要翻译成其他语言
4. 保护专有名词，包括人名、地名、品牌名等不得修改
5. 对于话题标签（以#开头的词汇），也需要进行适当修改，如替换为同义标签或相关标签
6. 可以重新组织内容结构和逻辑顺序
7. 保持语言自然流畅，易于理解
8. 如果文本包含标签，请将标签保留在第一行，并对标签进行适当改写
9. 文本内容从第二行开始
10. 只需要返回改写后的文本，不需要额外说明

预览改写结果：
"""

# ==================== 导出函数 ====================
def create_ai_rewriter(config: Dict[str, Any]) -> AITextRewriter:
    """创建AI文本改写器实例"""
    return AITextRewriter(config)

__all__ = [
    "AITextRewriter", "create_ai_rewriter"
]