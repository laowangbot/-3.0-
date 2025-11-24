# ==================== 交互式评论搬运操作 ====================
"""
交互式评论搬运操作脚本
通过命令行交互来操作搬运功能
"""

import asyncio
import logging
from pyrogram import Client
from comment_cloning_engine import CommentCloningEngine

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InteractiveCommentCloner:
    """交互式评论搬运器"""
    
    def __init__(self):
        self.client = None
        self.engine = None
        self.api_id = None
        self.api_hash = None
    
    async def setup(self):
        """设置客户端"""
        print("🔧 设置评论搬运器...")
        
        # 获取API信息
        self.api_id = input("请输入您的API ID: ")
        self.api_hash = input("请输入您的API Hash: ")
        
        try:
            self.api_id = int(self.api_id)
        except ValueError:
            print("❌ API ID必须是数字")
            return False
        
        # 创建客户端
        self.client = Client("interactive_clone", self.api_id, self.api_hash)
        await self.client.start()
        
        # 创建引擎
        self.engine = CommentCloningEngine(self.client)
        
        print("✅ 设置完成！")
        return True
    
    async def clone_messages(self):
        """搬运消息到评论区"""
        print("\n📝 搬运消息到评论区")
        print("=" * 40)
        
        # 获取参数
        source_channel = input("源频道 (@channel_name 或 channel_id): ")
        target_channel = input("目标频道 (@channel_name 或 channel_id): ")
        target_message_id = input("目标消息ID (将在此消息下评论): ")
        
        try:
            target_message_id = int(target_message_id)
        except ValueError:
            print("❌ 目标消息ID必须是数字")
            return
        
        # 获取要搬运的消息ID
        print("\n请输入要搬运的消息ID (每行一个，输入空行结束):")
        message_ids = []
        while True:
            msg_id = input("消息ID: ").strip()
            if not msg_id:
                break
            try:
                message_ids.append(int(msg_id))
            except ValueError:
                print("❌ 消息ID必须是数字")
                continue
        
        if not message_ids:
            print("❌ 没有输入任何消息ID")
            return
        
        print(f"\n📋 搬运配置:")
        print(f"  • 源频道: {source_channel}")
        print(f"  • 目标频道: {target_channel}")
        print(f"  • 目标消息ID: {target_message_id}")
        print(f"  • 要搬运的消息: {message_ids}")
        
        confirm = input("\n确认开始搬运? (y/N): ").lower()
        if confirm != 'y':
            print("❌ 操作已取消")
            return
        
        # 创建任务
        try:
            print("\n🚀 创建搬运任务...")
            task_id = await self.engine.create_comment_clone_task(
                source_chat_id=source_channel,
                target_chat_id=target_channel,
                target_message_id=target_message_id,
                message_ids=message_ids
            )
            
            print(f"✅ 任务创建成功: {task_id}")
            
            # 启动任务
            print("🔄 开始搬运...")
            success = await self.engine.start_comment_clone_task(task_id)
            
            if success:
                print("🎉 搬运完成！")
                
                # 显示结果
                status = await self.engine.get_task_status(task_id)
                print(f"\n📊 搬运结果:")
                print(f"  • 成功: {status['processed_messages']} 条")
                print(f"  • 失败: {status['failed_messages']} 条")
                print(f"  • 进度: {status['progress']:.1f}%")
            else:
                print("❌ 搬运失败！")
                
        except Exception as e:
            print(f"❌ 搬运失败: {e}")
    
    async def monitor_tasks(self):
        """监控任务状态"""
        print("\n📊 任务监控")
        print("=" * 40)
        
        tasks = self.engine.get_all_tasks()
        if not tasks:
            print("📭 当前没有活跃任务")
            return
        
        print(f"📋 当前有 {len(tasks)} 个任务:")
        for task_id, task_info in tasks.items():
            print(f"\n任务: {task_id}")
            print(f"  • 状态: {task_info['status']}")
            print(f"  • 进度: {task_info['progress']:.1f}%")
            print(f"  • 已处理: {task_info['processed_messages']}")
            print(f"  • 失败: {task_info['failed_messages']}")
            print(f"  • 源频道: {task_info['source_channel_name']}")
            print(f"  • 目标频道: {task_info['target_channel_name']}")
    
    async def control_task(self):
        """控制任务"""
        print("\n🎮 任务控制")
        print("=" * 40)
        
        tasks = self.engine.get_all_tasks()
        if not tasks:
            print("📭 当前没有活跃任务")
            return
        
        # 显示任务列表
        task_list = list(tasks.keys())
        for i, task_id in enumerate(task_list):
            status = tasks[task_id]['status']
            print(f"{i+1}. {task_id} ({status})")
        
        try:
            choice = int(input("\n选择任务编号: ")) - 1
            if choice < 0 or choice >= len(task_list):
                print("❌ 无效选择")
                return
            
            task_id = task_list[choice]
            task_info = tasks[task_id]
            
            print(f"\n任务: {task_id}")
            print(f"状态: {task_info['status']}")
            
            print("\n操作选项:")
            print("1. 暂停任务")
            print("2. 恢复任务")
            print("3. 取消任务")
            print("4. 查看详情")
            
            action = input("选择操作 (1-4): ")
            
            if action == "1":
                success = await self.engine.pause_task(task_id)
                print("✅ 任务已暂停" if success else "❌ 暂停失败")
            elif action == "2":
                success = await self.engine.resume_task(task_id)
                print("✅ 任务已恢复" if success else "❌ 恢复失败")
            elif action == "3":
                success = await self.engine.cancel_task(task_id)
                print("✅ 任务已取消" if success else "❌ 取消失败")
            elif action == "4":
                status = await self.engine.get_task_status(task_id)
                print(f"\n📋 任务详情:")
                for key, value in status.items():
                    print(f"  • {key}: {value}")
            else:
                print("❌ 无效操作")
                
        except ValueError:
            print("❌ 请输入有效数字")
        except Exception as e:
            print(f"❌ 操作失败: {e}")
    
    async def run(self):
        """运行交互式界面"""
        if not await self.setup():
            return
        
        try:
            while True:
                print("\n" + "=" * 50)
                print("🤖 评论搬运操作界面")
                print("=" * 50)
                print("1. 搬运消息到评论区")
                print("2. 监控任务状态")
                print("3. 控制任务")
                print("4. 退出")
                
                choice = input("\n请选择操作 (1-4): ")
                
                if choice == "1":
                    await self.clone_messages()
                elif choice == "2":
                    await self.monitor_tasks()
                elif choice == "3":
                    await self.control_task()
                elif choice == "4":
                    print("👋 再见！")
                    break
                else:
                    print("❌ 无效选择，请重新输入")
                
                input("\n按回车键继续...")
        
        finally:
            if self.client:
                await self.client.stop()

async def main():
    """主函数"""
    cloner = InteractiveCommentCloner()
    await cloner.run()

if __name__ == "__main__":
    asyncio.run(main())
