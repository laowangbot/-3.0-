# GCP 服务器配置与维护文档

> 创建日期: 2025-11-03  
> 适用环境: Google Compute Engine（Debian 12）  
> 维护目标: 三个 Telegram 机器人（bot1 / bot2 / bot3）在服务器上稳定常驻运行

---

## 1. 基本信息
- 实例类型: e2-medium（2 vCPU, 4 GB RAM）
- 操作系统: Debian GNU/Linux 12 (bookworm)
- 登录用户: `zwjmht`
- 公网 IP: `34.124.198.248`
- SSH 私钥（本地路径，Windows）: `C:\\Users\\PC\\.ssh\\gcp_ed25519`
- SSH 登录命令（PowerShell）:
  ```bash
  ssh -i "$env:USERPROFILE\\.ssh\\gcp_ed25519" zwjmht@34.124.198.248
  ```
- 应用主目录: `/home/zwjmht/telegram_bots/bybot3.0`
- Python 虚拟环境: `/home/zwjmht/telegram_bots/bybot3.0/venv`

> 提醒: 本文档不记录任何敏感值（Token/API_ID/API_HASH）。敏感值保存在 `.env.bot*`，切勿提交到仓库。

---

## 2. 目录结构（关键路径）
```
/home/zwjmht/telegram_bots/
└── bybot3.0/
    ├── venv/                    # Python 虚拟环境
    ├── .env.bot1                # bot1 环境变量（含敏感值）
    ├── .env.bot2                # bot2 环境变量（含敏感值）
    ├── .env.bot3                # bot3 环境变量（含敏感值）
    ├── data/
    │   ├── bot1/
    │   ├── bot2/
    │   └── bot3/
    ├── requirements.txt
    └── lsjmain.py               # 启动入口（--bot 指定实例）
```

Supervisor 配置与日志：
```
/etc/supervisor/conf.d/
├── bot1.conf
├── bot2.conf
└── bot3.conf

/var/log/
├── bot1.out.log
├── bot1.err.log
├── bot2.out.log
├── bot2.err.log
├── bot3.out.log
└── bot3.err.log
```

---

## 3. 环境变量文件规范（`.env.botX`）
- 文件: `.env.bot1` / `.env.bot2` / `.env.bot3`
- 权限: `chmod 600 .env.bot1 .env.bot2 .env.bot3`
- 示例（请用“现有值/新值”替换占位，勿写入文档/仓库）:
```
BOT_ID=bot1
BOT_NAME=机器人1号
BOT_TOKEN=<BOT1_TOKEN>
API_ID=<BOT1_API_ID>
API_HASH=<BOT1_API_HASH>
USE_LOCAL_STORAGE=true
LOG_LEVEL=INFO
PORT=8092
DATA_DIR=data/bot1
USER_SESSION_NAME=user_session_bot1
```
- 注意:
  - 三个机器人需使用独立的 `PORT` / `DATA_DIR` / `USER_SESSION_NAME`（如 8092/8093/8094）。
  - 不对外提供 HTTP 时，这些端口仅内部使用，无需在防火墙开放。

---

## 4. Supervisor 管理
- 服务单元: `bot1` / `bot2` / `bot3`
- 常用命令:
  ```bash
  # 状态/启动/停止/重启
  sudo supervisorctl status
  sudo supervisorctl start bot1
  sudo supervisorctl stop bot1
  sudo supervisorctl restart bot1

  # 批量
  sudo supervisorctl start all
  sudo supervisorctl stop all
  sudo supervisorctl restart all

  # 变更配置后
  sudo supervisorctl reread
  sudo supervisorctl update
  ```
- 配置模板（以 `bot1.conf` 为例）:
  ```
  [program:bot1]
  directory=/home/zwjmht/telegram_bots/bybot3.0
  command=/bin/bash -lc 'source /home/zwjmht/telegram_bots/bybot3.0/venv/bin/activate && export $(cat .env.bot1 | xargs) && exec python lsjmain.py --bot bot1'
  autostart=true
  autorestart=true
  stdout_logfile=/var/log/bot1.out.log
  stderr_logfile=/var/log/bot1.err.log
  stopsignal=TERM
  stopasgroup=true
  killasgroup=true
  ```

---

## 5. 常用维护操作
- 登录与环境激活：
  ```bash
  ssh -i "$env:USERPROFILE\\.ssh\\gcp_ed25519" zwjmht@34.124.198.248
  cd /home/zwjmht/telegram_bots/bybot3.0
  source venv/bin/activate
  ```
- 查看日志：
  ```bash
  sudo tail -n 200 /var/log/bot1.out.log /var/log/bot1.err.log
  sudo tail -n 200 /var/log/bot2.out.log /var/log/bot2.err.log
  sudo tail -n 200 /var/log/bot3.out.log /var/log/bot3.err.log
  ```
- 更新依赖（有变更时）：
  ```bash
  source venv/bin/activate
  pip install -r requirements.txt
  sudo supervisorctl restart bot1 bot2 bot3
  ```
- 资源与磁盘：
  ```bash
  top    # 或 htop（如已安装）
  free -m
  df -h
  ```

---

## 6. 变更流程与回滚
- 仅修改 `.env.bot*` 中的配置时：
  1) 备份原文件  2) 修改并保存  3) `sudo supervisorctl restart botX`
- 更新代码/依赖时：
  1) 进入目录并激活 venv  2) 安装/同步依赖  3) `sudo supervisorctl restart all`
- 回滚建议：
  - 保留 `.env.bot*` 与关键代码备份；
  - 如需回退版本，覆盖回旧目录并重启进程；
  - 建议启用磁盘快照（手动/每日）以便快速回滚。

---

## 7. 故障排查速查表
- 进程未运行/异常重启：
  - `sudo supervisorctl status` 查看状态；
  - 查看 `/var/log/botX.err.log` 错误堆栈；
  - 检查 `.env.botX` 是否存在格式错误/缺少变量。
- 网络/连接问题：
  - `ping api.telegram.org`，确认出站网络正常；
  - 若使用代理/防火墙，检查策略是否拦截。
- 依赖/环境问题：
  - `source venv/bin/activate` 后重新 `pip install -r requirements.txt`；
  - `python --version`、`pip --version` 校验运行环境。

---

## 8. 安全与合规建议
- 切勿将 `.env.bot*` 提交到任何仓库；本机与服务器均应设为 `600` 权限。
- Token 泄露或疑似被滥用时，立即在 @BotFather 重置，并同步更新到对应 `.env.bot*`。
- 建议后续将敏感变量迁移至 GCP Secret Manager，通过启动脚本注入环境变量。
- 如未来需要对外提供 HTTP 服务，务必经 Nginx/Caddy 反代并启用 HTTPS，仅暴露 80/443。

---

## 9. 附录：首次部署命令（备忘）
```bash
# 系统依赖
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3-venv python3-pip git supervisor ufw

# 项目目录与虚拟环境
mkdir -p /home/zwjmht/telegram_bots
# 代码已通过 SCP/SFTP 上传到 /home/zwjmht/telegram_bots/bybot3.0
cd /home/zwjmht/telegram_bots/bybot3.0
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Supervisor 生效
sudo systemctl enable --now supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start bot1 bot2 bot3
sudo supervisorctl status
```

> 维护联系人: （填写维护人/联系方式）

---

## 10. 常用命令速查

- SSH 登录
  ```bash
  ssh -i "$env:USERPROFILE\\.ssh\\gcp_ed25519" zwjmht@34.124.198.248
  ```

- 进程状态/启动/停止/重启
  ```bash
  sudo supervisorctl status
  sudo supervisorctl restart bot1
  sudo supervisorctl restart bot2
  sudo supervisorctl restart bot3
  sudo supervisorctl restart all

  sudo supervisorctl start bot1
  sudo supervisorctl stop bot1
  ```

- 变更配置后重新加载 Supervisor
  ```bash
  sudo supervisorctl reread
  sudo supervisorctl update
  ```

- 查看日志
  ```bash
  sudo tail -n 200 /var/log/bot1.out.log /var/log/bot1.err.log
  sudo tail -n 200 /var/log/bot2.out.log /var/log/bot2.err.log
  sudo tail -n 200 /var/log/bot3.out.log /var/log/bot3.err.log

  # 实时跟踪
  sudo tail -f /var/log/bot1.out.log /var/log/bot1.err.log
  ```

- 快速排障
  ```bash
  sudo systemctl status supervisor
  ps aux | grep lsjmain.py | grep -v grep
  top   # 或 htop（如已安装）
  ```

- 项目目录与虚拟环境
  ```bash
  cd /home/zwjmht/telegram_bots/bybot3.0
  source venv/bin/activate
  pip install -r requirements.txt
  ```

- 环境文件与权限
  ```bash
  ls -l .env.bot*
  chmod 600 .env.bot1 .env.bot2 .env.bot3
  ```


