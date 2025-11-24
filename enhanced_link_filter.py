# ==================== 增强版链接过滤器 ====================
"""
增强版链接过滤器
结合链接移除和广告内容过滤功能
优化：使用预编译正则和白名单机制
"""

import re
from typing import Dict, Any, Optional, List, Pattern

class EnhancedLinkFilter:
    """增强版链接过滤器类"""
    
    def __init__(self):
        """初始化过滤器，预编译正则表达式"""
        # 链接相关正则
        self.url_pattern = re.compile(r'https?://[^\s]+')
        self.tme_pattern = re.compile(r't\.me/[^\s]+')
        self.domain_pattern = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.(?:[a-zA-Z]{2,}|[a-zA-Z]{2,}\.[a-zA-Z]{2,})')
        
        # 移除链接正则（保留前后文本）
        self.remove_url_pattern = re.compile(r'\s*https?://[^\s]+\s*')
        self.remove_tme_pattern = re.compile(r'\s*t\.me/[^\s]+\s*')
        self.remove_username_pattern = re.compile(r'\s*@[a-zA-Z0-9_]+\s*')
        self.remove_domain_pattern = re.compile(r'\s*[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.(?:[a-zA-Z]{2,}|[a-zA-Z]{2,}\.[a-zA-Z]{2,})\s*')
        
        # 按钮文本正则
        self.button_patterns = [
            re.compile(r'\[.*?\]'),  # [按钮文本]
            re.compile(r'点击.*?'),   # 点击...
            re.compile(r'查看.*?'),   # 查看...
            re.compile(r'了解更多.*?'), # 了解更多...
            re.compile(r'立即.*?'),   # 立即...
        ]
        
        # 广告特征正则
        self.pure_link_pattern = re.compile(r'^https?://')
        self.contact_pattern = re.compile(r'(微信|QQ|电话|客服|联系).*?[:：]')
        self.collection_ad_pattern = re.compile(r'👑.*?【.*?合集.*?】.*?👑.*?#\d{4,}')
        self.chinese_chars_pattern = re.compile(r'[\u4e00-\u9fff]')
        self.number_ad_pattern = re.compile(r'#\d{4,}')
        self.file_size_pattern = re.compile(r'\d+[Vv]\s*\d+[Pp]')
        self.update_status_pattern = re.compile(r'(持续更新|已更新|更新中)')
        self.price_pattern = re.compile(r'(\d+元|\d+块|\d+币|付费|收费|价格|限时特惠|会员门票|秒上车)')
        self.vpn_pattern = re.compile(r'(VPN|加速|免费使用)')
        
        # 主要内容关键词（预定义）
        self.main_content_keywords = [
            '模特', '私拍', '国模', '户外', '露出', '泄密', '摄影师',
            '原版', '无水印', '湿地', '公园', '火儿', '合集', '完整'
        ]
        
        # 默认配置
        self.default_config = {
            "remove_links": True,
            "remove_buttons": True,
            "remove_ads": True,
            "remove_usernames": False,
            "link_based_filtering": True,
            "ad_keywords": [
                "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
                "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
                "QQ", "电话", "客服", "代理", "加盟", "投资", "理财"
            ],
            "whitelist_keywords": []  # 白名单关键词
        }

    def filter(self, text: str, config: Optional[Dict[str, Any]] = None) -> str:
        """
        执行过滤
        
        Args:
            text: 要过滤的文本
            config: 过滤配置
            
        Returns:
            过滤后的文本
        """
        if not text or not isinstance(text, str):
            return text
            
        # 合并配置
        current_config = self.default_config.copy()
        if config:
            current_config.update(config)
            
        # 检查是否包含链接
        has_links = bool(
            self.url_pattern.search(text) or 
            self.tme_pattern.search(text) or 
            self.domain_pattern.search(text)
        )
        
        # 如果启用基于链接的过滤模式，且没有链接，则只进行轻度过滤
        if current_config.get("link_based_filtering", True) and not has_links:
            return self._light_filter(text, current_config)
            
        filtered_text = text
        
        # 1. 智能移除链接
        if current_config.get("remove_links", True):
            filtered_text = self.remove_url_pattern.sub(' ', filtered_text)
            filtered_text = self.remove_tme_pattern.sub(' ', filtered_text)
            filtered_text = self.remove_username_pattern.sub(' ', filtered_text)
            filtered_text = self.remove_domain_pattern.sub(' ', filtered_text)
            
        # 2. 移除按钮文本
        if current_config.get("remove_buttons", True):
            for pattern in self.button_patterns:
                filtered_text = pattern.sub('', filtered_text)
                
        # 3. 移除广告内容
        if current_config.get("remove_ads", True):
            filtered_text = self._remove_ads(filtered_text, current_config)
            
        # 4. 移除用户名
        if current_config.get("remove_usernames", False):
            filtered_text = re.sub(r'@[a-zA-Z0-9_]+', '', filtered_text)
            
        # 5. 清理多余的空行和空格
        filtered_text = re.sub(r'\n\s*\n', '\n', filtered_text)
        filtered_text = re.sub(r' +', ' ', filtered_text)
        filtered_text = filtered_text.strip()
        
        return filtered_text

    def _remove_ads(self, text: str, config: Dict[str, Any]) -> str:
        """移除广告内容"""
        ad_keywords = config.get("ad_keywords", [])
        whitelist_keywords = config.get("whitelist_keywords", [])
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 白名单检查
            if any(kw in line for kw in whitelist_keywords):
                filtered_lines.append(line)
                continue
                
            # 检查是否包含广告关键词（但排除主要内容描述行）
            is_ad = False
            # 如果行包含实质性的中文描述内容（8个以上中文字符），则不认为是广告
            chinese_chars = self.chinese_chars_pattern.findall(line)
            has_substantial_content = len(chinese_chars) >= 8
            
            # 检查是否包含主要内容关键词
            has_main_content = any(keyword in line for keyword in self.main_content_keywords)
            
            # 如果包含主要内容关键词，降低过滤强度
            if has_main_content:
                has_substantial_content = True
            
            if not has_substantial_content:
                for keyword in ad_keywords:
                    if keyword in line:
                        is_ad = True
                        break
            
            # 检查各种广告特征
            if self.pure_link_pattern.match(line):
                is_ad = True
            
            if self.contact_pattern.search(line):
                is_ad = True
                
            if self.collection_ad_pattern.search(line):
                # 检查是否包含主要内容描述（至少5个中文字符）
                if len(self.chinese_chars_pattern.findall(line)) < 5:
                    is_ad = True
                    
            if self.number_ad_pattern.search(line) and len(line) < 20:
                is_ad = True
                
            if self.file_size_pattern.search(line):
                 if len(self.chinese_chars_pattern.findall(line)) < 5:
                    is_ad = True
                    
            if self.update_status_pattern.search(line):
                 if len(self.chinese_chars_pattern.findall(line)) < 5:
                    is_ad = True
            
            if self.price_pattern.search(line):
                is_ad = True
                
            if self.vpn_pattern.search(line):
                is_ad = True
                
            if not is_ad:
                filtered_lines.append(line)
                
        return '\n'.join(filtered_lines)

    def _light_filter(self, text: str, config: Dict[str, Any]) -> str:
        """轻度过滤函数"""
        lines = text.split('\n')
        filtered_lines = []
        whitelist_keywords = config.get("whitelist_keywords", [])
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 白名单检查
            if any(kw in line for kw in whitelist_keywords):
                filtered_lines.append(line)
                continue
            
            # 只过滤明显的广告行，保留主要内容
            is_obvious_ad = False
            
            # 检查是否是明显的广告关键词行（需要包含多个广告词）
            ad_keywords = config.get("ad_keywords", [])
            ad_count = sum(1 for keyword in ad_keywords if keyword in line)
            if ad_count >= 2:  # 需要包含2个或以上广告词才认为是广告
                is_obvious_ad = True
            
            # 检查是否是价格/付费广告行
            if self.price_pattern.search(line):
                is_obvious_ad = True
            
            # 检查是否是VPN广告行
            if self.vpn_pattern.search(line):
                is_obvious_ad = True
            
            # 保留主要内容（标签、描述等）
            if not is_obvious_ad:
                filtered_lines.append(line)
        
        filtered_text = '\n'.join(filtered_lines)
        
        # 清理多余的空行
        filtered_text = re.sub(r'\n\s*\n', '\n', filtered_text)
        filtered_text = filtered_text.strip()
        
        return filtered_text

# 全局单例实例
_global_filter = EnhancedLinkFilter()

def enhanced_link_filter(text: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    增强版链接过滤器（兼容旧接口）
    
    Args:
        text: 要过滤的文本
        config: 过滤配置
        
    Returns:
        过滤后的文本
    """
    return _global_filter.filter(text, config)

def get_enhanced_filter_config() -> Dict[str, Any]:
    """获取增强过滤器的默认配置"""
    return _global_filter.default_config.copy()

def apply_enhanced_filter_to_user_config(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """将增强过滤器配置应用到用户配置中"""
    enhanced_config = get_enhanced_filter_config()
    user_config.update(enhanced_config)
    return user_config
