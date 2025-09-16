"""
频道数据管理器
用于本地存储和管理频道信息，减少API调用
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ChannelDataManager:
    """频道数据管理器"""
    
    def __init__(self, data_file: str = "channel_data.json"):
        self.data_file = data_file
        self.channels_data = {}
        self.load_data()
    
    def load_data(self):
        """从本地文件加载频道数据"""
        try:
            logger.debug(f"🔍 尝试加载频道数据文件: {self.data_file}")
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.channels_data = json.load(f)
                logger.debug(f"✅ 已加载频道数据: {len(self.channels_data)} 个频道")
            else:
                self.channels_data = {}
                logger.debug(f"📝 频道数据文件不存在: {self.data_file}")
        except Exception as e:
            logger.error(f"❌ 加载频道数据失败: {e}")
            self.channels_data = {}
    
    def save_data(self):
        """保存频道数据到本地文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.channels_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 已保存频道数据: {len(self.channels_data)} 个频道")
        except Exception as e:
            logger.error(f"保存频道数据失败: {e}")
    
    def add_channel(self, channel_id: int, channel_data: Dict[str, Any]):
        """添加频道数据"""
        try:
            channel_key = str(channel_id)
            self.channels_data[channel_key] = {
                **channel_data,
                'last_verified': datetime.now().isoformat(),
                'verified': True
            }
            self.save_data()
            logger.info(f"✅ 已添加频道数据: {channel_id}")
        except Exception as e:
            logger.error(f"添加频道数据失败: {e}")
    
    def get_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """获取频道数据"""
        return self.channels_data.get(str(channel_id))
    
    def get_all_channels(self) -> List[Dict[str, Any]]:
        """获取所有频道数据"""
        return list(self.channels_data.values())
    
    def get_verified_channels(self) -> List[Dict[str, Any]]:
        """获取已验证的频道"""
        return [channel for channel in self.channels_data.values() 
                if channel.get('verified', False)]
    
    def update_channel_verification(self, channel_id: int, verified: bool):
        """更新频道验证状态"""
        try:
            channel_key = str(channel_id)
            if channel_key in self.channels_data:
                self.channels_data[channel_key]['verified'] = verified
                self.channels_data[channel_key]['last_verified'] = datetime.now().isoformat()
                if not verified:
                    # 验证失败时，添加提示信息而不是删除频道
                    self.channels_data[channel_key]['verification_error'] = "频道验证失败，请重新验证"
                else:
                    # 验证成功时，清除错误信息
                    self.channels_data[channel_key].pop('verification_error', None)
                self.save_data()
                logger.info(f"✅ 已更新频道验证状态: {channel_id} -> {verified}")
        except Exception as e:
            logger.error(f"更新频道验证状态失败: {e}")
    
    def remove_channel(self, channel_id: int):
        """移除频道数据"""
        try:
            channel_key = str(channel_id)
            if channel_key in self.channels_data:
                del self.channels_data[channel_key]
                self.save_data()
                logger.info(f"✅ 已移除频道数据: {channel_id}")
        except Exception as e:
            logger.error(f"移除频道数据失败: {e}")
    
    def get_channel_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名查找频道"""
        for channel in self.channels_data.values():
            if channel.get('username') == username:
                return channel
        return None
    
    def is_channel_verified(self, channel_id: int) -> bool:
        """检查频道是否已验证"""
        channel = self.get_channel(channel_id)
        return channel.get('verified', False) if channel else False
    
    def needs_verification(self, channel_id: int, max_age_hours: int = 24) -> bool:
        """检查频道是否需要重新验证"""
        channel = self.get_channel(channel_id)
        if not channel or not channel.get('verified', False):
            return True
        
        try:
            last_verified = datetime.fromisoformat(channel.get('last_verified', ''))
            age_hours = (datetime.now() - last_verified).total_seconds() / 3600
            return age_hours > max_age_hours
        except:
            return True
    
    def get_unverified_channels(self) -> List[Dict[str, Any]]:
        """获取未验证的频道"""
        return [channel for channel in self.channels_data.values() 
                if not channel.get('verified', False)]
    
    def get_channels_with_errors(self) -> List[Dict[str, Any]]:
        """获取验证失败的频道"""
        return [channel for channel in self.channels_data.values() 
                if channel.get('verification_error')]
    
    def clear_verification_error(self, channel_id: int):
        """清除频道的验证错误信息"""
        try:
            channel_key = str(channel_id)
            if channel_key in self.channels_data:
                self.channels_data[channel_key].pop('verification_error', None)
                self.save_data()
                logger.info(f"✅ 已清除频道验证错误: {channel_id}")
        except Exception as e:
            logger.error(f"清除频道验证错误失败: {e}")

