#!/bin/bash
# 班级成长管家 - PythonAnywhere 一键部署脚本
# 在PythonAnywhere的Bash控制台里直接运行

echo "=== 班级成长管家 - PythonAnywhere 部署 ==="

# 1. 创建项目目录
echo "[1/7] 创建项目目录..."
mkdir -p ~/mysite/static

# 2. 下载Flask应用
echo "[2/7] 下载Flask应用..."
cat > ~/mysite/flask_app.py << 'FLASKAPP'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, send_from_directory
import json, os, re, time, requests
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static')

BLOB_ID = "019da57f-5bda-7827-88e3-a7a87939b113"
JSONBLOB_API = "https://jsonblob.com/api/jsonBlob"
TDOC_TOKEN = "68f6acecb5ce46bf8d22062b77a1cc78"
TDOC_API = "https://docs.qq.com/openapi/mcp"
TDOC_FILE_ID = "KZYeTgkjnrpT"
TDOC_SHEET_ID = "t00i2h"

def get_blob_data():
    try:
        resp = requests.get(f"{JSONBLOB_API}/{BLOB_ID}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {"students": [], "records": [], "categories": {}}

def save_blob_data(data):
    try:
        resp = requests.put(f"{JSONBLOB_API}/{BLOB_ID}", json=data,
                          headers={"Content-Type": "application/json"}, timeout=10)
        return resp.status_code == 200
    except:
        return False

def parse_natural_language(text):
    result = {"raw_text": text, "students": [], "behaviors": [],
              "category": "日常表现", "score": 1,
              "date": datetime.now().strftime("%Y-%m-%d"), "notes": text}
    data = get_blob_data()
    students = data.get("students", [])
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            result["students"].append(name)
    category_keywords = {
        "学习": ["作业","考试","默写","背诵","课堂","预习","复习","测验","听写"],
        "品德": ["帮助","礼貌","纪律","尊重","诚实","团结","友爱","值日"],
        "体育": ["跑步","跳绳","体育","运动","锻炼","比赛"],
        "艺术": ["画画","音乐","唱歌","舞蹈","美术","书法","表演"],
        "劳动": ["打扫","整理","值日","劳动","卫生","清洁"],
        "日常表现": ["迟到","早退","缺勤","请假","表现","注意"]
    }
    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text:
                result["category"] = cat
                break
    score_match = re.search(r'[\+\+加](\d+)|(\d+)分', text)
    if score_match:
        s = score_match.group(1) or score_match.group(2)
        result["score"] = int(s)
    elif "扣" in text or "减" in text or "-" in text:
        score_match = re.search(r'(\d+)', text)
        if score_match:
            result["score"] = -int(score_match.group(1))
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
    if date_match:
        result["date"] = date_match.group(1).replace("/", "-")
    today_patterns = ["今天","今日","刚才","刚刚"]
    yesterday_patterns = ["昨天","昨日"]
    if any(p in text for p in today_patterns):
        result["date"] = datetime.now().strftime("%Y-%m-%d")
    elif any(p in text for p in yesterday_patterns):
        result["date"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return result

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/students', methods=['GET'])
def get_students():
    return jsonify(get_blob_data())

@app.route('/api/students', methods=['POST'])
def add_student():
    data = get_blob_data()
    new_student = request.json
    if 'students' not in data:
        data['students'] = []
    data['students'].append(new_student)
    save_blob_data(data)
    return jsonify({"ok": True, "student": new_student})

@app.route('/api/records', methods=['GET'])
def get_records():
    data = get_blob_data()
    student = request.args.get('student', '')
    category = request.args.get('category', '')
    date = request.args.get('date', '')
    records = data.get('records', [])
    if student:
        records = [r for r in records if r.get('student') == student]
    if category:
        records = [r for r in records if r.get('category') == category]
    if date:
        records = [r for r in records if r.get('date') == date]
    return jsonify({"records": records})

@app.route('/api/records', methods=['POST'])
def add_record():
    data = get_blob_data()
    new_record = request.json
    new_record['id'] = str(int(time.time() * 1000))
    new_record['created_at'] = datetime.now().isoformat()
    if 'records' not in data:
        data['records'] = []
    data['records'].append(new_record)
    save_blob_data(data)
    return jsonify({"ok": True, "record": new_record})

@app.route('/api/parse', methods=['POST'])
def parse_input():
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "请输入内容"}), 400
    parsed = parse_natural_language(text)
    data = get_blob_data()
    if 'records' not in data:
        data['records'] = []
    created_records = []
    for student in parsed['students']:
        record = {'id': str(int(time.time() * 1000)) + str(hash(student))[-4:],
                  'student': student, 'behavior': parsed['raw_text'],
                  'category': parsed['category'], 'score': parsed['score'],
                  'date': parsed['date'], 'notes': parsed['notes'],
                  'created_at': datetime.now().isoformat()}
        data['records'].append(record)
        created_records.append(record)
    if created_records:
        save_blob_data(data)
    return jsonify({"ok": True, "parsed": parsed, "created_records": created_records})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    data = get_blob_data()
    records = data.get('records', [])
    students = data.get('students', [])
    student_stats = {}
    for s in students:
        name = s.get('name', '')
        student_records = [r for r in records if r.get('student') == name]
        total_score = sum(r.get('score', 0) for r in student_records)
        student_stats[name] = {'total_score': total_score, 'record_count': len(student_records), 'records': student_records[-5:]}
    category_stats = {}
    for r in records:
        cat = r.get('category', '未分类')
        if cat not in category_stats:
            category_stats[cat] = {'count': 0, 'total_score': 0}
        category_stats[cat]['count'] += 1
        category_stats[cat]['total_score'] += r.get('score', 0)
    return jsonify({"student_stats": student_stats, "category_stats": category_stats, "total_records": len(records), "total_students": len(students)})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    app.run()
FLASKAPP

# 3. 下载前端页面
echo "[3/7] 下载前端页面..."
# 从GitHub raw下载（API域名可以访问）
curl -sL "https://raw.githubusercontent.com/LLLLLiang/class-growth-manager/main/public/index.html" -o ~/mysite/static/index.html
if [ $? -ne 0 ] || [ ! -s ~/mysite/static/index.html ]; then
    echo "  GitHub下载失败，尝试从jsonblob下载..."
    # 备用方案：从我们的Vercel站点下载
    curl -sL "https://vercel-deploy-neon-seven-72.vercel.app" -o ~/mysite/static/index.html 2>/dev/null
fi
echo "  index.html: $(wc -c < ~/mysite/static/index.html) bytes"

# 4. 安装Python依赖
echo "[4/7] 安装Python依赖..."
pip install --user flask requests 2>&1 | tail -3

# 5. 创建WSGI配置
echo "[5/7] 创建WSGI配置..."
cat > ~/mysite/wsgi.py << 'WSGI'
import sys
import os

project_home = '/home/yizheng/mysite'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from flask_app import app as application
WSGI

# 6. 创建虚拟环境（如果不存在）
echo "[6/7] 设置虚拟环境..."
if [ ! -d ~/myenv ]; then
    python3 -m venv ~/myenv
    source ~/myenv/bin/activate
    pip install flask requests
    deactivate
fi

echo "[7/7] 部署完成!"
echo ""
echo "========================================="
echo "接下来请在PythonAnywhere网页上操作："
echo "1. 打开 https://www.pythonanywhere.com/webapps/"
echo "2. 点 'Add a new web app'"
echo "3. 确认域名 yizheng.pythonanywhere.com"
echo "4. 选 'Manual configuration'（手动配置）"
echo "5. 选 Python 3.10"
echo "6. 在Web页面里设置："
echo "   - Source code: /home/yizheng/mysite"
echo "   - Working directory: /home/yizheng/mysite"  
echo "   - WSGI file: /home/yizheng/mysite/wsgi.py"
echo "   - Virtualenv: /home/yizheng/myenv"
echo "7. 点 Reload 重载"
echo "========================================="
echo ""
echo "完成后访问: https://yizheng.pythonanywhere.com"
