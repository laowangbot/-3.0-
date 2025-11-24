# Supervisor配置模板

本目录包含所有机器人的Supervisor配置模板。

## 文件说明

- `bot_template.conf` - 通用模板文件
- `transfer_bot1.conf` 到 `transfer_bot5.conf` - 5个搬运机器人配置
- `member_bot1.conf` 到 `member_bot3.conf` - 3个会员机器人配置
- `create_all_configs.sh` - 一键创建所有配置的脚本

## 使用方法

### 方法1：使用一键脚本（推荐）

```bash
cd ~/telegram_bots/bybot3.0/supervisor_templates
bash create_all_configs.sh
```

### 方法2：手动复制单个配置

```bash
# 复制单个配置文件
sudo cp transfer_bot1.conf /etc/supervisor/conf.d/

# 重新加载配置
sudo supervisorctl reread
sudo supervisorctl update
```

### 方法3：自定义配置

1. 复制 `bot_template.conf`
2. 修改文件中的 `BOT_NAME` 为实际机器人名称
3. 保存为 `你的机器人名称.conf`
4. 复制到 `/etc/supervisor/conf.d/`

## 配置文件说明

每个配置文件包含以下关键参数：

```ini
[program:机器人名称]
command=            # Python解释器和主程序路径
directory=          # 工作目录
environment=        # 环境变量，指定配置文件
user=              # 运行用户
autostart=         # 开机自启动
autorestart=       # 崩溃自动重启
startretries=      # 启动重试次数
stderr_logfile=    # 错误日志路径
stdout_logfile=    # 输出日志路径
```

## 常用命令

```bash
# 查看所有机器人状态
sudo supervisorctl status

# 启动所有机器人
sudo supervisorctl start all

# 停止所有机器人
sudo supervisorctl stop all

# 重启所有机器人
sudo supervisorctl restart all

# 启动单个机器人
sudo supervisorctl start transfer_bot1

# 重启单个机器人
sudo supervisorctl restart transfer_bot1

# 查看日志
sudo tail -f /var/log/transfer_bot1.out.log
sudo tail -f /var/log/transfer_bot1.err.log
```

## 注意事项

1. 确保路径正确（默认：`/home/ubuntu/telegram_bots/bybot3.0`）
2. 确保虚拟环境已创建（默认：`venv`）
3. 确保对应的 `.env.*` 配置文件已存在
4. 修改配置后需要执行 `supervisorctl reread` 和 `supervisorctl update`








