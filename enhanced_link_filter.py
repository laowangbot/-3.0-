# ==================== 增强版链接过滤器 ====================
"""
增强版链接过滤器
结合链接移除和广告内容过滤功能
"""

import re
from typing import Dict, Any, Optional

def enhanced_link_filter(text: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    增强版链接过滤器
    
    Args:
        text: 要过滤的文本
        config: 过滤配置
        
    Returns:
        过滤后的文本
    """
    if not text or not isinstance(text, str):
        return text
    
    # 默认配置
    default_config = {
        "remove_links": True,
        "remove_buttons": True,
        "remove_ads": True,
        "remove_usernames": False,
        "ad_keywords": [
            "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
            "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
            "QQ", "电话", "客服", "代理", "加盟", "投资", "理财"
        ]
    }
    
    # 合并配置
    if config:
        default_config.update(config)
    
    filtered_text = text
    
    # 1. 移除链接
    if default_config.get("remove_links", True):
        # 移除HTTP/HTTPS链接
        filtered_text = re.sub(r'https?://[^\s]+', '', filtered_text)
        # 移除t.me链接
        filtered_text = re.sub(r't\.me/[^\s]+', '', filtered_text)
        # 移除@用户名链接
        filtered_text = re.sub(r'@[a-zA-Z0-9_]+', '', filtered_text)
    
    # 2. 移除按钮文本
    if default_config.get("remove_buttons", True):
        # 移除常见的按钮文本
        button_patterns = [
            r'\[.*?\]',  # [按钮文本]
            r'点击.*?',   # 点击...
            r'查看.*?',   # 查看...
            r'了解更多.*?', # 了解更多...
            r'立即.*?',   # 立即...
        ]
        for pattern in button_patterns:
            filtered_text = re.sub(pattern, '', filtered_text)
    
    # 3. 移除广告内容
    if default_config.get("remove_ads", True):
        ad_keywords = default_config.get("ad_keywords", [])
        lines = filtered_text.split('\n')
        filtered_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 检查是否包含广告关键词
            is_ad = False
            for keyword in ad_keywords:
                if keyword in line:
                    is_ad = True
                    break
            
            # 检查是否是纯链接行
            if re.match(r'^https?://', line):
                is_ad = True
            
            # 检查是否是联系方式行
            if re.search(r'(微信|QQ|电话|客服|联系).*?[:：]', line):
                is_ad = True
            
            if not is_ad:
                filtered_lines.append(line)
        
        filtered_text = '\n'.join(filtered_lines)
    
    # 4. 移除用户名
    if default_config.get("remove_usernames", False):
        filtered_text = re.sub(r'@[a-zA-Z0-9_]+', '', filtered_text)
    
    # 5. 清理多余的空行和空格
    filtered_text = re.sub(r'\n\s*\n', '\n', filtered_text)
    filtered_text = re.sub(r' +', ' ', filtered_text)
    filtered_text = filtered_text.strip()
    
    return filtered_text

def get_enhanced_filter_config() -> Dict[str, Any]:
    """获取增强过滤器的默认配置"""
    return {
        "enhanced_filter_enabled": False,
        "enhanced_filter_mode": "aggressive",  # aggressive, moderate, conservative
        "remove_links": True,
        "remove_buttons": True,
        "remove_ads": True,
        "remove_usernames": False,
        "ad_keywords": [
            "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
            "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
            "QQ", "电话", "客服", "代理", "加盟", "投资", "理财"
        ]
    }

def apply_enhanced_filter_to_user_config(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """将增强过滤器配置应用到用户配置中"""
    enhanced_config = get_enhanced_filter_config()
    user_config.update(enhanced_config)
    return user_config
