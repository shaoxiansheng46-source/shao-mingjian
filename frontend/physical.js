/* Phase 5D physical workbench.  It is intentionally separate from app.js so
 * the legacy synthetic Demo and NSGA-II flow remain unchanged. */
(() => {
  const physical = { task: null, result: null, stale: false, timer: null, provider: null };
  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
  const number = (id) => Number(byId(id).value);
  const array = (id) => byId(id).value.split(",").map((item) => Number(item.trim())).filter((item) => Number.isFinite(item));
  const fmt = (value, digits = 4) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "未计算";
  const metric = (label, value, unit, note = "") => `<div class="physical-metric"><small>${esc(label)}</small><strong>${esc(value)}</strong><span>${esc(unit)}${note ? ` · ${esc(note)}` : ""}</span></div>`;

  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    return data;
  }

  function banner(message, kind = "error") {
    const el = byId("physicalBanner");
    el.textContent = message;
    el.className = `banner ${kind === "ok" ? "ok" : ""}`;
    el.classList.remove("hidden");
  }

  function invalidate() {
    if (!physical.result) return;
    physical.stale = true;
    byId("physicalStaleNotice").classList.remove("hidden");
    byId("physicalResultContent").classList.add("hidden");
    byId("physicalResultEmpty").textContent = "输入已变更，旧结果已失效。请重新运行真实物理计算。";
    byId("physicalResultEmpty").classList.remove("hidden");
    byId("physicalExportJson").disabled = true;
  }

  function sourceDefaults() {
    const external = byId("physicalSource").value === "external_database";
    byId("physicalCore").value = external ? "ETD 54/28/19" : "DEMO_CORE_XL";
    byId("physicalMaterial").value = external ? "3C95" : "DEMO_FERRITE_A";
    byId("physicalBobbin").value = external ? "Bobbin ETD 54" : "DEMO_CORE_XL-synthetic-bobbin";
    byId("physicalPrimaryWire").value = external ? "Litz 1000x0.02 - Grade 1 - Double Served" : "DEMO_LITZ_8000x0p1";
    byId("physicalSecondaryWire").value = byId("physicalPrimaryWire").value;
  }

  function buildPayload(geometryOnly = false) {
    const external = byId("physicalSource").value === "external_database";
    const times = array("physicalTimes");
    const currentPrimary = array("physicalIpWave");
    const currentSecondary = array("physicalIsWave");
    const voltagePrimary = array("physicalVpWave");
    const voltageSecondary = array("physicalVsWave");
    const waveform = (data) => ({ frequency_hz: number("physicalFrequency"), time_s: times, data });
    const primarySegments = byId("physicalLayout").value === "PSP" ? [number("physicalP1"), number("physicalP2")] : null;
    return {
      data_source: external ? "external_database" : "demo_fixture",
      layout: byId("physicalLayout").value,
      primary_turns: number("physicalNp"),
      secondary_turns: number("physicalNs"),
      primary_segments: primarySegments,
      core: external ? { shape_name: byId("physicalCore").value.trim(), material_name: byId("physicalMaterial").value.trim(), bobbin_name: byId("physicalBobbin").value.trim(), gap_mm: number("physicalGap") } : { core_id: byId("physicalCore").value.trim(), gap_mm: number("physicalGap") },
      wire: { primary_name: byId("physicalPrimaryWire").value.trim(), secondary_name: byId("physicalSecondaryWire").value.trim() },
      geometry: { main_insulation_mm: number("physicalInsulation"), winding_to_core_clearance_mm: number("physicalClearance"), end_margin_mm: number("physicalEndMargin") },
      design_requirements: { magnetizing_inductance_h: number("physicalLm") * 1e-6 },
      operating_point: {
        point_id: "web-nominal",
        voltage_primary_v: number("physicalV1"), voltage_secondary_v: number("physicalV2"), power_w: number("physicalPower"), frequency_hz: number("physicalFrequency"), ambient_c: number("physicalAmbient"), topology: byId("physicalTopology").value.trim() || "DAB_SPS", bridge_duty: 0.5, reference_side: "primary",
        currents_rms_a: geometryOnly ? {} : { Primary: number("physicalIp"), Secondary: number("physicalIs") },
        current_waveforms: geometryOnly ? {} : { Primary: waveform(currentPrimary), Secondary: waveform(currentSecondary) },
        voltage_waveforms: geometryOnly ? {} : { Primary: waveform(voltagePrimary), Secondary: waveform(voltageSecondary) },
      },
      include_openmagnetics: geometryOnly ? false : byId("physicalIncludeOpen").checked,
      seed: 20261103,
    };
  }

  function validateLocal(payload) {
    const errors = [];
    if (!Number.isInteger(payload.primary_turns) || payload.primary_turns < 1) errors.push("原边总匝数必须是正整数。");
    if (!Number.isInteger(payload.secondary_turns) || payload.secondary_turns < 1) errors.push("副边总匝数必须是正整数。");
    if (payload.layout === "PSP" && payload.primary_segments[0] + payload.primary_segments[1] !== payload.primary_turns) errors.push("PSP 必须满足 P1 + P2 = 原边总匝数。");
    const op = payload.operating_point;
    if (!Number.isFinite(op.frequency_hz) || op.frequency_hz <= 0) errors.push("工作频率必须为正数。");
    if (!Number.isFinite(op.voltage_primary_v) || !Number.isFinite(op.voltage_secondary_v)) errors.push("绕组端电压必须为有效数值。");
    if (!payload.operating_point.current_waveforms.Primary && !payload.operating_point.current_waveforms.Secondary) return errors;
    const lengths = ["Primary", "Secondary"].map((name) => [op.current_waveforms[name]?.data?.length, op.voltage_waveforms[name]?.data?.length, op.current_waveforms[name]?.time_s?.length]);
    if (lengths.some((items) => items.some((value) => value !== lengths[0][0]))) errors.push("四组波形与时间采样点数量必须一致。");
    return errors;
  }

  function renderStatus(status) {
    physical.provider = status.provider;
    const available = !!status.provider?.available;
    const counts = status.provider?.database_counts;
    byId("physicalStatusStrip").innerHTML = `<span class="status-dot ${available ? "" : "offline"}"></span><strong>${available ? "OpenMagnetics Provider 已就绪" : "OpenMagnetics Provider 不可用"}</strong><span>${available ? `PyOpenMagnetics ${esc(status.provider.third_party_version || "未知版本")} · 材料 ${fmt(counts?.core_materials, 0)} · 磁芯 ${fmt(counts?.core_shapes, 0)} · 导线 ${fmt(counts?.wires, 0)}` : esc(status.provider?.errors?.[0]?.message || "请使用独立 OpenMagnetics 环境启动后端")}</span>`;
    byId("physicalSolverLabel").textContent = available ? "外部数据库可查询 · 结果仍标记研究型" : "Provider 不可用 · 可使用明确的本地演示链路验证页面";
  }

  async function loadStatus() {
    try { renderStatus(await request("/api/v1.5/physical/status")); } catch (error) { byId("physicalStatusStrip").innerHTML = `<span class="status-dot offline"></span><strong>状态读取失败</strong><span>${esc(error.message)}</span>`; }
  }

  function renderProgress(task) {
    const pct = Math.round((task.progress || 0) * 100);
    byId("physicalProgressBar").style.width = `${pct}%`;
    byId("physicalProgressPct").textContent = `${pct}%`;
    byId("physicalProgressText").textContent = task.status === "running" ? "正在执行统一候选评估…" : task.status;
  }

  function renderDiagnostic(result) {
    const diagnostics = result?.diagnostics || [];
    const first = diagnostics[0];
    const message = first ? `${first.code}：${first.message}` : (result?.status === "completed" ? "统一候选评估完成。" : "请查看结果中的诊断信息。");
    byId("physicalDiagnostics").innerHTML = `<div class="diagnostic-icon">${result?.status === "completed" ? "✓" : "!"}</div><div><strong>${esc(message)}</strong><p>${result?.source_selection?.synthetic ? "当前结果明确标记为 synthetic / demo_only。" : "当前结果保留数据来源、模型版本和工程未批准标识。"}</p></div>`;
  }

  function renderSvg(result) {
    const layout = result?.geometry?.data;
    if (!layout?.core || !Array.isArray(layout.blocks)) { byId("physicalSvg").innerHTML = "<p class='muted'>几何数据不可用。</p>"; return; }
    const core = layout.core;
    const maxRadial = Math.max(Number(core.window_width_m) || 0.01, ...layout.blocks.map((item) => Number(item.radial_end_m) || 0), 0.01);
    const h = Number(core.window_height_m) || 0.03;
    const x0 = 50, y0 = 25, width = 500, height = 190;
    const sx = (value) => x0 + (Number(value) / maxRadial) * width;
    const sy = (value) => y0 + height - ((Number(value) + h / 2) / h) * height;
    const colors = { primary: "#1f6feb", secondary: "#0f8f84" };
    const blocks = layout.blocks.map((block) => {
      const x = sx(block.radial_start_m), w = Math.max(8, sx(block.radial_end_m) - x); const y = sy(block.axial_end_m), bh = Math.max(8, sy(block.axial_start_m) - y); const role = String(block.role).toLowerCase();
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${w.toFixed(2)}" height="${bh.toFixed(2)}" rx="3" fill="${colors[role] || "#778899"}" opacity=".9"><title>${esc(block.name)} · ${esc(block.turns)} 匝 · ${esc(block.layer_count)} 层</title></rect><text x="${(x + 4).toFixed(2)}" y="${(y + 17).toFixed(2)}" fill="#fff" font-size="12">${esc(block.name)} ${esc(block.turns)}T</text>`;
    }).join("");
    const interfaces = (layout.interfaces || []).map((item) => `<rect x="${sx(item.radial_start_m).toFixed(2)}" y="${y0}" width="${Math.max(2, sx(item.radial_end_m) - sx(item.radial_start_m)).toFixed(2)}" height="${height}" fill="#d97706" opacity=".25"><title>${esc(item.name)} · ${(item.thickness_m * 1000).toFixed(3)} mm</title></rect>`).join("");
    byId("physicalSvg").innerHTML = `<svg viewBox="0 0 620 255" role="img" aria-label="由当前候选几何生成的 ${esc(layout.template?.template_id || "")} 绕组剖面"><rect x="${x0}" y="${y0}" width="${width}" height="${height}" fill="#fff" stroke="#7892a8" stroke-width="2"/><text x="50" y="16" fill="#243b53" font-size="12">窗口 ${(Number(core.window_width_m) * 1000).toFixed(2)} × ${(h * 1000).toFixed(2)} mm · ${esc(layout.template?.template_id || "")}</text>${interfaces}${blocks}<text x="50" y="237" fill="#627d98" font-size="11">蓝：原边 · 青：副边 · 橙色淡区：主绝缘（每个界面独立）</text></svg>`;
  }

  function renderResult(result) {
    physical.result = result; physical.stale = false;
    byId("physicalStaleNotice").classList.add("hidden"); byId("physicalResultEmpty").classList.add("hidden"); byId("physicalResultContent").classList.remove("hidden"); byId("physicalExportJson").disabled = false;
    const s = result.summary || {};
    byId("physicalSummary").innerHTML = [metric("励磁电感 Lm", s.Lm_H == null ? "未计算" : fmt(s.Lm_H * 1e6), "μH", "OpenMagnetics/联合计算"), metric("峰值磁密 Bmax", s.Bmax_T == null ? "未计算" : fmt(s.Bmax_T * 1000), "mT"), metric("磁芯损耗", s.Pcore_W == null ? "未计算" : fmt(s.Pcore_W), "W"), metric("原边参考漏感", s.Lleak_p_H == null ? "未计算" : fmt(s.Lleak_p_H * 1e6), "μH", "研究性解析模型"), metric("工程状态", "UNKNOWN", "未经 COMSOL/试验批准")].join("");
    const source = result.source_selection || {}; const open = result.openmagnetics || {}; const thermal = result.thermal || {};
    const notes = [`<div class="constraint-row"><span>数据来源</span><strong>${esc(source.data_source || "—")} · ${source.synthetic ? "synthetic/demo_only" : "external_database"}</strong></div>`, `<div class="constraint-row"><span>Rdc 原边 / 副边</span><strong>${fmt((s.Rdc_primary_ohm || 0) * 1000, 4)} / ${fmt((s.Rdc_secondary_ohm || 0) * 1000, 4)} mΩ</strong></div>`, `<div class="constraint-row"><span>绕组损耗</span><strong>native ${fmt(s.Pcu_native_W)} W · complete ${s.Pcu_complete_W == null ? "未计算" : `${fmt(s.Pcu_complete_W)} W`}</strong></div>`, `<div class="constraint-row"><span>第三方状态</span><strong>${esc(open.status || "not_requested")}</strong></div>`, `<div class="constraint-row"><span>热模型</span><strong>${esc(thermal.status || "not_implemented")} · 热点未计算</strong></div>`, `<div class="constraint-row"><span>计算版本</span><strong>${esc(result.physical_model_version || "—")} · key ${esc(result.evaluation_key || "—")}</strong></div>`];
    (result.diagnostics || []).slice(0, 8).forEach((item) => notes.push(`<div class="constraint-row"><span>${esc(item.code)}</span><strong class="state-disabled">${esc(item.message)}</strong></div>`));
    byId("physicalResultNotes").innerHTML = notes.join(""); renderSvg(result); byId("physicalSnapshot").textContent = JSON.stringify(result, null, 2); renderDiagnostic(result);
  }

  async function run(geometryOnly = false) {
    let payload;
    try { payload = buildPayload(geometryOnly); const errors = geometryOnly ? [] : validateLocal(payload); if (errors.length) { banner(errors.join(" ")); return; } } catch (error) { banner(error.message); return; }
    byId("physicalRunBtn").disabled = true; byId("physicalGeometryBtn").disabled = true; byId("physicalSolverLabel").textContent = geometryOnly ? "几何检查任务" : "统一候选评估任务"; byId("physicalResultContent").classList.add("hidden"); byId("physicalResultEmpty").textContent = "正在执行…"; byId("physicalResultEmpty").classList.remove("hidden");
    try { physical.task = await request("/api/v1.5/physical/evaluations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); renderProgress(physical.task); if (physical.timer) clearInterval(physical.timer); physical.timer = setInterval(poll, 260); } catch (error) { banner(`任务提交失败：${error.message}`); byId("physicalRunBtn").disabled = false; byId("physicalGeometryBtn").disabled = false; }
  }

  async function poll() {
    if (!physical.task) return;
    try { const task = await request(`/api/v1.5/physical/evaluations/${physical.task.id}`); physical.task = task; renderProgress(task); if (["completed", "input_invalid", "failed"].includes(task.status)) { clearInterval(physical.timer); physical.timer = null; byId("physicalRunBtn").disabled = false; byId("physicalGeometryBtn").disabled = false; if (task.result) renderResult(task.result); else banner(task.error || "任务失败"); } } catch (error) { clearInterval(physical.timer); physical.timer = null; banner(`结果读取失败：${error.message}`); byId("physicalRunBtn").disabled = false; byId("physicalGeometryBtn").disabled = false; }
  }

  function bind() {
    if (!byId("physicalView")) return;
    if (!byId("physicalLm")) {
      const topology = byId("physicalTopology");
      const label = document.createElement("label");
      label.innerHTML = '磁化电感要求<input id="physicalLm" type="number" min="0.000001" step="1" value="100" /><em>μH · 第三方输入</em>';
      topology.parentElement.insertBefore(label, topology);
    }
    ["physicalSource", "physicalLayout", "physicalCore", "physicalMaterial", "physicalBobbin", "physicalPrimaryWire", "physicalSecondaryWire", "physicalNp", "physicalNs", "physicalP1", "physicalP2", "physicalGap", "physicalInsulation", "physicalClearance", "physicalEndMargin", "physicalV1", "physicalV2", "physicalPower", "physicalFrequency", "physicalAmbient", "physicalIp", "physicalIs", "physicalLm", "physicalTopology", "physicalTimes", "physicalIpWave", "physicalIsWave", "physicalVpWave", "physicalVsWave", "physicalIncludeOpen"].forEach((id) => byId(id).addEventListener("input", invalidate));
    byId("physicalSource").addEventListener("change", () => { sourceDefaults(); invalidate(); loadStatus(); });
    byId("physicalLayout").addEventListener("change", () => { const psp = byId("physicalLayout").value === "PSP"; byId("physicalP1").disabled = !psp; byId("physicalP2").disabled = !psp; invalidate(); });
    byId("physicalStatusBtn").addEventListener("click", loadStatus); byId("physicalRunBtn").addEventListener("click", () => run(false)); byId("physicalGeometryBtn").addEventListener("click", () => run(true));
    byId("physicalExportJson").addEventListener("click", () => { if (physical.task) window.location.href = `/api/v1.5/physical/evaluations/${physical.task.id}/report?format=json`; });
    byId("physicalLayout").dispatchEvent(new Event("change")); loadStatus();
  }
  document.addEventListener("DOMContentLoaded", bind);
})();
