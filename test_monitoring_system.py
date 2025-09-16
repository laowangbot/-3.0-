#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听系统功能测试脚本
测试监听系统是否能正常监听到信息并搬运
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from simple_monitor import get_simple_monitor
from monitoring_engine import RealTimeMonitoringEngine
from cloning_engine import create_cloning_engine
from pyrogram import Client
from config import get_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MonitoringSystemTester:
    """监听系统测试器"""
    
    def __init__(self):
        self.config = get_config()
        self.client = None
        self.simple_monitor = None
        self.realtime_monitor = None
        
    async def setup(self):
        """设置测试环境"""
        try:
            api_id = self.config.get('api_id')
            api_hash = self.config.get('api_hash')
            
            if not api_id or not api_hash:
                logger.error("❌ 未找到API配置")
                return False
            
            # 创建客户端
            self.client = Client("test_monitoring", api_id=api_id, api_hash=api_hash)
            
            # 启动客户端
            await self.client.start()
            logger.info("✅ 客户端已启动")
            
            # 获取当前用户信息
            me = await self.client.get_me()
            logger.info(f"👤 当前用户: {me.first_name} (ID: {me.id})")
            
            # 初始化监听器
            self.simple_monitor = get_simple_monitor(self.client)
            
            # 初始化实时监听引擎
            cloning_engine = create_cloning_engine(self.client, self.config)
            self.realtime_monitor = RealTimeMonitoringEngine(self.client, cloning_engine, self.config)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 设置测试环境失败: {e}")
            return False
    
    async def test_simple_monitor(self, source_channel: str, target_channel: str, user_id: int):
        """测试简单监听器"""
        try:
            logger.info("🧪 测试简单监听器...")
            
            # 创建监听任务
            success, message = await self.simple_monitor.start_monitoring(
                source_channel, target_channel, user_id
            )
            
            if not success:
                logger.error(f"❌ 简单监听器测试失败: {message}")
                return False
            
            logger.info(f"✅ 简单监听器测试成功: {message}")
            
            # 获取监听状态
            status = self.simple_monitor.get_monitoring_status()
            logger.info(f"📊 监听状态: {status}")
            
            # 测试连接
            user_tasks = self.simple_monitor.get_user_tasks(user_id)
            if user_tasks:
                task = user_tasks[0]
                test_result = await self.simple_monitor.test_monitoring(task['task_id'])
                logger.info(f"🔍 连接测试结果: {test_result}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 简单监听器测试失败: {e}")
            return False
    
    async def test_realtime_monitor(self, source_channel: str, target_channel: str, user_id: str):
        """测试实时监听引擎"""
        try:
            logger.info("🧪 测试实时监听引擎...")
            
            # 启动实时监听系统
            await self.realtime_monitor.start_monitoring()
            logger.info("✅ 实时监听系统已启动")
            
            # 创建监听任务
            source_channels = [{
                'channel_id': source_channel,
                'channel_name': f'测试源频道_{source_channel}',
                'channel_username': source_channel if source_channel.startswith('@') else None
            }]
            
            task_id = await self.realtime_monitor.create_monitoring_task(
                user_id=user_id,
                target_channel=target_channel,
                source_channels=source_channels,
                config={'monitoring_mode': 'realtime'}
            )
            
            logger.info(f"✅ 实时监听任务创建成功: {task_id}")
            
            # 获取监听状态
            status = self.realtime_monitor.get_monitoring_status()
            logger.info(f"📊 实时监听状态: {status}")
            
            # 测试消息处理器
            test_result = await self.realtime_monitor.test_message_handlers(task_id)
            logger.info(f"🔍 消息处理器测试结果: {test_result}")
            
            return True, task_id
            
        except Exception as e:
            logger.error(f"❌ 实时监听引擎测试失败: {e}")
            return False, None
    
    async def test_message_processing(self, source_channel: str):
        """测试消息处理功能"""
        try:
            logger.info("🧪 测试消息处理功能...")
            
            # 尝试获取源频道的最新消息
            messages = []
            async for message in self.client.get_chat_history(source_channel, limit=5):
                messages.append({
                    'id': message.id,
                    'text': message.text or message.caption or '媒体消息',
                    'date': message.date,
                    'media_type': self._get_media_type(message)
                })
            
            logger.info(f"📋 获取到 {len(messages)} 条消息:")
            for i, msg in enumerate(messages, 1):
                logger.info(f"  {i}. ID: {msg['id']}, 类型: {msg['media_type']}, 内容: {msg['text'][:50]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 消息处理测试失败: {e}")
            return False
    
    def _get_media_type(self, message):
        """获取消息媒体类型"""
        if message.photo:
            return "照片"
        elif message.video:
            return "视频"
        elif message.document:
            return "文档"
        elif message.audio:
            return "音频"
        elif message.voice:
            return "语音"
        elif message.sticker:
            return "贴纸"
        elif message.animation:
            return "动画"
        elif message.video_note:
            return "视频笔记"
        elif message.text:
            return "文本"
        else:
            return "未知"
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            if self.simple_monitor:
                await self.simple_monitor.stop_all_monitoring()
                logger.info("✅ 简单监听器已停止")
            
            if self.realtime_monitor:
                await self.realtime_monitor.stop_monitoring()
                logger.info("✅ 实时监听引擎已停止")
            
            if self.client:
                await self.client.stop()
                logger.info("✅ 客户端已停止")
                
        except Exception as e:
            logger.error(f"❌ 清理测试环境失败: {e}")

async def main():
    """主测试函数"""
    print("🧪 监听系统功能测试")
    print("=" * 50)
    
    # 获取用户输入
    print("\n📝 请输入测试配置:")
    source_channel = input("源频道 (例如: @xsm58 或 -1001234567890): ").strip()
    target_channel = input("目标频道 (例如: @xsm53 或 -1001234567890): ").strip()
    
    if not source_channel or not target_channel:
        print("❌ 源频道和目标频道不能为空")
        return
    
    # 创建测试器
    tester = MonitoringSystemTester()
    
    try:
        # 设置测试环境
        if not await tester.setup():
            return
        
        # 获取用户ID
        me = await tester.client.get_me()
        user_id = me.id
        
        print(f"\n📋 测试配置:")
        print(f"• 源频道: {source_channel}")
        print(f"• 目标频道: {target_channel}")
        print(f"• 用户ID: {user_id}")
        
        # 测试消息处理
        print(f"\n🔍 测试消息处理功能...")
        if await tester.test_message_processing(source_channel):
            print("✅ 消息处理功能正常")
        else:
            print("❌ 消息处理功能异常")
        
        # 测试简单监听器
        print(f"\n🔍 测试简单监听器...")
        if await tester.test_simple_monitor(source_channel, target_channel, user_id):
            print("✅ 简单监听器功能正常")
        else:
            print("❌ 简单监听器功能异常")
        
        # 测试实时监听引擎
        print(f"\n🔍 测试实时监听引擎...")
        success, task_id = await tester.test_realtime_monitor(source_channel, target_channel, str(user_id))
        if success:
            print("✅ 实时监听引擎功能正常")
            print(f"💡 任务ID: {task_id}")
        else:
            print("❌ 实时监听引擎功能异常")
        
        print(f"\n⏰ 监听系统已启动，请在源频道发送消息进行测试...")
        print(f"💡 观察下面的日志输出，应该看到消息监听和转发信息")
        print(f"⏹️ 按 Ctrl+C 停止测试")
        
        try:
            # 持续运行测试
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n⏹️ 用户停止测试")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
    finally:
        # 清理测试环境
        await tester.cleanup()
        print("✅ 测试完成")

if __name__ == "__main__":
    print("🧪 监听系统功能测试")
    print("=" * 50)
    print("⚠️ 请确保：")
    print("1. 已配置正确的API凭据")
    print("2. User API已登录")
    print("3. 有源频道和目标频道的访问权限")
    print("4. 在测试期间在源频道发送消息")
    print("=" * 50)
    
    asyncio.run(main())

