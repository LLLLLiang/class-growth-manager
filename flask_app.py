#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
班级成长管家 - PythonAnywhere部署版
数据存储在本地JSON文件，不依赖外部API
"""
from flask import Flask, request, jsonify, send_from_directory
import json
import os
import re
import time
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='public')

# ===== 配置 =====
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
TDOC_TOKEN = "68f6acecb5ce46bf8d22062b77a1cc78"
TDOC_API = "https://docs.qq.com/openapi/mcp"
TDOC_FILE_ID = "KZYeTgkjnrpT"
TDOC_SHEET_ID = "t00i2h"

def get_data():
    """从本地JSON文件读取数据"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"students": [], "records": [], "categories": {}}

def save_data(data):
    """保存数据到本地JSON文件"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_natural_language(text):
    """解析自然语言输入，提取学生、行为、类别等信息"""
    result = {
        "raw_text": text,
        "students": [],
        "behaviors": [],
        "category": "日常表现",
        "score": 1,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "notes": text
    }
    
    data = get_data()
    students = data.get("students", [])
    
    # 匹配学生名字
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            result["students"].append(name)
    
    # 匹配类别关键词
    category_keywords = {
        "学习": ["作业", "考试", "默写", "背诵", "课堂", "预习", "复习", "测验", "听写"],
        "品德": ["帮助", "礼貌", "纪律", "尊重", "诚实", "团结", "友爱", "值日"],
        "体育": ["跑步", "跳绳", "体育", "运动", "锻炼", "比赛"],
        "艺术": ["画画", "音乐", "唱歌", "舞蹈", "美术", "书法", "表演"],
        "劳动": ["打扫", "整理", "值日", "劳动", "卫生", "清洁"],
        "日常表现": ["迟到", "早退", "缺勤", "请假", "表现", "注意"]
    }
    
    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw in text:
                result["category"] = cat
                break
    
    # 匹配分数
    score_match = re.search(r'[\+\+加](\d+)|(\d+)分', text)
    if score_match:
        s = score_match.group(1) or score_match.group(2)
        result["score"] = int(s)
    elif "扣" in text or "减" in text or "-" in text:
        score_match = re.search(r'(\d+)', text)
        if score_match:
            result["score"] = -int(score_match.group(1))
    
    # 匹配日期
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
    if date_match:
        result["date"] = date_match.group(1).replace("/", "-")
    
    today_patterns = ["今天", "今日", "刚才", "刚刚"]
    yesterday_patterns = ["昨天", "昨日"]
    if any(p in text for p in today_patterns):
        result["date"] = datetime.now().strftime("%Y-%m-%d")
    elif any(p in text for p in yesterday_patterns):
        result["date"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    return result

# ===== 路由 =====

@app.route('/')
def index():
    """返回前端页面"""
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    """返回静态文件"""
    return send_from_directory('public', path)

@app.route('/api/students', methods=['GET'])
def get_students():
    """获取学生列表"""
    data = get_data()
    return jsonify(data)

@app.route('/api/students', methods=['POST'])
def add_student():
    """添加学生"""
    data = get_data()
    new_student = request.json
    if 'students' not in data:
        data['students'] = []
    data['students'].append(new_student)
    save_data(data)
    return jsonify({"ok": True, "student": new_student})

@app.route('/api/records', methods=['GET'])
def get_records():
    """获取记录"""
    data = get_data()
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
    """添加记录"""
    data = get_data()
    new_record = request.json
    new_record['id'] = str(int(time.time() * 1000))
    new_record['created_at'] = datetime.now().isoformat()
    if 'records' not in data:
        data['records'] = []
    data['records'].append(new_record)
    save_data(data)
    return jsonify({"ok": True, "record": new_record})

@app.route('/api/parse', methods=['POST'])
def parse_input():
    """解析自然语言输入"""
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "请输入内容"}), 400
    
    parsed = parse_natural_language(text)
    
    # 自动添加记录
    data = get_data()
    if 'records' not in data:
        data['records'] = []
    
    created_records = []
    for student in parsed['students']:
        record = {
            'id': str(int(time.time() * 1000)) + str(hash(student))[-4:],
            'student': student,
            'behavior': parsed['raw_text'],
            'category': parsed['category'],
            'score': parsed['score'],
            'date': parsed['date'],
            'notes': parsed['notes'],
            'created_at': datetime.now().isoformat()
        }
        data['records'].append(record)
        created_records.append(record)
    
    if created_records:
        save_data(data)
    
    return jsonify({
        "ok": True,
        "parsed": parsed,
        "created_records": created_records
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据"""
    data = get_data()
    records = data.get('records', [])
    students = data.get('students', [])
    
    # 按学生统计
    student_stats = {}
    for s in students:
        name = s.get('name', '')
        student_records = [r for r in records if r.get('student') == name]
        total_score = sum(r.get('score', 0) for r in student_records)
        student_stats[name] = {
            'total_score': total_score,
            'record_count': len(student_records),
            'records': student_records[-5:]
        }
    
    # 按类别统计
    category_stats = {}
    for r in records:
        cat = r.get('category', '未分类')
        if cat not in category_stats:
            category_stats[cat] = {'count': 0, 'total_score': 0}
        category_stats[cat]['count'] += 1
        category_stats[cat]['total_score'] += r.get('score', 0)
    
    return jsonify({
        "student_stats": student_stats,
        "category_stats": category_stats,
        "total_records": len(records),
        "total_students": len(students)
    })

@app.route('/api/sync_tdoc', methods=['POST'])
def sync_to_tencent_doc():
    """同步数据到腾讯文档"""
    # PythonAnywhere免费版可能无法访问腾讯文档API
    # 返回提示信息
    return jsonify({"ok": False, "error": "PythonAnywhere免费版无法访问腾讯文档API，如需同步请在本地服务器操作"})

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    data = get_data()
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "students_count": len(data.get('students', [])),
        "records_count": len(data.get('records', []))
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
