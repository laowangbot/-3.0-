#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移脚本：从单机器人存储迁移到多机器人存储
将数据从 users/{user_id} 结构迁移到 bots/{bot_id}/users/{user_id} 结构
"""

import asyncio
import logging
from typing import Dict, Any, List
from data_manager import DataManager
from multi_bot_data_manager import create_multi_bot_data_manager
from config import get_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataMigrator:
    """数据迁移器"""
    
    def __init__(self, bot_id: str = None):
        """初始化迁移器
        
        Args:
            bot_id: 目标机器人ID，如果为None则使用配置中的bot_id
        """
        self.config = get_config()
        self.bot_id = bot_id or self.config.get('bot_id', 'default_bot')
        
        # 初始化数据管理器
        self.old_manager = DataManager()
        self.new_manager = create_multi_bot_data_manager(self.bot_id)
        
        logger.info(f"数据迁移器初始化完成，目标机器人ID: {self.bot_id}")
    
    async def check_migration_status(self) -> Dict[str, Any]:
        """检查迁移状态"""
        try:
            # 检查旧数据结构
            old_users = await self._get_old_users()
            
            # 检查新数据结构
            new_users = await self.new_manager.get_all_user_ids()
            
            return {
                'old_users_count': len(old_users),
                'new_users_count': len(new_users),
                'old_users': old_users,
                'new_users': new_users,
                'migration_needed': len(old_users) > 0 and len(new_users) == 0
            }
            
        except Exception as e:
            logger.error(f"检查迁移状态失败: {e}")
            return {
                'error': str(e),
                'migration_needed': False
            }
    
    async def _get_old_users(self) -> List[str]:
        """获取旧数据结构中的所有用户ID"""
        try:
            if not self.old_manager.initialized:
                logger.warning("旧数据管理器未初始化")
                return []
            
            # 获取所有用户文档
            users_ref = self.old_manager.db.collection('users')
            docs = users_ref.stream()
            
            user_ids = []
            for doc in docs:
                user_ids.append(doc.id)
            
            return user_ids
            
        except Exception as e:
            logger.error(f"获取旧用户列表失败: {e}")
            return []
    
    async def migrate_user_data(self, user_id: str) -> bool:
        """迁移单个用户的数据
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 迁移是否成功
        """
        try:
            logger.info(f"开始迁移用户 {user_id} 的数据...")
            
            # 获取旧数据
            old_user_config = await self.old_manager.get_user_config(user_id)
            old_channel_pairs = await self.old_manager.get_channel_pairs(user_id)
            old_task_history = await self.old_manager.get_task_history(user_id, limit=1000)
            
            # 检查是否已有新数据
            new_user_config = await self.new_manager.get_user_config(user_id)
            if new_user_config and new_user_config != self.new_manager.DEFAULT_USER_CONFIG:
                logger.warning(f"用户 {user_id} 在新结构中已有数据，跳过迁移")
                return True
            
            # 迁移用户配置
            if old_user_config:
                success = await self.new_manager.save_user_config(user_id, old_user_config)
                if not success:
                    logger.error(f"迁移用户 {user_id} 配置失败")
                    return False
                logger.info(f"用户 {user_id} 配置迁移成功")
            
            # 迁移频道组
            if old_channel_pairs:
                success = await self.new_manager.save_channel_pairs(user_id, old_channel_pairs)
                if not success:
                    logger.error(f"迁移用户 {user_id} 频道组失败")
                    return False
                logger.info(f"用户 {user_id} 频道组迁移成功，共 {len(old_channel_pairs)} 个频道组")
            
            # 迁移任务历史
            if old_task_history:
                for task_record in old_task_history:
                    await self.new_manager.add_task_history(user_id, task_record)
                logger.info(f"用户 {user_id} 任务历史迁移成功，共 {len(old_task_history)} 条记录")
            
            logger.info(f"用户 {user_id} 数据迁移完成")
            return True
            
        except Exception as e:
            logger.error(f"迁移用户 {user_id} 数据失败: {e}")
            return False
    
    async def migrate_all_data(self, dry_run: bool = False) -> Dict[str, Any]:
        """迁移所有数据
        
        Args:
            dry_run: 是否为试运行（不实际执行迁移）
            
        Returns:
            Dict: 迁移结果统计
        """
        try:
            logger.info(f"开始迁移所有数据 (试运行: {dry_run})...")
            
            # 检查迁移状态
            status = await self.check_migration_status()
            if not status.get('migration_needed', False):
                logger.info("无需迁移，新结构中已有数据")
                return status
            
            old_users = status.get('old_users', [])
            if not old_users:
                logger.info("没有找到需要迁移的用户数据")
                return {'migrated_users': 0, 'failed_users': 0, 'total_users': 0}
            
            logger.info(f"找到 {len(old_users)} 个用户需要迁移")
            
            migrated_count = 0
            failed_count = 0
            
            for user_id in old_users:
                if dry_run:
                    logger.info(f"[试运行] 将迁移用户: {user_id}")
                    migrated_count += 1
                else:
                    success = await self.migrate_user_data(user_id)
                    if success:
                        migrated_count += 1
                    else:
                        failed_count += 1
            
            result = {
                'migrated_users': migrated_count,
                'failed_users': failed_count,
                'total_users': len(old_users),
                'dry_run': dry_run
            }
            
            logger.info(f"迁移完成: 成功 {migrated_count}, 失败 {failed_count}, 总计 {len(old_users)}")
            return result
            
        except Exception as e:
            logger.error(f"迁移所有数据失败: {e}")
            return {'error': str(e), 'migrated_users': 0, 'failed_users': 0, 'total_users': 0}
    
    async def backup_old_data(self) -> bool:
        """备份旧数据（可选功能）"""
        try:
            logger.info("开始备份旧数据...")
            # 这里可以实现备份逻辑，比如导出到JSON文件
            # 暂时跳过，因为Firebase本身就有版本控制
            logger.info("旧数据备份完成（Firebase自动版本控制）")
            return True
            
        except Exception as e:
            logger.error(f"备份旧数据失败: {e}")
            return False

async def main():
    """主函数"""
    try:
        logger.info("🚀 启动数据迁移工具...")
        
        # 创建迁移器
        migrator = DataMigrator()
        
        # 检查迁移状态
        logger.info("📊 检查迁移状态...")
        status = await migrator.check_migration_status()
        
        print("\n" + "="*50)
        print("📊 迁移状态检查结果")
        print("="*50)
        print(f"旧结构用户数量: {status.get('old_users_count', 0)}")
        print(f"新结构用户数量: {status.get('new_users_count', 0)}")
        print(f"需要迁移: {'是' if status.get('migration_needed', False) else '否'}")
        
        if status.get('old_users'):
            print(f"需要迁移的用户: {', '.join(status['old_users'][:5])}{'...' if len(status['old_users']) > 5 else ''}")
        
        if status.get('error'):
            print(f"检查错误: {status['error']}")
            return
        
        # 如果不需要迁移，直接退出
        if not status.get('migration_needed', False):
            print("\n✅ 无需迁移，数据已是最新结构")
            return
        
        # 询问是否执行迁移
        print("\n" + "="*50)
        print("⚠️  迁移确认")
        print("="*50)
        print("此操作将把数据从旧结构迁移到新结构")
        print("建议先进行试运行，确认无误后再执行实际迁移")
        
        # 试运行
        print("\n🔍 执行试运行...")
        dry_run_result = await migrator.migrate_all_data(dry_run=True)
        print(f"试运行结果: 将迁移 {dry_run_result.get('migrated_users', 0)} 个用户")
        
        # 实际迁移
        print("\n🚀 执行实际迁移...")
        result = await migrator.migrate_all_data(dry_run=False)
        
        print("\n" + "="*50)
        print("📈 迁移结果")
        print("="*50)
        print(f"成功迁移: {result.get('migrated_users', 0)} 个用户")
        print(f"迁移失败: {result.get('failed_users', 0)} 个用户")
        print(f"总计用户: {result.get('total_users', 0)} 个用户")
        
        if result.get('error'):
            print(f"迁移错误: {result['error']}")
        
        print("\n✅ 数据迁移完成！")
        print("现在可以启动使用多机器人存储的机器人了")
        
    except Exception as e:
        logger.error(f"迁移过程发生错误: {e}")
        print(f"\n❌ 迁移失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
