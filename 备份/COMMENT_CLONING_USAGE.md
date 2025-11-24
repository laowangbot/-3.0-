# 评论搬运功能使用指南

## 功能概述

评论搬运功能允许您将指定频道的消息搬运到目标频道某个消息的评论区中，支持文本消息和媒体组消息的搬运。

## 主要特性

- ✅ 支持文本消息搬运到评论区
- ✅ 支持单媒体消息搬运到评论区
- ✅ 支持媒体组消息搬运到评论区
- ✅ 支持消息过滤和内容处理
- ✅ 支持任务管理和状态监控
- ✅ 支持错误处理和重试机制
- ✅ 支持配置化参数设置

## 快速开始

### 1. 基本使用

```python
import asyncio
from pyrogram import Client
from comment_cloning_engine import CommentCloningEngine

async def main():
    # 创建客户端
    client = Client("my_session", api_id=12345, api_hash="your_hash")
    await client.start()
    
    # 创建评论搬运引擎
    engine = CommentCloningEngine(client)
    
    # 创建搬运任务
    task_id = await engine.create_comment_clone_task(
        source_chat_id="@source_channel",      # 源频道
        target_chat_id="@target_channel",       # 目标频道
        target_message_id=12345,                # 目标消息ID（将在此消息下评论）
        message_ids=[12346, 12347, 12348],      # 要搬运的消息ID列表
        config={},                              # 可选配置
        user_id="user123"                       # 可选用户ID
    )
    
    # 启动任务
    success = await engine.start_comment_clone_task(task_id)
    
    if success:
        print("评论搬运完成！")
    else:
        print("评论搬运失败！")
    
    await client.stop()

# 运行
asyncio.run(main())
```

### 2. 高级配置

```python
# 创建带配置的引擎
config = {
    'retry_attempts': 5,                    # 重试次数
    'retry_delay': 3.0,                     # 重试延迟（秒）
    'comment_delay': 2.0,                    # 评论间延迟（秒）
    'max_comments_per_message': 20,          # 每条消息最大评论数
    'media_group_search_range': 100,         # 媒体组搜索范围
    'media_group_timeout': 60.0,             # 媒体组处理超时（秒）
    'continue_on_error': True,               # 遇到错误是否继续
    'max_consecutive_errors': 10,            # 最大连续错误数
    'user_config': {                         # 用户配置
        'remove_links': True,                # 移除链接
        'filter_keywords': ['spam'],         # 过滤关键字
        'tail_text': '转发自源频道'           # 添加尾部文本
    }
}

engine = CommentCloningEngine(client, config)
```

## 配置参数说明

### 引擎配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `retry_attempts` | int | 3 | 发送失败时的重试次数 |
| `retry_delay` | float | 2.0 | 重试间隔时间（秒） |
| `comment_delay` | float | 1.0 | 评论发送间隔时间（秒） |
| `max_comments_per_message` | int | 10 | 每条目标消息最大评论数 |
| `media_group_search_range` | int | 50 | 媒体组消息搜索范围 |
| `media_group_timeout` | float | 30.0 | 媒体组处理超时时间（秒） |
| `continue_on_error` | bool | True | 遇到错误时是否继续处理 |
| `max_consecutive_errors` | int | 5 | 最大连续错误数，超过后停止任务 |

### 用户配置

支持所有 `message_engine.py` 中的配置选项，包括：

- 内容过滤设置
- 链接处理设置
- 媒体过滤设置
- 按钮处理设置
- 内容增强设置

## 任务管理

### 创建任务

```python
task_id = await engine.create_comment_clone_task(
    source_chat_id="源频道ID或用户名",
    target_chat_id="目标频道ID或用户名", 
    target_message_id=目标消息ID,
    message_ids=[消息ID列表],
    config=可选配置,
    user_id=可选用户ID
)
```

### 启动任务

```python
success = await engine.start_comment_clone_task(task_id)
```

### 监控任务状态

```python
status = await engine.get_task_status(task_id)
print(f"任务状态: {status['status']}")
print(f"进度: {status['progress']:.1f}%")
print(f"已处理: {status['processed_messages']}")
print(f"失败: {status['failed_messages']}")
```

### 任务控制

```python
# 暂停任务
await engine.pause_task(task_id)

# 恢复任务
await engine.resume_task(task_id)

# 取消任务
await engine.cancel_task(task_id)
```

### 获取所有任务

```python
all_tasks = engine.get_all_tasks()
for task_id, task_info in all_tasks.items():
    print(f"任务 {task_id}: {task_info['status']}")
```

## 支持的媒体类型

### 单媒体消息
- 📷 照片
- 🎥 视频
- 📄 文档
- 🎵 音频
- 🎤 语音
- 😀 贴纸
- 🎬 动画
- 📹 视频笔记

### 媒体组消息
- 📷 照片组
- 🎥 视频组
- 📄 混合媒体组

## 错误处理

### 常见错误类型

1. **频道访问错误**
   - 频道不存在
   - 没有访问权限
   - 频道ID格式错误

2. **消息访问错误**
   - 消息不存在
   - 消息已被删除
   - 消息ID无效

3. **发送错误**
   - API限制
   - 网络超时
   - 权限不足

### 错误处理策略

- 自动重试机制
- 连续错误检测
- 可配置的错误容忍度
- 详细的错误日志

## 使用注意事项

### 1. API限制
- Telegram API有发送频率限制
- 建议设置适当的延迟时间
- 避免短时间内大量操作

### 2. 权限要求
- 需要访问源频道的权限
- 需要在目标频道发送消息的权限
- 某些频道可能需要管理员权限

### 3. 媒体组处理
- 媒体组消息需要完整获取
- 搜索范围过小可能遗漏部分消息
- 搜索范围过大可能影响性能

### 4. 消息过滤
- 被过滤的消息不会发送
- 空消息会被跳过
- 无效媒体会被忽略

## 测试

使用提供的测试脚本验证功能：

```bash
python test_comment_cloning.py
```

测试前请修改脚本中的配置参数：
- API_ID 和 API_HASH
- 源频道和目标频道
- 消息ID列表

## 故障排除

### 1. 任务创建失败
- 检查频道ID格式是否正确
- 确认有访问权限
- 验证目标消息是否存在

### 2. 消息发送失败
- 检查网络连接
- 确认API限制
- 验证发送权限

### 3. 媒体组不完整
- 增加搜索范围
- 检查源频道媒体组是否完整
- 调整超时设置

### 4. 性能问题
- 减少并发任务数
- 增加延迟时间
- 优化搜索范围

## 示例场景

### 场景1: 转发重要通知
```python
# 将重要通知转发到多个频道的评论区
notifications = [12345, 12346, 12347]
target_channels = ["@channel1", "@channel2", "@channel3"]

for channel in target_channels:
    task_id = await engine.create_comment_clone_task(
        source_chat_id="@news_channel",
        target_chat_id=channel,
        target_message_id=99999,  # 置顶消息
        message_ids=notifications
    )
    await engine.start_comment_clone_task(task_id)
```

### 场景2: 内容审核
```python
# 将待审核内容转发到审核频道
config = {
    'user_config': {
        'remove_links': True,
        'filter_keywords': ['spam', 'ad'],
        'tail_text': '待审核内容'
    }
}

task_id = await engine.create_comment_clone_task(
    source_chat_id="@user_submissions",
    target_chat_id="@moderation_channel", 
    target_message_id=88888,
    message_ids=[11111, 11112, 11113],
    config=config
)
```

### 场景3: 媒体收集
```python
# 收集特定主题的媒体到收藏频道
media_messages = [22222, 22223, 22224]  # 媒体组消息ID

task_id = await engine.create_comment_clone_task(
    source_chat_id="@photo_channel",
    target_chat_id="@collection_channel",
    target_message_id=77777,  # 主题消息
    message_ids=media_messages
)
```

## 更新日志

### v1.0.0
- 初始版本发布
- 支持基本评论搬运功能
- 支持媒体组搬运
- 支持任务管理
- 支持错误处理

## 技术支持

如有问题或建议，请查看：
- 日志文件中的详细错误信息
- 测试脚本的运行结果
- 相关配置参数设置

---

**注意**: 使用此功能时请遵守Telegram的使用条款和当地法律法规。
