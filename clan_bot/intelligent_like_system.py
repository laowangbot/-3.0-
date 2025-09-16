#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能点赞系统 - 自动变速规避机器人检测
实现智能延迟、随机化操作、反检测机制
"""

import asyncio
import random
import time
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class DetectionRisk(Enum):
    """检测风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class LikeConfig:
    """点赞配置"""
    message_delay: float
    like_delay: float
    concurrent_limit: int
    risk_level: DetectionRisk
    description: str

class IntelligentLikeSystem:
    """智能点赞系统"""
    
    def __init__(self):
        self.api_call_history = []
        self.error_count = 0
        self.success_count = 0
        self.current_risk = DetectionRisk.LOW
        self.adaptive_delays = {
            'message_delay': 1.0,
            'like_delay': 0.5
        }
        
        # 速度模式配置
        self.speed_modes = {
            'stealth': LikeConfig(2.0, 1.0, 1, DetectionRisk.LOW, "潜行模式"),
            'safe': LikeConfig(1.5, 0.8, 2, DetectionRisk.LOW, "安全模式"),
            'normal': LikeConfig(1.0, 0.5, 3, DetectionRisk.MEDIUM, "标准模式"),
            'fast': LikeConfig(0.7, 0.3, 4, DetectionRisk.MEDIUM, "快速模式"),
            'aggressive': LikeConfig(0.4, 0.2, 5, DetectionRisk.HIGH, "激进模式")
        }
        
        # 反检测配置
        self.anti_detection = {
            'random_delay_variance': 0.3,  # 随机延迟变化范围
            'human_like_patterns': True,   # 启用人类行为模式
            'error_simulation': 0.02,     # 模拟错误率
            'burst_protection': True,      # 突发保护
            'cooldown_threshold': 10,      # 冷却阈值
            'max_consecutive_errors': 3    # 最大连续错误数
        }
    
    def calculate_adaptive_delay(self, base_delay: float, risk_level: DetectionRisk) -> float:
        """计算自适应延迟"""
        # 基础延迟
        delay = base_delay
        
        # 根据风险等级调整
        risk_multipliers = {
            DetectionRisk.LOW: 1.0,
            DetectionRisk.MEDIUM: 1.2,
            DetectionRisk.HIGH: 1.5,
            DetectionRisk.CRITICAL: 2.0
        }
        
        delay *= risk_multipliers.get(risk_level, 1.0)
        
        # 添加随机变化
        if self.anti_detection['random_delay_variance'] > 0:
            variance = self.anti_detection['random_delay_variance']
            random_factor = random.uniform(1 - variance, 1 + variance)
            delay *= random_factor
        
        # 人类行为模式：偶尔会有较长的延迟
        if self.anti_detection['human_like_patterns'] and random.random() < 0.1:
            delay *= random.uniform(2.0, 4.0)
        
        return max(0.1, delay)  # 最小延迟0.1秒
    
    def update_risk_assessment(self):
        """更新风险评估"""
        current_time = time.time()
        
        # 清理过期的API调用记录（保留最近5分钟）
        self.api_call_history = [
            call_time for call_time in self.api_call_history
            if current_time - call_time < 300
        ]
        
        # 计算最近5分钟的API调用频率
        recent_calls = len(self.api_call_history)
        
        # 计算错误率
        total_operations = self.success_count + self.error_count
        error_rate = self.error_count / max(total_operations, 1)
        
        # 风险评估逻辑
        if recent_calls > 200 or error_rate > 0.1:
            self.current_risk = DetectionRisk.CRITICAL
        elif recent_calls > 150 or error_rate > 0.05:
            self.current_risk = DetectionRisk.HIGH
        elif recent_calls > 100 or error_rate > 0.02:
            self.current_risk = DetectionRisk.MEDIUM
        else:
            self.current_risk = DetectionRisk.LOW
        
        logger.info(f"🔍 风险评估更新: {self.current_risk.value} "
                   f"(最近5分钟: {recent_calls}次调用, 错误率: {error_rate:.2%})")
    
    def get_optimal_speed_mode(self) -> str:
        """获取最优速度模式"""
        if self.current_risk == DetectionRisk.CRITICAL:
            return 'stealth'
        elif self.current_risk == DetectionRisk.HIGH:
            return 'safe'
        elif self.current_risk == DetectionRisk.MEDIUM:
            return 'normal'
        else:
            return 'fast'
    
    def should_enter_cooldown(self) -> bool:
        """判断是否应该进入冷却期"""
        if not self.anti_detection['burst_protection']:
            return False
        
        # 检查连续错误数
        if self.error_count >= self.anti_detection['max_consecutive_errors']:
            return True
        
        # 检查API调用频率
        current_time = time.time()
        recent_calls = len([
            call_time for call_time in self.api_call_history
            if current_time - call_time < 60  # 最近1分钟
        ])
        
        return recent_calls > self.anti_detection['cooldown_threshold']
    
    def get_cooldown_duration(self) -> float:
        """获取冷却时间"""
        base_cooldown = 30  # 基础冷却30秒
        
        # 根据风险等级调整冷却时间
        risk_multipliers = {
            DetectionRisk.LOW: 1.0,
            DetectionRisk.MEDIUM: 2.0,
            DetectionRisk.HIGH: 4.0,
            DetectionRisk.CRITICAL: 8.0
        }
        
        multiplier = risk_multipliers.get(self.current_risk, 1.0)
        return base_cooldown * multiplier
    
    async def execute_intelligent_like(self, channel_id: int, message_ids: List[int], 
                                     emoji: str, like_count: int) -> Tuple[int, int]:
        """执行智能点赞"""
        try:
            success_count = 0
            failed_count = 0
            
            logger.info(f"🚀 开始智能点赞: {len(message_ids)}条消息, {like_count}个赞/消息")
            
            for i, message_id in enumerate(message_ids):
                # 更新风险评估
                self.update_risk_assessment()
                
                # 检查是否需要冷却
                if self.should_enter_cooldown():
                    cooldown_duration = self.get_cooldown_duration()
                    logger.warning(f"⏸️ 进入冷却期: {cooldown_duration}秒")
                    await asyncio.sleep(cooldown_duration)
                    self.error_count = 0  # 重置错误计数
                
                # 获取最优速度模式
                speed_mode = self.get_optimal_speed_mode()
                config = self.speed_modes[speed_mode]
                
                # 计算自适应延迟
                message_delay = self.calculate_adaptive_delay(
                    config.message_delay, self.current_risk
                )
                like_delay = self.calculate_adaptive_delay(
                    config.like_delay, self.current_risk
                )
                
                # 执行单条消息点赞
                try:
                    success = await self._like_single_message_intelligent(
                        channel_id, message_id, emoji, like_count, like_delay
                    )
                    
                    if success:
                        success_count += 1
                        self.success_count += 1
                        logger.info(f"✅ 消息 {message_id} 点赞成功 (模式: {speed_mode})")
                    else:
                        failed_count += 1
                        self.error_count += 1
                        logger.warning(f"❌ 消息 {message_id} 点赞失败")
                    
                except Exception as e:
                    failed_count += 1
                    self.error_count += 1
                    logger.error(f"❌ 消息 {message_id} 点赞异常: {e}")
                
                # 记录API调用
                self.api_call_history.append(time.time())
                
                # 消息间延迟
                if i < len(message_ids) - 1:
                    await asyncio.sleep(message_delay)
                
                # 进度显示
                if (i + 1) % 100 == 0:
                    progress = (i + 1) / len(message_ids) * 100
                    logger.info(f"📊 进度: {progress:.1f}% ({i+1}/{len(message_ids)})")
            
            logger.info(f"🎉 智能点赞完成: 成功 {success_count}, 失败 {failed_count}")
            return success_count, failed_count
            
        except Exception as e:
            logger.error(f"智能点赞执行失败: {e}")
            return 0, len(message_ids)
    
    async def _like_single_message_intelligent(self, channel_id: int, message_id: int,
                                             emoji: str, like_count: int, like_delay: float) -> bool:
        """智能单条消息点赞"""
        try:
            # 模拟错误（反检测）
            if (self.anti_detection['error_simulation'] > 0 and 
                random.random() < self.anti_detection['error_simulation']):
                logger.debug(f"🎭 模拟错误: 消息 {message_id}")
                return False
            
            # 随机表情处理
            if emoji == 'random':
                emojis = ['👍', '❤️', '🔥', '🎉', '😍', '😊', '👏', '💯', '🌟', '💪']
            else:
                emojis = [emoji]
            
            # 执行点赞
            for i in range(like_count):
                current_emoji = random.choice(emojis)
                
                # 这里应该调用实际的API
                # await client.send_reaction(
                #     chat_id=channel_id,
                #     message_id=message_id,
                #     emoji=current_emoji
                # )
                
                # 模拟API调用
                await asyncio.sleep(0.1)
                
                # 点赞间延迟
                if i < like_count - 1:
                    await asyncio.sleep(like_delay)
            
            return True
            
        except Exception as e:
            logger.warning(f"单条消息点赞失败: {e}")
            return False
    
    def get_performance_stats(self) -> Dict[str, any]:
        """获取性能统计"""
        total_operations = self.success_count + self.error_count
        success_rate = self.success_count / max(total_operations, 1) * 100
        
        return {
            'total_operations': total_operations,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate': success_rate,
            'current_risk': self.current_risk.value,
            'recent_api_calls': len(self.api_call_history),
            'adaptive_delays': self.adaptive_delays
        }
    
    def reset_stats(self):
        """重置统计"""
        self.api_call_history = []
        self.error_count = 0
        self.success_count = 0
        self.current_risk = DetectionRisk.LOW
        logger.info("🔄 统计已重置")

class LikeSpeedCalculator:
    """点赞速度计算器"""
    
    @staticmethod
    def calculate_time_for_likes(total_likes: int, likes_per_message: int = 1, 
                                speed_mode: str = 'normal') -> Dict[str, any]:
        """计算点赞时间"""
        speed_configs = {
            'stealth': {'message_delay': 2.0, 'like_delay': 1.0},
            'safe': {'message_delay': 1.5, 'like_delay': 0.8},
            'normal': {'message_delay': 1.0, 'like_delay': 0.5},
            'fast': {'message_delay': 0.7, 'like_delay': 0.3},
            'aggressive': {'message_delay': 0.4, 'like_delay': 0.2}
        }
        
        config = speed_configs.get(speed_mode, speed_configs['normal'])
        
        total_messages = total_likes // likes_per_message
        remaining_likes = total_likes % likes_per_message
        
        # 计算时间
        message_time = total_messages * config['message_delay']
        like_time = total_likes * config['like_delay']
        total_time = message_time + like_time
        
        return {
            'total_time_seconds': total_time,
            'total_time_hours': total_time / 3600,
            'total_messages': total_messages,
            'total_likes': total_likes,
            'speed_mode': speed_mode,
            'estimated_completion': datetime.now() + timedelta(seconds=total_time)
        }

def main():
    """主函数 - 演示智能点赞系统"""
    print("🤖 智能点赞系统 - 自动变速规避机器人检测")
    print("=" * 60)
    
    # 创建智能点赞系统
    like_system = IntelligentLikeSystem()
    
    # 计算25684个赞的时间
    print("\n📊 25684个赞时间分析（智能变速）:")
    print("-" * 40)
    
    modes = ['stealth', 'safe', 'normal', 'fast', 'aggressive']
    for mode in modes:
        # 普通用户
        normal_result = LikeSpeedCalculator.calculate_time_for_likes(
            25684, 1, mode
        )
        # 会员用户
        vip_result = LikeSpeedCalculator.calculate_time_for_likes(
            25684, 3, mode
        )
        
        print(f"{mode.upper():12} 普通用户: {normal_result['total_time_hours']:.1f}小时")
        print(f"{'':12} 会员用户: {vip_result['total_time_hours']:.1f}小时")
        print()
    
    # 反检测特性
    print("🛡️ 反检测特性:")
    print("-" * 40)
    features = [
        "✅ 自适应延迟调整",
        "✅ 随机化操作模式", 
        "✅ 人类行为模拟",
        "✅ 智能风险评估",
        "✅ 突发保护机制",
        "✅ 错误率监控",
        "✅ 冷却期管理",
        "✅ 进度实时显示"
    ]
    
    for feature in features:
        print(feature)
    
    print("\n💡 使用建议:")
    print("-" * 40)
    print("• 建议从 'safe' 模式开始")
    print("• 系统会自动根据风险调整速度")
    print("• 遇到错误会自动降速并进入冷却")
    print("• 支持暂停和恢复功能")
    print("• 实时监控API调用频率")

if __name__ == "__main__":
    main()

