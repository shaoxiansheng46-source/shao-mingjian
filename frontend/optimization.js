/* Phase 6B real-structure optimization workbench.
 * It consumes only /api/v1.6 and never touches the legacy synthetic task state. */
(() => {
  const state = { task: null, result: null, view: 'all', filter: '', sort: 'loss', selected: null, stale: false, timer: null, provider: null };
  const $ = (id) => document.getElementById(id);
  const api = async (url, options = {}) => {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail?.message || data.detail || data.error || `HTTP ${response.status}`);
    return data;
  };
  const esc = (value) => String(value ?? '—').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (value, digits = 4) => value == null || !Number.isFinite(Number(value)) ? '未计算' : Number(value).toFixed(digits);
  const input = (id) => $(id)?.value ?? '';
  const bool = (id) => Boolean($(id)?.checked);
  const array = (id) => input(id).split(',').map((item) => Number(item.trim())).filter((item) => Number.isFinite(item));
  const rms = (values) => values.length ? Math.sqrt(values.reduce((sum, value) => sum + value * value, 0) / values.length) : 0;
  const mmToM = (value) => Number(value) * 1e-3;

  function notice(message, error = false) {
    const banner = $('optimizationBanner');
    if (!message) { banner.classList.add('hidden'); banner.textContent = ''; return; }
    banner.textContent = message; banner.classList.toggle('banner-error', error); banner.classList.remove('hidden');
  }

  function markStale() {
    if (!state.result && !state.task) return;
    state.stale = true;
    $('optimizationStaleNotice').classList.remove('hidden');
    $('optimizationExportJson').disabled = true;
    $('optimizationExportCsv').disabled = true;
    if (state.result) { state.result = null; renderResult(); }
  }

  function rangeVariable(onId, minId, maxId, integer = false) {
    const min = Number(input(minId)); const max = Number(input(maxId));
    return bool(onId) ? { optimize: true, min, max } : { optimize: false, value: integer ? min : min };
  }

  function realRange(id, defaultStep) {
    const values = array(id);
    if (values.length < 2) throw new Error(`${id} 需要最小值,最大值,步进`);
    return { optimize: true, min: mmToM(values[0]), max: mmToM(values[1]), step: mmToM(values[2] ?? defaultStep) };
  }

  function readPayload() {
    const times = array('optimizationTimes');
    const ip = array('optimizationIpWave'); const is = array('optimizationIsWave');
    const vp = array('optimizationVpWave'); const vs = array('optimizationVsWave');
    if (times.length < 4 || [ip, is, vp, vs].some((wave) => wave.length !== times.length)) throw new Error('四组显式波形必须与时间采样点长度一致，且至少有 4 个点。');
    const frequency = Number(input('optimizationFrequency'));
    const wave = (data) => ({ data, time: times, frequency_hz: frequency });
    const voltage = (data) => ({ waveform: { data, time: times } });
    const layoutMode = input('optimizationLayout');
    const variables = {
      Np: rangeVariable('optimizationNpOn', 'optimizationNpMin', 'optimizationNpMax', true),
      Ns: rangeVariable('optimizationNsOn', 'optimizationNsMin', 'optimizationNsMax', true),
      P1: rangeVariable('optimizationP1On', 'optimizationP1Min', 'optimizationP1Max', true),
      layout: bool('optimizationLayoutOn') ? { optimize: true, choices: ['PS', 'PSP'] } : { optimize: false, value: layoutMode },
      interwinding_gap_m: realRange('optimizationGapRange', 0.05),
      core_clearance_m: realRange('optimizationClearanceRange', 0.05),
    };
    return {
      data_source: 'external_database',
      fixed: {
        core: { shape_name: input('optimizationCore'), material_name: input('optimizationMaterial'), bobbin_name: input('optimizationBobbin') },
        wire: { primary_name: input('optimizationWire'), secondary_name: input('optimizationWire') },
      },
      operating_point: {
        point_id: `phase6b-${Date.now()}`, voltage_primary_v: Number(input('optimizationV1')), voltage_secondary_v: Number(input('optimizationV2')),
        power_w: Number(input('optimizationPower')), frequency_hz: frequency, ambient_c: Number(input('optimizationAmbient')),
        topology: input('optimizationTopology'), bridge_duty: 0.5, reference_side: 'primary',
        currents_rms_a: { Primary: rms(ip), Secondary: rms(is) * (is[0] < 0 ? -1 : 1) },
        current_waveforms: { Primary: wave(ip), Secondary: wave(is) },
        voltage_waveforms: { Primary: voltage(vp), Secondary: voltage(vs) },
      },
      variables,
      constraints: {
        turns_ratio_target: Number(input('optimizationRatio')), turns_ratio_tolerance: Number(input('optimizationRatioTol')),
        bmax_max_t: Number(input('optimizationBmax')), lm_min_h: Number(input('optimizationLmMin')),
        lm_max_h: Number(input('optimizationLmMax')), leakage_target_h: input('optimizationLeakage') ? Number(input('optimizationLeakage')) : null,
        leakage_relative_tolerance: Number(input('optimizationLeakageTol')),
      },
      optimizer: {
        population_size: Number(input('optimizationPopulation')), generations: Number(input('optimizationGenerations')),
        max_evaluations: Number(input('optimizationMaxEvaluations')), seed: Number(input('optimizationSeed')), timeout_s: 900,
      },
    };
  }

  function renderProvider(status) {
    state.provider = status;
    const provider = status?.provider || {};
    const available = Boolean(provider.available);
    $('optimizationProviderStrip').innerHTML = `<span class="status-dot ${available ? '' : 'status-dot-off'}"></span><strong>${available ? `真实 Provider 可用 · PyOpenMagnetics ${esc(provider.third_party_version || '版本未知')}` : '真实 Provider 不可用 · 优化任务不会回退 synthetic'}</strong>`;
    $('optimizationRunBtn').disabled = !available;
    if (!available) notice('OpenMagnetics Provider 当前不可用。请用隔离运行环境启动服务，或先完成单候选真实计算环境配置。', true);
  }

  async function loadProvider() {
    try { renderProvider(await api('/api/v1.6/status')); } catch (error) { notice(`无法读取真实优化服务：${error.message}`, true); }
  }

  function updateProgress(task) {
    state.task = task;
    const pct = Math.max(0, Math.min(100, Number(task.progress || 0) * 100));
    $('optimizationProgressBar').style.width = `${pct}%`;
    $('optimizationProgressPct').textContent = `${Math.round(pct)}%`;
    $('optimizationProgressText').textContent = task.status === 'running' ? '真实物理计算中' : task.status;
    $('optimizationSolverLabel').textContent = `${task.mode || 'real_structure_optimization'} · ${task.status}`;
    $('optimizationGeneration').textContent = task.generation ?? '—';
    $('optimizationEvaluated').textContent = task.evaluated_count ?? '—';
    $('optimizationUnique').textContent = `唯一 ${task.unique_count ?? '—'}`;
    $('optimizationPhysical').textContent = task.physical_success_count ?? '—';
    $('optimizationCache').textContent = `缓存 ${task.cache_hit_count ?? '—'}`;
    $('optimizationGeometry').textContent = task.geometry_rejected_count ?? '—';
    $('optimizationFeasible').textContent = `可行 ${task.research_feasible_count ?? '—'}`;
    $('optimizationParetoCount').textContent = task.pareto_count ?? '—';
    $('optimizationCancelBtn').classList.toggle('hidden', !['pending', 'running', 'cancelling'].includes(task.status));
    if (task.error) notice(task.error, true);
  }

  async function poll() {
    if (!state.task?.id) return;
    try {
      const task = await api(`/api/v1.6/optimizations/${state.task.id}/progress`);
      updateProgress(task);
      if (['completed', 'failed', 'cancelled'].includes(task.status)) {
        clearInterval(state.timer); state.timer = null;
        if (task.status === 'completed') {
          const finalTask = await api(`/api/v1.6/optimizations/${state.task.id}?include_result=true`);
          state.result = finalTask.result; state.stale = false; $('optimizationStaleNotice').classList.add('hidden');
          $('optimizationExportJson').disabled = false; $('optimizationExportCsv').disabled = false; renderResult();
        }
      }
    } catch (error) { clearInterval(state.timer); state.timer = null; notice(`优化进度读取失败：${error.message}`, true); }
  }

  async function runOptimization() {
    try {
      notice(''); const payload = readPayload();
      state.result = null; state.selected = null; state.stale = false; $('optimizationStaleNotice').classList.add('hidden'); renderResult();
      const task = await api('/api/v1.6/optimizations', { method: 'POST', body: JSON.stringify(payload) });
      updateProgress(task); clearInterval(state.timer); state.timer = setInterval(poll, 700); poll();
    } catch (error) { notice(error.message, true); }
  }

  async function cancelOptimization() {
    if (!state.task?.id) return;
    try { updateProgress(await api(`/api/v1.6/optimizations/${state.task.id}/cancel`, { method: 'POST', body: '{}' })); } catch (error) { notice(`取消失败：${error.message}`, true); }
  }

  function records() {
    if (!state.result) return [];
    let items = state.view === 'feasible' ? state.result.all_unique_candidates.filter((item) => item.research_feasible) : state.view === 'pareto' ? (state.result.pareto || []) : (state.result.all_unique_candidates || []);
    const needle = state.filter.trim().toLowerCase();
    if (needle) items = items.filter((item) => `${item.candidate_hash || ''} ${item.variables?.layout || ''} ${item.status || ''}`.toLowerCase().includes(needle));
    const metric = (item, key, index = null) => index == null ? Number(item.metrics?.[key] ?? Number.POSITIVE_INFINITY) : Number(item.objectives?.[index] ?? Number.POSITIVE_INFINITY);
    return [...items].sort((left, right) => {
      if (state.sort === 'volume') return metric(left, '', 1) - metric(right, '', 1);
      if (state.sort === 'bmax') return metric(left, 'bmax_t') - metric(right, 'bmax_t');
      if (state.sort === 'np') return Number(left.variables?.Np ?? Number.POSITIVE_INFINITY) - Number(right.variables?.Np ?? Number.POSITIVE_INFINITY);
      if (state.sort === 'layout') return String(left.variables?.layout || '').localeCompare(String(right.variables?.layout || ''));
      return metric(left, '', 0) - metric(right, '', 0);
    });
  }

  function statusTag(item) {
    if (item.research_feasible) return '<span class="small-tag">研究性可行</span>';
    if (item.geometry_feasible === false) return '<span class="status-pill">几何淘汰</span>';
    if (item.status === 'provider_unavailable') return '<span class="status-pill">Provider 不可用</span>';
    if (item.status === 'physical_failed') return '<span class="status-pill">物理失败</span>';
    return '<span class="status-pill">未满足约束</span>';
  }

  function renderTable() {
    const items = records(); const body = $('optimizationCandidateTable').querySelector('tbody');
    $('allCandidateTabCount').textContent = state.result?.all_unique_candidates?.length || 0;
    $('feasibleTabCount').textContent = state.result?.all_unique_candidates?.filter((item) => item.research_feasible).length || 0;
    $('paretoTabCount').textContent = state.result?.pareto?.length || 0;
    $('optimizationEmpty').classList.toggle('hidden', items.length > 0); $('optimizationCandidateTable').classList.toggle('hidden', items.length === 0);
    body.innerHTML = items.map((item) => { const v = item.variables || {}; const m = item.metrics || {}; const f = item.objectives || []; const selected = item.candidate_hash === state.selected?.candidate_hash; return `<tr data-candidate="${esc(item.candidate_hash)}" class="${selected ? 'selected' : ''}"><td><code>${esc(item.candidate_hash?.slice(0, 10))}</code></td><td>${esc(v.layout)}</td><td>${esc(v.Np)}/${esc(v.Ns)}</td><td>${esc(v.P1)}/${esc(v.P2)}</td><td>${num(f[0], 5)}</td><td>${num(f[1] * 1e9, 2)}</td><td>${num(m.bmax_t * 1e3, 2)} mT</td><td>${num(m.lm_h * 1e6, 2)} μH</td><td>${num(m.leakage_h * 1e6, 3)}</td><td>${statusTag(item)}</td><td>${item.pareto_rank === 0 ? '<span class="small-tag">0</span>' : '—'}</td></tr>`; }).join('');
    body.querySelectorAll('[data-candidate]').forEach((row) => row.addEventListener('click', () => selectCandidate(row.dataset.candidate)));
  }

  function renderChart() {
    const svg = $('optimizationParetoSvg'); const items = (state.result?.all_unique_candidates || []).filter((item) => item.research_feasible && Number.isFinite(item.objectives?.[0]) && Number.isFinite(item.objectives?.[1]));
    const width = 760; const height = 330; const pad = { left: 58, right: 22, top: 18, bottom: 42 }; const innerW = width - pad.left - pad.right; const innerH = height - pad.top - pad.bottom;
    if (!items.length) { svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle">尚无研究性可行候选，无法绘制 Pareto 图</text>`; $('optimizationChartNote').textContent = '只有实际完成物理计算且满足研究约束的候选才进入图表。'; return; }
    const xs = items.map((item) => item.objectives[1]); const ys = items.map((item) => item.objectives[0]); const xmin = Math.min(...xs); const xmax = Math.max(...xs); const ymin = Math.min(...ys); const ymax = Math.max(...ys); const sx = (value) => pad.left + ((value - xmin) / Math.max(xmax - xmin, 1e-30)) * innerW; const sy = (value) => pad.top + innerH - ((value - ymin) / Math.max(ymax - ymin, 1e-30)) * innerH;
    const grid = [0, .5, 1].map((fraction) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${pad.top + fraction * innerH}" y2="${pad.top + fraction * innerH}"/><line class="grid-line" x1="${pad.left + fraction * innerW}" x2="${pad.left + fraction * innerW}" y1="${pad.top}" y2="${pad.top + innerH}"/>`).join('');
    const points = items.map((item) => `<circle class="point ${item.pareto_rank === 0 ? 'pareto' : ''} ${item.candidate_hash === state.selected?.candidate_hash ? 'selected' : ''}" cx="${sx(item.objectives[1])}" cy="${sy(item.objectives[0])}" r="${item.pareto_rank === 0 ? 7 : 5}" data-candidate="${esc(item.candidate_hash)}"><title>${esc(item.candidate_hash)} · ${num(item.objectives[0], 5)} W · ${num(item.objectives[1], 8)} m³</title></circle>`).join('');
    svg.innerHTML = `${grid}<line class="axis-line" x1="${pad.left}" x2="${pad.left}" y1="${pad.top}" y2="${pad.top + innerH}"/><line class="axis-line" x1="${pad.left}" x2="${width - pad.right}" y1="${pad.top + innerH}" y2="${pad.top + innerH}"/><text x="${width / 2}" y="${height - 8}" text-anchor="middle">绕组包络体积 [m³] · ${num(xmin, 8)}–${num(xmax, 8)}</text><text x="16" y="${height / 2}" transform="rotate(-90 16 ${height / 2})" text-anchor="middle">总电磁损耗 [W] · ${num(ymin, 5)}–${num(ymax, 5)}</text>${points}`;
    svg.querySelectorAll('[data-candidate]').forEach((point) => point.addEventListener('click', () => selectCandidate(point.dataset.candidate)));
    $('optimizationChartNote').textContent = `${items.length} 个研究性可行候选；深色点为非支配候选。完全重合点仍按实际候选记录保留，但不会虚构额外目标差异。`;
  }

  function structureSvg(layout) {
    const blocks = layout?.blocks || []; if (!blocks.length) return '<div class="optimization-detail-note">没有可显示的几何快照。</div>';
    const minX = Math.min(...blocks.map((block) => block.radial_start_m)); const maxX = Math.max(...blocks.map((block) => block.radial_end_m)); const minY = Math.min(...blocks.map((block) => block.axial_start_m)); const maxY = Math.max(...blocks.map((block) => block.axial_end_m)); const scaleX = 390 / Math.max(maxX - minX, 1e-12); const scaleY = 100 / Math.max(maxY - minY, 1e-12);
    const rects = blocks.map((block, index) => { const x = 55 + (block.radial_start_m - minX) * scaleX; const width = Math.max(8, (block.radial_end_m - block.radial_start_m) * scaleX); const y = 28 + (block.axial_start_m - minY) * scaleY; const height = Math.max(20, (block.axial_end_m - block.axial_start_m) * scaleY); const color = block.role?.toLowerCase() === 'secondary' ? '#2b9b95' : '#326ea8'; return `<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${color}" opacity=".88"><title>${esc(block.name)} · ${block.turns}T · ${num(block.mean_turn_length_m * 1e3, 2)} mm MLT</title></rect><text x="${x + width / 2}" y="${y - 6}" text-anchor="middle">${esc(block.name)} ${block.turns}T</text>`; }).join('');
    return `<svg class="optimization-structure-svg" viewBox="0 0 520 180" role="img" aria-label="当前候选的实际绕组几何"><rect x="42" y="16" width="442" height="138" fill="#eef4f8" stroke="#7e9bb1" stroke-width="2"/><rect x="55" y="28" width="390" height="100" fill="#fff" stroke="#aac0d1"/>${rects}<text x="260" y="170" text-anchor="middle">窗口 ${num(layout.core?.window_width_m * 1e3, 1)} × ${num(layout.core?.window_height_m * 1e3, 1)} mm · ${esc(layout.template?.template_id)}</text></svg>`;
  }

  function selectCandidate(hash) {
    const item = (state.result?.all_unique_candidates || []).find((candidate) => candidate.candidate_hash === hash) || (state.result?.pareto || []).find((candidate) => candidate.candidate_hash === hash);
    if (!item) return; state.selected = item; renderTable(); renderChart();
    const v = item.variables || {}; const m = item.metrics || {}; const f = item.objectives || [];
    $('optimizationSelectedLabel').textContent = `${v.layout || '—'} · ${v.Np || '—'}/${v.Ns || '—'} · ${item.candidate_hash?.slice(0, 12)}`;
    $('optimizationSelectedContent').innerHTML = `<div class="optimization-detail"><div class="optimization-detail-head"><div><strong>${num(f[0], 5)} W</strong><span>${esc(item.status)} · ${statusTag(item)}</span></div><div><strong>${num(f[1] * 1e9, 2)} mm³</strong><span>绕组包络体积</span></div></div><div class="optimization-detail-grid"><div class="optimization-detail-kpi"><small>Np / Ns</small><strong>${esc(v.Np)} / ${esc(v.Ns)}</strong></div><div class="optimization-detail-kpi"><small>P1 / P2</small><strong>${esc(v.P1)} / ${esc(v.P2)}</strong></div><div class="optimization-detail-kpi"><small>Bmax</small><strong>${num(m.bmax_t * 1e3, 2)} mT</strong></div><div class="optimization-detail-kpi"><small>Lm</small><strong>${num(m.lm_h * 1e6, 2)} μH</strong></div><div class="optimization-detail-kpi"><small>Pcore</small><strong>${num(m.pcore_w, 5)} W</strong></div><div class="optimization-detail-kpi"><small>Pcu complete</small><strong>${num(m.pcu_complete_w, 5)} W</strong></div></div>${structureSvg(item.layout_snapshot)}<div class="optimization-detail-note">工程状态：UNKNOWN。漏感属于研究性模型；热模型未接入，未生成温升或热点结论。候选来源与完整计算快照保存在任务结果中。</div></div>`;
    updateComparisonOptions();
  }

  function updateComparisonOptions() {
    const items = state.result?.all_unique_candidates || []; const options = items.map((item) => `<option value="${esc(item.candidate_hash)}">${esc(item.candidate_hash?.slice(0, 12))} · ${esc(item.variables?.layout)} · ${esc(item.status)}</option>`).join('');
    $('optimizationCompareA').innerHTML = options; $('optimizationCompareB').innerHTML = options;
    if (state.selected) $('optimizationCompareA').value = state.selected.candidate_hash;
    if (items.length > 1) $('optimizationCompareB').value = items.find((item) => item.candidate_hash !== state.selected?.candidate_hash)?.candidate_hash || items[1].candidate_hash;
    renderComparison();
  }

  function renderComparison() {
    const items = state.result?.all_unique_candidates || []; const a = items.find((item) => item.candidate_hash === $('optimizationCompareA').value); const b = items.find((item) => item.candidate_hash === $('optimizationCompareB').value); if (!a || !b) { $('optimizationComparison').textContent = '请先完成优化并选择两个候选。'; return; }
    const row = (label, left, right) => `<tr><th>${label}</th><td>${left}</td><td>${right}</td></tr>`; const metric = (item, key, digits = 5) => num(item.metrics?.[key], digits); const obj = (item, index, digits = 7) => num(item.objectives?.[index], digits);
    $('optimizationComparison').innerHTML = `<div class="table-scroll"><table class="optimization-comparison-table"><thead><tr><th>指标</th><th>A · ${esc(a.candidate_hash?.slice(0, 10))}</th><th>B · ${esc(b.candidate_hash?.slice(0, 10))}</th></tr></thead><tbody>${row('结构', esc(a.variables?.layout), esc(b.variables?.layout))}${row('Np / Ns', `${esc(a.variables?.Np)} / ${esc(a.variables?.Ns)}`, `${esc(b.variables?.Np)} / ${esc(b.variables?.Ns)}`)}${row('P1 / P2', `${esc(a.variables?.P1)} / ${esc(a.variables?.P2)}`, `${esc(b.variables?.P1)} / ${esc(b.variables?.P2)}`)}${row('总电磁损耗', `${obj(a, 0)} W`, `${obj(b, 0)} W`)}${row('绕组包络体积', `${obj(a, 1)} m³`, `${obj(b, 1)} m³`)}${row('Bmax', `${metric(a, 'bmax_t', 5)} T`, `${metric(b, 'bmax_t', 5)} T`)}${row('Lm', `${metric(a, 'lm_h', 7)} H`, `${metric(b, 'lm_h', 7)} H`)}${row('漏感', `${metric(a, 'leakage_h', 7)} H`, `${metric(b, 'leakage_h', 7)} H`)}${row('状态', statusTag(a), statusTag(b))}</tbody></table></div>`;
  }

  function renderResult() {
    renderTable(); renderChart();
    if (!state.result) { $('optimizationSelectedLabel').textContent = '点击表格或图上的候选查看详情'; $('optimizationSelectedContent').className = 'optimization-detail-empty'; $('optimizationSelectedContent').textContent = '尚未选择方案。'; $('optimizationComparison').textContent = '请先完成优化并选择两个候选。'; return; }
    if (!state.selected && state.result.pareto?.length) selectCandidate(state.result.pareto[0].candidate_hash);
    else if (state.selected) selectCandidate(state.selected.candidate_hash);
  }

  function init() {
    $('optimizationStatusBtn')?.addEventListener('click', loadProvider); $('optimizationRunBtn')?.addEventListener('click', runOptimization); $('optimizationCancelBtn')?.addEventListener('click', cancelOptimization);
    $('optimizationExportJson')?.addEventListener('click', () => { if (state.task?.id && !state.stale) window.location.href = `/api/v1.6/optimizations/${state.task.id}/report?format=json`; });
    $('optimizationExportCsv')?.addEventListener('click', () => { if (state.task?.id && !state.stale) window.location.href = `/api/v1.6/optimizations/${state.task.id}/report?format=csv`; });
    document.querySelectorAll('.optimization-tab').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.optimization-tab').forEach((item) => item.classList.remove('active')); tab.classList.add('active'); state.view = tab.dataset.resultView; renderTable(); }));
    $('optimizationCandidateFilter')?.addEventListener('input', (event) => { state.filter = event.target.value; renderTable(); });
    $('optimizationCandidateSort')?.addEventListener('change', (event) => { state.sort = event.target.value; renderTable(); });
    $('optimizationCompareA')?.addEventListener('change', renderComparison); $('optimizationCompareB')?.addEventListener('change', renderComparison);
    document.querySelectorAll('#optimizationView input,#optimizationView select').forEach((element) => element.addEventListener('input', markStale));
    loadProvider();
  }
  document.addEventListener('DOMContentLoaded', init);
})();
