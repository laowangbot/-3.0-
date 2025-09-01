# 🤖 Telegram搬运机器人

一个功能强大的Telegram频道搬运机器人，支持文本过滤、内容增强、实时监听和自动搬运功能。

## ✨ 主要功能

### 🚀 核心功能
- **频道搬运**: 支持批量搬运频道消息
- **实时监听**: 自动监听频道并搬运新消息
- **断点续传**: 支持任务中断后继续执行
- **进度监控**: 实时显示搬运进度和状态

### 🔧 过滤功能
- **文本过滤**: 关键字过滤和敏感词替换
- **链接移除**: 支持HTTP、磁力链接等多种链接类型
- **文件过滤**: 按文件类型和扩展名过滤
- **按钮过滤**: 智能过滤和替换按钮

### ✨ 增强功能
- **文本小尾巴**: 支持自定义文本追加
- **附加按钮**: 可配置的附加按钮
- **频率控制**: 支持间隔、随机等多种添加模式

### 📊 管理功能
- **频道管理**: 添加、编辑、删除频道组
- **任务管理**: 查看搬运历史和任务状态
- **配置管理**: 灵活的用户配置系统
- **权限控制**: 完善的权限验证机制

## 🛠️ 技术架构

### 模块结构
```
├── main.py              # 主机器人文件
├── config.py            # 配置文件
├── data_manager.py      # 数据管理器
├── message_engine.py    # 消息处理引擎
├── cloning_engine.py    # 搬运引擎
├── monitor_system.py    # 监听系统
├── ui_layouts.py        # 用户界面布局
├── start_bot.py         # 启动脚本
├── requirements.txt     # 依赖包列表
└── README.md           # 说明文档
```

### 技术特点
- **异步架构**: 基于asyncio的高性能异步处理
- **模块化设计**: 清晰的模块分离和接口定义
- **错误处理**: 完善的异常处理和错误恢复
- **日志系统**: 详细的日志记录和监控
- **数据持久化**: Firebase数据库支持

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 稳定的网络连接
- Telegram Bot Token
- Firebase项目配置

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd csbybot
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置机器人**
编辑 `config.py` 文件，填入您的配置信息：
```python
BOT_TOKEN = "your_bot_token"
API_ID = "your_api_id"
API_HASH = "your_api_hash"
```

4. **启动机器人**
```bash
# 本地运行
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh

# 或直接使用Python
python main.py
```

### 🌐 Render云部署

本机器人完全支持在Render云平台上部署，内置了Web服务器和心跳功能。

1. **准备部署**
   - 确保所有配置信息已填写到环境变量中
   - 项目已推送到GitHub仓库

2. **在Render上创建服务**
   - 登录 [Render](https://render.com)
   - 选择 "New" -> "Web Service"
   - 连接您的GitHub仓库
   - 选择项目分支

3. **配置环境变量**
   在Render控制台中设置以下环境变量：
   ```
   BOT_TOKEN=your_bot_token
   API_ID=your_api_id
   API_HASH=your_api_hash
   FIREBASE_PROJECT_ID=your_project_id
   FIREBASE_CREDENTIALS=your_firebase_credentials_json
   RENDER_EXTERNAL_URL=https://your-app-name.onrender.com
   ```

4. **部署设置**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
   - Health Check Path: `/health`

5. **自动部署**
   - Render会自动检测到 `render.yaml` 配置文件
   - 每次推送代码都会自动重新部署

**Render部署优势：**
- ✅ 免费套餐支持
- ✅ 自动SSL证书
- ✅ 内置心跳防休眠
- ✅ 自动重启和健康检查
- ✅ 零配置部署

5. **停止机器人**
```bash
# Windows
stop.bat

# Linux/Mac
./stop.sh

# 或直接按 Ctrl+C
```

6. **进程管理**（推荐）
```bash
# Windows
process_manager.bat status    # 查看进程状态
process_manager.bat kill      # 停止所有机器人进程
process_manager.bat cleanup   # 清理僵尸进程

# Linux/Mac
chmod +x process_manager.sh
./process_manager.sh status   # 查看进程状态
./process_manager.sh kill     # 停止所有机器人进程
./process_manager.sh cleanup  # 清理僵尸进程

# 或直接使用Python
python process_manager.py status
python process_manager.py kill
python process_manager.py cleanup
```

## 📱 使用方法

### 基本命令
- `/start` - 启动机器人
- `/help` - 显示帮助信息
- `/menu` - 打开主菜单

### 使用流程

1. **启动机器人**
   - 发送 `/start` 命令
   - 机器人会显示欢迎信息和主菜单

2. **添加频道组**
   - 点击"频道管理"
   - 选择"新增频道组"
   - 按格式发送频道ID

3. **配置过滤规则**
   - 点击"过滤设定"
   - 配置关键字过滤、链接移除等
   - 设置文本小尾巴和附加按钮

4. **执行搬运任务**
   - 点击"开始搬运"
   - 选择要搬运的频道组
   - 确认开始搬运

5. **启用实时监听**（可选）
   - 点击"实时监听"
   - 配置监听频道
   - 启用自动搬运

## ⚙️ 配置说明

### 机器人配置
```python
# 基本信息
BOT_ID = "your_bot_id"
BOT_NAME = "机器人名称"
API_ID = "your_api_id"
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# Firebase配置
FIREBASE_PROJECT_ID = "your_project_id"
FIREBASE_CREDENTIALS = {...}
```

### 用户配置
```python
# 默认配置
DEFAULT_USER_CONFIG = {
    "filter_keywords": [],           # 关键字过滤列表
    "replacement_words": {},         # 敏感词替换映射
    "remove_links": False,          # 是否移除链接
    "tail_text": "",                # 文本小尾巴
    "additional_buttons": [],       # 附加按钮列表
    "monitor_enabled": False,       # 是否启用监听
    # ... 更多配置项
}
```

## 🔧 高级功能

### 自定义过滤规则
- 支持正则表达式匹配
- 可配置的过滤策略
- 灵活的替换规则

### 批量操作
- 批量添加频道组
- 批量配置过滤规则
- 批量执行搬运任务

### 监控和统计
- 实时任务状态监控
- 详细的统计信息
- 错误日志和调试信息

## 🚨 注意事项

### 运行模式
- **按需启动**: 机器人不需要常驻后台，可以按需启动和停止
- **前台运行**: 启动后在终端前台运行，按 Ctrl+C 可以停止
- **进程管理**: 使用提供的脚本可以方便地启动和停止机器人

### 权限要求
- 机器人需要加入源频道和目标频道
- 需要读取源频道的权限
- 需要发送到目标频道的权限

### 使用限制
- 遵守Telegram API使用规范
- 避免频繁的API调用
- 注意消息大小限制

### 安全建议
- 定期更新依赖包
- 保护好API密钥
- 监控机器人运行状态

## 🆘 故障排除

### 常见问题

1. **机器人无法启动**
   - 检查配置信息是否正确
   - 确认网络连接正常
   - 查看错误日志

2. **机器人关闭后无法重新打开**
   - 使用进程管理工具检查残留进程：`process_manager.bat status`
   - 清理所有机器人进程：`process_manager.bat kill`
   - 清理僵尸进程：`process_manager.bat cleanup`
   - 重新启动机器人

3. **搬运失败**
   - 检查频道权限
   - 确认频道ID正确
   - 查看详细错误信息

4. **监听功能异常**
   - 检查监听配置
   - 确认频道状态
   - 查看监控日志

5. **进程管理问题**
   - 机器人意外退出后，使用进程管理工具检查状态
   - 发现僵尸进程时，使用cleanup命令清理
   - 无法停止机器人时，使用kill命令强制停止

### 获取帮助
- 查看详细日志信息
- 检查配置文件
- 联系技术支持

## 📄 许可证

本项目采用 MIT 许可证，详见 LICENSE 文件。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至项目维护者

---

**感谢使用Telegram搬运机器人！** 🎉
