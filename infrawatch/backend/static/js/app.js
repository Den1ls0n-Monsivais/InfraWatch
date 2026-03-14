/* InfraWatch — Frontend SPA */

const API = '';
let token = localStorage.getItem('iw_token');
let currentUser = null;
let refreshTimer = null;
let cpuChart = null, ramChart = null;

// ─── AUTH ────────────────────────────────────────────────────────────────────

async function doLogin() {
  const u = document.getElementById('l-user').value;
  const p = document.getElementById('l-pass').value;
  const err = document.getElementById('login-err');
  err.textContent = '';
  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username: u, password: p})
    });
    if (!res.ok) { err.textContent = 'Credenciales incorrectas'; return; }
    const data = await res.json();
    token = data.token;
    localStorage.setItem('iw_token', token);
    currentUser = data;
    showApp();
  } catch(e) {
    err.textContent = 'Error de conexión con el servidor';
  }
}

function doLogout() {
  token = null;
  currentUser = null;
  localStorage.removeItem('iw_token');
  if (refreshTimer) clearInterval(refreshTimer);
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(`${API}${url}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(opts.headers || {})
    }
  });
  if (res.status === 401) { doLogout(); return null; }
  return res;
}

async function apiGet(url)         { const r = await apiFetch(url); return r ? r.json() : null; }
async function apiPost(url, body)  { const r = await apiFetch(url, {method:'POST', body: JSON.stringify(body)}); return r ? r.json() : null; }
async function apiPut(url, body)   { const r = await apiFetch(url, {method:'PUT',  body: JSON.stringify(body)}); return r ? r.json() : null; }
async function apiDelete(url)      { const r = await apiFetch(url, {method:'DELETE'}); return r ? r.json() : null; }

// ─── INIT ────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
  if (token) {
    try {
      const res = await apiFetch('/api/auth/me');
      if (res && res.ok) {
        currentUser = await res.json();
        showApp();
        return;
      }
    } catch(e) {}
    token = null; localStorage.removeItem('iw_token');
  }
  document.getElementById('login-screen').style.display = 'flex';
});

function showApp() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('sidebar-user').textContent = currentUser.username;
  document.getElementById('sidebar-role').textContent  = currentUser.role;
  if (currentUser.role === 'admin') {
    document.getElementById('nav-users').style.display = '';
  }
  // Nav links
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const view = link.dataset.view;
      document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      showView(view);
    });
  });
  showView('dashboard');
  startAutoRefresh();
}

function showView(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const el = document.getElementById(`view-${view}`);
  if (el) el.classList.add('active');
  loadView(view);
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    // Update alert badge
    const alerts = await apiGet('/api/alerts');
    if (alerts) {
      const unack = alerts.filter(a => !a.acknowledged).length;
      const badge = document.getElementById('alert-badge');
      badge.textContent = unack > 0 ? unack : '';
    }
    // Refresh active view quietly
    const activeView = document.querySelector('.view.active');
    if (activeView && activeView.id === 'view-dashboard') loadDashboard(true);
    if (activeView && activeView.id === 'view-inventory') loadInventory(true);
  }, 15000);
}

// ─── VIEW ROUTER ─────────────────────────────────────────────────────────────

function loadView(view) {
  switch(view) {
    case 'dashboard':   loadDashboard(); break;
    case 'inventory':   loadInventory(); break;
    case 'assets':      loadAssets(); break;
    case 'maintenance': loadMaintenance(); break;
    case 'alerts':      loadAlerts(); break;
    case 'users':       loadUsers(); break;
  }
}

// ─── DASHBOARD ───────────────────────────────────────────────────────────────

async function loadDashboard(silent = false) {
  const [dash, agents] = await Promise.all([apiGet('/api/dashboard'), apiGet('/api/agents')]);
  if (!dash || !agents) return;
  const el = document.getElementById('view-dashboard');

  if (!silent || !el.innerHTML) {
    el.innerHTML = `
    <div class="page-header">
      <div><h2>🖥 Panel de Control</h2><p>Vista general de infraestructura en tiempo real</p></div>
      <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Actualizar</button>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-icon">🖥</div>
        <div class="stat-label">Total Hosts</div>
        <div class="stat-value">${dash.agents.total}</div>
        <div class="stat-sub">Equipos registrados</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon">✅</div>
        <div class="stat-label">En Línea</div>
        <div class="stat-value" style="color:var(--green)">${dash.agents.online}</div>
        <div class="stat-sub">Respondiendo</div>
      </div>
      <div class="stat-card red">
        <div class="stat-icon">❌</div>
        <div class="stat-label">Fuera de Línea</div>
        <div class="stat-value" style="color:var(--red)">${dash.agents.offline}</div>
        <div class="stat-sub">Sin respuesta</div>
      </div>
      <div class="stat-card yellow">
        <div class="stat-icon">🔔</div>
        <div class="stat-label">Alertas</div>
        <div class="stat-value" style="color:var(--yellow)">${dash.alerts.unacknowledged}</div>
        <div class="stat-sub">${dash.alerts.critical} críticas</div>
      </div>
      <div class="stat-card purple">
        <div class="stat-icon">📦</div>
        <div class="stat-label">Activos Fijos</div>
        <div class="stat-value" style="color:var(--purple)">${dash.assets.total}</div>
        <div class="stat-sub">${dash.assets.active} activos</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🔧</div>
        <div class="stat-label">Mantenimientos</div>
        <div class="stat-value">${dash.maintenance.pending}</div>
        <div class="stat-sub">Pendientes</div>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-title">CPU Promedio — Últimos hosts activos</div>
        <div class="chart-wrap"><canvas id="chart-cpu"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">RAM Promedio — Últimos hosts activos</div>
        <div class="chart-wrap"><canvas id="chart-ram"></canvas></div>
      </div>
    </div>
    <div class="section-title">Estado de Hosts (NOC View)</div>
    <div class="noc-grid" id="noc-grid"></div>`;
  }

  // Render NOC cards
  const grid = document.getElementById('noc-grid');
  if (grid) {
    grid.innerHTML = agents.map(a => renderNocCard(a)).join('');
  }

  // Charts
  buildDashCharts(dash, agents);
}

function renderNocCard(a) {
  const tags = (a.tags || []).map(t => `<span class="tag">${t}</span>`).join('');
  const m = a.metrics || {};
  const offlineCls = a.status === 'offline' ? ' offline' : '';
  const lastSeen = a.last_seen ? timeAgo(a.last_seen) : '—';

  const cpuColor = m.cpu_percent > 90 ? 'bar-high' : m.cpu_percent > 70 ? 'bar-mid' : 'bar-low';
  const ramColor = m.ram_percent > 90 ? 'bar-high' : m.ram_percent > 70 ? 'bar-mid' : 'bar-low';
  const dskColor = m.disk_percent > 90 ? 'bar-high' : m.disk_percent > 70 ? 'bar-mid' : 'bar-low';

  return `
  <div class="noc-card${offlineCls}" onclick="loadAgentDetail(${a.id})">
    <div class="noc-card-header">
      <div>
        <div class="noc-hostname">${escHtml(a.hostname)}</div>
        <div class="noc-ip">${a.ip_address} <span style="color:var(--text2);font-size:10px">${a.mac_address || ''}</span></div>
      </div>
      <span class="status status-${a.status}">${a.status === 'online' ? 'Online' : 'Offline'}</span>
    </div>
    ${a.status === 'online' && m.cpu_percent !== undefined ? `
    <div class="noc-metrics">
      <div class="noc-metric-row">
        <span class="noc-metric-label">CPU</span>
        <div class="bar"><div class="bar-fill ${cpuColor}" style="width:${m.cpu_percent}%"></div></div>
        <span class="bar-value">${m.cpu_percent?.toFixed(0)}%</span>
      </div>
      <div class="noc-metric-row">
        <span class="noc-metric-label">RAM</span>
        <div class="bar"><div class="bar-fill ${ramColor}" style="width:${m.ram_percent}%"></div></div>
        <span class="bar-value">${m.ram_percent?.toFixed(0)}%</span>
      </div>
      <div class="noc-metric-row">
        <span class="noc-metric-label">Disco</span>
        <div class="bar"><div class="bar-fill ${dskColor}" style="width:${m.disk_percent}%"></div></div>
        <span class="bar-value">${m.disk_percent?.toFixed(0)}%</span>
      </div>
    </div>` : `<p class="text-muted" style="font-size:12px;margin-top:8px">Último visto: ${lastSeen}</p>`}
    <div class="noc-tags">${tags}</div>
  </div>`;
}

function buildDashCharts(dash, agents) {
  const online = agents.filter(a => a.status === 'online' && a.metrics);
  const labels = online.slice(0, 12).map(a => a.hostname.split('.')[0]);
  const cpus   = online.slice(0, 12).map(a => a.metrics.cpu_percent?.toFixed(1) || 0);
  const rams   = online.slice(0, 12).map(a => a.metrics.ram_percent?.toFixed(1) || 0);

  const chartOpts = (color) => ({
    type: 'bar',
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8b949e', font: {size: 10} }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e', font: {size: 10} }, grid: { color: '#21262d' }, min: 0, max: 100 }
      }
    }
  });

  const cpuCtx = document.getElementById('chart-cpu');
  const ramCtx = document.getElementById('chart-ram');
  if (!cpuCtx || !ramCtx) return;

  if (cpuChart) cpuChart.destroy();
  if (ramChart) ramChart.destroy();

  cpuChart = new Chart(cpuCtx, {
    ...chartOpts('#58a6ff'),
    data: {
      labels,
      datasets: [{ data: cpus, backgroundColor: cpus.map(v => v > 80 ? '#f85149' : v > 60 ? '#d29922' : '#58a6ff'), borderRadius: 4 }]
    }
  });
  ramChart = new Chart(ramCtx, {
    ...chartOpts('#3fb950'),
    data: {
      labels,
      datasets: [{ data: rams, backgroundColor: rams.map(v => v > 80 ? '#f85149' : v > 60 ? '#d29922' : '#3fb950'), borderRadius: 4 }]
    }
  });
}

// ─── AGENT DETAIL ────────────────────────────────────────────────────────────

async function loadAgentDetail(agentId) {
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-agent-detail').classList.add('active');

  const el = document.getElementById('view-agent-detail');
  el.innerHTML = `<div class="text-muted">Cargando...</div>`;

  const a = await apiGet(`/api/agents/${agentId}`);
  if (!a) return;

  const tags = (a.tags || []).map(t => `<span class="tag">${escHtml(t)}</span>`).join('') || '—';
  const history = a.metrics_history || [];
  const latest  = history[history.length - 1] || {};

  el.innerHTML = `
  <div class="detail-header">
    <button class="detail-back" onclick="showView('inventory')">← Volver</button>
    <div>
      <h2 style="font-size:20px">${escHtml(a.hostname)}</h2>
      <span class="status status-${a.status}" style="margin-top:4px">${a.status}</span>
    </div>
    <div style="margin-left:auto;display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id}, ${JSON.stringify(a.tags || []).replace(/"/g,"'")})">🏷 Tags</button>
      <button class="btn btn-danger btn-sm" onclick="deleteAgent(${a.id})">🗑 Eliminar</button>
    </div>
  </div>

  <div class="detail-info-grid">
    <div class="info-card"><div class="info-card-label">IP Address</div><div class="info-card-value">${a.ip_address}</div></div>
    <div class="info-card"><div class="info-card-label">MAC Address</div><div class="info-card-value">${a.mac_address}</div></div>
    <div class="info-card"><div class="info-card-label">Sistema Operativo</div><div class="info-card-value">${a.os_name} ${a.os_version}</div></div>
    <div class="info-card"><div class="info-card-label">CPU</div><div class="info-card-value">${a.cpu_model || '—'} (${a.cpu_cores || '?'} cores)</div></div>
    <div class="info-card"><div class="info-card-label">RAM Total</div><div class="info-card-value">${a.ram_total_gb?.toFixed(1)} GB</div></div>
    <div class="info-card"><div class="info-card-label">Disco Total</div><div class="info-card-value">${a.disk_total_gb?.toFixed(1)} GB</div></div>
    <div class="info-card"><div class="info-card-label">Tags</div><div class="info-card-value" style="font-size:12px">${tags}</div></div>
    <div class="info-card"><div class="info-card-label">Último Visto</div><div class="info-card-value" style="font-size:12px">${a.last_seen ? new Date(a.last_seen).toLocaleString('es-MX') : '—'}</div></div>
  </div>

  ${history.length > 0 ? `
  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">CPU % — Historial</div>
      <div class="chart-wrap"><canvas id="detail-cpu-chart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">RAM % — Historial</div>
      <div class="chart-wrap"><canvas id="detail-ram-chart"></canvas></div>
    </div>
  </div>
  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Disco % — Historial</div>
      <div class="chart-wrap"><canvas id="detail-disk-chart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Procesos — Historial</div>
      <div class="chart-wrap"><canvas id="detail-proc-chart"></canvas></div>
    </div>
  </div>` : '<p class="text-muted">Sin historial de métricas aún.</p>'}

  ${latest.open_ports && latest.open_ports.length > 0 ? `
  <div class="section-title mt-16">Puertos Abiertos Detectados</div>
  <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-family:monospace;font-size:12px;color:var(--green)">
    ${latest.open_ports.join(', ')}
  </div>` : ''}`;

  if (history.length > 0) {
    const labels = history.map(m => new Date(m.timestamp).toLocaleTimeString('es-MX', {hour:'2-digit',minute:'2-digit'}));
    const lineOpts = (color) => ({
      type: 'line',
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        elements: { point: { radius: 2 } },
        scales: {
          x: { ticks: { color: '#8b949e', font: {size: 10}, maxTicksLimit: 10 }, grid: { color: '#21262d' } },
          y: { ticks: { color: '#8b949e', font: {size: 10} }, grid: { color: '#21262d' }, min: 0 }
        }
      }
    });
    new Chart(document.getElementById('detail-cpu-chart'), {
      ...lineOpts('#58a6ff'),
      data: { labels, datasets: [{ data: history.map(m => m.cpu_percent?.toFixed(1)), borderColor: '#58a6ff', fill: true, backgroundColor: 'rgba(88,166,255,.1)', tension: .3 }] }
    });
    new Chart(document.getElementById('detail-ram-chart'), {
      ...lineOpts('#3fb950'),
      data: { labels, datasets: [{ data: history.map(m => m.ram_percent?.toFixed(1)), borderColor: '#3fb950', fill: true, backgroundColor: 'rgba(63,185,80,.1)', tension: .3 }] }
    });
    new Chart(document.getElementById('detail-disk-chart'), {
      ...lineOpts('#d29922'),
      data: { labels, datasets: [{ data: history.map(m => m.disk_percent?.toFixed(1)), borderColor: '#d29922', fill: true, backgroundColor: 'rgba(210,153,34,.1)', tension: .3 }] }
    });
    new Chart(document.getElementById('detail-proc-chart'), {
      ...lineOpts('#a371f7'),
      data: { labels, datasets: [{ data: history.map(m => m.process_count), borderColor: '#a371f7', fill: true, backgroundColor: 'rgba(163,113,247,.1)', tension: .3 }] }
    });
  }
}

// ─── INVENTORY ───────────────────────────────────────────────────────────────

async function loadInventory(silent = false) {
  const agents = await apiGet('/api/agents');
  if (!agents) return;
  const el = document.getElementById('view-inventory');

  el.innerHTML = `
  <div class="page-header">
    <div><h2>🖥 Inventario Automático</h2><p>${agents.length} equipos registrados</p></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="exportInventoryCSV()">⬇ CSV</button>
      <button class="btn btn-ghost btn-sm" onclick="loadInventory()">↻ Actualizar</button>
    </div>
  </div>
  <div class="table-container">
    <div class="table-toolbar">
      <input class="search-input" id="inv-search" placeholder="🔍 Buscar por hostname, IP, tag, OS..." oninput="filterInventory(this.value)"/>
      <select id="inv-status-filter" class="search-input" style="flex:0;min-width:130px" onchange="filterInventory(document.getElementById('inv-search').value)">
        <option value="">Todos</option>
        <option value="online">Online</option>
        <option value="offline">Offline</option>
      </select>
    </div>
    <table>
      <thead>
        <tr>
          <th>Hostname</th><th>IP / MAC</th><th>SO</th><th>CPU</th>
          <th>RAM</th><th>Disco</th><th>Tags</th><th>Estado</th><th>Visto</th><th></th>
        </tr>
      </thead>
      <tbody id="inv-tbody"></tbody>
    </table>
  </div>`;

  window._invAgents = agents;
  renderInventoryTable(agents);
}

function filterInventory(query) {
  const status = document.getElementById('inv-status-filter')?.value || '';
  const q = query.toLowerCase();
  const filtered = (window._invAgents || []).filter(a => {
    const matchQuery = !q ||
      a.hostname.toLowerCase().includes(q) ||
      a.ip_address.includes(q) ||
      (a.mac_address || '').toLowerCase().includes(q) ||
      (a.os_name || '').toLowerCase().includes(q) ||
      (a.tags || []).some(t => t.toLowerCase().includes(q));
    const matchStatus = !status || a.status === status;
    return matchQuery && matchStatus;
  });
  renderInventoryTable(filtered);
}

function renderInventoryTable(agents) {
  const tbody = document.getElementById('inv-tbody');
  if (!tbody) return;
  if (!agents.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="table-empty">Sin equipos registrados</td></tr>`;
    return;
  }
  tbody.innerHTML = agents.map(a => {
    const tags = (a.tags || []).map(t => `<span class="tag">${escHtml(t)}</span>`).join('');
    const m = a.metrics || {};
    const cpuColor = m.cpu_percent > 80 ? 'color:var(--red)' : m.cpu_percent > 60 ? 'color:var(--yellow)' : '';
    const ramColor = m.ram_percent > 80 ? 'color:var(--red)' : m.ram_percent > 60 ? 'color:var(--yellow)' : '';
    return `
    <tr>
      <td><strong>${escHtml(a.hostname)}</strong></td>
      <td class="monospace">${a.ip_address}<br><span class="text-muted">${a.mac_address || '—'}</span></td>
      <td>${a.os_name || '—'}<br><span class="text-muted" style="font-size:11px">${a.os_version || ''}</span></td>
      <td class="monospace" style="${cpuColor}">${m.cpu_percent !== undefined ? m.cpu_percent.toFixed(0)+'%' : '—'}</td>
      <td class="monospace" style="${ramColor}">${m.ram_percent !== undefined ? m.ram_percent.toFixed(0)+'%' : '—'}</td>
      <td class="monospace">${m.disk_percent !== undefined ? m.disk_percent.toFixed(0)+'%' : '—'}</td>
      <td><div class="tags-cell">${tags || '—'}</div></td>
      <td><span class="status status-${a.status}">${a.status === 'online' ? 'Online' : 'Offline'}</span></td>
      <td class="text-muted" style="font-size:11px">${a.last_seen ? timeAgo(a.last_seen) : '—'}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="loadAgentDetail(${a.id})">Ver</button>
        <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id}, ${JSON.stringify(a.tags || []).replace(/"/g,"'")})">Tags</button>
      </td>
    </tr>`;
  }).join('');
}

function exportInventoryCSV() {
  const agents = window._invAgents || [];
  const rows = [['Hostname','IP','MAC','SO','CPU%','RAM%','Disco%','Tags','Estado','Ultimo Visto']];
  agents.forEach(a => {
    const m = a.metrics || {};
    rows.push([
      a.hostname, a.ip_address, a.mac_address, `${a.os_name} ${a.os_version}`,
      m.cpu_percent?.toFixed(0) || '', m.ram_percent?.toFixed(0) || '', m.disk_percent?.toFixed(0) || '',
      (a.tags || []).join('; '), a.status, a.last_seen || ''
    ]);
  });
  downloadCSV(rows, 'inventario_infrawatch.csv');
}

// ─── ASSETS ──────────────────────────────────────────────────────────────────

async function loadAssets() {
  const assets = await apiGet('/api/assets');
  if (!assets) return;
  const el = document.getElementById('view-assets');

  el.innerHTML = `
  <div class="page-header">
    <div><h2>📦 Activos Fijos</h2><p>${assets.length} activos registrados</p></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="exportAssetsCSV()">⬇ CSV</button>
      <button class="btn btn-primary btn-sm" onclick="openAssetForm()">+ Nuevo Activo</button>
    </div>
  </div>
  <div class="table-container">
    <div class="table-toolbar">
      <input class="search-input" id="asset-search" placeholder="🔍 Buscar activo..." oninput="filterAssets(this.value)"/>
      <select id="asset-type-filter" class="search-input" style="flex:0;min-width:130px" onchange="filterAssets(document.getElementById('asset-search').value)">
        <option value="">Todos los tipos</option>
        <option value="laptop">Laptop</option>
        <option value="pc">PC</option>
        <option value="server">Servidor</option>
        <option value="switch">Switch</option>
        <option value="firewall">Firewall</option>
        <option value="printer">Impresora</option>
        <option value="other">Otro</option>
      </select>
    </div>
    <table>
      <thead>
        <tr><th>Código</th><th>Tipo</th><th>Equipo</th><th>Serie</th><th>Responsable</th><th>Ubicación</th><th>Costo</th><th>Estado</th><th>Mantenimientos</th><th></th></tr>
      </thead>
      <tbody id="assets-tbody"></tbody>
    </table>
  </div>`;

  window._assets = assets;
  renderAssetsTable(assets);
}

function filterAssets(q) {
  const type = document.getElementById('asset-type-filter')?.value || '';
  const query = q.toLowerCase();
  const filtered = (window._assets || []).filter(a =>
    (!query || a.brand?.toLowerCase().includes(query) || a.model?.toLowerCase().includes(query) || a.asset_code?.toLowerCase().includes(query) || a.responsible?.toLowerCase().includes(query) || a.location?.toLowerCase().includes(query)) &&
    (!type || a.asset_type === type)
  );
  renderAssetsTable(filtered);
}

function renderAssetsTable(assets) {
  const tbody = document.getElementById('assets-tbody');
  if (!tbody) return;
  if (!assets.length) { tbody.innerHTML = `<tr><td colspan="10" class="table-empty">Sin activos registrados</td></tr>`; return; }
  const icons = { laptop:'💻', pc:'🖥', server:'🗄', switch:'🔀', firewall:'🛡', printer:'🖨', other:'📦' };
  tbody.innerHTML = assets.map(a => `
  <tr>
    <td class="monospace">${a.asset_code}</td>
    <td>${icons[a.asset_type] || '📦'} ${a.asset_type}</td>
    <td><strong>${escHtml(a.brand)}</strong> ${escHtml(a.model)}</td>
    <td class="monospace text-muted">${a.serial_number || '—'}</td>
    <td>${escHtml(a.responsible || '—')}</td>
    <td>${escHtml(a.location || '—')}</td>
    <td>${a.purchase_cost > 0 ? '$'+a.purchase_cost.toLocaleString() : '—'}</td>
    <td><span class="status status-${a.status}">${a.status}</span></td>
    <td class="text-muted">${a.maintenance_count} registro(s)${a.last_maintenance ? '<br><span style="font-size:10px">Último: '+a.last_maintenance+'</span>' : ''}</td>
    <td>
      <button class="btn btn-ghost btn-sm" onclick="openAssetForm(${a.id})">✏</button>
      <button class="btn btn-danger btn-sm" onclick="deleteAsset(${a.id})">🗑</button>
    </td>
  </tr>`).join('');
}

async function openAssetForm(assetId = null) {
  let existing = null;
  if (assetId) {
    existing = (window._assets || []).find(a => a.id === assetId);
  }
  const v = existing || {};
  openModal(assetId ? 'Editar Activo' : 'Nuevo Activo Fijo', `
  <div class="form-row">
    <div class="form-field"><label>Tipo</label>
      <select id="f-type">
        ${['laptop','pc','server','switch','firewall','printer','other'].map(t => `<option value="${t}" ${v.asset_type===t?'selected':''}>${t}</option>`).join('')}
      </select></div>
    <div class="form-field"><label>Estado</label>
      <select id="f-status">
        ${['active','maintenance','repair','decommissioned'].map(s => `<option value="${s}" ${(v.status||'active')===s?'selected':''}>${s}</option>`).join('')}
      </select></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Marca</label><input id="f-brand" value="${v.brand||''}"/></div>
    <div class="form-field"><label>Modelo</label><input id="f-model" value="${v.model||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Número de Serie</label><input id="f-serial" value="${v.serial_number||''}"/></div>
    <div class="form-field"><label>Fecha Compra</label><input id="f-pdate" type="date" value="${v.purchase_date||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Costo ($)</label><input id="f-cost" type="number" value="${v.purchase_cost||0}"/></div>
    <div class="form-field"><label>Responsable</label><input id="f-resp" value="${v.responsible||''}"/></div>
  </div>
  <div class="form-field"><label>Ubicación</label><input id="f-loc" value="${v.location||''}"/></div>
  <div class="form-field"><label>Notas</label><textarea id="f-notes">${v.notes||''}</textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveAsset(${assetId||'null'})">Guardar</button>
  </div>`);
}

async function saveAsset(assetId) {
  const body = {
    asset_type: document.getElementById('f-type').value,
    brand:      document.getElementById('f-brand').value,
    model:      document.getElementById('f-model').value,
    serial_number: document.getElementById('f-serial').value,
    purchase_date: document.getElementById('f-pdate').value,
    purchase_cost: parseFloat(document.getElementById('f-cost').value) || 0,
    responsible: document.getElementById('f-resp').value,
    location:    document.getElementById('f-loc').value,
    status:      document.getElementById('f-status').value,
    notes:       document.getElementById('f-notes').value,
  };
  if (assetId) await apiPut(`/api/assets/${assetId}`, body);
  else await apiPost('/api/assets', body);
  closeModal(); toast('Activo guardado', 'success'); loadAssets();
}

async function deleteAsset(id) {
  if (!confirm('¿Eliminar este activo?')) return;
  await apiDelete(`/api/assets/${id}`);
  toast('Activo eliminado', 'info'); loadAssets();
}

function exportAssetsCSV() {
  const assets = window._assets || [];
  const rows = [['Código','Tipo','Marca','Modelo','Serie','Responsable','Ubicación','Costo','Estado','Último Mant.']];
  assets.forEach(a => rows.push([a.asset_code, a.asset_type, a.brand, a.model, a.serial_number, a.responsible, a.location, a.purchase_cost, a.status, a.last_maintenance||'']));
  downloadCSV(rows, 'activos_infrawatch.csv');
}

// ─── MAINTENANCE ─────────────────────────────────────────────────────────────

async function loadMaintenance() {
  const [records, assets] = await Promise.all([apiGet('/api/maintenance'), apiGet('/api/assets')]);
  if (!records) return;
  const el = document.getElementById('view-maintenance');
  const pending  = records.filter(m => m.status === 'pending').length;
  const inprog   = records.filter(m => m.status === 'in_progress').length;

  el.innerHTML = `
  <div class="page-header">
    <div><h2>🔧 Mantenimientos Preventivos</h2><p>${records.length} registros — ${pending} pendientes, ${inprog} en progreso</p></div>
    <button class="btn btn-primary btn-sm" onclick="openMaintenanceForm(${JSON.stringify(assets||[]).replace(/"/g,"'")})">+ Registrar</button>
  </div>
  <div class="table-container">
    <table>
      <thead><tr><th>Activo</th><th>Tipo</th><th>Fecha</th><th>Próximo</th><th>Técnico</th><th>Estado</th><th>Observaciones</th><th></th></tr></thead>
      <tbody>
        ${records.length ? records.map(m => `
        <tr>
          <td><strong>${m.asset_code}</strong><br><span class="text-muted">${escHtml(m.asset_name||'')}</span></td>
          <td>${m.maint_type}</td>
          <td class="monospace">${m.maintenance_date}</td>
          <td class="monospace ${m.next_date && m.next_date < todayStr() ? 'color:var(--red)' : ''}">${m.next_date||'—'}</td>
          <td>${escHtml(m.technician)}</td>
          <td><span class="status status-${m.status}">${m.status}</span></td>
          <td class="text-muted" style="max-width:200px;font-size:12px">${escHtml(m.observations||'').substring(0,80)}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteMaint(${m.id})">🗑</button></td>
        </tr>`).join('') : `<tr><td colspan="8" class="table-empty">Sin mantenimientos registrados</td></tr>`}
      </tbody>
    </table>
  </div>`;
  window._maintenanceAssets = assets || [];
}

function openMaintenanceForm(assets) {
  const assetList = typeof assets === 'string' ? JSON.parse(assets.replace(/'/g,'"')) : assets;
  openModal('Registrar Mantenimiento', `
  <div class="form-field"><label>Activo</label>
    <select id="m-asset">
      ${(assetList||[]).map(a => `<option value="${a.id}">${a.asset_code} — ${a.brand} ${a.model}</option>`).join('')}
    </select></div>
  <div class="form-row">
    <div class="form-field"><label>Fecha Mantenimiento</label><input id="m-date" type="date" value="${todayStr()}"/></div>
    <div class="form-field"><label>Próximo Mantenimiento</label><input id="m-next" type="date"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Técnico</label><input id="m-tech" placeholder="Nombre del técnico"/></div>
    <div class="form-field"><label>Tipo</label>
      <select id="m-type">
        <option value="preventive">Preventivo</option>
        <option value="corrective">Correctivo</option>
        <option value="upgrade">Upgrade</option>
      </select></div>
  </div>
  <div class="form-field"><label>Estado</label>
    <select id="m-status">
      <option value="completed">Completado</option>
      <option value="pending">Pendiente</option>
      <option value="in_progress">En Progreso</option>
    </select></div>
  <div class="form-field"><label>Observaciones</label><textarea id="m-obs" placeholder="Descripción del mantenimiento realizado..."></textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveMaintenance()">Guardar</button>
  </div>`);
}

async function saveMaintenance() {
  const body = {
    asset_id:         parseInt(document.getElementById('m-asset').value),
    maintenance_date: document.getElementById('m-date').value,
    next_date:        document.getElementById('m-next').value || null,
    technician:       document.getElementById('m-tech').value,
    maint_type:       document.getElementById('m-type').value,
    status:           document.getElementById('m-status').value,
    observations:     document.getElementById('m-obs').value,
  };
  await apiPost('/api/maintenance', body);
  closeModal(); toast('Mantenimiento guardado', 'success'); loadMaintenance();
}

async function deleteMaint(id) {
  if (!confirm('¿Eliminar este registro de mantenimiento?')) return;
  await apiDelete(`/api/maintenance/${id}`);
  toast('Eliminado', 'info'); loadMaintenance();
}

// ─── ALERTS ──────────────────────────────────────────────────────────────────

async function loadAlerts() {
  const alerts = await apiGet('/api/alerts');
  if (!alerts) return;
  const el = document.getElementById('view-alerts');
  const unack = alerts.filter(a => !a.acknowledged);

  el.innerHTML = `
  <div class="page-header">
    <div><h2>🔔 Alertas del Sistema</h2><p>${unack.length} sin reconocer</p></div>
    <button class="btn btn-ghost btn-sm" onclick="ackAllAlerts()">✓ Reconocer Todas</button>
  </div>
  <div class="alert-list">
    ${alerts.length ? alerts.map(a => `
    <div class="alert-item ${a.severity}" id="alert-${a.id}" style="${a.acknowledged ? 'opacity:.5' : ''}">
      <span class="alert-icon">${a.severity==='critical'?'🔴':a.severity==='warning'?'🟡':'🔵'}</span>
      <div class="alert-msg">
        <div>${escHtml(a.message)}</div>
        <div class="text-muted" style="font-size:11px;margin-top:2px">${a.alert_type} • ${a.severity}</div>
      </div>
      <span class="alert-time">${timeAgo(a.created_at)}</span>
      ${!a.acknowledged ? `<button class="alert-ack-btn" onclick="ackAlert(${a.id})">✓</button>` : '<span class="text-muted" style="font-size:11px">✓ ok</span>'}
    </div>`).join('') : `<div class="table-empty">🎉 Sin alertas activas</div>`}
  </div>`;
}

async function ackAlert(id) {
  await apiPut(`/api/alerts/${id}/acknowledge`, {});
  loadAlerts();
}

async function ackAllAlerts() {
  await apiPost('/api/alerts/ack-all', {});
  toast('Todas las alertas reconocidas', 'success'); loadAlerts();
}

// ─── USERS ───────────────────────────────────────────────────────────────────

async function loadUsers() {
  const users = await apiGet('/api/users');
  if (!users) return;
  const el = document.getElementById('view-users');
  el.innerHTML = `
  <div class="page-header">
    <div><h2>👤 Gestión de Usuarios</h2><p>${users.length} usuarios</p></div>
    <button class="btn btn-primary btn-sm" onclick="openUserForm()">+ Nuevo Usuario</button>
  </div>
  <div class="table-container">
    <table>
      <thead><tr><th>Usuario</th><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th>Creado</th><th></th></tr></thead>
      <tbody>
        ${users.map(u => `
        <tr>
          <td><strong>${escHtml(u.username)}</strong></td>
          <td>${escHtml(u.full_name||'')}</td>
          <td class="text-muted">${escHtml(u.email||'')}</td>
          <td><span class="role-badge">${u.role}</span></td>
          <td><span class="status ${u.is_active?'status-online':'status-offline'}">${u.is_active?'Activo':'Inactivo'}</span></td>
          <td class="text-muted">${new Date(u.created_at).toLocaleDateString('es-MX')}</td>
          <td>${u.username !== 'admin' ? `<button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id})">🗑</button>` : ''}</td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>`;
}

function openUserForm() {
  openModal('Nuevo Usuario', `
  <div class="form-row">
    <div class="form-field"><label>Usuario</label><input id="u-user" placeholder="username"/></div>
    <div class="form-field"><label>Contraseña</label><input id="u-pass" type="password" placeholder="••••••••"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Nombre Completo</label><input id="u-name"/></div>
    <div class="form-field"><label>Email</label><input id="u-email" type="email"/></div>
  </div>
  <div class="form-field"><label>Rol</label>
    <select id="u-role">
      <option value="viewer">Viewer (solo lectura)</option>
      <option value="technician">Técnico</option>
      <option value="auditor">Auditor</option>
      <option value="admin">Administrador</option>
    </select></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveUser()">Crear</button>
  </div>`);
}

async function saveUser() {
  const body = {
    username:  document.getElementById('u-user').value,
    password:  document.getElementById('u-pass').value,
    full_name: document.getElementById('u-name').value,
    email:     document.getElementById('u-email').value,
    role:      document.getElementById('u-role').value,
  };
  const res = await apiPost('/api/users', body);
  if (res) { closeModal(); toast('Usuario creado', 'success'); loadUsers(); }
}

async function deleteUser(id) {
  if (!confirm('¿Eliminar este usuario?')) return;
  await apiDelete(`/api/users/${id}`);
  toast('Usuario eliminado', 'info'); loadUsers();
}

// ─── TAG EDITOR ──────────────────────────────────────────────────────────────

function openTagEditor(agentId, tagsRaw) {
  const tags = typeof tagsRaw === 'string' ? JSON.parse(tagsRaw.replace(/'/g,'"')) : tagsRaw;
  let currentTags = [...tags];

  const renderTags = () => {
    document.getElementById('tag-list').innerHTML = currentTags.map((t, i) => `
      <span class="tag">${escHtml(t)} <button class="tag-remove" onclick="removeTag(${i})">×</button></span>`).join('');
  };

  openModal('Editar Tags', `
  <p class="text-muted mb-16">Agrega tags para clasificar este equipo (ej: FINANZAS, LAPTOP, CRITICO)</p>
  <div class="tag-input-row">
    <input class="tag-input" id="new-tag" placeholder="Nuevo tag (ENTER para agregar)" 
           onkeydown="if(event.key==='Enter'){addTag();event.preventDefault()}"/>
    <button class="btn btn-primary btn-sm" onclick="addTag()">Agregar</button>
  </div>
  <div id="tag-list" style="display:flex;flex-wrap:wrap;gap:4px;min-height:36px;margin-bottom:16px"></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveTags(${agentId})">Guardar</button>
  </div>`);

  window._editTags = currentTags;
  renderTags();

  window.addTag = () => {
    const inp = document.getElementById('new-tag');
    const v = inp.value.trim().toUpperCase();
    if (v && !window._editTags.includes(v)) { window._editTags.push(v); inp.value = ''; renderTags(); }
  };
  window.removeTag = (i) => { window._editTags.splice(i, 1); renderTags(); };
}

async function saveTags(agentId) {
  await apiPut(`/api/agents/${agentId}/tags`, {tags: window._editTags});
  closeModal(); toast('Tags guardados', 'success');
  loadInventory();
}

async function deleteAgent(id) {
  if (!confirm('¿Eliminar este agente del sistema?')) return;
  await apiDelete(`/api/agents/${id}`);
  toast('Agente eliminado', 'info'); showView('inventory');
}

// ─── MODAL ───────────────────────────────────────────────────────────────────

function openModal(title, body) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = body;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

// ─── TOAST ───────────────────────────────────────────────────────────────────

function toast(msg, type = 'info') {
  const icons = { success:'✅', error:'❌', info:'ℹ️' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type]||''}</span> ${msg}`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ─── UTILS ───────────────────────────────────────────────────────────────────

function timeAgo(isoStr) {
  const diff = Date.now() - new Date(isoStr+'Z').getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h/24)}d`;
}

function todayStr() {
  return new Date().toISOString().split('T')[0];
}

function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function downloadCSV(rows, filename) {
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob(['\uFEFF' + csv], {type: 'text/csv;charset=utf-8;'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
