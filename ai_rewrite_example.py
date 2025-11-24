# ==================== AI文本改写使用示例 ====================
"""
AI文本改写使用示例
展示如何在评论搬运中使用AI文本改写功能
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_text_rewriter import AITextRewriter
from message_engine import MessageEngine
from config import DEFAULT_USER_CONFIG

async def example_ai_rewrite_in_comment_clone():
    """在评论搬运中使用AI文本改写的示例"""
    print("🚀 AI文本改写在评论搬运中的使用示例")
    
    # 配置启用AI改写
    config = DEFAULT_USER_CONFIG.copy()
    config['ai_rewrite_enabled'] = True
    config['ai_rewrite_mode'] = 'auto'
    config['ai_rewrite_intensity'] = 'medium'
    
    # 创建消息引擎（包含AI改写功能）
    print("🔧 创建消息引擎...")
    message_engine = MessageEngine(config)
    
    if not message_engine.ai_rewriter or not message_engine.ai_rewriter.model:
        print("❌ AI改写器未正确初始化")
        return
    
    print("✅ 消息引擎创建成功，AI改写功能已启用")
    
    # 模拟从源频道获取的消息文本
    source_messages = [
        {
            'id': 1001,
            'text': "最新科技资讯：科学家开发出新型AI芯片，性能提升10倍！#科技 #AI #创新",
            'type': 'text'
        },
        {
            'id': 1002,
            'text': "今日美食推荐：香辣小龙虾，夏日必备美食，快来尝尝吧！#美食 #小龙虾 #夏日",
            'type': 'text'
        },
        {
            'id': 1003,
            'text': "旅游攻略分享：云南大理古城游玩指南，不容错过的美景。#旅游 #大理 #攻略",
            'type': 'text'
        }
    ]
    
    print(f"\n📝 开始处理 {len(source_messages)} 条消息...")
    
    # 处理每条消息
    for i, message in enumerate(source_messages, 1):
        print(f"\n--- 处理消息 {i} (ID: {message['id']}) ---")
        print(f"原文: {message['text']}")
        
        # 使用AI改写文本
        rewritten_text, was_rewritten = await message_engine.process_text_with_ai(
            message['text'], 
            user_id="test_user"
        )
        
        if was_rewritten:
            print("✅ AI改写成功:")
            print(f"改写后: {rewritten_text}")
        else:
            print("ℹ️ 未进行AI改写，使用原文:")
            print(f"原文: {rewritten_text}")
    
    # 显示额度使用情况
    print(f"\n📊 最终额度使用情况:")
    quota_status = message_engine.get_ai_quota_status()
    if quota_status:
        print(f"  输入tokens: {quota_status['input_used']:,}/{quota_status['input_limit']:,} "
              f"({quota_status['input_percent']:.2f}%)")
        print(f"  输出tokens: {quota_status['output_used']:,}/{quota_status['output_limit']:,} "
              f"({quota_status['output_percent']:.2f}%)")
    
    print("\n✅ 示例演示完成")

if __name__ == "__main__":
    asyncio.run(example_ai_rewrite_in_comment_clone())