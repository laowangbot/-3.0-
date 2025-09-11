#!/usr/bin/env python3
# ==================== 日志级别设置脚本 ====================
"""
用于设置机器人日志级别的便捷脚本
"""

import os
import sys

def set_log_level(level: str):
    """设置日志级别"""
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    if level.upper() not in valid_levels:
        print(f"❌ 无效的日志级别: {level}")
        print(f"✅ 有效的级别: {', '.join(valid_levels)}")
        return False
    
    # 设置环境变量
    os.environ['LOG_LEVEL'] = level.upper()
    print(f"✅ 日志级别已设置为: {level.upper()}")
    return True

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python set_log_level.py <级别>")
        print("级别: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        print("\n示例:")
        print("  python set_log_level.py INFO    # 显示一般信息")
        print("  python set_log_level.py DEBUG   # 显示详细调试信息")
        print("  python set_log_level.py WARNING # 只显示警告和错误")
        return
    
    level = sys.argv[1]
    if set_log_level(level):
        print(f"\n💡 提示: 现在可以运行机器人，日志级别为 {level.upper()}")
        print("💡 要永久设置，请将以下内容添加到环境变量:")
        print(f"   export LOG_LEVEL={level.upper()}")

if __name__ == "__main__":
    main()




