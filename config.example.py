#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置示例文件
请将此文件复制为config.py并填写实际配置
"""

# Telegram API配置
API_ID = 1234567  # 从 https://my.telegram.org 获取
API_HASH = "your_api_hash_here"  # 从 https://my.telegram.org 获取
BOT_TOKEN = "your_bot_token_here"  # 从 @BotFather 获取

# 机器人配置
BOT_ID = "default_bot"
BOT_NAME = "BTbot"

# Firebase配置（可选）
FIREBASE_CREDENTIALS = "path/to/firebase/credentials.json"
USE_FIREBASE = False

# AI配置
GEMINI_API_KEYS = [
    "your_gemini_api_key_1",
    "your_gemini_api_key_2"
]
AI_REWRITE_ENABLED = True

# 数据存储配置
USE_LOCAL_STORAGE = True
DATA_DIR = "data"

# 日志配置
LOG_LEVEL = "INFO"
LOG_FILE = "logs/bot.log"
ENABLE_FILE_LOGGING = True

# 默认用户配置
DEFAULT_USER_CONFIG = {
    # 搬运配置
    "cloning": {
        "enabled": True,
        "rate_limit": 10,  # 每分钟最大搬运消息数
        "delay_between_messages": 1  # 消息间延迟（秒）
    },
    
    # AI改写配置
    "ai_rewrite": {
        "enabled": True,
        "intensity": "medium",  # low, medium, high
        "preserve_emojis": True,
        "preserve_links": False
    },
    
    # 内容过滤配置
    "content_filter": {
        "remove_links": True,
        "remove_hashtags": False,
        "remove_usernames": False,
        "filter_keywords": [],
        "replacement_words": {}
    },
    
    # 反检测配置
    "anti_detection": {
        "enabled": True,
        "modify_media_ids": True,
        "add_random_delay": True
    },
    
    # Web配置
    "web": {
        "port": 8080,
        "host": "0.0.0.0"
    }
}

# 其他配置
MAX_CONCURRENT_TASKS = 5
TASK_CHECK_INTERVAL = 60  # 任务检查间隔（秒）