"use strict";

const CHART_MARGIN = Object.freeze({ left: 58, right: 14 });
const STRIKE_FLOW_COLOURS = Object.freeze(["#2bc2ff", "#f7c34d", "#c991ff", "#4bd59b"]);
const STRIKE_SNAPSHOT_MAX_ROWS = 11;
const VOLUME_PROFILE_FAMILY = "BN_REF_FUT_VOLUME_VPOC";
const INVENTORY_FAMILY_META = Object.freeze({
  FUT_POS_OI_VPOC: { label: "FUT +OI VPOC", group: "futures", colour: "#65e6a8" },
  FUT_NEG_OI_VPOC: { label: "FUT −OI VPOC", group: "futures", colour: "#ff708d" },
  CE_POS_OI_VPOC: { label: "CE +OI VPOC", group: "ce", colour: "#ffad66" },
  CE_NEG_OI_VPOC: { label: "CE −OI VPOC", group: "ce", colour: "#ff82b0" },
  PE_POS_OI_VPOC: { label: "PE +OI VPOC", group: "pe", colour: "#4fd8cf" },
  PE_NEG_OI_VPOC: { label: "PE −OI VPOC", group: "pe", colour: "#8ca8ff" }
});
const INVENTORY_TOGGLE_IDS = Object.freeze([
  "inventoryScopeID",
  "inventoryScope1D", "inventoryScope2D", "inventoryScope3D",
  "inventoryOiVpoc", "inventoryOiFutures", "inventoryOiCe", "inventoryOiPe",
  "inventoryVolumeProfile",
  "inventoryVolumeVpoc", "inventoryVolumeVah", "inventoryVolumeVal"
]);
const INVENTORY_SCOPE_IDS = Object.freeze([
  "inventoryScopeID", "inventoryScope1D", "inventoryScope2D", "inventoryScope3D"
]);
const FRAME_STORAGE_KEY = "banknifty-new-divergence-frame-visibility-v1";
const FRAME_MAXIMIZED_KEY = "banknifty-new-divergence-maximized-frame-v1";
const CODEX_TOKEN_STORAGE_KEY = "banknifty-new-divergence-codex-token-v1";
const FRAME_TARGETS = Object.freeze({
  frameMarket: "marketPanel",
  frameCeOi: "ceOiFlowPanel",
  framePeOi: "peOiFlowPanel",
  frameCeVolume: "ceVolumeFlowPanel",
  framePeVolume: "peVolumeFlowPanel",
  frameCeSnapshot: "ceSnapshotPanel",
  framePeSnapshot: "peSnapshotPanel",
  frameInventoryList: "inventoryListPanel"
});
const OVERLAY_TOGGLE_IDS = Object.freeze(["frameBasis"]);
const RIGHT_FRAME_IDS = Object.freeze([
  "frameCeSnapshot", "framePeSnapshot", "frameInventoryList"
]);
const byId = (id) => document.getElementById(id);
const json = async (path) => {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
};
const formatIST = (value) => new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit"
}).format(new Date(value));
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const number = (value, digits = 2) => Number(value).toLocaleString("en-IN", {
  minimumFractionDigits: digits, maximumFractionDigits: digits
});
const compactQuantity = (value) => {
  const amount = Math.abs(Number(value));
  if (!Number.isFinite(amount)) return "—";
  if (amount >= 1e7) return `${number(amount / 1e7, 2)}Cr`;
  if (amount >= 1e5) return `${number(amount / 1e5, 1)}L`;
  if (amount >= 1e3) return `${number(amount / 1e3, 1)}K`;
  return number(amount, 0);
};

function restoreFrameVisibility() {
  let saved = {};
  try {
    saved = JSON.parse(window.sessionStorage.getItem(FRAME_STORAGE_KEY) || "{}");
  } catch (_error) {
    saved = {};
  }
  for (const id of [...Object.keys(FRAME_TARGETS), ...OVERLAY_TOGGLE_IDS]) {
    if (typeof saved[id] === "boolean") byId(id).checked = saved[id];
  }
}

function applyFrameVisibility() {
  const saved = {};
  for (const [id, target] of Object.entries(FRAME_TARGETS)) {
    const visible = byId(id)?.checked === true;
    saved[id] = visible;
    byId(target).hidden = !visible;
  }
  for (const id of OVERLAY_TOGGLE_IDS) saved[id] = byId(id)?.checked === true;
  const rightVisible = RIGHT_FRAME_IDS.some((id) => byId(id)?.checked === true);
  document.querySelector(".strike-column").hidden = !rightVisible;
  document.querySelector(".replay-workspace").classList.toggle("no-strike-column", !rightVisible);
  try {
    window.sessionStorage.setItem(FRAME_STORAGE_KEY, JSON.stringify(saved));
  } catch (_error) {
    // Frame visibility remains functional when browser storage is unavailable.
  }
}

function restoreFrame() {
  const panel = document.querySelector(".frame-maximized");
  if (!panel) return false;
  panel.classList.remove("frame-maximized");
  document.body.classList.remove("has-maximized-frame");
  const button = panel.querySelector(".frame-maximize");
  if (button) { button.textContent = "Maximize"; button.setAttribute("aria-pressed", "false"); }
  try { window.sessionStorage.removeItem(FRAME_MAXIMIZED_KEY); } catch (_error) {}
  window.dispatchEvent(new Event("resize"));
  return true;
}

function maximizeFrame(panelId) {
  const panel = byId(panelId);
  if (!panel || panel.hidden) return;
  restoreFrame();
  panel.classList.add("frame-maximized");
  document.body.classList.add("has-maximized-frame");
  const button = panel.querySelector(".frame-maximize");
  if (button) { button.textContent = "Restore"; button.setAttribute("aria-pressed", "true"); }
  try { window.sessionStorage.setItem(FRAME_MAXIMIZED_KEY, panelId); } catch (_error) {}
  window.dispatchEvent(new Event("resize"));
}

function installFrameMaximizeControls() {
  for (const panelId of Object.values(FRAME_TARGETS)) {
    const panel = byId(panelId);
    const title = panel?.querySelector(".section-title");
    if (!title || title.querySelector(".frame-maximize")) continue;
    const button = element("button", "frame-maximize", "Maximize");
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-label", `Maximize ${panel.querySelector("h2")?.textContent || "frame"}`);
    button.addEventListener("click", () => panel.classList.contains("frame-maximized")
      ? restoreFrame() : maximizeFrame(panelId));
    title.append(button);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && restoreFrame()) event.preventDefault();
  });
  try {
    const saved = window.sessionStorage.getItem(FRAME_MAXIMIZED_KEY);
    if (saved && Object.values(FRAME_TARGETS).includes(saved)) maximizeFrame(saved);
  } catch (_error) {}
}

function latestIntradayControls(block, asOf) {
  if (!block || !Array.isArray(block.fields) || !Array.isArray(block.rows)) return [];
  const timestampIndex = block.fields.indexOf("t");
  const familyIndex = block.fields.indexOf("family");
  if (timestampIndex < 0 || familyIndex < 0) return [];
  const latest = new Map();
  for (const values of block.rows) {
    const timestamp = new Date(values[timestampIndex]).getTime();
    if (!Number.isFinite(timestamp) || timestamp > asOf) continue;
    latest.set(values[familyIndex], Object.fromEntries(
      block.fields.map((field, index) => [field, values[index]])
    ));
  }
  return [...latest.values()];
}

function inventoryDisplayLines(block, intradayBlock, asOf) {
  const scopes = new Set(
    ["ID", "1D", "2D", "3D"].filter((scope) => byId(`inventoryScope${scope}`)?.checked)
  );
  const oiEnabled = byId("inventoryOiVpoc")?.checked === true;
  const volumeEnabled = byId("inventoryVolumeProfile")?.checked === true;
  const groups = {
    futures: byId("inventoryOiFutures")?.checked === true,
    ce: byId("inventoryOiCe")?.checked === true,
    pe: byId("inventoryOiPe")?.checked === true
  };
  const result = [];
  const controls = [
    ...(Array.isArray(block?.controls) ? block.controls : []),
    ...latestIntradayControls(intradayBlock, asOf)
  ];
  for (const control of controls) {
    if (control.status !== "AVAILABLE" || !scopes.has(control.scope)) continue;
    if (control.family === VOLUME_PROFILE_FAMILY) {
      for (const [toggle, field, label, colour, kind] of [
        ["inventoryVolumeVpoc", "control_value", "BN-ref FUT VOL VPOC", "#f7c34d", "VPOC"],
        ["inventoryVolumeVah", "value_area_high", "BN-ref FUT VOL VAH", "#d3a8ff", "VAH"],
        ["inventoryVolumeVal", "value_area_low", "BN-ref FUT VOL VAL", "#d3a8ff", "VAL"]
      ]) {
        const rawValue = control[field];
        const value = Number(rawValue);
        if (rawValue !== null && rawValue !== undefined
            && volumeEnabled && byId(toggle)?.checked === true && Number.isFinite(value)) {
          result.push({ ...control, value, label, colour, kind });
        }
      }
      continue;
    }
    const meta = INVENTORY_FAMILY_META[control.family];
    const rawValue = control.control_value;
    const value = Number(rawValue);
    if (rawValue !== null && rawValue !== undefined
        && oiEnabled && meta && groups[meta.group] && Number.isFinite(value)) {
      result.push({ ...control, value, label: meta.label, colour: meta.colour, kind: "OI_VPOC" });
    }
  }
  const scopeOrder = { ID: 0, "1D": 1, "2D": 2, "3D": 3 };
  return result.sort((a, b) =>
    scopeOrder[a.scope] - scopeOrder[b.scope]
      || a.label.localeCompare(b.label)
      || a.value - b.value
  );
}

function inventoryDash(line) {
  if (line.kind === "VAH" || line.kind === "VAL") {
    return line.scope === "ID" ? [4, 3] : line.scope === "1D" ? [9, 4] : line.scope === "2D" ? [7, 3, 2, 3] : [2, 4];
  }
  return line.scope === "ID" ? [] : line.scope === "1D" ? [9, 4] : line.scope === "2D" ? [7, 3, 2, 3] : [2, 4];
}

function configureInventoryControls(block, intradayBlock) {
  const priorOi = block?.feature_flags?.oi_vpoc || { enabled: false, available: false };
  const priorVolume = block?.feature_flags?.volume_profile || { enabled: false, available: false };
  const intradayOi = intradayBlock?.feature_flags?.oi_vpoc || { enabled: false, available: false };
  const intradayVolume = intradayBlock?.feature_flags?.volume_profile || { enabled: false, available: false };
  const oiFeature = {
    enabled: priorOi.enabled || intradayOi.enabled,
    available: priorOi.available || intradayOi.available
  };
  const volumeFeature = {
    enabled: priorVolume.enabled || intradayVolume.enabled,
    available: priorVolume.available || intradayVolume.available
  };
  for (const id of ["inventoryOiVpoc", "inventoryOiFutures", "inventoryOiCe", "inventoryOiPe"]) {
    byId(id).disabled = !(oiFeature.enabled && oiFeature.available);
  }
  for (const id of ["inventoryVolumeProfile", "inventoryVolumeVpoc", "inventoryVolumeVah", "inventoryVolumeVal"]) {
    byId(id).disabled = !(volumeFeature.enabled && volumeFeature.available);
  }
  const priorAvailable = (priorOi.enabled && priorOi.available)
    || (priorVolume.enabled && priorVolume.available);
  const intradayAvailable = (intradayOi.enabled && intradayOi.available)
    || (intradayVolume.enabled && intradayVolume.available);
  const anyAvailable = (oiFeature.enabled && oiFeature.available)
    || (volumeFeature.enabled && volumeFeature.available);
  for (const id of ["inventoryScope1D", "inventoryScope2D", "inventoryScope3D"]) {
    const node = byId(id);
    node.disabled = !priorAvailable;
    if (node.disabled) node.checked = false;
  }
  byId("inventoryScopeID").disabled = !intradayAvailable;
  if (byId("inventoryScopeID").disabled) byId("inventoryScopeID").checked = false;
  const status = byId("inventoryContextStatus");
  status.className = `state-pill ${anyAvailable ? "green" : "neutral"}`;
  status.textContent = anyAvailable
    ? `${intradayAvailable ? `ID ${String(intradayBlock.status).toLowerCase()}` : "ID unavailable"} · ${priorAvailable ? `${block.cutoff_source_session} prior` : "prior unavailable"}`
    : block?.status === "DISABLED" ? "Disabled at build" : "Prior context unavailable";
}

function syncInventoryFamilyControls(block, intradayBlock) {
  const priorSelected = ["inventoryScope1D", "inventoryScope2D", "inventoryScope3D"]
    .some((id) => byId(id)?.checked && !byId(id)?.disabled);
  const intradaySelected = byId("inventoryScopeID")?.checked
    && !byId("inventoryScopeID")?.disabled;
  const priorOi = block?.feature_flags?.oi_vpoc || { enabled: false, available: false };
  const priorVolume = block?.feature_flags?.volume_profile || { enabled: false, available: false };
  const intradayOi = intradayBlock?.feature_flags?.oi_vpoc || { enabled: false, available: false };
  const intradayVolume = intradayBlock?.feature_flags?.volume_profile || { enabled: false, available: false };
  const oiMaster = byId("inventoryOiVpoc");
  oiMaster.disabled = !(
    (priorSelected && priorOi.enabled && priorOi.available)
    || (intradaySelected && intradayOi.enabled && intradayOi.available)
  );
  for (const id of ["inventoryOiFutures", "inventoryOiCe", "inventoryOiPe"]) {
    const node = byId(id);
    node.disabled = oiMaster.disabled || !oiMaster.checked;
  }
  const volumeMaster = byId("inventoryVolumeProfile");
  const priorVolumeSelectedAvailable = priorSelected
    && priorVolume.enabled && priorVolume.available;
  const intradayVolumeSelectedAvailable = intradaySelected
    && intradayVolume.enabled && intradayVolume.available;
  volumeMaster.disabled = !(priorVolumeSelectedAvailable || intradayVolumeSelectedAvailable);
  for (const id of ["inventoryVolumeVpoc", "inventoryVolumeVah", "inventoryVolumeVal"]) {
    const node = byId(id);
    node.disabled = volumeMaster.disabled || !volumeMaster.checked;
  }
  const volumeStatus = byId("inventoryVolumeStatus");
  const selectedScope = priorSelected || intradaySelected;
  if (!selectedScope) {
    volumeStatus.textContent = "Select a scope to display volume levels.";
  } else if (intradaySelected && !intradayVolumeSelectedAvailable
      && intradayBlock?.futures_market_retained === false) {
    volumeStatus.textContent = priorVolumeSelectedAvailable
      ? "Prior volume available; ID volume needs a V1.0.13+ raw replay."
      : "ID volume unavailable: replay this session with V1.0.13 or later.";
  } else if (priorVolumeSelectedAvailable || intradayVolumeSelectedAvailable) {
    volumeStatus.textContent = "Available for the selected scope.";
  } else if ((priorSelected && !priorVolume.enabled)
      || (intradaySelected && !intradayVolume.enabled)) {
    volumeStatus.textContent = "Volume profiles were disabled when this GUI was built.";
  } else {
    volumeStatus.textContent = "No verified Futures-volume profile for the selected scope.";
  }
}

function renderInventoryLevelList(block, intradayBlock, lines) {
  const list = byId("inventoryLevelList");
  list.replaceChildren();
  byId("inventoryLevelCount").textContent = `${lines.length} shown`;
  byId("inventoryVisibleCount").textContent = `${lines.length} levels shown`;
  if (!lines.length) {
    const noScope = !INVENTORY_SCOPE_IDS.some((id) => byId(id)?.checked);
    const message = noScope
      ? "Select ID, 1D, 2D, or 3D to display a profile."
      : block?.status === "DISABLED" && intradayBlock?.status === "DISABLED"
      ? "Inventory features were disabled when the browser was built."
      : block?.status === "UNAVAILABLE" && !byId("inventoryScopeID")?.checked
        ? `No verified prior context: ${String(block.reason || "unavailable").replaceAll("_", " ").toLowerCase()}.`
        : byId("inventoryScopeID")?.checked && intradayBlock?.status === "UNAVAILABLE"
          ? `Intraday profile unavailable: ${String(intradayBlock.reason || "unavailable").replaceAll("_", " ").toLowerCase()}.`
          : "The selected scope has no enabled profile family yet.";
    list.append(element("p", "empty inventory-empty", message));
    return;
  }
  for (const line of lines) {
    const row = element("div", "inventory-level-row");
    row.style.setProperty("--level-colour", line.colour);
    const swatch = element("span", "inventory-level-swatch");
    const copy = element("div", "inventory-level-copy");
    copy.append(
      element("strong", "", `${line.scope} · ${line.label}`),
      element("span", "", `Sources ${line.source_sessions.join(" / ")}`)
    );
    row.append(swatch, copy, element("strong", "inventory-level-value", number(line.value, 0)));
    list.append(row);
  }
}

async function landing() {
  const list = byId("sessionList");
  if (!list) return;
  try {
    const catalog = await json("catalog.json");
    byId("catalogStats").textContent = `${catalog.eligible_sessions.length} eligible / ${catalog.session_count} discovered`;
    byId("catalogPolicy").textContent = catalog.date_policy.replaceAll("_", " ").toLowerCase();
    if (!catalog.sessions.length) {
      list.append(element("p", "empty", "No completed session run is available yet."));
      return;
    }
    for (const session of catalog.sessions.slice().reverse()) {
      const card = element("article", "session-card");
      card.append(element("h3", "", session.session));
      const details = element("dl");
      const rows = [
        ["Status", session.eligible ? "Replay ready" : session.cash_sample_available ? "Cash sample ready · replay pending" : session.methodology_compatible === false ? "Replay required" : "Incomplete"],
        ["Cash sample", session.cash_sample_available ? `${session.cash_sample_row_count} rows` : "—"],
        ["Basis observations", String(session.basis_observation_count)],
        ["Transitions", String(session.transition_count)],
        ["Index", session.index_symbol || "—"],
        ["Futures", session.futures_symbol || "—"]
      ];
      for (const [label, value] of rows) {
        details.append(element("dt", "", label), element("dd", "", value));
      }
      card.append(details);
      if (session.eligible) {
        const link = element("a", "", "Open causal replay →");
        link.href = `replay.html?session=${encodeURIComponent(session.session)}`;
        card.append(link);
      }
      list.append(card);
    }
  } catch (error) {
    const message = byId("catalogError");
    message.hidden = false;
    message.textContent = `Catalog could not be loaded: ${error.message}`;
  }
}

function unpack(block) {
  return block.rows.map((values) => Object.fromEntries(block.fields.map((field, index) => [field, values[index]])));
}

function canvasSize(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(320, canvas.clientWidth);
  const panel = canvas.closest(".frame-maximized");
  const occupied = panel ? [...panel.children]
    .filter((child) => child !== canvas)
    .reduce((total, child) => total + child.offsetHeight, 0) : 0;
  const height = panel
    ? Math.max(240, panel.clientHeight - occupied - 42)
    : Number(canvas.dataset.logicalHeight);
  if (!Number.isFinite(height) || height <= 0) {
    throw new Error(`Canvas ${canvas.id} has no valid logical height`);
  }
  // Keep layout height independent from the high-DPI backing store. Assigning
  // canvas.height updates the HTML attribute, so re-reading that attribute on
  // every replay frame compounds devicePixelRatio and collapses/grows charts.
  canvas.style.height = `${height}px`;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function visibleConfirmedZones(zones, asOf) {
  return zones
    .filter((zone) => new Date(zone.confirmed_at).getTime() <= asOf)
    .map((zone) => {
      const terminal = zone.ended_at ? new Date(zone.ended_at).getTime() : null;
      return {
        ...zone,
        renderEnd: terminal !== null && terminal <= asOf ? terminal : asOf,
        closed: terminal !== null && terminal <= asOf
      };
    });
}

function transitionVisualClass(item) {
  if (item.state === "CONFIRMED" || item.state === "ACTIVE") return item.colour.toLowerCase();
  if (item.state === "CANDIDATE") return "candidate";
  if (item.state === "ROTATION") return "rotation";
  return "terminal";
}

function chart(canvas, rows, cursor, series, confirmedZones, gapToleranceSeconds) {
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  const margin = { ...CHART_MARGIN, top: 13, bottom: 28 };
  const w = width - margin.left - margin.right;
  const h = height - margin.top - margin.bottom;
  const visible = rows.slice(0, cursor + 1);
  if (!visible.length) return;
  const values = visible.flatMap((row) => series.map((item) => Number(row[item.field]))).filter(Number.isFinite);
  let low = Math.min(...values), high = Math.max(...values);
  const padding = Math.max((high - low) * .08, .5);
  low -= padding; high += padding;
  const first = new Date(visible[0].t).getTime();
  const last = new Date(visible.at(-1).t).getTime();
  const x = (time) => margin.left + (last === first ? 0 : (time - first) / (last - first) * w);
  const y = (value) => margin.top + (high - value) / (high - low) * h;

  for (const zone of confirmedZones) {
    const start = Math.max(first, new Date(zone.confirmed_at).getTime());
    const end = Math.min(last, zone.renderEnd);
    if (end < start || last === first) continue;
    const left = x(start), right = x(end);
    context.fillStyle = zone.colour === "GREEN" ? "rgba(75, 213, 155, .10)" : "rgba(255, 100, 131, .11)";
    context.fillRect(left, margin.top, Math.max(1, right - left), h);
  }

  const gapLimitMs = Math.max(1, Number(gapToleranceSeconds)) * 1000;
  const gaps = [];
  for (let index = 1; index < visible.length; index += 1) {
    const before = new Date(visible[index - 1].t).getTime();
    const after = new Date(visible[index].t).getTime();
    if (after - before > gapLimitMs) gaps.push({ before, after });
  }
  for (const gap of gaps) {
    const left = x(gap.before), right = x(gap.after);
    context.fillStyle = "rgba(142, 176, 193, .08)";
    context.fillRect(left, margin.top, Math.max(1, right - left), h);
  }

  context.strokeStyle = "#17384a";
  context.fillStyle = "#8eb0c1";
  context.font = "10px ui-monospace, monospace";
  context.lineWidth = 1;
  for (let tick = 0; tick <= 4; tick += 1) {
    const py = margin.top + h * tick / 4;
    context.beginPath(); context.moveTo(margin.left, py); context.lineTo(width - margin.right, py); context.stroke();
    const label = high - (high - low) * tick / 4;
    context.fillText(number(label, series.length > 1 ? 0 : 1), 4, py + 3);
  }
  for (const item of series) {
    context.strokeStyle = item.colour;
    context.lineWidth = 1.5;
    context.beginPath();
    let previousTime = null;
    let penDown = false;
    visible.forEach((row) => {
      const time = new Date(row.t).getTime();
      const value = Number(row[item.field]);
      if (!Number.isFinite(time) || !Number.isFinite(value)) {
        penDown = false;
        previousTime = time;
        return;
      }
      const point = [x(time), y(value)];
      if (!penDown || previousTime === null || time - previousTime > gapLimitMs) {
        context.moveTo(...point);
      } else {
        context.lineTo(...point);
      }
      penDown = true;
      previousTime = time;
    });
    context.stroke();
  }

  for (const zone of confirmedZones) {
    const start = new Date(zone.confirmed_at).getTime();
    if (start < first || start > last || last === first) continue;
    context.strokeStyle = zone.colour === "GREEN" ? "#4bd59b" : "#ff6483";
    context.lineWidth = 2;
    context.beginPath(); context.moveTo(x(start), margin.top); context.lineTo(x(start), margin.top + h); context.stroke();
    if (zone.closed && zone.renderEnd >= first && zone.renderEnd <= last) {
      context.strokeStyle = "#8eb0c1";
      context.setLineDash([4, 3]);
      context.beginPath(); context.moveTo(x(zone.renderEnd), margin.top); context.lineTo(x(zone.renderEnd), margin.top + h); context.stroke();
      context.setLineDash([]);
    }
  }
  for (const gap of gaps) {
    const left = x(gap.before), right = x(gap.after);
    context.strokeStyle = "#617f90";
    context.lineWidth = 1;
    context.setLineDash([2, 3]);
    context.beginPath();
    context.moveTo(left, margin.top); context.lineTo(left, margin.top + h);
    context.moveTo(right, margin.top); context.lineTo(right, margin.top + h);
    context.stroke();
    context.setLineDash([]);
    if (right - left >= 72) {
      const seconds = Math.round((gap.after - gap.before) / 1000);
      const label = `NO BASIS DATA ${Math.floor(seconds / 60)}m ${seconds % 60}s`;
      context.fillStyle = "#8eb0c1";
      context.fillText(label, left + 5, margin.top + 13);
    }
  }
  context.fillStyle = "#8eb0c1";
  context.fillText(formatIST(visible[0].t), margin.left, height - 8);
  const endLabel = formatIST(visible.at(-1).t);
  context.fillText(endLabel, width - margin.right - context.measureText(endLabel).width, height - 8);
}

function drawInventoryLevels(context, width, margin, priceY, lines) {
  context.save();
  const projected = lines
    .map((line) => ({ line, py: priceY(line.value), labelY: priceY(line.value) }))
    .sort((a, b) => a.py - b.py);
  const labelRoom = Math.max(0, margin.priceBottom - (margin.priceTop ?? margin.top) - 6);
  const minimumLabelGap = projected.length > 1
    ? Math.max(7, Math.min(11, labelRoom / (projected.length - 1))) : 11;
  for (let index = 1; index < projected.length; index += 1) {
    projected[index].labelY = Math.max(
      projected[index].py, projected[index - 1].labelY + minimumLabelGap
    );
  }
  const bottom = projected.at(-1);
  if (bottom && bottom.labelY > margin.priceBottom - 3) {
    const shift = bottom.labelY - (margin.priceBottom - 3);
    for (const item of projected) item.labelY -= shift;
  }
  for (const { line, py } of projected) {
    context.strokeStyle = line.colour;
    context.lineWidth = line.scope === "ID" ? 1.9 : line.kind === "VPOC" ? 1.6 : 1.2;
    context.globalAlpha = line.scope === "ID" ? .95 : line.kind === "OI_VPOC" ? .82 : .88;
    context.setLineDash(inventoryDash(line));
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
  }
  context.setLineDash([]);
  context.globalAlpha = 1;
  context.font = "9px ui-monospace, monospace";
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (const { line, labelY } of projected) {
    const label = `${line.scope} ${line.label.replace("BN-ref FUT VOL ", "VOL ")} ${number(line.value, 0)}`;
    const textWidth = context.measureText(label).width;
    const right = width - margin.right - 3;
    context.fillStyle = "rgba(3, 20, 29, .88)";
    context.fillRect(right - textWidth - 5, labelY - 5, textWidth + 7, 10);
    context.fillStyle = line.colour;
    context.fillText(label, right, labelY);
  }
  context.textBaseline = "alphabetic";
  context.textAlign = "left";
  context.restore();
}

function adaptiveBasisLane(rows, priceY, priceTop, priceBottom, enabled) {
  if (!enabled) return { mode: "HIDDEN", top: 0, bottom: 0 };
  const samples = rows.map((row) => ({
    index: Number(row.i), futures: Number(row.f), basis: Number(row.b)
  })).filter((row) => Number.isFinite(row.index)
    && Number.isFinite(row.futures) && Number.isFinite(row.basis));
  if (!samples.length) return { mode: "UNAVAILABLE", top: 0, bottom: 0 };
  const sign = Math.sign(samples.at(-1).basis);
  const oneSided = sign !== 0 && samples.every((row) => Math.sign(row.basis) === sign);
  const upper = samples.map((row) => Math.min(priceY(row.index), priceY(row.futures)));
  const lower = samples.map((row) => Math.max(priceY(row.index), priceY(row.futures)));
  const corridorTop = Math.max(...upper) + 9;
  const corridorBottom = Math.min(...lower) - 9;
  const requestedLaneHeight = 180;
  if (oneSided && corridorBottom - corridorTop >= requestedLaneHeight) {
    const centre = (corridorTop + corridorBottom) / 2;
    return {
      mode: "BETWEEN",
      top: centre - requestedLaneHeight / 2,
      bottom: centre + requestedLaneHeight / 2
    };
  }
  return {
    mode: "TOP",
    top: priceTop,
    bottom: Math.min(priceBottom, priceTop + requestedLaneHeight)
  };
}

function drawAdaptiveBasisLane(context, width, margin, rows, x, lane, gapLimitMs) {
  if (!lane || lane.mode === "HIDDEN" || lane.mode === "UNAVAILABLE") return;
  const values = rows.map((row) => Number(row.b)).filter(Number.isFinite);
  if (!values.length) return;
  let low = Math.min(...values), high = Math.max(...values);
  const padding = Math.max((high - low) * .12, .5);
  low -= padding; high += padding;
  const laneHeight = lane.bottom - lane.top;
  const y = (value) => lane.top + 8 + (high - value) / (high - low || 1) * Math.max(1, laneHeight - 16);
  context.save();
  context.fillStyle = "rgba(17, 28, 48, .93)";
  context.fillRect(margin.left, lane.top, width - margin.left - margin.right, laneHeight);
  context.strokeStyle = "rgba(183, 156, 255, .28)";
  context.strokeRect(margin.left, lane.top, width - margin.left - margin.right, laneHeight);
  context.font = "9px ui-monospace, monospace";
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (let guide = 1; guide <= 4; guide += 1) {
    const fraction = guide / 5;
    const guideY = lane.top + laneHeight * fraction;
    const guideValue = high - (high - low) * fraction;
    context.strokeStyle = "rgba(183, 156, 255, .24)";
    context.beginPath();
    context.moveTo(margin.left, guideY);
    context.lineTo(width - margin.right, guideY);
    context.stroke();
    context.fillStyle = "rgba(212, 197, 255, .72)";
    context.fillText(number(guideValue, 1), width - margin.right - 5, guideY - 7);
  }
  context.save();
  context.beginPath();
  context.rect(margin.left, lane.top, width - margin.left - margin.right, laneHeight);
  context.clip();
  context.strokeStyle = "#b79cff";
  context.lineWidth = 1.45;
  context.beginPath();
  let penDown = false;
  let priorTime = null;
  for (const row of rows) {
    const time = new Date(row.t).getTime();
    const value = Number(row.b);
    if (!Number.isFinite(time) || !Number.isFinite(value)) {
      penDown = false;
      priorTime = time;
      continue;
    }
    const point = [x(time), y(value)];
    if (!penDown || priorTime === null || time - priorTime > gapLimitMs) context.moveTo(...point);
    else context.lineTo(...point);
    penDown = true;
    priorTime = time;
  }
  context.stroke();
  context.restore();
  const latest = values.at(-1);
  context.font = "10px ui-monospace, monospace";
  context.textAlign = "left";
  context.textBaseline = "top";
  context.fillStyle = "#d4c5ff";
  context.fillText(
    `BASIS · FUT − INDEX · ${latest >= 0 ? "+" : ""}${number(latest, 1)} · ${lane.mode}`,
    margin.left + 6, lane.top + 4
  );
  context.textBaseline = "alphabetic";
  context.restore();
}

function marketOiChart(
  canvas, priceRows, oiRows, cursor, confirmedZones,
  priceGapToleranceSeconds, oiGapToleranceSeconds, inventoryLines, showBasis
) {
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  const margin = { ...CHART_MARGIN, top: 13, bottom: 28 };
  const plotWidth = width - margin.left - margin.right;
  const priceBottom = height - margin.bottom;
  const visiblePrice = priceRows.slice(0, cursor + 1);
  if (!visiblePrice.length || plotWidth <= 0 || priceBottom - margin.top <= 0) return;

  const first = new Date(visiblePrice[0].t).getTime();
  const last = new Date(visiblePrice.at(-1).t).getTime();
  const x = (time) => margin.left + (last === first ? 0 : (time - first) / (last - first) * plotWidth);
  const visibleOi = oiRows.filter((row) => {
    const time = new Date(row.t).getTime();
    return Number.isFinite(time) && time >= first && time <= last;
  });
  const prices = visiblePrice
    .flatMap((row) => [Number(row.i), Number(row.f)])
    .filter(Number.isFinite);
  for (const line of inventoryLines) {
    if (Number.isFinite(Number(line.value))) prices.push(Number(line.value));
  }
  const oiValues = visibleOi.map((row) => Number(row.oi)).filter(Number.isFinite);
  if (!prices.length) return;

  let priceLow = Math.min(...prices), priceHigh = Math.max(...prices);
  const pricePadding = Math.max((priceHigh - priceLow) * .08, .5);
  priceLow -= pricePadding; priceHigh += pricePadding;
  const preliminaryPriceY = (value) => margin.top
    + (priceHigh - value) / (priceHigh - priceLow) * (priceBottom - margin.top);
  let basisLane = adaptiveBasisLane(
    visiblePrice, preliminaryPriceY, margin.top, priceBottom, showBasis
  );
  const priceTop = basisLane.mode === "TOP" ? basisLane.bottom + 8 : margin.top;
  const priceHeight = priceBottom - priceTop;
  const priceY = (value) => priceTop
    + (priceHigh - value) / (priceHigh - priceLow) * priceHeight;
  if (basisLane.mode === "BETWEEN") {
    basisLane = adaptiveBasisLane(visiblePrice, priceY, priceTop, priceBottom, showBasis);
  }
  margin.priceTop = priceTop;
  margin.priceBottom = priceBottom;
  let oiLow = oiValues.length ? Math.min(...oiValues) : 0;
  let oiHigh = oiValues.length ? Math.max(...oiValues) : 1;
  const oiPadding = Math.max((oiHigh - oiLow) * .08, 1);
  oiLow -= oiPadding; oiHigh += oiPadding;
  const oiOverlayTop = priceTop + 22;
  const oiOverlayBottom = Math.max(oiOverlayTop + 1, priceBottom - 48);
  const oiY = (value) => oiOverlayTop
    + (oiHigh - value) / (oiHigh - oiLow || 1) * (oiOverlayBottom - oiOverlayTop);
  const deltaZeroY = priceBottom - 23;
  const deltaHalfHeight = 20;

  for (const zone of confirmedZones) {
    const start = Math.max(first, new Date(zone.confirmed_at).getTime());
    const end = Math.min(last, zone.renderEnd);
    if (end < start || last === first) continue;
    context.fillStyle = zone.colour === "GREEN"
      ? "rgba(75, 213, 155, .10)" : "rgba(255, 100, 131, .11)";
    context.fillRect(x(start), priceTop, Math.max(1, x(end) - x(start)), priceHeight);
  }

  const priceGapLimitMs = Math.max(1, Number(priceGapToleranceSeconds)) * 1000;
  const gaps = [];
  for (let index = 1; index < visiblePrice.length; index += 1) {
    const before = new Date(visiblePrice[index - 1].t).getTime();
    const after = new Date(visiblePrice[index].t).getTime();
    if (after - before > priceGapLimitMs) gaps.push({ before, after });
  }
  for (const gap of gaps) {
    context.fillStyle = "rgba(142, 176, 193, .08)";
    context.fillRect(x(gap.before), priceTop, Math.max(1, x(gap.after) - x(gap.before)), priceHeight);
  }

  context.strokeStyle = "#17384a";
  context.fillStyle = "#8eb0c1";
  context.font = "10px ui-monospace, monospace";
  context.lineWidth = 1;
  context.textAlign = "left";
  for (let tick = 0; tick <= 4; tick += 1) {
    const py = priceTop + priceHeight * tick / 4;
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
    const label = priceHigh - (priceHigh - priceLow) * tick / 4;
    context.fillText(number(label, 0), 4, py + 3);
  }
  if (oiValues.length) {
    context.fillStyle = "#f7c34d";
    context.textAlign = "right";
    context.fillText(`OI ${number(oiHigh, 0)}`, width - margin.right - 4, priceTop + 11);
    context.fillText(`OI ${number(oiLow, 0)}`, width - margin.right - 4, priceBottom - 5);
    context.textAlign = "left";
  }

  drawAdaptiveBasisLane(
    context, width, margin, visiblePrice, x, basisLane,
    Math.max(1, Number(priceGapToleranceSeconds)) * 1000
  );

  for (const series of [
    { field: "i", colour: "#2bc2ff" },
    { field: "f", colour: "#e7edf0" }
  ]) {
    context.strokeStyle = series.colour;
    context.lineWidth = 1.5;
    context.beginPath();
    let priorPriceTime = null;
    let pricePenDown = false;
    for (const row of visiblePrice) {
      const time = new Date(row.t).getTime();
      const value = Number(row[series.field]);
      if (!Number.isFinite(time) || !Number.isFinite(value)) {
        pricePenDown = false;
        priorPriceTime = time;
        continue;
      }
      const point = [x(time), priceY(value)];
      if (!pricePenDown || priorPriceTime === null || time - priorPriceTime > priceGapLimitMs) {
        context.moveTo(...point);
      } else {
        context.lineTo(...point);
      }
      pricePenDown = true;
      priorPriceTime = time;
    }
    context.stroke();
  }

  const oiGapLimitMs = Math.max(0, Number(oiGapToleranceSeconds)) * 1000;
  if (visibleOi.length) {
    context.strokeStyle = "#f7c34d";
    context.lineWidth = 1.6;
    context.beginPath();
    let priorOiTime = null;
    let oiPenDown = false;
    for (const row of visibleOi) {
      const time = new Date(row.t).getTime();
      const value = Number(row.oi);
      if (!Number.isFinite(time) || !Number.isFinite(value)) {
        oiPenDown = false;
        priorOiTime = time;
        continue;
      }
      const point = [x(time), oiY(value)];
      if (!oiPenDown || priorOiTime === null || time - priorOiTime > oiGapLimitMs || row.d === null) {
        context.moveTo(...point);
      } else {
        context.lineTo(...point);
      }
      oiPenDown = true;
      priorOiTime = time;
    }
    context.stroke();
    context.fillStyle = "#f7c34d";
    context.textAlign = "left";
    context.fillText(`FUT OI ${number(visibleOi.at(-1).oi, 0)}`, margin.left + 5, priceTop + 13);
  } else {
    context.fillStyle = "#8eb0c1";
    context.textAlign = "left";
    context.fillText("Futures OI unavailable", margin.left + 5, priceTop + 13);
    context.textAlign = "left";
  }

  for (const zone of confirmedZones) {
    const start = new Date(zone.confirmed_at).getTime();
    if (start < first || start > last || last === first) continue;
    context.strokeStyle = zone.colour === "GREEN" ? "#4bd59b" : "#ff6483";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(x(start), priceTop);
    context.lineTo(x(start), priceBottom);
    context.stroke();
    if (zone.closed && zone.renderEnd >= first && zone.renderEnd <= last) {
      context.strokeStyle = "#8eb0c1";
      context.setLineDash([4, 3]);
      context.beginPath();
      context.moveTo(x(zone.renderEnd), priceTop);
      context.lineTo(x(zone.renderEnd), priceBottom);
      context.stroke();
      context.setLineDash([]);
    }
  }
  for (const gap of gaps) {
    context.strokeStyle = "#617f90";
    context.lineWidth = 1;
    context.setLineDash([2, 3]);
    context.beginPath();
    context.moveTo(x(gap.before), priceTop);
    context.lineTo(x(gap.before), priceBottom);
    context.moveTo(x(gap.after), priceTop);
    context.lineTo(x(gap.after), priceBottom);
    context.stroke();
    context.setLineDash([]);
  }

  drawInventoryLevels(context, width, margin, priceY, inventoryLines);

  context.strokeStyle = "#31566a";
  context.beginPath();
  context.moveTo(margin.left, deltaZeroY);
  context.lineTo(width - margin.right, deltaZeroY);
  context.stroke();
  context.fillStyle = "#8eb0c1";
  context.fillText("±ΔOI", 4, deltaZeroY + 3);

  const deltas = visibleOi.map((row) => Number(row.d)).filter(Number.isFinite);
  const maximumDelta = Math.max(1, ...deltas.map(Math.abs));
  const barWidth = Math.max(1, Math.min(6, plotWidth / Math.max(visibleOi.length, 1) * .72));
  for (const row of visibleOi) {
    if (row.d === null) continue;
    const delta = Number(row.d);
    const time = new Date(row.t).getTime();
    if (!Number.isFinite(delta) || !Number.isFinite(time) || delta === 0) continue;
    const barHeight = Math.max(1, Math.abs(delta) / maximumDelta * deltaHalfHeight);
    context.fillStyle = delta > 0 ? "#4bd59b" : "#ff6483";
    context.fillRect(
      x(time) - barWidth / 2,
      delta > 0 ? deltaZeroY - barHeight : deltaZeroY,
      barWidth,
      barHeight
    );
  }

  context.fillStyle = "#8eb0c1";
  context.textAlign = "left";
  context.fillText(formatIST(visiblePrice[0].t), margin.left, height - 8);
  const endLabel = formatIST(visiblePrice.at(-1).t);
  context.fillText(endLabel, width - margin.right - context.measureText(endLabel).width, height - 8);
  return basisLane.mode;
}

function latestStrikeSnapshot(strikeRows, priceRows, cursor, selection, retained, maxAgeSeconds) {
  const visiblePrice = priceRows.slice(0, cursor + 1);
  if (!retained) return { code: "REPLAY_REQUIRED", expiry: null, receipt: null, rows: [] };
  if (!visiblePrice.length) return { code: "NO_PRICE", expiry: null, receipt: null, rows: [] };
  if (!selection || selection.available !== true) {
    return { code: "REFERENCE_UNAVAILABLE", expiry: null, receipt: null, rows: [] };
  }
  const first = new Date(visiblePrice[0].t).getTime();
  const last = new Date(visiblePrice.at(-1).t).getTime();
  const analysisStart = new Date(selection.reference_close?.target).getTime();
  const selectedAt = new Date(selection.selected_at).getTime();
  if (!Number.isFinite(analysisStart) || !Number.isFinite(selectedAt) || last < selectedAt) {
    return { code: "AWAITING_0945_SELECTION", expiry: null, receipt: null, rows: [] };
  }
  const visible = strikeRows.filter((row) => {
    const receipt = new Date(row.t).getTime();
    return row.e === selection.expiry && Number.isFinite(receipt)
      && receipt >= Math.max(first, analysisStart, selectedAt) && receipt <= last;
  });
  if (!visible.length) return { code: "NO_RECEIPT", expiry: null, receipt: null, rows: [] };
  const anchor = visible.at(-1);
  const ageSeconds = Math.max(0, (last - new Date(anchor.t).getTime()) / 1000);
  if (!Number.isFinite(ageSeconds) || ageSeconds > maxAgeSeconds) {
    return { code: "STALE_RECEIPT", expiry: anchor.e, receipt: anchor.t, rows: [] };
  }
  const snapshot = visible.filter((row) =>
    row.t === anchor.t && row.e === anchor.e && row.event_id === anchor.event_id
  );
  return {
    code: snapshot.length ? "READY" : "NO_RECEIPT",
    expiry: anchor.e,
    receipt: anchor.t,
    rows: snapshot
  };
}

function strikeOiSnapshotChart(
  canvas, snapshot, currentIndex, optionType, selection, sharedMaximumOi
) {
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  const margin = { left: 76, right: 104, top: 14, bottom: 28 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  if (plotWidth <= 0 || plotHeight <= 0) return { code: "NO_SPACE", strikes: 0 };
  const messages = {
    REPLAY_REQUIRED: "Strike OI was not retained in this run.",
    REFERENCE_UNAVAILABLE: "A fresh BankNifty 09:45 close is unavailable.",
    AWAITING_0945_SELECTION: "Awaiting the first option-chain receipt after 09:45 IST.",
    NO_RECEIPT: `No ${optionType} option-chain receipt is visible yet.`,
    STALE_RECEIPT: `The latest ${optionType} option-chain receipt is stale.`,
    NO_PRICE: "No synchronized BankNifty price is visible yet."
  };
  const message = snapshot.code === "READY" ? null : messages[snapshot.code] || "Strike OI is unavailable.";
  if (message) {
    canvasMessage(context, width, height, margin, message);
    return { code: snapshot.code, strikes: 0 };
  }

  const available = snapshot.rows.filter((row) =>
    row.k === optionType && Number.isFinite(Number(row.s)) && Number.isFinite(Number(row.oi))
  );
  const contracts = Array.isArray(selection[optionType]) ? selection[optionType] : [];
  const fixed = new Map(contracts.map((contract) => [contract.symbol, Number(contract.slot)]));
  const selected = [];
  const selectedSymbols = new Set();
  for (const contract of contracts) {
    const row = available.find((item) => item.symbol === contract.symbol);
    if (row && !selectedSymbols.has(row.symbol)) {
      selected.push(row);
      selectedSymbols.add(row.symbol);
    }
  }
  for (const row of available.slice().sort((a, b) =>
    Math.abs(Number(a.s) - currentIndex) - Math.abs(Number(b.s) - currentIndex)
      || Number(a.s) - Number(b.s)
  )) {
    if (selected.length >= STRIKE_SNAPSHOT_MAX_ROWS) break;
    if (!selectedSymbols.has(row.symbol)) {
      selected.push(row);
      selectedSymbols.add(row.symbol);
    }
  }
  selected.sort((a, b) => Number(b.s) - Number(a.s));
  if (!selected.length) {
    canvasMessage(context, width, height, margin, `No ${optionType} strikes exist in the latest receipt.`);
    return { code: "NO_STRIKES", strikes: 0 };
  }

  const strikes = selected.map((row) => Number(row.s)).sort((a, b) => a - b);
  let low = strikes[0], high = strikes.at(-1);
  const strikeStep = strikes.length > 1
    ? Math.max(1, Math.min(...strikes.slice(1).map((value, index) => value - strikes[index]).filter((value) => value > 0)))
    : 100;
  low -= strikeStep * .5;
  high += strikeStep * .5;
  const y = (strike) => margin.top + (high - strike) / (high - low) * plotHeight;
  const barHeight = Math.max(3, Math.min(14, plotHeight / selected.length * .58));
  const maximumOi = Math.max(1, Number(sharedMaximumOi) || 0);

  context.strokeStyle = "#17384a";
  context.fillStyle = "#8eb0c1";
  context.font = "9px ui-monospace, monospace";
  context.lineWidth = 1;
  for (const row of selected) {
    const strike = Number(row.s);
    const py = y(strike);
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
    const slot = fixed.get(row.symbol);
    context.fillStyle = slot ? "#f7c34d" : "#8eb0c1";
    context.textAlign = "right";
    context.fillText(`${slot ? `S${slot} ` : ""}${number(strike, 0)}`, margin.left - 5, py + 3);

    const oi = Math.max(0, Number(row.oi));
    const barWidth = oi / maximumOi * plotWidth;
    context.globalAlpha = slot ? .9 : .56;
    context.fillStyle = optionType === "CE" ? "#ff906f" : "#4bd59b";
    context.fillRect(margin.left, py - barHeight / 2, barWidth, barHeight);
    context.globalAlpha = 1;
    if (slot) {
      context.strokeStyle = "#f7c34d";
      context.strokeRect(margin.left, py - barHeight / 2, barWidth, barHeight);
    }

    const delta = row.d === null ? null : Number(row.d);
    context.textAlign = "right";
    context.fillStyle = "#edf7fb";
    context.fillText(compactQuantity(oi), width - 4, py - 1);
    context.fillStyle = delta === null ? "#8eb0c1" : delta >= 0 ? "#4bd59b" : "#ff6483";
    const deltaText = delta === null ? "Δ —" : `Δ ${delta >= 0 ? "+" : "−"}${compactQuantity(delta)}`;
    context.fillText(deltaText, width - 4, py + 9);
  }

  const bn = Number(currentIndex);
  if (Number.isFinite(bn) && bn >= low && bn <= high) {
    const py = y(bn);
    context.save();
    context.setLineDash([5, 4]);
    context.strokeStyle = "#2bc2ff";
    context.lineWidth = 1.2;
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
    context.restore();
    context.fillStyle = "#2bc2ff";
    context.textAlign = "left";
    context.fillText(`BN ${number(bn, 0)}`, margin.left + 3, py - 3);
  }
  context.fillStyle = "#8eb0c1";
  context.textAlign = "left";
  context.fillText(`OI receipt ${formatIST(snapshot.receipt)} IST · shared CE/PE scale`, margin.left, height - 8);
  return { code: "READY", strikes: selected.length };
}

function canvasMessage(context, width, height, margin, message) {
  const plotWidth = width - margin.left - margin.right;
  context.fillStyle = "#8eb0c1";
  context.font = "11px ui-sans-serif, system-ui, sans-serif";
  context.textAlign = "center";
  const words = message.split(" ");
  const lines = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (context.measureText(candidate).width > plotWidth - 18 && line) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  lines.forEach((text, index) => {
    context.fillText(text, margin.left + plotWidth / 2, height / 2 + (index - (lines.length - 1) / 2) * 16);
  });
  context.textAlign = "left";
}

function renderStrikeFlowLegend(container, contracts, visible) {
  container.replaceChildren();
  if (!visible) {
    container.append(element("span", "", "Strike identities become visible at the first option-chain receipt after 09:45."));
    return;
  }
  for (const contract of contracts) {
    const item = element("span", "", `S${contract.slot} ${number(contract.strike, 0)}`);
    item.style.setProperty("--series-colour", STRIKE_FLOW_COLOURS[contract.slot - 1]);
    container.append(item);
  }
}

function strikeFlowChart(
  canvas, flowRows, priceRows, cursor, optionType, metric,
  selection, volumeRetained
) {
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  const margin = { ...CHART_MARGIN, top: 14, bottom: 28 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const visiblePrice = priceRows.slice(0, cursor + 1);
  if (!visiblePrice.length || plotWidth <= 0 || plotHeight <= 0) {
    return { code: "NO_PRICE", points: 0, selectionVisible: false };
  }
  if (!selection || selection.available !== true) {
    const reason = "A fresh synchronized BankNifty close at 09:45 IST is unavailable.";
    canvasMessage(context, width, height, margin, reason);
    return { code: "REPLAY_REQUIRED", points: 0, selectionVisible: false };
  }

  const first = new Date(visiblePrice[0].t).getTime();
  const last = new Date(visiblePrice.at(-1).t).getTime();
  const analysisStart = new Date(selection.reference_close?.target).getTime();
  const selectedAt = new Date(selection.selected_at).getTime();
  const selectionVisible = Number.isFinite(analysisStart)
    && Number.isFinite(selectedAt) && last >= selectedAt;
  if (!selectionVisible) {
    canvasMessage(context, width, height, margin, "Awaiting the first valid selected-expiry option-chain receipt.");
    return { code: "AWAITING_SELECTION", points: 0, selectionVisible: false };
  }
  if (metric === "volume" && !volumeRetained) {
    canvasMessage(context, width, height, margin, "Option volume was not retained. Replay the full raw-plus-OI session with V1.0.13.");
    return { code: "VOLUME_REPLAY_REQUIRED", points: 0, selectionVisible: true };
  }

  const field = metric === "oi" ? "d" : "dv";
  const contracts = Array.isArray(selection[optionType]) ? selection[optionType] : [];
  const slots = new Map(contracts.map((contract) => [contract.symbol, Number(contract.slot) - 1]));
  const visible = flowRows.filter((row) => {
    const time = new Date(row.t).getTime();
    return row.k === optionType && slots.has(row.symbol) && Number.isFinite(time)
      && time >= Math.max(first, analysisStart, selectedAt) && time <= last;
  });
  const points = visible.filter((row) => row[field] !== null && Number.isFinite(Number(row[field])) && Number(row[field]) !== 0);
  if (!points.length) {
    const label = metric === "oi" ? "OI change" : "incremental volume";
    canvasMessage(context, width, height, margin, `No successive ${optionType} ${label} is visible yet.`);
    return { code: "NO_CHANGE", points: 0, selectionVisible: true };
  }

  const x = (time) => margin.left + (last === first ? plotWidth / 2 : (time - first) / (last - first) * plotWidth);
  const values = points.map((row) => Number(row[field]));
  const maximum = Math.max(1, ...values.map(Math.abs));
  const low = metric === "oi" ? -maximum : 0;
  const high = maximum;
  const y = (value) => margin.top + (high - value) / (high - low) * plotHeight;
  const zeroY = y(0);

  context.strokeStyle = "#17384a";
  context.fillStyle = "#8eb0c1";
  context.font = "10px ui-monospace, monospace";
  context.lineWidth = 1;
  const ticks = metric === "oi"
    ? [high, high / 2, 0, low / 2, low]
    : [high, high * .75, high * .5, high * .25, 0];
  for (const value of ticks) {
    const py = y(value);
    context.beginPath();
    context.moveTo(margin.left, py);
    context.lineTo(width - margin.right, py);
    context.stroke();
    context.fillText(number(value, 0), 3, py + 3);
  }
  context.strokeStyle = "#52758a";
  context.lineWidth = 1.2;
  context.beginPath();
  context.moveTo(margin.left, zeroY);
  context.lineTo(width - margin.right, zeroY);
  context.stroke();

  const receiptCount = new Set(points.map((row) => row.t)).size;
  const groupWidth = Math.max(4, Math.min(22, plotWidth / Math.max(receiptCount, 1) * .78));
  const barWidth = Math.max(1, groupWidth / Math.max(contracts.length, 4));
  for (const row of points) {
    const value = Number(row[field]);
    const time = new Date(row.t).getTime();
    const slot = slots.get(row.symbol);
    if (!Number.isFinite(value) || !Number.isFinite(time) || slot === undefined) continue;
    const px = x(time) + (slot - contracts.length / 2) * barWidth;
    const valueY = y(value);
    context.fillStyle = STRIKE_FLOW_COLOURS[slot];
    context.globalAlpha = metric === "oi" && value < 0 ? .58 : .9;
    context.fillRect(px, Math.min(zeroY, valueY), barWidth, Math.max(1, Math.abs(zeroY - valueY)));
  }
  context.globalAlpha = 1;
  context.fillStyle = "#8eb0c1";
  context.textAlign = "left";
  context.fillText(formatIST(visiblePrice[0].t), margin.left, height - 8);
  const endLabel = formatIST(visiblePrice.at(-1).t);
  context.fillText(endLabel, width - margin.right - context.measureText(endLabel).width, height - 8);
  return { code: "READY", points: points.length, selectionVisible: true };
}

function addFact(parent, label, value) {
  const node = element("div", "fact");
  node.append(element("span", "", label), element("strong", "", value));
  parent.append(node);
}

function renderCodexReplayAnswer(result) {
  const shell = byId("codexReplayAnswer");
  const answer = result;
  const textbook = result.market_profile_analysis || {};
  const scenario = result.backend_scenario || {};
  shell.replaceChildren();
  const header = element("div", "commentary-summary-row");
  header.append(
    element("strong", "commentary-bias", `${answer.bias || "NO_EDGE"} · ${answer.horizon_minutes || 30}m`),
    element("span", "state-pill neutral", `${answer.confidence || "LOW"} confidence`),
    element("span", "commentary-levels", `S ${(answer.support || []).join("/") || "—"} · R ${(answer.resistance || []).join("/") || "—"}`)
  );
  shell.append(header);
  shell.append(element("p", "commentary-shift", `SHIFT · ${answer.what_changed || "No material control migration"}`));
  const comparison = element("div", "analysis-comparison");
  const backend = element("section", "analysis-block backend-analysis");
  backend.append(element("h4", "", "Backend directional analysis"));
  backend.append(element("strong", "scenario-name", `${scenario.scenario || "NO_EDGE"} · ${scenario.stage || "UNRESOLVED"}`));
  for (const row of (scenario.evidence || []).slice(0, 4)) backend.append(element("p", "", row));
  backend.append(element("p", "commentary-outlook", `EXPECTED · ${scenario.expected || answer.possible_outcome || "No directional edge."}`));
  backend.append(element("p", "commentary-invalidation", `CONFIRM · ${scenario.confirmation || answer.confirmation || "unavailable"}`));
  backend.append(element("p", "commentary-invalidation", `INVALIDATE · ${scenario.invalidation || answer.invalidation || "unavailable"}`));
  if ((scenario.missing_evidence || []).length) backend.append(element("p", "commentary-warning", `MISSING · ${scenario.missing_evidence.join(", ")}`));
  const codex = element("section", "analysis-block codex-analysis");
  codex.append(element("h4", "", "Codex interpretation"));
  codex.append(element("p", "", answer.summary || "No Codex summary was returned."));
  comparison.append(backend, codex);
  shell.append(comparison);
  if (textbook.basis_warning) shell.append(element("p", "commentary-warning", `CHECK · ${textbook.basis_warning}`));
  const details = element("details", "commentary-details");
  details.append(element("summary", "", "Scenario rules and market-profile details"));
  if ((scenario.rules || []).length) details.append(element("p", "", `Rules: ${scenario.rules.join(" · ")}`));
  details.append(element("p", "", `Market profile: ${textbook.concise_read || "Unavailable"}`));
  for (const [heading, values] of [["Rule observations", textbook.observations], ["Cautions", textbook.cautions]]) {
    if (!Array.isArray(values) || !values.length) continue;
    details.append(element("h4", "", heading));
    const list = element("ul");
    for (const value of values) list.append(element("li", "", String(value)));
    details.append(list);
  }
  details.append(element("p", "codex-replay-meta", `Facts ${String(result.verified_prefix_sha256 || "").slice(0, 16)} · Codex ${result.codex_status || "unknown"}`));
  shell.append(details);
  shell.append(element(
    "p", "codex-replay-meta",
    `As of ${result.causal_as_of} · ${result.delivery_state || "STORED"}${result.stale_for_cursor ? " · generating exact cursor" : ""}`
  ));
  shell.hidden = false;
}

async function refreshReplayCodexStatus() {
  const pill = byId("codexReplayStatus");
  const button = byId("codexExplainButton");
  try {
    const response = await fetch("/api/v1/codex/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = await response.json();
    const ready = status.prompting_enabled === true && status.state === "REACHABLE_UNVERIFIED";
    pill.textContent = ready ? "Codex · central commentary ready"
      : status.prompting_enabled === true ? "Codex · worker offline" : "Codex · asks disabled";
    pill.className = `state-pill ${ready ? "candidate" : "neutral"}`;
    pill.title = status.detail || "Replay Codex status";
    button.disabled = !ready;
  } catch (error) {
    pill.textContent = "Codex · status error";
    pill.className = "state-pill neutral";
    pill.title = String(error);
    button.disabled = true;
  }
}

async function replay() {
  const app = byId("replayApp");
  if (!app) return;
  const errorShell = byId("replayError");
  try {
    const requested = new URLSearchParams(location.search).get("session");
    if (!requested) throw new Error("No session was requested.");
    const catalog = await json("catalog.json");
    const entry = catalog.sessions.find((row) => row.session === requested);
    if (!entry) throw new Error("The requested session is not in the verified catalog.");
    const payload = await json(entry.payload);
    const rows = unpack(payload.price);
    const oiRows = unpack(payload.futures_oi || { fields: [], rows: [] });
    const inventoryBlock = payload.inventory_context || {
      status: "UNAVAILABLE",
      reason: "INVENTORY_CONTEXT_NOT_RETAINED",
      feature_flags: {},
      controls: []
    };
    const intradayBlock = payload.intraday_inventory || {
      status: "UNAVAILABLE",
      reason: "INTRADAY_INVENTORY_NOT_RETAINED",
      feature_flags: {},
      fields: [],
      rows: []
    };
    configureInventoryControls(inventoryBlock, intradayBlock);
    syncInventoryFamilyControls(inventoryBlock, intradayBlock);
    const strikeBlock = payload.option_strike_oi || {
      fields: [], rows: [], retained: false, volume_retained: false,
      strike_selection: { available: false, CE: [], PE: [] }
    };
    const strikeRows = unpack(strikeBlock);
    const strikeRetained = strikeBlock.retained === true;
    const strikeVolumeRetained = strikeBlock.volume_retained === true;
    const strikeSelection = strikeBlock.strike_selection
      || strikeBlock.day_open_selection
      || { available: false, CE: [], PE: [] };
    const selectedSymbols = new Set([
      ...(Array.isArray(strikeSelection.CE) ? strikeSelection.CE : []),
      ...(Array.isArray(strikeSelection.PE) ? strikeSelection.PE : [])
    ].map((contract) => contract.symbol));
    const strikeFlowRows = strikeRows.filter((row) => selectedSymbols.has(row.symbol));
    const flowPanels = [
      { panel: "ceOiFlowPanel", optionType: "CE", metric: "oi", canvas: "ceOiFlowChart", status: "ceOiFlowStatus", legend: "ceOiFlowLegend" },
      { panel: "peOiFlowPanel", optionType: "PE", metric: "oi", canvas: "peOiFlowChart", status: "peOiFlowStatus", legend: "peOiFlowLegend" },
      { panel: "ceVolumeFlowPanel", optionType: "CE", metric: "volume", canvas: "ceVolumeFlowChart", status: "ceVolumeFlowStatus", legend: "ceVolumeFlowLegend" },
      { panel: "peVolumeFlowPanel", optionType: "PE", metric: "volume", canvas: "peVolumeFlowChart", status: "peVolumeFlowStatus", legend: "peVolumeFlowLegend" }
    ];
    const states = unpack(payload.states);
    if (!rows.length) throw new Error("The session contains no synchronized basis observations.");
    if (states.length !== rows.length) throw new Error("The basis and state projections are inconsistent.");
    const transitions = payload.transitions.slice().sort((a, b) => a.published_at.localeCompare(b.published_at));
    const zones = (payload.confirmed_zones || []).slice().sort((a, b) => a.confirmed_at.localeCompare(b.confirmed_at));
    const gapToleranceSeconds = Number(
      payload.config.horizon_gap_tolerance_seconds || payload.config.merge_gap_seconds || 15
    );
    const oiGapToleranceSeconds = Number(payload.config.participation_max_age_seconds || 300);
    let cursor = 0;
    let timer = null;
    let seenTransitionCount = 0;
    byId("sessionTitle").textContent = `${payload.session} · causal replay`;
    const slider = byId("replaySlider");
    slider.max = String(rows.length - 1);
    for (const [scope, dates] of Object.entries(payload.actual_scope_sessions)) {
      const row = element("div", "scope-row");
      row.append(element("strong", "", scope), element("span", "", dates.length ? dates.join(" · ") : "Insufficient eligible prior sessions"));
      byId("scopeList").append(row);
    }
    const facts = byId("runFacts");
    addFact(facts, "Method", payload.summary.methodology_version);
    addFact(facts, "Config hash", payload.summary.config_sha256.slice(0, 12));
    addFact(facts, "Match tolerance", `${payload.config.match_tolerance_ms} ms`);
    addFact(facts, "Production weight", String(payload.summary.production_weight));
    addFact(facts, "Ledger", payload.summary.ledger.valid ? "Verified" : "Invalid");
    addFact(facts, "Diagnostics", String(payload.summary.diagnostic_count));

    const render = () => {
      slider.value = String(cursor);
      const current = rows[cursor];
      const currentState = states[cursor];
      const asOf = new Date(current.t).getTime();
      const visible = transitions.filter((item) => new Date(item.published_at).getTime() <= asOf);
      const visibleZones = visibleConfirmedZones(zones, asOf);
      syncInventoryFamilyControls(inventoryBlock, intradayBlock);
      const inventoryLines = inventoryDisplayLines(inventoryBlock, intradayBlock, asOf);
      byId("replayClock").textContent = `${payload.session} ${formatIST(current.t)} IST`;
      byId("replayProgress").textContent = `${cursor + 1} / ${rows.length} synchronized observations`;
      if (!byId("marketPanel").hidden) {
        const basisPlacement = marketOiChart(
          byId("priceChart"), rows, oiRows, cursor, visibleZones,
          gapToleranceSeconds, oiGapToleranceSeconds, inventoryLines,
          byId("frameBasis").checked
        );
        byId("basisPlacement").textContent = basisPlacement === "BETWEEN"
          ? "Basis lane · between Index/Futures"
          : basisPlacement === "TOP" ? "Basis lane · top"
            : basisPlacement === "HIDDEN" ? "Basis lane · hidden" : "Basis lane · unavailable";
      }
      if (!byId("inventoryListPanel").hidden) {
        renderInventoryLevelList(inventoryBlock, intradayBlock, inventoryLines);
      }
      const strikeSnapshot = latestStrikeSnapshot(
        strikeRows, rows, cursor, strikeSelection, strikeRetained, oiGapToleranceSeconds
      );
      const sharedMaximumOi = Math.max(
        1,
        ...strikeSnapshot.rows.map((row) => Number(row.oi)).filter(Number.isFinite)
      );
      for (const [panelId, optionType, canvasId, statusId] of [
        ["ceSnapshotPanel", "CE", "ceStrikeChart", "ceStrikeStatus"],
        ["peSnapshotPanel", "PE", "peStrikeChart", "peStrikeStatus"]
      ]) {
        if (byId(panelId).hidden) continue;
        const strikeState = strikeOiSnapshotChart(
          byId(canvasId), strikeSnapshot, Number(current.i), optionType,
          strikeSelection, sharedMaximumOi
        );
        const status = byId(statusId);
        status.textContent = strikeState.code === "READY"
          ? `${strikeSnapshot.expiry} · ${formatIST(strikeSnapshot.receipt)}`
          : strikeState.code === "AWAITING_0945_SELECTION"
            ? "Awaiting 09:45"
            : strikeState.code === "REFERENCE_UNAVAILABLE"
              ? "09:45 close unavailable"
              : strikeState.code === "STALE_RECEIPT"
                ? "Stale receipt"
                : "No receipt yet";
      }
      for (const panel of flowPanels) {
        if (byId(panel.panel).hidden) continue;
        const flowState = strikeFlowChart(
          byId(panel.canvas), strikeFlowRows, rows, cursor, panel.optionType, panel.metric,
          strikeSelection, strikeVolumeRetained
        );
        const contracts = Array.isArray(strikeSelection[panel.optionType])
          ? strikeSelection[panel.optionType] : [];
        const legend = byId(panel.legend);
        if (strikeSelection.available === true) {
          renderStrikeFlowLegend(legend, contracts, flowState.selectionVisible);
        } else {
          legend.replaceChildren(element("span", "", "Full-session raw-plus-OI replay required."));
        }
        const status = byId(panel.status);
        status.textContent = flowState.code === "READY"
          ? `ATM ${number(strikeSelection.atm, 0)} · ${flowState.points} bars`
          : flowState.code === "AWAITING_SELECTION" || flowState.code === "NO_CHANGE"
            ? "Awaiting change"
            : flowState.code === "VOLUME_REPLAY_REQUIRED" || flowState.code === "REPLAY_REQUIRED"
              ? "Replay required"
              : "No data";
      }
      const visibleOi = oiRows.filter((row) => new Date(row.t).getTime() <= asOf);
      const latestOi = visibleOi.at(-1);
      const oiAgeSeconds = latestOi ? Math.max(0, (asOf - new Date(latestOi.t).getTime()) / 1000) : null;
      const oiFresh = oiAgeSeconds !== null && oiAgeSeconds <= oiGapToleranceSeconds;
      const readout = byId("currentReadout");
      readout.replaceChildren();
      for (const [label, value] of [
        ["Index", number(current.i)], ["Futures", number(current.f)], ["Basis", number(current.b)],
        ["Basis state", currentState.s], ["Supporting horizons", String(currentState.n)],
        ["Sync age", `${number(current.age, 0)} ms`],
        ["Futures OI", latestOi ? number(latestOi.oi, 0) : "Unavailable"],
        ["ΔOI", latestOi && latestOi.d !== null ? number(latestOi.d, 0) : "Gap reset / unavailable"],
        ["OI receipt", latestOi ? `${formatIST(latestOi.t)} IST` : "Unavailable"],
        ["OI status", latestOi ? `${oiFresh ? "Fresh" : "Stale"} · ${number(oiAgeSeconds, 0)} s` : "Not retained"]
      ]) {
        const node = element("div", "readout"); node.append(element("span", "", label), element("strong", "", value)); readout.append(node);
      }
      const latest = visible.at(-1);
      const status = byId("basisStatus");
      const confirmed = latest && (latest.state === "CONFIRMED" || latest.state === "ACTIVE");
      const candidate = currentState.s.endsWith("_CANDIDATE");
      const stateColour = confirmed ? latest.colour.toLowerCase() : candidate ? "candidate" : "neutral";
      status.className = `state-pill ${stateColour}`;
      status.textContent = confirmed
        ? `${latest.colour} · ${latest.state}`
        : candidate ? `${currentState.s} · unconfirmed` : `${currentState.s} · no confirmed zone`;
      const list = byId("transitionList");
      list.replaceChildren();
      if (!visible.length) list.append(element("p", "empty", "No transition was published by this receipt time."));
      for (const item of visible.slice().reverse()) {
        const card = element("article", `transition-card ${transitionVisualClass(item)}`);
        const head = element("div", "transition-head");
        head.append(element("span", "", `${item.colour} · ${item.state}`), element("time", "", `${formatIST(item.published_at)} IST`));
        card.append(head, element("p", "", item.reason_codes.join(" · ")), element("p", "", item.episode_id));
        list.append(card);
      }
      byId("transitionCount").textContent = `${visible.length} of ${transitions.length} visible`;
      const appeared = visible.length > seenTransitionCount;
      seenTransitionCount = visible.length;
      if (appeared && byId("pauseImportant").checked && timer) stop();
      byId("previousEvent").disabled = !transitions.some((item) => new Date(item.published_at).getTime() < asOf);
      byId("nextEvent").disabled = !transitions.some((item) => new Date(item.published_at).getTime() > asOf);
    };
    const stop = () => { if (timer) window.clearInterval(timer); timer = null; };
    const play = () => {
      stop();
      const speed = Number(byId("speedSelect").value);
      timer = window.setInterval(() => {
        if (cursor >= rows.length - 1) { stop(); return; }
        cursor += 1; render();
      }, Math.max(16, 1000 / speed));
    };
    const jump = (direction) => {
      stop();
      const current = new Date(rows[cursor].t).getTime();
      const targets = transitions.map((item) => new Date(item.published_at).getTime());
      const target = direction > 0 ? targets.find((time) => time > current) : targets.slice().reverse().find((time) => time < current);
      if (target === undefined) return;
      if (direction > 0) cursor = rows.findIndex((row) => new Date(row.t).getTime() >= target);
      else {
        cursor = 0;
        rows.forEach((row, index) => { if (new Date(row.t).getTime() <= target) cursor = index; });
      }
      seenTransitionCount = transitions.filter((item) => new Date(item.published_at).getTime() <= new Date(rows[cursor].t).getTime()).length;
      render();
    };
    byId("playButton").addEventListener("click", play);
    byId("pauseButton").addEventListener("click", stop);
    byId("previousEvent").addEventListener("click", () => jump(-1));
    byId("nextEvent").addEventListener("click", () => jump(1));
    byId("codexExplainButton").addEventListener("click", async () => {
      stop();
      const button = byId("codexExplainButton");
      const answerShell = byId("codexReplayAnswer");
      const requestedReceipt = rows[cursor].t;
      button.disabled = true;
      button.textContent = "Loading…";
      answerShell.replaceChildren(element("p", "", `Loading central commentary through ${formatIST(requestedReceipt)} IST…`));
      answerShell.hidden = false;
      try {
        const query = new URLSearchParams({session: payload.session, as_of: requestedReceipt});
        let delivered = false;
        for (let attempt = 0; attempt < 50; attempt += 1) {
          const response = await fetch(`/api/v1/commentary/current?${query}`, {cache: "no-store"});
          const result = await response.json();
          if (!response.ok && response.status !== 202) throw new Error(result.error || `HTTP ${response.status}`);
          if (response.status === 200 && result.stale_for_cursor !== true) {
            renderCodexReplayAnswer(result);
            delivered = true;
            break;
          }
          answerShell.replaceChildren(element("p", "", `Central commentary ${result.delivery_state || "PENDING"}…`));
          await new Promise((resolve) => window.setTimeout(resolve, 2000));
        }
        if (!delivered) throw new Error("central commentary remained pending beyond 100 seconds");
      } catch (error) {
        answerShell.replaceChildren(element("p", "", `Central commentary unavailable: ${error.message}`));
        answerShell.hidden = false;
      } finally {
        button.textContent = "Show commentary";
        await refreshReplayCodexStatus();
      }
    });
    for (const id of INVENTORY_TOGGLE_IDS) {
      byId(id).addEventListener("change", render);
    }
    restoreFrameVisibility();
    applyFrameVisibility();
    installFrameMaximizeControls();
    for (const id of [...Object.keys(FRAME_TARGETS), ...OVERLAY_TOGGLE_IDS]) {
      byId(id).addEventListener("change", () => {
        applyFrameVisibility();
        render();
      });
    }
    slider.addEventListener("input", () => { stop(); cursor = Number(slider.value); seenTransitionCount = 0; render(); });
    window.addEventListener("resize", render);
    app.hidden = false;
    render();
    refreshReplayCodexStatus();
  } catch (error) {
    errorShell.hidden = false;
    errorShell.querySelector("section").textContent = `Replay could not be loaded: ${error.message}`;
  }
}

landing();
replay();
