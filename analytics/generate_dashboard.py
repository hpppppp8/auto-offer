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
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #1a1a2e; }}
.header {{ background: linear-gradient(135deg, #1a237e 0%, #283593 100%); color: #fff; padding: 28px 40px; }}
.header h1 {{ font-size: 28px; font-weight: 600; letter-spacing: 1px; }}
.header .sub {{ font-size: 14px; opacity: 0.75; margin-top: 6px; }}
.stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; padding: 24px 40px; margin-top: -16px; }}
.stat-card {{ background: #fff; border-radius: 12px; padding: 22px 28px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }}
.stat-card .label {{ font-size: 13px; color: #6b7280; margin-bottom: 6px; }}
.stat-card .value {{ font-size: 32px; font-weight: 700; color: #1a237e; }}
.stat-card .unit {{ font-size: 14px; color: #9ca3af; margin-left: 4px; }}
.charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 0 40px 24px; }}
.chart-card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }}
.chart-card h3 {{ font-size: 15px; font-weight: 600; color: #1f2937; margin-bottom: 12px; }}
.chart-box {{ width: 100%; height: 360px; }}
.chart-box.tall {{ height: 420px; }}
.full-row {{ grid-column: 1 / -1; }}
.footer {{ text-align: center; padding: 20px; color: #9ca3af; font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
    <h1>岗位数据分析仪表盘</h1>
    <div class="sub">基于 {data['total_jobs']} 条岗位数据 · 生成于 {data['generated_at']}</div>
</div>

<div class="stats-row">
    <div class="stat-card">
        <div class="label">总岗位数</div>
        <div class="value">{data['total_jobs']}<span class="unit">条</span></div>
    </div>
    <div class="stat-card">
        <div class="label">覆盖公司</div>
        <div class="value">{data['total_companies']}<span class="unit">家</span></div>
    </div>
    <div class="stat-card">
        <div class="label">月薪岗位均价</div>
        <div class="value">{data['avg_salary_k']}<span class="unit">K</span></div>
    </div>
    <div class="stat-card">
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
        <div class="chart-box" id="chart-scatter" style="height:420px"></div>
    </div>
</div>

<div class="footer">Auto Offer Analytics · 数据来源：BOSS直聘</div>

<script>
var salaryBins = {json.dumps(data['salary_bins'], ensure_ascii=False)};
var expDist = {json.dumps(data['exp_dist'], ensure_ascii=False)};
var eduDist = {json.dumps(data['edu_dist'], ensure_ascii=False)};
var salaryTypes = {json.dumps(data['salary_types'], ensure_ascii=False)};
var topCompanies = {json.dumps(data['top_companies'], ensure_ascii=False)};
var topWords = {json.dumps(data['top_words'], ensure_ascii=False)};
var scatterData = {json.dumps(data['scatter_data'], ensure_ascii=False)};

(function() {{
    // ── Salary histogram ──────────────────────────────────────────
    var bins = ['0-3k', '3-5k', '5-8k', '8-12k', '12-18k', '18-25k', '25k+'];
    var binValues = bins.map(function(b) {{ return salaryBins[b] || 0; }});
    echarts.init(document.getElementById('chart-salary')).setOption({{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: 40, right: 20, top: 10, bottom: 30 }},
        xAxis: {{ type: 'category', data: bins, axisLabel: {{ fontSize: 11 }} }},
        yAxis: {{ type: 'value', name: '岗位数' }},
        series: [{{ type: 'bar', data: binValues, itemStyle: {{ color: new echarts.graphic.LinearGradient(0,0,0,1,[{{offset:0,color:'#6366f1'}},{{offset:1,color:'#818cf8'}}]) }}, barWidth: '55%' }}]
    }});

    // ── Experience pie ────────────────────────────────────────────
    var expData = Object.entries(expDist).map(function(e) {{ return {{ name: e[0], value: e[1] }}; }});
    echarts.init(document.getElementById('chart-exp')).setOption({{
        tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}} ({{d}}%)' }},
        series: [{{ type: 'pie', radius: ['40%', '72%'], center: ['50%', '52%'], data: expData, label: {{ fontSize: 11, formatter: '{{b}}\\n{{d}}%' }}, emphasis: {{ label: {{ fontSize: 16, fontWeight: 'bold' }} }} }}]
    }});

    // ── Education pie ─────────────────────────────────────────────
    var eduData = Object.entries(eduDist).map(function(e) {{ return {{ name: e[0], value: e[1] }}; }});
    echarts.init(document.getElementById('chart-edu')).setOption({{
        tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}} ({{d}}%)' }},
        series: [{{ type: 'pie', radius: ['40%', '72%'], center: ['50%', '52%'], data: eduData, label: {{ fontSize: 11, formatter: '{{b}}\\n{{d}}%' }}, emphasis: {{ label: {{ fontSize: 16, fontWeight: 'bold' }} }} }}]
    }});

    // ── Salary type rose ──────────────────────────────────────────
    var typeMap = {{ '月薪': '月薪', '日薪': '日薪', '时薪': '时薪', '面议': '面议' }};
    var typeData = Object.entries(salaryTypes).map(function(e) {{ return {{ name: typeMap[e[0]] || e[0] || '其他', value: e[1] }}; }});
    echarts.init(document.getElementById('chart-type')).setOption({{
        tooltip: {{ trigger: 'item' }},
        series: [{{ type: 'pie', roseType: 'area', radius: ['30%', '75%'], center: ['50%', '52%'], data: typeData, label: {{ fontSize: 11 }} }}]
    }});

    // ── Top companies bar ─────────────────────────────────────────
    var compNames = topCompanies.map(function(c) {{ return c[0]; }}).reverse();
    var compCounts = topCompanies.map(function(c) {{ return c[1]; }}).reverse();
    echarts.init(document.getElementById('chart-company')).setOption({{
        tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
        grid: {{ left: 120, right: 30, top: 10, bottom: 20 }},
        xAxis: {{ type: 'value' }},
        yAxis: {{ type: 'category', data: compNames, axisLabel: {{ fontSize: 10, width: 100, overflow: 'truncate' }} }},
        series: [{{ type: 'bar', data: compCounts, itemStyle: {{ color: '#6366f1' }}, barWidth: '65%' }}]
    }});

    // ── Word cloud ────────────────────────────────────────────────
    var wcData = topWords.map(function(w) {{ return {{ name: w[0], value: w[1] }}; }});
    echarts.init(document.getElementById('chart-wordcloud')).setOption({{
        tooltip: {{ show: true }},
        series: [{{ type: 'wordCloud', shape: 'circle', sizeRange: [14, 50], rotationRange: [-45, 45], gridSize: 8, drawOutOfBound: false, layoutAnimation: true, textStyle: {{ fontFamily: 'PingFang SC, Microsoft YaHei, sans-serif', fontWeight: 'normal', color: function() {{ return 'hsl(' + Math.round(Math.random()*60+200) + ',60%,50%)'; }} }}, data: wcData }}]
    }});

    // ── Scatter ───────────────────────────────────────────────────
    var expCategories = [...new Set(scatterData.map(function(d) {{ return d.experience; }}))];
    var expColorMap = {{}};
    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#f97316'];
    expCategories.forEach(function(e, i) {{ expColorMap[e] = colors[i % colors.length]; }});

    var seriesByExp = {{}};
    scatterData.forEach(function(d) {{
        if (!seriesByExp[d.experience]) seriesByExp[d.experience] = [];
        seriesByExp[d.experience].push([d.experience, d.salary, d.title, d.company]);
    }});

    var scatterSeries = Object.entries(seriesByExp).map(function(e) {{
        return {{
            name: e[0],
            type: 'scatter',
            data: e[1].map(function(d) {{ return [d[0], d[1]]; }}),
            symbolSize: 8,
            itemStyle: {{ color: expColorMap[e[0]], opacity: 0.7 }},
            emphasis: {{ focus: 'series' }}
        }};
    }});

    echarts.init(document.getElementById('chart-scatter')).setOption({{
        tooltip: {{ trigger: 'item', formatter: function(p) {{ return p.seriesName + '<br/>薪资: ' + p.value[1] + 'k<br/>点击查看详情'; }} }},
        grid: {{ left: 60, right: 30, top: 30, bottom: 60 }},
        xAxis: {{ type: 'category', name: '经验要求', axisLabel: {{ rotate: 30, fontSize: 10 }} }},
        yAxis: {{ type: 'value', name: '薪资 (K/月)', min: 0 }},
        series: scatterSeries
    }});

    // Responsive resize
    window.addEventListener('resize', function() {{
        ['chart-salary','chart-exp','chart-edu','chart-type','chart-company','chart-wordcloud','chart-scatter'].forEach(function(id) {{
            var dom = document.getElementById(id);
            if (dom) {{ var inst = echarts.getInstanceByDom(dom); if (inst) inst.resize(); }}
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
