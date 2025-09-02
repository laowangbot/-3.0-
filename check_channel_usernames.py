#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频道用户名查询工具
用于查询数据库中保存的频道组用户名信息
"""

import asyncio
import sys
from data_manager import get_channel_pairs

async def check_channel_usernames(user_id: str):
    """查询指定用户的频道组用户名信息"""
    try:
        print(f"正在查询用户 {user_id} 的频道组信息...")
        
        # 获取频道组列表
        channel_pairs = await get_channel_pairs(user_id)
        
        if not channel_pairs:
            print("❌ 该用户没有配置任何频道组")
            return
        
        print(f"\n📊 找到 {len(channel_pairs)} 个频道组:\n")
        
        for i, pair in enumerate(channel_pairs, 1):
            source_id = pair.get('source_id', '未知')
            target_id = pair.get('target_id', '未知')
            source_name = pair.get('source_name', f'频道{i}')
            target_name = pair.get('target_name', f'目标{i}')
            source_username = pair.get('source_username', '')
            target_username = pair.get('target_username', '')
            enabled = pair.get('enabled', True)
            
            status = "✅" if enabled else "❌"
            
            print(f"{status} 频道组 {i}")
            print(f"   📡 采集: {source_name} ({source_id})")
            if source_username:
                print(f"       👤 用户名: @{source_username}")
            else:
                print(f"       👤 用户名: 未保存")
            
            print(f"   📤 发布: {target_name} ({target_id})")
            if target_username:
                print(f"       👤 用户名: @{target_username}")
            else:
                print(f"       👤 用户名: 未保存")
            print()
        
        # 统计用户名保存情况
        source_with_username = sum(1 for pair in channel_pairs if pair.get('source_username'))
        target_with_username = sum(1 for pair in channel_pairs if pair.get('target_username'))
        
        print(f"📈 用户名保存统计:")
        print(f"   采集频道: {source_with_username}/{len(channel_pairs)} 个有用户名")
        print(f"   发布频道: {target_with_username}/{len(channel_pairs)} 个有用户名")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")

async def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("使用方法: python check_channel_usernames.py <用户ID>")
        print("示例: python check_channel_usernames.py 123456789")
        return
    
    user_id = sys.argv[1]
    await check_channel_usernames(user_id)

if __name__ == "__main__":
    asyncio.run(main())