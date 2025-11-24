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
from google.generativeai.generative_models import GenerativeModel  # 显式导入 GenerativeModel
from google.generativeai.client import configure
from log_config import get_logger

logger = get_logger(__name__)

@dataclass
class QuotaInfo:
    """额度信息"""
    used: int = 0
    limit: int = 1000  # 1K calls per day
    last_reset: Optional[date] = None
    
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

# 为每个API密钥维护一个额度管理器
api_key_quota_managers = {}

def get_quota_manager(api_key: str) -> QuotaManager:
    """获取指定API密钥的额度管理器"""
    if api_key not in api_key_quota_managers:
        api_key_quota_managers[api_key] = QuotaManager()
    return api_key_quota_managers[api_key]

class AITextRewriter:
    """AI文本改写器"""
    
    def __init__(self, config: Dict[str, Any], get_current_api_key_func=None):
        """初始化AI文本改写器"""
        self.config = config or {}
        self.model: Optional[GenerativeModel] = None  # 明确类型为 GenerativeModel
        self.client = None
        self.current_api_key = ""
        self.get_current_api_key = get_current_api_key_func  # 回调函数用于获取当前API密钥
        self.quota_manager: Optional[QuotaManager] = None  # 当前API密钥的额度管理器
        
        # 初始化Gemini客户端
        self._initialize_gemini_client()
    
    def _initialize_gemini_client(self):
        """初始化Gemini客户端"""
        try:
            # 获取API密钥（支持轮询）
            api_key = ""
            if self.get_current_api_key:
                api_key = self.get_current_api_key()
            else:
                # 兼容旧方式
                api_key = self.config.get('gemini_api_key', '')
            
            if api_key:
                # 获取该API密钥的额度管理器
                self.quota_manager = get_quota_manager(api_key)
                configure(api_key=api_key)
                self.client = genai
                # 尝试初始化模型
                self.model = GenerativeModel('gemini-2.5-flash-lite')  # 使用显式导入的类
                logger.info("✅ Gemini客户端初始化成功")
            else:
                logger.warning("⚠️ 未配置Gemini API密钥")
        except Exception as e:
            logger.error(f"❌ Gemini客户端初始化失败: {e}")
            self.model = None
    
    async def rewrite_text(self, text: str) -> Tuple[str, bool]:
        """改写文本"""
        try:
            # 检查是否启用了AI改写
            if not self.config.get('ai_rewrite_enabled', False):
                return text, False
            
            # 检查额度
            if self.quota_manager and not self.quota_manager.has_quota():
                logger.warning("⚠️ AI额度已用尽，返回原文")
                return text, False
            
            # 检查模型是否可用
            if not self.model:
                logger.warning("⚠️ AI模型不可用，返回原文")
                return text, False
            
            # 构建提示词
            prompt = self._build_prompt(text)
            
            # 调用AI模型
            response = await self.model.generate_content_async(
                prompt,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            
            # 处理响应
            if response and response.text:
                rewritten_text = response.text.strip()
                
                # 记录额度使用
                if self.quota_manager:
                    self.quota_manager.record_usage()
                
                return rewritten_text, True
            else:
                logger.warning("⚠️ AI改写返回空结果，返回原文")
                return text, False
                
        except Exception as e:
            logger.error(f"❌ AI文本改写失败: {e}")
            return text, False
    
    def _build_prompt(self, text: str) -> str:
        """构建提示词"""
        intensity_instructions = {
            'light': "请对以下文本进行轻微改写，保持原意不变，只做少量词汇替换和句式调整：",
            'medium': "请对以下文本进行适度改写，保持原意不变，可以调整句式结构和替换同义词：",
            'heavy': "请对以下文本进行较大幅度改写，保持原意不变，可以重新组织内容结构："
        }
        
        tag_instructions = {
            'optimize': "请优化话题标签，使其更符合内容主题：",
            'replace': "请替换话题标签为相关但不同的标签：",
            'extend': "请在保留原有标签的基础上增加相关标签：",
            'keep': "请保留原有话题标签不变："
        }
        
        # 获取配置
        intensity = self.config.get('ai_rewrite_intensity', 'medium')
        tag_handling = self.config.get('ai_tag_handling', 'optimize')
        
        # 构建完整的提示词
        prompt = f"{intensity_instructions.get(intensity, intensity_instructions['medium'])}\n\n"
        prompt += f"{tag_instructions.get(tag_handling, tag_instructions['optimize'])}\n\n"
        prompt += text
        
        return prompt
    
    def get_quota_status(self) -> Optional[Dict[str, Any]]:
        """获取当前API密钥的额度状态"""
        if self.quota_manager:
            return self.quota_manager.get_remaining_quota()
        return None

# ==================== 导出函数 ====================
def create_ai_rewriter(config: Dict[str, Any]) -> AITextRewriter:
    """创建AI文本改写器实例"""
    return AITextRewriter(config)

__all__ = [
    "AITextRewriter", "create_ai_rewriter"
]