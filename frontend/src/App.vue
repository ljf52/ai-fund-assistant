<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { demoRequest } from './demo.js'

const api = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8010/api'
const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'
const page = ref('dashboard')
const loading = ref(true)
const error = ref('')
const dashboard = ref({ holdings: [] })
const holdings = ref([])
const market = ref({ indices: [], industries: [] })
const report = ref(null)
const realtime = ref({ items: [], summary: {} })
const selectedFund = ref(null)
const showAdd = ref(false)
const generating = ref(false)
const syncing = ref(false)
const searchingFund = ref(false)
const marketRefreshing = ref(false)
const editingHolding = ref(null)
const savingEdit = ref(false)
const newHolding = ref({ fund_code: '', fund_name: '', shares: '', cost_nav: '', target_weight: 20 })

const pages = [
  ['dashboard', '总览', '⌁'], ['assets', '我的资产', '◫'], ['fund', '基金详情', '⌇'],
  ['report', 'AI 日报', '✦'], ['market', '市场雷达', '◎']
]
const titles = { dashboard: ['今日资产脉搏', '把市场变化翻译成与你有关的数字'], assets: ['我的资产', '成本、收益与仓位，一处看清'], fund: ['基金详情', '从净值曲线理解持仓节奏'], report: ['AI 投资日报', '信息是输入，纪律才是答案'], market: ['市场雷达', '看见强弱，但不追逐噪声'] }

function money(v) { return Number(v || 0).toLocaleString('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }) }
function pct(v) { return `${Number(v || 0) > 0 ? '+' : ''}${Number(v || 0).toFixed(2)}%` }
async function request(path, options) {
  if (demoMode) return demoRequest(path, options)
  const res = await fetch(`${api}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '服务暂时不可用')
  return res.status === 204 ? null : res.json()
}
async function load() {
  loading.value = true; error.value = ''
  try {
    const [d, h, m, r] = await Promise.all([request('/dashboard'), request('/holdings'), request('/market'), request('/reports/latest')])
    dashboard.value = d; holdings.value = h; market.value = m; report.value = r
    if (!selectedFund.value && h.length) await chooseFund(h[0].code, false)
    await loadRealtime()
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}
async function loadRealtime() {
  try { realtime.value = await request('/realtime/holdings') }
  catch { realtime.value = { items: [], summary: {} } }
}
async function loadMarket(force = false) {
  marketRefreshing.value = true
  try { market.value = await request(`/market${force ? '?force=true' : ''}`) }
  catch (e) { if (!market.value.indices?.length) error.value = e.message }
  finally { marketRefreshing.value = false }
}
async function chooseFund(code, navigate = true) {
  try { selectedFund.value = await request(`/funds/${code}`); if (navigate) page.value = 'fund' }
  catch (e) { error.value = e.message }
}
async function addHolding() {
  try {
    await request('/holdings', { method: 'POST', body: JSON.stringify({ ...newHolding.value, shares: +newHolding.value.shares, cost_nav: +newHolding.value.cost_nav, target_weight: +newHolding.value.target_weight }) })
    showAdd.value = false; newHolding.value = { fund_code: '', fund_name: '', shares: '', cost_nav: '', target_weight: 20 }; await load()
  } catch (e) { error.value = e.message }
}
async function lookupFund() {
  if (!/^\d{6}$/.test(newHolding.value.fund_code)) return
  searchingFund.value = true
  try {
    const results = await request(`/search/funds?q=${encodeURIComponent(newHolding.value.fund_code)}`)
    const fund = results.find(item => item.code === newHolding.value.fund_code)
    if (!fund) throw new Error('没有找到该基金代码')
    newHolding.value.fund_name = fund.name
    newHolding.value.category = fund.category
    if (!newHolding.value.cost_nav && fund.latest_nav) newHolding.value.cost_nav = fund.latest_nav
  } catch (e) { error.value = e.message }
  finally { searchingFund.value = false }
}
async function syncData() {
  syncing.value = true; error.value = ''
  try {
    const result = await request('/data/sync', { method: 'POST' })
    if (result.errors?.length) error.value = `部分数据同步失败：${result.errors.map(item => item.scope).join('、')}`
    await load()
  } catch (e) { error.value = e.message }
  finally { syncing.value = false }
}
async function removeHolding(id) { if (confirm('确认移除这笔持仓？历史基金数据会保留。')) { await request(`/holdings/${id}`, { method: 'DELETE' }); await load() } }
function openHoldingEdit(holding) {
  editingHolding.value = { id: holding.id, code: holding.code, name: holding.name, shares: holding.shares, cost_nav: holding.cost_nav, target_weight: holding.target_weight }
}
async function saveHoldingEdit() {
  savingEdit.value = true; error.value = ''
  try {
    await request(`/holdings/${editingHolding.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ shares: +editingHolding.value.shares, cost_nav: +editingHolding.value.cost_nav, target_weight: +editingHolding.value.target_weight }),
    })
    editingHolding.value = null
    await load()
  } catch (e) { error.value = e.message }
  finally { savingEdit.value = false }
}
async function createReport() {
  generating.value = true; error.value = ''
  try { report.value = await request('/reports/generate', { method: 'POST' }); dashboard.value.ai_suggestion = report.value.suggestion }
  catch (e) { error.value = e.message }
  finally { generating.value = false }
}

const allocation = computed(() => holdings.value.map(h => ({ name: h.name, value: h.market_value })))
const realtimeByHolding = computed(() => Object.fromEntries((realtime.value.items || []).map(item => [item.holding_id, item])))
const selectedRealtime = computed(() => (realtime.value.items || []).find(item => item.fund_code === selectedFund.value?.code && item.supported))
const intradayProfit = computed(() => realtime.value.summary?.supported ? realtime.value.summary.estimated_today_profit : dashboard.value.today_profit)
const marketUpdateTime = computed(() => market.value.updated_at ? new Date(market.value.updated_at).toLocaleTimeString('zh-CN', { hour12: false }) : '—')
let chart
function drawChart() {
  if (page.value !== 'fund' || !selectedFund.value) return
  nextTick(() => {
    const el = document.getElementById('nav-chart'); if (!el) return
    chart?.dispose(); chart = echarts.init(el)
    chart.setOption({
      animationDuration: 900, grid: { left: 16, right: 16, top: 22, bottom: 12, containLabel: true },
      tooltip: { trigger: 'axis', borderWidth: 0, backgroundColor: '#19372f', textStyle: { color: '#fff' } },
      xAxis: { type: 'category', data: selectedFund.value.navs.map(n => n.nav_date.slice(5)), boundaryGap: false, axisLine: { lineStyle: { color: '#ccd6cf' } }, axisLabel: { color: '#7b8a84', interval: 14 } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#e6ebe7' } }, axisLabel: { color: '#7b8a84' } },
      series: [{ type: 'line', data: selectedFund.value.navs.map(n => n.nav), showSymbol: false, smooth: 0.25, lineStyle: { color: '#c87942', width: 3 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(200,121,66,.28)' }, { offset: 1, color: 'rgba(200,121,66,0)' }] } } }]
    })
  })
}
watch([page, selectedFund], drawChart)
watch(page, current => { if (current === 'market') loadMarket() })
let realtimeTimer, marketTimer
const resizeChart = () => chart?.resize()
onMounted(() => {
  load()
  realtimeTimer = window.setInterval(loadRealtime, 30000)
  marketTimer = window.setInterval(() => { if (page.value === 'market') loadMarket() }, 30000)
  window.addEventListener('resize', resizeChart)
})
onUnmounted(() => { window.clearInterval(realtimeTimer); window.clearInterval(marketTimer); window.removeEventListener('resize', resizeChart) })
</script>

<template>
  <div class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">衡</span><div><b>知衡</b><small>AI FUND COMPASS</small></div></div>
      <nav><button v-for="item in pages" :key="item[0]" :class="{active: page===item[0]}" @click="page=item[0]"><span>{{ item[2] }}</span>{{ item[1] }}</button></nav>
      <div class="discipline"><span>投资纪律</span><p>先看仓位，再看涨跌。<br>先定条件，再做动作。</p></div>
      <div class="avatar"><i>廖</i><div><b>默认账户</b><small>个人投资视图</small></div><span>•••</span></div>
    </aside>

    <main>
      <header><div><p>{{ new Date().toLocaleDateString('zh-CN', {year:'numeric', month:'long', day:'numeric', weekday:'long'}) }}</p><h1>{{ titles[page][0] }}</h1><span>{{ titles[page][1] }}</span></div><div class="data-actions"><div class="data-badge" :class="dashboard.data_status?.mode || 'demo'"><i></i><span>{{ dashboard.data_status?.mode==='real'?'真实数据':dashboard.data_status?.mode==='mixed'?'部分真实':'演示数据' }}</span><small v-if="dashboard.data_status?.funds?.data_date">净值至 {{ dashboard.data_status.funds.data_date }}</small></div><button class="sync-button" :disabled="syncing" @click="syncData">{{ syncing ? '同步中…' : '同步真实数据' }} ↻</button></div></header>
      <section v-if="demoMode" class="pages-demo-note"><div><b>GitHub Pages 在线演示</b><span>页面使用虚构示例数据，修改不会保存；真实行情与 AI 功能需连接 FastAPI 后端。</span></div><a href="https://github.com/ljf52/ai-fund-assistant" target="_blank" rel="noreferrer">查看源码 ↗</a></section>
      <div v-if="error" class="alert">{{ error }} <button @click="error=''">×</button></div>
      <div v-if="loading" class="loading"><i></i><span>正在整理你的投资信息…</span></div>

      <template v-else-if="page==='dashboard'">
        <section class="asset-hero">
          <div><label>官方总资产 · 净值日 {{ dashboard.data_status?.funds?.data_date || '—' }}</label><strong>{{ money(dashboard.total_assets) }}</strong><p>官方累计收益 <em :class="dashboard.total_profit>=0?'up':'down'">{{ money(dashboard.total_profit) }} · {{ pct(dashboard.total_return_pct) }}</em></p></div>
          <div class="today"><label>{{ realtime.summary?.supported ? '盘中预计今日收益' : '最新净值日浮动' }}</label><b :class="intradayProfit>=0?'up':'down'">{{ intradayProfit>=0?'↗':'↘' }} {{ money(Math.abs(intradayProfit)) }}</b><small v-if="realtime.summary?.supported">估值 {{ realtime.summary.quote_time?.slice(11,19) }} · 非官方净值</small><small v-else>按最新官方净值计算</small></div>
          <div class="pulse-lines"><i></i><i></i><i></i><i></i><i></i></div>
        </section>
        <section class="ai-note"><div class="spark">✦</div><div><label>知衡今日观察</label><p>{{ dashboard.ai_suggestion }}</p></div><button @click="page='report'">查看完整日报 <span>→</span></button></section>
        <div class="section-title"><div><h2>主要持仓</h2><p>按当前市值排序</p></div><button @click="page='assets'">管理全部</button></div>
        <div class="holding-grid">
          <button class="holding-card" v-for="h in dashboard.holdings" :key="h.id" @click="chooseFund(h.code)"><div><span class="fund-type">{{ h.category.slice(0,2) }}</span><div><b>{{ h.name }}</b><small>{{ h.code }} · 仓位 {{ h.weight }}%</small></div></div><strong>{{ money(realtimeByHolding[h.id]?.supported ? realtimeByHolding[h.id].estimated_market_value : h.market_value) }}<small v-if="realtimeByHolding[h.id]?.supported" class="estimate-mark">盘中估算</small></strong><em :class="(realtimeByHolding[h.id]?.supported ? realtimeByHolding[h.id].estimated_total_return_pct : h.return_pct)>=0?'up':'down'">{{ pct(realtimeByHolding[h.id]?.supported ? realtimeByHolding[h.id].estimated_total_return_pct : h.return_pct) }}</em><div class="weight"><i :style="{width:h.weight+'%'}"></i></div></button>
        </div>
      </template>

      <template v-else-if="page==='assets'">
        <div class="asset-toolbar"><div><b>{{ holdings.length }}</b><span>只基金 · 权益资产 {{ money(dashboard.total_assets) }}</span></div><button class="primary" @click="showAdd=true">＋ 录入基金</button></div>
        <section class="panel table-wrap holdings-table"><table><colgroup><col class="col-fund"><col class="col-value"><col class="col-nav"><col class="col-profit"><col class="col-weight"><col class="col-actions"></colgroup><thead><tr><th>基金</th><th>持有市值</th><th>成本 / 官方 / 估算净值</th><th>累计收益</th><th>实际 / 目标仓位</th><th>持仓操作</th></tr></thead><tbody><tr v-for="h in holdings" :key="h.id"><td><button class="fund-link" @click="chooseFund(h.code)"><b>{{ h.name }}</b><small>{{ h.code }} · {{ h.risk_level }}</small></button></td><td><b>{{ money(realtimeByHolding[h.id]?.supported ? realtimeByHolding[h.id].estimated_market_value : h.market_value) }}</b><small>{{ h.shares.toLocaleString() }} 份 · {{ realtimeByHolding[h.id]?.supported?'盘中估算':'官方' }}</small></td><td><span class="nav-values"><span>{{ h.cost_nav.toFixed(4) }}</span><i>→</i><span>{{ h.nav.toFixed(4) }}</span><template v-if="realtimeByHolding[h.id]?.supported"><i>→</i><b>{{ realtimeByHolding[h.id].estimated_nav.toFixed(4) }}</b></template></span></td><td><b :class="(realtimeByHolding[h.id]?.supported?realtimeByHolding[h.id].estimated_total_profit:h.profit)>=0?'up':'down'">{{ money(realtimeByHolding[h.id]?.supported?realtimeByHolding[h.id].estimated_total_profit:h.profit) }}</b><small v-if="realtimeByHolding[h.id]?.supported" :class="realtimeByHolding[h.id].estimated_today_profit>=0?'up':'down'">今日估算 {{ money(realtimeByHolding[h.id].estimated_today_profit) }}</small><small v-else :class="h.return_pct>=0?'up':'down'">{{ pct(h.return_pct) }}</small></td><td><b>{{ h.weight }}% / {{ h.target_weight }}%</b><div class="weight"><i :style="{width:Math.min(h.weight,100)+'%'}"></i></div></td><td><div class="holding-actions"><button class="edit-holding" @click="openHoldingEdit(h)">编辑</button><button class="remove-holding" @click="removeHolding(h.id)">移除</button></div></td></tr></tbody></table></section>
        <section class="allocation"><div><label>仓位体检</label><h2>{{ Math.max(...holdings.map(h=>h.weight),0) > 35 ? '集中度需要留意' : '组合分布相对均衡' }}</h2><p>最大单只基金仓位为 {{ Math.max(...holdings.map(h=>h.weight),0).toFixed(1) }}%。建议把单一高波动基金控制在可承受范围内。</p></div><div class="allocation-list"><div v-for="a in allocation" :key="a.name"><span>{{ a.name }}</span><b>{{ (a.value/dashboard.total_assets*100).toFixed(1) }}%</b></div></div></section>
      </template>

      <template v-else-if="page==='fund' && selectedFund">
        <div class="fund-switch"><button v-for="h in holdings" :key="h.code" :class="{active:selectedFund.code===h.code}" @click="chooseFund(h.code,false)">{{ h.name }}</button></div>
        <section class="fund-head"><div><span>{{ selectedFund.category }} · {{ selectedFund.risk_level }}</span><h2>{{ selectedFund.name }}</h2><p>{{ selectedFund.code }} · {{ selectedFund.manager }}<template v-if="selectedFund.company"> · {{ selectedFund.company }}</template></p></div><div><label>官方净值 · {{ selectedFund.navs.at(-1)?.nav_date }}</label><strong>{{ selectedFund.navs.at(-1)?.nav.toFixed(4) }}</strong><em :class="selectedFund.navs.at(-1)?.daily_change>=0?'up':'down'">{{ pct(selectedFund.navs.at(-1)?.daily_change) }}</em><small class="source-line">{{ selectedFund.data_source || '演示数据' }}</small></div></section>
        <section v-if="selectedRealtime" class="realtime-strip"><div><label>盘中估算净值</label><strong>{{ selectedRealtime.estimated_nav.toFixed(4) }}</strong><em :class="selectedRealtime.estimated_change_pct>=0?'up':'down'">{{ pct(selectedRealtime.estimated_change_pct) }}</em></div><div><label>预计今日收益</label><strong :class="selectedRealtime.estimated_today_profit>=0?'up':'down'">{{ money(selectedRealtime.estimated_today_profit) }}</strong><small>累计估算 {{ money(selectedRealtime.estimated_total_profit) }}</small></div><div><label>估算依据</label><b>{{ selectedRealtime.method==='target_index' ? selectedRealtime.target_index_name : `${selectedRealtime.target_etf_name} ${selectedRealtime.target_etf_code}` }}</b><small>{{ pct(selectedRealtime.target_change_pct) }} × {{ (selectedRealtime.exposure_ratio*100).toFixed(0) }}% 暴露</small></div><div><label>更新时间</label><b>{{ selectedRealtime.quote_time.slice(11,19) }}</b><small>{{ selectedRealtime.quote_source }}</small></div><p>{{ selectedRealtime.disclaimer }}</p></section>
        <section class="panel chart-panel"><div class="panel-title"><div><h3>近 90 日净值轨迹</h3><p>净值曲线用于观察趋势，不代表未来收益</p></div><span>业绩基准 · {{ selectedFund.benchmark }}</span></div><div id="nav-chart"></div></section>
        <div class="two-col"><section class="panel holdings-through"><div class="panel-title"><div><h3>{{ selectedFund.target_fund ? '目标 ETF 穿透持仓' : '最新披露股票持仓' }}</h3><p>{{ selectedFund.target_fund ? '还原联接基金实际暴露的底层股票' : '基金定期报告披露口径' }}</p></div><span>披露期 {{ selectedFund.underlying_position_date || selectedFund.position_date || '—' }}</span></div><div v-if="selectedFund.target_fund" class="exposure-route"><div><small>当前基金</small><b>{{ selectedFund.name }}</b><em>{{ selectedFund.code }}</em></div><i>→</i><div class="route-target"><small>主要持有</small><b>{{ selectedFund.target_fund.name }}</b><em>{{ selectedFund.target_fund.code }} · 约 {{ (selectedFund.target_fund.exposure_ratio*100).toFixed(0) }}% 暴露</em></div></div><div class="holding-list-head" v-if="selectedFund.target_fund"><span>目标 ETF 前十大股票</span><small>权重为 ETF 内部占比</small></div><template v-if="selectedFund.target_fund"><div class="top-row" v-for="(s,i) in selectedFund.underlying_holdings" :key="s.stock_code"><i>{{ i+1 }}</i><b>{{ s.stock_name }} <small>{{ s.stock_code }}</small></b><span>{{ s.weight }}%</span></div><div v-if="!selectedFund.underlying_holdings.length" class="mini-empty">目标 ETF 持仓尚未同步，请点击右上角“同步真实数据”</div></template><template v-else><div class="top-row" v-for="(s,i) in selectedFund.top_holdings" :key="s.stock_code"><i>{{ i+1 }}</i><b>{{ s.stock_name }} <small>{{ s.stock_code }}</small></b><span>{{ s.weight }}%</span></div><div v-if="!selectedFund.top_holdings.length" class="mini-empty">最新报告未披露直接股票持仓</div></template><footer v-if="selectedFund.target_fund">007818 自身的直接股票持仓不代表主要风险暴露，因此这里优先展示目标 ETF 的穿透结果。</footer></section><section class="panel insight"><label>✦ AI 观察</label><h3>趋势仍在，节奏比方向更重要</h3><p>当前净值处于近三个月相对高位。已有盈利仓位以持有为主，若计划增配，等待波动回落并分批执行。</p><small>以上内容仅作信息辅助，不构成投资建议。</small></section></div>
      </template>

      <template v-else-if="page==='report'">
        <section class="report-cover"><div><span>DAILY / {{ report?.report_date || new Date().toISOString().slice(0,10) }}</span><h2>今天不必急着<br>证明自己的判断。</h2><p>知衡把市场信息与你的持仓放在一起，给出有条件的行动线索。</p></div><button class="primary" :disabled="generating" @click="createReport">{{ generating ? '正在分析…' : report ? '重新生成日报' : '生成今日日报' }}</button></section>
        <div v-if="report" class="report-grid"><article><span>01 · 市场</span><h3>市场发生了什么</h3><p>{{ report.market_summary }}</p></article><article><span>02 · 组合</span><h3>与你的持仓有什么关系</h3><p>{{ report.holding_impact }}</p></article><article class="accent"><span>03 · 行动</span><h3>今天可以怎么做</h3><p>{{ report.suggestion }}</p></article><article><span>04 · 风险</span><h3>需要防备什么</h3><p>{{ report.risks }}</p></article><article><span>05 · 条件</span><h3>接下来观察什么</h3><p>{{ report.watch_conditions }}</p></article><footer>生成方式：{{ report.source==='deepseek'?'DeepSeek 智能分析':'本地纪律规则' }} · 内容仅供投资研究参考</footer></div><div v-else class="empty"><span>✦</span><h3>还没有今天的观察记录</h3><p>生成日报后，系统会结合你的成本、仓位和市场强弱整理行动线索。</p></div>
      </template>

      <template v-else-if="page==='market'">
        <div class="radar-toolbar"><div class="radar-date"><i :class="market.session"></i><b>{{ market.session_label || '行情状态未知' }}</b><span>数据 {{ market.date }} {{ marketUpdateTime }} · {{ market.source || '演示数据' }}</span><small v-if="market.refresh_error">行情源暂时拥堵，当前显示最近一次成功数据</small><small v-else-if="market.is_trading">页面停留期间每 30 秒自动更新</small><small v-else>休市期间保留最后行情</small></div><button class="radar-refresh" :disabled="marketRefreshing" @click="loadMarket(true)">{{ marketRefreshing ? '刷新中…' : '立即刷新 ↻' }}</button></div><div class="index-grid"><article v-for="i in market.indices" :key="i.name"><span>{{ i.name }}</span><strong>{{ i.value.toLocaleString() }}</strong><em :class="i.change_pct>=0?'up':'down'">{{ pct(i.change_pct) }}</em><div class="mini-bars"><i v-for="n in 12" :key="n" :style="{height:(10+((n*13+i.name.length*5)%30))+'px'}"></i></div></article></div>
        <section class="panel industry-panel"><div class="panel-title"><div><h3>行业温度</h3><p>按当日涨跌排序，避免把热度误当趋势</p></div><span>弱 ← 中性 → 强</span></div><div class="industry-row" v-for="s in market.industries" :key="s.name"><b>{{ s.name }}</b><div><i :class="s.change_pct>=0?'positive':'negative'" :style="{width:Math.min(Math.abs(s.change_pct)*18,48)+'%', [s.change_pct>=0?'left':'right']:'50%'}"></i><span></span></div><em :class="s.change_pct>=0?'up':'down'">{{ pct(s.change_pct) }}</em></div></section>
        <section class="radar-note"><span>雷达提示</span><p>强势行业适合列入观察清单，不等于立即追涨。连续性、估值与组合已有暴露应一起判断。</p></section>
      </template>
    </main>

    <div class="modal-backdrop" v-if="showAdd" @click.self="showAdd=false"><form class="modal" @submit.prevent="addHolding"><div><span>新增持仓</span><button type="button" @click="showAdd=false">×</button></div><label>基金代码<div class="lookup-field"><input v-model="newHolding.fund_code" pattern="\d{6}" placeholder="例如 000001" required @blur="lookupFund"><button type="button" :disabled="searchingFund" @click="lookupFund">{{ searchingFund?'查询中':'查真实基金' }}</button></div></label><label>基金名称<input v-model="newHolding.fund_name" placeholder="输入代码后自动获取" required></label><div class="form-row"><label>持有份额<input v-model="newHolding.shares" type="number" step="0.01" min="0.01" required></label><label>成本净值<input v-model="newHolding.cost_nav" type="number" step="0.0001" min="0.0001" required></label></div><label>目标仓位 <output>{{ newHolding.target_weight }}%</output><input v-model="newHolding.target_weight" type="range" min="0" max="100"></label><button class="primary" type="submit">保存并同步净值</button></form></div>
    <div class="modal-backdrop" v-if="editingHolding" @click.self="editingHolding=null"><form class="modal holding-edit-modal" @submit.prevent="saveHoldingEdit"><div><span>编辑持仓</span><button type="button" @click="editingHolding=null">×</button></div><section class="edit-fund-identity"><span>{{ editingHolding.code }}</span><b>{{ editingHolding.name }}</b><small>修改后将重新计算市值、收益和实际仓位</small></section><div class="form-row"><label>持有份额<input v-model="editingHolding.shares" type="number" step="0.01" min="0.01" required></label><label>持仓成本净值<input v-model="editingHolding.cost_nav" type="number" step="0.0001" min="0.0001" required></label></div><label>目标仓位 <output>{{ editingHolding.target_weight }}%</output><input v-model="editingHolding.target_weight" type="range" min="0" max="100" step="1"></label><div class="modal-actions"><button class="cancel-edit" type="button" @click="editingHolding=null">取消</button><button class="primary" type="submit" :disabled="savingEdit">{{ savingEdit ? '保存中…' : '保存修改' }}</button></div></form></div>
  </div>
</template>
