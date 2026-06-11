let dashboard = null;
let intelligenceDashboard = null;
let contractDashboard = null;
let modelProgressSelection = "all";
let selectedCategory = "all";
let refreshInFlight = false;
const AUTO_REFRESH_MS = 15 * 60 * 1000;

const formatPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const formatSignedPercent = (value) => {
  const number = Number(value || 0) * 100;
  return `${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
};
const formatCoins = (value) => Number(value || 0).toFixed(2);
const detailRecords = () =>
  Object.fromEntries((dashboard?.bet_detail_records || []).map((record) => [record.candidate_id, record]));
const recommendationsById = () =>
  Object.fromEntries((dashboard?.recommendations || []).map((item) => [item.candidate.candidate_id, item]));

function formatValue(value, format = "number") {
  if (format === "percent") return formatPercent(value);
  if (format === "signed_percent") return formatSignedPercent(value);
  if (format === "coins") return formatCoins(value);
  return Number(value || 0).toFixed(4);
}

function trendArrow(value) {
  const number = Number(value || 0);
  if (number > 0) return "up";
  if (number < 0) return "down";
  return "flat";
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function loadDashboard(refresh = false) {
  if (refreshInFlight) return;
  refreshInFlight = true;
  const source = document.getElementById("sourceMode").value;
  try {
    const payload = refresh
      ? await fetchJson(`/api/refresh?source=${encodeURIComponent(source)}&target_count=300`, { method: "POST" })
      : await fetchJson("/api/all");
    dashboard = payload.multi_agent;
    renderPortfolioStrip(dashboard);
    renderOverview(dashboard);
    renderDailyBets(dashboard);
    renderCategories(dashboard);
    renderPlacedBets(dashboard);
    renderNews(dashboard);
    renderEvents(dashboard);
    try {
      contractDashboard = await fetchJson("/api/dashboard-contract");
      renderContractDashboard(contractDashboard);
    } catch (error) {
      renderContractDashboardError(error);
    }
    try {
      intelligenceDashboard = await fetchJson("/api/intelligence");
      const [runHistory, modelState, correlations] = await Promise.all([
        fetchJson("/api/run-history").catch(() => null),
        fetchJson("/api/model-state").catch(() => null),
        fetchJson("/api/correlation-matrix").catch(() => null),
      ]);
      intelligenceDashboard.runHistory = runHistory || intelligenceDashboard.runHistory;
      intelligenceDashboard.modelState = modelState || intelligenceDashboard.modelState;
      intelligenceDashboard.correlations = correlations || intelligenceDashboard.correlations;
      renderIntelligence(intelligenceDashboard);
    } catch (error) {
      renderIntelligenceError(error);
    }
    renderDetailPicker(dashboard);
    renderLearning(dashboard);
    renderAgents(dashboard);
    document.getElementById("reportText").textContent = await (await fetch("/api/report")).text();
  } finally {
    refreshInFlight = false;
  }
}

function renderContractDashboard(payload) {
  const status = payload.status || {};
  const freshness = payload.freshness || {};
  const decisions = payload.decisions || {};
  const performance = payload.performance || {};
  const portfolio = payload.portfolio || {};
  const warnings = payload.warnings || [];
  const errors = payload.errors || [];
  document.getElementById("contractStatusGrid").innerHTML = `
    <article class="metric"><span>Run</span><strong>${escapeHtml(status.status || "unknown")}</strong></article>
    <article class="metric"><span>Source</span><strong>${escapeHtml(status.sourceMode || "-")}</strong></article>
    <article class="metric"><span>Fresh markets</span><strong>${freshness.marketSnapshotCount || 0}</strong></article>
    <article class="metric"><span>External obs</span><strong>${freshness.externalObservationCount || 0}</strong></article>
    <article class="metric"><span>Paper bets</span><strong>${(decisions.paperBets || []).length}</strong></article>
    <article class="metric"><span>Rejected</span><strong>${(decisions.rejected || []).length}</strong></article>
    <article class="metric"><span>Drawdown</span><strong>${formatPercent(performance.drawdown?.currentDrawdownPct || portfolio.current_drawdown_pct || 0)}</strong></article>
    <article class="metric"><span>Warnings</span><strong>${warnings.length + errors.length}</strong></article>
  `;
  document.getElementById("contractFreshnessStatus").textContent =
    `${freshness.marketSnapshotCount || 0} markets / ${(payload.sources?.evidence || []).length} evidence rows`;
  const broad = payload.context?.broadReports || [];
  const specific = payload.context?.betSpecificReports || [];
  document.getElementById("contractContextGrid").innerHTML = [
    ...broad.map((report) => contractContextCard(report, "Broad")),
    ...specific.map((report) => contractContextCard(report, "Bet-specific")),
  ].join("");
  const candidates = payload.candidates || [];
  document.getElementById("contractCandidateRows").innerHTML = candidates
    .map((row) => `
      <tr>
        <td><span class="category-pill">${escapeHtml(row.category)}</span></td>
        <td>${escapeHtml(row.question)}</td>
        <td><span class="state-chip state-${escapeHtml(row.decision || "watchlist")}">${escapeHtml(row.decision || "watchlist")}</span></td>
        <td>${formatPercent(row.spread)}</td>
        <td>${formatCoins(row.liquidity)}</td>
        <td>${escapeHtml((row.reasons || [])[0] || "No reason recorded.")}</td>
      </tr>
    `)
    .join("");
  document.getElementById("contractPerformanceStatus").textContent = performance.status || "pending";
  const summary = performance.summary || {};
  document.getElementById("contractPerformanceGrid").innerHTML = `
    <article><span>History</span><strong>${(performance.paperTradingHistory || []).length}</strong></article>
    <article><span>Resolved</span><strong>${(performance.resolvedOutcomes || []).length}</strong></article>
    <article><span>Wins</span><strong>${summary.wins || 0}</strong></article>
    <article><span>Losses</span><strong>${summary.losses || 0}</strong></article>
    <article><span>PnL</span><strong>${formatCoins(summary.totalPnlUnits || 0)}</strong></article>
    <article><span>Brier</span><strong>${performance.calibration?.brierScore ?? "n/a"}</strong></article>
    <article><span>Lessons</span><strong>${(performance.knowledgeLessons || []).length}</strong></article>
  `;
  const disagreement = payload.models?.disagreement?.byCandidate || {};
  document.getElementById("contractModelGrid").innerHTML = Object.entries(disagreement)
    .map(([candidateId, row]) => `
      <article>
        <span>${escapeHtml(candidateId)}</span>
        <strong>${formatPercent(row.range || 0)} disagreement</strong>
        <small>${row.modelCount || 0} models / ${formatPercent(row.minProbability || 0)}-${formatPercent(row.maxProbability || 0)}</small>
      </article>
    `)
    .join("") || `<article><span>Models</span><strong>No disagreement rows</strong></article>`;
  document.getElementById("contractWarningCount").textContent = `${warnings.length} warnings / ${errors.length} errors`;
  document.getElementById("contractWarnings").innerHTML = [
    ...warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`),
    ...errors.map((error) => `<p class="error">${escapeHtml(JSON.stringify(error))}</p>`),
  ].join("") || `<p>No reliability warnings reported.</p>`;
}

function contractContextCard(report, label) {
  return `
    <article>
      <span>${escapeHtml(label)} / ${escapeHtml(report.category)}</span>
      <strong>${formatPercent(report.confidence)}</strong>
      <small>${escapeHtml(report.reliability)} · ${escapeHtml(report.uncertainty)}</small>
    </article>
  `;
}

function renderContractDashboardError(error) {
  document.getElementById("contractStatusGrid").innerHTML = `
    <article class="metric"><span>Contract</span><strong>unavailable</strong></article>
  `;
  document.getElementById("contractWarnings").innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
}

function renderPortfolioStrip(data) {
  const metrics = data.metrics;
  const rules = data.portfolio_rules || {};
  document.getElementById("stripBankroll").textContent = formatCoins(metrics.deployment_budget_units || 100);
  document.getElementById("stripStaked").textContent = formatCoins(metrics.total_staked_units);
  document.getElementById("stripAvailable").textContent = formatCoins(metrics.unallocated_budget_units);
  document.getElementById("stripBets").textContent = metrics.paper_bet_count;
  document.getElementById("stripWatch").textContent = metrics.watchlist_count;
  document.getElementById("stripRule").textContent =
    rules.collection_rule || "Track public market data, model estimates, and research-only paper status. No wallet or order execution.";
}

function dailyPaperBets(data) {
  return (data.recommendations || [])
    .filter((item) => item.decision === "PAPER_BET")
    .sort((a, b) => Number(b.rank_score || 0) - Number(a.rank_score || 0));
}

function renderDailyBets(data) {
  const rows = dailyPaperBets(data);
  const totalStake = rows.reduce((sum, item) => sum + Number(item.stake_units || 0), 0);
  const avgForecast = rows.reduce((sum, item) => sum + Number(item.blended_probability || 0), 0) / Math.max(rows.length, 1);
  const avgPrice = rows.reduce((sum, item) => sum + Number(item.candidate?.price || 0), 0) / Math.max(rows.length, 1);
  const avgEv = rows.reduce((sum, item) => sum + Number(item.expected_value || 0), 0) / Math.max(rows.length, 1);
  const runDate = shortDate(data.created_at || new Date().toISOString());
  document.getElementById("dailyBetRun").textContent = `${runDate} / ${rows.length} paper bets / research-only`;
  document.getElementById("dailyBetSummary").innerHTML = `
    <article class="metric"><span>Daily bets</span><strong>${rows.length}</strong></article>
    <article class="metric"><span>Total stake</span><strong>${formatCoins(totalStake)}</strong></article>
    <article class="metric"><span>Avg forecast</span><strong>${formatPercent(avgForecast)}</strong></article>
    <article class="metric"><span>Avg price</span><strong>${formatPercent(avgPrice)}</strong></article>
    <article class="metric"><span>Avg EV</span><strong>${formatSignedPercent(avgEv)}</strong></article>
    <article class="metric"><span>Mode</span><strong>paper</strong></article>
  `;
  document.getElementById("dailyBetEmpty").hidden = rows.length > 0;
  document.getElementById("dailyBetRows").innerHTML = rows
    .map((item, index) => {
      const candidate = item.candidate || {};
      const detail = detailRecords()[candidate.candidate_id] || {};
      return `
        <tr class="clickable state-row state-${detail.state || "betted"}" data-id="${candidate.candidate_id}">
          <td>${index + 1}</td>
          <td><span class="category-pill">${escapeHtml(candidate.category)}</span></td>
          <td>${escapeHtml(candidate.market_title)}</td>
          <td>${escapeHtml(candidate.outcome)}</td>
          <td>${formatPercent(item.blended_probability)}</td>
          <td>${formatPercent(candidate.price)}</td>
          <td class="${item.expected_value >= 0 ? "ev-pos" : "ev-neg"}">${formatSignedPercent(item.expected_value)}</td>
          <td>${formatCoins(item.stake_units)}</td>
          <td><span class="risk ${String(item.risk_tier || "").toLowerCase()}">${escapeHtml(item.risk_tier)}</span></td>
          <td><span class="state-chip state-${detail.state || "betted"}">${escapeHtml(detail.state_label || "Paper bet")}</span></td>
          <td>${escapeHtml(item.reason)}</td>
        </tr>
      `;
    })
    .join("");
  bindDetailRows();
}

function renderOverview(data) {
  const metrics = data.metrics;
  document.getElementById("candidateCount").textContent = metrics.candidate_count;
  document.getElementById("paperBetCount").textContent = metrics.paper_bet_count;
  document.getElementById("winRate").textContent = formatPercent(metrics.win_rate);
  document.getElementById("simulatedRoi").textContent = formatSignedPercent(metrics.simulated_roi);
  document.getElementById("bankroll").textContent = formatCoins(metrics.ending_bankroll_units);
  document.getElementById("staked").textContent = formatCoins(metrics.total_staked_units);
  document.getElementById("avgOdds").textContent = Number(metrics.average_decimal_odds || 0).toFixed(2);
  document.getElementById("brierScore").textContent = Number(metrics.brier_score || 0).toFixed(4);
  document.getElementById("sourceNote").textContent = data.source_note;

  document.getElementById("topBetRows").innerHTML = data.top_bets
    .map((item) => {
      const candidate = item.candidate;
      const detail = detailRecords()[candidate.candidate_id] || {};
      return `
        <tr class="clickable state-row state-${detail.state || "planning"}" data-id="${candidate.candidate_id}">
          <td><span class="category-pill">${candidate.category}</span></td>
          <td>
            <button class="link-button" type="button" data-id="${candidate.candidate_id}">${escapeHtml(candidate.market_title)}</button>
            <strong>${escapeHtml(candidate.outcome)}</strong>
            <small>${escapeHtml(detail.state_label || item.decision)}</small>
          </td>
          <td>${formatPercent(item.blended_probability)}</td>
          <td>${formatPercent(candidate.price)}</td>
          <td class="ev-pos">${formatSignedPercent(item.expected_value)}</td>
          <td><span class="risk ${item.risk_tier.toLowerCase()}">${item.risk_tier}</span></td>
          <td>${formatCoins(item.stake_units)}</td>
        </tr>
      `;
    })
    .join("");
  bindDetailRows();
  renderBankrollCurve(data.bankroll_curve);
  renderOverviewNews(data);
}

function renderBankrollCurve(curve) {
  const values = curve.map((row) => Number(row.bankroll));
  const min = Math.min(...values);
  const max = Math.max(...values);
  document.getElementById("bankrollCurve").innerHTML = curve
    .map((row) => {
      const height = max === min ? 50 : 18 + ((Number(row.bankroll) - min) / (max - min)) * 72;
      return `<span title="${row.label}: ${formatCoins(row.bankroll)}" style="height:${height}px"></span>`;
    })
    .join("");
}

function renderOverviewNews(data) {
  const target = document.getElementById("overviewNewsInfluence");
  if (!target) return;
  const nodes = data.news_influence_graph?.nodes || [];
  target.innerHTML = nodes
    .slice(0, 6)
    .map((node) => `
      <article class="news-mini ${node.direction}">
        <strong>${node.direction === "up" ? "↑" : "↓"} ${escapeHtml(node.source)}</strong>
        <span>${escapeHtml(node.conclusion)}</span>
      </article>
    `)
    .join("");
}

function renderCategories(data) {
  const readinessByCategory = Object.fromEntries(
    (data.external_data_readiness?.categoryReadiness || []).map((row) => [row.category, row])
  );
  document.getElementById("categoryCards").innerHTML = data.category_stats
    .map((row) => {
      const statusCounts = readinessByCategory[row.category]?.sourceStatusCounts || {};
      const planned = Number(statusCounts.registered_needs_fetcher_and_asof_storage || 0) + Number(statusCounts.client_available_not_wired || 0);
      return `
        <article class="category-card">
          <h3>${row.category}</h3>
          <dl>
            <dt>Candidates</dt><dd>${row.candidate_count}</dd>
            <dt>Bets</dt><dd>${row.paper_bet_count}</dd>
            <dt>Win rate</dt><dd>${formatPercent(row.win_rate)}</dd>
            <dt>Avg odds</dt><dd>${Number(row.average_decimal_odds).toFixed(2)}</dd>
            <dt>Avg EV</dt><dd>${formatSignedPercent(row.average_ev)}</dd>
            <dt>PnL</dt><dd>${formatCoins(row.pnl_units)}</dd>
            <dt>Sources</dt><dd>${statusCounts.implemented || 0} live / ${planned} planned / ${statusCounts.blocked_until_access_or_license_review || 0} blocked</dd>
          </dl>
        </article>
      `;
    })
    .join("");
  renderExternalReadiness(data.external_data_readiness);

  const categories = ["all", ...data.category_stats.map((row) => row.category)];
  document.getElementById("categoryFilters").innerHTML = categories
    .map((category) => `
      <button class="filter ${selectedCategory === category ? "active" : ""}" data-category="${category}" type="button">
        ${category}
      </button>
    `)
    .join("");
  document.querySelectorAll(".filter").forEach((button) => {
    button.addEventListener("click", () => {
      selectedCategory = button.dataset.category;
      renderCategories(dashboard);
    });
  });

  const rows = data.recommendations.filter((item) => selectedCategory === "all" || item.candidate.category === selectedCategory);
  document.getElementById("allBetRows").innerHTML = rows
    .slice(0, 160)
    .map((item) => `
      <tr class="clickable" data-id="${item.candidate.candidate_id}">
        <td><span class="category-pill">${item.candidate.category}</span></td>
        <td>${escapeHtml(item.candidate.market_title)}</td>
        <td><span class="badge ${decisionClass(item.decision)}">${item.decision.replace("_", " ")}</span></td>
        <td>${formatPercent(item.blended_probability)}</td>
        <td class="${item.expected_value >= 0 ? "ev-pos" : "ev-neg"}">${formatSignedPercent(item.expected_value)}</td>
        <td>${escapeHtml(item.reason)}</td>
      </tr>
    `)
    .join("");
  bindDetailRows();
}

function renderExternalReadiness(readiness) {
  const target = document.getElementById("externalReadinessCards");
  if (!target) return;
  const entities = readiness?.detectedEntities || {};
  const entityGroups = [
    ["Countries", entities.countries || []],
    ["Politics", entities.politicalTrends || []],
    ["Macro", entities.macroTrends || []],
    ["Companies", entities.companiesAndCommodities || []],
    ["Trade", entities.tradeSignals || []],
  ];
  target.innerHTML = `
    ${(readiness?.categoryReadiness || []).map((row) => {
      const counts = row.sourceStatusCounts || {};
      const planned = Number(counts.registered_needs_fetcher_and_asof_storage || 0) + Number(counts.client_available_not_wired || 0);
      return `
        <article class="readiness-card">
          <strong>${escapeHtml(row.category)}</strong>
          <dl>
            <dt>Markets</dt><dd>${row.candidateCount}</dd>
            <dt>Implemented</dt><dd>${counts.implemented || 0}</dd>
            <dt>Planned</dt><dd>${planned}</dd>
            <dt>Blocked</dt><dd>${counts.blocked_until_access_or_license_review || 0}</dd>
          </dl>
        </article>
      `;
    }).join("")}
    <article class="readiness-card readiness-wide">
      <strong>Detected entity coverage</strong>
      <div class="entity-chip-grid">
        ${entityGroups.map(([label, rows]) => `
          <div>
            <span>${escapeHtml(label)}</span>
            ${(rows || []).slice(0, 8).map((row) => `<em>${escapeHtml(row.name)} ${row.count}</em>`).join("") || "<em>none</em>"}
          </div>
        `).join("")}
      </div>
    </article>
  `;
}

function renderPlacedBets(data) {
  const approvedBets = dailyPaperBets(data);
  const stateCounts = approvedBets.reduce((acc, item) => {
    const record = detailRecords()[item.candidate.candidate_id] || {};
    const state = record.state || "approved";
    acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});
  document.getElementById("placedSummary").textContent =
    `${approvedBets.length} approved bets / ${formatCoins(data.metrics.total_staked_units)} allocated`;
  document.getElementById("betStateSummary").innerHTML = Object.entries(stateCounts)
    .map(([state, count]) => `<span class="state-chip state-${state}">${state.replaceAll("_", " ")} ${count}</span>`)
    .join("");
  document.getElementById("placedBets").innerHTML = approvedBets
    .slice(0, 180)
    .map((item) => `
      <article class="bet-card clickable state-card state-${detailRecords()[item.candidate.candidate_id]?.state || "planning"}" data-id="${item.candidate.candidate_id}">
        <header>
          <span class="category-pill">${item.candidate.category}</span>
          <span class="state-chip state-${detailRecords()[item.candidate.candidate_id]?.state || "planning"}">${escapeHtml(detailRecords()[item.candidate.candidate_id]?.state_label || item.decision)}</span>
        </header>
        <h3>${escapeHtml(item.candidate.market_title)}</h3>
        <dl>
          <dt>Outcome</dt><dd>${escapeHtml(item.candidate.outcome)}</dd>
          <dt>Forecast</dt><dd>${formatPercent(item.blended_probability)}</dd>
          <dt>Market price</dt><dd>${formatPercent(item.candidate.price)}</dd>
          <dt>EV</dt><dd>${formatSignedPercent(item.expected_value)}</dd>
          <dt>Stake</dt><dd>${formatCoins(item.stake_units)}</dd>
          <dt>Risk</dt><dd>${item.risk_tier}</dd>
          <dt>Result</dt><dd>${item.outcome || "PENDING"}</dd>
          <dt>PnL</dt><dd>${formatCoins(item.pnl_units)}</dd>
        </dl>
        <p>${escapeHtml(item.reason)}</p>
        <button class="open-detail" type="button" data-id="${item.candidate.candidate_id}">Open decision record</button>
      </article>
    `)
    .join("");
  bindDetailRows();
}

function renderNews(data) {
  const graph = data.news_influence_graph || { nodes: [], edges: [] };
  document.getElementById("newsSummary").textContent =
    `${graph.nodes.length} news/source nodes, ${graph.edges.length} influence links`;
  document.getElementById("newsInfluenceList").innerHTML = graph.nodes
    .slice(0, 40)
    .map((node) => `
      <article class="news-card ${node.direction}">
        <header>
          <span>${node.direction === "up" ? "↑ Raises" : "↓ Lowers"}</span>
          <strong>${escapeHtml(node.source)}</strong>
        </header>
        <p>${escapeHtml(node.conclusion)}</p>
        <dl>
          <dt>Affected bets</dt><dd>${node.affected_count}</dd>
          <dt>Net impact</dt><dd>${formatSignedPercent(node.net_impact)}</dd>
          <dt>Credibility</dt><dd>${formatPercent(node.avg_credibility)}</dd>
        </dl>
        <div class="influence-links">
          ${node.top_bets
            .map((bet) => `
              <button class="news-bet-link ${trendArrow(bet.impact)}" type="button" data-id="${bet.candidate_id}">
                ${trendArrow(bet.impact) === "up" ? "↑" : "↓"} ${escapeHtml(bet.market_title)}
              </button>
            `)
            .join("")}
        </div>
      </article>
    `)
    .join("");

  document.getElementById("newsEdgeRows").innerHTML = graph.edges
    .slice(0, 80)
    .map((edge) => `
      <tr class="clickable" data-id="${edge.to}">
        <td>${escapeHtml(edge.from.replace("news:", ""))}</td>
        <td>${edge.direction === "up" ? "↑" : "↓"}</td>
        <td>${formatPercent(edge.weight)}</td>
        <td>${escapeHtml(edge.explanation)}</td>
      </tr>
    `)
    .join("");
  bindDetailRows();
}

function renderEvents(data) {
  document.getElementById("eventSummary").textContent = `${data.event_groups?.length || 0} event groups with linked sub-bets`;
  document.getElementById("eventGroups").innerHTML = (data.event_groups || [])
    .slice(0, 80)
    .map((event) => `
      <article class="event-group">
        <header>
          <span class="category-pill">${event.category}</span>
          <strong>${escapeHtml(event.event_title)}</strong>
          <em>${formatCoins(event.total_stake_units)} coins</em>
        </header>
        <div class="sub-bets">
          ${event.sub_bets
            .map((bet) => `
              <button class="sub-bet state-${bet.state}" type="button" data-id="${bet.candidate_id}">
                <span>${escapeHtml(bet.outcome)}</span>
                <strong>${formatPercent(bet.probability)}</strong>
                <small>${escapeHtml(bet.decision)} · ${formatSignedPercent(bet.expected_value)} · ${formatCoins(bet.stake_units)}c</small>
              </button>
            `)
            .join("")}
        </div>
      </article>
    `)
    .join("");
  bindDetailRows();
}

function renderIntelligence(payload) {
  const summary = payload.summary || {};
  document.getElementById("intelLastRun").textContent = shortTime(payload.createdAt);
  document.getElementById("intelStatus").textContent = payload.status || "-";
  document.getElementById("intelMarkets").textContent = summary.marketCount || 0;
  document.getElementById("intelReliability").textContent = formatPercent(summary.averageReliability || 0);
  document.getElementById("intelMoves").textContent = summary.unusualMoveCount || 0;
  document.getElementById("intelCodex").textContent = payload.localCodex?.status || "skipped";
  document.getElementById("intelQueue").textContent = payload.codexQueue?.pendingCount ?? 0;
  document.getElementById("intelligenceOverviewStatus").textContent =
    `${payload.status || "unknown"} · ${shortTime(payload.createdAt)} · ${payload.localCodex?.status || "skipped"} · queue ${payload.codexQueue?.status || "n/a"}`;
  renderIntelligenceOverview(payload);
  renderIntelligenceSignals(payload);
  renderSourceReliability(payload);
  renderAnalysisRuns(payload);
  renderIntelligenceFallback(payload);
  renderChronology(payload);
  renderModelState(payload);
  renderCorrelations(payload);
  renderModelProgress(payload);
}

function renderIntelligenceError(error) {
  document.getElementById("intelligenceOverviewStatus").textContent = "failed";
  const fallback = {
    status: "failed",
    createdAt: "",
    summary: { marketCount: 0, averageReliability: 0, unusualMoveCount: 0, signalCounts: {} },
    localCodex: { status: "skipped", message: error.message },
    codexQueue: { status: "unavailable", pendingCount: 0, message: "Queue status unavailable because intelligence failed to load." },
    analysisSources: [],
    analysisRuns: [],
    marketAnalysisResults: [],
    runHistory: { runs: [], gaps: [] },
    modelState: { health: [] },
    correlations: { categories: [] },
  };
  renderIntelligence(fallback);
}

function renderIntelligenceOverview(payload) {
  const counts = payload.summary?.signalCounts || {};
  document.getElementById("intelligenceOverview").innerHTML = ["bullish", "bearish", "watch", "neutral", "avoid"]
    .map((signal) => `
      <article class="intel-count ${signal}">
        <span>${signal}</span>
        <strong>${counts[signal] || 0}</strong>
      </article>
    `)
    .join("");
}

function renderIntelligenceSignals(payload) {
  const rows = payload.marketAnalysisResults || [];
  document.getElementById("intelligenceSignals").innerHTML = rows
    .slice(0, 300)
    .map((row) => `
      <article class="signal-card ${row.decisionCommentary.signal}">
        <header>
          <span class="category-pill">${escapeHtml(row.category || "market")}</span>
          <span class="state-chip state-${row.state || "planning"}">${escapeHtml(row.decisionCommentary.signal)}</span>
          <strong>${formatPercent(row.reliability.overallScore)}</strong>
        </header>
        <h3>${escapeHtml(row.marketTitle)}</h3>
        ${renderForecastSvg(row.forecastChart)}
        <dl>
          <dt>Current</dt><dd>${formatPercent(row.marketSnapshot.currentProbability)}</dd>
          <dt>Previous</dt><dd>${formatPercent(row.marketSnapshot.previousProbability)}</dd>
          <dt>Delta</dt><dd>${formatSignedPercent(row.marketSnapshot.probabilityDelta)}</dd>
          <dt>Volatility</dt><dd>${formatPercent(row.marketSnapshot.priceVolatility)}</dd>
          <dt>Forecast</dt><dd>${escapeHtml(row.modelInterpretation.forecastDirection)} · ${escapeHtml(row.modelInterpretation.confidenceLabel)}</dd>
          <dt>Interval</dt><dd>${formatPercent(row.forecastChart.lowerInterval)} to ${formatPercent(row.forecastChart.upperInterval)}</dd>
        </dl>
        ${renderLifecycleTimes(row.lifecycleTimes)}
        ${renderMultiModelForecast(row.multiModelForecast)}
        ${renderNewsAndCorrelation(row.newsMonitor, row.correlatedOddsInfluence)}
        <details class="signal-notes analysis-disclosure" open>
          <summary>
            <span>Interpretation</span>
            <small>${escapeHtml(row.reliability.label)}</small>
          </summary>
          <div class="analysis-body">
            <p>${escapeHtml(row.reliability.explanation)}</p>
            <ul>${row.modelInterpretation.riskFactors.slice(0, 3).map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")}</ul>
          </div>
        </details>
        <div class="source-strip">
          ${row.newsContext.strongestSources.slice(0, 3).map(renderSignalSource).join("")}
        </div>
      </article>
    `)
    .join("");
}

function renderLifecycleTimes(times) {
  const row = times || {};
  return `
    <dl class="lifecycle-dl">
      <dt>Gathered</dt><dd>${escapeHtml(row.gatheredAt || "-")}</dd>
      <dt>Estimated</dt><dd>${escapeHtml(row.estimatedAt || "-")}</dd>
      <dt>Paper timestamp</dt><dd>${escapeHtml(row.paperExecutionAt || "-")}</dd>
      <dt>Expected resolution</dt><dd>${escapeHtml(row.expectedResolutionAt || "-")}</dd>
      <dt>Status</dt><dd>${escapeHtml((row.resolutionStatus || "pending").replaceAll("_", " "))}</dd>
    </dl>
  `;
}

function renderMultiModelForecast(forecast) {
  if (!forecast) return "";
  const outputs = forecast.outputs || [];
  return `
    <details class="multi-model-card analysis-disclosure" open>
      <summary>
        <span>Multi-output forecast</span>
        <small>${escapeHtml(forecast.expectedDirection || "flat")} / ensemble ${formatPercent(forecast.ensembleProbability)}</small>
      </summary>
      <div class="analysis-body">
        <p>${escapeHtml(forecast.expectation?.why || "")}</p>
        <div class="model-output-grid">
          ${outputs.map((model) => `
            <article>
              <strong>${escapeHtml(model.label)}</strong>
              <span>${formatPercent(model.probability)}</span>
              <small>${escapeHtml(model.explanation)}</small>
            </article>
          `).join("")}
        </div>
        <dl class="compact-dl">
          <dt>Model disagreement</dt><dd>${formatPercent(forecast.modelDisagreement)}</dd>
          <dt>Direct odds dominate</dt><dd>${forecast.rules?.directMarketEvidenceDominates ? "yes" : "no"}</dd>
          <dt>Related odds override</dt><dd>${forecast.rules?.relatedOddsNeverOverrideDirectMarket ? "never" : "allowed"}</dd>
        </dl>
      </div>
    </details>
  `;
}

function renderNewsAndCorrelation(news, correlation) {
  if (!news && !correlation) return "";
  const related = correlation?.relatedMarkets || [];
  return `
    <details class="news-corr-card analysis-disclosure" open>
      <summary>
        <span>News and correlation interpretation</span>
        <small>${escapeHtml(news?.stance || "unknown")} / score ${formatSignedPercent(news?.score || 0)}</small>
      </summary>
      <div class="news-corr-grid">
        <article>
          <strong>News monitor</strong>
          <span>${escapeHtml(news?.stance || "unknown")} / score ${formatSignedPercent(news?.score || 0)}</span>
          <p>${escapeHtml(news?.argument || "No attached news signal.")}</p>
          <ul>${(news?.topItems || []).slice(0, 3).map((item) => `<li>${escapeHtml(item.title)} <small>${escapeHtml(item.source || "")}</small></li>`).join("")}</ul>
        </article>
        <article>
          <strong>Correlated odds instrument</strong>
          <span>score ${formatSignedPercent(correlation?.score || 0)}</span>
          <p>${escapeHtml(correlation?.argument || "No related odds signal.")}</p>
          <ul>${related.slice(0, 4).map((item) => `<li>${escapeHtml(item.title || item.marketId)} <small>corr ${Number(item.correlation || 0).toFixed(2)} / delta ${formatSignedPercent(item.otherProbabilityDelta || 0)}</small></li>`).join("")}</ul>
        </article>
      </div>
    </details>
  `;
}

function renderSignalSource(source) {
  return `
    <span class="tier-badge tier-${source.reliabilityTier}" title="${escapeHtml(source.summary)}">
      T${source.reliabilityTier} ${escapeHtml(source.source)}
    </span>
  `;
}

function renderForecastSvg(chart) {
  const history = chart?.history || [];
  const values = [
    ...history.map((point) => Number(point.probability || 0)),
    Number(chart?.forecastProbability || 0),
    Number(chart?.lowerInterval || 0),
    Number(chart?.upperInterval || 0),
  ];
  const min = Math.max(0, Math.min(...values) - 0.04);
  const max = Math.min(1, Math.max(...values) + 0.04);
  const width = 520;
  const height = 170;
  const left = 44;
  const right = 24;
  const top = 18;
  const bottom = 32;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const scaleX = (index, count) => left + (count <= 1 ? 0 : (index / (count - 1)) * plotWidth);
  const scaleY = (value) => top + (1 - ((Number(value) - min) / Math.max(max - min, 0.001))) * plotHeight;
  const points = history.map((point, index) => `${scaleX(index, history.length + 1)},${scaleY(point.probability)}`).join(" ");
  const forecastX = scaleX(history.length, history.length + 1);
  const forecastY = scaleY(chart?.forecastProbability || 0);
  const lowerY = scaleY(chart?.lowerInterval || 0);
  const upperY = scaleY(chart?.upperInterval || 0);
  return `
    <div class="chart-scroll">
      <svg class="forecast-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Probability history with forecast interval">
        <line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" />
        <line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" />
        <text x="6" y="${scaleY(max)}">${formatPercent(max)}</text>
        <text x="6" y="${scaleY(min)}">${formatPercent(min)}</text>
        <rect x="${forecastX - 10}" y="${Math.min(lowerY, upperY)}" width="20" height="${Math.abs(lowerY - upperY)}" rx="5" />
        <polyline points="${points}" />
        ${history.map((point, index) => `<circle cx="${scaleX(index, history.length + 1)}" cy="${scaleY(point.probability)}" r="3"><title>${escapeHtml(point.time)} ${formatPercent(point.probability)}</title></circle>`).join("")}
        <circle class="forecast-dot" cx="${forecastX}" cy="${forecastY}" r="5" />
        <text class="forecast-label" x="${forecastX - 34}" y="${Math.max(forecastY - 10, 12)}">forecast ${formatPercent(chart?.forecastProbability)}</text>
        <text x="${left}" y="${height - 8}">history</text>
        <text x="${forecastX - 30}" y="${height - 8}">next</text>
      </svg>
    </div>
  `;
}

function renderSourceReliability(payload) {
  document.getElementById("sourceReliabilityPanel").innerHTML = (payload.analysisSources || [])
    .map((source) => `
      <article class="source-row ${source.enabled ? "enabled" : "disabled"}">
        <span class="tier-badge tier-${source.reliability_tier}">Tier ${source.reliability_tier}</span>
        <strong>${escapeHtml(source.name)}</strong>
        <small>${escapeHtml(source.category)} · ${escapeHtml(source.status)} · ${escapeHtml(source.update_frequency)}</small>
      </article>
    `)
    .join("");
}

function renderAnalysisRuns(payload) {
  document.getElementById("analysisRunRows").innerHTML = (payload.analysisRuns || [])
    .map((run) => `
      <tr>
        <td>${escapeHtml(run.id)}</td>
        <td>${escapeHtml(run.createdAt)}</td>
        <td>${escapeHtml(run.cycleType)}</td>
        <td>${escapeHtml(run.status)}</td>
        <td>${run.marketCount}</td>
        <td>${escapeHtml(run.localCodexStatus)}</td>
        <td>${escapeHtml(run.codexQueueStatus || "-")}</td>
      </tr>
    `)
    .join("");
}

function renderIntelligenceFallback(payload) {
  const queue = payload.codexQueue || {};
  const queueItem = queue.queueItem || {};
  document.getElementById("intelligenceFallback").innerHTML = `
    <p><strong>${escapeHtml(payload.localCodex?.status || "skipped")}</strong></p>
    <p>${escapeHtml(payload.localCodex?.message || "Deterministic fallback analysis is active.")}</p>
    <div class="queue-state">
      <strong>Codex backfill queue: ${escapeHtml(queue.status || "not_needed")}</strong>
      <dl>
        <dt>Pending</dt><dd>${queue.pendingCount ?? 0}</dd>
        <dt>Durable</dt><dd>${queue.durable === false ? "no" : "yes"}</dd>
        <dt>Storage</dt><dd>${escapeHtml(queue.storageMode || "local_file")}</dd>
        <dt>Cycle</dt><dd>${escapeHtml(queue.cycleId || queueItem.cycleId || "-")}</dd>
      </dl>
      <p>${escapeHtml(queue.message || "No queued local Codex backfill is required for this cycle.")}</p>
    </div>
    <p>Vercel never uses local Codex auth. Local Codex is only attempted when <code>ENABLE_LOCAL_CODEX_ANALYSIS=true</code> and <code>CODEX_ANALYSIS_MODE=local-cli</code>.</p>
  `;
}

function renderChronology(payload) {
  const chronology = payload.chronology || {};
  const runHistory = payload.runHistory || {};
  const runs = runHistory.runs || payload.analysisRuns || [];
  const gaps = runHistory.gaps || [];
  const target = document.getElementById("chronologyPanel");
  if (!target) return;
  target.innerHTML = `
    <dl>
      <dt>Current</dt><dd>${escapeHtml(chronology.currentRunId || payload.id || "-")}</dd>
      <dt>Previous</dt><dd>${escapeHtml(chronology.previousRunId || "-")}</dd>
      <dt>Run index</dt><dd>${chronology.runIndex || runs.length || 0}</dd>
      <dt>Gaps</dt><dd>${gaps.length}</dd>
      <dt>Source</dt><dd>${escapeHtml(payload.sourceMode || "-")}</dd>
    </dl>
    <p>${gaps.length ? escapeHtml(`${gaps.length} missing/late intervals recorded.`) : "No chronological gaps recorded in persisted state."}</p>
  `;
}

function renderModelState(payload) {
  const state = payload.modelState || {};
  const health = state.health || [];
  const diagnostics = state.diagnostics || {};
  const target = document.getElementById("modelStatePanel");
  if (!target) return;
  if (!health.length) {
    target.innerHTML = `<article class="source-row disabled"><strong>No persisted ML state yet</strong><small>Run managed cycle or ML automation</small></article>`;
    return;
  }
  target.innerHTML = `
    <div class="model-dashboard">
      ${renderOutputFamilies(state.outputFamilies || [])}
      <div class="model-health-list">
        ${health.slice(0, 24).map(renderModelHealthRow).join("")}
      </div>
      <div class="model-diagnostics-grid">
        <article class="model-plot-card">
          <h3>ML Probability Scatter</h3>
          ${renderModelScatter(diagnostics.scatter || [])}
        </article>
        <article class="model-plot-card">
          <h3>Feature Weights</h3>
          ${renderFeatureWeights(diagnostics.featureWeights || [])}
        </article>
      </div>
    </div>
  `;
}

function renderOutputFamilies(families) {
  if (!families.length) return "";
  return `
    <div class="model-family-grid">
      ${families.map((family) => `
        <article>
          <strong>${escapeHtml(family.label)}</strong>
          <span>${Number(family.marketCount || 0)} markets</span>
          <small>${escapeHtml(family.purpose || "")}</small>
        </article>
      `).join("")}
    </div>
  `;
}

function renderCorrelations(payload) {
  const correlations = payload.correlations || {};
  const categories = correlations.categories || [];
  const target = document.getElementById("correlationPanel");
  if (!target) return;
  if (!categories.length) {
    target.innerHTML = `<article class="news-mini flat"><strong>No correlation state yet</strong><span>Run managed ML update to build matrices.</span></article>`;
    return;
  }
  target.innerHTML = categories
    .map((category) => {
      return `
        <article class="correlation-category">
          <header>
            <strong>${escapeHtml(category.category)}</strong>
            <span>${category.marketCount || 0} markets · ${(category.pairs || []).length} coefs</span>
          </header>
          ${renderCorrelationHeatmap(category)}
          <div class="correlation-pairs">
            ${(category.pairs || []).slice(0, 8).map(renderCorrelationPair).join("") || "<p>No reliable overlapping odds correlations yet.</p>"}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderModelProgress(payload) {
  const panel = document.getElementById("modelProgressPanel");
  const summary = document.getElementById("modelProgressSummary");
  const selector = document.getElementById("modelProgressSelector");
  if (!panel || !summary || !selector) return;

  const models = buildModelProgressModels(payload);
  if (!models.length) {
    summary.innerHTML = `
      <article class="metric"><span>Models</span><strong>0</strong></article>
      <article class="metric"><span>Markets</span><strong>0</strong></article>
      <article class="metric"><span>Bet Rate</span><strong>0.0%</strong></article>
      <article class="metric"><span>Avg CI Width</span><strong>0.0%</strong></article>
    `;
    selector.innerHTML = `<option value="all">All models</option>`;
    panel.innerHTML = `<article class="empty-card">No multi-model forecast output is available yet. Run the managed agent and ML cycle to populate model progress.</article>`;
    return;
  }

  const allowed = new Set(["all", ...models.map((model) => model.id)]);
  const selected = allowed.has(modelProgressSelection) ? modelProgressSelection : "all";
  modelProgressSelection = selected;
  selector.innerHTML = [
    `<option value="all">All models</option>`,
    ...models.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.label)}</option>`),
  ].join("");
  selector.value = selected;
  selector.onchange = (event) => {
    modelProgressSelection = event.target.value;
    renderModelProgress(intelligenceDashboard || payload);
  };

  const visibleModels = selected === "all" ? models : models.filter((model) => model.id === selected);
  summary.innerHTML = renderModelProgressSummary(models, payload);
  panel.innerHTML = visibleModels.map(renderModelProgressDetail).join("");
}

function buildModelProgressModels(payload) {
  const rows = payload.marketAnalysisResults || [];
  const grouped = new Map();

  rows.forEach((row, index) => {
    const marketPrice = readProbability(row.multiModelForecast?.marketPrice ?? row.marketSnapshot?.currentProbability);
    const timestamp = row.lifecycleTimes?.estimatedAt || row.lifecycleTimes?.gatheredAt || payload.createdAt || "";
    const forecast = row.multiModelForecast || {};
    (forecast.outputs || []).forEach((output) => {
      addModelProgressPoint(grouped, {
        id: output.id || slugModelLabel(output.label),
        label: output.label || output.id || "Model",
        purpose: output.explanation || "",
        probability: readProbability(output.probability),
        marketPrice,
        row,
        index,
        timestamp,
      });
    });
    addModelProgressPoint(grouped, {
      id: "ensemble",
      label: "Ensemble",
      purpose: forecast.expectation?.why || "Blended probability from rule, ML, OLS, IV, tree, news, and related odds context.",
      probability: readProbability(forecast.ensembleProbability),
      marketPrice,
      row,
      index,
      timestamp,
    });
  });

  const preferredOrder = ["rule", "logistic", "ols", "iv", "tree", "ensemble"];
  return Array.from(grouped.values())
    .map(finalizeModelProgress)
    .sort((a, b) => {
      const orderA = preferredOrder.indexOf(a.id);
      const orderB = preferredOrder.indexOf(b.id);
      if (orderA !== -1 || orderB !== -1) return (orderA === -1 ? 99 : orderA) - (orderB === -1 ? 99 : orderB);
      return a.label.localeCompare(b.label);
    });
}

function addModelProgressPoint(grouped, point) {
  if (point.probability === null) return;
  const id = point.id || "model";
  if (!grouped.has(id)) {
    grouped.set(id, {
      id,
      label: point.label || id,
      purpose: point.purpose || "",
      points: [],
    });
  }
  const marketPrice = point.marketPrice === null ? 0 : point.marketPrice;
  grouped.get(id).points.push({
    category: point.row.category || "market",
    marketTitle: point.row.marketTitle || "Untitled market",
    timestamp: point.timestamp || "",
    marketPrice,
    probability: point.probability,
    edge: point.probability - marketPrice,
    signal: point.row.decisionCommentary?.signal || "watch",
    confidence: point.row.modelInterpretation?.confidenceLabel || "unknown",
    newsScore: Number(point.row.newsMonitor?.score || 0),
    correlationScore: Number(point.row.correlatedOddsInfluence?.score || 0),
    index: point.index,
  });
}

function finalizeModelProgress(model) {
  const points = model.points;
  const average = (selector) => points.reduce((sum, point) => sum + selector(point), 0) / Math.max(points.length, 1);
  const trend = buildProbabilityTrend(points);
  const highEdgeThreshold = 0.025;
  const ciWidths = trend.samples.map((sample) => Math.max(0, sample.upper - sample.lower));
  const averageCiWidth = ciWidths.reduce((sum, width) => sum + width, 0) / Math.max(ciWidths.length, 1);
  return {
    ...model,
    avgProbability: average((point) => point.probability),
    avgMarketPrice: average((point) => point.marketPrice),
    avgEdge: average((point) => point.edge),
    avgAbsEdge: average((point) => Math.abs(point.edge)),
    positiveEdgeRate: points.filter((point) => point.edge > 0).length / Math.max(points.length, 1),
    betRate: points.filter((point) => point.edge >= highEdgeThreshold).length / Math.max(points.length, 1),
    fadeRate: points.filter((point) => point.edge <= -highEdgeThreshold).length / Math.max(points.length, 1),
    avgNewsScore: average((point) => point.newsScore),
    avgCorrelationScore: average((point) => point.correlationScore),
    averageCiWidth,
    trend,
    topEdges: [...points].sort((a, b) => Math.abs(b.edge) - Math.abs(a.edge)).slice(0, 8),
    latestTimestamp: points.map((point) => point.timestamp).filter(Boolean).sort().at(-1) || "",
  };
}

function buildProbabilityTrend(points) {
  const usable = points
    .map((point, order) => ({
      ...point,
      x: Number.isFinite(point.marketPrice) ? point.marketPrice : order / Math.max(points.length - 1, 1),
      y: point.probability,
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
    .sort((a, b) => a.x - b.x);

  if (!usable.length) {
    return { slope: 0, intercept: 0, residualSe: 0, samples: [], points: [] };
  }

  const n = usable.length;
  const meanX = usable.reduce((sum, point) => sum + point.x, 0) / n;
  const meanY = usable.reduce((sum, point) => sum + point.y, 0) / n;
  const sxx = usable.reduce((sum, point) => sum + (point.x - meanX) ** 2, 0);
  const sxy = usable.reduce((sum, point) => sum + (point.x - meanX) * (point.y - meanY), 0);
  const slope = sxx > 0 ? sxy / sxx : 0;
  const intercept = meanY - slope * meanX;
  const residuals = usable.map((point) => point.y - (intercept + slope * point.x));
  const residualSe = n > 2 ? Math.sqrt(residuals.reduce((sum, value) => sum + value ** 2, 0) / (n - 2)) : 0.035;
  const minX = usable[0].x;
  const maxX = usable[usable.length - 1].x;
  const sampleCount = Math.min(28, Math.max(usable.length, 6));
  const samples = Array.from({ length: sampleCount }, (_, index) => {
    const x = sampleCount === 1 ? minX : minX + ((maxX - minX) * index) / (sampleCount - 1 || 1);
    const prediction = clampProbability(intercept + slope * x);
    const leverage = sxx > 0 ? Math.sqrt((1 / n) + ((x - meanX) ** 2 / sxx)) : 1;
    const ci = Math.max(0.025, Math.min(0.22, 1.96 * residualSe * leverage));
    return {
      x,
      prediction,
      lower: clampProbability(prediction - ci),
      upper: clampProbability(prediction + ci),
    };
  });

  return { slope, intercept, residualSe, samples, points: usable };
}

function renderModelProgressSummary(models, payload) {
  const marketCount = payload.summary?.marketCount || (payload.marketAnalysisResults || []).length;
  const ensemble = models.find((model) => model.id === "ensemble") || models.at(-1);
  const avgCiWidth = models.reduce((sum, model) => sum + model.averageCiWidth, 0) / Math.max(models.length, 1);
  const avgEdgeRate = models.reduce((sum, model) => sum + model.positiveEdgeRate, 0) / Math.max(models.length, 1);
  return `
    <article class="metric"><span>Models</span><strong>${models.length}</strong></article>
    <article class="metric"><span>Markets</span><strong>${marketCount || 0}</strong></article>
    <article class="metric"><span>Ensemble Bet Rate</span><strong>${formatPercent(ensemble?.betRate || 0)}</strong></article>
    <article class="metric"><span>Positive Edge Rate</span><strong>${formatPercent(avgEdgeRate)}</strong></article>
    <article class="metric"><span>Avg CI Width</span><strong>${formatPercent(avgCiWidth)}</strong></article>
    <article class="metric"><span>Last Estimated</span><strong>${shortTime(ensemble?.latestTimestamp || payload.createdAt)}</strong></article>
  `;
}

function renderModelProgressDetail(model) {
  const slopeLabel = `${model.trend.slope >= 0 ? "+" : ""}${model.trend.slope.toFixed(3)}`;
  return `
    <details class="model-progress-detail" open>
      <summary>
        <span>
          <strong>${escapeHtml(model.label)}</strong>
          <small>${escapeHtml(model.id)} · ${model.points.length} markets · slope ${slopeLabel}</small>
        </span>
        <span class="model-rate-chip">bet-rate ${formatPercent(model.betRate)} · edge ${formatSignedPercent(model.avgEdge)}</span>
      </summary>
      <div class="model-progress-body">
        <div class="model-progress-stats">
          <article><span>Avg forecast</span><strong>${formatPercent(model.avgProbability)}</strong></article>
          <article><span>Avg odds</span><strong>${formatPercent(model.avgMarketPrice)}</strong></article>
          <article><span>Positive edge</span><strong>${formatPercent(model.positiveEdgeRate)}</strong></article>
          <article><span>Fade rate</span><strong>${formatPercent(model.fadeRate)}</strong></article>
          <article><span>News score</span><strong>${formatSignedPercent(model.avgNewsScore)}</strong></article>
          <article><span>Corr score</span><strong>${formatSignedPercent(model.avgCorrelationScore)}</strong></article>
        </div>
        ${renderModelProgressSvg(model)}
        <p class="model-progress-note">${escapeHtml(model.purpose || "Current-run model diagnostics. Confidence bands are residual trend intervals, not settlement guarantees.")}</p>
        <div class="table-wrap model-progress-table">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Market</th>
                <th>Forecast</th>
                <th>Odds</th>
                <th>Edge</th>
                <th>Signal</th>
                <th>Estimated</th>
              </tr>
            </thead>
            <tbody>
              ${model.topEdges.map((point) => `
                <tr>
                  <td>${escapeHtml(point.category)}</td>
                  <td>${escapeHtml(point.marketTitle)}</td>
                  <td>${formatPercent(point.probability)}</td>
                  <td>${formatPercent(point.marketPrice)}</td>
                  <td>${formatSignedPercent(point.edge)}</td>
                  <td>${escapeHtml(point.signal)}</td>
                  <td>${escapeHtml(point.timestamp || "-")}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  `;
}

function renderModelProgressSvg(model) {
  const trend = model.trend;
  if (!trend.points.length) return `<p class="empty-note">No model trend points available.</p>`;
  const width = 680;
  const height = 310;
  const left = 48;
  const right = 26;
  const top = 22;
  const bottom = 44;
  const allY = [
    ...trend.points.map((point) => point.y),
    ...trend.samples.flatMap((sample) => [sample.lower, sample.upper, sample.prediction]),
  ];
  const minY = Math.max(0, Math.min(...allY) - 0.04);
  const maxY = Math.min(1, Math.max(...allY) + 0.04);
  const minX = Math.max(0, Math.min(...trend.points.map((point) => point.x)));
  const maxX = Math.min(1, Math.max(...trend.points.map((point) => point.x)));
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const scaleX = (value) => left + ((value - minX) / Math.max(maxX - minX, 0.001)) * plotWidth;
  const scaleY = (value) => top + (1 - ((value - minY) / Math.max(maxY - minY, 0.001))) * plotHeight;
  const bandTop = trend.samples.map((sample) => `${scaleX(sample.x)},${scaleY(sample.upper)}`).join(" ");
  const bandBottom = [...trend.samples].reverse().map((sample) => `${scaleX(sample.x)},${scaleY(sample.lower)}`).join(" ");
  const trendLine = trend.samples.map((sample) => `${scaleX(sample.x)},${scaleY(sample.prediction)}`).join(" ");
  const idealLine = `${scaleX(minX)},${scaleY(minX)} ${scaleX(maxX)},${scaleY(maxX)}`;
  return `
    <div class="chart-scroll">
      <svg class="model-progress-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(model.label)} probability trend with confidence interval">
        <line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" />
        <line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" />
        <text x="8" y="${scaleY(maxY)}">${formatPercent(maxY)}</text>
        <text x="8" y="${scaleY(minY)}">${formatPercent(minY)}</text>
        <text x="${left}" y="${height - 12}">odds ${formatPercent(minX)}</text>
        <text x="${width - 118}" y="${height - 12}">odds ${formatPercent(maxX)}</text>
        <polygon class="ci-band" points="${bandTop} ${bandBottom}" />
        <polyline class="ideal-line" points="${idealLine}" />
        <polyline class="trend-line" points="${trendLine}" />
        ${trend.points.map((point) => `
          <circle class="${point.edge >= 0 ? "positive" : "negative"}" cx="${scaleX(point.x)}" cy="${scaleY(point.y)}" r="${Math.min(7, Math.max(3, 3 + Math.abs(point.edge) * 20))}">
            <title>${escapeHtml(point.marketTitle)} · forecast ${formatPercent(point.y)} · odds ${formatPercent(point.x)} · edge ${formatSignedPercent(point.edge)}</title>
          </circle>
        `).join("")}
        <text class="chart-caption" x="${left}" y="16">linear trend with 95% residual confidence interval</text>
      </svg>
    </div>
  `;
}

function readProbability(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return clampProbability(number);
}

function clampProbability(value) {
  return Math.max(0, Math.min(1, Number(value || 0)));
}

function slugModelLabel(label) {
  return String(label || "model").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "model";
}

function renderModelHealthRow(row) {
  return `
    <article class="model-health-row">
      <strong>${escapeHtml(row.scope)}</strong>
      <span>samples ${row.sampleCount || 0}</span>
      <span>observed ${row.observedExampleCount || 0}</span>
      <span>labeled ${row.labeledExampleCount || 0}</span>
      <span>Brier ${row.brier === null || row.brier === undefined ? "n/a" : Number(row.brier).toFixed(4)}</span>
      <small>${escapeHtml(row.lastUpdatedAt || "not trained yet")}</small>
    </article>
  `;
}

function renderModelScatter(points) {
  if (!points.length) return `<p class="empty-note">No ML examples persisted yet.</p>`;
  const width = 560;
  const height = 320;
  const pad = 42;
  const scale = (value, axis) => {
    const number = Math.max(0, Math.min(1, Number(value || 0)));
    if (axis === "x") return pad + number * (width - pad * 1.5);
    return height - pad - number * (height - pad * 1.5);
  };
  return `
    <div class="chart-scroll">
      <svg class="model-scatter" viewBox="0 0 ${width} ${height}" role="img" aria-label="Agent probability versus category ML probability">
        <line x1="${pad}" y1="${height - pad}" x2="${width - pad / 2}" y2="${height - pad}" />
        <line x1="${pad}" y1="${height - pad}" x2="${pad}" y2="${pad / 2}" />
        <line class="ideal" x1="${pad}" y1="${height - pad}" x2="${width - pad / 2}" y2="${pad / 2}" />
        <text x="${pad}" y="${height - 10}">agent probability</text>
        <text x="8" y="20">ML probability</text>
        ${points.slice(-320).map((point) => `
          <circle class="category-${escapeHtml(point.category)} ${point.label === 1 ? "win" : point.label === 0 ? "loss" : "pending"}"
            cx="${scale(point.agentProbability, "x")}"
            cy="${scale(point.categoryMlProbability, "y")}"
            r="${point.label === null || point.label === undefined ? 3 : 4}">
            <title>${escapeHtml(point.category)} · ${escapeHtml(point.marketTitle)} · agent ${formatPercent(point.agentProbability)} · ML ${formatPercent(point.categoryMlProbability)}</title>
          </circle>
        `).join("")}
      </svg>
    </div>
    <div class="plot-legend">
      <span><b class="legend-dot pending"></b>pending</span>
      <span><b class="legend-dot win"></b>settled win</span>
      <span><b class="legend-dot loss"></b>settled loss</span>
    </div>
  `;
}

function renderFeatureWeights(rows) {
  if (!rows.length) return `<p class="empty-note">No feature weights available.</p>`;
  return rows.slice(0, 10).map((row) => `
    <details class="weight-scope">
      <summary>${escapeHtml(row.scope)}</summary>
      <div class="weight-columns">
        <div>
          <strong>Positive</strong>
          ${(row.topPositive || []).map(renderWeight).join("") || "<span>none yet</span>"}
        </div>
        <div>
          <strong>Negative</strong>
          ${(row.topNegative || []).map(renderWeight).join("") || "<span>none yet</span>"}
        </div>
      </div>
    </details>
  `).join("");
}

function renderWeight(row) {
  return `<span class="weight-chip">${escapeHtml(row.feature)} ${Number(row.weight).toFixed(4)}</span>`;
}

function renderCorrelationHeatmap(category) {
  const matrix = category.matrix || {};
  const markets = matrix.markets || [];
  const cells = matrix.cells || [];
  if (!markets.length || !cells.length) return `<p class="empty-note">No heatmap: sparse overlapping history.</p>`;
  const index = Object.fromEntries(markets.map((market, idx) => [market.id, idx]));
  const cellByKey = Object.fromEntries(cells.map((cell) => [`${cell.left}:${cell.right}`, cell]));
  return `
    <div class="heatmap-scroll">
      <div class="correlation-heatmap" style="--matrix-size:${markets.length}">
        <span class="matrix-corner"></span>
        ${markets.map((market, idx) => `<span class="matrix-label x" title="${escapeHtml(market.title)}">${idx + 1}</span>`).join("")}
        ${markets.map((market, rowIdx) => `
          <span class="matrix-label y" title="${escapeHtml(market.title)}">${rowIdx + 1}</span>
          ${markets.map((other) => {
            const cell = cellByKey[`${market.id}:${other.id}`] || {};
            const corr = cell.correlation;
            const numeric = corr === null || corr === undefined ? 0 : Number(corr);
            const alpha = Math.min(Math.abs(numeric), 1);
            return `<span class="matrix-cell ${numeric < 0 ? "neg" : "pos"}" style="--alpha:${alpha}" title="${escapeHtml(market.title)} / ${escapeHtml(other.title)} / corr ${corr === null || corr === undefined ? "n/a" : Number(corr).toFixed(3)}"></span>`;
          }).join("")}
        `).join("")}
      </div>
    </div>
    <ol class="matrix-key">
      ${markets.map((market, idx) => `<li>${idx + 1}. ${escapeHtml(market.title)}</li>`).join("")}
    </ol>
  `;
}

function renderCorrelationPair(pair) {
  const corr = Number(pair.correlation || 0);
  return `
    <article class="correlation-pair ${corr < 0 ? "neg" : "pos"}">
      <strong>${corr >= 0 ? "+" : ""}${corr.toFixed(3)}</strong>
      <span>${escapeHtml(pair.leftTitle || pair.left)} / ${escapeHtml(pair.rightTitle || pair.right)}</span>
      <small>related ${formatPercent(pair.relatedness)} · context weight ${Number(pair.contextWeight || 0).toFixed(3)}${pair.sharedEvent ? " · same event" : ""}</small>
    </article>
  `;
}

function shortTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").replace("Z", "");
}

function shortDate(value) {
  if (!value) return "-";
  return String(value).slice(0, 10);
}

function renderDetailPicker(data) {
  const picker = document.getElementById("detailPicker");
  picker.innerHTML = data.recommendations
    .slice(0, 120)
    .map((item) => `<option value="${item.candidate.candidate_id}">${item.candidate.category}: ${escapeHtml(item.candidate.market_title).slice(0, 80)}</option>`)
    .join("");
  picker.onchange = () => renderBetDetail(picker.value);
  if (data.recommendations.length) renderBetDetail(data.recommendations[0].candidate.candidate_id);
}

function renderBetDetail(candidateId) {
  const item = dashboard.recommendations.find((row) => row.candidate.candidate_id === candidateId);
  if (!item) return;
  const candidate = item.candidate;
  const detail = detailRecords()[candidateId] || {};
  const event = (dashboard.event_groups || []).find((row) => row.event_id === candidate.event_id);
  const sourceReviews = sourceReviewsFor(candidate, detail);
  const modelCards = modelCardsFor(item, detail);
  document.getElementById("betDetail").innerHTML = `
    <article class="detail-main state-card state-${detail.state || "planning"}">
      <div class="detail-title-row">
        <span class="category-pill">${candidate.category}</span>
        <span class="state-chip state-${detail.state || "planning"}">${escapeHtml(detail.state_label || item.decision)}</span>
      </div>
      <h2>${escapeHtml(candidate.market_title)}</h2>
      <p><strong>Market gathered:</strong> ${escapeHtml(dashboard.created_at || "-")} · <strong>Estimated:</strong> ${escapeHtml(detail.decision_made_at || dashboard.created_at || "-")}</p>
      <p>${escapeHtml(candidate.resolution_notes)}</p>
      <dl class="lifecycle-dl">
        <dt>Gathered</dt><dd>${escapeHtml(dashboard.created_at || "-")}</dd>
        <dt>Estimated decision time</dt><dd>${escapeHtml(detail.decision_made_at || dashboard.created_at || "-")}</dd>
        <dt>Paper execution time</dt><dd>${escapeHtml(detail.decision_made_at || dashboard.created_at || "-")}</dd>
        <dt>Expected resolution</dt><dd>${escapeHtml(candidate.end_time || "-")}</dd>
        <dt>Resolution status</dt><dd>${escapeHtml(candidate.resolved_outcome || detail.state_label || "expected/pending")}</dd>
      </dl>
      <dl>
        <dt>Outcome</dt><dd>${escapeHtml(candidate.outcome)}</dd>
        <dt>Forecast</dt><dd>${formatPercent(item.blended_probability)}</dd>
        <dt>Forecast band</dt><dd>${formatPercent(detail.forecast_summary?.lower_bound)} to ${formatPercent(detail.forecast_summary?.upper_bound)}</dd>
        <dt>Market price</dt><dd>${formatPercent(candidate.price)}</dd>
        <dt>Decimal odds</dt><dd>${Number(candidate.decimal_odds).toFixed(2)}</dd>
        <dt>Spread</dt><dd>${formatPercent(candidate.spread)}</dd>
        <dt>Liquidity</dt><dd>${formatCoins(candidate.liquidity)}</dd>
        <dt>Volume 24h</dt><dd>${formatCoins(candidate.volume_24h)}</dd>
      </dl>
      <div class="source-actions">
        ${renderMarketLink(candidate.source_url)}
        <button class="open-page" data-page="news" type="button">Open related news</button>
        <button class="open-page" data-page="events" type="button">Open event sub-bets</button>
      </div>
    </article>
    <article class="detail-side">
      <h3>History And Forecast Graph</h3>
      <div class="odds-chart">${renderOddsChart(candidate.odds_history || [], item.blended_probability)}</div>
      <dl class="compact-dl">
        <dt>Trend</dt><dd>${escapeHtml(detail.history_summary?.direction || "flat")}</dd>
        <dt>First / latest</dt><dd>${formatPercent(detail.history_summary?.first_price)} / ${formatPercent(detail.history_summary?.latest_price)}</dd>
        <dt>Min / max</dt><dd>${formatPercent(detail.history_summary?.min_price)} / ${formatPercent(detail.history_summary?.max_price)}</dd>
      </dl>
      <h3>Actors</h3>
      <div class="actor-map">${(candidate.actors || []).map((actor) => `<span>${escapeHtml(actor)}</span>`).join("") || "<span>Market participants</span>"}</div>
    </article>
    <section class="detail-section">
      <h3>Collection And Model Lifecycle</h3>
      <div class="process-flow">
        ${renderLifecycleStep("Gathered", dashboard.created_at, "Public market and odds data retrieved for the research snapshot.", "1")}
        ${renderLifecycleStep("Estimated", detail.decision_made_at || dashboard.created_at, "Forecast and reliability metrics computed from timestamp-valid inputs.", "2")}
        ${renderLifecycleStep("Paper timestamp", detail.decision_made_at || dashboard.created_at, "Research-only paper timestamp recorded; no wallet or order execution.", "3")}
        ${renderLifecycleStep("Resolution", candidate.end_time, candidate.resolved_outcome ? `Resolved as ${candidate.resolved_outcome}.` : "Expected/pending resolution status.", "4")}
      </div>
    </section>
    <section class="detail-section">
      <h3>Reviewed Sources And Queries</h3>
      <div class="source-grid">${sourceReviews.map(renderSourceReview).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>News Motivation</h3>
      <p>${escapeHtml(detail.news_motivation || "")}</p>
      <ul class="timeline">${(candidate.news_items || []).map(renderNewsItem).join("")}</ul>
    </section>
    <section class="detail-section">
      <h3>Monitored Values</h3>
      <div class="monitor-grid">${(detail.monitored_values || []).map(renderMonitoredValue).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Models And Forecasting</h3>
      <div class="agent-grid">${modelCards.map(renderModelCard).join("")}</div>
    </section>
    <section class="detail-section">
      <h3>Failure Conditions</h3>
      <ul>${item.failure_conditions.map((condition) => `<li>${escapeHtml(condition)}</li>`).join("")}</ul>
    </section>
    <section class="detail-section">
      <h3>Event Sub-Bets</h3>
      <div class="sub-bets">${(event?.sub_bets || []).map((bet) => `
        <button class="sub-bet state-${bet.state}" type="button" data-id="${bet.candidate_id}">
          <span>${escapeHtml(bet.outcome)}</span>
          <strong>${formatPercent(bet.probability)}</strong>
          <small>${escapeHtml(bet.decision)} · ${formatCoins(bet.stake_units)} coins</small>
        </button>
      `).join("")}</div>
    </section>
  `;
  bindDetailRows();
  document.querySelectorAll(".open-page").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.page));
  });
}

function sourceReviewsFor(candidate, detail) {
  const shared = dashboard.source_reviews_by_category?.[candidate.category] || [];
  const queries = Object.fromEntries((detail.source_queries || []).map((row) => [row.source_id, row.query]));
  const ids = new Set(detail.source_review_ids || shared.map((row) => row.id));
  return shared
    .filter((source) => ids.has(source.id))
    .map((source) => ({
      ...source,
      query: queries[source.id] || source.query_template || source.name,
    }));
}

function modelCardsFor(item, detail) {
  const cards = Object.entries(item.assessments || {}).map(([key, assessment]) => ({
    agent: key,
    probability: assessment.probability,
    confidence: assessment.confidence,
    score: assessment.score,
    rationale: assessment.rationale,
    features: assessment.features || {},
    flags: assessment.flags || [],
  }));
  const blend = (detail.model_cards || []).find((card) => card.agent === "forecast_blend");
  if (blend) cards.push(blend);
  return cards;
}

function renderLifecycleStep(label, time, body, marker) {
  return `
    <article class="process-step">
      <span class="step-marker">${escapeHtml(marker || label.slice(0, 1))}</span>
      <div class="process-step-body">
        <header class="process-step-header">
          <strong>${escapeHtml(label)}</strong>
          <time>${escapeHtml(time || "-")}</time>
        </header>
        <p>${escapeHtml(body || "")}</p>
      </div>
    </article>
  `;
}

function renderDecisionStep(step) {
  return `
    <article class="process-step status-${step.status}">
      <span>${step.step}</span>
      <div>
        <h4>${escapeHtml(step.title)}</h4>
        <p>${escapeHtml(step.motivation)}</p>
        <div class="step-links">${(step.links || []).map((link) => renderExternalLink(link.label, link.url)).join("")}</div>
      </div>
    </article>
  `;
}

function renderSourceReview(source) {
  return `
    <article class="source-review ${source.allowed_by_default ? "enabled" : "disabled"}">
      <header>
        <strong>${escapeHtml(source.name)}</strong>
        <span>${escapeHtml(source.reliability_tier)}</span>
      </header>
      <p>${escapeHtml(source.query)}</p>
      <small>${escapeHtml(source.review_status)} · ${escapeHtml((source.used_by_agents || []).join(", "))}</small>
      ${renderExternalLink("Open source", source.url)}
    </article>
  `;
}

function renderNewsItem(news) {
  const direction = trendArrow(news.impact);
  return `
    <li class="${direction}">
      <strong>${direction === "up" ? "↑" : direction === "down" ? "↓" : "→"} ${escapeHtml(news.source)}</strong>
      <span>${escapeHtml(news.headline)}</span>
      <small>${escapeHtml(news.time || "")} · impact ${formatSignedPercent(news.impact)} · credibility ${formatPercent(news.credibility)}</small>
    </li>
  `;
}

function renderMonitoredValue(item) {
  const direction = item.format === "signed_percent" ? trendArrow(item.value) : "flat";
  const explanation = item.explanation || monitorExplanation(item.name);
  return `
    <article class="monitor-card ${direction}">
      <span>${escapeHtml(item.name)}</span>
      <strong>${formatValue(item.value, item.format)}</strong>
      <p>${escapeHtml(explanation)}</p>
    </article>
  `;
}

function monitorExplanation(name) {
  const explanations = {
    "Blended probability": "Final model probability after agent blend.",
    "Market price": "Current market-implied probability.",
    "Expected value": "Estimated value versus current price.",
    Spread: "Liquidity friction; wide spread reduces reliability.",
    Liquidity: "Available market depth proxy.",
    "Volume 24h": "Recent activity proxy.",
    "Trend slope": "Direction of recent price movement.",
    "Resolution ambiguity": "Settlement wording risk.",
    "Bet research score": "Source depth, reliability, and contradiction-adjusted readiness.",
  };
  return explanations[name] || "Monitored input used by the paper decision process.";
}

function renderModelCard(card) {
  return `
    <details class="agent-card" open>
      <summary>${escapeHtml(card.agent.replaceAll("_", " "))}</summary>
      <dl>
        <dt>Probability</dt><dd>${formatPercent(card.probability)}</dd>
        <dt>Confidence</dt><dd>${formatPercent(card.confidence)}</dd>
        <dt>Score</dt><dd>${Number(card.score || 0).toFixed(4)}</dd>
      </dl>
      <p>${escapeHtml(card.rationale || modelRationale(card.agent))}</p>
      <small>${(card.flags || []).map(escapeHtml).join(", ") || "no flags"}</small>
      <pre class="feature-pre">${escapeHtml(JSON.stringify(card.features || card.summary_features || { feature_keys: card.feature_keys || [] }, null, 2))}</pre>
    </details>
  `;
}

function modelRationale(agent) {
  const rationales = {
    odds_modeling: "Reviews price history, log-odds movement, velocity, acceleration, volatility, spread, and liquidity.",
    market_context_news: "Reviews news direction, source credibility, actor map, timeline, source depth, and settlement ambiguity.",
    category_expert: "Applies category-specific liquidity, spread, wording, and source reliability gates.",
    forecast_blend: "Blends model, context, and category probabilities before portfolio and resolution-risk controls.",
  };
  return rationales[agent] || "Model output used in the paper decision process.";
}

function renderMarketLink(url) {
  if (!url) return "";
  if (!url.startsWith("http")) return `<span class="local-link">${escapeHtml(url)}</span>`;
  return renderExternalLink("Open market", url);
}

function renderExternalLink(label, url) {
  if (!url) return "";
  if (!url.startsWith("http")) return `<span class="local-link">${escapeHtml(label)}: ${escapeHtml(url)}</span>`;
  return `<a class="external-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function renderOddsChart(history, forecast) {
  const values = history.map((point) => Number(point.price));
  const allValues = [...values, Number(forecast)];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const bars = history
    .map((point) => {
      const height = max === min ? 45 : 12 + ((Number(point.price) - min) / (max - min)) * 78;
      return `<span title="${point.time}: ${formatPercent(point.price)}" style="height:${height}px"></span>`;
    })
    .join("");
  return `${bars}<b style="height:${max === min ? 45 : 12 + ((Number(forecast) - min) / (max - min)) * 78}px" title="forecast ${formatPercent(forecast)}"></b>`;
}

function renderLearning(data) {
  document.getElementById("calibration").innerHTML = data.metrics.calibration
    .map((bucket) => {
      const winRate = bucket.actual_win_rate === null ? 0 : Number(bucket.actual_win_rate);
      const label = bucket.actual_win_rate === null ? "n/a" : formatPercent(bucket.actual_win_rate);
      return `
        <div class="cal-row">
          <span>${bucket.label}</span>
          <div class="bar"><span style="width:${Math.max(winRate * 100, 2)}%"></span></div>
          <strong>${label}</strong>
        </div>
      `;
    })
    .join("");
  document.getElementById("mistakes").innerHTML = data.mistakes
    .map((mistake) => `
      <article class="bet-card">
        <header>
          <span class="category-pill">${mistake.category}</span>
          <span class="badge no">${mistake.mistake_type.replaceAll("_", " ")}</span>
        </header>
        <h3>${escapeHtml(mistake.market_title)}</h3>
        <p>${escapeHtml(mistake.learning_note)}</p>
        <strong>${formatCoins(mistake.pnl_units)} coins</strong>
      </article>
    `)
    .join("");
}

function renderAgents(data) {
  document.getElementById("agentRows").innerHTML = data.agent_performance
    .map((row) => `
      <tr>
        <td>${row.agent.replaceAll("_", " ")}</td>
        <td>${Number(row.score).toFixed(2)}</td>
        <td>${row.brier === null ? "n/a" : Number(row.brier).toFixed(4)}</td>
        <td>${row.confidence === null ? "n/a" : formatPercent(row.confidence)}</td>
        <td>${escapeHtml(row.notes)}</td>
      </tr>
    `)
    .join("");
}

function bindDetailRows() {
  document.querySelectorAll("[data-id]").forEach((row) => {
    if (row.dataset.bound === "true") return;
    row.dataset.bound = "true";
    row.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      selectBet(row.dataset.id);
    });
  });
}

function selectBet(candidateId) {
  showPage("details");
  const picker = document.getElementById("detailPicker");
  if ([...picker.options].some((option) => option.value === candidateId)) {
    picker.value = candidateId;
  }
  renderBetDetail(candidateId);
}

function decisionClass(decision) {
  if (decision === "PAPER_BET") return "play";
  if (decision === "WATCHLIST") return "watch";
  return "no";
}

function showPage(pageId) {
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === pageId));
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.page === pageId));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});

const requestedPage = new URLSearchParams(window.location.search).get("page") || window.location.hash.slice(1);
if (requestedPage && document.getElementById(requestedPage)) {
  showPage(requestedPage);
}

document.getElementById("refreshButton").addEventListener("click", async () => {
  const button = document.getElementById("refreshButton");
  button.disabled = true;
  button.textContent = "Running";
  try {
    await loadDashboard(true);
  } finally {
    button.disabled = false;
    button.textContent = "Run Cycle";
  }
});

loadDashboard().catch((error) => {
  document.body.insertAdjacentHTML("afterbegin", `<pre>${escapeHtml(error.message)}</pre>`);
});

setInterval(() => {
  loadDashboard(true).catch((error) => console.error(error));
}, AUTO_REFRESH_MS);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    loadDashboard(false).catch((error) => console.error(error));
  }
});
