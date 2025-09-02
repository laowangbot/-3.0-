#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接查询数据库中的频道用户名信息
"""

import os
import json
import asyncio
from typing import Dict, Any, List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置环境变量
os.environ['PYTHONPATH'] = os.getcwd()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    print("❌ 请安装Firebase依赖: pip install firebase-admin")
    exit(1)

async def query_channel_usernames():
    """直接查询Firebase数据库中的频道用户名信息"""
    try:
        print("正在连接Firebase数据库...")
        
        # 从环境变量获取Firebase配置
        firebase_credentials_str = os.getenv("FIREBASE_CREDENTIALS")
        firebase_project_id = os.getenv("FIREBASE_PROJECT_ID")
        
        if not firebase_credentials_str or not firebase_project_id:
            print("❌ 缺少Firebase配置信息")
            return
        
        # 解析Firebase凭据
        firebase_credentials = json.loads(firebase_credentials_str)
        
        # 初始化Firebase
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred, {
                'projectId': firebase_project_id,
            })
        
        # 获取Firestore客户端
        db = firestore.client()
        
        print("正在查询所有用户的频道组信息...")
        
        # 查询所有用户
        users_ref = db.collection('users')
        users = users_ref.stream()
        
        total_users = 0
        total_groups = 0
        groups_with_usernames = 0
        
        for user_doc in users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            total_users += 1
            print(f"\n👤 用户ID: {user_id}")
            
            # 获取频道组信息
            channel_pairs = user_data.get('channel_pairs', [])
            
            if not channel_pairs:
                print("   📋 无频道组")
                continue
            
            print(f"   📊 频道组数量: {len(channel_pairs)}")
            total_groups += len(channel_pairs)
            
            # 检查每个频道组的用户名信息
            for i, pair in enumerate(channel_pairs, 1):
                source_username = pair.get('source_username', '')
                target_username = pair.get('target_username', '')
                source_display_name = pair.get('source_display_name', '未知')
                target_display_name = pair.get('target_display_name', '未知')
                source_id = pair.get('source_id', '')
                target_id = pair.get('target_id', '')
                
                has_usernames = bool(source_username or target_username)
                if has_usernames:
                    groups_with_usernames += 1
                
                print(f"   ✅ 频道组 {i}")
                print(f"      📡 采集: {source_display_name} ({source_id})")
                if source_username:
                    print(f"         📝 用户名: @{source_username}")
                print(f"      📤 发布: {target_display_name} ({target_id})")
                if target_username:
                    print(f"         📝 用户名: @{target_username}")
                
                if not has_usernames:
                    print(f"         ⚠️ 此频道组无用户名信息")
        
        print(f"\n📊 统计信息:")
        print(f"   👥 总用户数: {total_users}")
        print(f"   📋 总频道组数: {total_groups}")
        print(f"   📝 有用户名的频道组: {groups_with_usernames}")
        print(f"   📈 用户名覆盖率: {groups_with_usernames/total_groups*100:.1f}%" if total_groups > 0 else "   📈 用户名覆盖率: 0%")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(query_channel_usernames())