# BTbot Makefile
# 用于简化常用命令

# 默认目标
.PHONY: help install test run deploy check clean

help:
	@echo "BTbot Makefile 使用说明:"
	@echo "  make install     - 安装项目依赖"
	@echo "  make test        - 运行测试"
	@echo "  make run         - 运行机器人"
	@echo "  make deploy      - 部署检查"
	@echo "  make check       - 检查配置"
	@echo "  make clean       - 清理临时文件"

install:
	@echo "正在安装项目依赖..."
	pip install -r requirements.txt

test:
	@echo "运行模块导入测试..."
	python tests/test_imports.py

test-unit:
	@echo "运行单元测试..."
	python -m unittest tests/test_core.py

run:
	@echo "启动机器人..."
	python main.py

run-dev:
	@echo "启动开发模式机器人..."
	python main.py --debug

deploy:
	@echo "执行部署检查..."
	python deploy.py

check:
	@echo "检查配置..."
	python deploy.py --check

clean:
	@echo "清理临时文件..."
	rm -f *.pyc
	rm -f */*.pyc
	rm -rf __pycache__
	rm -rf */__pycache__
	@echo "清理完成"

setup:
	@echo "设置项目环境..."
	python deploy.py
	@echo "项目环境设置完成"

example:
	@echo "运行使用示例..."
	python examples/module_usage_example.py