#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enhanced_link_filter import enhanced_link_filter

# 用户提供的新测试文本
test_text = """【25.08新增】解锁百位福利姬 ( `https://t.me/SC98K/6339)`  ✅"""

# 增强过滤配置
config = {
    "remove_links": True,
    "remove_buttons": True,
    "remove_ads": True,
    "remove_usernames": False,
    "ad_keywords": [
        "广告", "推广", "优惠", "折扣", "免费", "限时", "抢购",
        "特价", "促销", "活动", "报名", "咨询", "联系", "微信",
        "QQ", "电话", "客服", "代理", "加盟", "投资", "理财",
        "解锁", "福利", "新增"
    ]
}

print("原始文本:")
print(repr(test_text))
print("\n原始显示:")
print(test_text)
print("\n" + "="*50 + "\n")

# 应用增强过滤
filtered_text = enhanced_link_filter(test_text, config)

print("过滤后文本:")
print(repr(filtered_text))
print("\n过滤后显示:")
print(filtered_text if filtered_text else "[消息已完全过滤]")

print("\n" + "="*50 + "\n")
print("过滤分析:")
print(f"- 原始长度: {len(test_text)} 字符")
print(f"- 过滤后长度: {len(filtered_text)} 字符")
print(f"- 是否包含链接: {'是' if 'https://' in test_text else '否'}")
print(f"- 是否包含广告词: {'是' if any(keyword in test_text for keyword in ['解锁', '福利', '新增']) else '否'}")
print(f"- 过滤效果: {'完全过滤' if not filtered_text.strip() else '部分过滤'}")