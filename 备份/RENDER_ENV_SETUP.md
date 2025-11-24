# 🔧 Render环境变量设置指南

## 📋 **问题解决**

修复了User API管理器初始化问题，现在会优先从环境变量直接获取API配置。

## 🛠️ **环境变量配置**

在Render Dashboard的Environment标签页设置以下环境变量：

```
BOT_INSTANCE=wang
WANG_API_ID=29112215
WANG_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
WANG_BOT_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS=[从firebase_credentials_template.txt复制]
```

## 🔍 **预期日志输出**

设置正确后，应该看到：

```
🔍 User API 管理器初始化检查:
   BOT_INSTANCE: wang
   环境变量前缀: WANG_
   WANG_API_ID: 29112215
   WANG_API_HASH: ddd2a2c75e3018ff6abf0aa4add47047
✅ User API 管理器已创建，等待初始化
```

## 🚀 **部署步骤**

1. 在Render Dashboard设置环境变量
2. 重启服务
3. 检查日志确认User API管理器正确初始化
4. 测试User API登录功能

现在应该能解决 `❌ User API 管理器未初始化` 的问题了！
