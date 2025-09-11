#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from pyrogram import Client

async def test_bot():
    """测试Bot Token是否有效"""
    try:
        # 使用配置中的Bot Token
        bot_token = "8293428958:AAHKEGZN1dRWr0ubOT2rj32PJuFwDX49O-0"
        api_id = 29112215
        api_hash = "ddd2a2c75e3018ff6abf0aa4add47047"
        
        print("🔍 正在测试Bot Token...")
        
        # 创建客户端
        client = Client(
            "test_bot",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token
        )
        
        # 启动客户端
        await client.start()
        print("✅ Bot客户端启动成功")
        
        # 获取机器人信息
        me = await client.get_me()
        print(f"✅ 机器人信息: @{me.username} ({me.first_name})")
        print(f"✅ 机器人ID: {me.id}")
        
        # 停止客户端
        await client.stop()
        print("✅ 测试完成，Bot Token有效")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    asyncio.run(test_bot())




