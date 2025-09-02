#!/usr/bin/env python3
"""
检查机器人token是否有效
"""

import asyncio
import os
from pyrogram import Client
from config import get_config

async def check_bot_token():
    """检查机器人token"""
    config = get_config()
    
    print("🔍 检查机器人配置:")
    print(f"   Bot ID: {config.get('bot_id')}")
    print(f"   Bot Name: {config.get('bot_name')}")
    print(f"   Bot Token: {config.get('bot_token', '')[:8]}...")
    
    # 创建临时客户端测试token
    try:
        client = Client(
            "temp_session",
            api_id=config['api_id'],
            api_hash=config['api_hash'],
            bot_token=config['bot_token']
        )
        
        print("🚀 尝试连接机器人...")
        await client.start()
        
        # 获取机器人信息
        me = await client.get_me()
        print(f"✅ 机器人连接成功!")
        print(f"   用户名: @{me.username}")
        print(f"   名称: {me.first_name}")
        print(f"   ID: {me.id}")
        
        await client.stop()
        return True
        
    except Exception as e:
        print(f"❌ 机器人连接失败: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(check_bot_token())
