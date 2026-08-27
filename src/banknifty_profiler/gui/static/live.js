(() => {
  "use strict";

  const CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL";
  const STORE_KEY = "r6e1r-live-display-v1";
  const HORIZONS = ["3D", "2D", "1D", "ID"];
  const FAMILIES = [
    "BN_REF_FUT_VOLUME_VPOC", "FUT_POS_OI_VPOC", "FUT_NEG_OI_VPOC",
    "CE_POS_OI_VPOC", "CE_NEG_OI_VPOC", "PE_POS_OI_VPOC", "PE_NEG_OI_VPOC",
  ];
  const LABELS = {
    BN_REF_FUT_VOLUME_VPOC: "BN-REF FUT VOL-VPOC",
    FUT_POS_OI_VPOC: "FUT +ΔOI", FUT_NEG_OI_VPOC: "FUT −ΔOI",
    CE_POS_OI_VPOC: "CE +ΔOI", CE_NEG_OI_VPOC: "CE −ΔOI",
    PE_POS_OI_VPOC: "PE +ΔOI", PE_NEG_OI_VPOC: "PE −ΔOI",
  };
  const COLOURS = {
    BN_REF_FUT_VOLUME_VPOC: "#b7c9d3", FUT_POS_OI_VPOC: "#ffc857",
    FUT_NEG_OI_VPOC: "#ff5f78", CE_POS_OI_VPOC: "#f2a65a",
    CE_NEG_OI_VPOC: "#f88dad", PE_POS_OI_VPOC: "#57e3c3",
    PE_NEG_OI_VPOC: "#64b5f6",
  };
  const DEFAULTS = {
    market: { index: true, futures: true, basis: false },
    masters: { "3D": true, "2D": true, "1D": true, ID: true },
    children: {}, events: { confirmation: true, lifecycle: true },
    session: "latest", pollSeconds: 5,
  };
  for (const horizon of HORIZONS) {
    for (const family of FAMILIES) {
      DEFAULTS.children[`${horizon}|${family}`] =
        family === "BN_REF_FUT_VOLUME_VPOC" || family.startsWith("FUT_");
    }
  }

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const time = (value) => Date.parse(value);
  const numeric = (value) => Number.isFinite(Number(value));
  const clone = (value) => JSON.parse(JSON.stringify(value));

  function loadSettings() {
    const settings = clone(DEFAULTS);
    try {
      const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      for (const section of ["market", "masters", "children", "events"]) {
        if (!saved[section] || typeof saved[section] !== "object") continue;
        for (const key of Object.keys(settings[section])) {
          if (typeof saved[section][key] === "boolean") settings[section][key] = saved[section][key];
        }
      }
      if (["latest", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-18", "2026-08-19", "2026-08-20"].includes(saved.session)) {
        settings.session = saved.session;
      }
      if ([0, 2, 5, 15].includes(Number(saved.pollSeconds))) settings.pollSeconds = Number(saved.pollSeconds);
    } catch (_) {
      // Storage is optional; deterministic in-memory defaults remain available.
    }
    return settings;
  }

  const state = {
    settings: loadSettings(), chart: null, participation: null, sessionInfo: null,
    busy: false, timer: null, lastPoll: null, requestError: "",
  };

  function persist() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state.settings)); } catch (_) { /* optional */ }
  }

  function unpack(packed) {
    if (!packed || !Array.isArray(packed.fields) || !Array.isArray(packed.rows)) return [];
    return packed.rows.map((row) => Object.fromEntries(packed.fields.map((field, index) => [field, row[index]])));
  }

  async function fetchJson(path) {
    const response = await fetch(path, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    return response.json();
  }

  function query() {
    return state.settings.session === "latest" ? "" : `?date=${encodeURIComponent(state.settings.session)}`;
  }

  function setConnection(text, kind) {
    const badge = $("#connectionBadge");
    badge.textContent = text;
    badge.className = `availability ${kind}`;
  }

  async function refresh() {
    if (state.busy) return;
    state.busy = true;
    setConnection("UPDATING", "missing");
    try {
      const suffix = query();
      // Fetch sequentially so a poll never materializes multiple copies of a
      // session snapshot at once. Dense participation is server-capped.
      const chart = await fetchJson(`/api/chart${suffix}`);
      const participation = await fetchJson(`/api/participation${suffix ? `${suffix}&limit=1200` : "?limit=1200"}`);
      const expectedMode = state.settings.session === "latest" ? "LIVE_LATEST" : "HISTORICAL_REPLAY";
      const sessionInfo = !state.sessionInfo || state.sessionInfo.session_date !== chart.session_date || state.sessionInfo.mode !== expectedMode
        ? await fetchJson(`/api/session${suffix}`)
        : state.sessionInfo;
      if (chart.classification !== CLASSIFICATION || sessionInfo.classification !== CLASSIFICATION) {
        throw new Error("CLASSIFICATION_CONTRACT");
      }
      state.chart = chart;
      state.participation = participation;
      state.sessionInfo = sessionInfo;
      state.lastPoll = new Date();
      state.requestError = "";
      if (state.settings.session === "latest" && chart.stale_warning) {
        setConnection("STALE DATA · LAST VALID CHART", "stale");
      } else {
        setConnection(state.settings.session === "latest" ? "LIVE POLLING" : "HISTORICAL REPLAY", "available");
      }
      render();
    } catch (error) {
      state.requestError = String(error && error.message ? error.message : "DATA_UNAVAILABLE");
      setConnection("DATA UNAVAILABLE", "stale");
      renderOperational();
    } finally {
      state.busy = false;
    }
  }

  function restartPolling() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
    if (state.settings.pollSeconds > 0) {
      state.timer = setInterval(refresh, state.settings.pollSeconds * 1000);
    }
  }

  function layer(horizon) {
    return state.chart?.availability?.layers?.[horizon] || { state: "NOT_YET_AVAILABLE", reason: "NO_RECORD" };
  }

  function availabilityClass(value) {
    if (value === "AVAILABLE" || String(value).startsWith("LIVE_")) return "available";
    if (String(value).includes("STALE") || String(value).includes("SUSPENDED")) return "stale";
    return "missing";
  }

  function buildControls() {
    const host = $("#horizonControls");
    host.replaceChildren();
    for (const horizon of HORIZONS) {
      const row = document.createElement("div");
      row.className = "toggle-row horizon-row";
      const master = document.createElement("label");
      master.className = "toggle horizon-master";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.master = horizon;
      input.checked = state.settings.masters[horizon];
      master.append(input, document.createTextNode(horizon === "ID" ? "Intraday" : horizon));
      row.append(master);

      for (const family of FAMILIES) {
        const label = document.createElement("label");
        label.className = "toggle";
        label.dataset.horizonChild = horizon;
        label.classList.toggle("hidden", !state.settings.masters[horizon]);
        const child = document.createElement("input");
        child.type = "checkbox";
        child.dataset.child = `${horizon}|${family}`;
        child.checked = state.settings.children[child.dataset.child];
        const swatch = document.createElement("span");
        swatch.className = `swatch ${horizon === "ID" ? "step" : "fixed"} family-${family}`;
        label.append(child, swatch, document.createTextNode(LABELS[family]));
        row.append(label);
      }
      const item = layer(horizon);
      const badge = document.createElement("span");
      badge.className = `availability ${availabilityClass(item.state)}`;
      badge.textContent = item.state;
      badge.title = item.reason;
      row.append(badge);
      host.append(row);
    }
    bindDisplayControls();
  }

  function bindDisplayControls() {
    $$('[data-market]').forEach((input) => {
      input.checked = state.settings.market[input.dataset.market];
      input.onchange = () => {
        state.settings.market[input.dataset.market] = input.checked;
        persist(); renderCharts();
      };
    });
    $$('[data-event]').forEach((input) => {
      input.checked = state.settings.events[input.dataset.event];
      input.onchange = () => {
        state.settings.events[input.dataset.event] = input.checked;
        persist(); renderCharts();
      };
    });
    $$('[data-master]').forEach((input) => {
      input.onchange = () => {
        state.settings.masters[input.dataset.master] = input.checked;
        const row = input.closest(".horizon-row");
        row?.querySelectorAll("[data-horizon-child]").forEach((label) => {
          label.classList.toggle("hidden", !input.checked);
        });
        persist(); renderCharts();
      };
    });
    $$('[data-child]').forEach((input) => {
      input.onchange = () => {
        state.settings.children[input.dataset.child] = input.checked;
        persist(); renderCharts();
      };
    });
  }

  function setupCanvas(canvas, height) {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 1200;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { context, width, height, left: 64, right: width - 18, top: 18, bottom: height - 36 };
  }

  function domain() {
    const start = time(state.chart?.session?.start);
    const end = time(state.chart?.session?.end);
    return { start, end, valid: Number.isFinite(start) && Number.isFinite(end) && end > start };
  }

  function xMap(at, geometry, bounds) {
    return geometry.left + (at - bounds.start) / (bounds.end - bounds.start) * (geometry.right - geometry.left);
  }

  function segments(rows, timeKey, valueKey, maximumGap = 30000) {
    const result = [];
    let part = [];
    let previous = -Infinity;
    // Index, Futures and Basis carry different canonical receipt clocks.  Sort
    // each path on the clock it actually renders instead of relying on the
    // packed row order (or on the synchronized Basis clock) to order all three.
    const ordered = [...rows].sort((left, right) => {
      const leftAt = time(left[timeKey]);
      const rightAt = time(right[timeKey]);
      if (!Number.isFinite(leftAt)) return Number.isFinite(rightAt) ? 1 : 0;
      if (!Number.isFinite(rightAt)) return -1;
      return leftAt - rightAt;
    });
    for (const row of ordered) {
      const at = time(row[timeKey]);
      const value = Number(row[valueKey]);
      if (!Number.isFinite(at) || !Number.isFinite(value)) continue;
      if (at - previous > maximumGap && part.length) { result.push(part); part = []; }
      part.push([at, value, row]);
      previous = at;
    }
    if (part.length) result.push(part);
    return result;
  }

  function drawAxes(geometry, bounds, minimum, maximum) {
    const { context, left, right, top, bottom } = geometry;
    context.strokeStyle = "#234050";
    context.fillStyle = "#9db4c2";
    context.font = "11px system-ui";
    for (let index = 0; index <= 12; index += 1) {
      const at = bounds.start + (bounds.end - bounds.start) * index / 12;
      const x = xMap(at, geometry, bounds);
      context.beginPath(); context.moveTo(x, top); context.lineTo(x, bottom); context.stroke();
      if (index % 2 === 0) {
        context.fillText(new Date(at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }), x - 16, bottom + 17);
      }
    }
    for (let index = 0; index <= 5; index += 1) {
      const y = top + (bottom - top) * index / 5;
      const value = maximum - (maximum - minimum) * index / 5;
      context.beginPath(); context.moveTo(left, y); context.lineTo(right, y); context.stroke();
      context.fillText(value.toFixed(0), 4, y + 4);
    }
  }

  function activeEpisode(at, episodes) {
    let found = null;
    for (const episode of episodes) {
      const start = time(episode.confirmation_timestamp);
      const parsedEnd = time(episode.episode_end_timestamp);
      const end = Number.isFinite(parsedEnd) ? parsedEnd : Infinity;
      if (start <= at && at <= end) found = episode;
    }
    return found;
  }

  function drawPath(geometry, bounds, parts, minimum, maximum, colour, episodes = null) {
    const yMap = (value) => geometry.bottom - (value - minimum) / (maximum - minimum) * (geometry.bottom - geometry.top);
    for (const part of parts) {
      for (let index = 1; index < part.length; index += 1) {
        const previous = part[index - 1];
        const current = part[index];
        const episode = episodes ? activeEpisode(current[0], episodes) : null;
        geometry.context.strokeStyle = episode ? (episode.colour === "GREEN" ? "#40dc83" : "#ff5f78") : colour;
        geometry.context.lineWidth = 1.6;
        geometry.context.beginPath();
        geometry.context.moveTo(xMap(previous[0], geometry, bounds), yMap(previous[1]));
        geometry.context.lineTo(xMap(current[0], geometry, bounds), yMap(current[1]));
        geometry.context.stroke();
      }
    }
  }

  function inventoryGroups(rows, bounds) {
    const groups = new Map();
    for (const row of rows) {
      const horizon = row.horizon;
      const key = `${horizon}|${row.family}`;
      const at = time(row.control_effective_timestamp);
      const value = Number(row.control_value);
      if (!HORIZONS.includes(horizon) || !Number.isFinite(at) || !Number.isFinite(value)) continue;
      if (layer(horizon).state !== "AVAILABLE" || !state.settings.masters[horizon] || !state.settings.children[key]) continue;
      if (horizon === "ID") {
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push([at, value]);
      } else {
        groups.set(key, [[bounds.start, value], [bounds.end, value]]);
      }
    }
    return groups;
  }

  function drawInventory(geometry, bounds, groups, minimum, maximum) {
    const yMap = (value) => geometry.bottom - (value - minimum) / (maximum - minimum) * (geometry.bottom - geometry.top);
    for (const [key, rows] of groups) {
      const [horizon, family] = key.split("|");
      geometry.context.strokeStyle = COLOURS[family];
      geometry.context.lineWidth = horizon === "ID" ? 1.4 : 2;
      geometry.context.setLineDash(horizon === "ID" ? [] : [7, 5]);
      geometry.context.beginPath();
      if (horizon === "ID") {
        for (let index = 0; index < rows.length; index += 1) {
          const [at, value] = rows[index];
          if (index === 0) geometry.context.moveTo(xMap(at, geometry, bounds), yMap(value));
          else {
            const previous = rows[index - 1];
            geometry.context.lineTo(xMap(at, geometry, bounds), yMap(previous[1]));
            geometry.context.lineTo(xMap(at, geometry, bounds), yMap(value));
          }
          if (index === rows.length - 1) geometry.context.lineTo(geometry.right, yMap(value));
        }
      } else {
        geometry.context.moveTo(geometry.left, yMap(rows[0][1]));
        geometry.context.lineTo(geometry.right, yMap(rows[0][1]));
      }
      geometry.context.stroke();
      geometry.context.setLineDash([]);
    }
  }

  function drawMarkers(geometry, bounds, episodes, lifecycle) {
    if (state.settings.events.confirmation) {
      for (const episode of episodes) {
        const at = time(episode.confirmation_timestamp);
        if (!Number.isFinite(at)) continue;
        geometry.context.fillStyle = episode.colour === "GREEN" ? "#40dc83" : "#ff5f78";
        geometry.context.beginPath(); geometry.context.arc(xMap(at, geometry, bounds), geometry.top + 8, 4, 0, Math.PI * 2); geometry.context.fill();
      }
    }
    if (state.settings.events.lifecycle) {
      geometry.context.fillStyle = "#ffc857";
      for (const item of lifecycle) {
        const at = time(item.state_entry_timestamp);
        if (!Number.isFinite(at)) continue;
        const x = xMap(at, geometry, bounds);
        const y = geometry.bottom - 7;
        geometry.context.beginPath(); geometry.context.moveTo(x, y - 5); geometry.context.lineTo(x - 5, y + 4); geometry.context.lineTo(x + 5, y + 4); geometry.context.closePath(); geometry.context.fill();
      }
    }
  }

  function renderCharts() {
    if (!state.chart) return;
    const rows = unpack(state.chart.price).sort((a, b) => time(a.t) - time(b.t));
    const inventory = unpack(state.chart.inventory).sort((a, b) => time(a.control_effective_timestamp) - time(b.control_effective_timestamp));
    const episodes = unpack(state.chart.episodes).sort((a, b) => time(a.confirmation_timestamp) - time(b.confirmation_timestamp));
    const lifecycle = unpack(state.chart.lifecycle).sort((a, b) => time(a.state_entry_timestamp) - time(b.state_entry_timestamp));
    const bounds = domain();
    const geometry = setupCanvas($("#price"), 420);
    if (!bounds.valid) {
      geometry.context.fillStyle = "#ffc857";
      geometry.context.fillText("WAITING FOR A SESSION CLOCK", geometry.left, geometry.top + 20);
      return;
    }
    const indexParts = segments(rows, "it", "i");
    const futuresParts = segments(rows, "ft", "f");
    const groups = inventoryGroups(inventory, bounds);
    const values = [];
    if (state.settings.market.index) indexParts.flat().forEach((point) => values.push(point[1]));
    if (state.settings.market.futures) futuresParts.flat().forEach((point) => values.push(point[1]));
    for (const points of groups.values()) points.forEach((point) => values.push(point[1]));
    if (!values.length) {
      geometry.context.fillStyle = "#ffc857";
      geometry.context.fillText("NO VALID MARKET DATA IN THIS PROJECTION", geometry.left, geometry.top + 20);
      $("#scaleInfo").textContent = "The last valid chart remains available whenever the analytical projection retains it.";
      renderBasis(rows, bounds);
      return;
    }
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    const padding = Math.max(20, (maximum - minimum) * 0.05);
    minimum -= padding; maximum += padding;
    drawAxes(geometry, bounds, minimum, maximum);
    drawInventory(geometry, bounds, groups, minimum, maximum);
    if (state.settings.market.index) drawPath(geometry, bounds, indexParts, minimum, maximum, "#45c7ff", episodes);
    if (state.settings.market.futures) drawPath(geometry, bounds, futuresParts, minimum, maximum, "#f5f7fa");
    drawMarkers(geometry, bounds, episodes, lifecycle);
    $("#scaleInfo").textContent = `Separate paths: Index ${indexParts.flat().length} points · Futures ${futuresParts.flat().length} points · scale ${minimum.toFixed(2)}–${maximum.toFixed(2)}`;
    renderBasis(rows, bounds);
  }

  function renderBasis(rows, bounds) {
    const wrap = $("#basisWrap");
    wrap.classList.toggle("hidden", !state.settings.market.basis);
    if (!state.settings.market.basis || !bounds.valid) return;
    const geometry = setupCanvas($("#basis"), 130);
    const parts = segments(rows, "t", "b");
    const values = parts.flat().map((point) => point[1]);
    if (!values.length) return;
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    const padding = Math.max(5, (maximum - minimum) * 0.05);
    minimum -= padding; maximum += padding;
    drawAxes(geometry, bounds, minimum, maximum);
    drawPath(geometry, bounds, parts, minimum, maximum, "#b79cff");
  }

  function formatAge(value) {
    return numeric(value) ? `${Number(value).toFixed(1)}s` : "unavailable";
  }

  function renderAvailability() {
    const availability = state.chart?.availability || {};
    const overall = availability.overall_state || "NO_VALID_MARKET_DATA";
    const badge = $("#overallBadge");
    badge.textContent = overall.replaceAll("_", " ");
    badge.className = `availability ${availabilityClass(overall)}`;
    const summary = $("#availability");
    summary.replaceChildren();
    for (const horizon of HORIZONS) {
      const item = layer(horizon);
      const value = document.createElement("span");
      value.className = `availability ${availabilityClass(item.state)}`;
      value.textContent = `${horizon === "ID" ? "Intraday" : horizon}: ${item.state}`;
      value.title = item.reason;
      summary.append(value);
    }
    const ages = state.chart?.receipt_ages_seconds || {};
    const receipts = $("#receiptAges");
    receipts.replaceChildren();
    const states = {
      INDEX: availability.index_state, FUTURES: availability.futures_state,
      FUTURES_OI: availability.futures_oi_state, CE: availability.ce_state, PE: availability.pe_state,
    };
    for (const component of Object.keys(states)) {
      const value = document.createElement("span");
      value.className = `availability ${availabilityClass(states[component])}`;
      value.textContent = `${component.replace("FUTURES_OI", "Futures OI")}: ${states[component] || "NOT_YET_AVAILABLE"} · age ${formatAge(ages[component])}`;
      receipts.append(value);
    }
    const details = $("#layerDetails");
    details.replaceChildren();
    for (const horizon of HORIZONS) {
      const item = layer(horizon);
      const card = document.createElement("div");
      card.className = "layer-card";
      const title = document.createElement("b");
      title.textContent = horizon === "ID" ? "Intraday" : horizon;
      const stateText = document.createElement("span");
      stateText.className = availabilityClass(item.state);
      stateText.textContent = item.state;
      const reason = document.createElement("small");
      reason.textContent = item.reason;
      card.append(title, stateText, reason);
      details.append(card);
    }
  }

  function latestBy(rows, key) {
    let value = null;
    let latestAt = -Infinity;
    for (const row of Array.isArray(rows) ? rows : []) {
      const at = time(row?.[key]);
      if (!Number.isFinite(at) || at < latestAt) continue;
      value = row;
      latestAt = at;
    }
    return value;
  }

  function observable(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function movement(row, prefix) {
    return ["1m", "3m", "5m"]
      .map((window) => {
        const value = row?.[`${prefix}_${window}`];
        return observable(value) ? String(value) : "—";
      })
      .join(" / ");
  }

  function appendCell(table, name, value) {
    const row = document.createElement("tr");
    const label = document.createElement("th"); label.textContent = name;
    const data = document.createElement("td"); data.textContent = value == null || value === "" ? "—" : String(value);
    row.append(label, data); table.append(row);
  }

  function renderDivergence() {
    const episodes = unpack(state.chart?.episodes);
    const dependencies = unpack(state.chart?.dependencies);
    const lifecycle = unpack(state.chart?.lifecycle);
    const mechanisms = unpack(state.chart?.resolution_mechanisms);
    const episode = latestBy(episodes, "confirmation_timestamp");
    const host = $("#divergencePanel");
    host.replaceChildren();
    if (!episode) {
      host.textContent = state.chart?.availability?.divergence_state === "AVAILABLE" ? "No qualifying divergence observable." : "Divergence classification suspended by required market input freshness.";
      return;
    }
    const colour = document.createElement("span");
    colour.className = `badge ${episode.colour === "GREEN" ? "green" : "red"}`;
    colour.textContent = episode.colour;
    const identity = document.createElement("b"); identity.textContent = episode.episode_id;
    const dependency = dependencies.find((row) => row.episode_id === episode.episode_id);
    const life = latestBy(lifecycle.filter((row) => row.episode_id === episode.episode_id), "state_entry_timestamp");
    const mechanism = latestBy(mechanisms.filter((row) => row.episode_id === episode.episode_id), "timestamp");
    const lifecycleBadge = document.createElement("span");
    lifecycleBadge.className = "badge lifecycle-badge";
    lifecycleBadge.textContent = `Lifecycle: ${life?.state || "NOT YET OBSERVABLE"}`;
    const table = document.createElement("table");
    appendCell(table, "Dependency", dependency
      ? `${dependency.dependency_group_id || "—"} · ${dependency.classification || "—"}`
      : "NOT YET OBSERVABLE");
    appendCell(table, "Confirmation", episode.confirmation_timestamp);
    appendCell(table, "Index / Futures / Basis", `${episode.index_at_confirmation ?? "—"} / ${episode.futures_at_confirmation ?? "—"} / ${episode.basis_at_confirmation ?? "—"}`);
    appendCell(table, "Lifecycle reason", life?.reason_code);
    appendCell(table, "Resolution", mechanism?.resolution_mechanism_native || "NOT YET OBSERVABLE");
    appendCell(table, "Convergence / Index / Futures contribution", `${mechanism?.signed_basis_convergence ?? "—"} / ${mechanism?.index_contribution ?? "—"} / ${mechanism?.futures_contribution ?? "—"}`);
    host.append(colour, identity, lifecycleBadge, table);
  }

  function participationKind(row) {
    if (row.view_record_kind === "FUTURES") return "FUTURES";
    if (row.option_type === "CE") return "CE";
    if (row.option_type === "PE") return "PE";
    return "";
  }

  function renderParticipation() {
    const rows = Array.isArray(state.participation?.rows) ? state.participation.rows : [];
    const transitions = Array.isArray(state.participation?.transitions)
      ? state.participation.transitions : [];
    const availability = state.chart?.availability || {};
    const host = $("#participationPanel");
    host.replaceChildren();
    const states = { FUTURES: availability.futures_oi_state, CE: availability.ce_state, PE: availability.pe_state };
    for (const kind of ["FUTURES", "CE", "PE"]) {
      const latest = latestBy(rows.filter((row) => participationKind(row) === kind), "observation_timestamp");
      const card = document.createElement("div");
      card.className = "participation-card";
      card.dataset.participationKind = kind;
      const title = document.createElement("b"); title.textContent = kind;
      const badge = document.createElement("span");
      badge.className = `availability ${availabilityClass(states[kind])}`;
      badge.textContent = states[kind] || "NOT_YET_AVAILABLE";
      card.append(title, badge);
      if (latest) {
        const table = document.createElement("table");
        appendCell(table, "Symbol", latest.symbol);
        appendCell(table, "Receipt / age", `${latest.receipt_timestamp || "—"} / ${formatAge(latest.receipt_age_seconds)}`);
        appendCell(table, "5m volume / percentile / z", `${latest.incremental_volume_5m ?? "—"} / ${latest.volume_percentile ?? "—"} / ${latest.volume_robust_z ?? "—"}`);
        appendCell(table, "ΔOI 1m / 3m / 5m", `${latest.delta_oi_1m ?? "—"} / ${latest.delta_oi_3m ?? "—"} / ${latest.delta_oi_5m ?? "—"}`);
        appendCell(table, kind === "FUTURES" ? "Price Δ 1m / 3m / 5m" : "Premium Δ 1m / 3m / 5m",
          movement(latest, kind === "FUTURES" ? "price_change" : "premium_change"));
        appendCell(table, "Strike / expiry / moneyness", `${latest.strike ?? "—"} / ${latest.expiry ?? "—"} / ${latest.moneyness ?? "—"}`);
        appendCell(table, "Context", latest.inventory_state || latest.semantic_classification);
        const transition = latestBy(
          transitions.filter((row) => row.component === kind),
          "effective_timestamp",
        );
        appendCell(table, "Latest material transition", transition
          ? `${transition.component} · ${transition.new_state || "—"} · ${transition.effective_timestamp}`
          : "NOT YET OBSERVABLE");
        card.append(table);
      } else {
        const empty = document.createElement("p"); empty.textContent = "No current constituent evidence."; card.append(empty);
      }
      host.append(card);
    }
  }

  function renderOperational() {
    const value = {
      mode: state.settings.session === "latest" ? "LIVE_LATEST" : "HISTORICAL_REPLAY",
      session_date: state.chart?.session_date || state.settings.session,
      analytical_as_of: state.chart?.as_of || null,
      browser_poll_time: state.lastPoll?.toISOString() || null,
      overall_state: state.chart?.availability?.overall_state || null,
      counts: state.chart?.counts || {},
      dense_participation_total: state.participation?.count || 0,
      dense_participation_returned: state.participation?.returned_count || 0,
      projection_hash: state.chart?.projection_hash || null,
      stale_warning: Boolean(state.chart?.stale_warning),
      display_state: state.chart?.display_state || null,
      request_state: state.requestError || "AVAILABLE",
      read_only: true,
    };
    $("#operationalPanel").textContent = JSON.stringify(value, null, 2);
  }

  function render() {
    if (!state.chart) return;
    $("#asOf").textContent = `${state.settings.session === "latest" ? "Live/latest" : "Historical replay"} · analytical as-of ${state.chart.as_of || "not yet available"}`;
    buildControls();
    renderAvailability();
    renderCharts();
    renderDivergence();
    renderParticipation();
    renderOperational();
  }

  function initialize() {
    $("#sessionMode").value = state.settings.session;
    $("#pollRate").value = String(state.settings.pollSeconds);
    $("#sessionMode").onchange = (event) => {
      state.settings.session = event.target.value;
      persist(); refresh();
    };
    $("#pollRate").onchange = (event) => {
      state.settings.pollSeconds = Number(event.target.value);
      persist(); restartPolling();
    };
    $("#refreshNow").onclick = refresh;
    $("#restoreDefaults").onclick = () => {
      const session = state.settings.session;
      const pollSeconds = state.settings.pollSeconds;
      state.settings = clone(DEFAULTS);
      state.settings.session = session;
      state.settings.pollSeconds = pollSeconds;
      persist(); render();
    };
    bindDisplayControls();
    window.addEventListener("resize", renderCharts);
    restartPolling();
    refresh();
    window.R6E = { state, refresh, render, unpack, segments, layer, inventoryGroups };
  }

  initialize();
})();
