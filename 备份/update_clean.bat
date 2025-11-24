@echo off
chcp 65001 >nul
echo 🚀 更新干净版本到GitHub
echo ================================
echo.

echo 📋 运行Python更新脚本...
python update_clean_version.py

echo.
echo ✅ 更新完成！
pause
