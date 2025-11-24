#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频道访问诊断工具
诊断获取消息失败的问题
"""

import asyncio
import sys
import os
from pyrogram import Client
from pyrogram.errors import ChatAdminRequired, ChannelPrivate, FloodWait, UsernameNotOccupied

# 预设API配置
API_ID = 29112215
API_HASH = "ddd2a2c75e3018ff6abf0aa4add47047"
BOT_TOKEN = "8293428958:AAHKEGZN1dRWr0ubOT2rj32PJuFwDX49O-0"

class ChatAccessDiagnostic:
    """频道访问诊断类"""
    
    def __init__(self):
        self.client = None
    
    async def start_client(self):
        """启动客户端"""
        try:
            self.client = Client(
                "diagnostic_client",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=BOT_TOKEN
            )
            
            await self.client.start()
            print("✅ 客户端连接成功")
            return True
            
        except Exception as e:
            print(f"❌ 客户端连接失败: {e}")
            return False
    
    async def diagnose_chat_access(self, chat_id: str):
        """诊断频道访问问题"""
        print(f"\n🔍 开始诊断频道访问: {chat_id}")
        print("-" * 50)
        
        try:
            # 1. 检查频道是否存在
            print("1️⃣ 检查频道是否存在...")
            try:
                chat = await self.client.get_chat(chat_id)
                print(f"✅ 频道存在: {chat.title}")
                print(f"   频道类型: {chat.type}")
                print(f"   频道ID: {chat.id}")
                if hasattr(chat, 'username') and chat.username:
                    print(f"   用户名: @{chat.username}")
            except Exception as e:
                print(f"❌ 频道不存在或无法访问: {e}")
                return False
            
            # 2. 检查机器人权限
            print("\n2️⃣ 检查机器人权限...")
            try:
                bot_member = await self.client.get_chat_member(chat_id, "me")
                print(f"✅ 机器人是频道成员")
                print(f"   状态: {bot_member.status}")
                print(f"   权限: {bot_member.privileges if hasattr(bot_member, 'privileges') else '无特殊权限'}")
            except Exception as e:
                print(f"❌ 无法获取机器人成员信息: {e}")
                return False
            
            # 3. 检查是否可以获取消息历史
            print("\n3️⃣ 检查消息历史访问...")
            try:
                message_count = 0
                async for message in self.client.get_chat_history(chat_id, limit=5):
                    message_count += 1
                    print(f"   消息 {message_count}: ID={message.id}, 类型={type(message.media).__name__ if message.media else '文本'}")
                
                if message_count > 0:
                    print(f"✅ 可以访问消息历史，找到 {message_count} 条消息")
                else:
                    print("⚠️ 频道中没有消息")
                    
            except Exception as e:
                print(f"❌ 无法访问消息历史: {e}")
                return False
            
            # 4. 检查特定消息ID范围
            print("\n4️⃣ 检查特定消息ID范围...")
            try:
                # 获取最近的消息ID
                recent_messages = []
                async for message in self.client.get_chat_history(chat_id, limit=10):
                    recent_messages.append(message.id)
                
                if recent_messages:
                    min_id = min(recent_messages)
                    max_id = max(recent_messages)
                    print(f"   最近消息ID范围: {min_id} - {max_id}")
                    print(f"   建议测试范围: {min_id-5} - {max_id}")
                else:
                    print("   频道中没有消息")
                    
            except Exception as e:
                print(f"❌ 无法获取消息ID范围: {e}")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ 诊断过程中发生错误: {e}")
            return False
    
    async def get_chat_info(self, chat_id: str):
        """获取频道详细信息"""
        try:
            chat = await self.client.get_chat(chat_id)
            
            print(f"\n📋 频道详细信息:")
            print(f"   标题: {chat.title}")
            print(f"   类型: {chat.type}")
            print(f"   ID: {chat.id}")
            
            if hasattr(chat, 'username') and chat.username:
                print(f"   用户名: @{chat.username}")
            
            if hasattr(chat, 'description') and chat.description:
                print(f"   描述: {chat.description}")
            
            if hasattr(chat, 'members_count') and chat.members_count:
                print(f"   成员数: {chat.members_count}")
            
            return chat
            
        except Exception as e:
            print(f"❌ 获取频道信息失败: {e}")
            return None
    
    async def suggest_solutions(self, chat_id: str, error_type: str):
        """建议解决方案"""
        print(f"\n💡 解决方案建议:")
        print("-" * 30)
        
        if "Chat not found" in error_type:
            print("1️⃣ 频道不存在或ID错误")
            print("   - 检查频道ID是否正确")
            print("   - 确认频道是否被删除")
            print("   - 尝试使用频道用户名 @channel_name")
            
        elif "ChatAdminRequired" in error_type:
            print("1️⃣ 需要管理员权限")
            print("   - 将机器人添加为频道管理员")
            print("   - 给予机器人读取消息的权限")
            
        elif "ChannelPrivate" in error_type:
            print("1️⃣ 频道是私有的")
            print("   - 将机器人添加到频道")
            print("   - 或者使用公开频道进行测试")
            
        elif "FloodWait" in error_type:
            print("1️⃣ 触发频率限制")
            print("   - 等待一段时间后重试")
            print("   - 减少API调用频率")
            
        elif "UsernameNotOccupied" in error_type:
            print("1️⃣ 用户名不存在")
            print("   - 检查用户名是否正确")
            print("   - 确认频道是否改名或删除")
        
        print("\n2️⃣ 通用解决方案:")
        print("   - 确保机器人已添加到频道")
        print("   - 检查频道ID格式是否正确 (例如: -1001234567890)")
        print("   - 尝试使用频道用户名而不是ID")
        print("   - 确认频道不是私有的")

async def main():
    """主函数"""
    print("🔍 频道访问诊断工具")
    print("=" * 50)
    
    diagnostic = ChatAccessDiagnostic()
    
    # 启动客户端
    if not await diagnostic.start_client():
        return
    
    try:
        # 获取要诊断的频道ID
        chat_id = input("\n请输入要诊断的频道ID或用户名: ").strip()
        
        if not chat_id:
            print("❌ 频道ID不能为空")
            return
        
        # 诊断频道访问
        success = await diagnostic.diagnose_chat_access(chat_id)
        
        if success:
            print("\n✅ 频道访问正常")
            # 获取详细信息
            await diagnostic.get_chat_info(chat_id)
        else:
            print("\n❌ 频道访问有问题")
            # 建议解决方案
            await diagnostic.suggest_solutions(chat_id, "Chat not found")
        
        # 询问是否测试另一个频道
        another = input("\n是否诊断另一个频道? (y/n): ").strip().lower()
        if another in ['y', 'yes']:
            await main()
        
    except Exception as e:
        print(f"❌ 诊断过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if diagnostic.client:
            await diagnostic.client.stop()
            print("\n✅ 诊断完成")

if __name__ == "__main__":
    asyncio.run(main())




















