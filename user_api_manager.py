#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram User API 管理器
提供自动登录、会话管理和状态监控功能
"""

import asyncio
import logging
import os
import json
from typing import Optional, Dict, Any, List
from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, SessionPasswordNeeded, PhoneCodeInvalid, FloodWait

logger = logging.getLogger(__name__)

class UserAPIManager:
    """User API 管理器"""
    
    def __init__(self, api_id: int, api_hash: str, session_name: str = "user_session"):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.client: Optional[Client] = None
        self.is_logged_in = False
        self.login_attempts = 0
        self.max_attempts = 3
        self.pending_phone_code_hash = None
        self.pending_phone_number = None
        
    async def initialize(self) -> bool:
        """初始化 User API 客户端"""
        try:
            # 确保 sessions 目录存在
            os.makedirs("sessions", exist_ok=True)
            
            self.client = Client(
                name=self.session_name,
                api_id=self.api_id,
                api_hash=self.api_hash,
                workdir="sessions"
            )
            
            # 检查是否有现有会话
            session_path = f"sessions/{self.session_name}.session"
            if os.path.exists(session_path):
                logger.info("🔍 发现现有会话文件，跳过自动登录以避免控制台交互")
                logger.info("📱 请通过机器人界面进行登录")
                return False
            else:
                logger.info("📱 未发现会话文件，需要手动登录")
                return False
                
        except Exception as e:
            logger.error(f"❌ User API 初始化失败: {e}")
            return False
    
    async def initialize_client(self) -> bool:
        """初始化User API客户端（不自动登录）"""
        try:
            if not self.client:
                # 确保 sessions 目录存在
                os.makedirs("sessions", exist_ok=True)
                
                self.client = Client(
                    name=self.session_name,
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    workdir="sessions"
                )
            
            if not self.client.is_connected:
                await self.client.connect()
                logger.info("✅ User API客户端已连接")
            
            # 关键修复：启动客户端以激活消息处理器
            # 注意：Pyrogram Client 没有 is_running 属性，我们通过 get_me() 来激活客户端
            try:
                me = await self.client.get_me()
                if me:
                    logger.info(f"✅ User API客户端已激活: {me.first_name}")
            except Exception as e:
                logger.warning(f"⚠️ 无法激活客户端: {e}")
                # 尝试启动客户端
                try:
                    await self.client.start()
                    logger.info("✅ User API客户端已启动")
                except Exception as start_error:
                    logger.warning(f"⚠️ 启动客户端失败: {start_error}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化User API客户端失败: {e}")
            return False
    
    async def auto_login(self) -> bool:
        """自动登录（使用现有会话）"""
        try:
            # 使用超时机制避免交互式登录
            try:
                await asyncio.wait_for(self.client.start(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ 客户端启动超时，会话可能无效")
                await self.cleanup_invalid_session()
                return False
            
            # 检查是否真的登录成功
            if self.client.is_connected:
                # 尝试获取自己的信息来验证登录状态
                try:
                    me = await self.client.get_me()
                    if me:
                        self.is_logged_in = True
                        logger.info(f"✅ User API 自动登录成功，用户: {me.first_name}")
                        return True
                except Exception as e:
                    logger.warning(f"⚠️ 无法获取用户信息，会话可能无效: {e}")
                    await self.client.stop()
                    return False
            else:
                logger.warning("⚠️ 客户端未连接，会话可能无效")
                return False
                
        except AuthKeyUnregistered:
            logger.warning("⚠️ 会话已过期，需要重新登录")
            await self.cleanup_invalid_session()
            return False
        except Exception as e:
            logger.warning(f"⚠️ 自动登录失败: {e}")
            await self.cleanup_invalid_session()
            return False
    
    async def start_login_process(self, phone_number: str) -> Dict[str, Any]:
        """开始登录流程"""
        try:
            # 检查并清理可能损坏的会话文件
            session_path = f"sessions/{self.session_name}.session"
            if os.path.exists(session_path):
                try:
                    # 尝试加载现有会话文件来检查是否损坏
                    temp_client = Client(
                        name=f"{self.session_name}_temp",
                        api_id=self.api_id,
                        api_hash=self.api_hash,
                        workdir="sessions"
                    )
                    await temp_client.connect()
                    await temp_client.disconnect()
                    logger.info("✅ 现有会话文件正常")
                except Exception as e:
                    logger.warning(f"⚠️ 检测到损坏的会话文件，将清理: {e}")
                    await self.cleanup_invalid_session()
            
            # 清理之前的登录状态
            self.pending_phone_code_hash = None
            self.pending_phone_number = None
            
            if not self.client:
                # 创建新的客户端用于登录，传递 phone_number 参数
                self.client = Client(
                    name=self.session_name,
                    api_id=self.api_id,
                    api_hash=self.api_hash,
                    workdir="sessions",
                    phone_number=phone_number
                )
            
            # 确保客户端已启动
            if not self.client.is_connected:
                try:
                    # 添加超时机制
                    await asyncio.wait_for(self.client.connect(), timeout=30.0)
                    logger.info("✅ User API 客户端连接成功")
                    
                    # 关键修复：启动客户端以激活消息处理器
                    # 注意：Pyrogram Client 没有 is_running 属性，我们通过 get_me() 来激活客户端
                    try:
                        me = await self.client.get_me()
                        if me:
                            logger.info(f"✅ User API客户端已激活: {me.first_name}")
                    except Exception as e:
                        logger.warning(f"⚠️ 无法激活客户端: {e}")
                        # 尝试启动客户端
                        try:
                            await self.client.start()
                            logger.info("✅ User API 客户端已启动")
                        except Exception as start_error:
                            logger.warning(f"⚠️ 启动客户端失败: {start_error}")
                except asyncio.TimeoutError:
                    logger.error("❌ User API 客户端连接超时")
                    return {
                        "success": False,
                        "action": "connection_timeout",
                        "message": "❌ 连接超时\n\n可能的原因：\n• 网络连接不稳定\n• Telegram服务器繁忙\n\n请检查网络连接后重试"
                    }
                except Exception as e:
                    error_str = str(e).lower()
                    logger.error(f"❌ User API 客户端连接失败: {e}")
                    
                    # 根据具体错误类型提供不同的解决方案
                    if "auth" in error_str or "invalid" in error_str:
                        return {
                            "success": False,
                            "action": "auth_error",
                            "message": "❌ 认证失败\n\n可能的原因：\n• API_ID 或 API_HASH 无效\n• 请检查环境变量设置\n\n请检查配置后重试"
                        }
                    elif "network" in error_str or "connection" in error_str:
                        return {
                            "success": False,
                            "action": "network_error",
                            "message": "❌ 网络连接失败\n\n可能的原因：\n• 网络连接不稳定\n• 防火墙阻止连接\n• 代理设置问题\n\n请检查网络连接后重试"
                        }
                    elif "flood" in error_str or "wait" in error_str:
                        return {
                            "success": False,
                            "action": "flood_wait",
                            "message": "❌ 请求过于频繁\n\nTelegram限制：\n• 请等待几分钟后重试\n• 避免频繁登录尝试\n\n请稍后重试"
                        }
                    else:
                        return {
                            "success": False,
                            "action": "connection_error",
                            "message": f"❌ 连接失败：{str(e)[:100]}\n\n请检查网络连接和配置后重试"
                        }
            
            # 发送验证码
            sent_code = await self.client.send_code(phone_number)
            self.pending_phone_code_hash = sent_code.phone_code_hash
            self.pending_phone_number = phone_number
            
            return {
                "success": True,
                "action": "code_sent",
                "message": f"验证码已发送到 {phone_number}，请输入验证码（5-6位数字）："
            }
            
        except FloodWait as e:
            return {
                "success": False,
                "action": "flood_wait",
                "message": f"请等待 {e.value} 秒后重试"
            }
        except Exception as e:
            logger.error(f"❌ 发送验证码失败: {e}")
            error_msg = str(e)
            
            # 提供更友好的错误信息
            if "PHONE_NUMBER_INVALID" in error_msg:
                return {
                    "success": False,
                    "action": "invalid_phone",
                    "message": f"PHONE_NUMBER_INVALID: 手机号码格式无效"
                }
            elif "FLOOD_WAIT" in error_msg:
                return {
                    "success": False,
                    "action": "flood_wait",
                    "message": f"请求过于频繁，请稍后重试"
                }
            else:
                return {
                    "success": False,
                    "action": "error",
                    "message": f"发送验证码失败: {error_msg}"
                }
    
    async def verify_code(self, code: str) -> Dict[str, Any]:
        """验证验证码"""
        try:
            # 检查验证码是否有效
            if not code or not code.strip():
                return {
                    "success": False,
                    "action": "invalid_code",
                    "message": "验证码不能为空，请输入有效的验证码"
                }
            
            if not self.pending_phone_code_hash or not self.pending_phone_number:
                return {
                    "success": False,
                    "action": "no_pending_login",
                    "message": "没有待验证的登录请求，请先使用 /start_user_api_login 开始登录"
                }
            
            # 确保客户端已启动
            if not self.client.is_connected:
                await self.client.start()
            
            # 验证验证码
            try:
                logger.info(f"🔍 验证验证码: phone_number={self.pending_phone_number}, code={code}, phone_code_hash={self.pending_phone_code_hash}")
                # 使用正确的参数顺序：phone_number, phone_code_hash, phone_code
                await self.client.sign_in(
                    self.pending_phone_number, 
                    self.pending_phone_code_hash,
                    code
                )
                self.is_logged_in = True
                self.pending_phone_code_hash = None
                self.pending_phone_number = None
                logger.info("✅ User API 登录成功")
                return {
                    "success": True,
                    "action": "login_success",
                    "message": "登录成功！User API 已连接"
                }
                
            except SessionPasswordNeeded:
                return {
                    "success": False,
                    "action": "need_password",
                    "message": "需要两步验证密码，请输入您的两步验证密码："
                }
                
        except PhoneCodeInvalid:
            return {
                "success": False,
                "action": "invalid_code",
                "message": "验证码错误，请重试"
            }
        except Exception as e:
            error_str = str(e)
            if "PHONE_CODE_EXPIRED" in error_str:
                # 清理过期的登录状态
                self.pending_phone_code_hash = None
                self.pending_phone_number = None
                return {
                    "success": False,
                    "action": "code_expired",
                    "message": "❌ 验证码已失效\n\n可能原因：\n• 验证码已过期（5分钟）\n• 验证码已被使用过\n• 多次输入错误导致验证码被重置\n\n请使用 /resend_code 获取新验证码"
                }
            elif "PHONE_CODE_INVALID" in error_str:
                return {
                    "success": False,
                    "action": "invalid_code",
                    "message": "❌ 验证码错误\n\n请检查验证码是否正确，或重新获取验证码"
                }
            else:
                logger.error(f"❌ 验证码验证失败: {e}")
                return {
                    "success": False,
                    "action": "error",
                    "message": f"验证失败: {str(e)}"
                }
    
    async def verify_password(self, password: str) -> Dict[str, Any]:
        """验证两步验证密码"""
        try:
            # 确保客户端已启动
            if not self.client.is_connected:
                await self.client.start()
            
            await self.client.check_password(password)
            self.is_logged_in = True
            self.pending_phone_code_hash = None
            self.pending_phone_number = None
            logger.info("✅ 两步验证通过，User API 登录成功")
            return {
                "success": True,
                "action": "login_success",
                "message": "登录成功！User API 已连接"
            }
        except Exception as e:
            logger.error(f"❌ 密码验证失败: {e}")
            return {
                "success": False,
                "action": "invalid_password",
                "message": "密码错误，请重试"
            }
    
    async def logout(self) -> bool:
        """登出 User API"""
        try:
            if self.client and self.is_logged_in:
                # 检查客户端状态，避免对已终止的客户端调用stop
                if hasattr(self.client, 'is_connected') and self.client.is_connected:
                    try:
                        await self.client.stop()
                        logger.info("✅ User API 客户端已停止")
                    except Exception as stop_error:
                        if "already terminated" in str(stop_error) or "Client is already terminated" in str(stop_error):
                            logger.info("ℹ️ User API 客户端已经终止")
                        else:
                            logger.warning(f"⚠️ 停止客户端时出现警告: {stop_error}")
                
                self.is_logged_in = False
                
                # 删除会话文件
                session_path = f"sessions/{self.session_name}.session"
                if os.path.exists(session_path):
                    try:
                        os.remove(session_path)
                        logger.info("✅ 会话文件已删除")
                    except Exception as file_error:
                        logger.warning(f"⚠️ 删除会话文件失败: {file_error}")
                
                # 清理客户端引用
                self.client = None
                logger.info("✅ User API 已登出")
                return True
            else:
                logger.info("ℹ️ User API 未登录或客户端不存在")
                return True  # 返回True表示登出成功（已经是登出状态）
        except Exception as e:
            logger.error(f"❌ 登出失败: {e}")
            # 即使出错也要清理状态
            self.is_logged_in = False
            self.client = None
            return False
    
    async def restart(self) -> bool:
        """重启 User API 连接"""
        try:
            if self.client:
                await self.client.stop()
                await asyncio.sleep(2)
                return await self.auto_login()
            return False
        except Exception as e:
            logger.error(f"❌ 重启失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取登录状态"""
        session_path = f"sessions/{self.session_name}.session"
        
        # 安全地检查客户端状态
        client_connected = False
        client_exists = False
        if self.client:
            client_exists = True
            try:
                client_connected = self.client.is_connected
            except Exception as e:
                logger.warning(f"⚠️ 检查客户端连接状态时出错: {e}")
                client_connected = False
        
        return {
            "is_logged_in": self.is_logged_in,
            "session_exists": os.path.exists(session_path),
            "client_exists": client_exists,
            "client_connected": client_connected,
            "login_attempts": self.login_attempts,
            "has_pending_login": self.pending_phone_code_hash is not None
        }
    
    async def cleanup_invalid_session(self):
        """清理无效的会话文件"""
        try:
            session_path = f"sessions/{self.session_name}.session"
            if os.path.exists(session_path):
                os.remove(session_path)
                logger.info("🗑️ 已删除无效的会话文件")
        except Exception as e:
            logger.error(f"❌ 清理会话文件失败: {e}")
    
    async def resend_code(self) -> Dict[str, Any]:
        """重新发送验证码"""
        try:
            if not self.pending_phone_number:
                return {
                    "success": False,
                    "action": "no_pending_login",
                    "message": "❌ 没有待处理的登录请求\n\n请先使用 /start_user_api_login 开始登录"
                }
            
            if not self.client or not self.client.is_connected:
                return {
                    "success": False,
                    "action": "client_not_connected",
                    "message": "❌ 客户端未连接\n\n请使用 /relogin_user_api 重新开始登录"
                }
            
            # 重新发送验证码
            sent_code = await self.client.send_code(self.pending_phone_number)
            self.pending_phone_code_hash = sent_code.phone_code_hash
            
            logger.info(f"✅ 重新发送验证码到 {self.pending_phone_number}")
            return {
                "success": True,
                "action": "code_resent",
                "message": f"✅ 验证码已重新发送到 {self.pending_phone_number}\n\n请输入新的验证码（5-6位数字）："
            }
            
        except FloodWait as e:
            return {
                "success": False,
                "action": "flood_wait",
                "message": f"❌ 请求过于频繁\n\n请等待 {e.value} 秒后重试"
            }
        except Exception as e:
            logger.error(f"❌ 重新发送验证码失败: {e}")
            error_msg = str(e)
            
            if "PHONE_NUMBER_INVALID" in error_msg:
                return {
                    "success": False,
                    "action": "invalid_phone",
                    "message": "❌ 手机号码无效\n\n请使用 /relogin_user_api 重新开始登录"
                }
            elif "FLOOD_WAIT" in error_msg:
                return {
                    "success": False,
                    "action": "flood_wait",
                    "message": f"❌ 请求过于频繁\n\n请等待后重试"
                }
            else:
                return {
                    "success": False,
                    "action": "error",
                    "message": f"❌ 重新发送失败: {error_msg}"
                }
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.client:
                await self.client.stop()
        except Exception as e:
            logger.error(f"❌ 清理资源失败: {e}")

# 全局 User API 管理器实例
user_api_manager: Optional[UserAPIManager] = None

async def get_user_api_manager() -> UserAPIManager:
    """获取 User API 管理器实例"""
    global user_api_manager
    if user_api_manager is None:
        # 优先尝试从通用环境变量获取 API 凭据
        api_id = int(os.getenv('API_ID', '0'))
        api_hash = os.getenv('API_HASH', '')
        
        # 如果通用环境变量未设置，尝试从机器人特定环境变量获取
        if not api_id or not api_hash:
            # 获取机器人实例名称
            bot_instance = os.getenv('BOT_INSTANCE', 'default')
            if bot_instance and bot_instance != 'default':
                # 构建机器人特定的环境变量名
                prefix = bot_instance.upper()
                api_id = int(os.getenv(f'{prefix}_API_ID', '0'))
                api_hash = os.getenv(f'{prefix}_API_HASH', '')
                logger.info(f"🔍 尝试从机器人特定环境变量获取API配置: {prefix}_API_ID={api_id}, {prefix}_API_HASH={'已设置' if api_hash else '未设置'}")
        
        if not api_id or not api_hash:
            raise ValueError("API_ID 和 API_HASH 环境变量未设置")
        
        user_api_manager = UserAPIManager(api_id, api_hash)
        # 只初始化客户端，不自动登录
        await user_api_manager.initialize_client()
    
    return user_api_manager
