# BTbot 模块化Telegram机器人

这是一个模块化的Telegram机器人项目，专注于频道消息搬运、AI内容改写和实时监控功能。

## 项目结构

```
BTbot模块化代码计划/
├── core/                    # 核心模块（配置、日志）
├── modules/                 # 功能模块
│   ├── ai_rewrite/          # AI文本改写
│   ├── cloning/             # 消息搬运
│   ├── data_management/     # 数据管理
│   ├── monitoring/          # 实时监控
│   ├── user_api/            # 用户API管理
│   └── utils/               # 工具模块
├── web/                     # Web服务
├── tests/                   # 测试代码
├── examples/                # 使用示例
├── docs/                    # 文档
└── main.py                  # 主程序入口
```

## 功能特性

- **消息搬运**: 支持频道间的消息自动搬运
- **AI改写**: 集成AI技术对内容进行智能改写
- **实时监控**: 实时监听频道并自动处理新消息
- **评论搬运**: 支持搬运消息的评论
- **反检测机制**: 降低被平台检测的风险
- **多机器人支持**: 可同时管理多个机器人实例
- **Web监控界面**: 提供健康检查和状态监控

## 模块化架构

项目采用模块化设计，各模块职责明确：

- **核心模块**: 配置管理和日志系统
- **搬运模块**: 消息和评论搬运功能
- **AI改写模块**: AI文本改写和配额管理
- **监控模块**: 实时监控和任务管理
- **用户API模块**: 用户会话和API管理
- **数据管理模块**: 本地和远程数据存储
- **工具模块**: 实用工具和辅助功能
- **Web模块**: HTTP服务和状态监控

详细架构说明请参阅 [模块化架构说明](docs/MODULE_ARCHITECTURE.md)

## 安装和配置

1. 克隆项目代码
2. 安装依赖: `pip install -r requirements.txt`
3. 配置环境变量（参考 `.env.example`）
4. 运行程序: `python main.py`

## 使用示例

```bash
# 运行模块导入测试
python tests/test_imports.py

# 运行使用示例
python examples/module_usage_example.py

# 启动机器人
python main.py
```

## 文档

- [模块化架构说明](docs/MODULE_ARCHITECTURE.md)
- [AI改写使用指南](AI_REWRITE_USAGE.md)
- [评论搬运使用指南](COMMENT_CLONING_USAGE.md)
- [部署到Render指南](README_RENDER_DEPLOYMENT.md)

## 许可证

本项目仅供学习和研究使用，请遵守相关法律法规和Telegram服务条款。