# Render多机器人部署指南

## 概述

本指南将帮助您在Render上部署多个Telegram机器人实例，使用Firebase作为云存储，实现无状态会话管理。

## 部署架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Bot Instance 1│    │   Bot Instance 2│    │   Bot Instance 3│
│   (bot1)        │    │   (bot2)        │    │   (bot3)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Firebase      │
                    │   Firestore     │
                    │   (云存储)       │
                    └─────────────────┘
```

## 准备工作

### 1. Firebase项目设置

1. 访问 [Firebase Console](https://console.firebase.google.com/)
2. 创建新项目或使用现有项目
3. 启用Firestore数据库
4. 生成服务账户密钥：
   - 项目设置 → 服务账户 → 生成新私钥
   - 下载JSON文件

### 2. Telegram Bot设置

为每个机器人实例准备：
- API ID
- API Hash  
- Bot Token

## 部署步骤

### 步骤1：准备代码

1. 将代码推送到GitHub仓库
2. 确保包含以下文件：
   - `lsjmain.py` (主程序)
   - `multi_bot_deployment.py` (多机器人管理器)
   - `firebase_quota_manager.py` (配额管理器)
   - `render_multi_bot.yaml` (部署配置)
   - `requirements.txt` (依赖)

### 步骤2：创建Render服务

#### 方法A：使用render.yaml（推荐）

1. 在Render Dashboard中创建新Web服务
2. 连接GitHub仓库
3. 选择"使用render.yaml"
4. Render会自动创建所有3个服务

#### 方法B：手动创建

为每个机器人实例创建独立的Web服务：

**服务1配置：**
- 名称：`telegram-bot-instance-1`
- 环境：`bot1`
- 构建命令：`pip install -r requirements.txt && pip install firebase-admin`
- 启动命令：`python lsjmain.py`

**服务2配置：**
- 名称：`telegram-bot-instance-2`
- 环境：`bot2`
- 构建命令：`pip install -r requirements.txt && pip install firebase-admin`
- 启动命令：`python lsjmain.py`

**服务3配置：**
- 名称：`telegram-bot-instance-3`
- 环境：`bot3`
- 构建命令：`pip install -r requirements.txt && pip install firebase-admin`
- 启动命令：`python lsjmain.py`

### 步骤3：配置环境变量

为每个服务设置以下环境变量：

#### 通用变量
```
BOT_INSTANCE=bot1  # 或 bot2, bot3
FIREBASE_CREDENTIALS={"type":"service_account",...}  # Firebase JSON凭证
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
```

#### 机器人1专用变量
```
BOT1_API_ID=你的API_ID
BOT1_API_HASH=你的API_HASH
BOT1_TOKEN=你的BOT_TOKEN
```

#### 机器人2专用变量
```
BOT2_API_ID=你的API_ID
BOT2_API_HASH=你的API_HASH
BOT2_TOKEN=你的BOT_TOKEN
```

#### 机器人3专用变量
```
BOT3_API_ID=你的API_ID
BOT3_API_HASH=你的API_HASH
BOT3_TOKEN=你的BOT_TOKEN
```

### 步骤4：修改主程序

在`lsjmain.py`中添加多机器人支持：

```python
# 在文件开头添加
from multi_bot_deployment import deployment_manager, get_user_client

# 修改机器人初始化部分
async def initialize_bot():
    config = deployment_manager.config
    bot = Client(
        name="bot",
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token
    )
    return bot

# 修改用户会话管理
async def handle_user_login(user_id: int):
    client = await get_user_client(user_id)
    if client:
        # 处理用户登录逻辑
        pass
```

## 配额管理策略

### Firebase免费配额限制
- 读取：50,000次/天
- 写入：20,000次/天
- 删除：20,000次/天

### 优化策略

1. **缓存机制**：使用内存缓存减少读取操作
2. **批量写入**：将多个写入操作合并为批量操作
3. **会话压缩**：压缩会话数据减少存储空间
4. **定期清理**：清理过期数据

### 配额监控

```python
from firebase_quota_manager import get_quota_stats

# 获取配额使用情况
stats = get_quota_stats()
print(f"今日读取: {stats['reads']}/50000")
print(f"今日写入: {stats['writes']}/20000")
```

## 会话管理

### 无状态设计

每个机器人实例都是无状态的，用户会话存储在Firebase中：

```python
# 保存用户会话
await save_user_session(user_id)

# 加载用户会话
client = await get_user_client(user_id)

# 清理用户会话
await cleanup_user_session(user_id)
```

### 会话数据格式

```json
{
  "session_data": "base64编码的会话字符串",
  "timestamp": "2025-01-17T01:30:00Z",
  "bot_instance": "bot1"
}
```

## 监控和维护

### 健康检查

每个服务都有健康检查端点：
- URL：`https://your-service.onrender.com/health`
- 返回：`{"status": "healthy", "instance": "bot1"}`

### 日志监控

1. 在Render Dashboard中查看服务日志
2. 设置日志级别为INFO或DEBUG
3. 监控配额使用情况

### 故障恢复

1. **服务重启**：Render会自动重启失败的服务
2. **会话恢复**：从Firebase恢复用户会话
3. **数据备份**：定期备份Firebase数据

## 成本优化

### Render成本
- Starter计划：$7/月/服务
- 3个服务：$21/月

### Firebase成本
- 免费配额通常足够小规模使用
- 超出免费配额后按使用量计费

### 优化建议

1. **合并服务**：考虑将多个机器人合并到一个服务中
2. **缓存优化**：增加缓存命中率减少API调用
3. **批量操作**：使用批量写入减少操作次数

## 故障排除

### 常见问题

1. **服务启动失败**
   - 检查环境变量是否正确设置
   - 查看构建日志中的错误信息

2. **Firebase连接失败**
   - 验证FIREBASE_CREDENTIALS格式
   - 检查Firebase项目权限

3. **配额超限**
   - 检查配额使用情况
   - 优化缓存和批量操作

4. **会话丢失**
   - 检查Firebase写入权限
   - 验证会话数据格式

### 调试命令

```bash
# 检查服务状态
curl https://your-service.onrender.com/health

# 查看配额统计
curl https://your-service.onrender.com/quota-stats
```

## 扩展性

### 水平扩展

1. **添加更多实例**：在render.yaml中添加更多服务
2. **负载均衡**：使用Render的负载均衡功能
3. **数据库分片**：按用户ID分片存储

### 垂直扩展

1. **升级计划**：升级到更高性能的Render计划
2. **缓存优化**：增加内存缓存大小
3. **批量优化**：优化批量操作大小

## 安全考虑

1. **环境变量安全**：使用Render的加密环境变量
2. **Firebase安全规则**：设置适当的Firestore安全规则
3. **API密钥保护**：定期轮换API密钥
4. **访问控制**：限制Firebase访问权限

## 总结

通过本指南，您可以成功在Render上部署多个Telegram机器人实例，实现：

- ✅ 多机器人独立运行
- ✅ 无状态会话管理
- ✅ 云存储配额优化
- ✅ 自动故障恢复
- ✅ 成本优化

如有问题，请参考故障排除部分或查看Render和Firebase的官方文档。
