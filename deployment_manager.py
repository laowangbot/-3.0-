#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署管理器
管理本地+Render双部署环境的配置和启动
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional
from config import get_config, validate_config

logger = logging.getLogger(__name__)

class DeploymentManager:
    """部署管理器 - 管理多环境部署"""
    
    def __init__(self):
        self.config = get_config()
        self.bot_id = self.config.get('bot_id', 'default_bot')
        self.is_render = self.config.get('is_render', False)
        self.environment = 'render' if self.is_render else 'local'
        
        logger.info(f"🚀 部署管理器初始化 - 环境: {self.environment.upper()}")
    
    def get_deployment_info(self) -> Dict[str, Any]:
        """获取部署信息"""
        return {
            'environment': self.environment,
            'bot_id': self.bot_id,
            'is_render': self.is_render,
            'use_local_storage': self.config.get('use_local_storage', False),
            'firebase_project_id': self.config.get('firebase_project_id'),
            'port': self.config.get('port', 8080),
            'render_url': self.config.get('render_external_url'),
            'session_storage': 'firebase' if self.is_render else 'local',
            'data_storage': 'local' if self.config.get('use_local_storage') else 'firebase'
        }
    
    def validate_deployment_config(self) -> bool:
        """验证部署配置"""
        try:
            logger.info(f"🔍 验证 {self.environment.upper()} 环境配置...")
            
            # 基础配置验证
            if not validate_config():
                logger.error("❌ 基础配置验证失败")
                return False
            
            # 环境特定验证
            if self.is_render:
                return self._validate_render_config()
            else:
                return self._validate_local_config()
                
        except Exception as e:
            logger.error(f"❌ 部署配置验证失败: {e}")
            return False
    
    def _validate_render_config(self) -> bool:
        """验证Render环境配置"""
        try:
            logger.info("☁️ 验证Render环境配置...")
            
            # 检查必需的环境变量
            required_vars = [
                'BOT_TOKEN', 'API_ID', 'API_HASH', 'BOT_ID',
                'FIREBASE_PROJECT_ID', 'FIREBASE_CREDENTIALS'
            ]
            
            missing_vars = []
            for var in required_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
            
            if missing_vars:
                logger.error(f"❌ Render环境缺少必需的环境变量: {', '.join(missing_vars)}")
                return False
            
            # 验证Firebase凭据
            firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
            if firebase_creds and firebase_creds.startswith('your_'):
                logger.error("❌ Firebase凭据仍为占位符值")
                return False
            
            # 验证端口配置
            port = self.config.get('port', 8080)
            if not isinstance(port, int) or port < 1000:
                logger.error(f"❌ 无效的端口配置: {port}")
                return False
            
            logger.info("✅ Render环境配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ Render环境配置验证失败: {e}")
            return False
    
    def _validate_local_config(self) -> bool:
        """验证本地环境配置"""
        try:
            logger.info("💻 验证本地环境配置...")
            
            # 检查.env文件
            if not os.path.exists('.env'):
                logger.warning("⚠️ 未找到.env文件，将使用默认配置")
            
            # 检查sessions目录
            sessions_dir = f"sessions/{self.bot_id}"
            if not os.path.exists(sessions_dir):
                logger.info(f"📁 创建sessions目录: {sessions_dir}")
                os.makedirs(sessions_dir, exist_ok=True)
            
            # 检查数据目录（如果使用本地存储）
            if self.config.get('use_local_storage'):
                data_dir = f"data/{self.bot_id}"
                if not os.path.exists(data_dir):
                    logger.info(f"📁 创建数据目录: {data_dir}")
                    os.makedirs(data_dir, exist_ok=True)
            
            logger.info("✅ 本地环境配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ 本地环境配置验证失败: {e}")
            return False
    
    async def initialize_session_manager(self):
        """初始化用户Session管理器"""
        try:
            from user_session_manager import create_user_session_manager_from_config
            
            session_manager = create_user_session_manager_from_config()
            
            logger.info(f"✅ 用户Session管理器初始化完成")
            logger.info(f"   📁 Session目录: {session_manager.sessions_dir}")
            logger.info(f"   🔄 使用Firebase存储: {session_manager.use_firebase_sessions}")
            
            return session_manager
            
        except Exception as e:
            logger.error(f"❌ 初始化Session管理器失败: {e}")
            return None
    
    async def initialize_data_manager(self):
        """初始化数据管理器"""
        try:
            if self.config.get('use_local_storage'):
                from local_data_manager import LocalDataManager
                data_manager = LocalDataManager(self.bot_id)
                logger.info("✅ 本地数据管理器初始化完成")
            else:
                from multi_bot_data_manager import create_multi_bot_data_manager
                data_manager = create_multi_bot_data_manager(self.bot_id)
                logger.info("✅ Firebase数据管理器初始化完成")
            
            return data_manager
            
        except Exception as e:
            logger.error(f"❌ 初始化数据管理器失败: {e}")
            return None
    
    def get_startup_message(self) -> str:
        """获取启动消息"""
        info = self.get_deployment_info()
        
        message = f"""
🚀 **机器人启动成功！**

🌍 **部署环境:** {info['environment'].upper()}
🤖 **机器人ID:** `{info['bot_id']}`
📊 **数据存储:** {info['data_storage'].upper()}
💾 **Session存储:** {info['session_storage'].upper()}
"""
        
        if self.is_render:
            message += f"☁️ **Render URL:** {info['render_url']}\n"
            message += f"🔌 **端口:** {info['port']}\n"
        else:
            message += f"💻 **本地开发模式**\n"
        
        message += f"""
✅ **功能状态:**
• 用户专属Session管理
• 多环境数据同步
• Firebase云端存储
• 自动环境检测

🎯 **准备就绪，等待用户连接...**
        """
        
        return message.strip()
    
    def log_deployment_info(self):
        """记录部署信息"""
        info = self.get_deployment_info()
        
        logger.info("=" * 60)
        logger.info("🚀 部署信息")
        logger.info("=" * 60)
        logger.info(f"🌍 环境: {info['environment'].upper()}")
        logger.info(f"🤖 机器人ID: {info['bot_id']}")
        logger.info(f"📊 数据存储: {info['data_storage'].upper()}")
        logger.info(f"💾 Session存储: {info['session_storage'].upper()}")
        
        if self.is_render:
            logger.info(f"☁️ Render URL: {info['render_url']}")
            logger.info(f"🔌 端口: {info['port']}")
        else:
            logger.info("💻 本地开发模式")
        
        logger.info("=" * 60)

# ==================== 启动脚本 ====================

async def start_local_deployment():
    """启动本地部署"""
    try:
        logger.info("🚀 启动本地部署...")
        
        # 设置本地环境变量
        os.environ['USE_LOCAL_STORAGE'] = 'true'
        
        deployment_manager = DeploymentManager()
        deployment_manager.log_deployment_info()
        
        # 验证配置
        if not deployment_manager.validate_deployment_config():
            logger.error("❌ 本地部署配置验证失败")
            return False
        
        # 初始化管理器
        session_manager = await deployment_manager.initialize_session_manager()
        data_manager = await deployment_manager.initialize_data_manager()
        
        if not session_manager or not data_manager:
            logger.error("❌ 管理器初始化失败")
            return False
        
        logger.info(deployment_manager.get_startup_message())
        
        # 这里可以启动主机器人
        # from main import TelegramBot
        # bot = TelegramBot()
        # await bot.run()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 本地部署启动失败: {e}")
        return False

async def start_render_deployment():
    """启动Render部署"""
    try:
        logger.info("🚀 启动Render部署...")
        
        # 确保使用Firebase存储
        os.environ['USE_LOCAL_STORAGE'] = 'false'
        
        deployment_manager = DeploymentManager()
        deployment_manager.log_deployment_info()
        
        # 验证配置
        if not deployment_manager.validate_deployment_config():
            logger.error("❌ Render部署配置验证失败")
            return False
        
        # 初始化管理器
        session_manager = await deployment_manager.initialize_session_manager()
        data_manager = await deployment_manager.initialize_data_manager()
        
        if not session_manager or not data_manager:
            logger.error("❌ 管理器初始化失败")
            return False
        
        logger.info(deployment_manager.get_startup_message())
        
        # 这里可以启动主机器人
        # from main import TelegramBot
        # bot = TelegramBot()
        # await bot.run()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Render部署启动失败: {e}")
        return False

# ==================== 导出函数 ====================

def create_deployment_manager() -> DeploymentManager:
    """创建部署管理器实例"""
    return DeploymentManager()

__all__ = [
    "DeploymentManager",
    "create_deployment_manager",
    "start_local_deployment",
    "start_render_deployment"
]
