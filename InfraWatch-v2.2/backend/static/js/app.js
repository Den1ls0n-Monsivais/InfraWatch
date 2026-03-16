/* InfraWatch v2.1 — Frontend SPA */
const API = '';
let token = localStorage.getItem('iw_token');
let currentUser = null, refreshTimer = null;
let charts = {};

// ─── AUTH ────────────────────────────────────────────────────────────────────
async function doLogin() {
  const u = document.getElementById('l-user').value;
  const p = document.getElementById('l-pass').value;
  const err = document.getElementById('login-err');
  err.textContent = '';
  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username:u, password:p})
    });
    if (!res.ok) { err.textContent = 'Credenciales incorrectas'; return; }
    const data = await res.json();
    token = data.token; localStorage.setItem('iw_token', token);
    currentUser = data; showApp();
  } catch(e) { err.textContent = 'Error de conexión'; }
}

function doLogout() {
  token = null; currentUser = null;
  localStorage.removeItem('iw_token');
  if (refreshTimer) clearInterval(refreshTimer);
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
}

async function apiFetch(url, opts={}) {
  const res = await fetch(`${API}${url}`, {
    ...opts, headers:{'Content-Type':'application/json',
      'Authorization':`Bearer ${token}`, ...(opts.headers||{})}
  });
  if (res.status === 401) { doLogout(); return null; }
  return res;
}
async function apiGet(u)       { const r=await apiFetch(u); return r?r.json():null; }
async function apiPost(u,b)    { const r=await apiFetch(u,{method:'POST',body:JSON.stringify(b)}); return r?r.json():null; }
async function apiPut(u,b)     { const r=await apiFetch(u,{method:'PUT',body:JSON.stringify(b)}); return r?r.json():null; }
async function apiDelete(u)    { const r=await apiFetch(u,{method:'DELETE'}); return r?r.json():null; }
async function apiUpload(u,fd) {
  const r = await fetch(`${API}${u}`, {method:'POST', headers:{'Authorization':`Bearer ${token}`}, body:fd});
  return r?r.json():null;
}

// ─── INIT ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  if (token) {
    try {
      const r = await apiFetch('/api/auth/me');
      if (r && r.ok) { currentUser = await r.json(); showApp(); return; }
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
    document.getElementById('nav-users-li').style.display = '';
    document.getElementById('nav-config-li').style.display = '';
  }
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      document.querySelectorAll('.nav-link').forEach(l=>l.classList.remove('active'));
      link.classList.add('active');
      showView(link.dataset.view);
    });
  });
  showView('dashboard');
  startAutoRefresh();
}

function showView(view) {
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  const el = document.getElementById(`view-${view}`);
  if (el) el.classList.add('active');
  loadView(view);
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    const alerts = await apiGet('/api/alerts');
    if (alerts) {
      const unack = alerts.filter(a=>!a.acknowledged).length;
      document.getElementById('alert-badge').textContent = unack>0?unack:'';
    }
    const dash = await apiGet('/api/dashboard');
    if (dash) {
      const pm = dash.maintenance.upcoming_30d + dash.maintenance.overdue;
      const badge = document.getElementById('badge-maint');
      if (badge) { badge.textContent = pm>0?pm:''; badge.style.display=pm>0?'':'none'; }
      const pa = dash.assets.pending_assign;
      const badgeA = document.getElementById('badge-pending');
      if (badgeA) { badgeA.textContent = pa>0?pa:''; badgeA.style.display=pa>0?'':'none'; }
    }
    const av = document.querySelector('.view.active');
    if (av?.id === 'view-dashboard') loadDashboard(true);
    if (av?.id === 'view-inventory') loadInventory(true);
  }, 20000);
}

function loadView(v) {
  ({dashboard:loadDashboard, inventory:loadInventory, assets:loadAssets,
    personnel:loadPersonnel, maintenance:loadMaintenance, alerts:loadAlerts,
    users:loadUsers, config:loadConfig})[v]?.();
}

// ─── DASHBOARD ───────────────────────────────────────────────────────────────
async function loadDashboard(silent=false) {
  const [dash, agents] = await Promise.all([apiGet('/api/dashboard'), apiGet('/api/agents')]);
  if (!dash || !agents) return;
  const el = document.getElementById('view-dashboard');

  el.innerHTML = `
  <div class="page-header">
    <div><h2>📊 Panel de Control</h2>
      <p>InfraWatch v2.1 — ${new Date().toLocaleString('es-MX')}</p></div>
    <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Actualizar</button>
  </div>

  <div class="stat-grid">
    <div class="stat-card"><div class="stat-icon">🖥</div>
      <div class="stat-label">Hosts</div><div class="stat-value">${dash.agents.total}</div>
      <div class="stat-sub">registrados</div></div>
    <div class="stat-card green"><div class="stat-icon">✅</div>
      <div class="stat-label">Online</div>
      <div class="stat-value" style="color:var(--green)">${dash.agents.online}</div>
      <div class="stat-sub">activos ahora</div></div>
    <div class="stat-card red"><div class="stat-icon">❌</div>
      <div class="stat-label">Offline</div>
      <div class="stat-value" style="color:var(--red)">${dash.agents.offline}</div>
      <div class="stat-sub">sin respuesta</div></div>
    <div class="stat-card purple"><div class="stat-icon">👥</div>
      <div class="stat-label">Personal</div>
      <div class="stat-value" style="color:var(--purple)">${dash.personnel.total}</div>
      <div class="stat-sub">empleados</div></div>
    <div class="stat-card yellow"><div class="stat-icon">⚠</div>
      <div class="stat-label">Sin Responsable</div>
      <div class="stat-value" style="color:var(--yellow)">${dash.assets.pending_assign}</div>
      <div class="stat-sub">activos sin asignar</div></div>
    <div class="stat-card ${dash.maintenance.overdue>0?'red':'yellow'}"><div class="stat-icon">🔧</div>
      <div class="stat-label">Mantenimientos</div>
      <div class="stat-value" style="color:${dash.maintenance.overdue>0?'var(--red)':'var(--yellow)'}">
        ${dash.maintenance.overdue>0?dash.maintenance.overdue:dash.maintenance.upcoming_30d}</div>
      <div class="stat-sub">${dash.maintenance.overdue>0?'VENCIDOS':'próximos 30 días'}</div></div>
  </div>

  <!-- Avg metrics -->
  <div class="chart-card mb-24">
    <div class="chart-title">Promedio Uso — Hosts Online</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:8px 0">
      ${[['CPU',dash.avg_metrics.cpu],['RAM',dash.avg_metrics.ram],['Disco',dash.avg_metrics.disk]].map(([lbl,val])=>{
        const c=val>80?'var(--red)':val>60?'var(--yellow)':'var(--green)';
        return `<div>
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">
            <span class="text-muted">${lbl}</span><span style="font-weight:700;color:${c}">${val}%</span></div>
          <div style="background:var(--bg3);height:8px;border-radius:4px;overflow:hidden">
            <div style="width:${val}%;height:100%;background:${c};border-radius:4px;transition:width .5s"></div></div>
        </div>`;
      }).join('')}
    </div>
  </div>

  ${dash.maintenance.upcoming_list?.length>0?`
  <div class="warn-box mb-24">
    <div style="font-weight:700;margin-bottom:10px;font-size:14px">
      🔧 Mantenimientos Próximos / Vencidos
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr>
        <th style="text-align:left;padding:6px;border-bottom:1px solid var(--border);color:var(--text2)">Activo</th>
        <th style="text-align:left;padding:6px;border-bottom:1px solid var(--border);color:var(--text2)">Responsable</th>
        <th style="text-align:left;padding:6px;border-bottom:1px solid var(--border);color:var(--text2)">Fecha</th>
        <th style="text-align:left;padding:6px;border-bottom:1px solid var(--border);color:var(--text2)">Días</th>
      </tr></thead>
      <tbody>
        ${dash.maintenance.upcoming_list.map(m=>`<tr>
          <td style="padding:6px"><strong>${m.asset_code}</strong> ${m.asset_name}</td>
          <td style="padding:6px;color:var(--text2)">${m.responsible}</td>
          <td style="padding:6px;font-family:monospace">${m.next_date}</td>
          <td style="padding:6px"><span style="color:${m.days_left<0?'var(--red)':m.days_left<7?'var(--orange)':'var(--yellow)'}">
            ${m.days_left<0?`⚠ Vencido (${Math.abs(m.days_left)}d)`:m.days_left===0?'¡HOY!':m.days_left+' días'}</span></td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>`:''} 

  <div class="chart-grid">
    <div class="chart-card"><div class="chart-title">Sistemas Operativos</div>
      <div class="chart-wrap"><canvas id="ch-os"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Tipos de Activos</div>
      <div class="chart-wrap"><canvas id="ch-type"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">CPU % — Top Hosts</div>
      <div class="chart-wrap"><canvas id="ch-cpu"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">RAM % — Top Hosts</div>
      <div class="chart-wrap"><canvas id="ch-ram"></canvas></div></div>
  </div>

  <div class="section-title">Vista NOC</div>
  <div class="noc-grid">${agents.map(renderNocCard).join('')}</div>`;

  // Charts
  const C = ['#58a6ff','#3fb950','#d29922','#f85149','#a371f7','#e3b341','#f778ba'];
  const pie = (labels,data) => ({
    type:'doughnut', data:{labels, datasets:[{data,backgroundColor:C,borderWidth:0}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'60%',
      plugins:{legend:{position:'right',labels:{color:'#8b949e',font:{size:11}}}}}
  });
  const bar = (labels,data,colors) => ({
    type:'bar', data:{labels, datasets:[{data,backgroundColor:colors,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#8b949e',font:{size:10}},grid:{color:'#21262d'}},
              y:{ticks:{color:'#8b949e',font:{size:10}},grid:{color:'#21262d'},min:0,max:100}}}
  });

  const destroyDraw = (id, cfg) => {
    if (charts[id]) charts[id].destroy();
    const c = document.getElementById(id);
    if (c) charts[id] = new Chart(c, cfg);
  };

  const osK = Object.keys(dash.os_distribution);
  destroyDraw('ch-os', pie(osK, osK.map(k=>dash.os_distribution[k])));
  const atK = Object.keys(dash.asset_distribution);
  destroyDraw('ch-type', pie(atK, atK.map(k=>dash.asset_distribution[k])));

  const online = agents.filter(a=>a.status==='online'&&a.metrics).slice(0,10);
  const lbls  = online.map(a=>a.hostname.split('.')[0]);
  const cpus  = online.map(a=>a.metrics.cpu_percent?.toFixed(1)||0);
  const rams  = online.map(a=>a.metrics.ram_percent?.toFixed(1)||0);
  destroyDraw('ch-cpu', bar(lbls, cpus, cpus.map(v=>v>80?'#f85149':v>60?'#d29922':'#58a6ff')));
  destroyDraw('ch-ram', bar(lbls, rams, rams.map(v=>v>80?'#f85149':v>60?'#d29922':'#3fb950')));
}

function renderNocCard(a) {
  const m=a.metrics||{};
  const tags=(a.tags||[]).map(t=>`<span class="tag">${escHtml(t)}</span>`).join('');
  const cpuC=m.cpu_percent>80?'bar-high':m.cpu_percent>60?'bar-mid':'bar-low';
  const ramC=m.ram_percent>80?'bar-high':m.ram_percent>60?'bar-mid':'bar-low';
  const dskC=m.disk_percent>80?'bar-high':m.disk_percent>60?'bar-mid':'bar-low';
  return `
  <div class="noc-card${a.status==='offline'?' offline':''}" onclick="loadAgentDetail(${a.id})">
    <div class="noc-card-header">
      <div>
        <div class="noc-hostname">${escHtml(a.hostname)}</div>
        <div class="noc-ip">${a.ip_address}</div>
        ${a.asset_code?`<span class="noc-asset-code">📦 ${a.asset_code}</span>`:''}
      </div>
      <span class="status status-${a.status}">${a.status==='online'?'Online':'Offline'}</span>
    </div>
    ${a.status==='online'&&m.cpu_percent!==undefined?`
    <div class="noc-metrics">
      <div class="noc-metric-row"><span class="noc-metric-label">CPU</span>
        <div class="bar"><div class="bar-fill ${cpuC}" style="width:${m.cpu_percent}%"></div></div>
        <span class="bar-value">${m.cpu_percent?.toFixed(0)}%</span></div>
      <div class="noc-metric-row"><span class="noc-metric-label">RAM</span>
        <div class="bar"><div class="bar-fill ${ramC}" style="width:${m.ram_percent}%"></div></div>
        <span class="bar-value">${m.ram_percent?.toFixed(0)}%</span></div>
      <div class="noc-metric-row"><span class="noc-metric-label">DSK</span>
        <div class="bar"><div class="bar-fill ${dskC}" style="width:${m.disk_percent}%"></div></div>
        <span class="bar-value">${m.disk_percent?.toFixed(0)}%</span></div>
    </div>`:
    `<p class="text-muted" style="font-size:11px;margin-top:8px">Último: ${timeAgo(a.last_seen)}</p>`}
    ${a.personnel?`<div class="noc-person">👤 <strong>${escHtml(a.personnel.full_name)}</strong></div>`:
      `<div class="noc-person" style="color:var(--yellow)">⚠ Sin responsable</div>`}
    <div class="noc-tags">${tags}</div>
  </div>`;
}

// ─── INVENTORY ───────────────────────────────────────────────────────────────
async function loadInventory(silent=false) {
  const agents = await apiGet('/api/agents');
  if (!agents) return;
  const el = document.getElementById('view-inventory');
  el.innerHTML = `
  <div class="page-header">
    <div><h2>🖥 Inventario</h2><p>${agents.length} equipos</p></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="exportInventoryCSV()">⬇ CSV</button>
      <button class="btn btn-ghost btn-sm" onclick="loadInventory()">↻</button>
    </div>
  </div>
  <div class="table-container">
    <div class="table-toolbar">
      <input class="search-input" id="inv-q" placeholder="🔍 Hostname, IP, OS, responsable..." oninput="filterInventory(this.value)"/>
      <select class="search-input" id="inv-st" style="flex:0;min-width:120px" onchange="filterInventory(document.getElementById('inv-q').value)">
        <option value="">Todos</option><option value="online">Online</option><option value="offline">Offline</option>
      </select>
    </div>
    <table>
      <thead><tr><th>Hostname</th><th>IP / MAC</th><th>OS</th><th>CPU / RAM</th><th>Responsable</th><th>Tags</th><th>Estado</th><th>Visto</th><th></th></tr></thead>
      <tbody id="inv-tbody"></tbody>
    </table>
  </div>`;
  window._invAgents = agents;
  renderInventoryTable(agents);
}

function filterInventory(q) {
  const st = document.getElementById('inv-st')?.value||'';
  const f  = (window._invAgents||[]).filter(a=>
    (!q || a.hostname.toLowerCase().includes(q.toLowerCase()) || a.ip_address.includes(q) ||
     (a.os_name||'').toLowerCase().includes(q.toLowerCase()) ||
     (a.tags||[]).some(t=>t.toLowerCase().includes(q.toLowerCase())) ||
     (a.personnel?.full_name||'').toLowerCase().includes(q.toLowerCase())) &&
    (!st || a.status===st)
  );
  renderInventoryTable(f);
}

function renderInventoryTable(agents) {
  const tbody = document.getElementById('inv-tbody');
  if (!tbody) return;
  if (!agents.length) { tbody.innerHTML=`<tr><td colspan="9" class="table-empty">Sin equipos</td></tr>`; return; }
  tbody.innerHTML = agents.map(a=>{
    const m=a.metrics||{};
    const tags=(a.tags||[]).map(t=>`<span class="tag">${escHtml(t)}</span>`).join('');
    const cC=m.cpu_percent>80?'color:var(--red)':m.cpu_percent>60?'color:var(--yellow)':'';
    const rC=m.ram_percent>80?'color:var(--red)':m.ram_percent>60?'color:var(--yellow)':'';
    return `<tr>
      <td><strong>${escHtml(a.hostname)}</strong>${a.asset_code?`<br><span class="noc-asset-code">📦 ${a.asset_code}</span>`:''}</td>
      <td class="monospace">${a.ip_address}<br><span class="text-muted">${a.mac_address||'—'}</span></td>
      <td>${a.os_name||'—'} <span class="text-muted" style="font-size:10px">${a.os_version||''}</span></td>
      <td class="monospace"><span style="${cC}">CPU: ${m.cpu_percent!==undefined?m.cpu_percent.toFixed(0)+'%':'—'}</span><br>
        <span style="${rC}">RAM: ${m.ram_percent!==undefined?m.ram_percent.toFixed(0)+'%':'—'}</span></td>
      <td>${a.personnel?`👤 ${escHtml(a.personnel.full_name)}<br><span class="text-muted" style="font-size:10px">${a.personnel.department}</span>`:
          `<span style="color:var(--yellow);font-size:11px">⚠ Sin asignar</span>`}</td>
      <td><div class="tags-cell">${tags||'—'}</div></td>
      <td><span class="status status-${a.status}">${a.status==='online'?'Online':'Offline'}</span></td>
      <td class="text-muted" style="font-size:11px">${a.last_seen?timeAgo(a.last_seen):'—'}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-ghost btn-sm" onclick="loadAgentDetail(${a.id})">Ver</button>
        <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id},'${JSON.stringify(a.tags||[]).replace(/'/g,"\\'").replace(/"/g,'\\"')}')">Tags</button>
      </td>
    </tr>`;
  }).join('');
}

function exportInventoryCSV() {
  const rows=[['Hostname','IP','MAC','OS','CPU%','RAM%','Responsable','Departamento','Tags','Estado']];
  (window._invAgents||[]).forEach(a=>{
    const m=a.metrics||{};
    rows.push([a.hostname,a.ip_address,a.mac_address,`${a.os_name} ${a.os_version}`,
      m.cpu_percent?.toFixed(0)||'',m.ram_percent?.toFixed(0)||'',
      a.personnel?.full_name||'',a.personnel?.department||'',(a.tags||[]).join(';'),a.status]);
  });
  downloadCSV(rows,'inventario.csv');
}

// ─── AGENT DETAIL ────────────────────────────────────────────────────────────
async function loadAgentDetail(agentId) {
  document.querySelectorAll('.nav-link').forEach(l=>l.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-agent-detail').classList.add('active');
  const el = document.getElementById('view-agent-detail');
  el.innerHTML='<div class="text-muted">Cargando...</div>';
  const [a, personnel] = await Promise.all([apiGet(`/api/agents/${agentId}`), apiGet('/api/personnel')]);
  if (!a) return;
  const asset = a.asset;
  const nm    = a.next_maintenance;
  const daysLeft = nm?.days_left;
  const maintColor = daysLeft===undefined?'':daysLeft<0?'var(--red)':daysLeft<=7?'var(--orange)':daysLeft<=30?'var(--yellow)':'var(--green)';

  el.innerHTML = `
  <div class="detail-header">
    <button class="detail-back" onclick="showView('inventory')">← Inventario</button>
    <div>
      <h2 style="font-size:20px">${escHtml(a.hostname)}</h2>
      <span class="status status-${a.status}">${a.status}</span>
      ${asset?.auto_created?'<span class="auto-badge" style="margin-left:8px">AUTO</span>':''}
    </div>
    <div style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id},'${JSON.stringify(a.tags||[]).replace(/'/g,"\\'").replace(/"/g,'\\"')}')">🏷 Tags</button>
      ${asset?`<button class="btn btn-primary btn-sm" onclick="openAssignModal(${asset.id})">👤 ${asset.personnel_id?'Cambiar':'Asignar'}</button>`:''}
      ${asset&&asset.personnel_id?`<button class="btn btn-danger btn-sm" onclick="openBajaModal(${asset.id})">🔴 Dar de Baja</button>`:''}
      ${asset?`<button class="btn btn-ghost btn-sm" onclick="window.open('/api/assets/${asset.id}/carta/alta','_blank')">📄 Carta Alta</button>`:''}
      <button class="btn btn-danger btn-sm" onclick="deleteAgent(${a.id})">🗑</button>
    </div>
  </div>

  <div class="detail-info-grid">
    <div class="info-card"><div class="info-card-label">IP</div><div class="info-card-value">${a.ip_address}</div></div>
    <div class="info-card"><div class="info-card-label">MAC</div><div class="info-card-value">${a.mac_address}</div></div>
    <div class="info-card"><div class="info-card-label">OS</div><div class="info-card-value" style="font-size:12px">${a.os_name} ${a.os_version}</div></div>
    <div class="info-card"><div class="info-card-label">CPU</div><div class="info-card-value" style="font-size:11px">${a.cpu_model} (${a.cpu_cores} cores)</div></div>
    <div class="info-card"><div class="info-card-label">RAM</div><div class="info-card-value">${a.ram_total_gb?.toFixed(1)} GB</div></div>
    <div class="info-card"><div class="info-card-label">Disco</div><div class="info-card-value">${a.disk_total_gb?.toFixed(1)} GB</div></div>
    ${asset?`<div class="info-card"><div class="info-card-label">Activo</div><div class="info-card-value">${asset.asset_code}</div></div>`:''}
    <div class="info-card"><div class="info-card-label">Responsable</div>
      <div class="info-card-value" style="font-size:12px;color:${asset?.personnel_name?'var(--green)':'var(--yellow)'}">
        ${asset?.personnel_name||'Sin asignar'}</div></div>
    ${nm?`<div class="info-card"><div class="info-card-label">Próx. Mantenimiento</div>
      <div class="info-card-value" style="font-size:12px;color:${maintColor}">
        ${nm.next_date} (${daysLeft<0?`⚠ Vencido ${Math.abs(daysLeft)}d`:daysLeft+'d'})</div></div>`:''}
  </div>

  ${asset&&!asset.personnel_id?`<div class="warn-box">⚠ Sin responsable. <button class="btn btn-warning btn-sm" onclick="openAssignModal(${asset.id})">Asignar ahora</button></div>`:''}
  ${asset&&asset.personnel_id?`
  <div class="highlight-box" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
    <div>✅ Responsable: <strong>${a.asset?.personnel_name}</strong>
      ${asset.carta_alta_uploaded?'<span style="color:var(--green);font-size:11px;margin-left:8px">📎 Carta alta subida</span>':''}
      ${asset.carta_baja_uploaded?'<span style="color:var(--red);font-size:11px;margin-left:8px">📎 Carta baja subida</span>':''}
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-primary btn-sm" onclick="window.open('/api/assets/${asset.id}/carta/alta','_blank')">📄 Carta Alta</button>
      <button class="btn btn-ghost btn-sm" onclick="openUploadCarta(${asset.id},'alta')">⬆ Subir Firmada</button>
    </div>
  </div>`:''} 

  ${a.metrics_history?.length>0?`
  <div class="chart-grid" style="margin-top:16px">
    <div class="chart-card"><div class="chart-title">CPU %</div><div class="chart-wrap"><canvas id="d-cpu"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">RAM %</div><div class="chart-wrap"><canvas id="d-ram"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Disco %</div><div class="chart-wrap"><canvas id="d-disk"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Procesos</div><div class="chart-wrap"><canvas id="d-proc"></canvas></div></div>
  </div>`:''} 

  ${a.metrics_history?.[a.metrics_history.length-1]?.open_ports?.length?`
  <div class="section-title mt-16">Puertos Abiertos</div>
  <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-family:monospace;font-size:12px;display:flex;flex-wrap:wrap;gap:4px">
    ${a.metrics_history[a.metrics_history.length-1].open_ports.map(p=>`<span style="background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.2);border-radius:4px;padding:2px 8px;color:var(--green)">${p}</span>`).join('')}
  </div>`:''} `;

  window._detailPersonnel = personnel||[];

  if (a.metrics_history?.length) {
    const h = a.metrics_history;
    const labels = h.map(m=>new Date(m.timestamp).toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'}));
    const mkLine = (id,data,color,fill) => {
      const c = document.getElementById(id);
      if (!c) return;
      new Chart(c, {type:'line', data:{labels,datasets:[{data,borderColor:color,fill:true,backgroundColor:fill,tension:.3}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
          elements:{point:{radius:2}},
          scales:{x:{ticks:{color:'#8b949e',font:{size:10},maxTicksLimit:8},grid:{color:'#21262d'}},
                  y:{ticks:{color:'#8b949e',font:{size:10}},grid:{color:'#21262d'},min:0}}}});
    };
    mkLine('d-cpu',h.map(m=>m.cpu_percent?.toFixed(1)),'#58a6ff','rgba(88,166,255,.1)');
    mkLine('d-ram',h.map(m=>m.ram_percent?.toFixed(1)),'#3fb950','rgba(63,185,80,.1)');
    mkLine('d-disk',h.map(m=>m.disk_percent?.toFixed(1)),'#d29922','rgba(210,153,34,.1)');
    mkLine('d-proc',h.map(m=>m.process_count),'#a371f7','rgba(163,113,247,.1)');
  }
}

function openUploadCarta(assetId, tipo) {
  openModal(`⬆ Subir Carta ${tipo==='alta'?'de Alta':'de Baja'} Firmada`, `
  <p class="text-muted mb-16">Sube el PDF o imagen de la carta ${tipo} firmada para guardarla en el expediente.</p>
  <div class="form-field">
    <label>Seleccionar archivo (PDF, JPG, PNG)</label>
    <input type="file" id="carta-file" accept=".pdf,.jpg,.jpeg,.png"
      style="width:100%;background:var(--bg3);border:1px solid var(--border2);color:var(--text);padding:8px;border-radius:var(--radius)"/>
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="doUploadCarta(${assetId},'${tipo}')">⬆ Subir</button>
  </div>`);
}

async function doUploadCarta(assetId, tipo) {
  const file = document.getElementById('carta-file')?.files?.[0];
  if (!file) { toast('Selecciona un archivo','warning'); return; }
  const fd = new FormData();
  fd.append('file', file);
  const res = await apiUpload(`/api/assets/${assetId}/upload/${tipo}`, fd);
  if (res?.uploaded) { closeModal(); toast('Carta subida correctamente','success'); }
  else toast('Error al subir carta','error');
}

async function openAssignModal(assetId) {
  const people = window._detailPersonnel || await apiGet('/api/personnel') || [];
  const active = people.filter(p=>p.is_active);
  if (!active.length) { toast('Registra personal primero','warning'); showView('personnel'); return; }
  openModal('👤 Asignar Responsable', `
  <div class="form-field"><label>Empleado Responsable *</label>
    <select id="as-person" style="width:100%;background:var(--bg3);border:1px solid var(--border2);color:var(--text);padding:10px;border-radius:var(--radius)">
      <option value="">— Selecciona —</option>
      ${active.map(p=>`<option value="${p.id}">${p.full_name} | ${p.employee_id} | ${p.department}</option>`).join('')}
    </select></div>
  <div class="form-field"><label>Notas (opcional)</label>
    <textarea id="as-notes" placeholder="Motivo de asignación, condición del equipo..."></textarea></div>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:12px">
    <input type="checkbox" id="as-email" checked style="width:16px;height:16px;accent-color:var(--accent)">
    📧 Enviar correo con carta de alta al responsable
  </label>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="doAssign(${assetId})">✅ Asignar y Generar Carta</button>
  </div>`);
}

async function doAssign(assetId) {
  const pid = document.getElementById('as-person').value;
  if (!pid) { toast('Selecciona un empleado','warning'); return; }
  const res = await apiPost(`/api/assets/${assetId}/assign`, {
    personnel_id: parseInt(pid),
    send_email:   document.getElementById('as-email').checked,
    notes:        document.getElementById('as-notes').value,
  });
  if (res?.assigned) {
    closeModal();
    toast(`✅ Asignado a ${res.personnel}${document.getElementById('as-email')?.checked?' — Correo enviado':''}`, 'success');
    setTimeout(()=>{ window.location.reload(); }, 1500);
  }
}

async function openBajaModal(assetId) {
  openModal('🔴 Dar de Baja el Equipo', `
  <div class="warn-box" style="margin-bottom:14px">
    ⚠ Al dar de baja se desvincula el responsable y se genera la carta de baja.
  </div>
  <div class="form-field"><label>Motivo / Observaciones</label>
    <textarea id="baja-notes" placeholder="Motivo de la baja (término de contrato, reasignación, etc.)..."></textarea></div>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:12px">
    <input type="checkbox" id="baja-email" checked style="width:16px;height:16px;accent-color:var(--red)">
    📧 Enviar correo con carta de baja al empleado
  </label>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="doBaja(${assetId})">🔴 Confirmar Baja</button>
  </div>`);
}

async function doBaja(assetId) {
  const res = await apiPost(`/api/assets/${assetId}/baja`, {
    notes:      document.getElementById('baja-notes').value,
    send_email: document.getElementById('baja-email').checked,
  });
  if (res?.baja) {
    closeModal();
    toast('Baja registrada — Carta generada','info');
    setTimeout(()=>{ window.location.reload(); }, 1500);
  }
}

async function deleteAgent(id) {
  if (!confirm('¿Eliminar agente?')) return;
  await apiDelete(`/api/agents/${id}`);
  toast('Eliminado','info'); showView('inventory');
}

// ─── ASSETS ──────────────────────────────────────────────────────────────────
async function loadAssets() {
  const [assets, personnel] = await Promise.all([apiGet('/api/assets'), apiGet('/api/personnel')]);
  if (!assets) return;
  const el = document.getElementById('view-assets');
  const pending = assets.filter(a=>!a.personnel_id).length;

  el.innerHTML = `
  <div class="page-header">
    <div><h2>📦 Activos Fijos</h2>
      <p>${assets.length} activos — <span style="color:var(--yellow)">${pending} sin responsable</span></p></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="exportAssetsCSV()">⬇ CSV</button>
      <button class="btn btn-primary btn-sm" onclick="openAssetForm(null)">+ Nuevo Activo</button>
    </div>
  </div>
  <div class="table-container">
    <div class="table-toolbar">
      <input class="search-input" id="ast-q" placeholder="🔍 Código, marca, responsable..." oninput="filterAssets(this.value)"/>
      <select class="search-input" id="ast-type" style="flex:0;min-width:120px" onchange="filterAssets(document.getElementById('ast-q').value)">
        <option value="">Todos</option>
        ${['laptop','pc','server','switch','firewall','printer','other'].map(t=>`<option value="${t}">${t}</option>`).join('')}
      </select>
      <select class="search-input" id="ast-assign" style="flex:0;min-width:140px" onchange="filterAssets(document.getElementById('ast-q').value)">
        <option value="">Todos</option>
        <option value="assigned">Con responsable</option>
        <option value="unassigned">Sin responsable</option>
      </select>
    </div>
    <table>
      <thead><tr><th>Código</th><th>Tipo</th><th>Equipo / Host</th><th>Responsable</th>
        <th>Próx. Mant.</th><th>Estado</th><th>Cartas</th><th></th></tr></thead>
      <tbody id="ast-tbody"></tbody>
    </table>
  </div>`;
  window._assets = assets;
  window._personnel = personnel||[];
  renderAssetsTable(assets);
}

const AICONS = {laptop:'💻',pc:'🖥',server:'🗄',switch:'🔀',firewall:'🛡',printer:'🖨',other:'📦'};

function filterAssets(q) {
  const type  = document.getElementById('ast-type')?.value||'';
  const asgn  = document.getElementById('ast-assign')?.value||'';
  const query = q.toLowerCase();
  renderAssetsTable((window._assets||[]).filter(a=>
    (!query || a.asset_code?.toLowerCase().includes(query) || a.brand?.toLowerCase().includes(query) ||
     a.model?.toLowerCase().includes(query) || a.personnel?.full_name?.toLowerCase().includes(query) ||
     a.agent?.hostname?.toLowerCase().includes(query)) &&
    (!type || a.asset_type===type) &&
    (asgn===''||(asgn==='assigned'&&a.personnel_id)||(asgn==='unassigned'&&!a.personnel_id))
  ));
}

function renderAssetsTable(assets) {
  const tbody = document.getElementById('ast-tbody');
  if (!tbody) return;
  if (!assets.length) { tbody.innerHTML=`<tr><td colspan="8" class="table-empty">Sin activos</td></tr>`; return; }
  tbody.innerHTML = assets.map(a=>{
    const nm = a.next_maintenance;
    let maintHtml = '—';
    if (nm) {
      const today = new Date().toISOString().split('T')[0];
      const days  = Math.round((new Date(nm)-new Date(today))/(1000*60*60*24));
      const color = days<0?'var(--red)':days<=7?'var(--orange)':days<=30?'var(--yellow)':'var(--text2)';
      maintHtml = `<span style="color:${color};font-size:11px">${nm}<br>${days<0?`⚠ ${Math.abs(days)}d vencido`:days+' días'}</span>`;
    }
    return `<tr>
      <td class="monospace"><strong>${a.asset_code}</strong>${a.auto_created?'<br><span class="auto-badge">AUTO</span>':''}</td>
      <td>${AICONS[a.asset_type]||'📦'} ${a.asset_type}</td>
      <td>${a.brand?`<strong>${escHtml(a.brand)}</strong> ${escHtml(a.model)}`:
          a.agent?escHtml(a.agent.hostname):'—'}<br>
        <span class="text-muted" style="font-size:10px">${a.agent?.ip_address||''}</span></td>
      <td>${a.personnel?`👤 <strong>${escHtml(a.personnel.full_name)}</strong><br>
          <span class="text-muted" style="font-size:10px">${a.personnel.department}</span>`:
          `<span style="color:var(--yellow);font-size:11px">⚠ Sin asignar</span>`}</td>
      <td>${maintHtml}</td>
      <td><span class="status status-${a.status}">${a.status}</span></td>
      <td style="font-size:11px">
        ${a.carta_sent?'<span style="color:var(--green)">✉ Enviada</span>':''}
        ${a.carta_alta_uploaded?'<span style="color:var(--green)">📎 Alta</span>':''}
        ${a.carta_baja_uploaded?'<span style="color:var(--red)">📎 Baja</span>':''}
        ${!a.carta_sent&&!a.carta_alta_uploaded?'—':''}
      </td>
      <td style="white-space:nowrap">
        ${a.personnel_id?
          `<button class="btn btn-danger btn-sm" onclick="openBajaFromAsset(${a.id})">🔴 Baja</button>`:
          `<button class="btn btn-warning btn-sm" onclick="openAssignFromAsset(${a.id})">👤 Asignar</button>`}
        <button class="btn btn-ghost btn-sm" onclick="window.open('/api/assets/${a.id}/carta/alta','_blank')">📄</button>
        <button class="btn btn-ghost btn-sm" onclick="openAssetForm(${a.id})">✏</button>
        <button class="btn btn-danger btn-sm" onclick="deleteAsset(${a.id})">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

async function openAssignFromAsset(assetId) {
  window._detailPersonnel = window._personnel || await apiGet('/api/personnel') || [];
  await openAssignModal(assetId);
}

async function openBajaFromAsset(assetId) {
  await openBajaModal(assetId);
}

async function openAssetForm(assetId) {
  const v = assetId?(window._assets||[]).find(a=>a.id===assetId)||{}:{};
  openModal(assetId?'Editar Activo':'Nuevo Activo', `
  <div class="form-row">
    <div class="form-field"><label>Tipo</label>
      <select id="f-type">${['laptop','pc','server','switch','firewall','printer','other'].map(t=>`<option value="${t}" ${v.asset_type===t?'selected':''}>${AICONS[t]} ${t}</option>`).join('')}</select></div>
    <div class="form-field"><label>Estado</label>
      <select id="f-status">${['active','maintenance','repair','decommissioned'].map(s=>`<option value="${s}" ${(v.status||'active')===s?'selected':''}>${s}</option>`).join('')}</select></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Marca</label><input id="f-brand" value="${v.brand||''}"/></div>
    <div class="form-field"><label>Modelo</label><input id="f-model" value="${v.model||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Serie</label><input id="f-serial" value="${v.serial_number||''}"/></div>
    <div class="form-field"><label>Fecha Compra</label><input id="f-pdate" type="date" value="${v.purchase_date||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Costo ($)</label><input id="f-cost" type="number" value="${v.purchase_cost||0}"/></div>
    <div class="form-field"><label>Ubicación</label><input id="f-loc" value="${v.location||''}"/></div>
  </div>
  <div class="form-field"><label>Notas</label><textarea id="f-notes">${v.notes||''}</textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveAsset(${assetId||'null'})">Guardar</button>
  </div>`);
}

async function saveAsset(assetId) {
  const body={asset_type:document.getElementById('f-type').value,brand:document.getElementById('f-brand').value,
    model:document.getElementById('f-model').value,serial_number:document.getElementById('f-serial').value,
    purchase_date:document.getElementById('f-pdate').value,purchase_cost:parseFloat(document.getElementById('f-cost').value)||0,
    location:document.getElementById('f-loc').value,status:document.getElementById('f-status').value,
    notes:document.getElementById('f-notes').value};
  if (assetId) await apiPut(`/api/assets/${assetId}`,body); else await apiPost('/api/assets',body);
  closeModal(); toast('Activo guardado','success'); loadAssets();
}

async function deleteAsset(id) {
  if (!confirm('¿Eliminar?')) return;
  await apiDelete(`/api/assets/${id}`);
  toast('Eliminado','info'); loadAssets();
}

function exportAssetsCSV() {
  const rows=[['Código','Tipo','Marca','Modelo','Serie','Responsable','Depto','Email','Ubicación','Estado','Próx.Mant','Carta']];
  (window._assets||[]).forEach(a=>rows.push([a.asset_code,a.asset_type,a.brand,a.model,a.serial_number,
    a.personnel?.full_name||'',a.personnel?.department||'',a.personnel?.email||'',
    a.location,a.status,a.next_maintenance||'',a.carta_sent?'Sí':'No']));
  downloadCSV(rows,'activos.csv');
}

// ─── PERSONNEL ───────────────────────────────────────────────────────────────
async function loadPersonnel() {
  const people = await apiGet('/api/personnel');
  if (!people) return;
  const el = document.getElementById('view-personnel');
  el.innerHTML = `
  <div class="page-header">
    <div><h2>👥 Personal</h2><p>${people.length} empleados</p></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="exportPersonnelCSV()">⬇ CSV</button>
      <button class="btn btn-primary btn-sm" onclick="openPersonnelForm()">+ Nuevo Empleado</button>
    </div>
  </div>
  <div class="table-container">
    <div class="table-toolbar">
      <input class="search-input" id="per-q" placeholder="🔍 Nombre, puesto, departamento..." oninput="filterPersonnel(this.value)"/>
      <select class="search-input" id="per-dept" style="flex:0;min-width:150px" onchange="filterPersonnel(document.getElementById('per-q').value)">
        <option value="">Todos</option>
        ${[...new Set(people.map(p=>p.department).filter(Boolean))].map(d=>`<option value="${d}">${d}</option>`).join('')}
      </select>
    </div>
    <table>
      <thead><tr><th>ID</th><th>Empleado</th><th>Puesto</th><th>Departamento</th>
        <th>Email</th><th>Equipos</th><th>Estado</th><th></th></tr></thead>
      <tbody id="per-tbody"></tbody>
    </table>
  </div>`;
  window._personnel = people;
  renderPersonnelTable(people);
}

function filterPersonnel(q) {
  const dept = document.getElementById('per-dept')?.value||'';
  renderPersonnelTable((window._personnel||[]).filter(p=>
    (!q||p.full_name.toLowerCase().includes(q.toLowerCase())||p.position.toLowerCase().includes(q.toLowerCase())||
     p.employee_id.toLowerCase().includes(q.toLowerCase())||p.email.toLowerCase().includes(q.toLowerCase()))&&
    (!dept||p.department===dept)
  ));
}

function renderPersonnelTable(people) {
  const tbody = document.getElementById('per-tbody');
  if (!tbody) return;
  if (!people.length) { tbody.innerHTML=`<tr><td colspan="8" class="table-empty">Sin personal</td></tr>`; return; }
  tbody.innerHTML = people.map(p=>{
    const ini = p.full_name.split(' ').map(w=>w[0]).join('').substring(0,2).toUpperCase();
    return `<tr>
      <td class="monospace">${escHtml(p.employee_id)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,rgba(88,166,255,.2),rgba(163,113,247,.2));
            border:1px solid rgba(163,113,247,.3);display:flex;align-items:center;justify-content:center;
            font-weight:700;font-size:13px;flex-shrink:0;color:var(--purple)">${ini}</div>
          <div><strong>${escHtml(p.full_name)}</strong><br>
            <span class="text-muted" style="font-size:10px">${p.location||''}</span></div>
        </div>
      </td>
      <td>${escHtml(p.position)}</td>
      <td><span class="dept-tag">${escHtml(p.department)}</span></td>
      <td class="text-muted" style="font-size:12px">${escHtml(p.email)}</td>
      <td>
        <span class="badge" style="background:var(--accent)">${p.asset_count}</span>
        ${p.current_assets?.length?`<button class="btn btn-ghost btn-sm" style="margin-left:4px" onclick="showPersonnelHistory(${p.id},'${escHtml(p.full_name)}')">📋 Ver</button>`:''}
      </td>
      <td><span class="status ${p.is_active?'status-online':'status-offline'}">${p.is_active?'Activo':'Inactivo'}</span></td>
      <td style="white-space:nowrap">
        <button class="btn btn-ghost btn-sm" onclick="showPersonnelHistory(${p.id},'${escHtml(p.full_name)}')">📋 Historial</button>
        <button class="btn btn-ghost btn-sm" onclick="openPersonnelForm(${p.id})">✏</button>
        <button class="btn btn-danger btn-sm" onclick="deletePersonnel(${p.id})">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

async function showPersonnelHistory(pid, name) {
  const hist = await apiGet(`/api/personnel/${pid}/history`);
  if (!hist) return;
  openModal(`📋 Historial — ${name}`,
  `${hist.length===0?'<p class="text-muted">Sin historial de equipos.</p>':
    `<table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr>
        <th style="text-align:left;padding:7px;border-bottom:1px solid var(--border);color:var(--text2)">Acción</th>
        <th style="text-align:left;padding:7px;border-bottom:1px solid var(--border);color:var(--text2)">Activo</th>
        <th style="text-align:left;padding:7px;border-bottom:1px solid var(--border);color:var(--text2)">Fecha</th>
        <th style="text-align:left;padding:7px;border-bottom:1px solid var(--border);color:var(--text2)">Notas</th>
        <th style="text-align:left;padding:7px;border-bottom:1px solid var(--border);color:var(--text2)">Carta</th>
      </tr></thead>
      <tbody>
        ${hist.map(h=>`<tr>
          <td style="padding:7px">
            <span class="status ${h.action==='alta'?'status-online':'status-offline'}">${h.action==='alta'?'✅ Alta':'🔴 Baja'}</span>
          </td>
          <td style="padding:7px"><strong>${h.asset?.asset_code||'—'}</strong><br>
            <span style="color:var(--text2)">${h.asset?h.asset.asset_type+' '+h.asset.brand+' '+h.asset.model:''}</span></td>
          <td style="padding:7px;font-family:monospace;font-size:11px">${new Date(h.action_date).toLocaleDateString('es-MX')}</td>
          <td style="padding:7px;color:var(--text2)">${escHtml(h.notes||'—')}</td>
          <td style="padding:7px">${h.carta_path?'<span style="color:var(--green)">📎 Subida</span>':'—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>`}
  <div class="modal-footer"><button class="btn btn-ghost" onclick="closeModal()">Cerrar</button></div>`);
}

function openPersonnelForm(pid=null) {
  const v = pid?(window._personnel||[]).find(p=>p.id===pid)||{}:{};
  openModal(pid?'Editar Empleado':'Nuevo Empleado', `
  <div class="form-row">
    <div class="form-field"><label>Número de Empleado *</label><input id="p-empid" value="${v.employee_id||''}"/></div>
    <div class="form-field"><label>Nombre Completo *</label><input id="p-name" value="${v.full_name||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Puesto *</label><input id="p-pos" value="${v.position||''}"/></div>
    <div class="form-field"><label>Departamento *</label><input id="p-dept" value="${v.department||''}" list="dl-dept"/>
      <datalist id="dl-dept">${[...new Set((window._personnel||[]).map(p=>p.department).filter(Boolean))].map(d=>`<option value="${d}">`).join('')}</datalist></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Correo *</label><input id="p-email" type="email" value="${v.email||''}"/></div>
    <div class="form-field"><label>Teléfono</label><input id="p-phone" value="${v.phone||''}"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Ubicación / Sucursal</label><input id="p-loc" value="${v.location||''}"/></div>
    <div class="form-field"><label>Estado</label>
      <select id="p-active"><option value="true" ${v.is_active!==false?'selected':''}>Activo</option>
        <option value="false" ${v.is_active===false?'selected':''}>Inactivo</option></select></div>
  </div>
  <div class="form-field"><label>Notas</label><textarea id="p-notes">${v.notes||''}</textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="savePersonnel(${pid||'null'})">Guardar</button>
  </div>`);
}

async function savePersonnel(pid) {
  const body={employee_id:document.getElementById('p-empid').value,full_name:document.getElementById('p-name').value,
    position:document.getElementById('p-pos').value,department:document.getElementById('p-dept').value,
    email:document.getElementById('p-email').value,phone:document.getElementById('p-phone').value,
    location:document.getElementById('p-loc').value,is_active:document.getElementById('p-active').value==='true',
    notes:document.getElementById('p-notes').value};
  if (!body.employee_id||!body.full_name||!body.position||!body.department||!body.email){
    toast('Completa los campos obligatorios (*)','warning'); return; }
  if (pid) await apiPut(`/api/personnel/${pid}`,body); else await apiPost('/api/personnel',body);
  closeModal(); toast('Empleado guardado','success'); loadPersonnel();
}

async function deletePersonnel(id) {
  if (!confirm('¿Eliminar empleado?')) return;
  await apiDelete(`/api/personnel/${id}`);
  toast('Eliminado','info'); loadPersonnel();
}

function exportPersonnelCSV() {
  const rows=[['ID','Nombre','Puesto','Depto','Email','Teléfono','Ubicación','Equipos','Estado']];
  (window._personnel||[]).forEach(p=>rows.push([p.employee_id,p.full_name,p.position,p.department,
    p.email,p.phone,p.location,p.asset_count,p.is_active?'Activo':'Inactivo']));
  downloadCSV(rows,'personal.csv');
}

// ─── MAINTENANCE ─────────────────────────────────────────────────────────────
async function loadMaintenance() {
  const [records, assets] = await Promise.all([apiGet('/api/maintenance'), apiGet('/api/assets')]);
  if (!records) return;
  const el = document.getElementById('view-maintenance');
  const overdue  = records.filter(m=>m.status==='pending'&&m.days_left!==null&&m.days_left<0).length;
  const upcoming = records.filter(m=>m.status==='pending'&&m.days_left!==null&&m.days_left>=0&&m.days_left<=30).length;

  el.innerHTML = `
  <div class="page-header">
    <div><h2>🔧 Mantenimientos</h2>
      <p>${records.length} registros — <span style="color:var(--red)">${overdue} vencidos</span> — <span style="color:var(--yellow)">${upcoming} próximos 30d</span></p></div>
    <button class="btn btn-primary btn-sm" onclick="openMaintenanceForm()">+ Registrar</button>
  </div>
  <div class="table-container">
    <table>
      <thead><tr><th>Activo</th><th>Responsable</th><th>Tipo</th><th>Realizado</th>
        <th>Próximo</th><th>Días</th><th>Técnico</th><th>Estado</th><th></th></tr></thead>
      <tbody>${records.length?records.map(m=>{
        const dl = m.days_left;
        const dlColor = dl===null?'':dl<0?'var(--red)':dl<=7?'var(--orange)':dl<=30?'var(--yellow)':'var(--text2)';
        const dlText  = dl===null?'—':dl<0?`⚠ ${Math.abs(dl)}d vencido`:dl===0?'¡HOY!':dl+'d';
        return `<tr>
          <td><strong>${m.asset_code}</strong><br><span class="text-muted" style="font-size:11px">${escHtml(m.asset_name)}</span>
            ${m.auto_created?'<br><span class="auto-badge">AUTO</span>':''}</td>
          <td class="text-muted" style="font-size:12px">${escHtml(m.responsible||'—')}</td>
          <td>${m.maint_type}</td>
          <td class="monospace" style="font-size:11px">${m.maintenance_date}</td>
          <td class="monospace" style="font-size:11px;color:${dlColor}">${m.next_date||'—'}</td>
          <td><span style="color:${dlColor};font-weight:700;font-size:12px">${dlText}</span></td>
          <td class="text-muted">${escHtml(m.technician||'—')}</td>
          <td><span class="status status-${m.status}">${m.status}</span>
            ${m.email_sent?'<br><span style="font-size:10px;color:var(--green)">✉ Avisado</span>':''}</td>
          <td style="white-space:nowrap">
            ${m.status==='pending'?`<button class="btn btn-success btn-sm" onclick="completeMaint(${m.id})">✅ Completar</button>`:''}
            <button class="btn btn-danger btn-sm" onclick="deleteMaint(${m.id})">🗑</button>
          </td>
        </tr>`;}).join(''):`<tr><td colspan="9" class="table-empty">Sin mantenimientos</td></tr>`}
      </tbody>
    </table>
  </div>`;
  window._maintenanceAssets = assets||[];
}

function openMaintenanceForm() {
  const assets = window._maintenanceAssets||[];
  openModal('Registrar Mantenimiento', `
  <div class="form-field"><label>Activo</label>
    <select id="m-asset">${assets.map(a=>`<option value="${a.id}">${a.asset_code} — ${a.brand} ${a.model}</option>`).join('')}</select></div>
  <div class="form-row">
    <div class="form-field"><label>Fecha Realizado</label><input id="m-date" type="date" value="${todayStr()}"/></div>
    <div class="form-field"><label>Próximo (opcional)</label><input id="m-next" type="date"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Técnico</label><input id="m-tech" placeholder="Nombre técnico"/></div>
    <div class="form-field"><label>Tipo</label>
      <select id="m-type"><option value="preventive">Preventivo</option><option value="corrective">Correctivo</option><option value="upgrade">Upgrade</option></select></div>
  </div>
  <div class="form-field"><label>Estado</label>
    <select id="m-status"><option value="completed">Completado</option><option value="pending">Pendiente</option><option value="in_progress">En Progreso</option></select></div>
  <div class="form-field"><label>Observaciones</label><textarea id="m-obs"></textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveMaintenance()">Guardar</button>
  </div>`);
}

async function saveMaintenance() {
  const body={asset_id:parseInt(document.getElementById('m-asset').value),
    maintenance_date:document.getElementById('m-date').value,next_date:document.getElementById('m-next').value||null,
    technician:document.getElementById('m-tech').value,maint_type:document.getElementById('m-type').value,
    status:document.getElementById('m-status').value,observations:document.getElementById('m-obs').value};
  await apiPost('/api/maintenance',body);
  closeModal(); toast('Mantenimiento guardado','success'); loadMaintenance();
}

async function completeMaint(id) {
  const res = await apiPut(`/api/maintenance/${id}/complete`, {});
  if (res?.completed) {
    toast('✅ Mantenimiento completado — Próximo programado para 1 año','success');
    loadMaintenance();
  }
}

async function deleteMaint(id) {
  if (!confirm('¿Eliminar?')) return;
  await apiDelete(`/api/maintenance/${id}`);
  toast('Eliminado','info'); loadMaintenance();
}

// ─── ALERTS ──────────────────────────────────────────────────────────────────
async function loadAlerts() {
  const alerts = await apiGet('/api/alerts');
  if (!alerts) return;
  const el = document.getElementById('view-alerts');
  const unack = alerts.filter(a=>!a.acknowledged);
  el.innerHTML = `
  <div class="page-header">
    <div><h2>🔔 Alertas</h2><p>${unack.length} sin reconocer</p></div>
    <button class="btn btn-ghost btn-sm" onclick="ackAllAlerts()">✓ Reconocer Todas</button>
  </div>
  <div class="alert-list">${alerts.length?alerts.map(a=>`
  <div class="alert-item ${a.severity}" style="${a.acknowledged?'opacity:.45':''}">
    <span>${a.severity==='critical'?'🔴':a.severity==='warning'?'🟡':'🔵'}</span>
    <div class="alert-msg"><div>${escHtml(a.message)}</div>
      <div class="text-muted" style="font-size:11px;margin-top:2px">${a.alert_type} • ${a.severity}</div></div>
    <span class="alert-time">${timeAgo(a.created_at)}</span>
    ${!a.acknowledged?`<button class="alert-ack-btn" onclick="ackAlert(${a.id})">✓</button>`:
      '<span class="text-muted" style="font-size:11px">✓</span>'}
  </div>`).join(''):`<div class="table-empty">🎉 Sin alertas activas</div>`}
  </div>`;
}

async function ackAlert(id) { await apiPut(`/api/alerts/${id}/acknowledge`,{}); loadAlerts(); }
async function ackAllAlerts() { await apiPost('/api/alerts/ack-all',{}); toast('Reconocidas','success'); loadAlerts(); }

// ─── USERS ───────────────────────────────────────────────────────────────────
async function loadUsers() {
  const users = await apiGet('/api/users');
  if (!users) return;
  const el = document.getElementById('view-users');
  el.innerHTML = `
  <div class="page-header"><div><h2>👤 Usuarios</h2><p>${users.length} usuarios</p></div>
    <button class="btn btn-primary btn-sm" onclick="openUserForm()">+ Nuevo</button></div>
  <div class="table-container"><table>
    <thead><tr><th>Usuario</th><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th></th></tr></thead>
    <tbody>${users.map(u=>`<tr>
      <td><strong>${escHtml(u.username)}</strong></td><td>${escHtml(u.full_name||'')}</td>
      <td class="text-muted">${escHtml(u.email||'')}</td>
      <td><span class="role-badge">${u.role}</span></td>
      <td><span class="status ${u.is_active?'status-online':'status-offline'}">${u.is_active?'Activo':'Inactivo'}</span></td>
      <td>${u.username!=='admin'?`<button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id})">🗑</button>`:''}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function openUserForm() {
  openModal('Nuevo Usuario', `
  <div class="form-row">
    <div class="form-field"><label>Usuario</label><input id="u-user"/></div>
    <div class="form-field"><label>Contraseña</label><input id="u-pass" type="password"/></div>
  </div>
  <div class="form-row">
    <div class="form-field"><label>Nombre</label><input id="u-name"/></div>
    <div class="form-field"><label>Email</label><input id="u-email" type="email"/></div>
  </div>
  <div class="form-field"><label>Rol</label>
    <select id="u-role"><option value="viewer">Viewer</option><option value="technician">Técnico</option>
      <option value="auditor">Auditor</option><option value="admin">Administrador</option></select></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveUser()">Crear</button>
  </div>`);
}

async function saveUser() {
  const body={username:document.getElementById('u-user').value,password:document.getElementById('u-pass').value,
    full_name:document.getElementById('u-name').value,email:document.getElementById('u-email').value,
    role:document.getElementById('u-role').value};
  const res=await apiPost('/api/users',body);
  if (res) { closeModal(); toast('Usuario creado','success'); loadUsers(); }
}

async function deleteUser(id) {
  if (!confirm('¿Eliminar?')) return;
  await apiDelete(`/api/users/${id}`); toast('Eliminado','info'); loadUsers();
}

// ─── CONFIG ──────────────────────────────────────────────────────────────────
async function loadConfig() {
  const cfg = await apiGet('/api/config/smtp');
  if (!cfg) return;
  document.getElementById('view-config').innerHTML = `
  <div class="page-header"><div><h2>⚙ Configuración SMTP</h2>
    <p>Correos para cartas, asignaciones y avisos de mantenimiento</p></div></div>
  <div class="config-section">
    <h3>📧 Configuración de Correo</h3>
    <div class="highlight-box mb-16">
      💡 <strong>Gmail:</strong> Usa tu correo y una 
      <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:var(--accent)">Contraseña de Aplicación</a>
      (no tu contraseña normal). Activa la verificación en 2 pasos primero.
    </div>
    <div class="form-row">
      <div class="form-field"><label>Servidor SMTP</label><input id="s-host" value="${cfg.host}"/></div>
      <div class="form-field"><label>Puerto</label><input id="s-port" type="number" value="${cfg.port}"/></div>
    </div>
    <div class="form-row">
      <div class="form-field"><label>Correo / Usuario</label><input id="s-user" value="${cfg.username}"/></div>
      <div class="form-field"><label>Contraseña / App Password</label><input id="s-pass" type="password" placeholder="••••••••"/></div>
    </div>
    <div class="form-row">
      <div class="form-field"><label>Nombre Remitente</label><input id="s-name" value="${cfg.from_name}"/></div>
      <div class="form-field"><label>Nombre Empresa (cartas)</label><input id="s-company" value="${cfg.company}"/></div>
    </div>
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:16px">
      <input type="checkbox" id="s-en" ${cfg.enabled?'checked':''} style="width:16px;height:16px;accent-color:var(--accent)">
      Habilitar envío automático de correos
    </label>
    <div style="display:flex;gap:10px">
      <button class="btn btn-primary" onclick="saveSmtp()">💾 Guardar</button>
      <button class="btn btn-ghost" onclick="testSmtp()">📨 Enviar prueba</button>
    </div>
  </div>`;
}

async function saveSmtp() {
  const body={host:document.getElementById('s-host').value,port:parseInt(document.getElementById('s-port').value),
    username:document.getElementById('s-user').value,password:document.getElementById('s-pass').value||'***',
    from_name:document.getElementById('s-name').value,company:document.getElementById('s-company').value,
    enabled:document.getElementById('s-en').checked};
  const r=await apiPut('/api/config/smtp',body);
  if (r) toast('Configuración guardada','success');
}

async function testSmtp() {
  toast('Enviando prueba...','info');
  const r=await apiPost('/api/config/smtp/test',{});
  if (r) toast(r.message,r.success?'success':'error');
}

// ─── TAG EDITOR ──────────────────────────────────────────────────────────────
function openTagEditor(agentId, tagsRaw) {
  let tags;
  try { tags = typeof tagsRaw==='string'?JSON.parse(tagsRaw):tagsRaw; } catch(e) { tags=[]; }
  window._editTags = [...(tags||[])];
  const renderTags = () => {
    const el = document.getElementById('tag-list');
    if (el) el.innerHTML = window._editTags.map((t,i)=>
      `<span class="tag">${escHtml(t)} <button onclick="window._editTags.splice(${i},1);renderTagList()" style="background:none;border:none;cursor:pointer;color:var(--red);font-weight:700;margin-left:3px">×</button></span>`).join('');
  };
  window.renderTagList = renderTags;
  openModal('🏷 Tags del Equipo', `
  <p class="text-muted mb-16">Tags para clasificar equipos en el inventario</p>
  <div style="display:flex;gap:8px;margin-bottom:10px">
    <input class="search-input" id="new-tag" placeholder="Nuevo tag..." style="flex:1"
      onkeydown="if(event.key==='Enter'){const v=this.value.trim().toUpperCase();if(v&&!window._editTags.includes(v)){window._editTags.push(v);this.value='';window.renderTagList();}event.preventDefault()}"/>
    <button class="btn btn-primary btn-sm" onclick="const v=document.getElementById('new-tag').value.trim().toUpperCase();if(v&&!window._editTags.includes(v)){window._editTags.push(v);document.getElementById('new-tag').value='';window.renderTagList();}">+</button>
  </div>
  <div id="tag-list" style="min-height:36px;display:flex;flex-wrap:wrap;gap:4px;margin-bottom:14px"></div>
  <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px">
    <span style="font-size:11px;color:var(--text2)">Sugeridos:</span>
    ${['LAPTOP','PC','SERVIDOR','FINANZAS','RRHH','TI','PRODUCCION','CRITICO','WINDOWS','LINUX','IMPRESORA'].map(t=>
      `<span class="tag" style="cursor:pointer" onclick="if(!window._editTags.includes('${t}'))window._editTags.push('${t}');window.renderTagList()">${t}</span>`).join('')}
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveTags(${agentId})">Guardar</button>
  </div>`);
  setTimeout(renderTags, 50);
}

async function saveTags(agentId) {
  await apiPut(`/api/agents/${agentId}/tags`, {tags:window._editTags});
  closeModal(); toast('Tags guardados','success'); loadInventory();
}

// ─── MODAL / TOAST ───────────────────────────────────────────────────────────
function openModal(title, body) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = body;
  document.getElementById('modal-overlay').classList.add('open');
}
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }

function toast(msg, type='info') {
  const icons={success:'✅',error:'❌',info:'ℹ️',warning:'⚠️'};
  const el=document.createElement('div');
  el.className=`toast ${type}`;
  el.innerHTML=`<span>${icons[type]||''}</span> ${msg}`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(()=>el.remove(), 4000);
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
function timeAgo(s) {
  if (!s) return '—';
  const d=Date.now()-new Date(s.endsWith('Z')?s:s+'Z').getTime(),sec=Math.floor(d/1000);
  if (sec<60) return sec+'s'; const m=Math.floor(sec/60);
  if (m<60) return m+'m';    const h=Math.floor(m/60);
  if (h<24) return h+'h';    return Math.floor(h/24)+'d';
}
function todayStr() { return new Date().toISOString().split('T')[0]; }
function escHtml(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function downloadCSV(rows,fn) {
  const csv=rows.map(r=>r.map(c=>`"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv'}));
  a.download=fn; a.click();
}
