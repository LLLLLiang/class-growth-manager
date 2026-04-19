#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
班级成长管家 - PythonAnywhere部署版
完全兼容前端index.html的API接口
数据存储在本地JSON文件
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

# 四大维度
DIMENSIONS = ["学术发展", "个人成长", "社会性发展", "特色与潜能"]

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

def match_dimension(text):
    """根据文本内容匹配四大维度"""
    dim_keywords = {
        "学术发展": ["作业", "考试", "默写", "背诵", "课堂", "预习", "复习", "测验", "听写",
                     "成绩", "分数", "数学", "语文", "英语", "科学", "学习", "读书", "写作",
                     "作文", "计算", "思考", "逻辑", "知识", "研究", "实验", "观察"],
        "个人成长": ["坚持", "努力", "进步", "独立", "自律", "认真", "负责", "勇气",
                     "自信", "毅力", "成长", "改变", "态度", "勤奋", "专注", "耐心",
                     "反思", "改进", "目标", "计划", "习惯", "自理", "情绪"],
        "社会性发展": ["帮助", "合作", "团队", "分享", "友爱", "团结", "尊重", "沟通",
                     "领导", "组织", "协调", "值日", "服务", "贡献", "班级", "集体",
                     "关系", "朋友", "同学", "老师", "互动", "参与", "志愿"],
        "特色与潜能": ["特长", "才艺", "创意", "想象", "画画", "音乐", "唱歌", "舞蹈",
                     "体育", "运动", "跑步", "跳绳", "书法", "表演", "手工", "发明",
                     "兴趣", "爱好", "天赋", "潜能", "创新", "设计", "编程", "棋类"]
    }
    for dim, keywords in dim_keywords.items():
        for kw in keywords:
            if kw in text:
                return dim
    return "个人成长"  # 默认维度

def match_students(text):
    """从文本中匹配学生名字"""
    data = get_data()
    students = data.get("students", [])
    matched = []
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            matched.append(name)
    return matched

def generate_summary(text, student, dimension):
    """根据原始文本生成归纳总结"""
    # 简单的归纳逻辑：提取关键信息
    summary = text
    # 去掉学生名字后面多余的连接词
    for connector in ["今天", "今日", "刚才", "刚刚", "这学期", "本学期"]:
        if connector in summary:
            summary = summary.replace(connector, "", 1)
            break
    summary = summary.strip()
    if not summary:
        summary = text
    return summary

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
    """获取记录 - 支持前端过滤参数"""
    data = get_data()
    student = request.args.get('student', '')
    dimension = request.args.get('dimension', '')
    category = request.args.get('category', '')
    date = request.args.get('date', '')
    
    records = data.get('records', [])
    if student:
        records = [r for r in records if r.get('student') == student]
    if dimension:
        records = [r for r in records if r.get('dimension') == dimension]
    if category:
        records = [r for r in records if r.get('category') == category or r.get('dimension') == category]
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

@app.route('/api/records/batch', methods=['POST'])
def batch_records():
    """批量保存记录 - 前端确认保存和快速保存都调用这个"""
    data = get_data()
    body = request.json
    
    if 'records' in body:
        # 从预览确认保存
        records_to_save = body['records']
    elif 'text' in body:
        # 快速保存模式：直接解析并保存
        text = body['text']
        students = match_students(text)
        dimension = match_dimension(text)
        
        records_to_save = []
        if students:
            for student in students:
                summary = generate_summary(text, student, dimension)
                record = {
                    'id': str(int(time.time() * 1000)) + str(hash(student))[-4:],
                    'student': student,
                    'description': text,
                    'summary': summary,
                    'dimension': dimension,
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'created_at': datetime.now().isoformat()
                }
                records_to_save.append(record)
        else:
            # 没匹配到学生，也创建一条记录
            summary = generate_summary(text, "", dimension)
            record = {
                'id': str(int(time.time() * 1000)),
                'student': '',
                'description': text,
                'summary': summary,
                'dimension': dimension,
                'date': datetime.now().strftime("%Y-%m-%d"),
                'created_at': datetime.now().isoformat()
            }
            records_to_save.append(record)
    else:
        return jsonify({"success": False, "error": "参数错误"}), 400
    
    if 'records' not in data:
        data['records'] = []
    data['records'].extend(records_to_save)
    save_data(data)
    
    count = len(records_to_save)
    return jsonify({
        "success": True,
        "message": f"已保存 {count} 条记录",
        "count": count
    })

@app.route('/api/records/<record_id>', methods=['PUT'])
def update_record(record_id):
    """编辑记录"""
    data = get_data()
    records = data.get('records', [])
    
    for i, r in enumerate(records):
        if str(r.get('id')) == str(record_id):
            body = request.json
            if 'summary' in body:
                records[i]['summary'] = body['summary']
            if 'description' in body:
                records[i]['description'] = body['description']
            if 'dimension' in body:
                records[i]['dimension'] = body['dimension']
            records[i]['updated_at'] = datetime.now().isoformat()
            save_data(data)
            return jsonify({"success": True, "record": records[i]})
    
    return jsonify({"success": False, "error": "记录不存在"}), 404

@app.route('/api/records/<record_id>', methods=['DELETE'])
def delete_record(record_id):
    """删除记录"""
    data = get_data()
    records = data.get('records', [])
    
    new_records = [r for r in records if str(r.get('id')) != str(record_id)]
    if len(new_records) < len(records):
        data['records'] = new_records
        save_data(data)
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "记录不存在"}), 404

@app.route('/api/parse', methods=['POST'])
def parse_input():
    """解析自然语言输入 - 前端智能解析按钮调用"""
    text = request.json.get('text', '')
    if not text:
        return jsonify({"error": "请输入内容"}), 400
    
    students = match_students(text)
    dimension = match_dimension(text)
    
    # 匹配日期
    date = datetime.now().strftime("%Y-%m-%d")
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
    if date_match:
        date = date_match.group(1).replace("/", "-")
    
    today_patterns = ["今天", "今日", "刚才", "刚刚"]
    yesterday_patterns = ["昨天", "昨日"]
    if any(p in text for p in today_patterns):
        date = datetime.now().strftime("%Y-%m-%d")
    elif any(p in text for p in yesterday_patterns):
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 生成解析后的记录列表（前端期望的格式）
    records = []
    if students:
        for student in students:
            summary = generate_summary(text, student, dimension)
            record = {
                'id': str(int(time.time() * 1000)) + str(hash(student))[-4:],
                'student': student,
                'description': text,
                'summary': summary,
                'dimension': dimension,
                'date': date,
                'created_at': datetime.now().isoformat()
            }
            records.append(record)
    else:
        # 没匹配到学生，仍然返回解析结果
        summary = generate_summary(text, "", dimension)
        record = {
            'id': str(int(time.time() * 1000)),
            'student': '',
            'description': text,
            'summary': summary,
            'dimension': dimension,
            'date': date,
            'created_at': datetime.now().isoformat()
        }
        records.append(record)
    
    return jsonify({
        "records": records,
        "message": f"解析完成：识别到 {len(students)} 位学生，归类为「{dimension}」"
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据 - 兼容前端dashboard"""
    data = get_data()
    records = data.get('records', [])
    students = data.get('students', [])
    
    # 按维度统计
    by_dimension = {}
    for dim in DIMENSIONS:
        by_dimension[dim] = 0
    for r in records:
        dim = r.get('dimension', '个人成长')
        if dim in by_dimension:
            by_dimension[dim] += 1
        else:
            by_dimension[dim] = 1
    
    # 有记录的学生数
    students_with_records = set(r.get('student', '') for r in records if r.get('student'))
    students_covered = len(students_with_records)
    
    # 最近5条记录
    recent_5 = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)[:5]
    
    return jsonify({
        "total_records": len(records),
        "total_students": len(students),
        "students_covered": students_covered,
        "by_dimension": by_dimension,
        "recent_5": recent_5
    })

@app.route('/api/report', methods=['GET'])
def get_report():
    """生成学生成长报告"""
    student_name = request.args.get('student', '')
    if not student_name:
        return jsonify({"error": "请指定学生"}), 400
    
    data = get_data()
    records = data.get('records', [])
    student_records = [r for r in records if r.get('student') == student_name]
    
    if not student_records:
        return jsonify({"error": f"暂无 {student_name} 的记录"})
    
    # 按维度分组
    dimensions = {}
    for dim in DIMENSIONS:
        dim_records = [r for r in student_records if r.get('dimension') == dim]
        dimensions[dim] = {
            "count": len(dim_records),
            "records": dim_records
        }
    
    # 生成综合评价
    dim_counts = {dim: dimensions[dim]["count"] for dim in DIMENSIONS}
    strongest = max(dim_counts, key=dim_counts.get)
    
    summary = f"{student_name}同学共有{len(student_records)}条成长记录。"
    if dim_counts[strongest] > 0:
        summary += f"在「{strongest}」方面表现突出（{dim_counts[strongest]}条记录）。"
    weak_dims = [d for d in DIMENSIONS if dim_counts[d] == 0]
    if weak_dims:
        summary += f"在「{'、'.join(weak_dims)}」方面暂无记录，建议关注。"
    
    return jsonify({
        "report": {
            "student": student_name,
            "total": len(student_records),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dimensions": dimensions,
            "summary": summary
        }
    })

@app.route('/api/query', methods=['POST'])
def smart_query():
    """智能查询"""
    text = request.json.get('text', '')
    if not text:
        return jsonify({"type": "error", "message": "请输入查询内容"})
    
    data = get_data()
    records = data.get('records', [])
    students = data.get('students', [])
    
    # 匹配学生名字
    matched_students = []
    for s in students:
        name = s.get("name", "")
        if name and name in text:
            matched_students.append(name)
    
    if matched_students:
        student_name = matched_students[0]
        student_records = [r for r in records if r.get('student') == student_name]
        
        if not student_records:
            return jsonify({
                "type": "no_data",
                "student": student_name
            })
        
        # 生成报告
        dimensions = {}
        for dim in DIMENSIONS:
            dim_records = [r for r in student_records if r.get('dimension') == dim]
            dimensions[dim] = {
                "count": len(dim_records),
                "records": dim_records
            }
        
        dim_counts = {dim: dimensions[dim]["count"] for dim in DIMENSIONS}
        strongest = max(dim_counts, key=dim_counts.get)
        summary = f"{student_name}同学共有{len(student_records)}条成长记录。"
        if dim_counts[strongest] > 0:
            summary += f"在「{strongest}」方面表现突出（{dim_counts[strongest]}条记录）。"
        weak_dims = [d for d in DIMENSIONS if dim_counts[d] == 0]
        if weak_dims:
            summary += f"在「{'、'.join(weak_dims)}」方面暂无记录，建议关注。"
        
        return jsonify({
            "type": "report",
            "report": {
                "student": student_name,
                "total": len(student_records),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "dimensions": dimensions,
                "summary": summary
            }
        })
    
    # 没匹配到学生，返回统计概览
    students_with_records = list(set(r.get('student', '') for r in records if r.get('student')))
    return jsonify({
        "type": "overview",
        "message": f"目前共有 {len(records)} 条记录，{len(students_with_records)} 位学生有记录。",
        "students_with_records": students_with_records
    })

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

# 以下API在PythonAnywhere免费版无法使用，返回提示
@app.route('/api/tdoc/sync', methods=['POST'])
def tdoc_sync():
    return jsonify({"success": False, "error": "PythonAnywhere免费版暂不支持腾讯文档同步"})

@app.route('/api/tdoc/load', methods=['POST'])
def tdoc_load():
    return jsonify({"success": False, "error": "PythonAnywhere免费版暂不支持腾讯文档加载"})

@app.route('/api/cloud/save', methods=['POST'])
def cloud_save():
    return jsonify({"success": False, "error": "PythonAnywhere免费版暂不支持云端保存"})

@app.route('/api/cloud/load', methods=['POST'])
def cloud_load():
    return jsonify({"success": False, "error": "PythonAnywhere免费版暂不支持云端加载"})

@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    """导出CSV"""
    data = get_data()
    records = data.get('records', [])
    
    csv_lines = ["学生,维度,归纳总结,原始描述,日期"]
    for r in records:
        student = r.get('student', '')
        dim = r.get('dimension', '')
        summary = r.get('summary', '').replace(',', '，')
        desc = r.get('description', '').replace(',', '，').replace('\n', ' ')
        date = r.get('date', '')
        csv_lines.append(f"{student},{dim},{summary},{desc},{date}")
    
    csv_content = '\n'.join(csv_lines)
    from flask import Response
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=class_records.csv'}
    )

@app.route('/api/export/json', methods=['GET'])
def export_json():
    """导出JSON"""
    data = get_data()
    from flask import Response
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=class_records.json'}
    )

@app.route('/api/import', methods=['POST'])
def import_json():
    """导入JSON数据"""
    body = request.json
    import_data = body.get('data', {})
    
    if not import_data:
        return jsonify({"success": False, "error": "数据为空"})
    
    # 合并数据
    current = get_data()
    
    if 'students' in import_data and import_data['students']:
        existing_names = {s.get('name') for s in current.get('students', [])}
        for s in import_data['students']:
            if s.get('name') not in existing_names:
                current.setdefault('students', []).append(s)
    
    if 'records' in import_data and import_data['records']:
        current.setdefault('records', []).extend(import_data['records'])
    
    save_data(current)
    return jsonify({"success": True, "message": f"导入成功：{len(import_data.get('students', []))}名学生，{len(import_data.get('records', []))}条记录"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
