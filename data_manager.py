# ==================== 数据管理器 ====================
"""
数据管理器
负责Firebase连接、用户配置存储、频道组管理和任务历史记录
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, auth
from config import FIREBASE_CREDENTIALS, FIREBASE_PROJECT_ID, DEFAULT_USER_CONFIG

# 配置日志 - 显示详细状态信息
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataManager:
    """数据管理器类"""
    
    def __init__(self):
        """初始化数据管理器"""
        self.db = None
        self.initialized = False
        self._init_firebase()
    
    def _init_firebase(self):
        """初始化Firebase连接"""
        try:
            # 初始化Firebase应用
            if not firebase_admin._apps:
                cred = credentials.Certificate(FIREBASE_CREDENTIALS)
                firebase_admin.initialize_app(cred, {
                    'projectId': FIREBASE_PROJECT_ID
                })
            
            # 获取Firestore数据库实例
            self.db = firestore.client()
            self.initialized = True
            logger.info("✅ Firebase连接初始化成功")
            
        except Exception as e:
            logger.error(f"❌ Firebase连接初始化失败: {e}")
            self.initialized = False
    
    async def get_user_config(self, user_id: str) -> Dict[str, Any]:
        """获取用户配置"""
        if not self.initialized:
            return DEFAULT_USER_CONFIG.copy()
        
        try:
            doc_ref = self.db.collection('users').document(str(user_id))
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
            doc_ref = self.db.collection('users').document(str(user_id))
            
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
                    'updated_at': datetime.now().isoformat()
                })
            
            logger.info(f"用户配置保存成功: {user_id}")
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
            doc_ref = self.db.collection('users').document(str(user_id))
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
            doc_ref = self.db.collection('users').document(str(user_id))
            doc_ref.set({
                'channel_pairs': channel_pairs,
                'updated_at': datetime.now().isoformat()
            }, merge=True)
            logger.info(f"频道组列表保存成功: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存频道组列表失败 {user_id}: {e}")
            return False
    
    async def add_channel_pair(self, user_id: str, source_id: str, target_id: str, 
                              source_name: str = "", target_name: str = "", 
                              source_username: str = "", target_username: str = "") -> bool:
        """添加新的频道组"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            # 检查是否已存在
            for pair in channel_pairs:
                if pair.get('source_id') == source_id and pair.get('target_id') == target_id:
                    logger.warning(f"频道组已存在: {source_id} → {target_id}")
                    return False
            
            # 添加新频道组
            new_pair = {
                'id': f"pair_{len(channel_pairs)}_{int(datetime.now().timestamp())}",
                'source_id': source_id,
                'target_id': target_id,
                'source_name': source_name or f"频道{len(channel_pairs)+1}",
                'target_name': target_name or f"目标{len(channel_pairs)+1}",
                'source_username': source_username,
                'target_username': target_username,
                'enabled': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            channel_pairs.append(new_pair)
            return await self.save_channel_pairs(user_id, channel_pairs)
            
        except Exception as e:
            logger.error(f"添加频道组失败: {e}")
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
    
    async def get_task_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务历史记录"""
        if not self.initialized:
            return []
        
        try:
            doc_ref = self.db.collection('users').document(str(user_id))
            doc = doc_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                history = user_data.get('task_history', [])
                # 按时间倒序排列，限制数量
                history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                return history[:limit]
            else:
                return []
                
        except Exception as e:
            logger.error(f"获取任务历史失败 {user_id}: {e}")
            return []
    
    async def add_task_record(self, user_id: str, task_data: Dict[str, Any]) -> bool:
        """添加任务记录"""
        try:
            history = await self.get_task_history(user_id, limit=1000)
            
            # 添加新任务记录
            task_record = {
                'id': f"task_{int(datetime.now().timestamp())}",
                'created_at': datetime.now().isoformat(),
                'status': 'completed',
                **task_data
            }
            
            history.insert(0, task_record)
            
            # 保存到数据库
            doc_ref = self.db.collection('users').document(str(user_id))
            doc_ref.set({
                'task_history': history,
                'updated_at': datetime.now().isoformat()
            }, merge=True)
            
            logger.info(f"任务记录添加成功: {user_id}")
            return True
            
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

    async def _cleanup_channel_filter_config(self, user_id: str, deleted_index: int):
        """清理指定索引的频道过滤配置（已废弃，保留用于兼容性）"""
        logger.warning("_cleanup_channel_filter_config方法已废弃，请使用_delete_channel_filter_config")
        pass

    async def clear_all_channel_filter_configs(self, user_id: str):
        """清理所有频道过滤配置"""
        try:
            user_config = await self.get_user_config(user_id)
            user_config['channel_filters'] = {}
            await self.save_user_config(user_id, user_config)
            logger.info(f"已清理用户 {user_id} 的所有频道过滤配置")
        except Exception as e:
            logger.error(f"清理所有频道过滤配置失败: {e}")

    async def get_monitor_settings(self, user_id: str) -> Dict[str, Any]:
        """获取监听设置"""
        try:
            config = await self.get_user_config(user_id)
            return {
                'monitor_enabled': config.get('monitor_enabled', False),
                'monitored_pairs': config.get('monitored_pairs', [])
            }
        except Exception as e:
            logger.error(f"获取监听设置失败: {e}")
            return {'monitor_enabled': False, 'monitored_pairs': []}
    
    async def update_monitor_settings(self, user_id: str, 
                                    monitor_enabled: bool, 
                                    monitored_pairs: List[Dict[str, Any]]) -> bool:
        """更新监听设置"""
        try:
            config = await self.get_user_config(user_id)
            config['monitor_enabled'] = monitor_enabled
            config['monitored_pairs'] = monitored_pairs
            
            return await self.save_user_config(user_id, config)
            
        except Exception as e:
            logger.error(f"更新监听设置失败: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.initialized:
                return {
                    'status': 'error',
                    'message': 'Firebase未初始化',
                    'timestamp': datetime.now().isoformat()
                }
            
            # 测试数据库连接
            self.db.collection('health').document('test').get()
            
            return {
                'status': 'healthy',
                'message': '数据库连接正常',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'数据库连接异常: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }

# 全局数据管理器实例
data_manager = DataManager()

# ==================== 导出函数 ====================
async def get_user_config(user_id: str) -> Dict[str, Any]:
    """获取用户配置"""
    return await data_manager.get_user_config(user_id)

async def save_user_config(user_id: str, config: Dict[str, Any]) -> bool:
    """保存用户配置"""
    return await data_manager.save_user_config(user_id, config)

async def get_channel_pairs(user_id: str) -> List[Dict[str, Any]]:
    """获取频道组列表"""
    return await data_manager.get_channel_pairs(user_id)

async def add_channel_pair(user_id: str, source_id: str, target_id: str, 
                          source_name: str = "", target_name: str = "",
                          source_username: str = "", target_username: str = "") -> bool:
    """添加频道组"""
    return await data_manager.add_channel_pair(user_id, source_id, target_id, source_name, target_name, source_username, target_username)

async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return await data_manager.health_check()

__all__ = [
    "DataManager", "data_manager",
    "get_user_config", "save_user_config",
    "get_channel_pairs", "add_channel_pair",
    "health_check"
]




