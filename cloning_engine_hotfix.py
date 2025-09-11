#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搬运引擎热修复
直接修复消息丢失问题
"""

def apply_hotfix_to_cloning_engine():
    """应用热修复到cloning_engine.py"""
    
    # 需要替换的代码段
    old_code = '''
            # 计算总消息数
            if actual_start_id and task.end_id:
                task.total_messages = task.end_id - actual_start_id + 1
            else:
                task.total_messages = len(first_batch)
    '''
    
    # 新的代码段
    new_code = '''
            # 计算总消息数 - 修复版本
            if actual_start_id and task.end_id:
                # 先计算实际存在的消息数量
                actual_total = await self._count_actual_messages_in_range(
                    task.source_chat_id, actual_start_id, task.end_id
                )
                task.total_messages = actual_total
                logger.info(f"📊 实际总消息数: {actual_total} (范围: {actual_start_id}-{task.end_id})")
            else:
                task.total_messages = len(first_batch)
    '''
    
    # 需要添加的新方法
    new_method = '''
    async def _count_actual_messages_in_range(self, chat_id: str, start_id: int, end_id: int) -> int:
        """计算指定范围内实际存在的消息数量"""
        logger.info(f"📊 开始计算实际消息数量: {start_id} - {end_id}")
        actual_count = 0
        batch_size = 1000
        current_id = start_id
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                logger.debug(f"📊 检查批次: {current_id} - {batch_end} ({len(message_ids)} 个ID)")
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                
                # 计算有效消息数量
                valid_count = sum(1 for msg in messages if msg is not None)
                actual_count += valid_count
                
                logger.debug(f"📊 批次 {current_id}-{batch_end}: 发现 {valid_count} 条消息")
                
                current_id = batch_end + 1
                
                # 添加小延迟避免API限制
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"📊 计算批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"📊 实际消息数量计算完成: {actual_count} 条")
        return actual_count
    '''
    
    return {
        'old_code': old_code,
        'new_code': new_code,
        'new_method': new_method,
        'file_path': 'cloning_engine.py',
        'line_range': (1006, 1010)
    }

def create_hotfix_script():
    """创建热修复脚本"""
    script_content = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搬运引擎热修复脚本
自动修复消息丢失问题
"""

import os
import re
import shutil
from datetime import datetime

def backup_file(file_path):
    """备份原文件"""
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(file_path, backup_path)
    print(f"✅ 已备份原文件到: {backup_path}")
    return backup_path

def apply_hotfix():
    """应用热修复"""
    file_path = "cloning_engine.py"
    
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    # 备份原文件
    backup_path = backup_file(file_path)
    
    try:
        # 读取原文件
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 1. 添加新方法
        new_method = '''
    async def _count_actual_messages_in_range(self, chat_id: str, start_id: int, end_id: int) -> int:
        """计算指定范围内实际存在的消息数量"""
        logger.info(f"📊 开始计算实际消息数量: {start_id} - {end_id}")
        actual_count = 0
        batch_size = 1000
        current_id = start_id
        
        while current_id <= end_id:
            try:
                batch_end = min(current_id + batch_size - 1, end_id)
                message_ids = list(range(current_id, batch_end + 1))
                
                logger.debug(f"📊 检查批次: {current_id} - {batch_end} ({len(message_ids)} 个ID)")
                
                # 获取消息
                messages = await self.client.get_messages(chat_id, message_ids=message_ids)
                
                # 计算有效消息数量
                valid_count = sum(1 for msg in messages if msg is not None)
                actual_count += valid_count
                
                logger.debug(f"📊 批次 {current_id}-{batch_end}: 发现 {valid_count} 条消息")
                
                current_id = batch_end + 1
                
                # 添加小延迟避免API限制
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"📊 计算批次失败 {current_id}-{batch_end}: {e}")
                current_id += batch_size
                continue
        
        logger.info(f"📊 实际消息数量计算完成: {actual_count} 条")
        return actual_count
'''
        
        # 在类定义内添加新方法
        class_pattern = r'(class CloningEngine:.*?)(    async def _count_messages)'
        replacement = r'\1' + new_method + r'\n    \2'
        content = re.sub(class_pattern, replacement, content, flags=re.DOTALL)
        
        # 2. 替换消息计数逻辑
        old_counting = '''            # 计算总消息数
            if actual_start_id and task.end_id:
                task.total_messages = task.end_id - actual_start_id + 1
            else:
                task.total_messages = len(first_batch)'''
        
        new_counting = '''            # 计算总消息数 - 修复版本
            if actual_start_id and task.end_id:
                # 先计算实际存在的消息数量
                actual_total = await self._count_actual_messages_in_range(
                    task.source_chat_id, actual_start_id, task.end_id
                )
                task.total_messages = actual_total
                logger.info(f"📊 实际总消息数: {actual_total} (范围: {actual_start_id}-{task.end_id})")
            else:
                task.total_messages = len(first_batch)'''
        
        content = content.replace(old_counting, new_counting)
        
        # 写入修复后的文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 热修复应用成功!")
        print("📋 修复内容:")
        print("   1. 添加了 _count_actual_messages_in_range 方法")
        print("   2. 修改了消息计数逻辑，使用实际存在的消息数量")
        print("   3. 添加了详细的日志记录")
        
        return True
        
    except Exception as e:
        print(f"❌ 热修复失败: {e}")
        # 恢复备份
        shutil.copy2(backup_path, file_path)
        print("🔄 已恢复原文件")
        return False

if __name__ == "__main__":
    print("🔧 搬运引擎热修复工具")
    print("=" * 50)
    
    success = apply_hotfix()
    
    if success:
        print("\\n🎉 修复完成!")
        print("现在搬运大量消息时应该能正确显示实际消息数量了。")
    else:
        print("\\n❌ 修复失败，请手动检查。")
'''
    
    with open('apply_hotfix.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("✅ 热修复脚本已创建: apply_hotfix.py")

if __name__ == "__main__":
    print("🔧 搬运引擎热修复工具")
    print("=" * 50)
    
    # 显示修复信息
    hotfix_info = apply_hotfix_to_cloning_engine()
    print(f"📋 修复文件: {hotfix_info['file_path']}")
    print(f"📋 修复行数: {hotfix_info['line_range']}")
    print("\\n🔍 问题分析:")
    print("   - 原代码假设消息ID连续")
    print("   - 实际Telegram消息ID不连续")
    print("   - 导致大量消息被跳过")
    print("\\n🔧 修复方案:")
    print("   - 先发现实际存在的消息")
    print("   - 使用实际消息数量计算进度")
    print("   - 添加详细日志记录")
    
    # 创建热修复脚本
    create_hotfix_script()
    
    print("\\n📝 使用方法:")
    print("   1. 运行: python apply_hotfix.py")
    print("   2. 重启机器人")
    print("   3. 测试搬运功能")

