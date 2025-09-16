# ==================== 机器人配置文件 ====================
"""
机器人配置文件
包含所有敏感配置信息
"""

import os
from typing import Dict, Any

# ==================== 机器人配置 ====================

# 机器人基本信息
BOT_ID = "your_bot_id"
BOT_NAME = "your_bot_name"
BOT_VERSION = "3.0.0"
BOT_DESCRIPTION = "Telegram搬运机器人"
API_ID = "your_api_id"
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# ==================== Render配置 ====================

# 端口配置
PORT = 8092
RENDER_EXTERNAL_URL = "your_render_url"  # 请替换为实际的Render URL

# ==================== Firebase配置 ====================

# Firebase服务账号凭据（请在环境变量中配置实际值）
FIREBASE_CREDENTIALS = {
    "type": "service_account",
    "project_id": "your_project_id",
    "private_key_id": "your_private_key_id",
    "private_key": "your_private_key",
    "client_email": "your_client_email",
    "client_id": "your_client_id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "your_client_x509_cert_url",
    "universe_domain": "googleapis.com"
}

# Firebase项目ID
FIREBASE_PROJECT_ID = "your_project_id"

# ==================== 默认用户配置 ====================
DEFAULT_USER_CONFIG = {
    # 内容过滤设置
    "keywords_enabled": False,  # 关键字过滤开关
    "replacements_enabled": False,  # 敏感词替换开关
    "filter_keywords": [],
    "replacement_words": {},
    "content_removal": False,
    "remove_links": False,
    "remove_links_mode": "links_only",  # links_only, remove_message
    "remove_magnet_links": False,
    "remove_all_links": False,
    "remove_hashtags": False,
    "remove_usernames": False,
    
    # 增强过滤设置
    "enhanced_filter_enabled": False,  # 增强过滤开关
    "enhanced_filter_mode": "moderate",  # aggressive, moderate, conservative
    
    # 文件过滤设置
    "filter_photo": False,
    "filter_video": False,
    "file_extensions": [],
    
    # 按钮过滤设置
    "filter_buttons": False,
    "button_filter_mode": "remove_all",  # remove_all, keep_safe, custom
    
    # 内容增强功能
    "tail_text": "",
    "tail_position": "end",  # start, end
    "tail_frequency": "always",  # always, interval, random
    "tail_interval": 5,
    "tail_probability": 1.0,
    
    "additional_buttons": [],
    "button_frequency": "always",  # always, interval, random
    "button_interval": 5,
    "button_probability": 1.0,
    
    # 评论搬运设置已移除
    
    # 监听设置
    "monitor_enabled": False,
    "monitored_pairs": [],
    
    # 频道组设置
    "channel_pairs": [],
    "channel_filters": {},  # 频道组独立过滤配置
    "max_channel_pairs": 100,
    
    # 任务设置 - 优化并发处理能力
    "max_concurrent_tasks": 50,  # 支持最多50个并发任务（从10提升到50）
    "max_user_concurrent_tasks": 100,  # 用户最大并发任务数（从20提升到100）
    "task_timeout": 86400,  # 24小时 - 适应大量消息搬运
    "max_task_time": 172800,  # 单个任务最大运行时间（48小时）- 支持超大规模搬运
    "progress_update_timeout": 172800,  # 进度更新循环最大运行时间（48小时）- 支持长期运行
    
    # 性能设置 - 优化处理速度
    "message_delay": 0.02,  # 减少消息延迟（从0.05减少到0.02）
    "media_group_delay": 0.5,  # 媒体组处理延迟（从0.3增加到0.5）
    "max_messages_per_check": 200,  # 每次检查最大消息数（从100增加到200）
    
    # API限制保护
    "api_rate_limit": 30,  # 每分钟最多API调用次数
    "api_retry_attempts": 5,  # API重试次数
    "api_retry_delay": 2,  # API重试延迟（秒）
    "api_backoff_factor": 2,  # 指数退避因子
    
    # 内存管理
    "max_processed_messages": 10000,  # 最大存储已处理消息数
    "message_cleanup_interval": 3600,  # 消息清理间隔（秒）
    "memory_usage_threshold": 0.8,  # 内存使用阈值
    
    # 错误处理
    "max_consecutive_errors": 5,  # 最大连续错误数
    "error_recovery_delay": 30,  # 错误恢复延迟（秒）
    "circuit_breaker_threshold": 10,  # 熔断器阈值
    
    # 性能监控
    "metrics_collection_interval": 60,  # 指标收集间隔（秒）
    "performance_alert_threshold": 0.9,  # 性能告警阈值
    "slow_task_threshold": 10,  # 慢任务阈值（秒）
    
    # 监听系统优化配置
    "batch_size": 5,  # 分批处理大小（减少到5个频道）
    "check_interval": 5,  # 检查间隔（增加到5秒）
    
    # Firebase批量存储设置
    "firebase_batch_enabled": True,  # 是否启用Firebase批量存储
    "firebase_batch_interval": 300,  # 批量存储间隔（秒），默认5分钟
    "firebase_max_batch_size": 100,  # 最大批量大小
}

# ==================== 环境变量配置 ====================

def get_config() -> Dict[str, Any]:
    """获取配置信息，优先使用环境变量"""
    # 检查是否在Render环境（多种检测方式）
    is_render = (
        os.getenv("RENDER") is not None or  # Render官方环境变量
        os.getenv("RENDER_EXTERNAL_URL") is not None or  # 我们的自定义环境变量
        "render.com" in os.getenv("HOST", "")  # Render域名检测
    )
    
    # 只在非Render环境加载.env文件
    if not is_render:
        from dotenv import load_dotenv
        load_dotenv()
    
    # 处理Firebase凭据
    firebase_credentials = FIREBASE_CREDENTIALS
    firebase_credentials_env = os.getenv("FIREBASE_CREDENTIALS")
    
    if firebase_credentials_env and firebase_credentials_env != "your_firebase_credentials_json":
        try:
            # 尝试解析环境变量中的JSON格式Firebase凭据
            import json
            firebase_credentials = json.loads(firebase_credentials_env)
        except json.JSONDecodeError as e:
            print(f"⚠️ Firebase凭据JSON格式错误: {e}")
            print("使用默认配置，请检查FIREBASE_CREDENTIALS环境变量格式")
    
    # 检查是否使用本地开发模式（默认使用本地存储）
    use_local_storage = os.getenv("USE_LOCAL_STORAGE", "true").lower() == "true"
    
    # 获取配置值，优先使用环境变量
    bot_id = os.getenv("BOT_ID", BOT_ID)
    bot_name = os.getenv("BOT_NAME", BOT_NAME)
    api_id_str = os.getenv("API_ID", API_ID)
    api_hash = os.getenv("API_HASH", API_HASH)
    bot_token = os.getenv("BOT_TOKEN", BOT_TOKEN)
    

    
    # 处理API_ID
    if api_id_str and api_id_str != "your_api_id":
        try:
            api_id = int(api_id_str)
        except ValueError:
            api_id = 12345
    else:
        api_id = 12345
    
    # 合并默认配置和基础配置
    config = DEFAULT_USER_CONFIG.copy()
    
    # 添加基础配置
    config.update({
        # 机器人配置
        "bot_id": bot_id,
        "bot_name": bot_name,
        "api_id": api_id,
        "api_hash": api_hash,
        "bot_token": bot_token,
        
        # Render配置
        "port": int(os.getenv("PORT", PORT)),
        "render_external_url": os.getenv("RENDER_EXTERNAL_URL", RENDER_EXTERNAL_URL),
        
        # Firebase配置
        "firebase_credentials": firebase_credentials,
        "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID", FIREBASE_PROJECT_ID),
        
        # 存储配置
        "use_local_storage": use_local_storage,
        
        # 环境信息
        "is_render": is_render,
    })
    
    return config

# ==================== 配置验证 ====================

def validate_config() -> bool:
    """验证配置是否完整"""
    config = get_config()
    
    required_fields = [
        "bot_id", "bot_name", "api_id", "api_hash", 
        "bot_token", "firebase_project_id"
    ]
    
    for field in required_fields:
        if not config.get(field):
            print(f"❌ 缺少必需的配置字段: {field}")
            return False
    
    if not config.get("firebase_credentials"):
        print("❌ 缺少Firebase凭据配置")
        return False
    
    print("✅ 配置验证通过")
    return True

# ==================== 配置信息显示 ====================

def show_config_info():
    """显示配置信息（隐藏敏感数据）"""
    config = get_config()
    
    print("🔧 机器人配置信息:")
    print(f"   机器人ID: {config['bot_id']}")
    print(f"   机器人名称: {config['bot_name']}")
    print(f"   API ID: {config['api_id']}")
    print(f"   API Hash: {config['api_hash'][:8]}...")
    print(f"   Bot Token: {config['bot_token'][:8]}...")
    print(f"   Firebase项目: {config['firebase_project_id']}")
    print(f"   端口: {config['port']}")

# ==================== 导出配置 ====================
__all__ = [
    "BOT_ID", "BOT_NAME", "API_ID", "API_HASH", "BOT_TOKEN",
    "PORT", "RENDER_EXTERNAL_URL",
    "FIREBASE_CREDENTIALS", "FIREBASE_PROJECT_ID",
    "DEFAULT_USER_CONFIG",
    "validate_config", "get_config", "show_config_info"
]
