# ==================== 简化版监听系统UI布局 ====================
"""
简化版监听系统的UI布局
基于原有UI，简化流程，更适合实时监听
"""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Tuple, Dict, Any

# ==================== 简化版监听管理按钮布局 ====================
SIMPLE_MONITOR_MENU_BUTTONS = [
    [("📡 我的监听任务", "view_simple_monitoring_tasks")],
    [("➕ 创建监听任务", "create_simple_monitoring_task")],
    [("⚙️ 监听设置", "simple_monitor_settings")],
    [("🔍 监听状态", "check_simple_monitoring_status")],
    [("🔙 返回主菜单", "show_main_menu")]
]

# ==================== 简化版监听任务列表按钮布局 ====================
SIMPLE_MONITORING_TASKS_BUTTONS = [
    # 监听任务列表按钮（动态生成）
    [
        ("➕ 新建监听任务", "create_simple_monitoring_task"),
        ("🔄 刷新列表", "view_simple_monitoring_tasks")
    ],
    [("🔙 返回监听菜单", "show_simple_monitor_menu")]
]

# ==================== 简化版创建监听任务按钮布局 ====================
CREATE_SIMPLE_MONITORING_TASK_BUTTONS = [
    [("🎯 选择目标频道", "select_simple_monitor_target_channel")],
    [("📡 添加源频道", "add_simple_monitor_source_channel")],
    [("⚙️ 监听设置", "configure_simple_monitor_settings")],
    [("✅ 创建任务", "confirm_create_simple_monitoring_task")],
    [("🔙 返回监听菜单", "show_simple_monitor_menu")]
]

# ==================== 简化版监听任务详情按钮布局 ====================
SIMPLE_MONITORING_TASK_DETAIL_BUTTONS = [
    [("▶️ 启动监听", "start_simple_monitoring_task:{task_id}")],
    [("⏹️ 停止监听", "stop_simple_monitoring_task:{task_id}")],
    [("✏️ 编辑任务", "edit_simple_monitoring_task:{task_id}")],
    [("🗑️ 删除任务", "delete_simple_monitoring_task:{task_id}")],
    [("🔙 返回任务列表", "view_simple_monitoring_tasks")]
]

# ==================== 简化版监听设置按钮布局 ====================
SIMPLE_MONITOR_CONFIG_BUTTONS = [
    [("🔧 过滤设置", "configure_simple_monitor_filters")],
    [("📊 统计信息", "view_simple_monitor_stats")],
    [("🔙 返回监听菜单", "show_simple_monitor_menu")]
]

# ==================== 源频道选择按钮布局 ====================
SOURCE_CHANNEL_SELECTION_BUTTONS = [
    # 源频道选择按钮（动态生成）
    [
        ("✅ 全选", "select_all_source_channels"),
        ("❌ 全不选", "select_none_source_channels")
    ],
    [("➕ 手动添加频道", "add_manual_source_channel")],
    [("🔙 返回创建任务", "create_simple_monitoring_task")]
]

# ==================== 目标频道选择按钮布局 ====================
TARGET_CHANNEL_SELECTION_BUTTONS = [
    # 目标频道选择按钮（动态生成）
    [("➕ 手动添加频道", "add_manual_target_channel")],
    [("🔙 返回创建任务", "create_simple_monitoring_task")]
]

# ==================== 监听状态显示按钮布局 ====================
MONITORING_STATUS_BUTTONS = [
    [("🔄 刷新状态", "check_simple_monitoring_status")],
    [("📊 详细统计", "view_simple_monitor_stats")],
    [("🔙 返回监听菜单", "show_simple_monitor_menu")]
]

# ==================== 任务确认按钮布局 ====================
SIMPLE_TASK_CONFIRMATION_BUTTONS = [
    [("✅ 确认创建", "confirm_create_simple_monitoring_task")],
    [("✏️ 修改设置", "edit_simple_monitoring_task_settings")],
    [("❌ 取消创建", "show_simple_monitor_menu")]
]

# ==================== 动态按钮生成函数 ====================
def generate_simple_monitoring_task_buttons(tasks: List[Dict[str, Any]], page: int = 0, page_size: int = 10) -> List[List[InlineKeyboardButton]]:
    """生成简化版监听任务列表按钮"""
    buttons = []
    
    # 计算分页
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_tasks = tasks[start_idx:end_idx]
    
    for i, task in enumerate(page_tasks):
        task_id = task.get('task_id', f'task_{i}')
        target_channel = task.get('target_channel', '未知频道')
        source_count = len(task.get('source_channels', []))
        status = task.get('status', 'unknown')
        
        # 状态图标
        status_icon = "🟢" if status == "active" else "🔴" if status == "stopped" else "⚪"
        
        # 按钮文本
        button_text = f"{status_icon} {target_channel} ({source_count}源)"
        
        # 按钮回调数据
        button_data = f"view_simple_monitoring_task:{task_id}"
        
        buttons.append([InlineKeyboardButton(button_text, callback_data=button_data)])
    
    # 添加分页按钮
    if len(tasks) > page_size:
        pagination_buttons = []
        
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"view_simple_monitoring_tasks:{page-1}"))
        
        if end_idx < len(tasks):
            pagination_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"view_simple_monitoring_tasks:{page+1}"))
        
        if pagination_buttons:
            buttons.append(pagination_buttons)
    
    return buttons

def generate_source_channel_buttons(channels: List[Dict[str, Any]], selected_channels: List[str] = None) -> List[List[InlineKeyboardButton]]:
    """生成源频道选择按钮"""
    if selected_channels is None:
        selected_channels = []
    
    buttons = []
    for channel in channels:
        channel_id = str(channel.get('id', ''))
        channel_name = channel.get('name', '未知频道')
        channel_username = channel.get('username', '')
        
        # 显示名称
        display_name = f"@{channel_username}" if channel_username else channel_name
        
        # 选择状态
        is_selected = channel_id in selected_channels
        status_icon = "✅" if is_selected else "⚪"
        
        button_text = f"{status_icon} {display_name}"
        button_data = f"toggle_source_channel:{channel_id}"
        
        buttons.append([InlineKeyboardButton(button_text, callback_data=button_data)])
    
    return buttons

def generate_target_channel_buttons(channels: List[Dict[str, Any]], selected_channel: str = None) -> List[List[InlineKeyboardButton]]:
    """生成目标频道选择按钮"""
    buttons = []
    for channel in channels:
        channel_id = str(channel.get('id', ''))
        channel_name = channel.get('name', '未知频道')
        channel_username = channel.get('username', '')
        
        # 显示名称
        display_name = f"@{channel_username}" if channel_username else channel_name
        
        # 选择状态
        is_selected = channel_id == selected_channel
        status_icon = "✅" if is_selected else "⚪"
        
        button_text = f"{status_icon} {display_name}"
        button_data = f"select_target_channel:{channel_id}"
        
        buttons.append([InlineKeyboardButton(button_text, callback_data=button_data)])
    
    return buttons

# ==================== 按钮布局模板 ====================
def generate_simple_button_layout(button_template: List[List[Tuple[str, str]]], **kwargs) -> InlineKeyboardMarkup:
    """生成简化版按钮布局"""
    buttons = []
    
    for button_row in button_template:
        row_buttons = []
        for button_text, callback_data in button_row:
            # 替换占位符
            for key, value in kwargs.items():
                placeholder = f"{{{key}}}"
                if placeholder in button_text:
                    button_text = button_text.replace(placeholder, str(value))
                if placeholder in callback_data:
                    callback_data = callback_data.replace(placeholder, str(value))
            
            row_buttons.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        buttons.append(row_buttons)
    
    return InlineKeyboardMarkup(buttons)

# ==================== 导出的按钮布局 ====================
__all__ = [
    "SIMPLE_MONITOR_MENU_BUTTONS",
    "SIMPLE_MONITORING_TASKS_BUTTONS", 
    "CREATE_SIMPLE_MONITORING_TASK_BUTTONS",
    "SIMPLE_MONITORING_TASK_DETAIL_BUTTONS",
    "SIMPLE_MONITOR_CONFIG_BUTTONS",
    "SOURCE_CHANNEL_SELECTION_BUTTONS",
    "TARGET_CHANNEL_SELECTION_BUTTONS",
    "MONITORING_STATUS_BUTTONS",
    "SIMPLE_TASK_CONFIRMATION_BUTTONS",
    "generate_simple_monitoring_task_buttons",
    "generate_source_channel_buttons", 
    "generate_target_channel_buttons",
    "generate_simple_button_layout"
]




