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
        "link_based_filtering": True,  # 新增：基于链接的过滤模式
        "ad_keywords": [
            "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
            "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
            "QQ", "电话", "客服", "代理", "加盟", "投资", "理财"
        ]
    }
    
    # 合并配置
    if config:
        default_config.update(config)
    
    # 检查是否包含链接 - 改进的检测方法
    has_links = bool(
        re.search(r'https?://[^\s]+', text, re.IGNORECASE) or 
        re.search(r't\.me/[^\s]+', text, re.IGNORECASE) or 
        re.search(r'@\w+', text) or  # 用户名也是一种链接形式
        re.search(r'\b[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.(?:[a-zA-Z]{2,}|[a-zA-Z]{2,}\.[a-zA-Z]{2,})\b', text, re.IGNORECASE)
    )
    
    # 如果启用基于链接的过滤模式，且没有链接，则只进行轻度过滤
    if default_config.get("link_based_filtering", True) and not has_links:
        # 对于没有链接的消息，只移除明显的广告关键词行，保留主要内容
        return _light_filter(text, default_config)
    
    filtered_text = text
    
    # 1. 智能移除链接（保留链接前后的文本）
    if default_config.get("remove_links", True):
        # 移除HTTP/HTTPS链接，但保留链接前后的文本
        filtered_text = re.sub(r'\s*https?://[^\s]+\s*', ' ', filtered_text, flags=re.IGNORECASE)
        # 移除t.me链接，但保留链接前后的文本
        filtered_text = re.sub(r'\s*t\.me/[^\s]+\s*', ' ', filtered_text, flags=re.IGNORECASE)
        # 移除@用户名链接，但保留链接前后的文本
        filtered_text = re.sub(r'\s*@[a-zA-Z0-9_]+\s*', ' ', filtered_text)
        # 移除纯域名链接（如 TTYUZU.TOP, example.com 等）
        filtered_text = re.sub(r'\s*\b[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.(?:[a-zA-Z]{2,}|[a-zA-Z]{2,}\.[a-zA-Z]{2,})\b\s*', ' ', filtered_text, flags=re.IGNORECASE)
    
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
                
            # 检查是否包含广告关键词（但排除主要内容描述行）
            is_ad = False
            # 如果行包含实质性的中文描述内容（8个以上中文字符），则不认为是广告
            has_substantial_content = len(re.findall(r'[\u4e00-\u9fff]', line)) >= 8
            
            # 检查是否包含主要内容关键词（如：模特、私拍、国模等）
            main_content_keywords = [
                '模特', '私拍', '国模', '户外', '露出', '泄密', '摄影师',
                '原版', '无水印', '湿地', '公园', '火儿', '合集', '完整'
            ]
            has_main_content = any(keyword in line for keyword in main_content_keywords)
            
            # 如果包含主要内容关键词，降低过滤强度
            if has_main_content:
                has_substantial_content = True
            
            if not has_substantial_content:
                for keyword in ad_keywords:
                    if keyword in line:
                        is_ad = True
                        break
            
            # 检查是否是纯链接行
            if re.match(r'^https?://', line, re.IGNORECASE):
                is_ad = True
            
            # 检查是否是联系方式行
            if re.search(r'(微信|QQ|电话|客服|联系).*?[:：]', line):
                is_ad = True
            
            # 检查是否是明显的广告推广行（包含👑符号和数字编号的合集广告）
            # 但如果包含主要内容描述（如：国模 火儿 湿地公园），则保留
            if re.search(r'👑.*?【.*?合集.*?】.*?👑.*?#\d{4,}', line):
                # 检查是否包含主要内容描述（至少5个中文字符）
                if not re.search(r'[\u4e00-\u9fff]{5,}', line):
                    is_ad = True
            
            # 检查是否是数字编号广告行（如：#10327, #12345等，但不包含主要内容）
            if re.search(r'#\d{4,}', line) and len(line.strip()) < 20:
                is_ad = True
            
            # 检查是否是文件大小/数量广告行（如：69V 450P, 24V 37P等）
            # 但如果包含主要内容描述，则保留
            if re.search(r'\d+[Vv]\s*\d+[Pp]', line):
                # 检查是否包含主要内容描述（至少5个中文字符）
                if not re.search(r'[\u4e00-\u9fff]{5,}', line):
                    is_ad = True
            
            # 检查是否是更新状态广告行（如：持续更新中、已更新等）
            # 但如果包含主要内容描述，则保留
            if re.search(r'(持续更新|已更新|更新中)', line):
                # 检查是否包含主要内容描述（至少5个中文字符）
                if not re.search(r'[\u4e00-\u9fff]{5,}', line):
                    is_ad = True
            
            # 检查是否是价格/付费广告行
            if re.search(r'(\d+元|\d+块|\d+币|付费|收费|价格|限时特惠|会员门票|秒上车)', line):
                is_ad = True
            
            # 检查是否是VPN/加速器广告行
            if re.search(r'(VPN|加速|免费使用)', line):
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

def _light_filter(text: str, config: Dict[str, Any]) -> str:
    """
    轻度过滤函数 - 用于没有链接的消息
    只移除明显的广告关键词和特定模式，保留主要内容
    """
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 只过滤明显的广告行，保留主要内容
        is_obvious_ad = False
        
        # 检查是否是明显的广告关键词行（需要包含多个广告词）
        ad_keywords = config.get("ad_keywords", [])
        ad_count = sum(1 for keyword in ad_keywords if keyword in line)
        if ad_count >= 2:  # 需要包含2个或以上广告词才认为是广告
            is_obvious_ad = True
        
        # 检查是否是价格/付费广告行
        if re.search(r'(\d+元|\d+块|\d+币|付费|收费|价格|限时特惠|会员门票|秒上车)', line):
            is_obvious_ad = True
        
        # 检查是否是VPN广告行
        if re.search(r'(VPN|加速|免费使用)', line):
            is_obvious_ad = True
        
        # 保留主要内容（标签、描述等）
        if not is_obvious_ad:
            filtered_lines.append(line)
    
    filtered_text = '\n'.join(filtered_lines)
    
    # 清理多余的空行
    filtered_text = re.sub(r'\n\s*\n', '\n', filtered_text)
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
