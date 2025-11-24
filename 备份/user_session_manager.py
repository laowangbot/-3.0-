#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户专属Session管理器
为每个用户创建独立的Telegram客户端会话
支持本地+Render双部署架构
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from telethon import TelegramClient
import socket
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

logger = logging.getLogger(__name__)

class UserSessionManager:
    """用户专属Session管理器 - 支持多环境部署"""
    
    def __init__(self, bot_id: str, api_id: int, api_hash: str, is_render: bool = False):
        """初始化Session管理器
        
        Args:
            bot_id: 机器人ID
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            is_render: 是否在Render环境运行
        """
        self.bot_id = bot_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.is_render = is_render
        
        # 根据环境设置不同的session目录
        if is_render:
            # Render环境：使用临时目录，session数据存储在Firebase
            self.sessions_dir = f"/tmp/sessions/{bot_id}"
            self.use_firebase_sessions = True
        else:
            # 本地环境：使用持久化目录
            self.sessions_dir = f"sessions/{bot_id}"
            self.use_firebase_sessions = False
        
        self.active_sessions: Dict[str, TelegramClient] = {}
        self.session_metadata: Dict[str, Dict[str, Any]] = {}
        
        # 创建sessions目录
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        # 加载现有session元数据
        self._load_session_metadata()
        
        logger.info(f"✅ UserSessionManager初始化完成 - Bot: {bot_id}, 环境: {'Render' if is_render else '本地'}")
    
    def _get_session_path(self, user_id: str) -> str:
        """获取用户session文件路径"""
        # 兼容接口：默认返回 legacy path（不带 device），调用方可传 device_id 时自行构造
        return os.path.join(self.sessions_dir, f"user_{user_id}.session")

    def _get_session_path_for_device(self, user_id: str, device_id: str = None) -> str:
        """根据 device_id 获取用户 session 文件路径（device-specific），默认用主机名"""
        device_id = device_id or socket.gethostname()
        # 使用短的 device_id（避免路径过长）
        safe_device = str(device_id).replace(' ', '_')
        return os.path.join(self.sessions_dir, f"user_{user_id}_{safe_device}.session")
    
    def _get_metadata_path(self) -> str:
        """获取session元数据文件路径"""
        return os.path.join(self.sessions_dir, "metadata.json")
    
    def _load_session_metadata(self):
        """加载session元数据"""
        try:
            if self.use_firebase_sessions:
                # Render环境：从Firebase加载元数据
                self._load_firebase_metadata()
            else:
                # 本地环境：从文件加载元数据
                metadata_path = self._get_metadata_path()
                if os.path.exists(metadata_path):
                    import json
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        self.session_metadata = json.load(f)
                else:
                    self.session_metadata = {}
        except Exception as e:
            logger.error(f"加载session元数据失败: {e}")
            self.session_metadata = {}
    
    def _save_session_metadata(self):
        """保存session元数据"""
        try:
            if self.use_firebase_sessions:
                # Render环境：保存到Firebase
                self._save_firebase_metadata()
            else:
                # 本地环境：保存到文件
                import json
                metadata_path = self._get_metadata_path()
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(self.session_metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存session元数据失败: {e}")
    
    def _load_firebase_metadata(self):
        """从Firebase加载session元数据"""
        try:
            from multi_bot_data_manager import create_multi_bot_data_manager
            data_manager = create_multi_bot_data_manager(self.bot_id)
            
            if data_manager.initialized:
                # 从Firebase获取session元数据
                doc_ref = data_manager.db.collection('bots').document(self.bot_id).collection('system').document('session_metadata')
                doc = doc_ref.get()
                
                if doc.exists:
                    self.session_metadata = doc.to_dict()
                else:
                    self.session_metadata = {}
            else:
                logger.warning("Firebase未初始化，使用空元数据")
                self.session_metadata = {}
                
        except Exception as e:
            logger.error(f"从Firebase加载session元数据失败: {e}")
            self.session_metadata = {}
    
    def _save_firebase_metadata(self):
        """保存session元数据到Firebase"""
        try:
            from multi_bot_data_manager import create_multi_bot_data_manager
            from firebase_batch_storage import batch_set
            import asyncio
            
            data_manager = create_multi_bot_data_manager(self.bot_id)
            
            if data_manager.initialized:
                # 使用批量存储保存元数据
                collection = f"bots/{self.bot_id}/system"
                document = "session_metadata"
                
                # 异步调用批量存储
                asyncio.create_task(batch_set(collection, document, self.session_metadata, self.bot_id))
                logger.info("✅ Session元数据已加入批量存储队列")
            else:
                logger.warning("Firebase未初始化，无法保存session元数据")
                
        except Exception as e:
            logger.error(f"保存session元数据到Firebase失败: {e}")
    
    async def _save_session_to_firebase(self, user_id: str, session_data: bytes, device_id: str = None):
        """将session数据保存到Firebase"""
        try:
            from multi_bot_data_manager import create_multi_bot_data_manager
            from firebase_batch_storage import batch_set
            import base64
            
            data_manager = create_multi_bot_data_manager(self.bot_id)
            
            if data_manager.initialized:
                # 将session数据编码为base64
                session_b64 = base64.b64encode(session_data).decode('utf-8')

                # 兼容多设备：根据 device_id 保存为独立文档，防止覆盖
                device_id = device_id or socket.gethostname()

                # 使用批量存储保存session数据
                collection = f"bots/{self.bot_id}/user_sessions"
                document = f"{user_id}_{device_id}"
                data = {
                    'session_data': session_b64,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                    'bot_id': self.bot_id,
                    'user_id': user_id,
                    'device_id': device_id
                }

                # 添加到批量存储队列
                await batch_set(collection, document, data, self.bot_id)
                logger.info(f"✅ 用户 {user_id} 的session已加入批量存储队列 (device: {device_id})")
                return True
            else:
                logger.warning("Firebase未初始化，无法保存session数据")
                return False
                
        except Exception as e:
            logger.error(f"保存session到Firebase失败 {user_id}: {e}")
            return False
    
    async def _load_session_from_firebase(self, user_id: str, device_id: str = None) -> Optional[bytes]:
        """从Firebase加载session数据"""
        try:
            from multi_bot_data_manager import create_multi_bot_data_manager
            import base64
            
            data_manager = create_multi_bot_data_manager(self.bot_id)
            
            if data_manager.initialized:
                # 先尝试按 device_id 加载（优先匹配当前设备），再回退兼容旧的 document id
                device_id = device_id or socket.gethostname()

                # 优先查找 device-specific 文档
                doc_ref = data_manager.db.collection('bots').document(self.bot_id).collection('user_sessions').document(f"{user_id}_{device_id}")
                doc = doc_ref.get()
                if doc.exists:
                    session_b64 = doc.to_dict().get('session_data')
                    if session_b64:
                        session_data = base64.b64decode(session_b64)
                        logger.info(f"✅ 从Firebase加载用户 {user_id} 的session成功 (device: {device_id})")
                        return session_data

                # 向后兼容：尝试旧的以 user_id 为文档 id 的存储
                doc_ref_old = data_manager.db.collection('bots').document(self.bot_id).collection('user_sessions').document(user_id)
                doc_old = doc_ref_old.get()
                if doc_old.exists:
                    session_b64 = doc_old.to_dict().get('session_data')
                    if session_b64:
                        session_data = base64.b64decode(session_b64)
                        logger.info(f"✅ 从Firebase加载用户 {user_id} 的session成功 (legacy)")
                        return session_data

                logger.warning(f"Firebase中未找到用户 {user_id} 的session数据")
                return None
            else:
                logger.warning("Firebase未初始化，无法加载session数据")
                return None
                
        except Exception as e:
            logger.error(f"从Firebase加载session失败 {user_id}: {e}")
            return None
    
    async def create_user_session(self, user_id: str, phone_number: str = None) -> bool:
        """为用户创建新的Telegram会话
        
        Args:
            user_id: 用户ID
            phone_number: 用户手机号（可选，用于用户账号登录）
            
        Returns:
            bool: 是否创建成功
        """
        try:
            # 当前设备标识（用于区分不同设备的 session）
            device_id = socket.gethostname()
            # 优先使用 device-specific session 文件路径（兼容旧的 legacy 路径）
            session_path = self._get_session_path_for_device(user_id, device_id)
            
            # 检查是否已有有效session
            if await self._validate_existing_session(user_id):
                logger.info(f"用户 {user_id} 的session已存在且有效")
                return True
            
            # 清理无效的 session 文件（优先 device-specific，再回退 legacy）
            if os.path.exists(session_path):
                logger.info(f"用户 {user_id} 的device session无效，重新创建: {session_path}")
                os.remove(session_path)
            else:
                # 回退兼容：如存在 legacy session 文件也一并清理
                legacy_path = self._get_session_path(user_id)
                if os.path.exists(legacy_path):
                    logger.info(f"用户 {user_id} 的 legacy session 无效，重新创建: {legacy_path}")
                    os.remove(legacy_path)
            
            # 创建新的Telegram客户端
            client = TelegramClient(
                session_path,
                self.api_id,
                self.api_hash
            )
            
            await client.start()
            
            # 如果是用户账号登录（非机器人）
            if phone_number:
                try:
                    await client.sign_in(phone_number)
                    # 这里需要处理验证码等流程
                    logger.info(f"用户 {user_id} 账号登录成功")
                except SessionPasswordNeededError:
                    logger.warning(f"用户 {user_id} 需要两步验证密码")
                    # 需要用户提供密码
                    return False
                except PhoneCodeInvalidError:
                    logger.error(f"用户 {user_id} 验证码无效")
                    return False
            
            # 保存session元数据：支持同一用户下多设备
            user_meta = self.session_metadata.get(user_id, {})
            devices = user_meta.get('devices', {})

            devices[device_id] = {
                'created_at': datetime.now().isoformat(),
                'last_used': datetime.now().isoformat(),
                'phone_number': phone_number,
                'is_bot_session': phone_number is None,
                'status': 'active',
                'environment': 'render' if self.is_render else 'local',
                'device_id': device_id
            }

            user_meta['devices'] = devices
            # 方便兼容：保留 top-level summary 字段
            user_meta['last_used'] = devices[device_id]['last_used']
            user_meta['created_at'] = user_meta.get('created_at', devices[device_id]['created_at'])
            self.session_metadata[user_id] = user_meta
            self._save_session_metadata()
            
            # 如果是Render环境，将session数据保存到Firebase
            if self.use_firebase_sessions:
                try:
                    with open(session_path, 'rb') as f:
                        session_data = f.read()
                    await self._save_session_to_firebase(user_id, session_data, device_id)
                except Exception as e:
                    logger.error(f"保存session到Firebase失败: {e}")
            
            # 缓存活跃session（以 user_id@device_id 为 key 以便同时支持多设备）
            active_key = f"{user_id}@{device_id}"
            self.active_sessions[active_key] = client
            
            logger.info(f"✅ 用户 {user_id} 的session创建成功 (device: {device_id}, {'Render' if self.is_render else '本地'}环境)")
            return True
            
        except Exception as e:
            logger.error(f"创建用户session失败 {user_id}: {e}")
            return False
    
    async def _validate_existing_session(self, user_id: str) -> bool:
        """验证现有session是否有效"""
        try:
            # 优先使用 device-specific session 文件进行验证，回退兼容 legacy
            device_id = socket.gethostname()
            checked_paths = [
                self._get_session_path_for_device(user_id, device_id),
                self._get_session_path(user_id)
            ]

            for path in checked_paths:
                try:
                    if not os.path.exists(path):
                        continue
                    client = TelegramClient(
                        path,
                        self.api_id,
                        self.api_hash
                    )
                    await client.start()
                    me = await client.get_me()
                    await client.disconnect()
                    if me:
                        return True
                except Exception:
                    # 某一文件验证失败，继续尝试其它路径
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    continue

            return False
                
        except Exception as e:
            logger.warning(f"验证session失败 {user_id}: {e}")
            return False
    
    async def get_user_client(self, user_id: str) -> Optional[TelegramClient]:
        """获取用户的Telegram客户端
        
        Args:
            user_id: 用户ID
            
        Returns:
            TelegramClient: 用户专属的客户端实例
        """
        try:
            # 如果客户端已在缓存中，直接返回（尝试匹配 user@device 首选项，然后回退到任意 device）
            device_id = socket.gethostname()
            active_key = f"{user_id}@{device_id}"
            if active_key in self.active_sessions:
                # 更新 metadata 中对应设备的 last_used
                if user_id in self.session_metadata:
                    devices = self.session_metadata[user_id].get('devices', {})
                    if device_id in devices:
                        devices[device_id]['last_used'] = datetime.now().isoformat()
                        self.session_metadata[user_id]['last_used'] = devices[device_id]['last_used']
                        self._save_session_metadata()
                return self.active_sessions[active_key]

            # 如果未命中 device-specific 缓存，尝试返回该用户任一已缓存客户端（方便对接旧逻辑）
            for key, client in list(self.active_sessions.items()):
                if key.startswith(f"{user_id}@"):
                    # 更新对应 metadata
                    dev = key.split('@', 1)[1]
                    if user_id in self.session_metadata:
                        devices = self.session_metadata[user_id].get('devices', {})
                        if dev in devices:
                            devices[dev]['last_used'] = datetime.now().isoformat()
                            self.session_metadata[user_id]['last_used'] = devices[dev]['last_used']
                            self._save_session_metadata()
                    return client
            
            # 尝试加载现有session
            session_path = self._get_session_path(user_id)
            session_loaded = False
            
            # 检查本地 session 文件：优先 device-specific path，再回退 legacy
            device_id = socket.gethostname()
            device_path = self._get_session_path_for_device(user_id, device_id)
            legacy_path = self._get_session_path(user_id)

            if os.path.exists(device_path):
                session_path = device_path
                session_loaded = True
            elif os.path.exists(legacy_path):
                session_path = legacy_path
                session_loaded = True
            elif self.use_firebase_sessions:
                # Render环境：尝试从Firebase加载session（优先匹配当前设备）
                session_data = await self._load_session_from_firebase(user_id, device_id)
                if session_data:
                    # 将session数据写入 device-specific 临时文件
                    with open(device_path, 'wb') as f:
                        f.write(session_data)
                    session_path = device_path
                    session_loaded = True
                    logger.info(f"✅ 从Firebase恢复用户 {user_id} 的session (device: {device_id})")
            
            if session_loaded:
                client = TelegramClient(
                    session_path,
                    self.api_id,
                    self.api_hash
                )
                
                await client.start()
                
                # 验证session有效性
                me = await client.get_me()
                if me:
                    self.active_sessions[user_id] = client
                    
                    # 更新元数据
                    if user_id in self.session_metadata:
                        self.session_metadata[user_id]['last_used'] = datetime.now().isoformat()
                        self._save_session_metadata()
                    
                    logger.info(f"✅ 加载用户 {user_id} 的session成功 ({'Render' if self.is_render else '本地'}环境)")
                    return client
                else:
                    await client.disconnect()
                    logger.warning(f"用户 {user_id} 的session无效")
                    return None
            else:
                logger.warning(f"用户 {user_id} 的session不存在")
                return None
                
        except Exception as e:
            logger.error(f"获取用户客户端失败 {user_id}: {e}")
            return None
    
    async def delete_user_session(self, user_id: str) -> bool:
        """删除用户的session"""
        try:
            # 断开连接
            if user_id in self.active_sessions:
                await self.active_sessions[user_id].disconnect()
                del self.active_sessions[user_id]
            
            # 删除session文件
            # 删除 device-specific 与 legacy 两种可能的 session 文件
            device_id = socket.gethostname()
            device_path = self._get_session_path_for_device(user_id, device_id)
            legacy_path = self._get_session_path(user_id)

            for session_path in (device_path, legacy_path):
                if os.path.exists(session_path):
                    os.remove(session_path)
                    # 同时删除journal文件
                    journal_path = session_path + "-journal"
                    if os.path.exists(journal_path):
                        os.remove(journal_path)
            
            # 删除元数据（全部设备）
            if user_id in self.session_metadata:
                # 如果启用了 Firebase，会尝试删除每个 device 对应的文档
                try:
                    from multi_bot_data_manager import create_multi_bot_data_manager
                    data_manager = create_multi_bot_data_manager(self.bot_id)
                    if data_manager.initialized:
                        devices = self.session_metadata[user_id].get('devices', {})
                        for dev in devices.keys():
                            try:
                                data_manager.db.collection('bots').document(self.bot_id).collection('user_sessions').document(f"{user_id}_{dev}").delete()
                            except Exception:
                                pass
                except Exception:
                    pass

                del self.session_metadata[user_id]
                self._save_session_metadata()
            
            logger.info(f"✅ 删除用户 {user_id} 的session成功")
            return True
            
        except Exception as e:
            logger.error(f"删除用户session失败 {user_id}: {e}")
            return False
    
    async def cleanup_inactive_sessions(self, days: int = 30):
        """清理不活跃的session"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            inactive_users = []
            
            for user_id, metadata in self.session_metadata.items():
                last_used = datetime.fromisoformat(metadata.get('last_used', '1970-01-01'))
                if last_used < cutoff_date:
                    inactive_users.append(user_id)
            
            for user_id in inactive_users:
                logger.info(f"清理不活跃session: {user_id}")
                await self.delete_user_session(user_id)
            
            logger.info(f"✅ 清理完成，删除了 {len(inactive_users)} 个不活跃session")
            
        except Exception as e:
            logger.error(f"清理不活跃session失败: {e}")
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """获取session统计信息"""
        try:
            total_sessions = len(self.session_metadata)
            active_sessions = len(self.active_sessions)
            
            # 按类型统计
            bot_sessions = sum(1 for m in self.session_metadata.values() if m.get('is_bot_session', False))
            user_sessions = total_sessions - bot_sessions
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'bot_sessions': bot_sessions,
                'user_sessions': user_sessions,
                'sessions_dir': self.sessions_dir,
                'bot_id': self.bot_id
            }
            
        except Exception as e:
            logger.error(f"获取session统计失败: {e}")
            return {}
    
    async def close_all_sessions(self):
        """关闭所有活跃session"""
        try:
            for user_id, client in self.active_sessions.items():
                try:
                    await client.disconnect()
                    logger.info(f"关闭用户 {user_id} 的session")
                except Exception as e:
                    logger.error(f"关闭用户 {user_id} session失败: {e}")
            
            self.active_sessions.clear()
            logger.info("✅ 所有session已关闭")
            
        except Exception as e:
            logger.error(f"关闭所有session失败: {e}")

# ==================== 导出函数 ====================

def create_user_session_manager(bot_id: str, api_id: int, api_hash: str, is_render: bool = False) -> UserSessionManager:
    """创建用户Session管理器实例
    
    Args:
        bot_id: 机器人ID
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        is_render: 是否在Render环境运行
    """
    return UserSessionManager(bot_id, api_id, api_hash, is_render)

def create_user_session_manager_from_config() -> UserSessionManager:
    """从配置文件创建用户Session管理器实例"""
    from config import get_config
    config = get_config()
    
    return UserSessionManager(
        bot_id=config['bot_id'],
        api_id=config['api_id'],
        api_hash=config['api_hash'],
        is_render=config.get('is_render', False)
    )


    # 设备管理接口：列出设备与踢出设备（用户级）
    
async def list_user_devices(manager: UserSessionManager, user_id: str) -> Dict[str, Any]:
    """列出指定用户的所有设备信息（从 metadata 中读取）"""
    try:
        if user_id not in manager.session_metadata:
            return {}
        return manager.session_metadata[user_id].get('devices', {})
    except Exception as e:
        logger.error(f"列出用户设备失败 {user_id}: {e}")
        return {}


async def kick_user_device(manager: UserSessionManager, user_id: str, device_id: str) -> bool:
    """踢出指定用户的某个设备（删除对应 session 文件 + Firebase 文档 + 元数据）"""
    try:
        # 断开缓存中的连接（user@device key）
        active_key = f"{user_id}@{device_id}"
        if active_key in manager.active_sessions:
            try:
                await manager.active_sessions[active_key].disconnect()
            except Exception:
                pass
            del manager.active_sessions[active_key]

        # 删除本地 session 文件（device-specific + legacy guard）
        device_path = manager._get_session_path_for_device(user_id, device_id)
        legacy_path = manager._get_session_path(user_id)
        for p in (device_path, legacy_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
                    journal = p + "-journal"
                    if os.path.exists(journal):
                        os.remove(journal)
            except Exception:
                pass

        # 删除 Firebase 文档（若启用）
        try:
            from multi_bot_data_manager import create_multi_bot_data_manager
            data_manager = create_multi_bot_data_manager(manager.bot_id)
            if data_manager.initialized:
                try:
                    data_manager.db.collection('bots').document(manager.bot_id).collection('user_sessions').document(f"{user_id}_{device_id}").delete()
                except Exception:
                    pass
        except Exception:
            pass

        # 更新 metadata
        if user_id in manager.session_metadata:
            devices = manager.session_metadata[user_id].get('devices', {})
            if device_id in devices:
                del devices[device_id]
                manager.session_metadata[user_id]['devices'] = devices
                # 更新 summary
                manager.session_metadata[user_id]['last_used'] = max((d.get('last_used') for d in devices.values()), default=manager.session_metadata[user_id].get('created_at'))
                if not devices:
                    # 如果无设备则删除该用户元数据
                    del manager.session_metadata[user_id]
                manager._save_session_metadata()

        logger.info(f"✅ 踢出用户 {user_id} 的设备 {device_id} 完成")
        return True
    except Exception as e:
        logger.error(f"踢出用户设备失败 {user_id}@{device_id}: {e}")
        return False

__all__ = [
    "UserSessionManager",
    "create_user_session_manager",
    "create_user_session_manager_from_config"
]
