#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户专属Session使用示例
展示如何在主机器人中集成用户专属session系统
"""

import asyncio
import logging
from user_session_manager import UserSessionManager
from config import get_config

logger = logging.getLogger(__name__)

class EnhancedTelegramBot:
    """增强版Telegram机器人，支持用户专属session"""
    
    def __init__(self):
        self.config = get_config()
        self.bot_id = self.config.get('bot_id', 'default_bot')
        self.is_render = self.config.get('is_render', False)
        
        # 初始化用户session管理器（自动检测环境）
        self.session_manager = UserSessionManager(
            bot_id=self.bot_id,
            api_id=self.config['api_id'],
            api_hash=self.config['api_hash'],
            is_render=self.is_render
        )
        
        # 主机器人客户端（用于接收用户命令）
        self.main_client = None
    
    async def initialize(self):
        """初始化机器人"""
        try:
            logger.info("🚀 初始化增强版机器人...")
            
            # 初始化主机器人客户端
            from telethon import TelegramClient
            self.main_client = TelegramClient(
                f"sessions/{self.bot_id}/main_bot.session",
                self.config['api_id'],
                self.config['api_hash'],
                bot_token=self.config['bot_token']
            )
            
            await self.main_client.start()
            logger.info("✅ 主机器人客户端启动成功")
            
            # 设置消息处理器
            self.main_client.add_event_handler(self.handle_message)
            
            logger.info("🎯 机器人初始化完成，等待消息...")
            
        except Exception as e:
            logger.error(f"❌ 机器人初始化失败: {e}")
    
    async def handle_message(self, event):
        """处理用户消息"""
        try:
            user_id = str(event.sender_id)
            message_text = event.message.message
            
            logger.info(f"收到用户 {user_id} 的消息: {message_text}")
            
            # 根据命令处理不同功能
            if message_text.startswith('/start'):
                await self.handle_start_command(event, user_id)
            elif message_text.startswith('/create_session'):
                await self.handle_create_session_command(event, user_id)
            elif message_text.startswith('/my_channels'):
                await self.handle_my_channels_command(event, user_id)
            elif message_text.startswith('/session_stats'):
                await self.handle_session_stats_command(event, user_id)
            else:
                await event.reply("🤖 请使用 /start 查看可用命令")
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    async def handle_start_command(self, event, user_id: str):
        """处理开始命令"""
        try:
            welcome_text = f"""
🤖 **欢迎使用增强版搬运机器人！**

👤 **用户ID:** `{user_id}`
🔧 **机器人ID:** `{self.bot_id}`
🌍 **运行环境:** {'☁️ Render云端' if self.is_render else '💻 本地开发'}

📋 **可用命令:**
• `/create_session` - 创建您的专属session
• `/my_channels` - 管理您的频道
• `/session_stats` - 查看session统计
• `/help` - 获取帮助信息

💡 **新功能:**
• 每个用户都有独立的Telegram会话
• 更好的数据隔离和安全性
• 支持用户账号登录（用于访问私密频道）
• 支持本地+Render双部署架构
• Session数据自动同步到Firebase

🚀 开始使用吧！
            """
            
            await event.reply(welcome_text)
            
        except Exception as e:
            logger.error(f"处理开始命令失败: {e}")
    
    async def handle_create_session_command(self, event, user_id: str):
        """处理创建session命令"""
        try:
            # 检查是否已有session
            existing_client = await self.session_manager.get_user_client(user_id)
            if existing_client:
                await event.reply("✅ 您已经有一个活跃的session了！")
                return
            
            # 创建新session
            success = await self.session_manager.create_user_session(user_id)
            
            if success:
                await event.reply(f"""
✅ **Session创建成功！**

👤 **用户ID:** `{user_id}`
🔧 **机器人ID:** `{self.bot_id}`
📁 **Session文件:** `sessions/{self.bot_id}/user_{user_id}.session`

🎯 **现在您可以:**
• 使用 `/my_channels` 管理频道
• 访问私密频道（需要用户账号登录）
• 享受更好的数据隔离

💡 **提示:** 您的session数据完全独立，不会与其他用户冲突。
                """)
            else:
                await event.reply("❌ Session创建失败，请稍后重试。")
                
        except Exception as e:
            logger.error(f"处理创建session命令失败: {e}")
            await event.reply("❌ 创建session时发生错误。")
    
    async def handle_my_channels_command(self, event, user_id: str):
        """处理我的频道命令"""
        try:
            # 获取用户专属客户端
            user_client = await self.session_manager.get_user_client(user_id)
            
            if not user_client:
                await event.reply("""
❌ **您还没有创建session！**

请先使用 `/create_session` 创建您的专属session，然后才能管理频道。
                """)
                return
            
            # 获取用户的频道列表
            try:
                # 这里可以添加获取用户频道列表的逻辑
                await event.reply(f"""
📋 **您的频道管理**

👤 **用户ID:** `{user_id}`
🔧 **Session状态:** ✅ 活跃

📡 **频道功能:**
• 添加采集频道
• 配置目标频道
• 设置过滤规则
• 启动监听任务

💡 **提示:** 使用您的专属session，可以访问更多频道功能。
                """)
                
            except Exception as e:
                logger.error(f"获取用户频道失败: {e}")
                await event.reply("❌ 获取频道信息失败，请检查您的session状态。")
                
        except Exception as e:
            logger.error(f"处理我的频道命令失败: {e}")
    
    async def handle_session_stats_command(self, event, user_id: str):
        """处理session统计命令"""
        try:
            stats = await self.session_manager.get_session_stats()
            
            stats_text = f"""
📊 **Session统计信息**

🔧 **机器人ID:** `{self.bot_id}`
📁 **Session目录:** `{stats.get('sessions_dir', 'N/A')}`

📈 **统计数据:**
• 总Session数: `{stats.get('total_sessions', 0)}`
• 活跃Session数: `{stats.get('active_sessions', 0)}`
• 机器人Session: `{stats.get('bot_sessions', 0)}`
• 用户Session: `{stats.get('user_sessions', 0)}`

👤 **您的Session状态:** {'✅ 活跃' if user_id in self.session_manager.active_sessions else '❌ 未激活'}
            """
            
            await event.reply(stats_text)
            
        except Exception as e:
            logger.error(f"处理session统计命令失败: {e}")
    
    async def run(self):
        """运行机器人"""
        try:
            await self.initialize()
            
            # 定期清理不活跃的session
            asyncio.create_task(self._periodic_cleanup())
            
            # 保持运行
            await self.main_client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"机器人运行失败: {e}")
        finally:
            await self.cleanup()
    
    async def _periodic_cleanup(self):
        """定期清理任务"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时清理一次
                await self.session_manager.cleanup_inactive_sessions(days=7)
            except Exception as e:
                logger.error(f"定期清理失败: {e}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.main_client:
                await self.main_client.disconnect()
            
            await self.session_manager.close_all_sessions()
            logger.info("✅ 资源清理完成")
            
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

# ==================== 使用示例 ====================

async def main():
    """主函数"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建并运行机器人
    bot = EnhancedTelegramBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
