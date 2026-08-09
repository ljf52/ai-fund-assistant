const today = new Date().toISOString().slice(0, 10)
const quoteTime = `${today}T14:35:20+08:00`

const holding = {
  id: 1, code: '007818', name: '国泰中证全指通信设备ETF联接C', category: '指数型', risk_level: '中高风险',
  shares: 1000, cost_nav: 3.5, target_weight: 60, nav: 3.6279, daily_change: 1.18,
  market_value: 3627.9, cost_value: 3500, profit: 127.9, return_pct: 3.65, weight: 100, today_profit: 42.1,
}

const underlying = [
  ['300502', '新易盛', 15.6], ['300308', '中际旭创', 14.61], ['601138', '工业富联', 9.12],
  ['600487', '亨通光电', 6.89], ['300394', '天孚通信', 6.33], ['600522', '中天科技', 5.3],
  ['002281', '光迅科技', 3.98], ['000063', '中兴通讯', 3.73], ['300136', '信维通信', 3.69],
  ['600105', '永鼎股份', 2.52],
].map(([stock_code, stock_name, weight], index) => ({ stock_code, stock_name, weight, shares_10k: 1000 - index * 63, market_value_10k: 900000 - index * 70000, report_date: '2026-06-30', data_source: '公开披露示例' }))

const navs = Array.from({ length: 90 }, (_, index) => {
  const date = new Date()
  date.setDate(date.getDate() - (89 - index))
  const nav = 3.16 + index * 0.0052 + Math.sin(index / 5) * 0.045
  return { nav_date: date.toISOString().slice(0, 10), nav: Number(nav.toFixed(4)), daily_change: Number((Math.cos(index / 5) * 0.42).toFixed(2)), data_source: '演示数据' }
})
navs[navs.length - 1].nav = holding.nav

const dataStatus = {
  mode: 'demo',
  funds: { real: 0, total: 1, data_date: today, updated_at: quoteTime },
  market: { data_date: today, updated_at: quoteTime },
  latest_sync: null,
  source: 'GitHub Pages 演示数据',
}

const dashboard = {
  total_assets: holding.market_value, today_profit: holding.today_profit, total_profit: holding.profit,
  total_return_pct: holding.return_pct,
  ai_suggestion: '演示组合集中于通信设备主题，观察行业连续性，避免仅因单日上涨追高。',
  holdings: [holding], data_status: dataStatus,
}

const realtimeItem = {
  holding_id: 1, supported: true, fund_code: holding.code, official_nav: holding.nav, official_nav_date: today,
  estimated_nav: 3.6684, estimated_change_pct: 1.12, estimated_today_profit: 40.5,
  estimated_market_value: 3668.4, estimated_total_profit: 168.4, estimated_total_return_pct: 4.81,
  target_etf_code: '515880', target_etf_name: '通信ETF', target_index_code: '931160',
  target_index_name: '中证全指通信设备指数', target_change_pct: 1.23, exposure_ratio: 0.91,
  quote_time: quoteTime, quote_source: '演示行情', method: 'target_etf',
  disclaimer: '在线演示数据仅用于展示界面，不代表真实基金净值或收益。',
}

const prediction = {
  supported: true, fund_code: holding.code, target_code: '515880', target_name: '通信ETF',
  horizon: '下一交易日', as_of_date: today, up_probability: 0.6009, down_probability: 0.3991,
  expected_return_pct: 0.67, lower_bound_pct: -3.24, upper_bound_pct: 4.41,
  signal: '方向不明', confidence: '低', qualified: false,
  status_message: '滚动回测尚未超过简单基准，本次概率仅供模型研究。', exposure_ratio: 0.91,
  factors: [
    { name: '5日均线距离', direction: 'positive', value: '+4.00%' },
    { name: '60日趋势距离', direction: 'positive', value: '-13.74%' },
    { name: '近10日动量', direction: 'positive', value: '+2.17%' },
    { name: '短期波动率', direction: 'negative', value: '+3.87%' },
  ],
  validation: { accuracy: 0.5302, baseline_accuracy: 0.5357, auc: 0.5088, brier: 0.2567, validation_samples: 728, training_samples: 1616, method: '扩展窗口滚动验证（4折）' },
  model_name: 'xgboost-direction-v1', training_basis: 'target_etf', data_source: '在线演示历史行情', source_warning: null, generated_at: quoteTime,
  disclaimer: '概率来自历史行情模型，不保证未来结果；区间为近期历史分布估计，不是收益承诺。',
}

const report = {
  report_date: today,
  market_summary: '宽基指数小幅上涨，通信设备、电子等成长行业表现相对活跃。',
  holding_impact: '演示组合主要暴露于通信设备行业，板块上涨对当日估算收益形成正贡献。',
  suggestion: '保持观察，不因单日涨幅追高；若计划增加仓位，应设置价格条件并分批执行。',
  risks: '组合行业集中度较高，需留意成长风格回撤和目标 ETF 跟踪误差。',
  watch_conditions: '观察通信设备指数连续三日强弱、成交额变化及单一行业仓位上限。',
  source: 'rules',
}

const market = {
  date: today, source: 'GitHub Pages 演示行情', updated_at: quoteTime, session: 'closed', session_label: '演示数据', is_trading: false,
  indices: [
    { name: '上证指数', value: 3940.04, change_pct: 1.02 }, { name: '深证成指', value: 14311.01, change_pct: 1.42 },
    { name: '创业板指', value: 3563.12, change_pct: 1.35 }, { name: '沪深300', value: 4694.44, change_pct: 0.93 },
  ],
  industries: [
    ['医药生物', 4.77], ['电子', 3.49], ['建筑材料', 3.27], ['有色金属', 3.18], ['机械设备', 2.07], ['国防军工', 1.48],
    ['商贸零售', -0.39], ['房地产', -0.49], ['银行', -0.56], ['交通运输', -0.57], ['计算机', -0.6], ['家用电器', -0.95],
  ].map(([name, change_pct]) => ({ name, value: 0, change_pct })),
}

const fund = {
  code: holding.code, name: holding.name, category: holding.category, risk_level: holding.risk_level,
  manager: '示例基金经理', benchmark: '中证全指通信设备指数收益率', company: '示例基金公司', data_source: 'GitHub Pages 演示数据',
  navs, top_holdings: [], position_date: null,
  target_fund: { code: '515880', name: '通信ETF', exposure_ratio: 0.91, source: '演示映射' },
  underlying_holdings: underlying, underlying_position_date: '2026-06-30',
}

function clone(value) { return JSON.parse(JSON.stringify(value)) }

export async function demoRequest(path, options = {}) {
  const route = path.split('?')[0]
  if (route === '/dashboard') return clone(dashboard)
  if (route === '/holdings') return clone([holding])
  if (route === '/market') return clone(market)
  if (route === '/reports/latest' || route === '/reports/generate') return clone(report)
  if (route === '/realtime/holdings') return clone({ items: [realtimeItem], summary: { supported: true, total: 1, estimated_today_profit: realtimeItem.estimated_today_profit, estimated_market_value: realtimeItem.estimated_market_value, quote_time: quoteTime } })
  if (route === `/realtime/funds/${holding.code}`) return clone(realtimeItem)
  if (route === `/predictions/funds/${holding.code}`) return clone(prediction)
  if (route === `/funds/${holding.code}`) return clone(fund)
  if (route === '/search/funds') return clone([{ code: holding.code, name: holding.name, category: holding.category, latest_nav: holding.nav, nav_date: today }])
  if (route === '/data/sync') return { status: 'success', results: [], errors: [], finished_at: quoteTime }
  if (route.startsWith('/holdings/') || (route === '/holdings' && options.method === 'POST')) return { id: 1, demo: true }
  throw new Error('在线演示版不提供此操作')
}
