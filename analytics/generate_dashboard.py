#!/usr/bin/env python3
"""生成 Apple 风格岗位数据分析仪表盘 HTML 文件。"""

import json
import os
import sys
from collections import Counter
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import func
from storage.db import get_engine, get_session
from storage.models import Job, Company
from storage.cleaner import clean_salary

import jieba

# ── Stop words ────────────────────────────────────────────────────
_STOP_CHARS = set('的一了是在人有为以上之及和与或等对将从到使个可自己这那什么怎么哪些因为所以如果但是虽然然而已经正在将要应该可能必须能够需要关于对于根据按照经过通过当就也都很更太最非常比较全部少数许多任何每各个某另再曾')
_STOP_WORDS = set('岗位 职责 要求 任职 以上 以下 工作 相关 经验 优先 能力 具备 熟悉 负责 进行 完成 参与 公司 团队 业务 项目 提供 包括 分析 开发 管理 设计 使用 技术 产品 数据 系统 平台 服务 客户 问题 内容 用户 部门 合作 沟通 协调 支持 组织 维护 制定 执行 推动 优化 提升 保证 确保 实现 处理 研究 探索 关注 了解 掌握 标注 熟练 一定'.split())


def _compute_stats(session, keyword):
    """Compute all statistics for a given keyword (None = all)."""
    q = session.query(Job)
    if keyword:
        q = q.filter(Job.keyword == keyword)
    jobs = q.all()

    if not jobs:
        return None

    total = len(jobs)
    companies = len(set(j.company_name for j in jobs if j.company_name))

    # Salary bins for monthly jobs
    salary_bins = {'0-3k': 0, '3-5k': 0, '5-8k': 0, '8-12k': 0, '12-18k': 0, '18-25k': 0, '25k+': 0}
    monthly_mids = []
    salary_type_counts = {}
    exp_counts = {}
    edu_counts = {}
    company_counts = Counter()
    all_descs = []
    scatter_pts = []

    for j in jobs:
        s = clean_salary(j.salary)
        st = s['type'] or '未知'
        salary_type_counts[st] = salary_type_counts.get(st, 0) + 1

        exp = j.experience if j.experience else '未知'
        exp_counts[exp] = exp_counts.get(exp, 0) + 1

        edu = j.education if j.education else '未知'
        edu_counts[edu] = edu_counts.get(edu, 0) + 1

        if j.company_name:
            company_counts[j.company_name] += 1

        if j.description:
            all_descs.append(j.description)

        if s['type'] == '月薪' and s['min'] and s['max']:
            mid = (s['min'] + s['max']) / 2
            mid_k = mid if s['max'] < 500 else mid / 1000
            monthly_mids.append(mid_k)
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
            scatter_pts.append({
                'salary': round(mid_k, 1),
                'experience': exp,
                'title': j.title,
                'company': j.company_name,
            })

    avg_salary = round(sum(monthly_mids) / len(monthly_mids), 1) if monthly_mids else 0

    # Word cloud
    text = ' '.join(all_descs)
    words = jieba.cut(text)
    wf = Counter()
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w not in _STOP_CHARS and w not in _STOP_WORDS:
            wf[w] += 1

    top_companies = company_counts.most_common(15)

    return {
        'total': total,
        'companies': companies,
        'monthly_count': len(monthly_mids),
        'avg_salary': avg_salary,
        'salary_bins': salary_bins,
        'salary_types': salary_type_counts,
        'exp_counts': exp_counts,
        'edu_counts': edu_counts,
        'top_companies': [(c, n) for c, n in top_companies],
        'top_words': [(w, c) for w, c in wf.most_common(100)],
        'scatter_pts': scatter_pts,
    }


def query_all():
    engine = get_engine()
    session = get_session(engine)

    keywords = sorted([r[0] for r in session.query(Job.keyword).distinct() if r[0]])

    data = {}
    data['全部'] = _compute_stats(session, None)
    for kw in keywords:
        stats = _compute_stats(session, kw)
        if stats:
            data[kw] = stats

    session.close()
    return {
        'keywords': ['全部'] + keywords,
        'data': data,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


# ═══════════════════════════════════════════════════════════════════
#  HTML template — Apple-style design
# ═══════════════════════════════════════════════════════════════════

def generate_html(dashboard):
    raw_json = json.dumps(dashboard, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>岗位数据分析 — Auto Offer</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts-wordcloud@2.1.0/dist/echarts-wordcloud.min.js"></script>
<style>
:root {{
  --bg: #141118;
  --surface: #1e1b24;
  --surface2: #25222d;
  --surface3: #2d2936;
  --border: #302c39;
  --text: #ffffff;
  --text2: #b0acb9;
  --text3: #787380;
  --lavender: #b8a9d4;
  --mint: #7ecba1;
  --cream: #f0d78c;
  --rose: #e8998d;
  --sky: #8ecae6;
  --radius: 24px;
  --radius-sm: 16px;
  --shadow-card: 0 2px 8px rgba(0,0,0,.25), 0 0 1px rgba(255,255,255,.04);
  --shadow-lg: 0 8px 40px rgba(0,0,0,.4), 0 0 1px rgba(255,255,255,.06);
  --shadow-diffuse: 0 20px 80px rgba(0,0,0,.5);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
  display: flex; min-height: 100vh;
}}

/* ── Sidebar ─────────────────────────────────────────────── */
.side {{
  width: 64px; flex-shrink: 0; background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; align-items: center;
  padding: 20px 0; gap: 6px; position: sticky; top: 0; height: 100vh;
}}
.side-icon {{
  width: 40px; height: 40px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; cursor: pointer; transition: all .2s;
  color: var(--text3); position: relative;
}}
.side-icon:hover {{ color: var(--text2); background: var(--surface3); }}
.side-icon.active {{ color: var(--lavender); background: rgba(184,169,212,.15); }}
.side-icon.active::before {{
  content: ''; position: absolute; left: -12px; top: 12px; bottom: 12px;
  width: 3px; border-radius: 0 3px 3px 0; background: var(--lavender);
}}

/* ── Main area ───────────────────────────────────────────── */
.main {{ flex:1; display: flex; flex-direction: column; min-width: 0; }}

/* ── Top bar ─────────────────────────────────────────────── */
.topbar {{
  position: sticky; top:0; z-index:50;
  background: rgba(20,17,24,.82); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--border);
  padding: 0 32px; height: 56px; display: flex; align-items: center; gap: 24px;
}}
.topbar-logo {{ font-size: 17px; font-weight: 700; letter-spacing: -.2px; color: var(--text); }}
.topbar-tabs {{ display: flex; gap: 6px; flex:1; }}
.tab-pill {{
  padding: 6px 16px; border-radius: 980px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .18s; border: none; outline: none;
  background: transparent; color: var(--text3); font-family: inherit;
  white-space: nowrap;
}}
.tab-pill:hover {{ color: var(--text2); background: var(--surface3); }}
.tab-pill.active {{ background: var(--surface3); color: var(--text); font-weight: 600; }}
.topbar-actions {{ display: flex; gap: 10px; align-items: center; }}
.topbar-date {{ font-size: 12px; color: var(--text3); }}

/* ── Content ──────────────────────────────────────────────── */
.content {{ flex:1; padding: 28px 32px 40px; display: flex; flex-direction: column; gap: 24px; }}

/* ── Two-column section ──────────────────────────────────── */
.twocol {{ display: flex; gap: 24px; }}
.col-left {{ flex: 1.2; display: flex; flex-direction: column; gap: 24px; min-width: 0; }}
.col-right {{ flex: 0.8; min-width: 320px; }}

/* ── Stacked cards ───────────────────────────────────────── */
.stacked-area {{ position: relative; padding: 8px 0 8px 40px; }}
.stack-card {{
  background: var(--surface2); border-radius: var(--radius);
  padding: 22px 24px; box-shadow: var(--shadow-card);
  position: relative; transition: transform .2s, box-shadow .2s;
  border: 1px solid var(--border);
}}
.stack-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-lg); }}
.stack-card:nth-child(1) {{ z-index:4; }}
.stack-card:nth-child(2) {{ z-index:3; margin-top: -16px; margin-left: 12px; }}
.stack-card:nth-child(3) {{ z-index:2; margin-top: -16px; margin-left: 24px; }}
.stack-card:nth-child(4) {{ z-index:1; margin-top: -16px; margin-left: 36px; }}
.stack-inner {{ display: flex; align-items: center; justify-content: space-between; }}
.stack-label {{ font-size: 13px; font-weight: 500; color: var(--text3); letter-spacing: .3px; text-transform: uppercase; }}
.stack-value {{ font-size: 28px; font-weight: 700; letter-spacing: -.6px; }}
.stack-value.lav {{ color: var(--lavender); }}
.stack-value.mint {{ color: var(--mint); }}
.stack-value.cream {{ color: var(--cream); }}
.stack-value.rose {{ color: var(--rose); }}

/* ── Table ───────────────────────────────────────────────── */
.table-card {{
  background: var(--surface); border-radius: var(--radius);
  padding: 20px 24px; box-shadow: var(--shadow-card);
  border: 1px solid var(--border);
}}
.table-card h3 {{ font-size: 15px; font-weight: 600; margin-bottom: 14px; color: var(--text2); }}
.table-wrap {{ width: 100%; }}
.table-wrap table {{ width: 100%; border-collapse: collapse; }}
.table-wrap th {{
  text-align: left; font-size: 11px; font-weight: 600; color: var(--text3);
  text-transform: uppercase; letter-spacing: .5px; padding: 8px 12px 10px;
  border-bottom: 1px solid var(--border);
}}
.table-wrap td {{
  padding: 10px 12px; font-size: 13px; color: var(--text2);
  border: none;
}}
.table-wrap tr:nth-child(even) td {{ background: rgba(255,255,255,.015); }}
.table-wrap .rank {{ color: var(--text3); font-size: 12px; font-weight: 500; width: 32px; }}
.table-wrap .count {{ color: var(--lavender); font-weight: 600; text-align: right; }}

/* ── Hero card (right column) ────────────────────────────── */
.hero-card {{
  background: var(--surface2); border-radius: var(--radius);
  box-shadow: var(--shadow-card); border: 1px solid var(--border);
  position: relative; overflow: visible; height: 100%;
  display: flex; flex-direction: column;
}}
/* Concave notch */
.hero-card::before {{
  content: ''; position: absolute; top: -28px; left: 50%; transform: translateX(-50%);
  width: 56px; height: 56px; border-radius: 50%;
  background: var(--bg);
  box-shadow: inset 0 2px 8px rgba(0,0,0,.3);
  z-index: 2;
}}
.hero-card-inner {{
  flex:1; padding: 36px 24px 24px; display: flex; flex-direction: column;
}}
.hero-card h3 {{ font-size: 15px; font-weight: 600; margin-bottom: 4px; }}
.hero-card .hero-sub {{ font-size: 12px; color: var(--text3); margin-bottom: 16px; }}
.hero-visual {{ flex:1; min-height: 360px; }}

/* ── Chart grid (full width, below two-column) ───────────── */
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.chart-card {{
  background: var(--surface); border-radius: var(--radius);
  padding: 20px 24px; box-shadow: var(--shadow-card);
  border: 1px solid var(--border);
}}
.chart-card.full {{ grid-column: 1 / -1; }}
.chart-card h3 {{ font-size: 15px; font-weight: 600; margin-bottom: 2px; }}
.chart-card .chart-sub {{ font-size: 12px; color: var(--text3); margin-bottom: 12px; }}
.chart-box {{ width: 100%; height: 320px; }}
.chart-box.tall {{ height: 370px; }}

/* ── Diffuse shadow bottom ────────────────────────────────── */
.diffuse-shadow {{
  position: fixed; bottom: -60px; left: 50%; transform: translateX(-50%);
  width: 600px; height: 120px; border-radius: 50%;
  background: radial-gradient(ellipse, rgba(184,169,212,.08) 0%, transparent 70%);
  pointer-events: none; z-index: -1;
}}

/* ── Semi-transparent pill labels ────────────────────────── */
.tag-pill {{
  display: inline-block; padding: 3px 12px; border-radius: 980px;
  font-size: 12px; font-weight: 500;
  background: rgba(255,255,255,.08); color: var(--text2);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}}

@media (max-width: 1000px) {{
  .twocol {{ flex-direction: column; }}
  .col-right {{ min-width: 0; }}
  .chart-grid {{ grid-template-columns: 1fr; }}
  .stacked-area {{ padding-left: 20px; }}
  .side {{ display: none; }}
  .topbar {{ padding: 0 16px; }}
  .content {{ padding: 20px 16px 32px; }}
}}
</style>
</head>
<body>

<!-- Sidebar -->
<aside class="side">
  <div class="side-icon active" title="仪表盘" data-nav="0">📊</div>
  <div class="side-icon" title="薪资分析" data-nav="1">💰</div>
  <div class="side-icon" title="公司分布" data-nav="2">🏢</div>
  <div class="side-icon" title="关键词" data-nav="3">🔑</div>
  <div class="side-icon" title="散点对比" data-nav="4">📈</div>
  <div class="side-icon" title="数据导出" data-nav="5">⚙</div>
</aside>

<!-- Main -->
<div class="main">

<!-- Top bar -->
<div class="topbar">
  <span class="topbar-logo">Auto Offer</span>
  <div class="topbar-tabs" id="tab-bar"></div>
  <div class="topbar-actions">
    <span class="topbar-date">{dashboard['generated_at']}</span>
  </div>
</div>

<!-- Content -->
<div class="content">

<!-- Two-column: stacked cards + table | hero card -->
<div class="twocol">
  <div class="col-left">
    <div class="stacked-area" id="stacked-cards"></div>
    <div class="table-card">
      <h3>热门公司</h3>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>公司</th><th>岗位数</th></tr></thead>
        <tbody id="company-tbody"></tbody></table>
      </div>
    </div>
  </div>
  <div class="col-right">
    <div class="hero-card">
      <div class="hero-card-inner">
        <h3>岗位关键词云</h3>
        <div class="hero-sub">JD 描述中的高频技能词</div>
        <div class="hero-visual" id="chart-wordcloud"></div>
      </div>
    </div>
  </div>
</div>

<!-- Charts -->
<div class="chart-grid" id="chart-grid"></div>

</div>
</div>

<div class="diffuse-shadow"></div>

<script>
// ═══════════════════════════════════════════════════════════════
//  Data & palette
// ═══════════════════════════════════════════════════════════════
var D = {raw_json};
var P = ['#b8a9d4','#7ecba1','#f0d78c','#e8998d','#8ecae6','#c4b5e0','#a0d8b8','#f5e2a8','#edb0a7','#a8d6ed'];

// ═══════════════════════════════════════════════════════════════
//  Dark chart theme
// ═══════════════════════════════════════════════════════════════
function dTheme() {{
  return {{
    tooltip: {{
      backgroundColor: 'rgba(30,27,36,.96)',
      borderColor: '#302c39', borderRadius: 14, padding: [10,14],
      textStyle: {{ color: '#fff', fontSize: 13 }}
    }}
  }};
}}
function dAxis() {{
  return {{
    axisTick: {{ show: false }},
    axisLine: {{ lineStyle: {{ color: '#302c39' }} }},
    splitLine: {{ lineStyle: {{ color: '#25222d' }} }},
    axisLabel: {{ color: '#787380', fontSize: 10 }},
    nameTextStyle: {{ color: '#b0acb9', fontSize: 11 }}
  }};
}}

// ═══════════════════════════════════════════════════════════════
//  Chart renderers
// ═══════════════════════════════════════════════════════════════
var charts = {{}};

charts.salary = function(dom, d) {{
  var bins = ['0-3k','3-5k','5-8k','8-12k','12-18k','18-25k','25k+'];
  var vals = bins.map(function(b){{return d.salary_bins[b]||0;}});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(dTheme(), {{
    grid: {{ left:44, right:20, top:12, bottom:28 }},
    xAxis: Object.assign({{ type:'category', data:bins }}, dAxis()),
    yAxis: Object.assign({{ type:'value', name:'岗位数' }}, dAxis()),
    series: [{{
      type:'bar', data:vals, barWidth:'48%',
      itemStyle: {{
        borderRadius: [6,6,0,0],
        color: new echarts.graphic.LinearGradient(0,0,0,1,[
          {{offset:0,color:'#b8a9d4'}},{{offset:1,color:'#8ecae6'}}
        ])
      }}
    }}]
  }}));
  return inst;
}};

charts.experience = function(dom, d) {{
  var data = Object.entries(d.exp_counts).map(function(e){{return{{name:e[0],value:e[1]}};}});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(dTheme(), {{
    color: P,
    series: [{{
      type:'pie', radius:['48%','76%'], center:['50%','54%'], data:data,
      label: {{ fontSize:11, color:'#b0acb9', formatter:'{{b}}\\n{{d}}%' }},
      emphasis: {{ label:{{ fontSize:15, fontWeight:'bold', color:'#fff' }} }},
      itemStyle: {{ borderColor:'#1e1b24', borderWidth:2 }}
    }}]
  }}));
  return inst;
}};

charts.education = function(dom, d) {{
  var data = Object.entries(d.edu_counts).map(function(e){{return{{name:e[0],value:e[1]}};}});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(dTheme(), {{
    color: P,
    series: [{{
      type:'pie', radius:['48%','76%'], center:['50%','54%'], data:data,
      label: {{ fontSize:11, color:'#b0acb9', formatter:'{{b}}\\n{{d}}%' }},
      emphasis: {{ label:{{ fontSize:15, fontWeight:'bold', color:'#fff' }} }},
      itemStyle: {{ borderColor:'#1e1b24', borderWidth:2 }}
    }}]
  }}));
  return inst;
}};

charts.type = function(dom, d) {{
  var map = {{'月薪':'月薪','日薪':'日薪','时薪':'时薪','面议':'面议'}};
  var data = Object.entries(d.salary_types).map(function(e){{return{{name:map[e[0]]||e[0]||'其他',value:e[1]}};}});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(dTheme(), {{
    color: P,
    series: [{{
      type:'pie', roseType:'area', radius:['36%','76%'], center:['50%','54%'], data:data,
      label: {{ fontSize:11, color:'#b0acb9' }},
      itemStyle: {{ borderColor:'#1e1b24', borderWidth:2 }}
    }}]
  }}));
  return inst;
}};

charts.scatter = function(dom, d) {{
  var expSet = [...new Set(d.scatter_pts.map(function(p){{return p.experience;}}))];
  var expCol = {{}};
  expSet.forEach(function(e,i){{expCol[e]=P[i%P.length];}});
  var series = {{}};
  d.scatter_pts.forEach(function(p){{
    if(!series[p.experience]) series[p.experience]=[];
    series[p.experience].push({{value:[p.experience,p.salary],title:p.title,company:p.company}});
  }});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(dTheme(), {{
    grid: {{ left:56, right:24, top:16, bottom:54 }},
    xAxis: Object.assign({{ type:'category', name:'经验要求', axisLabel:{{rotate:22,fontSize:10}} }}, dAxis()),
    yAxis: Object.assign({{ type:'value', name:'薪资 (K/月)', min:0 }}, dAxis()),
    series: Object.entries(series).map(function(e){{
      return {{
        name:e[0], type:'scatter', data:e[1],
        symbolSize: function(v){{return 5+Math.random()*6;}},
        itemStyle: {{ color:expCol[e[0]], opacity:.75 }},
        emphasis: {{ focus:'series', scale:1.6 }}
      }};
    }})
  }}));
  return inst;
}};

charts.wordcloud = function(dom, d) {{
  var data = d.top_words.map(function(w){{return{{name:w[0],value:w[1]}};}});
  var inst = echarts.init(dom);
  inst.setOption({{
    tooltip: {{
      backgroundColor: 'rgba(30,27,36,.96)', borderColor: '#302c39',
      borderRadius: 14, padding: [10,14],
      textStyle: {{ color:'#fff', fontSize:13 }}, formatter:'{{b}}: {{c}} 次'
    }},
    series: [{{
      type:'wordCloud', shape:'circle', sizeRange:[14,50],
      rotationRange:[-25,25], gridSize:6, drawOutOfBound:false,
      layoutAnimation:true, keepAspect:true,
      textStyle: {{
        fontFamily: 'Inter, PingFang SC, sans-serif', fontWeight:'600',
        color: function(){{ var h=Math.round(Math.random()*40+250); return 'hsl('+h+',50%,65%)'; }}
      }},
      data:data
    }}]
  }});
  return inst;
}};

// ═══════════════════════════════════════════════════════════════
//  UI renderers
// ═══════════════════════════════════════════════════════════════
function renderStackedCards(d) {{
  var cards = [
    {{ label:'岗位总数', value:d.total, cls:'lav', sub:'条' }},
    {{ label:'覆盖公司', value:d.companies, cls:'mint', sub:'家' }},
    {{ label:'月薪均价', value:d.avg_salary, cls:'cream', sub:'K' }},
    {{ label:'月薪岗位', value:d.monthly_count, cls:'rose', sub:'条' }},
  ];
  var html = '';
  cards.forEach(function(c){{
    html += '<div class="stack-card"><div class="stack-inner"><div><div class="stack-label">'+c.label+'</div></div><div class="stack-value '+c.cls+'">'+c.value+'<span style="font-size:14px;font-weight:400;color:var(--text3);margin-left:4px">'+c.sub+'</span></div></div></div>';
  }});
  document.getElementById('stacked-cards').innerHTML = html;
}}

function renderTable(d) {{
  var rows = '';
  d.top_companies.forEach(function(c,i){{
    rows += '<tr><td class="rank">'+(i+1)+'</td><td>'+c[0]+'</td><td class="count">'+c[1]+'</td></tr>';
  }});
  document.getElementById('company-tbody').innerHTML = rows;
}}

// ═══════════════════════════════════════════════════════════════
//  Chart grid structure
// ═══════════════════════════════════════════════════════════════
var CHART_DEFS = [
  {{ id:'chart-salary',    title:'薪资分布',     sub:'月薪岗位的薪资区间分布',     renderer:'salary'    }},
  {{ id:'chart-experience',title:'经验要求',     sub:'招聘要求的工作经验年限',     renderer:'experience'}},
  {{ id:'chart-education', title:'学历要求',     sub:'招聘要求的学历层次',         renderer:'education' }},
  {{ id:'chart-type',     title:'薪资类型',     sub:'月薪、日薪、时薪、面议占比', renderer:'type'      }},
  {{ id:'chart-scatter',  title:'薪资 vs 经验', sub:'不同经验水平的薪资分布',     renderer:'scatter', cls:'full' }},
];

function buildChartGrid() {{
  var html = '';
  CHART_DEFS.forEach(function(def){{
    var cls = def.cls || '';
    html += '<div class="chart-card'+(cls==='full'?' full':'')+'">';
    html += '<h3>'+def.title+'</h3>';
    html += '<div class="chart-sub">'+def.sub+'</div>';
    html += '<div class="chart-box" id="'+def.id+'"></div>';
    html += '</div>';
  }});
  document.getElementById('chart-grid').innerHTML = html;
}}

// ═══════════════════════════════════════════════════════════════
//  Tabs
// ═══════════════════════════════════════════════════════════════
function buildTabs() {{
  var html = '';
  D.keywords.forEach(function(kw,i){{
    html += '<button class="tab-pill'+(i===0?' active':'')+'" data-kw="'+kw+'">'+kw+'</button>';
  }});
  document.getElementById('tab-bar').innerHTML = html;
}}

// ═══════════════════════════════════════════════════════════════
//  Render all
// ═══════════════════════════════════════════════════════════════
var activeInstances = [];

function renderAll(keyword) {{
  var d = D.data[keyword];
  if (!d) return;

  activeInstances.forEach(function(inst){{ inst.dispose(); }});
  activeInstances = [];

  renderStackedCards(d);
  renderTable(d);

  // Word cloud in hero card
  var wcDom = document.getElementById('chart-wordcloud');
  activeInstances.push(charts.wordcloud(wcDom, d));

  // Grid charts
  CHART_DEFS.forEach(function(def){{
    var dom = document.getElementById(def.id);
    if (dom) activeInstances.push(charts[def.renderer](dom, d));
  }});
}}

// ═══════════════════════════════════════════════════════════════
//  Init
// ═══════════════════════════════════════════════════════════════
(function init() {{
  buildTabs();
  buildChartGrid();
  renderAll('全部');

  // Tab clicks
  document.getElementById('tab-bar').addEventListener('click', function(e){{
    if (e.target.classList.contains('tab-pill')) {{
      var kw = e.target.dataset.kw;
      document.querySelectorAll('.tab-pill').forEach(function(b){{b.classList.remove('active');}});
      e.target.classList.add('active');
      renderAll(kw);
    }}
  }});

  // Sidebar clicks — scroll to sections or switch tabs
  document.querySelector('.side').addEventListener('click', function(e){{
    var icon = e.target.closest('.side-icon');
    if (!icon) return;
    document.querySelectorAll('.side-icon').forEach(function(s){{s.classList.remove('active');}});
    icon.classList.add('active');
    var navIdx = parseInt(icon.dataset.nav);
    if (navIdx === 0) {{
      window.scrollTo({{top:0,behavior:'smooth'}});
    }} else {{
      var chartIds = ['','chart-salary','chart-company','chart-wordcloud','chart-scatter'];
      var target = document.getElementById(chartIds[navIdx]);
      if (target) target.scrollIntoView({{behavior:'smooth',block:'center'}});
    }}
  }});

  // Resize
  window.addEventListener('resize', function(){{
    activeInstances.forEach(function(inst){{ inst.resize(); }});
  }});
}})();
</script>
</body>
</html>'''


def main():
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, 'dashboard.html')

    print('查询数据库...')
    dashboard = query_all()
    print(f'  关键词: {dashboard["keywords"]}')
    for kw in dashboard['keywords']:
        d = dashboard['data'][kw]
        print(f'    {kw}: {d["total"]} 条岗位, {d["companies"]} 家公司, 均价 {d["avg_salary"]}K')

    print('生成 HTML...')
    html = generate_html(dashboard)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'已生成: {output_path} ({len(html)} bytes)')
    print('用浏览器打开即可查看。')


if __name__ == '__main__':
    main()
