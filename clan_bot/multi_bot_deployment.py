# ==================== 多机器人部署管理器 ====================
"""
多机器人部署管理器
支持在Render上部署多个机器人实例，使用云存储管理用户会话
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client

# 配置日志
from log_config import get_logger
logger = get_logger(__name__)

@dataclass
class BotConfig:
    """机器人配置"""
    instance_name: str
    api_id: int
    api_hash: str
    bot_token: str
    webhook_url: Optional[str] = None

class FirebaseStorageManager:
    """Firebase云存储管理器"""
    
    def __init__(self, credentials_path: str = None):
        """初始化Firebase存储"""
        try:
            if credentials_path:
                # 从文件加载凭证
                cred = credentials.Certificate(credentials_path)
            else:
                # 从环境变量加载凭证（Render部署）
                cred_dict = json.loads(os.getenv('FIREBASE_CREDENTIALS', '{}'))
                cred = credentials.Certificate(cred_dict)
            
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.info("✅ Firebase存储初始化成功")
        except Exception as e:
            logger.error(f"❌ Firebase存储初始化失败: {e}")
            self.db = None
    
    async def save_user_data(self, user_id: int, data: Dict[str, Any], collection: str = "users"):
        """保存用户数据到云存储"""
        if not self.db:
            logger.warning("Firebase未初始化，跳过保存")
            return False
        
        try:
            doc_ref = self.db.collection(collection).document(str(user_id))
            doc_ref.set(data)
            logger.debug(f"✅ 用户数据已保存: {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存用户数据失败: {e}")
            return False
    
    async def load_user_data(self, user_id: int, collection: str = "users") -> Optional[Dict[str, Any]]:
        """从云存储加载用户数据"""
        if not self.db:
            logger.warning("Firebase未初始化，返回空数据")
            return None
        
        try:
            doc_ref = self.db.collection(collection).document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                logger.debug(f"✅ 用户数据已加载: {user_id}")
                return doc.to_dict()
            else:
                logger.debug(f"用户数据不存在: {user_id}")
                return None
        except Exception as e:
            logger.error(f"❌ 加载用户数据失败: {e}")
            return None
    
    async def save_session(self, user_id: int, session_data: bytes):
        """保存用户会话到云存储"""
        try:
            # 将会话数据转换为Base64字符串
            import base64
            session_str = base64.b64encode(session_data).decode('utf-8')
            
            data = {
                'session_data': session_str,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            
            return await self.save_user_data(user_id, data, "sessions")
        except Exception as e:
            logger.error(f"❌ 保存会话失败: {e}")
            return False
    
    async def load_session(self, user_id: int) -> Optional[bytes]:
        """从云存储加载用户会话"""
        try:
            data = await self.load_user_data(user_id, "sessions")
            if data and 'session_data' in data:
                import base64
                return base64.b64decode(data['session_data'])
            return None
        except Exception as e:
            logger.error(f"❌ 加载会话失败: {e}")
            return None

class MultiBotDeploymentManager:
    """多机器人部署管理器"""
    
    def __init__(self):
        """初始化部署管理器"""
        self.bot_instance = os.getenv('BOT_INSTANCE', 'bot1')
        self.storage = FirebaseStorageManager()
        self.config = self._load_bot_config()
        self.clients = {}
        
        logger.info(f"🚀 初始化机器人实例: {self.bot_instance}")
    
    def _load_bot_config(self) -> BotConfig:
        """加载机器人配置"""
        instance_configs = {
            'bot1': {
                'api_id': int(os.getenv('BOT1_API_ID', '0')),
                'api_hash': os.getenv('BOT1_API_HASH', ''),
                'bot_token': os.getenv('BOT1_TOKEN', ''),
            },
            'bot2': {
                'api_id': int(os.getenv('BOT2_API_ID', '0')),
                'api_hash': os.getenv('BOT2_API_HASH', ''),
                'bot_token': os.getenv('BOT2_TOKEN', ''),
            },
            'bot3': {
                'api_id': int(os.getenv('BOT3_API_ID', '0')),
                'api_hash': os.getenv('BOT3_API_HASH', ''),
                'bot_token': os.getenv('BOT3_TOKEN', ''),
            }
        }
        
        config_data = instance_configs.get(self.bot_instance, instance_configs['bot1'])
        
        return BotConfig(
            instance_name=self.bot_instance,
            api_id=config_data['api_id'],
            api_hash=config_data['api_hash'],
            bot_token=config_data['bot_token'],
            webhook_url=os.getenv('WEBHOOK_URL')
        )
    
    async def create_client(self, user_id: int) -> Optional[Client]:
        """为用户创建Pyrogram客户端"""
        try:
            # 尝试从云存储加载会话
            session_data = await self.storage.load_session(user_id)
            
            if session_data:
                # 使用现有会话创建客户端
                client = Client(
                    name=f"user_{user_id}",
                    api_id=self.config.api_id,
                    api_hash=self.config.api_hash,
                    session_string=session_data.decode('utf-8') if isinstance(session_data, bytes) else session_data
                )
            else:
                # 创建新客户端
                client = Client(
                    name=f"user_{user_id}",
                    api_id=self.config.api_id,
                    api_hash=self.config.api_hash
                )
            
            self.clients[user_id] = client
            logger.info(f"✅ 客户端创建成功: {user_id}")
            return client
            
        except Exception as e:
            logger.error(f"❌ 创建客户端失败: {e}")
            return None
    
    async def save_user_session(self, user_id: int):
        """保存用户会话到云存储"""
        if user_id in self.clients:
            client = self.clients[user_id]
            try:
                # 获取会话字符串
                session_string = await client.export_session_string()
                await self.storage.save_session(user_id, session_string.encode('utf-8'))
                logger.info(f"✅ 用户会话已保存: {user_id}")
            except Exception as e:
                logger.error(f"❌ 保存用户会话失败: {e}")
    
    async def cleanup_user_session(self, user_id: int):
        """清理用户会话"""
        if user_id in self.clients:
            try:
                client = self.clients[user_id]
                await client.stop()
                del self.clients[user_id]
                logger.info(f"✅ 用户会话已清理: {user_id}")
            except Exception as e:
                logger.error(f"❌ 清理用户会话失败: {e}")
    
    def get_bot_info(self) -> Dict[str, Any]:
        """获取机器人信息"""
        return {
            'instance': self.bot_instance,
            'api_id': self.config.api_id,
            'bot_token': self.config.bot_token[:10] + "..." if self.config.bot_token else "未设置",
            'active_clients': len(self.clients),
            'storage_available': self.storage.db is not None
        }

# 全局部署管理器实例
deployment_manager = MultiBotDeploymentManager()

# 导出函数
async def get_user_client(user_id: int) -> Optional[Client]:
    """获取用户客户端"""
    return await deployment_manager.create_client(user_id)

async def save_user_session(user_id: int):
    """保存用户会话"""
    await deployment_manager.save_user_session(user_id)

async def cleanup_user_session(user_id: int):
    """清理用户会话"""
    await deployment_manager.cleanup_user_session(user_id)

def get_bot_info() -> Dict[str, Any]:
    """获取机器人信息"""
    return deployment_manager.get_bot_info()

# ==================== 使用示例 ====================
if __name__ == "__main__":
    async def test_deployment():
        """测试部署管理器"""
        manager = MultiBotDeploymentManager()
        
        # 测试创建客户端
        test_user_id = 123456789
        client = await manager.create_client(test_user_id)
        
        if client:
            print("✅ 客户端创建成功")
            
            # 测试保存会话
            await manager.save_user_session(test_user_id)
            
            # 测试清理会话
            await manager.cleanup_user_session(test_user_id)
        
        # 显示机器人信息
        info = manager.get_bot_info()
        print(f"机器人信息: {info}")
    
    # 运行测试
    asyncio.run(test_deployment())
