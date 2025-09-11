# ==================== 用户界面布局文件 ====================
"""
此文件包含机器人的所有按钮布局和回调数据结构
用于生成动态用户界面
"""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Tuple, Dict, Any

# ==================== 主菜单按钮布局（带 User API 登录）====================
MAIN_MENU_BUTTONS_WITH_USER_API = [
    [
        ("🚀 搬运管理", "show_clone_test"),
        ("📡 监听管理", "show_monitor_menu")
    ],
    [
        ("📋 频道管理", "show_channel_admin_test"),
        ("🔧 过滤设定", "show_feature_config_menu")
    ],
    [
        ("📜 我的任务", "view_tasks"),
        ("📋 历史记录", "view_history")
    ],
    [
        ("🔍 当前配置", "view_config"),
        ("❓ 帮助", "show_help")
    ],
    [
        ("🔐 User API 登录", "start_user_api_login"),
        ("🔍 API 状态", "user_api_status")
    ]
]

# ==================== 主菜单按钮布局（User API 已登录）====================
MAIN_MENU_BUTTONS_USER_API_LOGGED_IN = [
    [
        ("🚀 搬运管理", "show_clone_test"),
        ("📡 监听管理", "show_monitor_menu")
    ],
    [
        ("📋 频道管理", "show_channel_admin_test"),
        ("🔧 过滤设定", "show_feature_config_menu")
    ],
    [
        ("📜 我的任务", "view_tasks"),
        ("📋 历史记录", "view_history")
    ],
    [
        ("🔍 当前配置", "view_config"),
        ("❓ 帮助", "show_help")
    ],
    [
        ("🔐 User API 登出", "logout_user_api"),
        ("🔍 API 状态", "user_api_status")
    ]
]

# ==================== 频道管理按钮布局 ====================
CHANNEL_MANAGEMENT_BUTTONS = [
    # 频道组列表按钮（动态生成）
    # 编辑和删除按钮
    [
        ("🔲 批量选择", "batch_select_channels"),
        ("🗑️ 一键清空", "clear_all_channels")
    ],
    [
        ("➕ 新增频道组", "add_channel_pair")
    ],
    [
        ("🔙 返回主菜单", "show_main_menu")
    ]
]

# ==================== 频道组编辑按钮布局 ====================
CHANNEL_PAIR_EDIT_BUTTONS = [
    [("🔄 更改采集频道", "edit_pair_source:{pair_id}")],
    [("🔄 更改目标频道", "edit_pair_target:{pair_id}")],
    [("{status_text}该频道组", "toggle_pair_enabled:{pair_id}")],
    [("{filter_status} {filter_text}", "manage_pair_filters:{pair_id}")],
    [("🔙 返回管理菜单", "show_channel_config_menu")]
]

# ==================== 批量操作按钮布局 ====================
BATCH_OPERATION_BUTTONS = [
    # 批量选择按钮（动态生成）
    [
        ("🗑️ 删除选中({selected_count})", "batch_delete_selected"),
        ("❌ 取消", "show_channel_config_menu")
    ],
    [("🔙 返回管理", "show_channel_config_menu")]
]

# ==================== 功能配置按钮布局 ====================
FEATURE_CONFIG_BUTTONS = [
    [
        ("📝 关键字过滤 ({keywords_count})", "manage_filter_keywords"),
        ("🔀 敏感词替换 ({replacements_count})", "manage_replacement_words")
    ],
    [
        ("👤 移除用户名", "toggle_remove_usernames"),
        ("🚀 增强版链接过滤", "show_enhanced_filter_menu")
    ],
        [
        ("🔘 按钮移除", "manage_filter_buttons"),
        ("📝 纯文本过滤", "manage_content_removal")
    ],
    [
        ("✨ 附加文字小尾巴", "request_tail_text"),
        ("📋 附加按钮", "request_buttons")
    ],
    [
        # 评论转发功能已移除
        ("🎯 附加频率", "show_frequency_settings")
    ],
    [
        ("🔙 返回主菜单", "show_main_menu")
    ]
]



# ==================== 增强过滤按钮布局 ====================
ENHANCED_FILTER_BUTTONS = [
    [("🚀 增强版链接过滤: {enhanced_status}", "toggle_enhanced_filter")],
    [("⚙️ 过滤模式: {mode_text}", "toggle_enhanced_filter_mode")],
    [("👁️ 预览效果", "preview_enhanced_filter")],
    [("🔙 返回功能配置", "show_feature_config_menu")]
]

# ==================== 链接过滤按钮布局 ====================
LINK_FILTER_BUTTONS = [
    [("🔗 过滤所有链接: {links_status}", "toggle_remove_all_links")],
    [("🔧 过滤方式: {mode_text}", "toggle_remove_links_mode")],
    [("🔙 返回功能设定", "show_feature_config_menu")]
]



# ==================== 评论相关按钮布局已移除 ====================
# 评论转发功能已移除

# ==================== 频率设置按钮布局 ====================
FREQUENCY_SETTINGS_BUTTONS = [
    [
        ("📝 附加文字频率", "config_tail_frequency"),
        ("📋 附加按钮频率", "config_button_frequency")
    ],
    [("🔙 返回功能设定", "show_feature_config_menu")]
]

# ==================== 文字频率设置按钮布局 ====================
TAIL_FREQUENCY_BUTTONS = [
    [("✅ 每条消息都添加", "set_tail_frequency:always")],
    [("⚪ 间隔添加", "set_tail_frequency:interval")],
    [("⚪ 随机添加", "set_tail_frequency:random")],
    [("🔙 返回频率设置", "show_frequency_settings")]
]

# ==================== 按钮频率设置按钮布局 ====================
BUTTON_FREQUENCY_BUTTONS = [
    [("✅ 每条消息都添加", "set_button_frequency:always")],
    [("⚪ 间隔添加", "set_button_frequency:interval")],
    [("⚪ 随机添加", "set_button_frequency:random")],
    [("🔙 返回频率设置", "show_frequency_settings")]
]

# ==================== 监听管理按钮布局（分批轮换版本）====================
MONITOR_MENU_BUTTONS = [
    [("📡 我的监听任务", "view_monitoring_tasks")],
    [("➕ 创建监听任务", "create_monitoring_task")],
    [("🔍 监听状态", "check_monitoring_status")],
    [("⚙️ 监听设置", "monitor_settings")],
    [("🔙 返回主菜单", "show_main_menu")]
]

# ==================== 监听任务管理按钮布局 ====================
MONITORING_TASKS_BUTTONS = [
    # 监听任务列表按钮（动态生成）
    [
        ("➕ 新建监听任务", "create_monitoring_task"),
        ("🔄 刷新列表", "view_monitoring_tasks")
    ],
    [("🔙 返回监听菜单", "show_monitor_menu")]
]

# ==================== 创建监听任务按钮布局 ====================
CREATE_MONITORING_TASK_BUTTONS = [
    [("🎯 选择目标频道", "select_monitor_target_channel")],
    [("📡 添加源频道", "add_monitor_source_channel")],
    [("⚙️ 监听设置", "configure_monitor_settings")],
    [("✅ 创建任务", "confirm_create_monitoring_task")],
    [("🔙 返回监听菜单", "show_monitor_menu")]
]

# ==================== 监听任务详情按钮布局 ====================
MONITORING_TASK_DETAIL_BUTTONS = [
    [("▶️ 启动监听", "start_monitoring_task:{task_id}")],
    [("⏸️ 暂停监听", "pause_monitoring_task:{task_id}")],
    [("⏹️ 停止监听", "stop_monitoring_task:{task_id}")],
    [("✏️ 编辑任务", "edit_monitoring_task:{task_id}")],
    [("🔢 设置起始消息ID", "set_monitoring_start_id:{task_id}")],
    [("🗑️ 删除任务", "delete_monitoring_task:{task_id}")],
    [("🔙 返回任务列表", "view_monitoring_tasks")]
]

# ==================== 监听设置按钮布局 ====================
MONITOR_CONFIG_BUTTONS = [
    [("📊 分批设置", "configure_batch_settings")],
    [("⏰ 检查间隔: {interval}秒", "set_monitor_interval")],
    [("🔄 重试次数: {retries}次", "set_monitor_retries")],
    [("⏱️ 重试延迟: {delay}秒", "set_monitor_retry_delay")],
    [("🔙 返回监听菜单", "show_monitor_menu")]
]

# ==================== 分批设置按钮布局 ====================
BATCH_SETTINGS_BUTTONS = [
    [("📦 批次大小: {batch_size}个频道", "set_batch_size")],
    [("⏱️ 检查间隔: {interval}秒", "set_batch_interval")],
    [("🔧 高级设置", "advanced_batch_settings")],
    [("🔙 返回监听设置", "monitor_settings")]
]

# ==================== 任务确认按钮布局 ====================
TASK_CONFIRMATION_BUTTONS = [
    [("✅ 确认开始搬运 ({task_count} 组频道)", "confirm_clone_action:{task_id}")],
    [("❌ 取消", "cancel:{task_id}")]
]

# ==================== 任务管理按钮布局 ====================
TASK_MANAGEMENT_BUTTONS = [
    [("📋 查看历史记录", "view_history")],
    [("📜 查看我的任务", "view_tasks")],
    [("🔙 返回主菜单", "show_main_menu")]
]

# ==================== 频道管理测试按钮布局 ====================
CHANNEL_ADMIN_TEST_BUTTONS = [
    [("🔙 返回主菜单", "show_main_menu")]
]

# ==================== 帮助和状态按钮布局 ====================
HELP_AND_STATUS_BUTTONS = [
    [("🔍 刷新状态", "refresh_floodwait_status")],
    [("🔙 返回主菜单", "show_main_menu")]
]

# ==================== 按钮状态文本映射 ====================
BUTTON_STATUS_MAPPING = {
    "enabled": "✅",
    "disabled": "❌",
    "on": "✅ 开启",
    "off": "❌ 关闭",
    "always": "✅ 每条消息都添加",
    "interval": "⚪ 间隔添加",
    "random": "⚪ 随机添加",
            "links_only": "📝 智能移除链接",
    "remove_message": "🗑️ 移除整条消息",
    # 评论相关状态映射
    # 评论相关状态映射已移除
}

# ==================== 按钮布局生成函数 ====================
def generate_button_layout(button_template: List[List[Tuple[str, str]]], **kwargs) -> InlineKeyboardMarkup:
    """根据模板和参数生成按钮布局"""
    buttons = []
    for row in button_template:
        button_row = []
        for button_text, callback_data in row:
            # 替换占位符
            for key, value in kwargs.items():
                placeholder = f"{{{key}}}"
                if placeholder in button_text:
                    button_text = button_text.replace(placeholder, str(value))
                if placeholder in callback_data:
                    callback_data = callback_data.replace(placeholder, str(value))
            
            button_row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        buttons.append(button_row)
    
    return InlineKeyboardMarkup(buttons)

# ==================== 动态按钮生成函数 ====================
def generate_channel_list_buttons(channel_pairs: List[Dict[str, Any]], user_id: str, page: int = 0, page_size: int = 30) -> List[List[InlineKeyboardButton]]:
    """生成频道组列表按钮（支持分页）
    
    Args:
        channel_pairs: 频道组列表
        user_id: 用户ID
        page: 当前页码（从0开始）
        page_size: 每页显示数量
    
    Returns:
        按钮列表
    """
    buttons = []
    
    # 计算分页范围
    start_index = page * page_size
    end_index = min(start_index + page_size, len(channel_pairs))
    
    # 生成当前页的频道组按钮
    for i in range(start_index, end_index):
        pair = channel_pairs[i]
        source_name = pair.get('source_name', f'频道{i+1}')
        target_name = pair.get('target_name', f'目标{i+1}')
        enabled = pair.get('enabled', True)
        status_icon = "✅" if enabled else "❌"
        
        # 检查是否为私密频道
        is_private_source = pair.get('is_private_source', False)
        is_private_target = pair.get('is_private_target', False)
        
        # 添加私密频道标识
        private_icon = ""
        if is_private_source or is_private_target:
            private_icon = " 🔒"
        
        button_text = f"{status_icon} {source_name} → {target_name}{private_icon}"
        buttons.append([
            InlineKeyboardButton(button_text, callback_data=f"edit_channel_pair:{i}"),
            InlineKeyboardButton(f"🗑️", callback_data=f"delete_channel_pair:{i}")
        ])
    
    return buttons

def generate_pagination_buttons(total_items: int, current_page: int = 0, page_size: int = 30) -> List[List[InlineKeyboardButton]]:
    """生成分页按钮
    
    Args:
        total_items: 总项目数
        current_page: 当前页码（从0开始）
        page_size: 每页显示数量
    
    Returns:
        分页按钮列表
    """
    buttons = []
    
    # 计算总页数
    total_pages = (total_items + page_size - 1) // page_size
    
    # 只有超过一页时才显示分页按钮
    if total_pages > 1:
        pagination_row = []
        
        # 上一页按钮
        if current_page > 0:
            pagination_row.append(
                InlineKeyboardButton("⬅️ 上一页", callback_data=f"channel_page:{current_page - 1}")
            )
        
        # 页码信息
        pagination_row.append(
            InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="page_info")
        )
        
        # 下一页按钮
        if current_page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton("下一页 ➡️", callback_data=f"channel_page:{current_page + 1}")
            )
        
        buttons.append(pagination_row)
    
    return buttons

def generate_monitor_channel_buttons(monitored_pairs: List[Dict[str, Any]]) -> List[List[InlineKeyboardButton]]:
    """生成监听频道选择按钮"""
    buttons = []
    for i, pair in enumerate(monitored_pairs):
        source_name = pair.get('source_name', f'频道{i+1}')
        target_name = pair.get('target_name', f'目标{i+1}')
        monitored = pair.get('monitored', False)
        status_icon = "✅" if monitored else "⚪"
        
        button_text = f"{status_icon} {source_name} → {target_name}"
        buttons.append([
            InlineKeyboardButton(button_text, callback_data=f"toggle_monitor_pair:{i}")
        ])
    
    return buttons

# ==================== 导出所有按钮布局 ====================
__all__ = [
    "MAIN_MENU_BUTTONS_WITH_USER_API",
    "MAIN_MENU_BUTTONS_USER_API_LOGGED_IN",
    "CHANNEL_MANAGEMENT_BUTTONS", 
    "CHANNEL_PAIR_EDIT_BUTTONS",
    "BATCH_OPERATION_BUTTONS",
    "FEATURE_CONFIG_BUTTONS",
    "ENHANCED_FILTER_BUTTONS",
    "LINK_FILTER_BUTTONS",
    "FREQUENCY_SETTINGS_BUTTONS",
    "TAIL_FREQUENCY_BUTTONS",
    "BUTTON_FREQUENCY_BUTTONS",
    "MONITOR_MENU_BUTTONS",
    "MONITORING_TASKS_BUTTONS",
    "CREATE_MONITORING_TASK_BUTTONS",
    "MONITORING_TASK_DETAIL_BUTTONS",
    "MONITOR_CONFIG_BUTTONS",
    "BATCH_SETTINGS_BUTTONS",
    "TASK_CONFIRMATION_BUTTONS",
    "TASK_MANAGEMENT_BUTTONS",
    "CHANNEL_ADMIN_TEST_BUTTONS",
    "HELP_AND_STATUS_BUTTONS",
    "BUTTON_STATUS_MAPPING",
    "generate_button_layout",
    "generate_channel_list_buttons",
    "generate_pagination_buttons",
    "generate_monitor_channel_buttons"
]


# 简化版监听系统UI
from simple_monitoring_ui import *
