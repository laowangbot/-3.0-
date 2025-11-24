# ==================== 批量评论搬运操作 ====================
"""
批量评论搬运操作脚本
支持批量搬运多个频道的消息到不同目标消息的评论区
"""

import asyncio
import logging
import json
from typing import List, Dict, Any
from pyrogram import Client
from comment_cloning_engine import CommentCloningEngine

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BatchCommentCloner:
    """批量评论搬运器"""
    
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = None
        self.engine = None
    
    async def setup(self):
        """设置客户端和引擎"""
        self.client = Client("batch_clone", self.api_id, self.api_hash)
        await self.client.start()
        self.engine = CommentCloningEngine(self.client)
        logger.info("✅ 批量搬运器设置完成")
    
    async def clone_batch_tasks(self, tasks_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量执行搬运任务"""
        results = {
            'total_tasks': len(tasks_config),
            'success_tasks': 0,
            'failed_tasks': 0,
            'task_results': {}
        }
        
        logger.info(f"🚀 开始批量搬运 {len(tasks_config)} 个任务")
        
        for i, task_config in enumerate(tasks_config, 1):
            try:
                logger.info(f"📝 处理任务 {i}/{len(tasks_config)}: {task_config.get('name', f'Task-{i}')}")
                
                # 创建任务
                task_id = await self.engine.create_comment_clone_task(
                    source_chat_id=task_config['source_channel'],
                    target_chat_id=task_config['target_channel'],
                    target_message_id=task_config['target_message_id'],
                    message_ids=task_config['message_ids'],
                    config=task_config.get('config', {}),
                    user_id=task_config.get('user_id')
                )
                
                # 启动任务
                success = await self.engine.start_comment_clone_task(task_id)
                
                # 获取任务结果
                status = await self.engine.get_task_status(task_id)
                
                task_result = {
                    'task_id': task_id,
                    'success': success,
                    'processed_messages': status['processed_messages'],
                    'failed_messages': status['failed_messages'],
                    'progress': status['progress']
                }
                
                results['task_results'][task_config.get('name', f'Task-{i}')] = task_result
                
                if success:
                    results['success_tasks'] += 1
                    logger.info(f"✅ 任务 {i} 完成: {status['processed_messages']} 条成功")
                else:
                    results['failed_tasks'] += 1
                    logger.error(f"❌ 任务 {i} 失败")
                
                # 任务间延迟
                if i < len(tasks_config):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"❌ 任务 {i} 执行失败: {e}")
                results['failed_tasks'] += 1
                results['task_results'][task_config.get('name', f'Task-{i}')] = {
                    'error': str(e),
                    'success': False
                }
        
        logger.info(f"🎉 批量搬运完成: {results['success_tasks']}/{results['total_tasks']} 成功")
        return results
    
    async def cleanup(self):
        """清理资源"""
        if self.client:
            await self.client.stop()

def load_tasks_from_file(filename: str) -> List[Dict[str, Any]]:
    """从JSON文件加载任务配置"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"❌ 配置文件不存在: {filename}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件格式错误: {e}")
        return []

def create_sample_config(filename: str):
    """创建示例配置文件"""
    sample_config = [
        {
            "name": "重要通知搬运",
            "source_channel": "@news_channel",
            "target_channel": "@group1",
            "target_message_id": 12345,
            "message_ids": [12346, 12347, 12348],
            "config": {
                "remove_links": True,
                "tail_text": "转发自新闻频道"
            },
            "user_id": "user1"
        },
        {
            "name": "媒体收集",
            "source_channel": "@photo_channel", 
            "target_channel": "@collection_channel",
            "target_message_id": 54321,
            "message_ids": [54322, 54323],
            "config": {
                "filter_photo": False,
                "filter_video": False
            },
            "user_id": "user2"
        },
        {
            "name": "内容审核",
            "source_channel": "@submissions",
            "target_channel": "@moderation",
            "target_message_id": 99999,
            "message_ids": [11111, 11112, 11113, 11114],
            "config": {
                "filter_keywords": ["spam", "ad"],
                "remove_links": True,
                "tail_text": "待审核内容"
            },
            "user_id": "moderator1"
        }
    ]
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(sample_config, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 示例配置文件已创建: {filename}")

async def main():
    """主函数"""
    # 配置参数
    API_ID = 12345678  # 替换为您的API ID
    API_HASH = "your_api_hash_here"  # 替换为您的API Hash
    CONFIG_FILE = "batch_tasks.json"
    
    # 创建批量搬运器
    cloner = BatchCommentCloner(API_ID, API_HASH)
    
    try:
        # 设置
        await cloner.setup()
        
        # 检查配置文件
        tasks_config = load_tasks_from_file(CONFIG_FILE)
        if not tasks_config:
            print(f"📝 配置文件 {CONFIG_FILE} 不存在，创建示例配置...")
            create_sample_config(CONFIG_FILE)
            print(f"✅ 请编辑 {CONFIG_FILE} 文件，然后重新运行脚本")
            return
        
        # 显示任务概览
        print(f"📋 加载了 {len(tasks_config)} 个任务:")
        for i, task in enumerate(tasks_config, 1):
            print(f"  {i}. {task.get('name', f'Task-{i}')}")
            print(f"     {task['source_channel']} → {task['target_channel']}")
            print(f"     消息数量: {len(task['message_ids'])}")
        
        # 确认执行
        confirm = input(f"\n确认执行这 {len(tasks_config)} 个任务? (y/N): ").lower()
        if confirm != 'y':
            print("❌ 操作已取消")
            return
        
        # 执行批量搬运
        results = await cloner.clone_batch_tasks(tasks_config)
        
        # 显示结果
        print("\n" + "=" * 50)
        print("📊 批量搬运结果")
        print("=" * 50)
        print(f"总任务数: {results['total_tasks']}")
        print(f"成功任务: {results['success_tasks']}")
        print(f"失败任务: {results['failed_tasks']}")
        print(f"成功率: {results['success_tasks']/results['total_tasks']*100:.1f}%")
        
        print("\n📋 详细结果:")
        for task_name, result in results['task_results'].items():
            if result.get('success'):
                print(f"✅ {task_name}: {result['processed_messages']} 条成功")
            else:
                print(f"❌ {task_name}: {result.get('error', '未知错误')}")
        
        # 保存结果到文件
        with open('batch_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 详细结果已保存到: batch_results.json")
        
    except Exception as e:
        logger.error(f"❌ 批量搬运失败: {e}")
    
    finally:
        await cloner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
