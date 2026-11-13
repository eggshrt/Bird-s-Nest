#!/bin/bash
# 插件安装后自动执行
cd "$(dirname "$0")/.." && python3 tools/post_install.py
