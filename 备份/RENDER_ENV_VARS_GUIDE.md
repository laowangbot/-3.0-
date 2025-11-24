# 🔧 Render环境变量配置指南

## 📋 **问题诊断**

### **问题描述**
Render上启动的是本地机器人而不是环境变量中设置的机器人。

### **根本原因**
1. **硬编码会话文件** - GitHub仓库中包含 `bot_session_default.session` 等会话文件
2. **环境检测失败** - Render环境检测逻辑不完善
3. **配置加载优先级** - 环境变量加载失败时回退到硬编码配置

## 🛠️ **解决方案**

### **步骤1: 移除硬编码会话文件**
```bash
# 从GitHub仓库移除会话文件
git rm --cached bot_session_default.session
git rm --cached bot_session_default.session-journal
git rm --cached sessions/user_session.session
git rm --cached sessions/user_session.session-journal
```

### **步骤2: 设置正确的环境变量**

#### **wang机器人配置**
```
BOT_INSTANCE=wang
BOT3_API_ID=29112215
BOT3_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
BOT3_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS=[从firebase_credentials_template.txt复制]
```

### **步骤3: 环境变量命名规则**

#### **多机器人环境变量前缀**
- `BOT_INSTANCE=wang` - 指定当前机器人实例
- `BOT3_API_ID=29112215` - 机器人3的API ID
- `BOT3_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047` - 机器人3的API Hash
- `BOT3_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE` - 机器人3的Token

#### **通用环境变量**
- `FIREBASE_PROJECT_ID=bybot-142d8` - Firebase项目ID
- `LOG_LEVEL=INFO` - 日志级别
- `DEPLOYMENT_MODE=render` - 部署模式标识

## 🔍 **环境检测逻辑**

### **Render环境检测**
```python
def detect_deployment_environment(self) -> str:
    # 检查是否在Render环境
    if os.getenv('RENDER') or os.getenv('DEPLOYMENT_MODE') == 'render':
        return 'render'
    # 其他环境检测...
    else:
        return 'local'
```

### **配置加载优先级**
1. **环境变量** - 优先从环境变量加载
2. **JSON配置文件** - 回退到JSON配置文件
3. **硬编码配置** - 最后回退到硬编码配置

## 📊 **调试信息**

### **环境变量检查**
程序会输出以下调试信息：
```
🔍 环境变量检查:
   BOT_INSTANCE: wang
   BOT3_API_ID: 29112215
   BOT3_API_HASH: ddd2a2c75e3018ff6abf0aa4add47047
   BOT3_TOKEN: 8267186020...
```

### **配置验证结果**
```
🔍 配置验证结果:
   bot_token: ✅
   api_id: ✅
   api_hash: ✅
```

## 🚀 **部署步骤**

### **步骤1: 本地更新**
```bash
# 运行直接部署脚本
python direct_deploy.py
```

### **步骤2: Render配置**
1. 登录 [render.com](https://render.com)
2. 进入服务配置
3. 设置环境变量
4. 重启服务

### **步骤3: 验证部署**
1. 检查服务日志
2. 确认环境变量正确加载
3. 测试机器人功能

## 🔧 **故障排除**

### **问题1: 环境变量未加载**
**症状**: 日志显示使用本地配置
**解决**: 检查 `DEPLOYMENT_MODE=render` 是否设置

### **问题2: 机器人Token错误**
**症状**: 启动的是错误的机器人
**解决**: 检查 `BOT3_TOKEN` 环境变量是否正确

### **问题3: API配置错误**
**症状**: 无法连接Telegram API
**解决**: 检查 `BOT3_API_ID` 和 `BOT3_API_HASH` 是否正确

## 📝 **环境变量模板**

### **wang机器人完整配置**
```
BOT_INSTANCE=wang
BOT3_API_ID=29112215
BOT3_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
BOT3_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"bybot-142d8",...}
```

### **tong机器人完整配置**
```
BOT_INSTANCE=tong
BOT1_API_ID=28843352
BOT1_API_HASH=7c2370cd68799486c833641aaf273897
BOT1_TOKEN=8474266715:AAG1WsmmUGBy3XCvHbcwQePll8vEb8eMpms
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"bybot-142d8",...}
```

### **yg机器人完整配置**
```
BOT_INSTANCE=yg
BOT2_API_ID=26503296
BOT2_API_HASH=b9c2274752c28434efc4a2beca20aece
BOT2_TOKEN=8238467676:AAFjbbc2ZSYn7esFJ0qNvx4vDj7lEuinbcc
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"bybot-142d8",...}
```

现在你可以按照这个指南正确配置Render环境变量了！
