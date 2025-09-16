#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地数据管理器
使用JSON文件进行本地数据存储
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from config import DEFAULT_USER_CONFIG

logger = logging.getLogger(__name__)

class LocalDataManager:
    """本地数据管理器类"""
    
    def __init__(self, bot_id: str = "default_bot"):
        """初始化本地数据管理器
        
        Args:
            bot_id: 机器人ID，用于数据分离
        """
        self.bot_id = bot_id
        self.data_dir = f"data/{bot_id}"
        self.users_dir = os.path.join(self.data_dir, "users")
        self.initialized = False
        self._init_local_storage()
    
    def _init_local_storage(self):
        """初始化本地存储目录"""
        try:
            # 创建数据目录
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.users_dir, exist_ok=True)
            
            # 创建索引文件
            self.index_file = os.path.join(self.data_dir, "index.json")
            if not os.path.exists(self.index_file):
                self._save_index({})
            
            self.initialized = True
            logger.debug(f"✅ 本地存储初始化成功 (Bot: {self.bot_id})")
            
        except Exception as e:
            logger.error(f"❌ 本地存储初始化失败: {e}")
            self.initialized = False
    
    def _get_user_file_path(self, user_id: str) -> str:
        """获取用户数据文件路径"""
        return os.path.join(self.users_dir, f"{user_id}.json")
    
    def _save_index(self, index_data: Dict[str, Any]):
        """保存索引文件"""
        try:
            import tempfile
            import shutil
            
            # 使用临时文件避免锁定问题
            temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.json')
            try:
                json.dump(index_data, temp_file, ensure_ascii=False, indent=2)
                temp_file.close()
                
                # 原子性替换
                shutil.move(temp_file.name, self.index_file)
            except Exception as e:
                # 清理临时文件
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                raise e
        except Exception as e:
            logger.error(f"保存索引文件失败: {e}")
    
    def _load_index(self) -> Dict[str, Any]:
        """加载索引文件"""
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载索引文件失败: {e}")
            return {}
    
    def _save_user_data(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """保存用户数据"""
        try:
            import tempfile
            import shutil
            
            user_file = self._get_user_file_path(user_id)
            
            # 使用临时文件避免锁定问题
            temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.json')
            try:
                json.dump(user_data, temp_file, ensure_ascii=False, indent=2)
                temp_file.close()
                
                # 原子性替换
                shutil.move(temp_file.name, user_file)
            except Exception as e:
                # 清理临时文件
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                raise e
            
            # 更新索引
            index_data = self._load_index()
            index_data[user_id] = {
                'last_updated': datetime.now().isoformat(),
                'bot_id': self.bot_id
            }
            self._save_index(index_data)
            
            return True
        except Exception as e:
            logger.error(f"保存用户数据失败 {user_id}: {e}")
            return False
    
    def _load_user_data(self, user_id: str) -> Dict[str, Any]:
        """加载用户数据"""
        try:
            user_file = self._get_user_file_path(user_id)
            if os.path.exists(user_file):
                with open(user_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载用户数据失败 {user_id}: {e}")
            return {}
    
    async def get_user_config(self, user_id: str) -> Dict[str, Any]:
        """获取用户配置"""
        if not self.initialized:
            return DEFAULT_USER_CONFIG.copy()
        
        try:
            user_data = self._load_user_data(user_id)
            return user_data.get('config', DEFAULT_USER_CONFIG.copy())
        except Exception as e:
            logger.error(f"获取用户配置失败 {user_id}: {e}")
            return DEFAULT_USER_CONFIG.copy()
    
    async def save_user_config(self, user_id: str, config: Dict[str, Any]) -> bool:
        """保存用户配置"""
        if not self.initialized:
            return False
        
        try:
            user_data = self._load_user_data(user_id)
            user_data['config'] = config
            user_data['updated_at'] = datetime.now().isoformat()
            return self._save_user_data(user_id, user_data)
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
            user_data = self._load_user_data(user_id)
            return user_data.get('channel_pairs', [])
        except Exception as e:
            logger.error(f"获取频道组列表失败 {user_id}: {e}")
            return []
    
    async def save_channel_pairs(self, user_id: str, channel_pairs: List[Dict[str, Any]]) -> bool:
        """保存频道组列表"""
        if not self.initialized:
            return False
        
        try:
            user_data = self._load_user_data(user_id)
            user_data['channel_pairs'] = channel_pairs
            user_data['updated_at'] = datetime.now().isoformat()
            return self._save_user_data(user_id, user_data)
        except Exception as e:
            logger.error(f"保存频道组列表失败 {user_id}: {e}")
            return False
    
    async def add_channel_pair(self, user_id: str, source_username: str, target_username: str, 
                              source_name: str = "", target_name: str = "", 
                              source_id: str = "", target_id: str = "") -> bool:
        """添加频道组"""
        try:
            channel_pairs = await self.get_channel_pairs(user_id)
            
            # 生成新的频道组ID
            pair_id = f"pair_{len(channel_pairs) + 1}_{int(datetime.now().timestamp())}"
            
            # 检测私密频道
            is_private_source = self._detect_private_channel(source_username, source_id)
            is_private_target = self._detect_private_channel(target_username, target_id)
            
            new_pair = {
                'id': pair_id,
                'source_username': source_username,
                'target_username': target_username,
                'source_name': source_name,
                'target_name': target_name,
                'source_id': source_id,
                'target_id': target_id,
                'is_private_source': is_private_source,
                'is_private_target': is_private_target,
                'enabled': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            channel_pairs.append(new_pair)
            success = await self.save_channel_pairs(user_id, channel_pairs)
            
            if success:
                logger.info(f"添加频道组成功: {user_id} -> {pair_id}")
            
            return success
            
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
                # 清理过滤配置
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
    
    async def get_task_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务历史"""
        try:
            user_data = self._load_user_data(user_id)
            task_history = user_data.get('task_history', [])
            return task_history[-limit:] if task_history else []
        except Exception as e:
            logger.error(f"获取任务历史失败 {user_id}: {e}")
            return []
    
    async def save_task_history(self, user_id: str, task_data: Dict[str, Any]) -> bool:
        """保存任务历史"""
        try:
            user_data = self._load_user_data(user_id)
            task_history = user_data.get('task_history', [])
            
            task_data['timestamp'] = datetime.now().isoformat()
            task_history.append(task_data)
            
            # 限制历史记录数量
            if len(task_history) > 100:
                task_history = task_history[-100:]
            
            user_data['task_history'] = task_history
            user_data['updated_at'] = datetime.now().isoformat()
            return self._save_user_data(user_id, user_data)
        except Exception as e:
            logger.error(f"保存任务历史失败 {user_id}: {e}")
            return False
    
    async def get_all_users(self) -> List[str]:
        """获取当前机器人的所有用户ID"""
        if not self.initialized:
            return []
        
        try:
            index_data = self._load_index()
            return [user_id for user_id, data in index_data.items() 
                   if data.get('bot_id') == self.bot_id]
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.initialized:
                return {
                    'status': 'error',
                    'message': '本地存储未初始化',
                    'bot_id': self.bot_id,
                    'timestamp': datetime.now().isoformat()
                }
            
            # 检查目录是否存在
            if not os.path.exists(self.data_dir):
                return {
                    'status': 'error',
                    'message': '数据目录不存在',
                    'bot_id': self.bot_id,
                    'timestamp': datetime.now().isoformat()
                }
            
            return {
                'status': 'healthy',
                'message': '本地存储连接正常',
                'bot_id': self.bot_id,
                'data_dir': self.data_dir,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'本地存储连接异常: {str(e)}',
                'bot_id': self.bot_id,
                'timestamp': datetime.now().isoformat()
            }

# ==================== 导出函数 ====================

def create_local_data_manager(bot_id: str) -> LocalDataManager:
    """创建本地数据管理器实例"""
    return LocalDataManager(bot_id)

__all__ = [
    "LocalDataManager",
    "create_local_data_manager"
]
