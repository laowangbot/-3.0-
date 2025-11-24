#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多模型调度策略示例
展示如何根据需求合理分配不同AI模型的使用
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict

class ModelScheduler:
    """模型调度器"""
    
    def __init__(self):
        # 定义模型及其配额 (根据用户提供的最新信息)
        self.models = {
            'gemma-3-27b': {
                'daily_quota': 14400,
                'rpm': 30,
                'quality': 'high',
                'current_usage': 0
            },
            'gemini-2.5-flash': {
                'daily_quota': 250,  # 更新为实际限制
                'rpm': 10,  # 假设值
                'quality': 'medium',
                'current_usage': 0
            },
            'gemini-2.5-flash-lite': {
                'daily_quota': 1000,  # 更新为实际限制
                'rpm': 15,  # 假设值
                'quality': 'medium',
                'current_usage': 0
            },
            'deepai': {
                'daily_quota': 50000,  # 假设值
                'rpm': 100,  # 假设值
                'quality': 'medium',
                'current_usage': 0
            }
        }
        self.daily_requests = 0
    
    def reset_daily_usage(self):
        """重置每日使用量"""
        for model in self.models.values():
            model['current_usage'] = 0
        self.daily_requests = 0
    
    def select_model(self, required_quality='medium') -> str:
        """
        根据需求选择合适的模型
        
        Args:
            required_quality: 所需质量等级 ('high', 'medium')
            
        Returns:
            str: 选中的模型名称
        """
        # 检查gemma-3-27b模型（主要处理模型）
        if self.models['gemma-3-27b']['current_usage'] < self.models['gemma-3-27b']['daily_quota']:
            return 'gemma-3-27b'
        
        # 检查Gemini模型作为备用
        if required_quality == 'high':
            if self.models['gemini-2.5-flash']['current_usage'] < self.models['gemini-2.5-flash']['daily_quota']:
                return 'gemini-2.5-flash'
        
        # 对于中等质量需求，按优先级检查模型
        if self.models['gemini-2.5-flash-lite']['current_usage'] < self.models['gemini-2.5-flash-lite']['daily_quota']:
            return 'gemini-2.5-flash-lite'
        
        if self.models['gemini-2.5-flash']['current_usage'] < self.models['gemini-2.5-flash']['daily_quota']:
            return 'gemini-2.5-flash'
        
        # 使用DeepAI作为最终备用
        if self.models['deepai']['current_usage'] < self.models['deepai']['daily_quota']:
            return 'deepai'
        
        # 所有模型配额用完，返回空
        return None
    
    def process_request(self, text: str, required_quality='medium') -> Dict:
        """
        处理单个请求
        
        Args:
            text: 待处理文本
            required_quality: 所需质量等级
            
        Returns:
            Dict: 处理结果
        """
        self.daily_requests += 1
        
        # 选择模型
        selected_model = self.select_model(required_quality)
        
        if not selected_model:
            return {
                'status': 'error',
                'message': '所有模型配额已用完',
                'model_used': None,
                'result': text
            }
        
        # 更新使用量
        self.models[selected_model]['current_usage'] += 1
        
        # 模拟处理结果
        processed_text = f"[由{selected_model}处理] {text}"
        
        return {
            'status': 'success',
            'message': '处理成功',
            'model_used': selected_model,
            'result': processed_text
        }
    
    def get_status_report(self) -> str:
        """获取状态报告"""
        report = "📊 模型使用状态报告\n"
        report += "=" * 30 + "\n"
        
        for model_name, model_info in self.models.items():
            usage_percent = (model_info['current_usage'] / model_info['daily_quota']) * 100
            report += f"{model_name}:\n"
            report += f"  - 质量等级: {model_info['quality']}\n"
            report += f"  - 使用量: {model_info['current_usage']:,}/{model_info['daily_quota']:,} ({usage_percent:.1f}%)\n"
            report += f"  - 剩余额度: {model_info['daily_quota'] - model_info['current_usage']:,}\n\n"
        
        report += f"总计今日请求数: {self.daily_requests:,}\n"
        return report

def simulate_daily_processing():
    """模拟每日处理过程"""
    print("🚀 开始模拟每日AI文本处理...")
    scheduler = ModelScheduler()
    
    # 模拟每日5000-10000次请求
    daily_requests = random.randint(5000, 10000)
    print(f"📝 今日预计处理请求数: {daily_requests:,}")
    
    # 分批处理请求，模拟一天的时间分布
    for i in range(daily_requests):
        # 90%的请求为中等质量需求，10%为高质量需求
        quality = 'high' if random.random() < 0.1 else 'medium'
        text = f"这是第{i+1}条待处理文本，内容关于{random.choice(['科技', '生活', '娱乐', '教育'])}"
        
        result = scheduler.process_request(text, quality)
        
        # 每处理1000条显示一次状态
        if (i + 1) % 1000 == 0:
            print(f"已处理 {i+1} 条请求...")
    
    # 输出最终状态报告
    print("\n" + scheduler.get_status_report())

if __name__ == "__main__":
    simulate_daily_processing()