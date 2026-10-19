// Rico Multi-Model Gateway & TokenOps Proxy — Client Engine
document.addEventListener('DOMContentLoaded', () => {
  // Navigation
  const tabButtons = document.querySelectorAll('.nav-item[data-tab]');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const gatewayStatus = document.getElementById('gateway-status');

  // Tab switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      tabButtons.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add('active');

      if (targetId === 'tab-mesh') refreshCircuits();
      if (targetId === 'tab-quotas') refreshQuotas();
      if (targetId === 'tab-metrics') refreshMetrics();
    });
  });

  // Render navigation shortcut
  const btnRenderNav = document.getElementById('btn-render-nav');
  if (btnRenderNav) {
    btnRenderNav.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = document.querySelector('.nav-item[data-tab="tab-render"]');
      if (tab) tab.click();
    });
  }

  // Copy helper
  document.querySelectorAll('.btn-copy').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const el = document.getElementById(targetId);
      if (!el) return;
      navigator.clipboard.writeText(el.textContent).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = orig; }, 1500);
      });
    });
  });

  // ── Tab 1: Circuit Breaker Mesh ──
  const btnRefreshMesh = document.getElementById('btn-refresh-mesh');
  const btnResetAll = document.getElementById('btn-reset-all-circuits');

  async function refreshCircuits() {
    try {
      const res = await fetch('/v1/circuits');
      if (res.ok) {
        const circuits = await res.json();
        updateCircuitUI(circuits);
      }
    } catch (e) {
      // Offline fallback state
      updateCircuitUI([
        { model_id: 'gpt-4o', state: 'CLOSED', consecutive_failures: 0, total_trips: 0 },
        { model_id: 'gpt-4o-mini', state: 'CLOSED', consecutive_failures: 0, total_trips: 0 },
        { model_id: 'llama-3-8b-local', state: 'CLOSED', consecutive_failures: 0, total_trips: 0 },
      ]);
    }
  }

  function updateCircuitUI(circuits) {
    circuits.forEach(c => {
      const badge = document.getElementById(`status-${c.model_id}`);
      const fails = document.getElementById(`fails-${c.model_id}`);
      const trips = document.getElementById(`trips-${c.model_id}`);

      if (badge) {
        badge.textContent = c.state;
        badge.className = `circuit-status ${c.state.toLowerCase()}`;
      }
      if (fails) fails.textContent = `${c.consecutive_failures} / ${c.failure_threshold || 3}`;
      if (trips) trips.textContent = c.total_trips || 0;
    });
  }

  // Chaos: Trip / Reset individual models
  document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('btn-trip-model')) {
      const modelId = e.target.getAttribute('data-model');
      try {
        await fetch(`/v1/circuits/${modelId}/trip`, { method: 'POST' });
        refreshCircuits();
      } catch (err) {
        const badge = document.getElementById(`status-${modelId}`);
        if (badge) {
          badge.textContent = 'OPEN';
          badge.className = 'circuit-status open';
        }
      }
    } else if (e.target.classList.contains('btn-reset-model')) {
      const modelId = e.target.getAttribute('data-model');
      try {
        await fetch(`/v1/circuits/${modelId}/reset`, { method: 'POST' });
        refreshCircuits();
      } catch (err) {
        const badge = document.getElementById(`status-${modelId}`);
        if (badge) {
          badge.textContent = 'CLOSED';
          badge.className = 'circuit-status closed';
        }
      }
    }
  });

  btnResetAll.addEventListener('click', async () => {
    const models = ['gpt-4o', 'gpt-4o-mini', 'llama-3-8b-local'];
    for (const m of models) {
      try {
        await fetch(`/v1/circuits/${m}/reset`, { method: 'POST' });
      } catch (e) {
        const badge = document.getElementById(`status-${m}`);
        if (badge) {
          badge.textContent = 'CLOSED';
          badge.className = 'circuit-status closed';
        }
      }
    }
    refreshCircuits();
  });

  if (btnRefreshMesh) btnRefreshMesh.addEventListener('click', refreshCircuits);

  // ── Tab 2: Chat Console & Live Failover ──
  const chatInput = document.getElementById('chat-input-prompt');
  const chatTeamSelect = document.getElementById('chat-team-select');
  const chatResponseOutput = document.getElementById('chat-response-output');
  const chatFallbackBadge = document.getElementById('chat-fallback-badge');
  const chatLatencyBadge = document.getElementById('chat-latency-badge');
  const chatTraceId = document.getElementById('chat-trace-id');
  const traceModelVal = document.getElementById('trace-model-val');
  const traceFailoverVal = document.getElementById('trace-failover-val');
  const traceTokensVal = document.getElementById('trace-tokens-val');
  const btnSendChat = document.getElementById('btn-send-chat');

  async function sendChatRequest() {
    chatFallbackBadge.className = 'badge-status ready';
    chatFallbackBadge.textContent = 'ROUTING MESH';

    const teamId = chatTeamSelect.value;
    const prompt = chatInput.value.trim();

    const payload = {
      model: 'gpt-4o',
      messages: [{ role: 'user', content: prompt }],
      team_id: teamId,
    };

    const startTime = performance.now();
    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Team-ID': teamId,
        },
        body: JSON.stringify(payload),
      });

      const latency = (performance.now() - startTime).toFixed(2);
      const data = await res.json();

      if (res.ok) {
        const choice = data.choices[0];
        const trace = data.fallback_trace;

        chatResponseOutput.textContent = choice.message.content;
        traceModelVal.textContent = data.model;

        if (trace.fallback_triggered) {
          chatFallbackBadge.className = 'badge-status warn';
          chatFallbackBadge.textContent = 'FAILOVER ACTIVE';
          traceFailoverVal.innerHTML = `<span style="color: var(--accent-amber);">TRUE &bull; Primary failed &rarr; degraded to ${data.model}</span>`;
        } else {
          chatFallbackBadge.className = 'badge-status success';
          chatFallbackBadge.textContent = 'PRIMARY HEALTHY';
          traceFailoverVal.innerHTML = `<span style="color: var(--accent-green);">FALSE &bull; Primary fulfilled request</span>`;
        }

        traceTokensVal.textContent = `${data.usage.total_tokens} tokens (${data.usage.prompt_tokens} prompt + ${data.usage.completion_tokens} completion)`;
        chatLatencyBadge.textContent = `${trace.total_latency_ms || latency} ms`;
        chatTraceId.textContent = `Trace: ${res.headers.get('X-Trace-Id') || 'trace_mesh_01'}`;
      } else {
        chatFallbackBadge.className = 'badge-status error';
        chatFallbackBadge.textContent = `ERROR ${res.status}`;
        chatResponseOutput.textContent = JSON.stringify(data, null, 2);
        chatLatencyBadge.textContent = `${latency} ms`;
      }
    } catch (err) {
      // Offline fallback simulation
      simulateOfflineChat(teamId, prompt);
    }

    refreshCircuits();
    refreshQuotas();
  }

  function simulateOfflineChat(teamId, prompt) {
    const isPrimaryOpen = document.getElementById('status-gpt-4o')?.textContent === 'OPEN';
    const isSecondaryOpen = document.getElementById('status-gpt-4o-mini')?.textContent === 'OPEN';

    let modelUsed = 'gpt-4o';
    let failover = false;

    if (isPrimaryOpen && !isSecondaryOpen) {
      modelUsed = 'gpt-4o-mini';
      failover = true;
    } else if (isPrimaryOpen && isSecondaryOpen) {
      modelUsed = 'llama-3-8b-local';
      failover = true;
    }

    traceModelVal.textContent = modelUsed;
    if (failover) {
      chatFallbackBadge.className = 'badge-status warn';
      chatFallbackBadge.textContent = 'FAILOVER ACTIVE';
      traceFailoverVal.innerHTML = `<span style="color: var(--accent-amber);">TRUE &bull; Primary failed &rarr; degraded to ${modelUsed}</span>`;
    } else {
      chatFallbackBadge.className = 'badge-status success';
      chatFallbackBadge.textContent = 'PRIMARY HEALTHY';
      traceFailoverVal.innerHTML = `<span style="color: var(--accent-green);">FALSE &bull; Primary fulfilled request</span>`;
    }

    chatResponseOutput.textContent = `[${modelUsed}] Successfully processed request for ${teamId}!\nResponse: Safe and resilient answer to '${prompt.substring(0, 45)}...'`;
    traceTokensVal.textContent = `42 tokens (22 prompt + 20 completion)`;
    chatLatencyBadge.textContent = `28.50 ms`;
    chatTraceId.textContent = `Trace: 00-mock-trace-offline-01`;
  }

  btnSendChat.addEventListener('click', sendChatRequest);

  // ── Tab 3: Team TokenOps Quotas ──
  const btnRefreshQuotas = document.getElementById('btn-refresh-quotas');

  async function refreshQuotas() {
    try {
      const res = await fetch('/v1/quotas/teams');
      if (res.ok) {
        const teams = await res.json();
        updateQuotasUI(teams);
      }
    } catch (e) {
      // Default offline visualization
    }
  }

  function updateQuotasUI(teams) {
    teams.forEach(t => {
      const rpmText = document.getElementById(`rpm-text-${t.team_id}`);
      const rpmBar = document.getElementById(`rpm-bar-${t.team_id}`);
      const tpmText = document.getElementById(`tpm-text-${t.team_id}`);
      const tpmBar = document.getElementById(`tpm-bar-${t.team_id}`);

      if (rpmText) rpmText.textContent = `${t.current_rpm} / ${t.rpm_limit} RPM (${t.rpm_utilization_pct}%)`;
      if (rpmBar) rpmBar.style.width = `${Math.min(100, t.rpm_utilization_pct)}%`;

      if (tpmText) tpmText.textContent = `${t.available_tokens.toLocaleString()} / ${t.tpm_limit.toLocaleString()} TPM`;
      if (tpmBar) {
        const availPct = Math.max(0, 100 - t.tpm_utilization_pct);
        tpmBar.style.width = `${availPct}%`;
      }
    });
  }

  if (btnRefreshQuotas) btnRefreshQuotas.addEventListener('click', refreshQuotas);

  // ── Tab 4: Prometheus Metrics ──
  const metricsOutput = document.getElementById('metrics-output');
  const btnRefreshMetrics = document.getElementById('btn-refresh-metrics');

  async function refreshMetrics() {
    metricsOutput.textContent = 'Fetching /metrics stream...';
    try {
      const res = await fetch('/metrics');
      if (res.ok) {
        metricsOutput.textContent = await res.text();
      } else {
        metricsOutput.textContent = getSamplePrometheus();
      }
    } catch (e) {
      metricsOutput.textContent = getSamplePrometheus();
    }
  }

  function getSamplePrometheus() {
    return `# HELP rico_requests_total Total number of LLM proxy requests processed.
# TYPE rico_requests_total counter
rico_requests_total{team="team-ai-agents",model="gpt-4o",status="success",fallback="false"} 245
rico_requests_total{team="team-analytics",model="gpt-4o-mini",status="success",fallback="true"} 18
rico_requests_total{team="team-growth",model="llama-3-8b-local",status="success",fallback="true"} 4

# HELP rico_tokens_consumed_total Total LLM tokens consumed per team and model.
# TYPE rico_tokens_consumed_total counter
rico_tokens_consumed_total{team="team-ai-agents",model="gpt-4o",type="total"} 142500
rico_tokens_consumed_total{team="team-analytics",model="gpt-4o-mini",type="total"} 8940

# HELP rico_circuit_state Current circuit state (0=CLOSED, 1=HALF_OPEN, 2=OPEN).
# TYPE rico_circuit_state gauge
rico_circuit_state{model="gpt-4o"} 0
rico_circuit_state{model="gpt-4o-mini"} 0
rico_circuit_state{model="llama-3-8b-local"} 0

# HELP rico_request_duration_seconds Request latency in seconds.
# TYPE rico_request_duration_seconds histogram
rico_request_duration_seconds_bucket{team="team-ai-agents",model="gpt-4o",le="0.05"} 120
rico_request_duration_seconds_bucket{team="team-ai-agents",model="gpt-4o",le="0.1"} 210
rico_request_duration_seconds_bucket{team="team-ai-agents",model="gpt-4o",le="+Inf"} 245
rico_request_duration_seconds_sum{team="team-ai-agents",model="gpt-4o"} 7.8240
rico_request_duration_seconds_count{team="team-ai-agents",model="gpt-4o"} 245`;
  }

  if (btnRefreshMetrics) btnRefreshMetrics.addEventListener('click', refreshMetrics);

  // Global Ctrl+Enter shortcut
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      const activeTab = document.querySelector('.tab-pane.active');
      if (activeTab.id === 'tab-console') sendChatRequest();
    }
  });

  // Initial load
  fetch('/health').then(r => r.json()).then(d => {
    gatewayStatus.textContent = `Gateway: Online (${d.service} v${d.version})`;
  }).catch(() => {
    gatewayStatus.textContent = 'Gateway: Offline / Preview';
  });

  refreshCircuits();
  refreshQuotas();
});
