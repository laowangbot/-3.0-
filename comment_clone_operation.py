# ==================== 评论搬运操作脚本 ====================
"""
简单的评论搬运操作脚本
用于快速搬运消息到评论区
"""

import asyncio
import logging
from pyrogram import Client
from comment_cloning_engine import CommentCloningEngine

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clone_to_comments():
    """搬运消息到评论区的操作函数"""
    
    # 1. 配置您的API信息
    API_ID = 12345678  # 替换为您的API ID
    API_HASH = "your_api_hash_here"  # 替换为您的API Hash
    
    # 2. 配置搬运参数
    SOURCE_CHANNEL = "@source_channel"  # 源频道（要搬运消息的频道）
    TARGET_CHANNEL = "@target_channel"  # 目标频道（要发送评论的频道）
    TARGET_MESSAGE_ID = 12345  # 目标消息ID（将在此消息下评论）
    MESSAGE_IDS_TO_CLONE = [12346, 12347, 12348]  # 要搬运的消息ID列表
    
    # 3. 创建客户端
    client = Client("comment_clone_session", API_ID, API_HASH)
    
    try:
        # 启动客户端
        await client.start()
        logger.info("✅ 客户端启动成功")
        
        # 创建评论搬运引擎
        engine = CommentCloningEngine(client)
        
        # 创建搬运任务
        logger.info("📝 创建评论搬运任务...")
        task_id = await engine.create_comment_clone_task(
            source_chat_id=SOURCE_CHANNEL,
            target_chat_id=TARGET_CHANNEL,
            target_message_id=TARGET_MESSAGE_ID,
            message_ids=MESSAGE_IDS_TO_CLONE
        )
        
        logger.info(f"✅ 任务创建成功: {task_id}")
        
        # 启动任务
        logger.info("🚀 开始搬运...")
        success = await engine.start_comment_clone_task(task_id)
        
        if success:
            logger.info("🎉 搬运完成！")
            
            # 显示任务结果
            status = await engine.get_task_status(task_id)
            logger.info(f"📊 处理结果:")
            logger.info(f"  • 成功: {status['processed_messages']} 条")
            logger.info(f"  • 失败: {status['failed_messages']} 条")
            logger.info(f"  • 进度: {status['progress']:.1f}%")
        else:
            logger.error("❌ 搬运失败！")
        
    except Exception as e:
        logger.error(f"❌ 操作失败: {e}")
    
    finally:
        await client.stop()

if __name__ == "__main__":
    # 运行搬运操作
    asyncio.run(clone_to_comments())
