# 🔧 Render正确环境变量配置

## 📋 **问题分析**

从日志可以看出问题：
```
BOT_INSTANCE: @wang1984bot  # ❌ 错误：应该是 wang
DEFAULT_API_ID: None        # ❌ 错误：环境变量前缀不匹配
DEFAULT_API_HASH: None      # ❌ 错误：环境变量前缀不匹配
DEFAULT_BOT_TOKEN: None     # ❌ 错误：环境变量前缀不匹配
```

## 🛠️ **正确的环境变量配置**

### **wang机器人配置**
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

### **tong机器人配置**
```
BOT_INSTANCE=tong
TONG_API_ID=28843352
TONG_API_HASH=7c2370cd68799486c833641aaf273897
TONG_BOT_TOKEN=8474266715:AAG1WsmmUGBy3XCvHbcwQePll8vEb8eMpms
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS=[从firebase_credentials_template.txt复制]
```

### **yg机器人配置**
```
BOT_INSTANCE=yg
YG_API_ID=26503296
YG_API_HASH=b9c2274752c28434efc4a2beca20aece
YG_BOT_TOKEN=8238467676:AAFjbbc2ZSYn7esFJ0qNvx4vDj7lEuinbcc
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS=[从firebase_credentials_template.txt复制]
```

## 🔍 **环境变量命名规则**

### **关键规则**
1. **BOT_INSTANCE** - 必须是机器人名称（如：`wang`, `tong`, `yg`），不能是 `@wang1984bot`
2. **环境变量前缀** - 必须是 `{BOT_INSTANCE.upper()}_`，如：`WANG_`, `TONG_`, `YG_`
3. **变量名格式** - `{PREFIX}API_ID`, `{PREFIX}API_HASH`, `{PREFIX}BOT_TOKEN`

### **示例对比**

#### ❌ **错误配置**
```
BOT_INSTANCE=@wang1984bot
BOT3_API_ID=29112215
BOT3_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
BOT3_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
```

#### ✅ **正确配置**
```
BOT_INSTANCE=wang
WANG_API_ID=29112215
WANG_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
WANG_BOT_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
```

## 📊 **预期日志输出**

配置正确后，应该看到：
```
🔍 开始从Render环境变量加载机器人 'default' 的配置
🔍 检测到BOT_INSTANCE: wang, 使用机器人名称: wang
🔍 环境变量检查:
   BOT_INSTANCE: wang
   实际机器人名称: wang
   环境变量前缀: WANG_
   WANG_API_ID: 29112215
   WANG_API_HASH: ddd2a2c75e3018ff6abf0aa4add47047
   WANG_BOT_TOKEN: 8267186020...
🔍 配置验证结果:
   bot_token: ✅
   api_id: ✅
   api_hash: ✅
✅ 已从Render环境变量加载机器人 'wang' 的配置
```

## 🚀 **部署步骤**

### **步骤1: 在Render Dashboard设置环境变量**
1. 登录 [render.com](https://render.com)
2. 进入你的服务
3. 点击 "Environment" 标签
4. 添加以下环境变量：

```
BOT_INSTANCE=wang
WANG_API_ID=29112215
WANG_API_HASH=ddd2a2c75e3018ff6abf0aa4add47047
WANG_BOT_TOKEN=8267186020:AAHOY7z90X6AUAg57MNy969rQPoYkx7FqSE
FIREBASE_PROJECT_ID=bybot-142d8
LOG_LEVEL=INFO
DEPLOYMENT_MODE=render
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"bybot-142d8",...}
```

### **步骤2: 重启服务**
1. 保存环境变量
2. 重启服务
3. 检查日志

### **步骤3: 验证部署**
1. 检查服务日志
2. 确认环境变量正确加载
3. 测试机器人功能

## 🔧 **故障排除**

### **问题1: BOT_INSTANCE格式错误**
**症状**: `BOT_INSTANCE: @wang1984bot`
**解决**: 改为 `BOT_INSTANCE=wang`

### **问题2: 环境变量前缀不匹配**
**症状**: `DEFAULT_API_ID: None`
**解决**: 使用 `WANG_API_ID` 而不是 `BOT3_API_ID`

### **问题3: 变量名错误**
**症状**: `DEFAULT_BOT_TOKEN: None`
**解决**: 使用 `WANG_BOT_TOKEN` 而不是 `BOT3_TOKEN`

现在按照这个指南重新配置Render环境变量，应该就能正确启动了！
