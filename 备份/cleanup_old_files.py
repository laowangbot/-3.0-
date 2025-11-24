# ==================== GitHub仓库清理脚本 ====================
"""
清理GitHub仓库中的旧文件
删除不需要的文件，只保留干净版本和必要文件
"""

import os
import subprocess
import sys
from pathlib import Path

def get_files_to_delete():
    """获取需要删除的文件列表"""
    files_to_delete = [
        # 用户数据文件
        "data/",
        "sessions/",
        "*.session",
        "*.session-journal",
        "*.log",
        
        # Python缓存
        "__pycache__/",
        
        # 测试文件
        "test_*.py",
        "*_test.py",
        "check_*.py",
        "diagnose_*.py",
        "simple_*.py",
        "interactive_*.py",
        "set_log_level.py",
        
        # 备份文件
        "*.backup_*",
        "*.backup_v*",
        "*_fix.py",
        "*_hotfix*.py",
        "*_patch.py",
        
        # 分析报告
        "*_analysis.md",
        "*_report.md",
        "*_fix_report.md",
        "*_guide.md",
        "*_checklist.md",
        "*_summary.md",
        "*_optimization.md",
        "*_usage.md",
        "*_setup.md",
        "*_configuration.md",
        "*_deployment.md",
        "*_quick_setup.md",
        "*_user_api_guide.md",
        "*_user_api_session_guide.md",
        "*_issue_analysis.md",
        "*_issue_deep_analysis.md",
        "*_management_report.md",
        "*_speed_optimization_report.md",
        "*_system_analysis.md",
        "*_tail_fix_report.md",
        "*_log_optimization.py",
        "*_fix_summary.md",
        "*_monitoring_analysis.md",
        "*_concurrent_monitoring_analysis.md",
        "*_filtering_bug_fix_report.md",
        "*_media_group_fix_report.md",
        "*_monitoring_fixes_report.md",
        "*_monitoring_system_analysis.md",
        "*_monitoring_tail_fix_report.md",
        "*_optimization_summary_report.md",
        "*_intelligent_message_management_report.md",
        "*_intelligent_speed_optimization_report.md",
        
        # 配置文件（保留clan_bot中的）
        "channel_data.json",
        "bot_session_default.session",
        "bot_session_default.session-journal",
        
        # 特定文件
        "apply_hotfix.py",
        "apply_hotfix_v2.py",
        "cloning_engine_fix.py",
        "cloning_engine_hotfix.py",
        "cloning_engine_hotfix_v2.py",
        "cloning_engine_patch.py",
        "cloning_issue_analysis.md",
        "cloning_issue_deep_analysis.md",
        "concurrent_monitoring_analysis.md",
        "deployment_checklist.md",
        "diagnose_filtering.py",
        "filtering_bug_fix_report.md",
        "firebase_optimization_guide.md",
        "firebase_setup_guide.md",
        "firebase_usage_analysis.md",
        "intelligent_message_management_report.md",
        "intelligent_speed_optimization_report.md",
        "interactive_monitor_test.py",
        "interactive_monitor_test.session",
        "media_group_fix_report.md",
        "monitoring_fixes_report.md",
        "monitoring_log_optimization.py",
        "monitoring_system_analysis.md",
        "monitoring_tail_fix_report.md",
        "optimization_summary_report.md",
        "render_configuration_guide.md",
        "render_deployment_guide.md",
        "render_quick_setup.md",
        "render_user_api_guide.md",
        "render_user_api_session_guide.md",
        "simple_concurrent_test.py",
        "simple_monitoring_ui.py",
        "simple_optimization_test.py",
        "simple_realtime_fix.py",
        "simple_start.py",
        "test_api_optimization.py",
        "test_batch_optimization.py",
        "test_blank_message_detection.py",
        "test_bulk_task_fix.py",
        "test_channel_config_debug.py",
        "test_firebase_optimization.py",
        "test_intelligent_speed.py",
        "test_logging.py",
        "test_media_group.py",
        "test_media_group_fix.py",
        "test_monitor_core.py",
        "test_monitor_core.session",
        "test_monitor_logic.py",
        "test_monitoring_config_fix.py",
        "test_monitoring_fixes.py",
        "test_monitoring_system.py",
        "test_monitoring_tail_fix.py",
        "test_optimization.py",
        "test_optimization_integration.py",
        "test_user_state_fix.py",
        "test_with_existing_session.py",
        "user_session.session",
        "check_monitor.session",
        "independent_monitor.session",
        "independent_monitor.session-journal",
        "simple_monitor.session",
        
        # 中文文件名
        "分批监听系统说明.md",
        "日志优化说明.md", 
        "简化版监听系统启动指南.md",
        
        # 其他不需要的文件
        "bulk_task_fix_summary.md",
        "bulk_task_issue_analysis.md",
        "cloning_issue_analysis.md",
        "cloning_issue_deep_analysis.md",
        "concurrent_monitoring_analysis.md",
        "deployment_checklist.md",
        "filtering_bug_fix_report.md",
        "firebase_optimization_guide.md",
        "firebase_setup_guide.md",
        "firebase_usage_analysis.md",
        "intelligent_message_management_report.md",
        "intelligent_speed_optimization_report.md",
        "media_group_fix_report.md",
        "monitoring_fixes_report.md",
        "monitoring_system_analysis.md",
        "monitoring_tail_fix_report.md",
        "optimization_summary_report.md",
        "render_configuration_guide.md",
        "render_deployment_guide.md",
        "render_quick_setup.md",
        "render_user_api_guide.md",
        "render_user_api_session_guide.md"
    ]
    
    return files_to_delete

def delete_files():
    """删除文件"""
    files_to_delete = get_files_to_delete()
    deleted_count = 0
    
    print("🗑️  开始删除旧文件...")
    print("=" * 50)
    
    for file_pattern in files_to_delete:
        try:
            # 使用git rm删除文件
            if file_pattern.endswith('/'):
                # 删除目录
                result = subprocess.run(['git', 'rm', '-r', file_pattern], 
                                      capture_output=True, text=True)
            else:
                # 删除文件
                result = subprocess.run(['git', 'rm', file_pattern], 
                                      capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ 删除: {file_pattern}")
                deleted_count += 1
            else:
                # 文件不存在或已被删除
                if "did not match any files" not in result.stderr:
                    print(f"⚠️  跳过: {file_pattern} ({result.stderr.strip()})")
                    
        except Exception as e:
            print(f"❌ 删除失败: {file_pattern} - {e}")
    
    print("=" * 50)
    print(f"📊 删除了 {deleted_count} 个文件/目录")
    return deleted_count

def commit_cleanup():
    """提交清理更改"""
    try:
        print("\n💾 提交清理更改...")
        subprocess.run(['git', 'add', '-A'], check=True)
        subprocess.run(['git', 'commit', '-m', '🧹 清理GitHub仓库旧文件\n\n- 删除用户数据文件\n- 删除测试文件\n- 删除分析报告\n- 删除备份文件\n- 只保留干净版本和核心文件'], check=True)
        print("✅ 清理更改已提交")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 提交失败: {e}")
        return False

def push_to_github():
    """推送到GitHub"""
    try:
        print("\n🚀 推送到GitHub...")
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        print("✅ 成功推送到GitHub!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 推送失败: {e}")
        return False

def main():
    """主函数"""
    print("🧹 GitHub仓库清理工具")
    print("=" * 50)
    print("⚠️  警告: 此操作将删除大量文件!")
    print("📋 将删除:")
    print("   - 用户数据文件 (data/, sessions/, *.session)")
    print("   - 测试文件 (test_*.py, *_test.py)")
    print("   - 分析报告 (*_analysis.md, *_report.md)")
    print("   - 备份文件 (*.backup_*, *_fix.py)")
    print("   - Python缓存 (__pycache__/)")
    print("   - 日志文件 (*.log)")
    print()
    
    # 确认操作
    confirm = input("确认继续清理? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ 操作已取消")
        return
    
    print("\n🚀 开始清理...")
    
    # 删除文件
    deleted_count = delete_files()
    
    if deleted_count > 0:
        # 提交更改
        if commit_cleanup():
            # 推送到GitHub
            if push_to_github():
                print("\n🎉 仓库清理完成!")
                print(f"📊 统计: 删除了 {deleted_count} 个文件/目录")
                print("🌐 GitHub仓库已清理: https://github.com/laowangbot/-3.0-.git")
            else:
                print("\n❌ 推送失败，请手动推送")
        else:
            print("\n❌ 提交失败")
    else:
        print("\n✅ 没有需要删除的文件")

if __name__ == "__main__":
    main()
