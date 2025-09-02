#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询所有用户的频道组用户名信息
"""

import asyncio
from data_manager import data_manager

async def query_all_users():
    """查询所有用户的频道组信息"""
    try:
        print("正在检查数据管理器状态...")
        
        # 检查数据管理器是否已初始化
        if not data_manager.initialized:
            print("❌ 数据管理器未初始化，请检查Firebase配置")
            return
        
        print("正在查询所有用户...")
        
        # 获取所有用户文档
        users_ref = data_manager.db.collection('users')
        docs = users_ref.stream()
        
        user_count = 0
        total_pairs = 0
        
        for doc in docs:
            user_id = doc.id
            user_data = doc.to_dict()
            channel_pairs = user_data.get('channel_pairs', [])
            
            if not channel_pairs:
                continue
                
            user_count += 1
            total_pairs += len(channel_pairs)
            
            print(f"\n👤 用户 {user_id} - {len(channel_pairs)} 个频道组:")
            
            for i, pair in enumerate(channel_pairs, 1):
                source_id = pair.get('source_id', '未知')
                target_id = pair.get('target_id', '未知')
                source_name = pair.get('source_name', f'频道{i}')
                target_name = pair.get('target_name', f'目标{i}')
                source_username = pair.get('source_username', '')
                target_username = pair.get('target_username', '')
                enabled = pair.get('enabled', True)
                
                status = "✅" if enabled else "❌"
                
                print(f"  {status} 频道组 {i}")
                print(f"     📡 采集: {source_name} ({source_id})")
                if source_username:
                    print(f"         👤 用户名: @{source_username}")
                else:
                    print(f"         👤 用户名: 未保存")
                
                print(f"     📤 发布: {target_name} ({target_id})")
                if target_username:
                    print(f"         👤 用户名: @{target_username}")
                else:
                    print(f"         👤 用户名: 未保存")
        
        if user_count == 0:
            print("❌ 没有找到任何用户数据")
        else:
            print(f"\n📊 总计: {user_count} 个用户，{total_pairs} 个频道组")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(query_all_users())