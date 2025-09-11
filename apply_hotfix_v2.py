#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搬运引擎热修复V2脚本
修复流式处理提前结束的问题
"""

import os
import re
import shutil
from datetime import datetime

def backup_file(file_path):
    """备份原文件"""
    backup_path = f"{file_path}.backup_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(file_path, backup_path)
    print(f"✅ 已备份原文件到: {backup_path}")
    return backup_path

def apply_hotfix_v2():
    """应用热修复V2"""
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
        
        # 1. 修改批次大小配置
        old_batch_config = '''            # 流式处理：边获取边搬运，支持预取和动态批次调整 - User API 优化
            batch_size = 1000  # User API: 增加初始批次大小到1000
            min_batch_size = 500  # User API: 增加最小批次大小到500
            max_batch_size = 2000  # User API: 增加最大批次大小到2000'''
        
        new_batch_config = '''            # 流式处理：边获取边搬运，支持预取和动态批次调整 - 修复版本
            batch_size = 200  # 修复: 减少批次大小避免跳过消息
            min_batch_size = 100  # 修复: 减少最小批次大小
            max_batch_size = 500  # 修复: 减少最大批次大小'''
        
        content = content.replace(old_batch_config, new_batch_config)
        
        # 2. 改进空档处理逻辑
        old_empty_handling = '''                    if not valid_messages:
                        logger.info(f"批次 {current_id}-{batch_end} 没有有效消息，跳过")
                        current_id = batch_end + 1
                        continue'''
        
        new_empty_handling = '''                    if not valid_messages:
                        # 检查是否真的没有消息，还是批次太大导致跳过
                        if batch_end - current_id + 1 > 100:  # 如果批次很大
                            logger.warning(f"⚠️ 大批次 {current_id}-{batch_end} 没有有效消息，可能跳过消息")
                            # 分成更小的批次重新检查
                            sub_batch_size = 50
                            sub_current = current_id
                            found_any = False
                            
                            while sub_current <= batch_end:
                                sub_end = min(sub_current + sub_batch_size - 1, batch_end)
                                sub_message_ids = list(range(sub_current, sub_end + 1))
                                
                                try:
                                    sub_messages = await self.client.get_messages(
                                        task.source_chat_id,
                                        message_ids=sub_message_ids
                                    )
                                    sub_valid = [msg for msg in sub_messages if msg is not None]
                                    
                                    if sub_valid:
                                        found_any = True
                                        logger.info(f"🔍 子批次 {sub_current}-{sub_end} 发现 {len(sub_valid)} 条消息")
                                        # 处理这批消息
                                        success = await self._process_message_batch(task, sub_valid, task_start_time)
                                        if not success:
                                            logger.warning(f"子批次 {sub_current}-{sub_end} 处理失败")
                                    
                                    await asyncio.sleep(0.01)  # 小延迟
                                    
                                except Exception as e:
                                    logger.warning(f"子批次 {sub_current}-{sub_end} 检查失败: {e}")
                                
                                sub_current = sub_end + 1
                            
                            if not found_any:
                                logger.info(f"✅ 确认批次 {current_id}-{batch_end} 没有有效消息")
                        else:
                            logger.info(f"批次 {current_id}-{batch_end} 没有有效消息，跳过")
                        
                        current_id = batch_end + 1
                        continue'''
        
        content = content.replace(old_empty_handling, new_empty_handling)
        
        # 3. 改进异常处理
        old_exception_handling = '''                except Exception as e:
                    logger.warning(f"批次 {current_id}-{batch_end} 处理失败: {e}")
                    current_id += batch_size
                    continue'''
        
        new_exception_handling = '''                except Exception as e:
                    logger.warning(f"批次 {current_id}-{batch_end} 处理失败: {e}")
                    # 不要跳过整个批次大小，只跳过当前批次
                    current_id = batch_end + 1
                    continue'''
        
        content = content.replace(old_exception_handling, new_exception_handling)
        
        # 写入修复后的文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 热修复V2应用成功!")
        print("📋 修复内容:")
        print("   1. 减少批次大小: 1000 -> 200")
        print("   2. 改进空档处理: 大批次分成小批次检查")
        print("   3. 改进异常处理: 不跳过整个批次大小")
        print("   4. 添加详细日志: 记录跳过和发现的消息")
        
        return True
        
    except Exception as e:
        print(f"❌ 热修复V2失败: {e}")
        # 恢复备份
        shutil.copy2(backup_path, file_path)
        print("🔄 已恢复原文件")
        return False

if __name__ == "__main__":
    print("🔧 搬运引擎热修复V2工具")
    print("=" * 50)
    print("修复问题: 流式处理提前结束，跳过大量消息")
    print("修复方案: 减少批次大小，改进空档处理")
    print("=" * 50)
    
    success = apply_hotfix_v2()
    
    if success:
        print("\n🎉 修复完成!")
        print("现在搬运大量消息时应该不会跳过消息了。")
        print("\n📝 建议:")
        print("   1. 重启机器人")
        print("   2. 测试搬运9-2096范围")
        print("   3. 检查日志中的消息发现记录")
    else:
        print("\n❌ 修复失败，请手动检查。")

