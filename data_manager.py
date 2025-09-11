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
            logger.info("✅ Firebase连接初始化成功")
            
        except Exception as e:
            logger.error(f"❌ Firebase连接初始化失败: {e}")
            self._diagnose_firebase_error(e)
            self.initialized = False
    
    def _validate_firebase_credentials(self, credentials_dict: Dict[str, Any]) -> bool:
        """验证Firebase凭据格式"""
        if not isinstance(credentials_dict, dict):
            logger.error("❌ Firebase凭据必须是字典格式")
            return False
        
        required_fields = [
            'type', 'project_id', 'private_key_id', 'private_key',
            'client_email', 'client_id', 'auth_uri', 'token_uri'
        ]
        
        for field in required_fields:
            if field not in credentials_dict:
                logger.error(f"❌ Firebase凭据缺少必需字段: {field}")
                return False
            
            if not credentials_dict[field] or credentials_dict[field].startswith('your_'):
                logger.error(f"❌ Firebase凭据字段 {field} 未配置或使用占位符值")
                return False
        
        # 验证private_key格式
        private_key = credentials_dict.get('private_key', '')
        if not private_key.startswith('-----BEGIN PRIVATE KEY-----'):
            logger.error("❌ private_key格式错误：必须以 '-----BEGIN PRIVATE KEY-----' 开头")
            return False
        
        if not private_key.endswith('-----END PRIVATE KEY-----\n'):
            logger.error("❌ private_key格式错误：必须以 '-----END PRIVATE KEY-----\\n' 结尾")
            return False
        
        logger.info("✅ Firebase凭据格式验证通过")
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
    
    async def get_user_config(self, user_id: str) -> Dict[str, Any]:
        """获取用户配置"""
        if not self.initialized:
            return DEFAULT_USER_CONFIG.copy()
        
        try:
            # 使用异步方式获取文档
            import asyncio
            doc_ref = self.db.collection('users').document(str(user_id))
            
            # 在线程池中执行同步操作
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, doc_ref.get)
            
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
            import asyncio
            doc_ref = self.db.collection('users').document(str(user_id))
            
            # 获取现有配置
            loop = asyncio.get_event_loop()
            existing_doc = await loop.run_in_executor(None, doc_ref.get)
            if existing_doc.exists:
                existing_data = existing_doc.to_dict()
                # 完全替换config字段，而不是合并
                existing_data['config'] = config
                existing_data['updated_at'] = datetime.now().isoformat()
                await loop.run_in_executor(None, doc_ref.set, existing_data)
            else:
                # 新用户，直接设置
                user_data = {
                    'config': config,
                    'updated_at': datetime.now().isoformat()
                }
                await loop.run_in_executor(None, doc_ref.set, user_data)
            
            logger.info(f"用户配置保存成功: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存用户配置失败 {user_id}: {e}")
            return False
    
    async def create_user_config(self, user_id: str) -> bool:
        """创建新用户配置"""
        return await self.save_user_config(user_id, DEFAULT_USER_CONFIG.copy())
    
    async def get_all_user_ids(self) -> List[str]:
        """获取所有用户ID列表"""
        if not self.initialized:
            return []
        
        try:
            import asyncio
            # 获取所有用户文档
            loop = asyncio.get_event_loop()
            docs = await loop.run_in_executor(None, lambda: list(self.db.collection('users').stream()))
            
            user_ids = []
            for doc in docs:
                user_ids.append(doc.id)
            
            logger.info(f"📂 获取到 {len(user_ids)} 个用户ID")
            return user_ids
            
        except Exception as e:
            logger.error(f"获取所有用户ID失败: {e}")
            return []
    
    async def get_channel_pairs(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的频道组列表"""
        if not self.initialized:
            return []
        
        try:
            import asyncio
            doc_ref = self.db.collection('users').document(str(user_id))
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, doc_ref.get)
            
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
            import asyncio
            doc_ref = self.db.collection('users').document(str(user_id))
            data = {
                'channel_pairs': channel_pairs,
                'updated_at': datetime.now().isoformat()
            }
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: doc_ref.set(data, merge=True))
            logger.info(f"频道组列表保存成功: {user_id}")
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
            await self.save_user_config(user_id, config)
            logger.info(f"已更新用户 {user_id} 的监听设置")
            return True
        except Exception as e:
            logger.error(f"更新监听设置失败: {e}")
            return False
    
    # ==================== 监听任务数据管理 ====================
    
    async def create_monitoring_task(self, user_id: str, task_data: Dict[str, Any]) -> str:
        """创建监听任务"""
        try:
            task_id = task_data.get('task_id')
            if not task_id:
                task_id = f"monitor_{user_id}_{int(datetime.now().timestamp())}"
                task_data['task_id'] = task_id
            
            # 获取用户配置
            user_config = await self.get_user_config(user_id)
            
            # 初始化监听任务存储
            if 'monitoring_tasks' not in user_config:
                user_config['monitoring_tasks'] = {}
            
            # 添加任务数据
            task_data['created_at'] = datetime.now().isoformat()
            task_data['status'] = 'pending'
            user_config['monitoring_tasks'][task_id] = task_data
            
            # 保存配置
            await self.save_user_config(user_id, user_config)
            
            logger.info(f"✅ 创建监听任务: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"创建监听任务失败: {e}")
            raise
    
    async def get_monitoring_tasks(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """获取用户的监听任务列表"""
        try:
            user_config = await self.get_user_config(user_id)
            return user_config.get('monitoring_tasks', {})
        except Exception as e:
            logger.error(f"获取监听任务失败: {e}")
            return {}
    
    async def get_monitoring_task(self, user_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """获取指定的监听任务"""
        try:
            tasks = await self.get_monitoring_tasks(user_id)
            return tasks.get(task_id)
        except Exception as e:
            logger.error(f"获取监听任务失败: {e}")
            return None
    
    async def update_monitoring_task(self, user_id: str, task_id: str, updates: Dict[str, Any]) -> bool:
        """更新监听任务"""
        try:
            user_config = await self.get_user_config(user_id)
            
            if 'monitoring_tasks' not in user_config:
                user_config['monitoring_tasks'] = {}
            
            if task_id not in user_config['monitoring_tasks']:
                logger.error(f"监听任务不存在: {task_id}")
                return False
            
            # 更新任务数据
            task_data = user_config['monitoring_tasks'][task_id]
            task_data.update(updates)
            task_data['updated_at'] = datetime.now().isoformat()
            
            # 保存配置
            await self.save_user_config(user_id, user_config)
            
            logger.info(f"✅ 更新监听任务: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新监听任务失败: {e}")
            return False
    
    async def delete_monitoring_task(self, user_id: str, task_id: str) -> bool:
        """删除监听任务"""
        try:
            user_config = await self.get_user_config(user_id)
            
            if 'monitoring_tasks' not in user_config:
                return True
            
            if task_id in user_config['monitoring_tasks']:
                del user_config['monitoring_tasks'][task_id]
                await self.save_user_config(user_id, user_config)
                logger.info(f"✅ 删除监听任务: {task_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除监听任务失败: {e}")
            return False
    
    async def get_active_monitoring_tasks(self) -> List[Dict[str, Any]]:
        """获取所有活跃的监听任务"""
        try:
            active_tasks = []
            
            # 获取所有用户
            all_users = await self.get_all_user_ids()
            
            for user_id in all_users:
                tasks = await self.get_monitoring_tasks(user_id)
                for task_id, task_data in tasks.items():
                    if task_data.get('status') == 'active':
                        task_data['user_id'] = user_id
                        task_data['task_id'] = task_id
                        active_tasks.append(task_data)
            
            return active_tasks
            
        except Exception as e:
            logger.error(f"获取活跃监听任务失败: {e}")
            return []
    
    async def save_monitoring_task_stats(self, user_id: str, task_id: str, stats: Dict[str, Any]) -> bool:
        """保存监听任务统计信息"""
        try:
            updates = {
                'stats': stats,
                'last_stats_update': datetime.now().isoformat()
            }
            return await self.update_monitoring_task(user_id, task_id, updates)
        except Exception as e:
            logger.error(f"保存监听任务统计失败: {e}")
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

async def add_channel_pair(user_id: str, source_username: str, target_username: str, 
                          source_name: str = "", target_name: str = "",
                          source_id: str = "", target_id: str = "") -> bool:
    """添加频道组（主要存储用户名）"""
    return await data_manager.add_channel_pair(user_id, source_username, target_username, source_name, target_name, source_id, target_id)

async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return await data_manager.health_check()

__all__ = [
    "DataManager", "data_manager",
    "get_user_config", "save_user_config",
    "get_channel_pairs", "add_channel_pair",
    "health_check"
]




