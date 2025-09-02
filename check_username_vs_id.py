#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中保存的是频道ID还是频道用户名
"""

import asyncio
import os
from dotenv import load_dotenv
from data_manager import DataManager

# 加载环境变量
load_dotenv()

async def check_username_vs_id():
    """检查数据库中保存的频道信息类型"""
    
    # 初始化数据管理器
    data_manager = DataManager()
    
    if not data_manager.initialized:
        print("❌ Firebase连接失败")
        return
    
    print("🔍 检查数据库中的频道信息类型...\n")
    
    try:
        # 获取所有用户的频道组信息
        users_ref = data_manager.db.collection('users')
        users = users_ref.stream()
        
        total_pairs = 0
        username_count = 0
        id_count = 0
        mixed_count = 0
        
        for user_doc in users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            if 'channel_pairs' in user_data:
                channel_pairs = user_data['channel_pairs']
                
                # 检查channel_pairs是否为列表格式
                if isinstance(channel_pairs, list):
                    for i, pair_data in enumerate(channel_pairs):
                        pair_id = f"pair_{i}"
                        if isinstance(pair_data, dict):
                            total_pairs += 1
                            
                            source_username = pair_data.get('source_username', '')
                            target_username = pair_data.get('target_username', '')
                            source_id = pair_data.get('source_id', '')
                            target_id = pair_data.get('target_id', '')
                            
                            print(f"用户 {user_id} - 频道组 {pair_id}:")
                            print(f"  源频道ID: {source_id}")
                            print(f"  源频道用户名: {source_username}")
                            print(f"  目标频道ID: {target_id}")
                            print(f"  目标频道用户名: {target_username}")
                            
                            # 分析数据类型
                            source_is_username = source_username.startswith('@') if source_username else False
                            target_is_username = target_username.startswith('@') if target_username else False
                            source_is_id = source_username.startswith('-') if source_username else False
                            target_is_id = target_username.startswith('-') if target_username else False
                            
                            if source_is_username and target_is_username:
                                print("  ✅ 类型: 两个都是用户名")
                                username_count += 1
                            elif source_is_id and target_is_id:
                                print("  ❌ 类型: 两个都是ID")
                                id_count += 1
                            else:
                                print("  ⚠️ 类型: 混合类型")
                                mixed_count += 1
                            
                            print()
                elif isinstance(channel_pairs, dict):
                    for pair_id, pair_data in channel_pairs.items():
                        total_pairs += 1
                        
                        source_username = pair_data.get('source_username', '')
                        target_username = pair_data.get('target_username', '')
                        source_id = pair_data.get('source_id', '')
                        target_id = pair_data.get('target_id', '')
                        
                        print(f"用户 {user_id} - 频道组 {pair_id}:")
                        print(f"  源频道ID: {source_id}")
                        print(f"  源频道用户名: {source_username}")
                        print(f"  目标频道ID: {target_id}")
                        print(f"  目标频道用户名: {target_username}")
                        
                        # 分析数据类型
                        source_is_username = source_username.startswith('@') if source_username else False
                        target_is_username = target_username.startswith('@') if target_username else False
                        source_is_id = source_username.startswith('-') if source_username else False
                        target_is_id = target_username.startswith('-') if target_username else False
                        
                        if source_is_username and target_is_username:
                            print("  ✅ 类型: 两个都是用户名")
                            username_count += 1
                        elif source_is_id and target_is_id:
                            print("  ❌ 类型: 两个都是ID")
                            id_count += 1
                        else:
                            print("  ⚠️ 类型: 混合类型")
                            mixed_count += 1
                        
                        print()
        
        print("\n📊 统计结果:")
        print(f"总频道组数量: {total_pairs}")
        print(f"保存用户名的频道组: {username_count} ({username_count/total_pairs*100:.1f}%)" if total_pairs > 0 else "保存用户名的频道组: 0")
        print(f"保存ID的频道组: {id_count} ({id_count/total_pairs*100:.1f}%)" if total_pairs > 0 else "保存ID的频道组: 0")
        print(f"混合类型的频道组: {mixed_count} ({mixed_count/total_pairs*100:.1f}%)" if total_pairs > 0 else "混合类型的频道组: 0")
        
        if id_count > username_count:
            print("\n⚠️ 结论: 系统主要保存的是频道ID，不是用户名")
        elif username_count > id_count:
            print("\n✅ 结论: 系统主要保存的是频道用户名")
        else:
            print("\n🤔 结论: 用户名和ID数量相当")
            
    except Exception as e:
        print(f"❌ 查询失败: {e}")

if __name__ == "__main__":
    asyncio.run(check_username_vs_id())