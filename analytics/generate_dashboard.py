#!/usr/bin/env python3
"""生成自包含的岗位数据分析仪表盘 HTML 文件。"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

# Project root for storage imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import func
from storage.db import get_engine, get_session
from storage.models import Job, Company
from storage.cleaner import clean_salary

import jieba

# ── Stop words ────────────────────────────────────────────────────
STOP_WORDS = set('的了一不在人有是为以于上他之及了和与或等对将并从到使个可以自己这那什么怎么哪些因为所以但是如果虽然然而已经正在将要应该可能必须能够需要关于对于根据按照经过通过当就也都很更太最非常比较全部少数许多任何每各个某另再曾' +
    '岗位 职责 要求 任职 以上 以下 工作 相关 经验 优先 能力 具备 熟悉 负责 进行 完成 参与 公司 团队 业务 项目 提供 包括 分析 开发 管理 设计 使用 技术 产品 数据 系统 平台 服务 客户 问题 内容 用户 部门 合作 沟通 协调 支持 组织 维护 制定 执行 推动 优化 提升 保证 确保 实现 处理 研究 探索 关注 了解 掌握')


def query_data():
    engine = get_engine()
    session = get_session(engine)

    jobs = session.query(Job).all()
    total_jobs = len(jobs)
    total_companies = session.query(Company).count()

    # Salary type distribution
    salary_types = dict(session.query(Job.salary_type, func.count(Job.id)).group_by(Job.salary_type).all())

    # Experience distribution
    exp_rows = session.query(Job.experience, func.count(Job.id)).group_by(Job.experience).all()
    exp_dist = {k if k else '未知': v for k, v in exp_rows}

    # Education distribution
    edu_rows = session.query(Job.education, func.count(Job.id)).group_by(Job.education).all()
    edu_dist = {k if k else '未知': v for k, v in edu_rows}

    # Top companies
    top_companies = session.query(
        Job.company_name, func.count(Job.id)
    ).filter(Job.company_name != '').group_by(Job.company_name).order_by(
        func.count(Job.id).desc()
    ).limit(15).all()

    # All job descriptions for word cloud
    descriptions = session.query(Job.description).filter(Job.description != '').all()

    # Salary & experience for scatter
    salary_exp_rows = session.query(Job.salary, Job.experience, Job.title, Job.company_name).all()

    # Location distribution
    loc_rows = session.query(Job.location, func.count(Job.id)).filter(Job.location != '').group_by(Job.location).order_by(func.count(Job.id).desc()).limit(10).all()

    session.close()

    # ── Process salary distribution ────────────────────────────────
    salary_bins = {'0-3k': 0, '3-5k': 0, '5-8k': 0, '8-12k': 0, '12-18k': 0, '18-25k': 0, '25k+': 0}
    monthly_salaries = []
    for job in jobs:
        s = clean_salary(job.salary)
        if s['type'] == '月薪' and s['min'] and s['max']:
            mid = (s['min'] + s['max']) / 2
            # Values stored as k (e.g. 15) or raw (e.g. 15000)
            if s['max'] < 500:
                mid_k = mid  # already in k
            else:
                mid_k = mid / 1000  # convert to k
            monthly_salaries.append(mid_k)
            if mid_k < 3:
                salary_bins['0-3k'] += 1
            elif mid_k < 5:
                salary_bins['3-5k'] += 1
            elif mid_k < 8:
                salary_bins['5-8k'] += 1
            elif mid_k < 12:
                salary_bins['8-12k'] += 1
            elif mid_k < 18:
                salary_bins['12-18k'] += 1
            elif mid_k < 25:
                salary_bins['18-25k'] += 1
            else:
                salary_bins['25k+'] += 1

    avg_salary_k = round(sum(monthly_salaries) / len(monthly_salaries), 1) if monthly_salaries else 0

    # ── Process word cloud ─────────────────────────────────────────
    all_text = ' '.join(d[0] for d in descriptions if d[0])
    words = jieba.cut(all_text)
    word_freq = Counter()
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w not in STOP_WORDS:
            word_freq[w] += 1
    top_words = word_freq.most_common(100)

    # ── Process scatter data ───────────────────────────────────────
    scatter_data = []
    for salary, exp, title, company in salary_exp_rows:
        s = clean_salary(salary)
        if s['type'] == '月薪' and s['min'] and s['max']:
            mid = (s['min'] + s['max']) / 2
            if s['max'] < 500:
                mid_k = mid
            else:
                mid_k = mid / 1000
            scatter_data.append({
                'salary': round(mid_k, 1),
                'experience': exp if exp else '未知',
                'title': title,
                'company': company,
            })

    return {
        'total_jobs': total_jobs,
        'total_companies': total_companies,
        'avg_salary_k': avg_salary_k,
        'monthly_job_count': len(monthly_salaries),
        'salary_bins': salary_bins,
        'salary_types': salary_types,
        'exp_dist': exp_dist,
        'edu_dist': edu_dist,
        'top_companies': [(c, n) for c, n in top_companies],
        'top_words': [(w, c) for w, c in top_words],
        'scatter_data': scatter_data,
        'loc_dist': [(l, n) for l, n in loc_rows],
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def generate_html(data):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岗位数据分析仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js"></script>
<style>
:root {{
  --bg: #f5f6fa;
  --card: #fff;
  --text: #1e293b;
  --muted: #94a3b8;
  --accent: #6366f1;
  --accent2: #8b5cf6;
  --green: #10b981;
  --amber: #f59e0b;
  --rose: #f43f5e;
  --sky: #0ea5e9;
  --radius: 16px;
  --shadow: 0 1px 3px rgba(0,0,0,.04), 0 1px 2px rgba(0,0,0,.06);
  --shadow-lg: 0 4px 24px rgba(0,0,0,.08);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

/* ── Sidebar ──────────────────────────────────────────────── */
.sidebar {{
  position: fixed; left: 0; top: 0; bottom: 0; width: 240px;
  background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
  color: #e2e8f0; padding: 32px 24px; z-index: 10;
  display: flex; flex-direction: column; gap: 8px;
}}
.sidebar .logo {{ font-size: 20px; font-weight: 700; letter-spacing: .5px; margin-bottom: 28px; }}
.sidebar .logo span {{ background: linear-gradient(135deg, #818cf8, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.sidebar .nav-item {{
  padding: 10px 14px; border-radius: 10px; font-size: 14px; cursor: pointer;
  transition: all .2s; color: #94a3b8; display: flex; align-items: center; gap: 10px;
}}
.sidebar .nav-item:hover {{ background: rgba(255,255,255,.06); color: #e2e8f0; }}
.sidebar .nav-item.active {{ background: rgba(99,102,241,.2); color: #a5b4fc; font-weight: 500; }}
.sidebar .nav-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.sidebar .nav-dot.a {{ background: var(--accent); }}
.sidebar .nav-dot.b {{ background: var(--green); }}
.sidebar .nav-dot.c {{ background: var(--amber); }}
.sidebar .nav-dot.d {{ background: var(--sky); }}
.sidebar .nav-dot.e {{ background: var(--accent2); }}
.sidebar .nav-dot.f {{ background: var(--rose); }}
.sidebar .nav-dot.g {{ background: #ec4899; }}

/* ── Main content ─────────────────────────────────────────── */
.main {{ margin-left: 240px; padding: 32px 36px 24px; }}

/* ── Top bar ──────────────────────────────────────────────── */
.topbar {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }}
.topbar h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -.3px; }}
.topbar .breadcrumb {{ font-size: 13px; color: var(--muted); margin-top: 2px; }}
.topbar .refresh {{ font-size: 12px; color: var(--muted); background: var(--card); border: 1px solid #e2e8f0; padding: 6px 16px; border-radius: 20px; }}

/* ── Stats row ────────────────────────────────────────────── */
.stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; margin-bottom: 28px; }}
.stat-card {{
  background: var(--card); border-radius: var(--radius); padding: 20px 24px;
  box-shadow: var(--shadow); position: relative; overflow: hidden;
  transition: transform .15s, box-shadow .15s; cursor: default;
}}
.stat-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-lg); }}
.stat-card .icon {{ width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 14px; }}
.stat-card .icon.blue {{ background: #eef2ff; }}
.stat-card .icon.green {{ background: #ecfdf5; }}
.stat-card .icon.amber {{ background: #fffbeb; }}
.stat-card .icon.purple {{ background: #f5f3ff; }}
.stat-card .label {{ font-size: 12.5px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }}
.stat-card .value {{ font-size: 30px; font-weight: 700; color: #0f172a; letter-spacing: -.5px; }}
.stat-card .unit {{ font-size: 14px; color: #94a3b8; font-weight: 400; margin-left: 3px; }}
.stat-card::after {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}}
.stat-card.c1::after {{ background: var(--accent); }}
.stat-card.c2::after {{ background: var(--green); }}
.stat-card.c3::after {{ background: var(--amber); }}
.stat-card.c4::after {{ background: var(--accent2); }}

/* ── Charts grid ──────────────────────────────────────────── */
.charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 20px; }}
.chart-card {{
  background: var(--card); border-radius: var(--radius); padding: 20px 24px;
  box-shadow: var(--shadow); transition: box-shadow .15s;
}}
.chart-card:hover {{ box-shadow: var(--shadow-lg); }}
.chart-card h3 {{ font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
.chart-card h3::before {{ content: ''; width: 4px; height: 16px; border-radius: 2px; flex-shrink: 0; }}
.chart-card:nth-child(1) h3::before {{ background: var(--accent); }}
.chart-card:nth-child(2) h3::before {{ background: var(--green); }}
.chart-card:nth-child(3) h3::before {{ background: var(--amber); }}
.chart-card:nth-child(4) h3::before {{ background: var(--sky); }}
.chart-card:nth-child(5) h3::before {{ background: var(--accent2); }}
.chart-card:nth-child(6) h3::before {{ background: var(--rose); }}
.chart-card:nth-child(7) h3::before {{ background: var(--accent); }}
.chart-box {{ width: 100%; height: 340px; }}
.chart-box.tall {{ height: 400px; }}
.full-row {{ grid-column: 1 / -1; }}

/* ── Footer ───────────────────────────────────────────────── */
.footer {{ text-align: center; padding: 16px; color: var(--muted); font-size: 12px; border-top: 1px solid #e2e8f0; margin-top: 8px; }}

/* ── Responsive ───────────────────────────────────────────── */
@media (max-width: 1200px) {{
  .sidebar {{ display: none; }}
  .main {{ margin-left: 0; }}
  .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
  .charts-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<!-- ── Sidebar ──────────────────────────────────────────────── -->
<aside class="sidebar">
  <div class="logo"><span>Auto Offer</span> 分析</div>
  <div class="nav-item active"><span class="nav-dot a"></span>总览仪表盘</div>
  <div class="nav-item"><span class="nav-dot b"></span>薪资分析</div>
  <div class="nav-item"><span class="nav-dot c"></span>经验与学历</div>
  <div class="nav-item"><span class="nav-dot d"></span>公司分布</div>
  <div class="nav-item"><span class="nav-dot e"></span>关键词洞察</div>
  <div class="nav-item"><span class="nav-dot f"></span>散点对比</div>
</aside>

<!-- ── Main ─────────────────────────────────────────────────── -->
<div class="main">

<div class="topbar">
  <div>
    <h1>岗位数据分析仪表盘</h1>
    <div class="breadcrumb">BOSS直聘 · 基于 {data['total_jobs']} 条岗位数据 · 更新于 {data['generated_at']}</div>
  </div>
</div>

<div class="stats-row">
  <div class="stat-card c1">
    <div class="icon blue">📋</div>
    <div class="label">总岗位数</div>
    <div class="value">{data['total_jobs']}<span class="unit">条</span></div>
  </div>
  <div class="stat-card c2">
    <div class="icon green">🏢</div>
    <div class="label">覆盖公司</div>
    <div class="value">{data['total_companies']}<span class="unit">家</span></div>
  </div>
  <div class="stat-card c3">
    <div class="icon amber">💰</div>
    <div class="label">月薪岗位均价</div>
    <div class="value">{data['avg_salary_k']}<span class="unit">K</span></div>
  </div>
  <div class="stat-card c4">
    <div class="icon purple">📊</div>
    <div class="label">月薪岗位数量</div>
    <div class="value">{data['monthly_job_count']}<span class="unit">条</span></div>
  </div>
</div>

<div class="charts-grid">
  <div class="chart-card">
    <h3>薪资分布</h3>
    <div class="chart-box" id="chart-salary"></div>
  </div>
  <div class="chart-card">
    <h3>经验要求</h3>
    <div class="chart-box" id="chart-exp"></div>
  </div>
  <div class="chart-card">
    <h3>学历要求</h3>
    <div class="chart-box" id="chart-edu"></div>
  </div>
  <div class="chart-card">
    <h3>薪资类型</h3>
    <div class="chart-box" id="chart-type"></div>
  </div>
  <div class="chart-card">
    <h3>热门公司 TOP15</h3>
    <div class="chart-box tall" id="chart-company"></div>
  </div>
  <div class="chart-card">
    <h3>岗位关键词</h3>
    <div class="chart-box tall" id="chart-wordcloud"></div>
  </div>
  <div class="chart-card full-row">
    <h3>薪资 vs 经验</h3>
    <div class="chart-box" id="chart-scatter" style="height:400px"></div>
  </div>
</div>

<div class="footer">Auto Offer Analytics · 数据来源：BOSS直聘 · 仅供参考</div>

</div>

<script>
// ── Chart color palette ──────────────────────────────────────
var C = ['#6366f1','#10b981','#f59e0b','#0ea5e9','#8b5cf6','#f43f5e','#ec4899','#14b8a6','#f97316','#6366f1'];
var salaryBins = {json.dumps(data['salary_bins'], ensure_ascii=False)};
var expDist = {json.dumps(data['exp_dist'], ensure_ascii=False)};
var eduDist = {json.dumps(data['edu_dist'], ensure_ascii=False)};
var salaryTypes = {json.dumps(data['salary_types'], ensure_ascii=False)};
var topCompanies = {json.dumps(data['top_companies'], ensure_ascii=False)};
var topWords = {json.dumps(data['top_words'], ensure_ascii=False)};
var scatterData = {json.dumps(data['scatter_data'], ensure_ascii=False)};

(function() {{
    // ── Salary histogram ──────────────────────────────────────
    var bins = ['0-3k','3-5k','5-8k','8-12k','12-18k','18-25k','25k+'];
    var binVals = bins.map(function(b){{return salaryBins[b]||0;}});
    var maxVal = Math.max.apply(null, binVals);
    echarts.init(document.getElementById('chart-salary')).setOption({{
        tooltip: {{ trigger:'axis', backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter: '{{b}}<br/><b>{{c}}</b> 个岗位' }},
        grid: {{ left:44, right:24, top:16, bottom:28 }},
        xAxis: {{ type:'category', data:bins, axisTick:{{show:false}}, axisLine:{{lineStyle:{{color:'#e2e8f0'}}}}, axisLabel:{{color:'#64748b',fontSize:11}} }},
        yAxis: {{ type:'value', name:'岗位数', nameTextStyle:{{color:'#94a3b8',fontSize:11}}, splitLine:{{lineStyle:{{color:'#f1f5f9'}}}}, axisLabel:{{color:'#94a3b8',fontSize:10}} }},
        series:[{{ type:'bar', data:binVals.map(function(v,i){{return{{value:v,itemStyle:{{borderRadius:[6,6,0,0],color:new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:C[i]}},{{offset:1,color:C[i]+'88'}}])}}}};}}), barWidth:'52%', emphasis:{{itemStyle:{{color:C[0]}}}} }}]
    }});

    // ── Experience donut ──────────────────────────────────────
    var expData = Object.entries(expDist).map(function(e){{return{{name:e[0],value:e[1]}};}});
    echarts.init(document.getElementById('chart-exp')).setOption({{
        color: C,
        tooltip: {{ trigger:'item', backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter:'{{b}}: <b>{{c}}</b> ({{d}}%)' }},
        series:[{{ type:'pie', radius:['48%','78%'], center:['50%','54%'], data:expData, label:{{fontSize:11,color:'#64748b',formatter:'{{b}}\\n{{d}}%'}}, emphasis:{{label:{{fontSize:15,fontWeight:'bold'}}}}, itemStyle:{{borderColor:'#fff',borderWidth:2}} }}]
    }});

    // ── Education donut ───────────────────────────────────────
    var eduData = Object.entries(eduDist).map(function(e){{return{{name:e[0],value:e[1]}};}});
    echarts.init(document.getElementById('chart-edu')).setOption({{
        color: C,
        tooltip: {{ trigger:'item', backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter:'{{b}}: <b>{{c}}</b> ({{d}}%)' }},
        series:[{{ type:'pie', radius:['48%','78%'], center:['50%','54%'], data:eduData, label:{{fontSize:11,color:'#64748b',formatter:'{{b}}\\n{{d}}%'}}, emphasis:{{label:{{fontSize:15,fontWeight:'bold'}}}}, itemStyle:{{borderColor:'#fff',borderWidth:2}} }}]
    }});

    // ── Salary type rose ──────────────────────────────────────
    var typeMap = {{'月薪':'月薪','日薪':'日薪','时薪':'时薪','面议':'面议'}};
    var typeData = Object.entries(salaryTypes).map(function(e){{return{{name:typeMap[e[0]]||e[0]||'其他',value:e[1]}};}});
    echarts.init(document.getElementById('chart-type')).setOption({{
        color: ['#6366f1','#10b981','#f59e0b','#94a3b8'],
        tooltip: {{ trigger:'item', backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}} }},
        series:[{{ type:'pie', roseType:'area', radius:['36%','78%'], center:['50%','54%'], data:typeData, label:{{fontSize:11,color:'#64748b'}}, itemStyle:{{borderColor:'#fff',borderWidth:2}} }}]
    }});

    // ── Top companies bar ─────────────────────────────────────
    var compNames = topCompanies.map(function(c){{return c[0];}}).reverse();
    var compCounts = topCompanies.map(function(c){{return c[1];}}).reverse();
    var maxComp = Math.max.apply(null, compCounts);
    echarts.init(document.getElementById('chart-company')).setOption({{
        tooltip: {{ trigger:'axis', axisPointer:{{type:'shadow'}}, backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter:'{{b}}<br/>岗位数: <b>{{c}}</b>' }},
        grid: {{ left:130, right:28, top:8, bottom:16 }},
        xAxis: {{ type:'value', splitLine:{{lineStyle:{{color:'#f1f5f9'}}}}, axisLabel:{{color:'#94a3b8',fontSize:10}} }},
        yAxis: {{ type:'category', data:compNames, axisLine:{{show:false}}, axisTick:{{show:false}}, axisLabel:{{fontSize:11,color:'#475569',width:112,overflow:'truncate'}} }},
        series:[{{ type:'bar', data:compCounts.map(function(v,i){{return{{value:v,itemStyle:{{color:new echarts.graphic.LinearGradient(0,0,1,0,[{{offset:0,color:'#8b5cf6'}},{{offset:1,color:'#a78bfa'}}]),borderRadius:[0,4,4,0]}}}};}}), barWidth:'60%' }}]
    }});

    // ── Word cloud ────────────────────────────────────────────
    var wcData = topWords.map(function(w){{return{{name:w[0],value:w[1]}};}});
    echarts.init(document.getElementById('chart-wordcloud')).setOption({{
        tooltip: {{ show:true, backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter:'{{b}}: {{c}} 次' }},
        series:[{{ type:'wordCloud', shape:'circle', sizeRange:[14,52], rotationRange:[-30,30], gridSize:6, drawOutOfBound:false, layoutAnimation:true, textStyle:{{ fontFamily:'PingFang SC, Microsoft YaHei, sans-serif', fontWeight:'normal', color:function(){{var h=Math.round(Math.random()*50+215);var s=Math.round(Math.random()*30+55);var l=Math.round(Math.random()*20+38);return'hsl('+h+','+s+'%,'+l+'%)';}} }}, data:wcData }}]
    }});

    // ── Scatter ───────────────────────────────────────────────
    var expSet = [...new Set(scatterData.map(function(d){{return d.experience;}}))];
    var expColor = {{}};
    expSet.forEach(function(e,i){{expColor[e]=C[i%C.length];}});
    var seriesByExp = {{}};
    scatterData.forEach(function(d){{
        if(!seriesByExp[d.experience]) seriesByExp[d.experience] = [];
        seriesByExp[d.experience].push({{value:[d.experience,d.salary],title:d.title,company:d.company}});
    }});
    var scatterSeries = Object.entries(seriesByExp).map(function(e){{
        return {{ name:e[0], type:'scatter', data:e[1], symbolSize:function(v){{return 6+Math.random()*5;}}, itemStyle:{{color:expColor[e[0]],opacity:.72,borderColor:'#fff',borderWidth:1}}, emphasis:{{focus:'series',scale:1.5}} }};
    }});
    echarts.init(document.getElementById('chart-scatter')).setOption({{
        tooltip: {{ trigger:'item', backgroundColor:'#fff', borderColor:'#e2e8f0', textStyle:{{color:'#334155'}}, formatter:function(p){{return'<b>'+p.data.title+'</b><br/>公司: '+p.data.company+'<br/>薪资: <b>'+p.value[1]+'k</b> · 经验: <b>'+p.seriesName+'</b>';}} }},
        grid: {{ left:60, right:30, top:20, bottom:56 }},
        xAxis: {{ type:'category', name:'经验要求', nameTextStyle:{{color:'#94a3b8',fontSize:11}}, axisLabel:{{rotate:25,fontSize:10,color:'#64748b'}}, axisTick:{{show:false}}, axisLine:{{lineStyle:{{color:'#e2e8f0'}}}} }},
        yAxis: {{ type:'value', name:'薪资 (K/月)', nameTextStyle:{{color:'#94a3b8',fontSize:11}}, splitLine:{{lineStyle:{{color:'#f1f5f9'}}}}, axisLabel:{{color:'#94a3b8',fontSize:10}}, min:0 }},
        series: scatterSeries
    }});

    // ── Sidebar nav scroll ────────────────────────────────────
    var chartIds = ['chart-salary','chart-exp','chart-edu','chart-type','chart-company','chart-wordcloud','chart-scatter'];
    var navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(function(item, i){{
        item.addEventListener('click', function(){{
            navItems.forEach(function(n){{n.classList.remove('active');}});
            item.classList.add('active');
            var target = document.getElementById(chartIds[i]);
            if(target) target.scrollIntoView({{behavior:'smooth',block:'center'}});
        }});
    }});

    // ── Responsive resize ─────────────────────────────────────
    window.addEventListener('resize', function(){{
        chartIds.forEach(function(id){{
            var dom = document.getElementById(id);
            if(dom){{var inst=echarts.getInstanceByDom(dom);if(inst)inst.resize();}}
        }});
    }});
}})();
</script>
</body>
</html>'''


def main():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, 'dashboard.html')

    print('查询数据库...')
    data = query_data()
    print(f'  岗位总数: {data["total_jobs"]}')
    print(f'  公司总数: {data["total_companies"]}')
    print(f'  月薪均价: {data["avg_salary_k"]}K')
    print(f'  高频词: {len(data["top_words"])}')

    print('生成 HTML...')
    html = generate_html(data)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'已生成: {output_path} ({len(html)} bytes)')
    print('用浏览器打开即可查看。')


if __name__ == '__main__':
    main()
