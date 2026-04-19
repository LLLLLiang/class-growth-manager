#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
班级成长管家 - Vercel Serverless API
所有API端点统一入口，数据存储在jsonblob.com + 腾讯文档
"""
from flask import Flask, request, jsonify, send_from_directory
import json
import os
import re
import time
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# ===== 配置 =====
TDOC_TOKEN = os.environ.get("TDOC_TOKEN", "68f6acecb5ce46bf8d22062b77a1cc78")
TDOC_API = "https://docs.qq.com/openapi/mcp"
TDOC_FILE_ID = os.environ.get("TDOC_FILE_ID", "KZYeTgkjnrpT")
TDOC_SHEET_ID = os.environ.get("TDOC_SHEET_ID", "t00i2h")
TDOC_URL = "https://docs.qq.com/smartsheet/DS1pZZVRna2pucnBU"
BLOB_ID = os.environ.get("BLOB_ID", "019da57f-5bda-7827-88e3-a7a87939b113")
JSONBLOB_API = "https://jsonblob.com/api/jsonBlob"

# ===== 数据存储 =====
def cloud_load_data():
    """从jsonblob加载全量数据"""
    if not BLOB_ID:
        return None
    try:
        resp = requests.get(f"{JSONBLOB_API}/{BLOB_ID}", headers={"Accept": "application/json"}, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def cloud_save_data(data):
    """保存数据到jsonblob"""
    if not BLOB_ID:
        return False
    try:
        resp = requests.put(
            f"{JSONBLOB_API}/{BLOB_ID}",
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        return resp.status_code in (200, 201)
    except:
        return False

def load_data():
    """从云端加载数据"""
    data = cloud_load_data()
    if data:
        return data
    # 兜底：返回空数据（首次部署需初始化）
    return {"students": [], "records": []}

def save_data(data):
    """保存数据到云端"""
    return cloud_save_data(data)

# ===== 腾讯文档API =====
def tdoc_call(tool_name, args_dict):
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args_dict},
        "id": 1
    }
    try:
        resp = requests.post(TDOC_API, json=payload,
                           headers={"Authorization": TDOC_TOKEN, "Content-Type": "application/json"},
                           timeout=30)
        result = resp.json()
        if "result" in result:
            content = result["result"].get("content", [])
            for c in content:
                if c.get("type") == "text":
                    try:
                        return json.loads(c["text"])
                    except:
                        return {"text": c["text"]}
        if "error" in result:
            return result
        return result
    except Exception as e:
        return {"error": str(e)}

def _text_val(s):
    return [{"text": str(s), "type": "text"}]

def _option_val(s):
    return [{"text": str(s)}]

def _date_val(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return str(int(dt.timestamp() * 1000))
    except:
        return ""

def tdoc_add_records(records):
    formatted = []
    for r in records:
        formatted.append({
            "field_values": {
                "学生姓名": _text_val(r["student"]),
                "date": _date_val(r["date"]),
                "记录维度": _option_val(r["dimension"]),
                "归纳描述": _text_val(r.get("summary", "")),
                "原始描述": _text_val(r.get("description", "")),
                "记录人": _text_val(r.get("recorder", "梁老师"))
            }
        })
    results = []
    for record in formatted:
        r = tdoc_call("smartsheet.add_records", {
            "file_id": TDOC_FILE_ID,
            "sheet_id": TDOC_SHEET_ID,
            "records": [record]
        })
        results.append(r)
    return results

def tdoc_list_records():
    return tdoc_call("smartsheet.list_records", {
        "file_id": TDOC_FILE_ID,
        "sheet_id": TDOC_SHEET_ID,
        "offset": 0,
        "limit": 1000
    })

# ===== 语义解析引擎 =====
DIMENSION_RULES = {
    "学术发展": {
        "primary": ["课堂", "作业", "成绩", "考试", "测验", "数学", "英语", "语文", "科学",
                    "阅读", "写作", "背诵", "预习", "复习", "笔记", "提问", "回答", "发言",
                    "项目", "思维", "学习", "知识", "题", "实验", "分析", "解题", "研究",
                    "探究", "方案", "展示", "思路", "逻辑", "理解", "掌握"],
        "secondary": ["态度端正", "勤能补拙", "认真", "努力学"],
        "negative": []
    },
    "个人成长": {
        "primary": ["习惯", "品格", "品质", "心态", "态度", "情绪", "自律", "坚持", "诚实",
                    "守时", "准时", "细心", "耐心", "勇气", "勤奋", "自信", "反思", "改正",
                    "成长", "进步", "改变", "坚强", "乐观", "积极", "自我管理", "规划",
                    "计划", "目标", "紧张", "焦虑", "心态不好", "容易紧张", "笑嘻嘻",
                    "可爱", "正气", "一身正气", "勤能补拙", "胖乎乎"],
        "secondary": [],
        "negative": ["班长", "为班级", "做事最多", "志愿者"]
    },
    "社会性发展": {
        "primary": ["合作", "协作", "团队", "小组", "沟通", "交流", "帮助", "责任", "班级",
                    "值日", "扫地", "擦", "劳动", "班长", "班委", "干部", "服务",
                    "规则", "纪律", "秩序", "礼貌", "尊重", "友善", "关心", "同学",
                    "朋友", "集体", "组织", "协调", "解决冲突", "义务", "负责",
                    "为班级", "为年级", "做事", "付出", "志愿者", "家访", "哭"],
        "secondary": [],
        "negative": ["最喜欢", "一身正气", "可爱"]
    },
    "特色与潜能": {
        "primary": ["特长", "创意", "创新", "领导", "领导力", "才艺", "绘画", "音乐", "体育",
                    "运动", "竞赛", "比赛", "获奖", "奖项", "编程", "设计", "发明",
                    "游戏", "表演", "主持", "策划", "独特", "擅长", "兴趣", "爱好",
                    "潜力", "突出", "优秀", "贡献", "亮点", "最喜欢", "做事最多",
                    "一身正气", "默默付出", "不可替代"],
        "secondary": [],
        "negative": []
    }
}

def score_text_for_dimension(text, dim_name):
    rules = DIMENSION_RULES.get(dim_name, {})
    score = 0
    for kw in rules.get("primary", []):
        count = text.count(kw)
        if count > 0:
            score += 2 * count
    for kw in rules.get("secondary", []):
        if kw in text:
            score += 1
    for kw in rules.get("negative", []):
        if kw in text:
            score -= 3
    return score

def classify_dimension(text):
    scores = {}
    for dim in DIMENSION_RULES:
        scores[dim] = score_text_for_dimension(text, dim)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "个人成长"
    return best

def split_into_segments(text):
    sentences = re.split(r'[。！？；\n]', text)
    segments = []
    current = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        test_text = current + s if current else s
        if current:
            current_dim = classify_dimension(current)
            new_dim = classify_dimension(s)
            if current_dim != new_dim and len(current) > 6:
                segments.append(current.strip())
                current = s
            else:
                current = test_text
        else:
            current = s
    if current.strip():
        segments.append(current.strip())
    return segments if segments else [text]

def extract_date_from_text(text):
    today = datetime.now().strftime("%Y-%m-%d")
    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', text)
    if date_match:
        return f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    month_match = re.search(r'(\d{1,2})月(\d{1,2})日?', text)
    if month_match:
        year = datetime.now().year
        return f"{year}-{int(month_match.group(1)):02d}-{int(month_match.group(2)):02d}"
    if "今天" in text or "今日" in text:
        return today
    elif "昨天" in text or "昨日" in text:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "前天" in text:
        return (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    return today

def clean_oral_text(text):
    result = text
    filler_words = ["其实", "就是说", "然后", "那个", "就是", "反正", "怎么说呢",
                   "你知道吗", "对吧", "嘛", "吧", "啊", "呢", "哎", "哎呦", "嗯"]
    for fw in filler_words:
        result = result.replace(fw, "")
    result = re.sub(r"比如说\s*", "", result)
    result = re.sub(r"真的很(.{1,2})很\1", r"真的很\1", result)
    result = re.sub(r'\s+', '', result)
    return result.strip()

def summarize_text_rules(text, dimension):
    cleaned = clean_oral_text(text)
    dim_understanding = {
        "学术发展": {
            "analyzers": [
                (r"成绩.{0,5}(不好|一般|差|不行)", lambda m: "学业基础尚待夯实"),
                (r"成绩(最好|第一|拔尖|顶尖)", lambda m: "学业成绩在班级拔尖"),
                (r"成绩.{0,5}(好|不错|优秀|突出)", lambda m: "学业表现良好"),
                (r"勤能补拙", lambda m: "勤奋踏实，以坚持弥补不足"),
                (r"态度.{0,4}(端正|认真|好)", lambda m: "学习态度端正自觉"),
                (r"态度.{0,4}(不好|差|敷衍)", lambda m: "学习态度有待端正"),
                (r"(数学|英语|语文|科学).{0,8}(好|优秀|突出|进步)", lambda m: f"{m.group(1)}学科优势明显"),
                (r"(语文|数学|英语|科学).{0,10}全面发展", lambda m: "各学科全面发展"),
                (r"课堂.{0,6}(积极|发言|提问|参与)", lambda m: "课堂参与积极主动"),
                (r"作业.{0,6}(全对|认真|完成|不交|拖拉)", lambda m: "作业习惯需关注"),
                (r"(努力|认真).{0,4}(学习|学|钻研)", lambda m: "学习投入度高"),
                (r"(分心|走神|开小差|不专注)", lambda m: "注意力容易分散"),
                (r"班级.{0,6}(第二|第三|前[二三]|前三)", lambda m: "学业成绩稳居班级前列"),
                (r"永远.{0,4}(第二|第三|前[二三])", lambda m: "学业成绩稳定在班级前列"),
                (r"成绩.{0,5}(稳定|没有波动)", lambda m: "学业成绩稳定"),
                (r"非常非常.{0,3}(好|优秀)", lambda m: "学业表现优异"),
                (r"十佳|最高规格", lambda m: "获得过校级重要荣誉"),
                (r"乐器|打鼓|才艺", lambda m: "具有才艺特长"),
            ],
        },
        "个人成长": {
            "analyzers": [
                (r"紧张", lambda m: "在压力情境下容易紧张"),
                (r"心态.{0,4}(不好|差|不稳|容易崩)", lambda m: "情绪调节能力尚在发展中"),
                (r"笑嘻嘻|整天笑|开朗|乐观", lambda m: "性格开朗乐观"),
                (r"正气|一身正气|正直", lambda m: "品性正直端正"),
                (r"可爱|讨人喜欢", lambda m: "性格温和讨喜"),
                (r"容易紧张|说不利索|人多.{0,4}紧张", lambda m: "社交场合容易紧张"),
                (r"心态好|抗压|坚强", lambda m: "心理韧性较好"),
                (r"(胖乎乎|胖胖|壮壮)", lambda m: "外形憨厚亲和"),
                (r"独立|自理", lambda m: "生活自理能力较强"),
                (r"敏感|细腻|心思重", lambda m: "内心细腻敏感"),
                (r"瘦瘦|瘦|黑|黑黑的", lambda m: "外表清瘦"),
                (r"戴.{0,3}眼镜", lambda m: "戴眼镜"),
                (r"变声期|声音.{0,4}(特点|特别|独特)", lambda m: "正处于青春期发育阶段"),
                (r"(没|不).{0,5}(上瘾|沉迷|手机|游戏|网)", lambda m: "生活自律，未沉迷电子产品"),
                (r"睡.{0,4}(早|规律|好)", lambda m: "作息规律健康"),
                (r"生活.{0,4}(习惯|规律|好)", lambda m: "生活习惯良好"),
                (r"家.{0,15}(和睦|温暖|支持|氛围好|关心)", lambda m: "家庭环境温暖有支持"),
                (r"家长|父母|家里面.{0,8}(好|支持|关心|和睦)", lambda m: "家庭支持系统良好"),
                (r"很好.{0,2}很好", lambda m: "整体发展良好"),
                (r"不错.{0,2}不错|真的不错", lambda m: "各方面表现良好"),
            ],
        },
        "社会性发展": {
            "analyzers": [
                (r"班长|干部", lambda m: "承担班级管理职责"),
                (r"负责|责任心", lambda m: "责任心突出"),
                (r"为班级.{0,6}(做事|付出|做|操心)", lambda m: "主动为班级付出"),
                (r"值日|扫地|擦|劳动|打扫", lambda m: "积极参与班级劳动"),
                (r"志愿者|公益", lambda m: "热心公益志愿服务"),
                (r"哭.{0,10}(责任|班长|班级)", lambda m: "对集体有强烈的使命感"),
                (r"不善表达|说不利索|不会说", lambda m: "不善于表达自我"),
                (r"付出.{0,6}(不知道|看不到|没人知道)", lambda m: "付出常被忽视"),
                (r"帮助|帮忙|关心同学", lambda m: "乐于助人"),
                (r"家访", lambda m: "（家访了解）"),
                (r"好胜|要强|争强", lambda m: "好胜心强，对竞争结果敏感"),
                (r"赌气|不满|生气", lambda m: "遇到不公时情绪反应强烈"),
                (r"(没|不).{0,5}(选|投票|推荐)", lambda m: "对落选结果难以释怀"),
                (r"大队委员|班委|干部|代表", lambda m: "关注班级管理角色"),
                (r"争辩|反驳|顶嘴|不服", lambda m: "遇到不同意见时容易争辩"),
                (r"帮老师.{0,6}(做事|做事情|帮忙)", lambda m: "乐于帮助老师处理事务"),
                (r"活泼.{0,8}(不靠谱|不认真|不仔细|马虎)", lambda m: "性格活泼但做事不够细致"),
                (r"(不|没那么).{0,4}靠谱", lambda m: "做事不够靠谱稳重"),
                (r"很.{0,2}(活泼|开朗|积极).{0,8}(但|不过|但是|就是)", lambda m: "性格活泼但执行力有落差"),
                (r"太.{0,2}(活泼|开朗|积极)", lambda m: "性格过于活泼"),
                (r"领头|核心|骨干|主力|带头人", lambda m: "在班级中具有核心影响力"),
                (r"三个人.{0,6}(领头|核心|主力|代表)", lambda m: "是班级核心学生之一"),
                (r"为年级.{0,6}(做事|付出|做|服务)", lambda m: "积极参与年级事务"),
                (r"愿意.{0,4}(做|帮忙|做事|参与)", lambda m: "做事积极主动"),
            ],
        },
        "特色与潜能": {
            "analyzers": [
                (r"领导|带领|组织", lambda m: "具有组织领导潜质"),
                (r"最喜欢|特别欣赏|最欣赏", lambda m: "是老师特别关注的学生"),
                (r"做事最多|贡献最多", lambda m: "在集体中贡献突出"),
                (r"创新|创意|点子", lambda m: "思维活跃富有创意"),
                (r"特长|擅长|才艺", lambda m: "具有突出才艺特长"),
                (r"独特|与众不同", lambda m: "有独特的个人特质"),
                (r"潜力|天赋", lambda m: "有较大发展潜力"),
            ],
        }
    }
    rules = dim_understanding.get(dimension, {})
    analyzers = rules.get("analyzers", [])
    observations = []
    seen = set()
    for pattern, analyzer in analyzers:
        match = re.search(pattern, text)
        if match:
            obs = analyzer(match)
            if obs and obs not in seen:
                observations.append(obs)
                seen.add(obs)
    if not observations:
        return generic_summarize(text)
    return "；".join(observations)

def generic_summarize(text):
    cleaned = clean_oral_text(text)
    summary_patterns = [
        (r"成绩.{0,5}(稳定|很好|不错|优秀|厉害)", lambda m: f"学业成绩{m.group(1)}"),
        (r"成绩(最好|第一|拔尖)", lambda m: "学业成绩在班级拔尖"),
        (r"(开朗|活泼|阳光|乐观|积极)", lambda m: f"性格{m.group(1)}"),
        (r"(成熟|稳重|长大)", lambda m: "逐渐成熟稳重"),
        (r"(好胜|要强|争强|不服输)", lambda m: "好胜心强，自尊心高"),
        (r"(帮|愿意).{0,5}(老师|班级|同学).{0,5}(做事|做事情|帮忙)", lambda m: "乐于为班级和老师做事"),
        (r"(十佳|奖|荣誉|称号)", lambda m: "获得过重要荣誉"),
        (r"(乐器|打鼓|音乐|绘画|运动|体育)", lambda m: f"有{m.group(1)}等才艺特长"),
    ]
    for pattern, handler in summary_patterns:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return handler(match)
            except:
                continue
    result = re.sub(r"^(包括|而且|但是|不过|然后|同时|另外|当然了)\s*", "", cleaned)
    if len(result) > 60:
        result = result[:60]
    return result if result else text.strip()[:50]

def parse_long_text_to_records(text, student_names):
    student = find_student_in_text(text, student_names)
    if not student:
        return None, "未能识别到班级学生姓名，请确认姓名是否正确。"
    record_date = extract_date_from_text(text)
    segments = split_into_segments(text)
    records = []
    now_ms = int(datetime.now().timestamp() * 1000)
    for i, seg in enumerate(segments):
        if not seg.strip() or len(seg.strip()) < 3:
            continue
        stripped = seg.strip()
        if re.match(r'^(最后|然后|接着|接下来|还有).{0,3}(说|讲|聊聊|提).{0,3}一下.{0,5}[吧啊呢]?$', stripped):
            continue
        if len(stripped) < 8:
            continue
        dimension = classify_dimension(seg)
        summary = summarize_text_rules(seg, dimension)
        is_dup = False
        for existing in records:
            if existing["summary"] == summary:
                is_dup = True
                break
        if is_dup:
            continue
        record = {
            "id": now_ms + i,
            "student": student,
            "date": record_date,
            "dimension": dimension,
            "description": seg.strip(),
            "summary": summary,
            "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }
        records.append(record)
    if len(records) <= 1 and len(text) > 50:
        records = force_split_by_dimension(text, student, record_date, now_ms)
    return records, None

def force_split_by_dimension(text, student, date, base_id):
    dim_scores = {}
    for dim in DIMENSION_RULES:
        dim_scores[dim] = score_text_for_dimension(text, dim)
    active_dims = [(dim, score) for dim, score in dim_scores.items() if score > 0]
    active_dims.sort(key=lambda x: x[1], reverse=True)
    if not active_dims:
        return [{
            "id": base_id, "student": student, "date": date,
            "dimension": "个人成长", "description": text.strip(),
            "summary": generic_summarize(text), "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }]
    records = []
    for i, (dim, score) in enumerate(active_dims):
        relevant_sentences = []
        sentences = re.split(r'[，。！？；、\n]', text)
        for s in sentences:
            s = s.strip()
            if not s or len(s) < 3:
                continue
            if score_text_for_dimension(s, dim) > 0:
                relevant_sentences.append(s)
        if not relevant_sentences:
            continue
        relevant_text = "，".join(relevant_sentences)
        summary = summarize_text_rules(relevant_text, dim)
        record = {
            "id": base_id + i, "student": student, "date": date,
            "dimension": dim, "description": relevant_text,
            "summary": summary, "recorder": "梁老师",
            "created_at": datetime.now().isoformat()
        }
        records.append(record)
    return records if records else [{
        "id": base_id, "student": student, "date": date,
        "dimension": "个人成长", "description": text.strip(),
        "summary": generic_summarize(text), "recorder": "梁老师",
        "created_at": datetime.now().isoformat()
    }]

def find_student_in_text(text, student_names):
    found = []
    for name in student_names:
        idx = text.find(name)
        if idx >= 0:
            found.append((idx, name))
    if not found:
        return None
    found.sort(key=lambda x: x[0])
    return found[0][1]

def get_student_names(data):
    return [s["name"] for s in data.get("students", [])]

def generate_report(student_name, records):
    student_records = [r for r in records if r["student"] == student_name]
    if not student_records:
        return None
    dims = {
        "学术发展": {"emoji": "📚", "records": []},
        "个人成长": {"emoji": "🌱", "records": []},
        "社会性发展": {"emoji": "🤝", "records": []},
        "特色与潜能": {"emoji": "✨", "records": []}
    }
    for r in student_records:
        dim = r.get("dimension", "个人成长")
        summary = r.get("summary", "")
        if "过渡语" in summary or "无实质信息" in summary:
            continue
        if dim in dims:
            dims[dim]["records"].append(r)
    report = {
        "student": student_name,
        "total": len(student_records),
        "generated_at": datetime.now().strftime("%Y年%m月%d日 %H:%M"),
        "dimensions": {}
    }
    for dim_name, dim_data in dims.items():
        recs = dim_data["records"]
        report["dimensions"][dim_name] = {
            "emoji": dim_data["emoji"],
            "count": len(recs),
            "records": sorted(recs, key=lambda x: x["date"], reverse=True),
            "summaries": list(set(r.get("summary", r["description"]) for r in recs))
        }
    # 规则引擎综合观察
    report["summary"] = generate_insightful_summary(student_name, student_records, report)
    return report

def generate_insightful_summary(student_name, records, report):
    traits = {"学术发展": [], "个人成长": [], "社会性发展": [], "特色与潜能": []}
    for r in records:
        dim = r.get("dimension", "个人成长")
        summary = r.get("summary", "")
        if summary and dim in traits:
            traits[dim].append(summary)
    personality_keywords = []
    all_personal = " ".join(traits.get("个人成长", []) + traits.get("社会性发展", []))
    if "正直" in all_personal or "正气" in all_personal: personality_keywords.append("品性端正")
    if "开朗" in all_personal or "乐观" in all_personal or "活泼" in all_personal: personality_keywords.append("性格开朗")
    if "紧张" in all_personal: personality_keywords.append("容易紧张")
    if "责任" in all_personal or "付出" in all_personal or "担当" in all_personal: personality_keywords.append("有担当")
    if "不善表达" in all_personal or "表达" in all_personal: personality_keywords.append("不善表达")
    if "勤奋" in all_personal or "端正" in all_personal: personality_keywords.append("勤奋踏实")
    if "好胜" in all_personal or "争强" in all_personal: personality_keywords.append("好胜心强")
    if "争辩" in all_personal or "赌气" in all_personal: personality_keywords.append("遇事较真")
    if "自律" in all_personal or "习惯" in all_personal: personality_keywords.append("生活自律")
    if "不靠谱" in all_personal or "不够细致" in all_personal: personality_keywords.append("做事不够细致")
    if "核心" in all_personal or "领头" in all_personal: personality_keywords.append("班级核心")
    tensions = []
    if "有担当" in personality_keywords and "不善表达" in personality_keywords:
        tensions.append("责任心强却不善于展示自我，付出容易被忽视")
    if "性格开朗" in personality_keywords and "容易紧张" in personality_keywords:
        tensions.append("日常开朗但在高压场合容易紧张退缩")
    if "好胜心强" in personality_keywords:
        tensions.append("好胜心强，在竞争受挫时容易产生情绪波动")
    if "勤奋踏实" in personality_keywords:
        academic_text = " ".join(traits.get("学术发展", []))
        if "待夯实" in academic_text or "不足" in academic_text:
            tensions.append("勤奋但学业基础尚在提升中，需要学习方法上的引导")
    if "性格开朗" in personality_keywords and "做事不够细致" in personality_keywords:
        tensions.append("性格活泼热情，但做事不够细致靠谱——热情有余，落地不足")
    if personality_keywords:
        portrait = f"{student_name}是一个{'、'.join(personality_keywords[:3])}的孩子"
    else:
        portrait = f"{student_name}"
    result_parts = [portrait + "。"]
    if tensions:
        result_parts.append("值得注意的" + ("是" if len(tensions) == 1 else "几点是") + "：" + "；".join(tensions) + "。")
    suggestions = []
    if "不善表达" in personality_keywords:
        suggestions.append(f"可以给{student_name}创造小范围表达的机会，让ta在安全感中逐步锻炼表达能力")
    if "容易紧张" in personality_keywords:
        suggestions.append(f"在公开场合前给予提前准备和练习的时间，帮助ta建立心理安全感")
    if "好胜心强" in personality_keywords:
        suggestions.append(f"引导{student_name}理解'输赢'的意义——失败也是成长的机会")
    if "做事不够细致" in personality_keywords:
        suggestions.append(f"在肯定{student_name}热情的同时，给ta安排需要细心完成的任务")
    if suggestions:
        result_parts.append("建议：" + "；".join(suggestions[:3]) + "。")
    return "".join(result_parts)


# ===== API路由 =====

@app.route('/api/students', methods=['GET'])
def api_students():
    data = load_data()
    return jsonify({"students": data.get("students", [])})

@app.route('/api/records', methods=['GET', 'POST'])
def api_records():
    if request.method == 'GET':
        data = load_data()
        student = request.args.get("student")
        dim = request.args.get("dimension")
        records = data.get("records", [])
        if student:
            records = [r for r in records if r["student"] == student]
        if dim:
            records = [r for r in records if r["dimension"] == dim]
        records = sorted(records, key=lambda x: x.get("date", ""), reverse=True)
        return jsonify({"records": records, "total": len(records)})
    else:
        data = load_data()
        record = request.json.get("record")
        if not record:
            return jsonify({"error": "记录数据为空"}), 400
        if "id" not in record:
            record["id"] = int(datetime.now().timestamp() * 1000)
        if "created_at" not in record:
            record["created_at"] = datetime.now().isoformat()
        data["records"].append(record)
        save_data(data)
        return jsonify({"success": True, "record": record})

@app.route('/api/records/batch', methods=['POST'])
def api_records_batch():
    data = load_data()
    records = request.json.get("records", [])
    if not records:
        text = request.json.get("text", "").strip()
        if not text:
            return jsonify({"error": "请输入内容"}), 400
        student_names = get_student_names(data)
        records, err = parse_long_text_to_records(text, student_names)
        if err:
            return jsonify({"error": err}), 400
    saved = []
    for record in records:
        if "id" not in record:
            record["id"] = int(datetime.now().timestamp() * 1000) + len(saved)
        if "created_at" not in record:
            record["created_at"] = datetime.now().isoformat()
        data["records"].append(record)
        saved.append(record)
    save_data(data)
    # 同步腾讯文档
    tdoc_msg = ""
    try:
        tdoc_results = tdoc_add_records(saved)
        synced = sum(1 for r in tdoc_results if not r.get("error"))
        tdoc_msg = f"，已同步 {synced} 条到腾讯文档"
    except Exception as e:
        tdoc_msg = f"，腾讯文档同步失败"
    return jsonify({
        "success": True,
        "saved_count": len(saved),
        "records": saved,
        "message": f"✅ 已保存 {len(saved)} 条记录{tdoc_msg}"
    })

@app.route('/api/parse', methods=['POST'])
def api_parse():
    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入内容"}), 400
    data = load_data()
    student_names = get_student_names(data)
    records, err = parse_long_text_to_records(text, student_names)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"records": records, "preview": True,
                   "message": f"已从您的描述中提取出 {len(records)} 条记录，请确认后保存"})

@app.route('/api/report', methods=['GET'])
def api_report():
    student = request.args.get("student")
    if not student:
        return jsonify({"error": "请指定学生姓名"}), 400
    data = load_data()
    report = generate_report(student, data.get("records", []))
    if not report:
        return jsonify({"error": f"暂无 {student} 的成长记录"}), 404
    return jsonify({"report": report})

@app.route('/api/stats', methods=['GET'])
def api_stats():
    data = load_data()
    records = data.get("records", [])
    stats = {
        "total_records": len(records),
        "students_covered": len(set(r["student"] for r in records)),
        "total_students": len(data.get("students", [])),
        "by_dimension": {},
        "recent_5": sorted(records, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
    }
    for dim in ["学术发展", "个人成长", "社会性发展", "特色与潜能"]:
        stats["by_dimension"][dim] = len([r for r in records if r["dimension"] == dim])
    return jsonify(stats)

@app.route('/api/records/<int:record_id>', methods=['PUT', 'DELETE'])
def api_record_crud(record_id):
    data = load_data()
    if request.method == 'PUT':
        updates = request.json or {}
        for r in data["records"]:
            if r.get("id") == record_id:
                for field in ["summary", "description", "dimension", "date", "student"]:
                    if field in updates:
                        r[field] = updates[field]
                r["updated_at"] = datetime.now().isoformat()
                save_data(data)
                return jsonify({"success": True, "record": r})
        return jsonify({"error": "记录不存在"}), 404
    else:  # DELETE
        original_len = len(data["records"])
        data["records"] = [r for r in data["records"] if r.get("id") != record_id]
        if len(data["records"]) < original_len:
            save_data(data)
            return jsonify({"success": True, "message": "记录已删除"})
        return jsonify({"error": "记录不存在"}), 404

@app.route('/api/query', methods=['POST'])
def api_query():
    text = request.json.get("text", "").strip()
    if not text:
        return jsonify({"error": "请输入查询内容"}), 400
    data = load_data()
    student_names = get_student_names(data)
    student = find_student_in_text(text, student_names)
    if student:
        report = generate_report(student, data.get("records", []))
        if not report:
            return jsonify({"type": "no_data", "student": student,
                           "message": f"暂无 **{student}** 的成长记录"})
        return jsonify({"type": "report", "report": report})
    records = data.get("records", [])
    return jsonify({
        "type": "stats",
        "message": f"当前共有 {len(records)} 条成长记录，覆盖 {len(set(r['student'] for r in records))} 名同学",
        "students_with_records": list(set(r["student"] for r in records))
    })

@app.route('/api/tdoc/sync', methods=['POST'])
def api_tdoc_sync():
    data = load_data()
    if not data.get("records"):
        return jsonify({"error": "没有记录可同步"}), 400
    try:
        results = tdoc_add_records(data["records"])
        synced = sum(1 for r in results if not r.get("error"))
        return jsonify({
            "success": True, "total": len(data["records"]), "synced": synced,
            "message": f"✅ 已同步 {synced} 条记录到腾讯文档", "url": TDOC_URL
        })
    except Exception as e:
        return jsonify({"error": f"同步失败: {str(e)}"}), 500

@app.route('/api/tdoc/url', methods=['GET'])
def api_tdoc_url():
    return jsonify({"url": TDOC_URL, "file_id": TDOC_FILE_ID})

@app.route('/api/tdoc/load', methods=['POST'])
def api_tdoc_load():
    try:
        cloud_data = tdoc_list_records()
        if cloud_data.get("error"):
            return jsonify({"error": f"加载失败: {cloud_data['error']}"}), 500
        data = load_data()
        added = 0
        for cr in cloud_data.get("records", []):
            fields = cr.get("fields", {})
            local_record = {
                "id": int(datetime.now().timestamp() * 1000) + added,
                "student": fields.get("学生姓名", ""),
                "date": fields.get("date", ""),
                "dimension": fields.get("记录维度", ""),
                "summary": fields.get("归纳描述", ""),
                "description": fields.get("原始描述", ""),
                "recorder": fields.get("记录人", "梁老师"),
                "created_at": datetime.now().isoformat()
            }
            dup_key = f"{local_record['student']}_{local_record['date']}_{local_record['summary']}"
            existing_keys = set(f"{r.get('student','')}_{r.get('date','')}_{r.get('summary','')}" for r in data["records"])
            if dup_key not in existing_keys and local_record["student"]:
                data["records"].append(local_record)
                added += 1
        save_data(data)
        return jsonify({
            "success": True, "added": added, "total": len(data["records"]),
            "message": f"✅ 从腾讯文档加载 {added} 条新记录，共 {len(data['records'])} 条"
        })
    except Exception as e:
        return jsonify({"error": f"加载失败: {str(e)}"}), 500

@app.route('/api/cloud/save', methods=['POST'])
def api_cloud_save():
    data = load_data()
    ok = save_data(data)
    if ok:
        return jsonify({"success": True, "blob_id": BLOB_ID,
                       "url": f"https://jsonblob.com/api/jsonBlob/{BLOB_ID}",
                       "message": f"✅ 已同步到云端"})
    return jsonify({"error": "云同步失败"}), 500

@app.route('/api/export/excel', methods=['GET'])
def api_export_excel():
    data = load_data()
    records = data.get("records", [])
    lines = ["\ufeff学生姓名,日期,记录维度,归纳描述,原始描述,记录人"]
    for r in sorted(records, key=lambda x: (x.get("student",""), x.get("date",""))):
        summary = r.get("summary","").replace(",","，").replace("\n"," ")
        desc = r.get("description","").replace(",","，").replace("\n"," ")
        lines.append(f'{r["student"]},{r["date"]},{r["dimension"]},{summary},{desc},{r.get("recorder","")}')
    return "\n".join(lines), 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": "attachment; filename=班级成长记录.csv"
    }

@app.route('/api/export/json', methods=['GET'])
def api_export_json():
    data = load_data()
    return jsonify(data)

@app.route('/api/init', methods=['POST'])
def api_init():
    """首次部署时初始化数据"""
    init_data = request.json
    if not init_data or "students" not in init_data:
        return jsonify({"error": "数据格式错误"}), 400
    # 如果已有数据，合并
    existing = load_data()
    if not existing.get("students"):
        existing = init_data
    else:
        existing_ids = set(r.get("id") for r in existing.get("records", []))
        for record in init_data.get("records", []):
            if record.get("id") not in existing_ids:
                existing.setdefault("records", []).append(record)
                existing_ids.add(record.get("id"))
    ok = save_data(existing)
    if ok:
        return jsonify({"success": True, "message": "✅ 数据初始化成功",
                       "total_records": len(existing.get("records", [])),
                       "total_students": len(existing.get("students", []))})
    return jsonify({"error": "初始化失败"}), 500

# Vercel入口
if __name__ == '__main__':
    app.run(debug=True)
