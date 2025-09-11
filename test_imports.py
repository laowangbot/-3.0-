#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试导入是否正常
"""

import sys
import os

def test_imports():
    """测试所有导入"""
    print("🧪 测试导入...")
    
    try:
        # 测试简化版监听引擎导入
        from simple_monitoring_engine import SimpleMonitoringEngine
        print("✅ SimpleMonitoringEngine 导入成功")
        
        # 测试简化版UI布局导入
        from simple_monitoring_ui import (
            SIMPLE_MONITOR_MENU_BUTTONS, 
            SIMPLE_MONITORING_TASKS_BUTTONS,
            CREATE_SIMPLE_MONITORING_TASK_BUTTONS, 
            MONITORING_STATUS_BUTTONS
        )
        print("✅ 简化版UI布局 导入成功")
        
        # 测试其他必要模块
        from user_api_manager import UserAPIManager
        print("✅ UserAPIManager 导入成功")
        
        from message_engine import MessageEngine
        print("✅ MessageEngine 导入成功")
        
        from data_manager import DataManager
        print("✅ DataManager 导入成功")
        
        # 测试主程序导入
        print("\n🔍 测试主程序导入...")
        try:
            # 只测试导入，不执行
            import main
            print("✅ main.py 导入成功")
        except Exception as e:
            print(f"❌ main.py 导入失败: {e}")
            return False
        
        print("\n🎉 所有导入测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 导入测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)




