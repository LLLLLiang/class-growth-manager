#!/bin/bash
# 班级成长管家 - PythonAnywhere 更新脚本
# 在 PythonAnywhere Bash 控制台中运行此脚本

echo "=== 班级成长管家 - 更新部署 ==="

SITE_DIR="$HOME/mysite"

# 创建目录
mkdir -p "$SITE_DIR/public"

# 下载最新代码
echo "[1/4] 下载代码..."
curl -sL "https://raw.githubusercontent.com/LLLLLiang/class-growth-manager/pa-deploy/flask_app.py" -o "$SITE_DIR/flask_app.py"
curl -sL "https://raw.githubusercontent.com/LLLLLiang/class-growth-manager/pa-deploy/data.json" -o "$SITE_DIR/data.json"
curl -sL "https://raw.githubusercontent.com/LLLLLiang/class-growth-manager/pa-deploy/public/index.html" -o "$SITE_DIR/public/index.html"

# 验证文件
echo "[2/4] 验证文件..."
FILES_OK=true
for f in "$SITE_DIR/flask_app.py" "$SITE_DIR/data.json" "$SITE_DIR/public/index.html"; do
    if [ -f "$f" ] && [ -s "$f" ]; then
        SIZE=$(wc -c < "$f")
        echo "  OK: $f ($SIZE bytes)"
    else
        echo "  FAIL: $f"
        FILES_OK=false
    fi
done

if [ "$FILES_OK" = false ]; then
    echo "ERROR: Some files failed to download!"
    exit 1
fi

# 安装依赖
echo "[3/4] 安装依赖..."
if [ -d "$HOME/myenv" ]; then
    source "$HOME/myenv/bin/activate"
    pip install flask --quiet
    echo "  Dependencies installed"
else
    echo "  Creating virtualenv..."
    mkvirtualenv myenv --python=python3.13
    pip install flask --quiet
    echo "  Dependencies installed"
fi

# 验证数据
echo "[4/4] 验证数据..."
STUDENT_COUNT=$(python3 -c "import json; d=json.load(open('$SITE_DIR/data.json')); print(len(d.get('students',[])))")
RECORD_COUNT=$(python3 -c "import json; d=json.load(open('$SITE_DIR/data.json')); print(len(d.get('records',[])))")
echo "  Students: $STUDENT_COUNT"
echo "  Records: $RECORD_COUNT"

echo ""
echo "=== 部署完成! ==="
echo "请回到 Web 配置页面点 Reload 按钮"
echo "然后访问: https://yizheng.pythonanywhere.com"
