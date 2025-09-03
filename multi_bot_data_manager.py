#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多机器人数据管理器
支持按机器人ID分离数据存储
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import firebase_admin
from firebase_admin import credentials, firestore
from config import DEFAULT_USER_CONFIG

logger = logging.getLogger(__name__)

class MultiBotDataManager:
    """多机器人数据管理器类"""
    
    def __init__(self, bot_id: str):
        """初始化数据管理器
        
        Args:
            bot_id: 机器人ID，用于数据分离
        """
        self.bot_id = bot_id
        self.db = None
        self.initialized = False
        self._init_firebase()
    
    def _init_firebase(self):
        """初始化Firebase连接"""
        try:
            # 获取配置
            from config import get_config
            config = get_config()
            firebase_credentials = config.get('firebase_credentials')
            
            # 验证Firebase凭据
            if not self._validate_firebase_credentials(firebase_credentials):
                logger.error("❌ Firebase凭据验证失败")
                self.initialized = False
                return
            
            # 初始化Firebase应用
            if not firebase_admin._apps:
                cred = credentials.Certificate(firebase_credentials)
                firebase_admin.initialize_app(cred, {
                    'projectId': config.get('firebase_project_id')
                })
            
            # 获取Firestore数据库实例
            self.db = firestore.client()
            self.initialized = True
            logger.info(f"✅ Firebase连接初始化成功 (Bot: {self.bot_id})")
            
        except Exception as e:
            logger.error(f"❌ Firebase连接初始化失败: {e}")
            self._diagnose_firebase_error(e)
            self.initialized = False
    
    def _validate_firebase_credentials(self, credentials: Dict[str, Any]) -> bool:
        """验证Firebase凭据"""
        required_fields = [
            'type', 'project_id', 'private_key_id', 'private_key',
            'client_email', 'client_id', 'auth_uri', 'token_uri'
        ]
        
        for field in required_fields:
            if field not in credentials or not credentials[field]:
                logger.error(f"❌ Firebase凭据缺少必需字段: {field}")
                return False
            
            # 检查是否为占位符值
            if str(credentials[field]).startswith('your_'):
                logger.error(f"❌ Firebase凭据字段 {field} 仍为占位符值")
                return False
        
        return True
    
    def _diagnose_firebase_error(self, error: Exception):
        """诊断Firebase错误并提供解决建议"""
        error_str = str(error).lower()
        
        if 'malformedframing' in error_str or 'pem file' in error_str:
            logger.error("🔧 Firebase PEM证书格式错误诊断:")
            logger.error("   1. 检查 private_key 字段是否包含完整的证书内容")
            logger.error("   2. 确保换行符已正确转义为 \\n")
            logger.error("   3. 验证证书以 '-----BEGIN PRIVATE KEY-----' 开头")
            logger.error("   4. 验证证书以 '-----END PRIVATE KEY-----' 结尾")
            logger.error("   5. 检查JSON格式是否正确（无多余逗号、引号匹配）")
        
        elif 'certificate' in error_str:
            logger.error("🔧 Firebase证书错误诊断:")
            logger.error("   1. 重新下载Firebase服务账号密钥文件")
            logger.error("   2. 确保使用正确的项目凭据")
            logger.error("   3. 检查服务账号是否有足够权限")
        
        elif 'project' in error_str:
            logger.error("🔧 Firebase项目错误诊断:")
            logger.error("   1. 检查 FIREBASE_PROJECT_ID 是否正确")
            logger.error("   2. 确保项目已启用Firestore数据库")
            logger.error("   3. 验证服务账号属于正确的项目")
        
        else:
            logger.error(f"🔧 其他Firebase错误: {error}")
            logger.error("   请检查网络连接和Firebase服务状态")
    
    def _get_user_doc_ref(self, user_id: str):
        """获取用户文档引用
        
        数据结构: bots/{bot_id}/users/{user_id}
        """
        return self.db.collection('bots').document(self.bot_id).collection('users').document(str(user_id))
    
    async def get_user_config(self, user_id: str) -> Dict[str, Any]:
        """获取用户配置"""
        if not self.initialized:
            return DEFAULT_USER_CONFIG.copy()
        
        try:
            doc_ref = self._get_user_doc_ref(user_id)
            doc = doc_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                config = user_data.get('config', {})
                # 合并默认配置和用户配置
                merged_config = DEFAULT_USER_CONFIG.copy()
                merged_config.update(config)
                return merged_config
            else:
                # 创建新用户配置
                await self.create_user_config(user_id)
                return DEFAULT_USER_CONFIG.copy()
                
        except Exception as e:
            logger.error(f"获取用户配置失败 {user_id}: {e}")
            return DEFAULT_USER_CONFIG.copy()
    
    async def save_user_config(self, user_id: str, config: Dict[str, Any]) -> bool:
        """保存用户配置"""
        if not self.initialized:
            return False
        
        try:
            doc_ref = self._get_user_doc_ref(user_id)
            
            # 获取现有配置
            existing_doc = doc_ref.get()
            if existing_doc.exists:
                existing_data = existing_doc.to_dict()
                # 完全替换config字段，而不是合并
                existing_data['config'] = config
                existing_data['updated_at'] = datetime.now().isoformat()
                doc_ref.set(existing_data)
            else:
                # 新用户，直接设置
                doc_ref.set({
                    'config': config,
                    'bot_id': self.bot_id,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                })
            
            logger.info(f"用户配置保存成功: {user_id} (Bot: {self.bot_id})")
            return True
            
        except Exception as e:
            logger.error(f"保存用户配置失败 {user_id}: {e}")
            return False
    
    async def create_user_config(self, user_id: str) -> bool:
        """创建新用户配置"""
        return await self.save_user_config(user_id, DEFAULT_USER_CONFIG.copy())
    
    async def get_channel_pairs(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的频道组列表"""
        if not self.initialized:
            return []
        
        try:
            doc_ref = self._get_user_doc_ref(user_id)
            doc = doc_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                return user_data.get('channel_pairs', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"获取频道组列表失败 {user_id}: {e}")
            return []
    
    async def save_channel_pairs(self, user_id: str, channel_pairs: List[Dict[str, Any]]) -> bool:
        """保存频道组列表"""
        if not self.initialized:
            return False
        
        try:
            doc_ref = self._get_user_doc_ref(user_id)
            doc_ref.set({
                'channel_pairs': channel_pairs,
                'bot_id': self.bot_id,
                'updated_at': datetime.now().isoformat()
            }, merge=True)
            logger.info(f"频道组列表保存成功: {user_id} (Bot: {self.bot_id})")
            return True
            
        except Exception as e:
            logger.error(f"保存频道组列表失败 {user_id}: {e}")
            return False
    
    async def add_channel_pair(self, user_id: str, source_username: str, target_username: str, 
                              source_name: str = "", target_name: str = "", 
                              source_id: str = "", target_id: str = "") -> bool:
        """添加新的频道组（主要存储用户名）"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            # 检查是否已存在（基于用户名检查）
            for pair in channel_pairs:
                if pair.get('source_username') == source_username and pair.get('target_username') == target_username:
                    logger.warning(f"频道组已存在: {source_username} → {target_username}")
                    return False
            
            # 添加新频道组（主要存储用户名）
            new_pair = {
                'id': f"pair_{len(channel_pairs)}_{int(datetime.now().timestamp())}",
                'source_username': source_username,  # 主要存储：用户名
                'target_username': target_username,  # 主要存储：用户名
                'source_id': source_id,              # 辅助存储：频道ID
                'target_id': target_id,              # 辅助存储：频道ID
                'source_name': source_name or f"频道{len(channel_pairs)+1}",
                'target_name': target_name or f"目标{len(channel_pairs)+1}",
                'enabled': True,
                'bot_id': self.bot_id,
                'is_private_source': self._detect_private_channel(source_username, source_id),
                'is_private_target': self._detect_private_channel(target_username, target_id),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            channel_pairs.append(new_pair)
            return await self.save_channel_pairs(user_id, channel_pairs)
            
        except Exception as e:
            logger.error(f"添加频道组失败: {e}")
            return False
    
    def _detect_private_channel(self, username: str, channel_id: str) -> bool:
        """检测是否为私密频道"""
        try:
            # 检查用户名格式
            if username:
                if username.startswith('@c/'):
                    return True
                if username.startswith('PENDING_@c/'):
                    return True
            
            # 检查频道ID格式
            if channel_id:
                if channel_id.startswith('PENDING_@c/'):
                    return True
                if channel_id.startswith('-100') and len(channel_id) > 10:
                    return True
            
            return False
        except Exception as e:
            logger.warning(f"检测私密频道失败: {e}")
            return False
    
    async def update_channel_pair(self, user_id: str, pair_id: str, 
                                updates: Dict[str, Any]) -> bool:
        """更新频道组信息"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            for i, pair in enumerate(channel_pairs):
                if pair.get('id') == pair_id:
                    channel_pairs[i].update(updates)
                    channel_pairs[i]['updated_at'] = datetime.now().isoformat()
                    return await self.save_channel_pairs(user_id, channel_pairs)
            
            logger.warning(f"未找到频道组: {pair_id}")
            return False
            
        except Exception as e:
            logger.error(f"更新频道组失败: {e}")
            return False
    
    async def get_channel_pair_by_channels(self, user_id: str, source_id: str, target_id: str) -> Optional[Dict[str, Any]]:
        """根据源频道ID和目标频道ID查找频道组"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            for pair in channel_pairs:
                if (pair.get('source_id') == source_id and pair.get('target_id') == target_id) or \
                   (pair.get('source_id') == target_id and pair.get('target_id') == source_id):
                    return pair
            
            return None
            
        except Exception as e:
            logger.error(f"查找频道组失败: {e}")
            return None
    
    async def delete_channel_pair(self, user_id: str, pair_id: str) -> bool:
        """删除频道组"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            # 检查频道组是否存在
            pair_exists = any(pair.get('id') == pair_id for pair in channel_pairs)
            if not pair_exists:
                logger.warning(f"未找到频道组: {pair_id}")
                return False
            
            # 过滤掉要删除的频道组
            filtered_pairs = [pair for pair in channel_pairs if pair.get('id') != pair_id]
            
            # 保存更新后的频道组列表
            success = await self.save_channel_pairs(user_id, filtered_pairs)
            
            if success:
                # 直接删除对应pair_id的过滤配置
                await self._delete_channel_filter_config(user_id, pair_id)
                logger.info(f"删除频道组成功，已清理过滤配置: {pair_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"删除频道组失败: {e}")
            return False
    
    async def _delete_channel_filter_config(self, user_id: str, pair_id: str):
        """删除指定频道组的过滤配置"""
        try:
            user_config = await self.get_user_config(user_id)
            channel_filters = user_config.get('channel_filters', {})
            
            # 直接删除对应pair_id的过滤配置
            if pair_id in channel_filters:
                del channel_filters[pair_id]
                logger.info(f"删除频道过滤配置: {pair_id}")
                
                # 更新用户配置
                user_config['channel_filters'] = channel_filters
                await self.save_user_config(user_id, user_config)
            else:
                logger.info(f"未找到频道组 {pair_id} 的过滤配置")
            
        except Exception as e:
            logger.error(f"删除频道过滤配置失败: {e}")
    
    async def clear_all_channel_filter_configs(self, user_id: str):
        """清空所有频道过滤配置"""
        try:
            user_config = await self.get_user_config(user_id)
            user_config['channel_filters'] = {}
            await self.save_user_config(user_id, user_config)
            logger.info(f"清空所有频道过滤配置成功: {user_id}")
        except Exception as e:
            logger.error(f"清空所有频道过滤配置失败: {e}")
    
    async def get_all_users(self) -> List[str]:
        """获取当前机器人的所有用户ID"""
        if not self.initialized:
            return []
        
        try:
            users_ref = self.db.collection('bots').document(self.bot_id).collection('users')
            docs = users_ref.stream()
            return [doc.id for doc in docs]
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []
    
    async def migrate_from_old_structure(self, old_data_manager) -> bool:
        """从旧的数据结构迁移数据
        
        Args:
            old_data_manager: 旧的DataManager实例
        """
        try:
            logger.info(f"开始迁移数据到新结构 (Bot: {self.bot_id})")
            
            # 获取旧结构中的所有用户
            old_users_ref = old_data_manager.db.collection('users')
            old_docs = old_users_ref.stream()
            
            migrated_count = 0
            for doc in old_docs:
                user_id = doc.id
                user_data = doc.to_dict()
                
                # 迁移用户配置
                if 'config' in user_data:
                    await self.save_user_config(user_id, user_data['config'])
                
                # 迁移频道组
                if 'channel_pairs' in user_data:
                    await self.save_channel_pairs(user_id, user_data['channel_pairs'])
                
                migrated_count += 1
                logger.info(f"已迁移用户: {user_id}")
            
            logger.info(f"数据迁移完成，共迁移 {migrated_count} 个用户")
            return True
            
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.initialized:
                return {
                    'status': 'error',
                    'message': 'Firebase未初始化',
                    'bot_id': self.bot_id,
                    'timestamp': datetime.now().isoformat()
                }
            
            # 测试数据库连接
            self.db.collection('bots').document(self.bot_id).collection('health').document('test').get()
            
            return {
                'status': 'healthy',
                'message': '数据库连接正常',
                'bot_id': self.bot_id,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'数据库连接异常: {str(e)}',
                'bot_id': self.bot_id,
                'timestamp': datetime.now().isoformat()
            }

# ==================== 导出函数 ====================

def create_multi_bot_data_manager(bot_id: str) -> MultiBotDataManager:
    """创建多机器人数据管理器实例"""
    return MultiBotDataManager(bot_id)

__all__ = [
    "MultiBotDataManager",
    "create_multi_bot_data_manager"
]