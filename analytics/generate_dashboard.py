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
  --bg: #f5f5f7;
  --card: #ffffff;
  --text: #1d1d1f;
  --secondary: #86868b;
  --tertiary: #aeaeb2;
  --accent: #0071e3;
  --green: #34c759;
  --orange: #ff9500;
  --purple: #af52de;
  --pink: #ff2d55;
  --teal: #5ac8fa;
  --indigo: #5856d6;
  --separator: #d2d2d7;
  --radius: 18px;
  --radius-sm: 12px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', 'PingFang SC', 'Helvetica Neue', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
}}

/* ── Navigation ──────────────────────────────────────────── */
.nav {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(245,245,247,0.82); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--separator);
}}
.nav-inner {{
  max-width: 1200px; margin: 0 auto; padding: 0 32px;
  display: flex; align-items: center; justify-content: space-between; height: 52px;
}}
.nav-title {{ font-size: 19px; font-weight: 600; letter-spacing: -.2px; }}
.nav-badge {{ font-size: 12px; color: var(--secondary); }}

/* ── Main content ────────────────────────────────────────── */
.container {{ max-width: 1200px; margin: 0 auto; padding: 32px 32px 60px; }}

/* ── Hero ───────────────────────────────────────────────── */
.hero {{ margin-bottom: 36px; }}
.hero h1 {{ font-size: 40px; font-weight: 700; letter-spacing: -.5px; line-height: 1.12; margin-bottom: 8px; }}
.hero p {{ font-size: 17px; color: var(--secondary); }}

/* ── Select ─────────────────────────────────────────────── */
.select-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 32px; }}
.select-row label {{ font-size: 15px; font-weight: 500; color: var(--text); }}
.kw-select {{
  appearance: none; -webkit-appearance: none;
  background: var(--card); border: 1px solid var(--separator);
  border-radius: 980px; padding: 8px 36px 8px 16px;
  font-size: 15px; font-family: inherit; color: var(--text);
  cursor: pointer; outline: none; min-width: 180px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2386868b' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 14px center;
  transition: border-color .15s, box-shadow .15s;
}}
.kw-select:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,.15); }}

/* ── Stats grid ─────────────────────────────────────────── */
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
.stat {{
  background: var(--card); border-radius: var(--radius); padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,.04); transition: box-shadow .2s;
}}
.stat:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.06); }}
.stat-label {{ font-size: 13px; font-weight: 500; color: var(--secondary); margin-bottom: 4px; letter-spacing: -.1px; }}
.stat-value {{ font-size: 34px; font-weight: 700; letter-spacing: -.8px; line-height: 1.1; }}
.stat-sub {{ font-size: 13px; color: var(--tertiary); margin-top: 2px; }}

/* ── Chart grid ─────────────────────────────────────────── */
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.chart-card {{
  background: var(--card); border-radius: var(--radius); padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,.04); transition: box-shadow .2s;
}}
.chart-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.06); }}
.chart-card.full {{ grid-column: 1 / -1; }}
.chart-card h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 4px; letter-spacing: -.2px; }}
.chart-card .chart-sub {{ font-size: 12px; color: var(--tertiary); margin-bottom: 12px; }}
.chart-box {{ width: 100%; height: 340px; }}
.chart-box.tall {{ height: 400px; }}

/* ── Footer ─────────────────────────────────────────────── */
.footer {{ text-align: center; padding: 24px; color: var(--tertiary); font-size: 12px; }}

/* ── Empty state ─────────────────────────────────────────── */
.empty {{ display: flex; align-items: center; justify-content: center; height: 200px; color: var(--tertiary); font-size: 15px; }}

@media (max-width: 900px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
  .chart-grid {{ grid-template-columns: 1fr; }}
  .hero h1 {{ font-size: 28px; }}
  .container {{ padding: 20px 16px 40px; }}
}}
</style>
</head>
<body>

<nav class="nav">
  <div class="nav-inner">
    <span class="nav-title">Auto Offer</span>
    <span class="nav-badge">岗位分析</span>
  </div>
</nav>

<div class="container">

<div class="hero">
  <h1>岗位数据分析</h1>
  <p>了解市场全貌，做出更好的求职决策</p>
</div>

<div class="select-row">
  <label for="kw-select">关键词</label>
  <select class="kw-select" id="kw-select"></select>
</div>

<div class="stats" id="stats-row"></div>

<div class="chart-grid" id="chart-grid"></div>

<div class="footer">Auto Offer · 数据来源 BOSS直聘 · 生成于 {dashboard['generated_at']}</div>

</div>

<script>
// ═══════════════════════════════════════════════════════════════
//  Data
// ═══════════════════════════════════════════════════════════════
var D = {raw_json};

// ═══════════════════════════════════════════════════════════════
//  Chart color palette
// ═══════════════════════════════════════════════════════════════
var P = ['#0071e3','#34c759','#ff9500','#af52de','#ff2d55','#5ac8fa','#5856d6','#ff9f0a','#30d158','#0a84ff'];

// ═══════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════
function chartTheme() {{
  return {{
    tooltip: {{
      backgroundColor: 'rgba(29,29,31,.94)',
      borderColor: 'transparent',
      borderRadius: 10,
      padding: [10,14],
      textStyle: {{ color: '#fff', fontSize: 13, fontWeight: 400 }},
      extraCssText: 'backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);'
    }}
  }};
}}

// ═══════════════════════════════════════════════════════════════
//  Chart renderers — each takes (dom, data)
// ═══════════════════════════════════════════════════════════════
var charts = {{}};

charts.salary = function(dom, d) {{
  var bins = ['0-3k','3-5k','5-8k','8-12k','12-18k','18-25k','25k+'];
  var vals = bins.map(function(b){{ return d.salary_bins[b] || 0; }});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(chartTheme(), {{
    grid: {{ left: 44, right: 20, top: 12, bottom: 28 }},
    xAxis: {{
      type: 'category', data: bins,
      axisTick: {{ show: false }},
      axisLine: {{ lineStyle: {{ color: '#d2d2d7' }} }},
      axisLabel: {{ color: '#86868b', fontSize: 11 }}
    }},
    yAxis: {{
      type: 'value', name: '岗位数',
      nameTextStyle: {{ color: '#aeaeb2', fontSize: 11 }},
      splitLine: {{ lineStyle: {{ color: '#f5f5f7' }} }},
      axisLabel: {{ color: '#aeaeb2', fontSize: 10 }}
    }},
    series: [{{
      type: 'bar', data: vals,
      itemStyle: {{
        borderRadius: [6,6,0,0],
        color: new echarts.graphic.LinearGradient(0,0,0,1,[
          {{offset:0,color:'#0071e3'}},{{offset:1,color:'#5ac8fa'}}
        ])
      }},
      barWidth: '48%', emphasis: {{ itemStyle: {{ color: '#0077ed' }} }}
    }}]
  }}));
  return inst;
}};

charts.experience = function(dom, d) {{
  var data = Object.entries(d.exp_counts).map(function(e){{ return {{name:e[0],value:e[1]}}; }});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(chartTheme(), {{
    color: P,
    series: [{{
      type: 'pie', radius: ['50%','78%'], center: ['50%','54%'],
      data: data, label: {{ fontSize: 11, color: '#86868b', formatter: '{{b}}\\n{{d}}%' }},
      emphasis: {{ label: {{ fontSize: 15, fontWeight: '600' }} }},
      itemStyle: {{ borderColor: '#fff', borderWidth: 2 }}
    }}]
  }}));
  return inst;
}};

charts.education = function(dom, d) {{
  var data = Object.entries(d.edu_counts).map(function(e){{ return {{name:e[0],value:e[1]}}; }});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(chartTheme(), {{
    color: P,
    series: [{{
      type: 'pie', radius: ['50%','78%'], center: ['50%','54%'],
      data: data, label: {{ fontSize: 11, color: '#86868b', formatter: '{{b}}\\n{{d}}%' }},
      emphasis: {{ label: {{ fontSize: 15, fontWeight: '600' }} }},
      itemStyle: {{ borderColor: '#fff', borderWidth: 2 }}
    }}]
  }}));
  return inst;
}};

charts.type = function(dom, d) {{
  var map = {{'月薪':'月薪','日薪':'日薪','时薪':'时薪','面议':'面议'}};
  var data = Object.entries(d.salary_types).map(function(e){{ return {{name:map[e[0]]||e[0]||'其他',value:e[1]}}; }});
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(chartTheme(), {{
    color: [P[0],P[1],P[2],'#aeaeb2'],
    series: [{{
      type: 'pie', roseType: 'area', radius: ['38%','78%'], center: ['50%','54%'],
      data: data, label: {{ fontSize: 11, color: '#86868b' }},
      itemStyle: {{ borderColor: '#fff', borderWidth: 2 }}
    }}]
  }}));
  return inst;
}};

charts.company = function(dom, d) {{
  var names = d.top_companies.map(function(c){{return c[0];}}).reverse();
  var counts = d.top_companies.map(function(c){{return c[1];}}).reverse();
  var inst = echarts.init(dom);
  inst.setOption(Object.assign(chartTheme(), {{
    grid: {{ left: 130, right: 24, top: 8, bottom: 16 }},
    xAxis: {{
      type: 'value', splitLine: {{ lineStyle: {{ color: '#f5f5f7' }} }},
      axisLabel: {{ color: '#aeaeb2', fontSize: 10 }}
    }},
    yAxis: {{
      type: 'category', data: names,
      axisLine: {{ show: false }}, axisTick: {{ show: false }},
      axisLabel: {{ fontSize: 11, color: '#1d1d1f', width: 114, overflow: 'truncate' }}
    }},
    series: [{{
      type: 'bar', data: counts,
      itemStyle: {{
        borderRadius: [0,6,6,0],
        color: new echarts.graphic.LinearGradient(0,0,1,0,[
          {{offset:0,color:'#5856d6'}},{{offset:1,color:'#af52de'}}
        ])
      }},
      barWidth: '58%'
    }}]
  }}));
  return inst;
}};

charts.wordcloud = function(dom, d) {{
  var data = d.top_words.map(function(w){{ return {{name:w[0],value:w[1]}}; }});
  var inst = echarts.init(dom);
  inst.setOption({{
    tooltip: {{
      backgroundColor: 'rgba(29,29,31,.94)', borderColor: 'transparent',
      borderRadius: 10, padding: [10,14],
      textStyle: {{ color: '#fff', fontSize: 13 }},
      formatter: '{{b}}: {{c}} 次'
    }},
    series: [{{
      type: 'wordCloud', shape: 'circle', sizeRange: [14,50],
      rotationRange: [-25,25], gridSize: 6, drawOutOfBound: false,
      layoutAnimation: true, keepAspect: true,
      textStyle: {{
        fontFamily: '-apple-system, PingFang SC, sans-serif', fontWeight: '500',
        color: function(){{ var h=Math.round(Math.random()*60+200); return 'hsl('+h+',55%,45%)'; }}
      }},
      data: data
    }}]
  }});
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
  inst.setOption(Object.assign(chartTheme(), {{
    grid: {{ left: 56, right: 28, top: 16, bottom: 54 }},
    xAxis: {{
      type: 'category', name: '经验要求',
      nameTextStyle: {{ color: '#aeaeb2', fontSize: 11 }},
      axisLabel: {{ rotate: 22, fontSize: 10, color: '#86868b' }},
      axisTick: {{ show: false }},
      axisLine: {{ lineStyle: {{ color: '#d2d2d7' }} }}
    }},
    yAxis: {{
      type: 'value', name: '薪资 (K/月)',
      nameTextStyle: {{ color: '#aeaeb2', fontSize: 11 }},
      splitLine: {{ lineStyle: {{ color: '#f5f5f7' }} }},
      axisLabel: {{ color: '#aeaeb2', fontSize: 10 }}, min: 0
    }},
    series: Object.entries(series).map(function(e){{
      return {{
        name: e[0], type: 'scatter', data: e[1],
        symbolSize: function(v){{ return 5+Math.random()*6; }},
        itemStyle: {{ color: expCol[e[0]], opacity: .7 }},
        emphasis: {{ focus: 'series', scale: 1.6 }}
      }};
    }})
  }}));
  return inst;
}};

// ═══════════════════════════════════════════════════════════════
//  Stats renderer
// ═══════════════════════════════════════════════════════════════
function renderStats(d) {{
  document.getElementById('stats-row').innerHTML =
    '<div class="stat"><div class="stat-label">岗位总数</div><div class="stat-value" style="color:var(--accent)">'+d.total+'</div><div class="stat-sub">条</div></div>' +
    '<div class="stat"><div class="stat-label">覆盖公司</div><div class="stat-value" style="color:var(--green)">'+d.companies+'</div><div class="stat-sub">家</div></div>' +
    '<div class="stat"><div class="stat-label">月薪均价</div><div class="stat-value" style="color:var(--orange)">'+d.avg_salary+'</div><div class="stat-sub">K</div></div>' +
    '<div class="stat"><div class="stat-label">月薪岗位</div><div class="stat-value" style="color:var(--purple)">'+d.monthly_count+'</div><div class="stat-sub">条</div></div>';
}}

// ═══════════════════════════════════════════════════════════════
//  Chart grid structure (extensible — add a div + renderer above)
// ═══════════════════════════════════════════════════════════════
var CHART_DEFS = [
  {{ id:'chart-salary',    title:'薪资分布',     sub:'月薪岗位的薪资区间分布',     renderer:'salary',    cls:'' }},
  {{ id:'chart-experience',title:'经验要求',     sub:'招聘要求的工作经验年限',     renderer:'experience',cls:'' }},
  {{ id:'chart-education', title:'学历要求',     sub:'招聘要求的学历层次',         renderer:'education', cls:'' }},
  {{ id:'chart-type',     title:'薪资类型',     sub:'月薪、日薪、时薪、面议占比',   renderer:'type',      cls:'' }},
  {{ id:'chart-company',  title:'热门公司',     sub:'发布岗位最多的公司 TOP15',    renderer:'company',   cls:'tall' }},
  {{ id:'chart-wordcloud',title:'岗位关键词',   sub:'JD 描述中的高频技能词',       renderer:'wordcloud', cls:'tall' }},
  {{ id:'chart-scatter',  title:'薪资 vs 经验', sub:'不同经验水平的薪资分布',      renderer:'scatter',   cls:'full' }},
];

function buildChartGrid() {{
  var html = '';
  CHART_DEFS.forEach(function(def){{
    html += '<div class="chart-card'+(def.cls==='full'?' full':'')+'">';
    html += '<h3>'+def.title+'</h3>';
    html += '<div class="chart-sub">'+def.sub+'</div>';
    html += '<div class="chart-box'+(def.cls==='tall'?' tall':'')+'" id="'+def.id+'"></div>';
    html += '</div>';
  }});
  document.getElementById('chart-grid').innerHTML = html;
}}

// ═══════════════════════════════════════════════════════════════
//  Render all
// ═══════════════════════════════════════════════════════════════
var activeInstances = [];

function renderAll(keyword) {{
  var d = D.data[keyword];
  if (!d) return;

  // Dispose old chart instances
  activeInstances.forEach(function(inst){{ inst.dispose(); }});
  activeInstances = [];

  renderStats(d);

  CHART_DEFS.forEach(function(def){{
    var dom = document.getElementById(def.id);
    var inst = charts[def.renderer](dom, d);
    activeInstances.push(inst);
  }});
}}

// ═══════════════════════════════════════════════════════════════
//  Init
// ═══════════════════════════════════════════════════════════════
(function init() {{
  // Build select options
  var sel = document.getElementById('kw-select');
  D.keywords.forEach(function(kw){{
    var opt = document.createElement('option');
    opt.value = kw;
    opt.textContent = kw + (kw !== '全部' ? '' : ' (' + D.data['全部'].total + ' 条)');
    sel.appendChild(opt);
  }});
  sel.addEventListener('change', function(){{ renderAll(this.value); }});

  // Build chart grid
  buildChartGrid();

  // Initial render
  renderAll('全部');

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
