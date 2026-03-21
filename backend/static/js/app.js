/* InfraWatch v2.2 — Frontend SPA completo */
'use strict';

const API = '';
let token = localStorage.getItem('iw_token');
let currentUser = null, refreshTimer = null, charts = {};

// ─── AUTH ────────────────────────────────────────────────────────────────────
async function doLogin() {
  const u = id('l-user').value.trim();
  const p = id('l-pass').value;
  id('login-err').textContent = '';
  try {
    const r = await fetch(`${API}/api/auth/login`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username: u, password: p})
    });
    if (!r.ok) { id('login-err').textContent = 'Credenciales incorrectas'; return; }
    const d = await r.json();
    token = d.token; localStorage.setItem('iw_token', token);
    currentUser = d; showApp();
  } catch { id('login-err').textContent = 'Error de conexión'; }
}

function doLogout() {
  token = null; currentUser = null; localStorage.removeItem('iw_token');
  if (refreshTimer) clearInterval(refreshTimer);
  id('app').style.display = 'none';
  id('login-screen').style.display = 'flex';
}

async function apiFetch(url, opts = {}) {
  const r = await fetch(`${API}${url}`, {
    ...opts, headers: {'Content-Type':'application/json',
      'Authorization': `Bearer ${token}`, ...(opts.headers || {})}
  });
  if (r.status === 401) { doLogout(); return null; }
  return r;
}
const apiGet    = async u      => { const r = await apiFetch(u); return r ? r.json() : null; };
const apiPost   = async (u, b) => { const r = await apiFetch(u, {method:'POST', body:JSON.stringify(b)}); return r ? r.json() : null; };
const apiPut    = async (u, b) => { const r = await apiFetch(u, {method:'PUT',  body:JSON.stringify(b)}); return r ? r.json() : null; };
const apiPatch  = async (u, b) => { const r = await apiFetch(u, {method:'PATCH',body:JSON.stringify(b||{})}); return r ? r.json() : null; };
const apiDelete = async u      => { const r = await apiFetch(u, {method:'DELETE'}); return r ? r.json() : null; };
const apiUpload = async (u, fd) => {
  const r = await fetch(`${API}${u}`, {method:'POST', headers:{'Authorization':`Bearer ${token}`}, body: fd});
  return r ? r.json() : null;
};

// ─── INIT ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  if (token) {
    try {
      const r = await apiFetch('/api/auth/me');
      if (r && r.ok) { currentUser = await r.json(); showApp(); return; }
    } catch {}
    token = null; localStorage.removeItem('iw_token');
  }
  id('login-screen').style.display = 'flex';
});

function showApp() {
  id('login-screen').style.display = 'none';
  id('app').style.display = 'flex';

  // Sidebar user info
  const ini = (currentUser.full_name || currentUser.username).split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  id('sf-avatar').textContent = ini;
  id('sf-name').textContent   = currentUser.full_name || currentUser.username;
  id('sf-role').textContent   = currentUser.role;

  // Show nav items by role
  const role = currentUser.role;
  const isIT    = ['admin','it'].includes(role);
  const isAdmin = role === 'admin';

  if (isIT || role === 'rh') { show('nl-audit'); }
  if (isIT)   { show('nl-areas'); show('nl-users'); show('nl-config'); }
  if (isAdmin){ show('nl-users'); }

  // Nav links
  qsa('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      qsa('.nav-link').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      showView(link.dataset.view);
    });
  });

  showView('dashboard');
  startRefresh();
}

function showView(view) {
  qsa('.view').forEach(v => v.classList.remove('active'));
  const el = id(`view-${view}`);
  if (el) el.classList.add('active');
  ({
    dashboard: loadDashboard, inventory: loadInventory, assets: loadAssets,
    personnel: loadPersonnel, maintenance: loadMaintenance, alerts: loadAlerts,
    audit: loadAudit, areas: loadAreas, users: loadUsers, config: loadConfig
  })[view]?.();
}

function startRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    const [alerts, dash] = await Promise.all([apiGet('/api/alerts'), apiGet('/api/dashboard')]);
    if (alerts) {
      const n = alerts.filter(a => !a.acknowledged).length;
      id('alert-badge').textContent = n > 0 ? n : '';
    }
    if (dash) {
      const pa = dash.assets?.pending_assign || 0;
      const pm = (dash.maintenance?.overdue || 0) + (dash.maintenance?.upcoming_30d || 0);
      setBadge('badge-assets', pa);
      setBadge('badge-maint', pm, true);
    }
    const av = qs('.view.active');
    if (av?.id === 'view-dashboard') loadDashboard(true);
    if (av?.id === 'view-inventory') loadInventory(true);
  }, 20000);
}

// ─── DASHBOARD ───────────────────────────────────────────────────────────────
async function loadDashboard(silent = false) {
  const [dash, agents] = await Promise.all([apiGet('/api/dashboard'), apiGet('/api/agents')]);
  if (!dash || !agents) return;
  const el = id('view-dashboard');

  const mList = dash.maintenance?.upcoming_list || [];
  const overdue = mList.filter(m => m.days_left < 0);

  el.innerHTML = `
  <div class="ph">
    <div><h2>📊 Panel de Control</h2>
      <p>InfraWatch v2.2 — ${new Date().toLocaleString('es-MX')}</p></div>
    <div class="ph-actions">
      <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Actualizar</button>
    </div>
  </div>

  <div class="sg">
    <div class="sc"><div class="sc-ico">🖥</div>
      <div class="sc-lbl">Hosts</div>
      <div class="sc-val">${dash.agents.total}</div>
      <div class="sc-sub">registrados</div></div>
    <div class="sc g"><div class="sc-ico">✅</div>
      <div class="sc-lbl">Online</div>
      <div class="sc-val">${dash.agents.online}</div>
      <div class="sc-sub">respondiendo</div></div>
    <div class="sc r"><div class="sc-ico">❌</div>
      <div class="sc-lbl">Offline</div>
      <div class="sc-val">${dash.agents.offline}</div>
      <div class="sc-sub">sin respuesta</div></div>
    <div class="sc p"><div class="sc-ico">👥</div>
      <div class="sc-lbl">Personal</div>
      <div class="sc-val">${dash.personnel.total}</div>
      <div class="sc-sub">${dash.personnel.active} activos</div></div>
    <div class="sc y"><div class="sc-ico">⚠</div>
      <div class="sc-lbl">Sin Responsable</div>
      <div class="sc-val">${dash.assets.pending_assign}</div>
      <div class="sc-sub">activos sin asignar</div></div>
    <div class="sc ${overdue.length > 0 ? 'r' : 'y'}"><div class="sc-ico">🔧</div>
      <div class="sc-lbl">Mantenimientos</div>
      <div class="sc-val">${overdue.length > 0 ? overdue.length : dash.maintenance.upcoming_30d}</div>
      <div class="sc-sub">${overdue.length > 0 ? '⚠ VENCIDOS' : 'próximos 30d'}</div></div>
  </div>

  <!-- Avg metrics -->
  <div class="cc mb16">
    <div class="ct">Promedio de Uso — Hosts Online</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:4px 0">
      ${[['CPU', dash.avg_metrics.cpu,'var(--cyn)'],['RAM',dash.avg_metrics.ram,'var(--grn)'],['Disco',dash.avg_metrics.disk,'var(--ylw)']].map(([l,v,c]) => `
      <div>
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">
          <span class="muted">${l}</span><span style="font-weight:700;color:${v>80?'var(--red)':v>60?'var(--ylw)':c}">${v}%</span>
        </div>
        <div style="background:var(--bg4);height:7px;border-radius:4px;overflow:hidden">
          <div style="width:${v}%;height:100%;background:${v>80?'var(--red)':v>60?'var(--ylw)':c};border-radius:4px;transition:width .5s"></div>
        </div>
      </div>`).join('')}
    </div>
  </div>

  ${mList.length ? `
  <div class="wbox mb16">
    <div style="font-weight:700;margin-bottom:10px">🔧 Mantenimientos Próximos / Vencidos</div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr>
        ${['Activo','Equipo','Responsable','Fecha','Días'].map(h=>`<th style="text-align:left;padding:6px;border-bottom:1px solid var(--bdr);color:var(--txt2);font-family:var(--mono);font-size:9px;text-transform:uppercase">${h}</th>`).join('')}
      </tr></thead>
      <tbody>${mList.map(m => {
        const c = m.days_left < 0 ? 'var(--red)' : m.days_left <= 7 ? 'var(--orn)' : 'var(--ylw)';
        const d = m.days_left < 0 ? `⚠ ${Math.abs(m.days_left)}d vencido` : m.days_left === 0 ? '¡HOY!' : `${m.days_left}d`;
        return `<tr>
          <td style="padding:6px"><strong>${m.asset_code}</strong></td>
          <td style="padding:6px;color:var(--txt2)">${esc(m.asset_name)}</td>
          <td style="padding:6px;color:var(--txt2)">${esc(m.responsible)}</td>
          <td style="padding:6px;font-family:var(--mono);font-size:11px">${m.next_date}</td>
          <td style="padding:6px"><span style="color:${c};font-weight:700">${d}</span></td>
        </tr>`;
      }).join('')}</tbody>
    </table>
  </div>` : ''}

  <div class="cg">
    <div class="cc"><div class="ct">Sistemas Operativos</div><div class="cw"><canvas id="ch-os"></canvas></div></div>
    <div class="cc"><div class="ct">Tipos de Activos</div><div class="cw"><canvas id="ch-type"></canvas></div></div>
    <div class="cc"><div class="ct">CPU % — Top Hosts</div><div class="cw"><canvas id="ch-cpu"></canvas></div></div>
    <div class="cc"><div class="ct">RAM % — Top Hosts</div><div class="cw"><canvas id="ch-ram"></canvas></div></div>
  </div>

  <div class="sec-title">Vista NOC — Estado de Hosts</div>
  <div class="ng">${agents.map(renderNoc).join('')}</div>`;

  // Charts
  const C = ['#00d4ff','#00c864','#ffcc00','#ff3355','#8855ff','#ff8800','#f778ba'];
  const pie = (id2, lbl, dat) => {
    if (charts[id2]) charts[id2].destroy();
    const c = document.getElementById(id2);
    if (!c) return;
    charts[id2] = new Chart(c, {
      type:'doughnut', data:{labels:lbl, datasets:[{data:dat, backgroundColor:C, borderWidth:0}]},
      options:{responsive:true,maintainAspectRatio:false,cutout:'60%',
        plugins:{legend:{position:'right',labels:{color:'#6a8fa8',font:{size:10},boxWidth:10}}}}
    });
  };
  const bar = (id2, lbl, dat, cs) => {
    if (charts[id2]) charts[id2].destroy();
    const c = document.getElementById(id2);
    if (!c) return;
    charts[id2] = new Chart(c, {
      type:'bar', data:{labels:lbl, datasets:[{data:dat, backgroundColor:cs, borderRadius:3}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
        scales:{x:{ticks:{color:'#6a8fa8',font:{size:9}},grid:{color:'#0f1923'}},
                y:{ticks:{color:'#6a8fa8',font:{size:9}},grid:{color:'#0f1923'},min:0,max:100}}}
    });
  };
  const osK = Object.keys(dash.os_distribution || {});
  pie('ch-os', osK, osK.map(k => dash.os_distribution[k]));
  const atK = Object.keys(dash.asset_distribution || {});
  pie('ch-type', atK, atK.map(k => dash.asset_distribution[k]));
  const online = agents.filter(a => a.status==='online' && a.metrics).slice(0,10);
  const lbls   = online.map(a => a.hostname.split('.')[0]);
  const cpus   = online.map(a => +(a.metrics.cpu_percent||0).toFixed(1));
  const rams   = online.map(a => +(a.metrics.ram_percent||0).toFixed(1));
  bar('ch-cpu', lbls, cpus, cpus.map(v => v>80?'#ff3355':v>60?'#ffcc00':'#00d4ff'));
  bar('ch-ram', lbls, rams, rams.map(v => v>80?'#ff3355':v>60?'#ffcc00':'#00c864'));
}

function renderNoc(a) {
  const m = a.metrics || {};
  const tags = (a.tags||[]).map(t => `<span class="tag">${esc(t)}</span>`).join('');
  const bc = v => v>80?'br':v>60?'by':'bg';
  return `
  <div class="nc ${a.status==='online'?'on':'off'}" onclick="loadAgent(${a.id})">
    <div class="nc-head">
      <div>
        <div class="nc-hn">${esc(a.hostname)}</div>
        <div class="nc-ip">${a.ip_address}</div>
        ${a.asset_code?`<span class="nc-code">📦 ${a.asset_code}</span>`:''}
      </div>
      <span class="st st-${a.status}">${a.status==='online'?'Online':'Offline'}</span>
    </div>
    ${a.status==='online' && m.cpu_percent!==undefined ? `
    <div class="nc-bar">
      ${[['CPU',m.cpu_percent],['RAM',m.ram_percent],['DSK',m.disk_percent]].map(([l,v])=>`
      <div class="nc-row"><span class="nc-lbl">${l}</span>
        <div class="bar"><div class="bar-fill ${bc(v)}" style="width:${v||0}%"></div></div>
        <span class="nc-val">${(v||0).toFixed(0)}%</span>
      </div>`).join('')}
    </div>` : `<p class="muted" style="font-size:10px;margin-top:6px">Último: ${ago(a.last_seen)}</p>`}
    ${a.personnel
      ? `<div class="nc-person">👤 <strong>${esc(a.personnel.full_name)}</strong></div>`
      : `<div class="nc-person" style="color:var(--ylw)">⚠ Sin responsable</div>`}
    <div class="nc-tags">${tags}</div>
  </div>`;
}

// ─── INVENTORY ───────────────────────────────────────────────────────────────
async function loadInventory(silent = false) {
  const agents = await apiGet('/api/agents');
  if (!agents) return;
  const el = id('view-inventory');
  el.innerHTML = `
  <div class="ph">
    <div><h2>🖥 Inventario Automático</h2><p>${agents.length} equipos detectados</p></div>
    <div class="ph-actions">
      <button class="btn btn-ghost btn-sm" onclick="exportCSV(window._agents||[],'inventario.csv',['hostname','ip_address','mac_address','os_name','os_version','status'])">⬇ CSV</button>
      <button class="btn btn-ghost btn-sm" onclick="loadInventory()">↻</button>
    </div>
  </div>
  <div class="tc">
    <div class="tb">
      <input class="si" id="inv-q" placeholder="🔍 Hostname, IP, OS, responsable, tag..."
        oninput="filterInv(this.value)"/>
      <select class="si" id="inv-st" style="flex:0;min-width:110px" onchange="filterInv(id('inv-q').value)">
        <option value="">Todos</option><option value="online">Online</option><option value="offline">Offline</option>
      </select>
    </div>
    <table>
      <thead><tr><th>Hostname</th><th>IP / MAC</th><th>OS</th><th>CPU/RAM</th><th>Responsable</th><th>Tags</th><th>Estado</th><th>Visto</th><th></th></tr></thead>
      <tbody id="inv-tbody"></tbody>
    </table>
  </div>`;
  window._agents = agents;
  renderInv(agents);
}

function filterInv(q) {
  const st = id('inv-st')?.value || '';
  renderInv((window._agents||[]).filter(a =>
    (!q || [a.hostname,a.ip_address,a.mac_address,a.os_name,a.os_version,
              a.personnel?.full_name].some(f => (f||'').toLowerCase().includes(q.toLowerCase())) ||
     (a.tags||[]).some(t => t.toLowerCase().includes(q.toLowerCase()))) &&
    (!st || a.status === st)
  ));
}

function renderInv(agents) {
  const tb = id('inv-tbody');
  if (!tb) return;
  if (!agents.length) { tb.innerHTML=`<tr><td colspan="9" class="te">Sin equipos</td></tr>`; return; }
  tb.innerHTML = agents.map(a => {
    const m = a.metrics || {};
    const cc = v => v>80?'color:var(--red)':v>60?'color:var(--ylw)':'';
    const tags = (a.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('');
    return `<tr>
      <td><strong>${esc(a.hostname)}</strong>
        ${a.asset_code?`<br><span class="nc-code">📦 ${a.asset_code}</span>`:''}</td>
      <td class="mono">${a.ip_address}<br><span class="muted">${a.mac_address||'—'}</span></td>
      <td>${esc(a.os_name||'—')}<br><span class="muted" style="font-size:10px">${esc(a.os_version||'')}</span></td>
      <td class="mono">
        <span style="${cc(m.cpu_percent)}">CPU: ${m.cpu_percent!==undefined?m.cpu_percent.toFixed(0)+'%':'—'}</span><br>
        <span style="${cc(m.ram_percent)}">RAM: ${m.ram_percent!==undefined?m.ram_percent.toFixed(0)+'%':'—'}</span>
      </td>
      <td>${a.personnel
        ?`👤 ${esc(a.personnel.full_name)}<br><span class="muted" style="font-size:10px">${esc(a.personnel.department)}</span>`
        :`<span style="color:var(--ylw);font-size:11px">⚠ Sin asignar</span>`}</td>
      <td>${tags||'—'}</td>
      <td><span class="st st-${a.status}">${a.status==='online'?'Online':'Offline'}</span></td>
      <td class="muted mono" style="font-size:10px">${ago(a.last_seen)}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-ghost btn-sm" onclick="loadAgent(${a.id})">Ver</button>
        <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id},${JSON.stringify(a.tags||[])})">Tags</button>
      </td>
    </tr>`;
  }).join('');
}

// ─── AGENT DETAIL ────────────────────────────────────────────────────────────
async function loadAgent(agentId) {
  qsa('.nav-link').forEach(l=>l.classList.remove('active'));
  qsa('.view').forEach(v=>v.classList.remove('active'));
  id('view-agent').classList.add('active');

  const [a, personnel] = await Promise.all([apiGet(`/api/agents/${agentId}`), apiGet('/api/personnel')]);
  if (!a) return;
  window._dPersonnel = personnel || [];

  const asset = a.asset;
  const nm    = a.next_maintenance;
  const dep   = asset?.depreciation;
  const daysLeft = nm?.days_left;
  const mc = daysLeft===undefined?'':daysLeft<0?'var(--red)':daysLeft<=7?'var(--orn)':daysLeft<=30?'var(--ylw)':'var(--grn)';

  id('view-agent').innerHTML = `
  <div class="dh">
    <button class="db-btn" onclick="showView('inventory')">← Inventario</button>
    <div>
      <h2 style="font-size:20px">${esc(a.hostname)}</h2>
      <span class="st st-${a.status}" style="margin-top:4px">${a.status}</span>
      ${asset?.auto_created?'<span class="tag auto-tag" style="margin-left:8px">AUTO</span>':''}
    </div>
    <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="openTagEditor(${a.id},${JSON.stringify(a.tags||[])})">🏷 Tags</button>
      ${asset?`<button class="btn btn-cyan btn-sm" onclick="openAssign(${asset.id})">👤 ${asset.personnel_id?'Cambiar':'Asignar'}</button>`:''}
      ${asset&&asset.personnel_id?`<button class="btn btn-danger btn-sm" onclick="openBaja(${asset.id})">🔴 Dar de Baja</button>`:''}
      ${asset?`<button class="btn btn-ghost btn-sm" onclick="window.open('/api/assets/${asset.id}/carta/alta','_blank')">📄 Carta Alta</button>`:''}
      <button class="btn btn-danger btn-sm" onclick="delAgent(${a.id})">🗑</button>
    </div>
  </div>

  <div class="di-grid">
    <div class="di"><div class="di-lbl">IP Address</div><div class="di-val">${a.ip_address}</div></div>
    <div class="di"><div class="di-lbl">MAC Address</div><div class="di-val">${a.mac_address}</div></div>
    <div class="di"><div class="di-lbl">Sistema Op.</div><div class="di-val" style="font-size:11px">${esc(a.os_name)} ${esc(a.os_version||'')}</div></div>
    <div class="di"><div class="di-lbl">CPU</div><div class="di-val" style="font-size:11px">${esc(a.cpu_model||'—')} (${a.cpu_cores} cores)</div></div>
    <div class="di"><div class="di-lbl">RAM Total</div><div class="di-val">${(a.ram_total_gb||0).toFixed(1)} GB</div></div>
    <div class="di"><div class="di-lbl">Disco Total</div><div class="di-val">${(a.disk_total_gb||0).toFixed(1)} GB</div></div>
    ${asset?`<div class="di"><div class="di-lbl">Código Activo</div><div class="di-val">${asset.asset_code}</div></div>`:''}
    <div class="di"><div class="di-lbl">Responsable</div>
      <div class="di-val" style="font-size:11px;color:${asset?.personnel_name?'var(--grn)':'var(--ylw)'}">
        ${esc(asset?.personnel_name||'Sin asignar')}</div></div>
    ${nm?`<div class="di"><div class="di-lbl">Próx. Mantto</div>
      <div class="di-val" style="font-size:11px;color:${mc}">${nm.next_date}
        <br>${daysLeft<0?`⚠ ${Math.abs(daysLeft)}d vencido`:daysLeft+'d restantes'}</div></div>`:''}
  </div>

  ${dep && dep.purchase_cost > 0 ? `
  <div class="cc mb16">
    <div class="ct">Depreciación del Activo</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:12px">
      <div><div class="muted" style="font-size:10px;margin-bottom:3px">Costo Original</div>
        <strong>$${dep.purchase_cost.toLocaleString()}</strong></div>
      <div><div class="muted" style="font-size:10px;margin-bottom:3px">Valor Actual</div>
        <strong style="color:var(--grn)">$${dep.current_value.toLocaleString()}</strong></div>
      <div><div class="muted" style="font-size:10px;margin-bottom:3px">Depreciado</div>
        <strong style="color:var(--ylw)">${dep.depreciated_pct}%</strong></div>
    </div>
    <div class="dep-bar mt16"><div class="dep-fill" style="width:${dep.depreciated_pct}%;background:${dep.depreciated_pct>80?'var(--red)':dep.depreciated_pct>50?'var(--ylw)':'var(--grn)'}"></div></div>
  </div>` : ''}

  ${asset && !asset.personnel_id ? `<div class="wbox">⚠ Sin responsable asignado.
    <button class="btn btn-warn btn-sm" style="margin-left:10px" onclick="openAssign(${asset.id})">Asignar ahora</button>
  </div>` : ''}
  ${asset && asset.personnel_id ? `
  <div class="hbox" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
    <div>✅ <strong>${esc(asset.personnel_name)}</strong> — Responsable asignado
      ${asset.carta_alta_uploaded?'<span class="tag" style="margin-left:8px">📎 Alta</span>':''}
      ${asset.carta_baja_uploaded?'<span class="tag auto-tag" style="margin-left:4px">📎 Baja</span>':''}
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-ghost btn-sm" onclick="window.open('/api/assets/${asset.id}/carta/alta','_blank')">📄 Carta Alta</button>
      <button class="btn btn-ghost btn-sm" onclick="openUpload(${asset.id},'alta')">⬆ Subir</button>
    </div>
  </div>` : ''}

  ${a.metrics_history?.length ? `
  <div class="cg mt16">
    <div class="cc"><div class="ct">CPU %</div><div class="cw"><canvas id="d-cpu"></canvas></div></div>
    <div class="cc"><div class="ct">RAM %</div><div class="cw"><canvas id="d-ram"></canvas></div></div>
    <div class="cc"><div class="ct">Disco %</div><div class="cw"><canvas id="d-disk"></canvas></div></div>
    <div class="cc"><div class="ct">Procesos</div><div class="cw"><canvas id="d-proc"></canvas></div></div>
  </div>` : ''}

  ${a.metrics_history?.[a.metrics_history.length-1]?.open_ports?.length ? `
  <div class="sec-title mt16">Puertos Abiertos Detectados</div>
  <div style="background:var(--bg2);border:1px solid var(--bdr);border-radius:var(--r);padding:12px;display:flex;flex-wrap:wrap;gap:4px">
    ${a.metrics_history[a.metrics_history.length-1].open_ports.map(p=>
      `<span style="background:rgba(0,200,100,.1);border:1px solid rgba(0,200,100,.2);border-radius:4px;padding:2px 8px;font-family:var(--mono);font-size:11px;color:var(--grn)">${p}</span>`).join('')}
  </div>` : ''}`;

  // History charts
  if (a.metrics_history?.length) {
    const h = a.metrics_history;
    const lbl = h.map(m => new Date(m.timestamp).toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'}));
    const line = (cid, data, color, fill) => {
      const c = document.getElementById(cid);
      if (!c) return;
      new Chart(c, {type:'line',
        data:{labels:lbl,datasets:[{data,borderColor:color,fill:true,backgroundColor:fill,tension:.3,pointRadius:1}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
          elements:{point:{radius:1}},
          scales:{x:{ticks:{color:'#6a8fa8',font:{size:9},maxTicksLimit:8},grid:{color:'#0f1923'}},
                  y:{ticks:{color:'#6a8fa8',font:{size:9}},grid:{color:'#0f1923'},min:0}}}});
    };
    line('d-cpu', h.map(m=>m.cpu_percent?.toFixed(1)),  '#00d4ff','rgba(0,212,255,.1)');
    line('d-ram', h.map(m=>m.ram_percent?.toFixed(1)),  '#00c864','rgba(0,200,100,.1)');
    line('d-disk',h.map(m=>m.disk_percent?.toFixed(1)), '#ffcc00','rgba(255,204,0,.1)');
    line('d-proc',h.map(m=>m.process_count),            '#8855ff','rgba(136,85,255,.1)');
  }
}

// ─── ASSETS ──────────────────────────────────────────────────────────────────
async function loadAssets() {
  const [assets, personnel] = await Promise.all([apiGet('/api/assets'), apiGet('/api/personnel')]);
  if (!assets) return;
  window._assets = assets; window._personnel = personnel || [];
  const pending = assets.filter(a=>!a.personnel_id).length;
  const el = id('view-assets');
  el.innerHTML = `
  <div class="ph">
    <div><h2>📦 Activos Fijos</h2>
      <p>${assets.length} activos — <span style="color:var(--ylw)">${pending} sin responsable</span></p></div>
    <div class="ph-actions">
      <button class="btn btn-ghost btn-sm" onclick="exportAssetsCSV()">⬇ CSV</button>
      <button class="btn btn-primary btn-sm" onclick="openAssetForm()">+ Nuevo</button>
    </div>
  </div>
  <div class="tc">
    <div class="tb">
      <input class="si" id="ast-q" placeholder="🔍 Código, marca, responsable..." oninput="filterAssets(this.value)"/>
      <select class="si" id="ast-type" style="flex:0;min-width:110px" onchange="filterAssets(id('ast-q').value)">
        <option value="">Todos</option>
        ${['laptop','pc','server','switch','firewall','printer','other'].map(t=>`<option value="${t}">${t}</option>`).join('')}
      </select>
      <select class="si" id="ast-sg" style="flex:0;min-width:130px" onchange="filterAssets(id('ast-q').value)">
        <option value="">Todos</option><option value="assigned">Con responsable</option>
        <option value="unassigned">Sin responsable</option><option value="auto">Auto-detectados</option>
      </select>
    </div>
    <table>
      <thead><tr><th>Código</th><th>Tipo</th><th>Equipo/Host</th><th>Responsable</th>
        <th>Valor Actual</th><th>Próx.Mant</th><th>Estado</th><th>Carta</th><th></th></tr></thead>
      <tbody id="ast-tbody"></tbody>
    </table>
  </div>`;
  renderAssets(assets);
}

const AICO = {laptop:'💻',pc:'🖥',server:'🗄',switch:'🔀',firewall:'🛡',printer:'🖨',other:'📦'};

function filterAssets(q) {
  const type = id('ast-type')?.value||'';
  const sg   = id('ast-sg')?.value||'';
  renderAssets((window._assets||[]).filter(a=>
    (!q || [a.asset_code,a.brand,a.model,a.personnel?.full_name,a.agent?.hostname].some(f=>(f||'').toLowerCase().includes(q.toLowerCase()))) &&
    (!type || a.asset_type===type) &&
    (sg===''||(sg==='assigned'&&a.personnel_id)||(sg==='unassigned'&&!a.personnel_id)||(sg==='auto'&&a.auto_created))
  ));
}

function renderAssets(assets) {
  const tb = id('ast-tbody');
  if (!tb) return;
  if (!assets.length) { tb.innerHTML=`<tr><td colspan="9" class="te">Sin activos</td></tr>`; return; }
  tb.innerHTML = assets.map(a => {
    const dep = a.depreciation || {};
    const nm  = a.next_maintenance;
    let mh = '—';
    if (nm) {
      const dl = Math.round((new Date(nm)-new Date())/(1000*60*60*24));
      const c  = dl<0?'var(--red)':dl<=7?'var(--orn)':dl<=30?'var(--ylw)':'var(--txt3)';
      mh = `<span style="color:${c};font-size:11px">${nm}<br>${dl<0?`⚠${Math.abs(dl)}d`:dl+'d'}</span>`;
    }
    return `<tr>
      <td class="mono"><strong>${a.asset_code}</strong>
        ${a.auto_created?'<br><span class="tag auto-tag">AUTO</span>':''}</td>
      <td>${AICO[a.asset_type]||'📦'} ${a.asset_type}</td>
      <td>${a.brand?`<strong>${esc(a.brand)}</strong> ${esc(a.model)}`:a.agent?esc(a.agent.hostname):'—'}
        <br><span class="muted" style="font-size:10px">${a.agent?.ip_address||''}</span></td>
      <td>${a.personnel
        ?`<span class="color-dot" style="background:${a.personnel.area_color||'#58a6ff'}"></span>👤 <strong>${esc(a.personnel.full_name)}</strong><br><span class="muted" style="font-size:10px">${esc(a.personnel.department)}</span>`
        :`<span class="tag warn-tag">⚠ Sin asignar</span>`}</td>
      <td class="mono" style="font-size:11px">${dep.purchase_cost>0?`$${dep.current_value?.toLocaleString()}<br><span class="muted">${dep.depreciated_pct}% dep.</span>`:'—'}</td>
      <td>${mh}</td>
      <td><span class="st st-${a.status}">${a.status}</span></td>
      <td style="font-size:11px">
        ${a.carta_sent?'<span style="color:var(--grn)">✉</span>':''}
        ${a.carta_alta_uploaded?'<span title="Alta firmada" style="color:var(--grn)">📎A</span>':''}
        ${a.carta_baja_uploaded?'<span title="Baja firmada" style="color:var(--red)">📎B</span>':''}
        ${!a.carta_sent&&!a.carta_alta_uploaded&&!a.carta_baja_uploaded?'—':''}
      </td>
      <td style="white-space:nowrap">
        ${a.personnel_id
          ?`<button class="btn btn-danger btn-sm" onclick="openBaja(${a.id})">🔴 Baja</button>`
          :`<button class="btn btn-warn btn-sm" onclick="openAssign(${a.id})">👤 Asignar</button>`}
        <button class="btn btn-ghost btn-sm" onclick="window.open('/api/assets/${a.id}/carta/alta','_blank')">📄</button>
        <button class="btn btn-ghost btn-sm" onclick="openAssetForm(${a.id})">✏</button>
        <button class="btn btn-danger btn-sm" onclick="delAsset(${a.id})">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

function exportAssetsCSV() {
  const rows = [['Código','Tipo','Marca','Modelo','Serie','Responsable','Área','Email','Estado','Valor Actual','Próx.Mant']];
  (window._assets||[]).forEach(a=>rows.push([a.asset_code,a.asset_type,a.brand,a.model,a.serial_number,
    a.personnel?.full_name||'',a.personnel?.department||'',a.personnel?.email||'',
    a.status,a.depreciation?.current_value||'',a.next_maintenance||'']));
  dlCSV(rows,'activos.csv');
}

async function openAssign(assetId) {
  const ppl = window._dPersonnel || window._personnel || await apiGet('/api/personnel') || [];
  const active = ppl.filter(p=>p.is_active);
  if (!active.length) { toast('Registra personal primero','warning'); showView('personnel'); return; }
  openModal('👤 Asignar Responsable', `
  <div class="ff"><label>Empleado Responsable *</label>
    <select id="as-p" style="width:100%">
      <option value="">— Selecciona —</option>
      ${active.map(p=>`<option value="${p.id}">${p.full_name} | ${p.employee_id} | ${p.department}</option>`).join('')}
    </select></div>
  <div class="ff"><label>Notas</label><textarea id="as-n" placeholder="Motivo de asignación..."></textarea></div>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:12px">
    <input type="checkbox" id="as-e" checked style="width:16px;height:16px;accent-color:var(--grn)">
    📧 Enviar correo con carta de alta al responsable
  </label>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="doAssign(${assetId})">✅ Asignar y Generar Carta</button>
  </div>`);
}

async function doAssign(assetId) {
  const pid = id('as-p').value;
  if (!pid) { toast('Selecciona un empleado','warning'); return; }
  const res = await apiPost(`/api/assets/${assetId}/assign`, {
    personnel_id: +pid,
    send_email:   id('as-e').checked,
    notes:        id('as-n').value,
  });
  if (res?.assigned) {
    closeModal();
    toast(`✅ Asignado a ${res.personnel}${id('as-e')?.checked?' — Correo enviado':''}`, 'success');
    setTimeout(() => location.reload(), 1500);
  }
}

async function openBaja(assetId) {
  openModal('🔴 Dar de Baja el Equipo', `
  <div class="wbox">⚠ Al dar de baja se desvincula el responsable y se genera la carta de baja.</div>
  <div class="ff"><label>Motivo / Observaciones</label>
    <textarea id="bj-n" placeholder="Término de contrato, reasignación, etc..."></textarea></div>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:12px">
    <input type="checkbox" id="bj-e" checked style="width:16px;height:16px;accent-color:var(--red)">
    📧 Enviar correo con carta de baja al empleado
  </label>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="doBaja(${assetId})">🔴 Confirmar Baja</button>
  </div>`);
}

async function doBaja(assetId) {
  const res = await apiPost(`/api/assets/${assetId}/baja`, {
    notes: id('bj-n').value, send_email: id('bj-e').checked
  });
  if (res?.baja) {
    closeModal(); toast('Baja registrada — Carta generada','info');
    setTimeout(() => location.reload(), 1500);
  }
}

async function openUpload(assetId, tipo) {
  openModal(`⬆ Subir Carta ${tipo==='alta'?'de Alta':'de Baja'} Firmada`, `
  <p class="muted mb16">Sube el PDF o imagen de la carta firmada para guardarla en el expediente.</p>
  <div class="ff"><label>Archivo (PDF, JPG, PNG)</label>
    <input type="file" id="up-f" accept=".pdf,.jpg,.jpeg,.png"
      style="width:100%;background:var(--bg3);border:1px solid var(--bdr2);color:var(--txt);padding:8px;border-radius:var(--r)"/></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="doUpload(${assetId},'${tipo}')">⬆ Subir</button>
  </div>`);
}

async function doUpload(assetId, tipo) {
  const file = id('up-f')?.files?.[0];
  if (!file) { toast('Selecciona un archivo','warning'); return; }
  const fd = new FormData(); fd.append('file', file);
  const res = await apiUpload(`/api/assets/${assetId}/upload/${tipo}`, fd);
  if (res?.uploaded) { closeModal(); toast('Carta subida','success'); }
  else toast('Error al subir','error');
}

async function openAssetForm(assetId = null) {
  const v = assetId ? (window._assets||[]).find(a=>a.id===assetId)||{} : {};
  openModal(assetId?'Editar Activo':'Nuevo Activo', `
  <div class="fr">
    <div class="ff"><label>Tipo</label>
      <select id="f-type">${['laptop','pc','server','switch','firewall','printer','other'].map(t=>
        `<option value="${t}" ${v.asset_type===t?'selected':''}>${AICO[t]} ${t}</option>`).join('')}</select></div>
    <div class="ff"><label>Estado</label>
      <select id="f-status">${['active','maintenance','repair','decommissioned'].map(s=>
        `<option value="${s}" ${(v.status||'active')===s?'selected':''}>${s}</option>`).join('')}</select></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Marca</label><input id="f-brand" value="${v.brand||''}"/></div>
    <div class="ff"><label>Modelo</label><input id="f-model" value="${v.model||''}"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Serie</label><input id="f-serial" value="${v.serial_number||''}"/></div>
    <div class="ff"><label>Fecha Compra</label><input id="f-pdate" type="date" value="${v.purchase_date||''}"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Costo ($)</label><input id="f-cost" type="number" value="${v.purchase_cost||0}"/></div>
    <div class="ff"><label>Vida Útil (años)</label><input id="f-life" type="number" value="${v.useful_life_yrs||4}"/></div>
  </div>
  <div class="ff"><label>Ubicación</label><input id="f-loc" value="${v.location||''}"/></div>
  <div class="ff"><label>Notas</label><textarea id="f-notes">${v.notes||''}</textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveAsset(${assetId||'null'})">Guardar</button>
  </div>`);
}

async function saveAsset(assetId) {
  const body = {asset_type:id('f-type').value,brand:id('f-brand').value,model:id('f-model').value,
    serial_number:id('f-serial').value,purchase_date:id('f-pdate').value,
    purchase_cost:+id('f-cost').value||0,useful_life_yrs:+id('f-life').value||4,
    location:id('f-loc').value,status:id('f-status').value,notes:id('f-notes').value};
  if (assetId) await apiPut(`/api/assets/${assetId}`,body); else await apiPost('/api/assets',body);
  closeModal(); toast('Activo guardado','success'); loadAssets();
}
async function delAsset(i) { if(!confirm('¿Eliminar?'))return; await apiDelete(`/api/assets/${i}`); toast('Eliminado','info'); loadAssets(); }
async function delAgent(i) { if(!confirm('¿Eliminar agente?'))return; await apiDelete(`/api/agents/${i}`); toast('Eliminado','info'); showView('inventory'); }

// ─── PERSONNEL ───────────────────────────────────────────────────────────────
async function loadPersonnel() {
  const [people, areas] = await Promise.all([apiGet('/api/personnel'), apiGet('/api/areas')]);
  if (!people) return;
  window._personnel = people; window._areas = areas || [];
  const el = id('view-personnel');
  el.innerHTML = `
  <div class="ph">
    <div><h2>👥 Personal</h2><p>${people.length} empleados</p></div>
    <div class="ph-actions">
      <button class="btn btn-ghost btn-sm" onclick="openImportCSV()">⬆ CSV</button>
      <button class="btn btn-ghost btn-sm" onclick="dlCSV([['ID','Nombre','Puesto','Departamento','Correo','Teléfono','Ubicación'],...(window._personnel||[]).map(p=>[p.employee_id,p.full_name,p.position,p.department,p.email,p.phone,p.location])],'personal.csv')">⬇ CSV</button>
      <button class="btn btn-primary btn-sm" onclick="openPersonnelForm()">+ Nuevo</button>
    </div>
  </div>
  <div class="tc">
    <div class="tb">
      <input class="si" id="per-q" placeholder="🔍 Nombre, ID, puesto, área..." oninput="filterPer(this.value)"/>
      <select class="si" id="per-area" style="flex:0;min-width:140px" onchange="filterPer(id('per-q').value)">
        <option value="">Todas las áreas</option>
        ${[...new Set(people.map(p=>p.area_name||p.department).filter(Boolean))].map(a=>`<option value="${a}">${a}</option>`).join('')}
      </select>
      <select class="si" id="per-st" style="flex:0;min-width:110px" onchange="filterPer(id('per-q').value)">
        <option value="">Todos</option><option value="active">Activos</option><option value="inactive">Inactivos</option>
      </select>
    </div>
    <table>
      <thead><tr><th>ID</th><th>Empleado</th><th>Puesto</th><th>Área</th><th>Correo</th>
        <th>Equipos</th><th>Estado</th><th></th></tr></thead>
      <tbody id="per-tbody"></tbody>
    </table>
  </div>`;
  renderPer(people);
}

function filterPer(q) {
  const area = id('per-area')?.value||'';
  const st   = id('per-st')?.value||'';
  renderPer((window._personnel||[]).filter(p=>
    (!q||[p.full_name,p.employee_id,p.position,p.email,p.area_name,p.department].some(f=>(f||'').toLowerCase().includes(q.toLowerCase()))) &&
    (!area||(p.area_name||p.department)===area) &&
    (st===''||(st==='active'&&p.is_active)||(st==='inactive'&&!p.is_active))
  ));
}

function renderPer(people) {
  const tb = id('per-tbody');
  if (!tb) return;
  if (!people.length) { tb.innerHTML=`<tr><td colspan="8" class="te">Sin personal</td></tr>`; return; }
  tb.innerHTML = people.map(p => {
    const ini = p.full_name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
    const roleCanEdit = ['admin','it','rh'].includes(currentUser?.role);
    return `<tr style="${p.is_active?'':'opacity:.55'}">
      <td class="mono">${esc(p.employee_id)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:9px">
          <div class="av" style="background:rgba(136,85,255,.15);border:1px solid rgba(136,85,255,.3);color:var(--pur)">${ini}</div>
          <div><strong>${esc(p.full_name)}</strong><br><span class="muted" style="font-size:10px">${esc(p.location||'')}</span></div>
        </div>
      </td>
      <td>${esc(p.position)}</td>
      <td><span class="color-dot" style="background:${p.area_color||'#58a6ff'}"></span>${esc(p.area_name||p.department||'—')}</td>
      <td class="muted" style="font-size:12px">${esc(p.email)}</td>
      <td>
        <span class="nb" style="background:var(--cyn)">${p.asset_count}</span>
        ${p.asset_count>0?`<button class="btn btn-ghost btn-sm" style="margin-left:4px" onclick="showHistory(${p.id},'${esc(p.full_name)}')">📋</button>`:''}
      </td>
      <td><span class="st ${p.is_active?'st-online':'st-offline'}">${p.is_active?'Activo':'Inactivo'}</span></td>
      <td style="white-space:nowrap">
        ${roleCanEdit?`
        <button class="btn btn-ghost btn-sm" onclick="showHistory(${p.id},'${esc(p.full_name)}')">📋</button>
        <button class="btn btn-ghost btn-sm" onclick="openPersonnelForm(${p.id})">✏</button>
        <button class="btn ${p.is_active?'btn-warn':'btn-cyan'} btn-sm" onclick="togglePer(${p.id})">${p.is_active?'🔒 Des.':'🔓 Act.'}</button>
        <button class="btn btn-danger btn-sm" onclick="delPer(${p.id})">🗑</button>`:
        `<button class="btn btn-ghost btn-sm" onclick="showHistory(${p.id},'${esc(p.full_name)}')">📋 Ver</button>`}
      </td>
    </tr>`;
  }).join('');
}

async function showHistory(pid, name) {
  const h = await apiGet(`/api/personnel/${pid}/history`);
  if (!h) return;
  openModal(`📋 Historial — ${name}`, `
  ${!h.length?'<p class="muted">Sin historial de equipos.</p>':`
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr>${['Acción','Activo','Fecha','Por','Notas','Carta'].map(c=>`<th style="text-align:left;padding:6px;border-bottom:1px solid var(--bdr);font-family:var(--mono);font-size:9px;text-transform:uppercase;color:var(--txt3)">${c}</th>`).join('')}</tr></thead>
    <tbody>${h.map(x=>`<tr>
      <td style="padding:6px"><span class="st ${x.action==='alta'?'st-online':'st-offline'}">${x.action==='alta'?'✅ Alta':'🔴 Baja'}</span></td>
      <td style="padding:6px"><strong>${x.asset?.asset_code||'—'}</strong><br>
        <span class="muted">${esc(x.asset?(x.asset.brand+' '+x.asset.model):'')}</span></td>
      <td style="padding:6px;font-family:var(--mono);font-size:10px">${new Date(x.action_date).toLocaleDateString('es-MX')}</td>
      <td style="padding:6px;color:var(--txt2)">${esc(x.created_by||'—')}</td>
      <td style="padding:6px;color:var(--txt2)">${esc((x.notes||'').slice(0,40))}</td>
      <td style="padding:6px">${x.carta_path?'<span style="color:var(--grn)">📎</span>':'—'}</td>
    </tr>`).join('')}</tbody>
  </table>`}
  <div class="modal-footer"><button class="btn btn-ghost" onclick="closeModal()">Cerrar</button></div>`);
}

function openPersonnelForm(pid = null) {
  const v = pid?(window._personnel||[]).find(p=>p.id===pid)||{}:{};
  const areas = window._areas || [];
  openModal(pid?'Editar Empleado':'Nuevo Empleado', `
  <div class="fr">
    <div class="ff"><label>Número de Empleado *</label><input id="p-id" value="${v.employee_id||''}"/></div>
    <div class="ff"><label>Nombre Completo *</label><input id="p-name" value="${v.full_name||''}"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Puesto *</label><input id="p-pos" value="${v.position||''}"/></div>
    <div class="ff"><label>Área *</label>
      <select id="p-area">
        <option value="">— Sin área —</option>
        ${areas.filter(a=>a.is_active).map(a=>`<option value="${a.id}" ${v.area_id===a.id?'selected':''}>${a.name}</option>`).join('')}
      </select></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Correo *</label><input id="p-email" type="email" value="${v.email||''}"/></div>
    <div class="ff"><label>Teléfono</label><input id="p-phone" value="${v.phone||''}"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Ubicación</label><input id="p-loc" value="${v.location||''}"/></div>
    <div class="ff"><label>Estado</label>
      <select id="p-active"><option value="true" ${v.is_active!==false?'selected':''}>Activo</option>
        <option value="false" ${v.is_active===false?'selected':''}>Inactivo</option></select></div>
  </div>
  <div class="ff"><label>Notas</label><textarea id="p-notes">${v.notes||''}</textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="savePer(${pid||'null'})">Guardar</button>
  </div>`);
}

async function savePer(pid) {
  const areaEl  = id('p-area');
  const areaId  = areaEl?.value ? +areaEl.value : null;
  const areaObj = (window._areas||[]).find(a=>a.id===areaId);
  const body = {
    employee_id: id('p-id').value, full_name: id('p-name').value,
    position: id('p-pos').value,
    department: areaObj?.name || '',
    area_id: areaId,
    email: id('p-email').value, phone: id('p-phone').value,
    location: id('p-loc').value, is_active: id('p-active').value==='true',
    notes: id('p-notes').value,
  };
  if (!body.employee_id||!body.full_name||!body.position||!body.email) {
    toast('Completa los campos obligatorios (*)','warning'); return; }
  if (pid) await apiPut(`/api/personnel/${pid}`,body); else await apiPost('/api/personnel',body);
  closeModal(); toast('Empleado guardado','success'); loadPersonnel();
}

async function togglePer(pid) {
  const res = await apiPatch(`/api/personnel/${pid}/toggle`);
  if (res) { toast(`Empleado ${res.is_active?'activado':'desactivado'}`,'info'); loadPersonnel(); }
}

async function delPer(pid) {
  if (!confirm('¿Eliminar empleado? Asegúrate de dar de baja sus equipos primero.')) return;
  const res = await apiDelete(`/api/personnel/${pid}`);
  if (res?.deleted) { toast('Eliminado','info'); loadPersonnel(); }
  else toast(res?.detail||'Error al eliminar','error');
}

function openImportCSV() {
  openModal('⬆ Importar Personal desde CSV', `
  <div class="hbox mb16">
    <strong>Formato CSV esperado:</strong><br>
    <code style="font-size:11px;color:var(--grn)">employee_id, full_name, position, department, email, phone, location</code>
  </div>
  <div class="ff"><label>Archivo CSV</label>
    <input type="file" id="csv-f" accept=".csv"
      style="width:100%;background:var(--bg3);border:1px solid var(--bdr2);color:var(--txt);padding:8px;border-radius:var(--r)"/></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="doImportCSV()">⬆ Importar</button>
  </div>`);
}

async function doImportCSV() {
  const file = id('csv-f')?.files?.[0];
  if (!file) { toast('Selecciona un archivo CSV','warning'); return; }
  const fd = new FormData(); fd.append('file', file);
  const res = await apiUpload('/api/personnel/import-csv', fd);
  if (res) {
    closeModal();
    toast(`✅ ${res.created} empleados importados${res.errors?.length?` — ${res.errors.length} errores`:''}`, res.errors?.length?'warning':'success');
    loadPersonnel();
  }
}

// ─── MAINTENANCE ─────────────────────────────────────────────────────────────
async function loadMaintenance() {
  const [records, assets] = await Promise.all([apiGet('/api/maintenance'), apiGet('/api/assets')]);
  if (!records) return;
  window._mAssets = assets || [];
  const overdue  = records.filter(m=>m.status==='pending'&&m.days_left!==null&&m.days_left<0).length;
  const upcoming = records.filter(m=>m.status==='pending'&&m.days_left!==null&&m.days_left>=0&&m.days_left<=30).length;
  const el = id('view-maintenance');
  el.innerHTML = `
  <div class="ph">
    <div><h2>🔧 Mantenimientos</h2>
      <p>${records.length} registros — <span style="color:var(--red)">${overdue} vencidos</span> — <span style="color:var(--ylw)">${upcoming} próximos 30d</span></p></div>
    <div class="ph-actions"><button class="btn btn-primary btn-sm" onclick="openMaintForm()">+ Registrar</button></div>
  </div>
  <div class="tc"><table>
    <thead><tr><th>Activo</th><th>Responsable</th><th>Tipo</th><th>Realizado</th>
      <th>Próximo</th><th>Días</th><th>Estado</th><th></th></tr></thead>
    <tbody>${records.length?records.map(m=>{
      const dl = m.days_left;
      const c  = dl===null?'':dl<0?'var(--red)':dl<=7?'var(--orn)':dl<=30?'var(--ylw)':'var(--txt3)';
      const dt = dl===null?'—':dl<0?`⚠ ${Math.abs(dl)}d`:dl===0?'¡HOY!':dl+'d';
      return `<tr>
        <td><strong>${m.asset_code}</strong><br><span class="muted" style="font-size:10px">${esc(m.asset_name)}</span>
          ${m.auto_created?'<br><span class="tag auto-tag">AUTO</span>':''}</td>
        <td class="muted" style="font-size:12px">${esc(m.responsible||'—')}</td>
        <td>${m.maint_type}</td>
        <td class="mono" style="font-size:10px">${m.maintenance_date}</td>
        <td class="mono" style="font-size:10px;color:${c}">${m.next_date||'—'}</td>
        <td><span style="color:${c};font-weight:700;font-size:12px">${dt}</span></td>
        <td><span class="st st-${m.status}">${m.status}</span>
          ${m.email_sent?'<br><span style="font-size:10px;color:var(--grn)">✉ Avisado</span>':''}</td>
        <td style="white-space:nowrap">
          ${m.status==='pending'?`<button class="btn btn-primary btn-sm" onclick="completeMaint(${m.id})">✅ Completar</button>`:''}
          <button class="btn btn-danger btn-sm" onclick="delMaint(${m.id})">🗑</button>
        </td>
      </tr>`;}).join(''):`<tr><td colspan="8" class="te">Sin mantenimientos</td></tr>`}
    </tbody>
  </table></div>`;
}

function openMaintForm() {
  const assets = window._mAssets || [];
  openModal('Registrar Mantenimiento', `
  <div class="ff"><label>Activo</label>
    <select id="m-a">${assets.map(a=>`<option value="${a.id}">${a.asset_code} — ${a.brand} ${a.model}</option>`).join('')}</select></div>
  <div class="fr">
    <div class="ff"><label>Fecha Realizado</label><input id="m-d" type="date" value="${today()}"/></div>
    <div class="ff"><label>Próximo</label><input id="m-n" type="date"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Técnico</label><input id="m-t" placeholder="Nombre técnico"/></div>
    <div class="ff"><label>Tipo</label>
      <select id="m-tp"><option value="preventive">Preventivo</option>
        <option value="corrective">Correctivo</option><option value="upgrade">Upgrade</option></select></div>
  </div>
  <div class="ff"><label>Estado</label>
    <select id="m-s"><option value="completed">Completado</option>
      <option value="pending">Pendiente</option><option value="in_progress">En Progreso</option></select></div>
  <div class="ff"><label>Observaciones</label><textarea id="m-o"></textarea></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveMaint()">Guardar</button>
  </div>`);
}

async function saveMaint() {
  const body={asset_id:+id('m-a').value,maintenance_date:id('m-d').value,
    next_date:id('m-n').value||null,technician:id('m-t').value,
    maint_type:id('m-tp').value,status:id('m-s').value,observations:id('m-o').value};
  await apiPost('/api/maintenance',body);
  closeModal(); toast('Mantenimiento guardado','success'); loadMaintenance();
}
async function completeMaint(mid) {
  const r = await apiPut(`/api/maintenance/${mid}/complete`,{});
  if (r?.completed) { toast('✅ Completado — Próximo a 1 año','success'); loadMaintenance(); }
}
async function delMaint(mid) {
  if(!confirm('¿Eliminar?'))return; await apiDelete(`/api/maintenance/${mid}`);
  toast('Eliminado','info'); loadMaintenance();
}

// ─── ALERTS ──────────────────────────────────────────────────────────────────
async function loadAlerts() {
  const alerts = await apiGet('/api/alerts');
  if (!alerts) return;
  const unack = alerts.filter(a=>!a.acknowledged);
  id('view-alerts').innerHTML = `
  <div class="ph">
    <div><h2>🔔 Alertas</h2><p>${unack.length} sin reconocer</p></div>
    <div class="ph-actions"><button class="btn btn-ghost btn-sm" onclick="ackAll()">✓ Reconocer Todas</button></div>
  </div>
  <div class="al">${alerts.length?alerts.map(a=>`
  <div class="ai ${a.severity}" style="${a.acknowledged?'opacity:.4':''}">
    <span>${a.severity==='critical'?'🔴':a.severity==='warning'?'🟡':'🔵'}</span>
    <div class="ai-msg">
      <div class="ai-t">${esc(a.message)}</div>
      <div class="ai-sub">${a.alert_type} • ${a.severity}</div>
    </div>
    <span class="ai-time">${ago(a.created_at)}</span>
    ${!a.acknowledged?`<button class="ai-ack" onclick="ackAlert(${a.id})">✓</button>`:
      '<span class="muted" style="font-size:11px">✓</span>'}
  </div>`).join(''):`<div class="te">🎉 Sin alertas activas</div>`}
  </div>`;
}
async function ackAlert(i)  { await apiPut(`/api/alerts/${i}/acknowledge`,{}); loadAlerts(); }
async function ackAll()     { await apiPost('/api/alerts/ack-all',{}); toast('Reconocidas','success'); loadAlerts(); }

// ─── AUDIT LOG ───────────────────────────────────────────────────────────────
async function loadAudit() {
  const logs = await apiGet('/api/audit');
  if (!logs) return;
  id('view-audit').innerHTML = `
  <div class="ph"><div><h2>📋 Auditoría del Sistema</h2><p>${logs.length} registros recientes</p></div></div>
  <div class="tc"><table>
    <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Descripción</th><th>Email</th></tr></thead>
    <tbody>${logs.length?logs.map(l=>`<tr>
      <td class="mono" style="font-size:10px">${new Date(l.timestamp).toLocaleString('es-MX')}</td>
      <td><strong>${esc(l.user)}</strong></td>
      <td><span class="st ${l.action==='CREATE'?'st-online':l.action==='DELETE'?'st-offline':'st-warning'}">${l.action}</span></td>
      <td class="muted">${esc(l.entity)}</td>
      <td style="font-size:12px">${esc(l.description)}</td>
      <td>${l.email_sent?'<span style="color:var(--grn)">✉ Sí</span>':'—'}</td>
    </tr>`).join(''):`<tr><td colspan="6" class="te">Sin registros</td></tr>`}
    </tbody>
  </table></div>`;
}

// ─── AREAS ───────────────────────────────────────────────────────────────────
async function loadAreas() {
  const areas = await apiGet('/api/areas');
  if (!areas) return;
  window._areas = areas;
  const isIT = ['admin','it'].includes(currentUser?.role);
  id('view-areas').innerHTML = `
  <div class="ph">
    <div><h2>🏢 Áreas</h2><p>${areas.length} áreas configuradas</p></div>
    ${isIT?`<div class="ph-actions"><button class="btn btn-primary btn-sm" onclick="openAreaForm()">+ Nueva Área</button></div>`:''}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">
    ${areas.map(a=>`
    <div style="background:var(--bg2);border:1px solid var(--bdr);border-radius:var(--rl);padding:16px;
      border-left:4px solid ${a.color}">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:8px">
          <div class="color-dot" style="background:${a.color};width:14px;height:14px"></div>
          <strong>${esc(a.name)}</strong>
        </div>
        <span class="st ${a.is_active?'st-online':'st-offline'}">${a.is_active?'Activa':'Inactiva'}</span>
      </div>
      <p class="muted" style="font-size:12px;margin-bottom:10px">${esc(a.description||'Sin descripción')}</p>
      <p class="muted" style="font-size:11px">👥 ${a.personnel_count} empleados</p>
      ${isIT?`<div style="display:flex;gap:6px;margin-top:10px">
        <button class="btn btn-ghost btn-sm" onclick="openAreaForm(${a.id})">✏ Editar</button>
        ${a.personnel_count===0?`<button class="btn btn-danger btn-sm" onclick="delArea(${a.id})">🗑</button>`:''}
      </div>`:''}
    </div>`).join('')}
  </div>`;
}

function openAreaForm(aid = null) {
  const v = aid ? (window._areas||[]).find(a=>a.id===aid)||{} : {};
  openModal(aid?'Editar Área':'Nueva Área', `
  <div class="fr">
    <div class="ff"><label>Nombre *</label><input id="ar-n" value="${esc(v.name||'')}"/></div>
    <div class="ff"><label>Color</label>
      <input id="ar-c" type="color" value="${v.color||'#58a6ff'}"
        style="width:100%;height:38px;padding:2px;background:var(--bg3);border:1px solid var(--bdr2);border-radius:var(--r);cursor:pointer"/></div>
  </div>
  <div class="ff"><label>Descripción</label><input id="ar-d" value="${esc(v.description||'')}"/></div>
  <div class="ff"><label>Estado</label>
    <select id="ar-s"><option value="true" ${v.is_active!==false?'selected':''}>Activa</option>
      <option value="false" ${v.is_active===false?'selected':''}>Inactiva</option></select></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveArea(${aid||'null'})">Guardar</button>
  </div>`);
}

async function saveArea(aid) {
  const body={name:id('ar-n').value,color:id('ar-c').value,
    description:id('ar-d').value,is_active:id('ar-s').value==='true'};
  if (!body.name) { toast('El nombre es obligatorio','warning'); return; }
  if (aid) await apiPut(`/api/areas/${aid}`,body); else await apiPost('/api/areas',body);
  closeModal(); toast('Área guardada','success'); loadAreas();
}
async function delArea(aid) {
  if(!confirm('¿Eliminar área?'))return;
  await apiDelete(`/api/areas/${aid}`); toast('Área eliminada','info'); loadAreas();
}

// ─── USERS ───────────────────────────────────────────────────────────────────
async function loadUsers() {
  const users = await apiGet('/api/users');
  if (!users) return;
  id('view-users').innerHTML = `
  <div class="ph"><div><h2>👤 Usuarios</h2><p>${users.length} usuarios</p></div>
    <div class="ph-actions"><button class="btn btn-primary btn-sm" onclick="openUserForm()">+ Nuevo</button></div>
  </div>
  <div class="tc"><table>
    <thead><tr><th>Usuario</th><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th></th></tr></thead>
    <tbody>${users.map(u=>`<tr>
      <td><strong>${esc(u.username)}</strong></td>
      <td>${esc(u.full_name||'')}</td>
      <td class="muted" style="font-size:12px">${esc(u.email||'')}</td>
      <td><span class="st st-${u.role==='admin'?'critical':u.role==='it'?'info':u.role==='rh'?'warning':'active'}">${u.role}</span></td>
      <td><span class="st ${u.is_active?'st-online':'st-offline'}">${u.is_active?'Activo':'Inactivo'}</span></td>
      <td>${u.username!=='admin'?`<button class="btn btn-danger btn-sm" onclick="delUser(${u.id})">🗑</button>`:''}</td>
    </tr>`).join('')}
    </tbody>
  </table></div>
  <div class="hbox mt16" style="font-size:12px">
    <strong>Roles disponibles:</strong><br>
    🔴 <strong>admin</strong> — Acceso total<br>
    🔵 <strong>it</strong> — Infraestructura completa (agentes, activos, mantenimiento, áreas, usuarios)<br>
    🟡 <strong>rh</strong> — Solo gestión de personal (crear, modificar, activar/desactivar empleados)<br>
    🟢 <strong>auditor</strong> — Solo lectura + auditoría<br>
    🟢 <strong>viewer</strong> — Solo lectura del dashboard
  </div>`;
}

function openUserForm() {
  openModal('Nuevo Usuario', `
  <div class="fr">
    <div class="ff"><label>Usuario</label><input id="u-u"/></div>
    <div class="ff"><label>Contraseña</label><input id="u-p" type="password"/></div>
  </div>
  <div class="fr">
    <div class="ff"><label>Nombre Completo</label><input id="u-n"/></div>
    <div class="ff"><label>Correo</label><input id="u-e" type="email"/></div>
  </div>
  <div class="ff"><label>Rol</label>
    <select id="u-r">
      <option value="viewer">viewer — Solo lectura</option>
      <option value="auditor">auditor — Lectura + auditoría</option>
      <option value="rh">rh — Gestión de Personal</option>
      <option value="it">it — Infraestructura completa</option>
      ${currentUser?.role==='admin'?'<option value="admin">admin — Acceso total</option>':''}
    </select></div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveUser()">Crear</button>
  </div>`);
}

async function saveUser() {
  const body={username:id('u-u').value,password:id('u-p').value,
    full_name:id('u-n').value,email:id('u-e').value,role:id('u-r').value};
  const r = await apiPost('/api/users',body);
  if (r?.id) { closeModal(); toast('Usuario creado — Correo de bienvenida enviado','success'); loadUsers(); }
  else toast(r?.detail||'Error','error');
}
async function delUser(i) {
  if(!confirm('¿Eliminar usuario?'))return; await apiDelete(`/api/users/${i}`); toast('Eliminado','info'); loadUsers();
}

// ─── CONFIG ──────────────────────────────────────────────────────────────────
async function loadConfig() {
  const cfg = await apiGet('/api/config/smtp');
  if (!cfg) return;
  id('view-config').innerHTML = `
  <div class="ph"><div><h2>⚙ Configuración</h2><p>SMTP y opciones del sistema</p></div></div>
  <div class="cc-section">
    <h3>📧 Configuración SMTP</h3>
    <div class="hbox mb16">
      💡 <strong>Gmail:</strong> Usa tu correo y una
      <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:var(--cyn)">Contraseña de Aplicación</a>
      (activa verificación en 2 pasos primero).
    </div>
    <div class="fr">
      <div class="ff"><label>Servidor SMTP</label><input id="s-h" value="${cfg.host}"/></div>
      <div class="ff"><label>Puerto</label><input id="s-p" type="number" value="${cfg.port}"/></div>
    </div>
    <div class="fr">
      <div class="ff"><label>Correo / Usuario</label><input id="s-u" value="${cfg.username}"/></div>
      <div class="ff"><label>App Password</label><input id="s-pw" type="password" placeholder="••••••••"/></div>
    </div>
    <div class="fr">
      <div class="ff"><label>Nombre Remitente</label><input id="s-n" value="${cfg.from_name}"/></div>
      <div class="ff"><label>Nombre Empresa (en cartas)</label><input id="s-c" value="${cfg.company}"/></div>
    </div>
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:16px">
      <input type="checkbox" id="s-en" ${cfg.enabled?'checked':''} style="width:16px;height:16px;accent-color:var(--grn)">
      Habilitar envío automático de correos
    </label>
    <div style="display:flex;gap:10px">
      <button class="btn btn-primary" onclick="saveSmtp()">💾 Guardar</button>
      <button class="btn btn-ghost" onclick="testSmtp()">📨 Enviar prueba</button>
    </div>
  </div>`;
}

async function saveSmtp() {
  const body={host:id('s-h').value,port:+id('s-p').value,username:id('s-u').value,
    password:id('s-pw').value||'***',from_name:id('s-n').value,
    company:id('s-c').value,enabled:id('s-en').checked};
  const r = await apiPut('/api/config/smtp',body);
  if (r?.updated) toast('Configuración guardada','success');
}
async function testSmtp() {
  toast('Enviando prueba...','info');
  const r = await apiPost('/api/config/smtp/test',{});
  if (r) toast(r.message, r.success?'success':'error');
}

// ─── TAGS ────────────────────────────────────────────────────────────────────
function openTagEditor(agentId, tags) {
  window._etags = [...(Array.isArray(tags)?tags:JSON.parse(tags||'[]'))];
  const render = () => {
    const el = id('tag-list');
    if (el) el.innerHTML = window._etags.map((t,i)=>
      `<span class="tag">${esc(t)} <button onclick="window._etags.splice(${i},1);${render.toString()}()" style="background:none;border:none;cursor:pointer;color:var(--red);font-weight:700">×</button></span>`).join('');
  };
  openModal('🏷 Tags del Equipo', `
  <p class="muted mb16">Clasifica el equipo para búsquedas y filtros rápidos</p>
  <div style="display:flex;gap:8px;margin-bottom:10px">
    <input class="si" id="new-tag" placeholder="Nuevo tag..." style="flex:1"
      onkeydown="if(event.key==='Enter'){const v=this.value.trim().toUpperCase();if(v&&!window._etags.includes(v)){window._etags.push(v);this.value='';document.getElementById('tag-list').innerHTML='x';}event.preventDefault()}"/>
    <button class="btn btn-cyan btn-sm" onclick="const v=id('new-tag').value.trim().toUpperCase();if(v&&!window._etags.includes(v)){window._etags.push(v);id('new-tag').value=''}">+</button>
  </div>
  <div id="tag-list" style="display:flex;flex-wrap:wrap;gap:4px;min-height:32px;margin-bottom:12px"></div>
  <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">
    <span class="muted" style="font-size:11px;width:100%;margin-bottom:4px">Sugeridos:</span>
    ${['LAPTOP','PC','SERVIDOR','FINANZAS','RRHH','TI','PRODUCCION','CRITICO','WINDOWS','LINUX','IMPRESORA','SUCURSAL-1'].map(t=>
      `<span class="tag" style="cursor:pointer" onclick="if(!window._etags.includes('${t}'))window._etags.push('${t}')">${t}</span>`).join('')}
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveTags(${agentId})">Guardar Tags</button>
  </div>`);
  setTimeout(render, 50);
  window._tagRender = render;
}

async function saveTags(agentId) {
  await apiPut(`/api/agents/${agentId}/tags`, {tags: window._etags});
  closeModal(); toast('Tags guardados','success'); loadInventory();
}

// ─── MODAL / TOAST ───────────────────────────────────────────────────────────
function openModal(title, body) {
  id('modal-title').textContent = title;
  id('modal-body').innerHTML    = body;
  id('modal-overlay').classList.add('open');
}
function closeModal() { id('modal-overlay').classList.remove('open'); }

function toast(msg, type = 'info') {
  const icons = {success:'✅',error:'❌',info:'ℹ️',warning:'⚠️'};
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type]||''}</span>${esc(msg)}`;
  id('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
const id  = s => document.getElementById(s);
const qs  = s => document.querySelector(s);
const qsa = s => document.querySelectorAll(s);
const show = s => { const el = id(s); if (el) el.style.display = ''; };

function ago(iso) {
  if (!iso) return '—';
  const d = Date.now() - new Date(iso.endsWith('Z')?iso:iso+'Z').getTime();
  const s = Math.floor(d/1000);
  if (s<60)  return s+'s';
  const m = Math.floor(s/60); if (m<60)  return m+'m';
  const h = Math.floor(m/60); if (h<24)  return h+'h';
  return Math.floor(h/24)+'d';
}
function today() { return new Date().toISOString().split('T')[0]; }
function esc(s)  { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function setBadge(bid, n, warn=false) {
  const el = id(bid);
  if (!el) return;
  if (n > 0) { el.textContent = n; el.style.display = ''; if (warn) el.classList.add('nb-warn'); else el.classList.remove('nb-warn'); }
  else el.style.display = 'none';
}
function dlCSV(rows, fn) {
  const csv = rows.map(r=>r.map(c=>`"${String(c||'').replace(/"/g,'""')}"`).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv'}));
  a.download = fn; a.click();
}
function exportCSV(data, fn, keys) {
  dlCSV([keys, ...data.map(r=>keys.map(k=>r[k]||''))], fn);
}
/* ─────────────────────────────────────────────────────────────────────────
   InfraWatch v2.3 — Frontend Additions (app.js)
   Pegar al FINAL del archivo app.js existente
   ────────────────────────────────────────────────────────────────────────── */

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 1 — SOFTWARE INSTALADO
   Se añade una pestaña "Software" en el panel del agente (loadAgentDetail)
   ═══════════════════════════════════════════════════════════════════════════ */

async function loadAgentSoftware(agentId, containerEl) {
  containerEl.innerHTML = `<div style="padding:24px;color:var(--txt2);font-family:var(--mono);font-size:12px">⏳ Cargando software instalado...</div>`;
  const data = await apiGet(`/api/agents/${agentId}/software`);
  if (!data) { containerEl.innerHTML = `<div style="padding:20px;color:var(--red)">Error cargando software</div>`; return; }

  const sw   = data.software || [];
  const det  = data.detected_at ? new Date(data.detected_at).toLocaleString('es-MX') : '—';

  // Barra de búsqueda local
  let filtered = sw;
  const render = (list) => {
    containerEl.innerHTML = `
    <div style="padding:16px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
        <span style="font-family:var(--mono);font-size:11px;color:var(--txt2)">
          📦 <strong style="color:var(--cyn)">${list.length}</strong> de ${sw.length} paquetes
        </span>
        <span style="font-family:var(--mono);font-size:10px;color:var(--txt3)">Detectado: ${det}</span>
        <input id="sw-search-${agentId}" type="text" placeholder="🔍 Buscar software..."
          style="flex:1;min-width:180px;background:var(--bg3);border:1px solid var(--bdr2);
                 color:var(--txt);padding:5px 10px;border-radius:var(--r);font-family:var(--mono);font-size:11px"
          oninput="filterSoftware(${agentId}, this.value)"/>
        <button class="btn btn-ghost btn-sm"
          onclick="exportCSV(window._swData_${agentId}||[], 'software_${data.hostname}.csv',
                  ['name','version','publisher','install_date'])">
          ↓ CSV
        </button>
      </div>
      <div style="max-height:420px;overflow-y:auto">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="position:sticky;top:0;background:var(--bg2);z-index:1">
              <th class="th" style="text-align:left">Nombre</th>
              <th class="th" style="text-align:left">Versión</th>
              <th class="th" style="text-align:left">Publisher</th>
              <th class="th" style="text-align:left">Instalado</th>
            </tr>
          </thead>
          <tbody>
            ${list.map(s => `
            <tr style="border-bottom:1px solid var(--bdr);transition:background .1s"
                onmouseover="this.style.background='var(--bg3)'"
                onmouseout="this.style.background=''">
              <td style="padding:7px 10px;font-size:12px;color:var(--txt)">${esc(s.name)}</td>
              <td style="padding:7px 10px;font-family:var(--mono);font-size:11px;color:var(--cyn)">${esc(s.version||'—')}</td>
              <td style="padding:7px 10px;font-size:11px;color:var(--txt2)">${esc(s.publisher||'—')}</td>
              <td style="padding:7px 10px;font-family:var(--mono);font-size:10px;color:var(--txt3)">${esc(s.install_date||'—')}</td>
            </tr>`).join('')}
          </tbody>
        </table>
        ${list.length === 0 ? `<div style="padding:24px;text-align:center;color:var(--txt3);font-family:var(--mono);font-size:12px">Sin resultados</div>` : ''}
      </div>
    </div>`;
    // Guardar para exportar
    window[`_swData_${agentId}`] = list;
  };

  window[`filterSoftware`] = (aid, q) => {
    if (aid !== agentId) return;
    const low = q.toLowerCase();
    const f   = q.length < 2 ? sw : sw.filter(s =>
      (s.name||'').toLowerCase().includes(low) ||
      (s.publisher||'').toLowerCase().includes(low));
    render(f);
    setTimeout(() => id(`sw-search-${agentId}`) && (id(`sw-search-${agentId}`).value = q), 0);
  };

  render(sw);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 2 — UMBRALES CONFIGURABLES
   Modal para editar thresholds de un agente
   ═══════════════════════════════════════════════════════════════════════════ */

async function openThresholdModal(agentId, hostname) {
  const t = await apiGet(`/api/agents/${agentId}/thresholds`);
  if (!t) return;

  const row = (label, field, val) => `
    <tr>
      <td style="padding:10px 12px;color:var(--txt2);font-family:var(--mono);font-size:11px">${label}</td>
      <td style="padding:6px 8px">
        <input id="thr-${field}" type="number" min="1" max="99" step="1" value="${val}"
          style="width:70px;background:var(--bg3);border:1px solid var(--bdr2);color:var(--txt);
                 padding:5px 8px;border-radius:var(--r);font-family:var(--mono);font-size:12px;text-align:center"/>
        <span style="color:var(--txt3);font-size:11px">%</span>
      </td>
    </tr>`;

  openModal(`⚙️ Umbrales de alerta — ${esc(hostname)}`, `
    <p style="color:var(--txt2);font-size:12px;margin-bottom:14px">
      Personaliza los límites de alerta para este equipo. El agente enviará alertas cuando supere estos valores.
    </p>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px 12px;color:var(--txt3);font-family:var(--mono);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--bdr)">Métrica</th>
          <th style="text-align:left;padding:8px 12px;color:var(--txt3);font-family:var(--mono);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--bdr)">Valor</th>
        </tr>
      </thead>
      <tbody>
        ${row('⚠️ CPU Aviso',      'cpu_warn',  t.cpu_warn  || 75)}
        ${row('🔴 CPU Crítico',    'cpu_crit',  t.cpu_crit  || 90)}
        ${row('⚠️ RAM Aviso',      'ram_warn',  t.ram_warn  || 80)}
        ${row('🔴 RAM Crítico',    'ram_crit',  t.ram_crit  || 90)}
        ${row('⚠️ Disco Aviso',    'disk_warn', t.disk_warn || 80)}
        ${row('🔴 Disco Crítico',  'disk_crit', t.disk_crit || 90)}
      </tbody>
    </table>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="saveThresholds(${agentId})">💾 Guardar</button>
    </div>
  `);
}

async function saveThresholds(agentId) {
  const fields = ['cpu_warn','cpu_crit','ram_warn','ram_crit','disk_warn','disk_crit'];
  const data   = {};
  for (const f of fields) {
    const el = id(`thr-${f}`);
    if (!el) continue;
    const v = parseFloat(el.value);
    if (isNaN(v) || v < 1 || v > 99) { toast(`Valor inválido en ${f}`, 'error'); return; }
    data[f] = v;
  }
  const r = await apiPut(`/api/agents/${agentId}/thresholds`, data);
  if (r && r.updated) {
    toast('✅ Umbrales guardados', 'success');
    closeModal();
  } else {
    toast('Error guardando umbrales', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 3 — DETALLE DE AGENTE AMPLIADO (reemplaza / extiende loadAgentDetail)
   Añade pestañas: Métricas | Software | Umbrales
   ═══════════════════════════════════════════════════════════════════════════ */

async function openAgentDetailV23(agentId) {
  const a = await apiGet(`/api/agents/${agentId}`);
  if (!a) return;

  const statusColor = a.status === 'online' ? 'var(--grn)' : 'var(--red)';
  const lastSeen    = ago(a.last_seen);
  const asset       = a.asset;

  openModal(`🖥 ${esc(a.hostname)} — Detalle`, `
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <span style="background:var(--bg3);border:1px solid var(--bdr2);padding:4px 12px;
                   border-radius:20px;font-size:11px;font-family:var(--mono);color:${statusColor}">
        ● ${a.status.toUpperCase()}
      </span>
      <span style="background:var(--bg3);border:1px solid var(--bdr2);padding:4px 12px;
                   border-radius:20px;font-size:11px;font-family:var(--mono);color:var(--cyn)">
        ${esc(a.ip_address)}
      </span>
      <span style="background:var(--bg3);border:1px solid var(--bdr2);padding:4px 12px;
                   border-radius:20px;font-size:11px;font-family:var(--mono);color:var(--txt3)">
        ${esc(a.os_name)} ${esc(a.os_version||'').substring(0,20)}
      </span>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto"
        onclick="openThresholdModal(${agentId}, '${esc(a.hostname)}')">
        ⚙️ Umbrales
      </button>
    </div>

    <!-- Pestañas -->
    <div style="display:flex;gap:0;border-bottom:1px solid var(--bdr);margin-bottom:0">
      ${['📊 Métricas','📦 Software','🏷 Tags'].map((t,i) => `
        <button id="atab-${i}" onclick="showAgentTab(${agentId},${i})"
          style="background:${i===0?'var(--bg2)':'transparent'};border:none;
                 border-bottom:${i===0?'2px solid var(--grn)':'2px solid transparent'};
                 padding:10px 18px;color:${i===0?'var(--grn)':'var(--txt2)'};
                 font-family:var(--ui);font-size:12px;font-weight:600;cursor:pointer;
                 transition:all .15s;letter-spacing:.5px">
          ${t}
        </button>`).join('')}
    </div>

    <!-- Contenido pestañas -->
    <div id="atab-content" style="min-height:300px">
      <!-- Se llena dinámicamente -->
    </div>
  `);

  // Mostrar tab 0 por defecto
  showAgentTab(agentId, 0, a);
}

async function showAgentTab(agentId, tabIdx, agentData) {
  // Highlight tab
  [0,1,2].forEach(i => {
    const el = id(`atab-${i}`);
    if (!el) return;
    el.style.background    = i === tabIdx ? 'var(--bg2)' : 'transparent';
    el.style.borderBottom  = i === tabIdx ? '2px solid var(--grn)' : '2px solid transparent';
    el.style.color         = i === tabIdx ? 'var(--grn)' : 'var(--txt2)';
  });

  const cont = id('atab-content');
  if (!cont) return;

  if (tabIdx === 0) {
    // ── Métricas ──────────────────────────────────────────────────────────
    const a = agentData || await apiGet(`/api/agents/${agentId}`);
    const m = a?.metrics || {};
    const uptime = m.uptime_seconds
      ? `${Math.floor(m.uptime_seconds/86400)}d ${Math.floor((m.uptime_seconds%86400)/3600)}h`
      : '—';

    const bar = (v, warn=75, crit=90) => {
      const color = v >= crit ? 'var(--red)' : v >= warn ? 'var(--ylw)' : 'var(--grn)';
      return `<div style="background:var(--bg3);border-radius:3px;height:6px;overflow:hidden;margin-top:4px">
        <div style="background:${color};height:100%;width:${Math.min(v,100)}%;transition:width .4s"></div>
      </div>`;
    };

    cont.innerHTML = `
    <div style="padding:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
      ${[['🔲 CPU', m.cpu_percent,'%'],['💾 RAM', m.ram_percent,'%'],['💽 Disco', m.disk_percent,'%']].map(([lbl,val,unit]) => `
      <div style="background:var(--bg3);border:1px solid var(--bdr);border-radius:var(--r);padding:12px">
        <div style="font-size:10px;color:var(--txt3);font-family:var(--mono);text-transform:uppercase">${lbl}</div>
        <div style="font-size:24px;font-weight:700;color:var(--txt);font-family:var(--mono);margin:4px 0">${val||0}${unit}</div>
        ${bar(val||0)}
      </div>`).join('')}
    </div>
    <div style="padding:0 16px 16px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
      <div class="mini-stat"><span style="color:var(--txt3)">Procesos</span><strong>${m.process_count||0}</strong></div>
      <div class="mini-stat"><span style="color:var(--txt3)">Uptime</span><strong>${uptime}</strong></div>
      <div class="mini-stat"><span style="color:var(--txt3)">Puertos</span><strong>${(a?.metrics?.open_ports||[]).length}</strong></div>
    </div>
    ${a?.asset ? `
    <div style="padding:0 16px;margin-bottom:12px">
      <div style="background:var(--bg3);border:1px solid var(--bdr);border-radius:var(--r);padding:12px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--txt3);margin-bottom:8px">ACTIVO VINCULADO</div>
        <div style="font-size:13px;color:var(--cyn);font-weight:600">${esc(a.asset.asset_code)}</div>
        ${a.asset.personnel_name ? `<div style="font-size:12px;color:var(--txt2);margin-top:4px">👤 ${esc(a.asset.personnel_name)}</div>` : ''}
        <div style="font-family:var(--mono);font-size:11px;color:var(--txt3);margin-top:6px">
          Valor: $${a.asset.depreciation?.current_value?.toLocaleString('es-MX', {minimumFractionDigits:2}) || '0.00'} MXN
        </div>
      </div>
    </div>` : ''}`;

  } else if (tabIdx === 1) {
    // ── Software ──────────────────────────────────────────────────────────
    await loadAgentSoftware(agentId, cont);

  } else if (tabIdx === 2) {
    // ── Tags ──────────────────────────────────────────────────────────────
    const a = agentData || await apiGet(`/api/agents/${agentId}`);
    const tags = a?.tags || [];
    cont.innerHTML = `
    <div style="padding:20px">
      <p style="color:var(--txt2);font-size:12px;margin-bottom:12px">
        Etiquetas para clasificar este equipo en el inventario.
      </p>
      <div id="tag-chips" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px">
        ${tags.map(t => `
          <span style="background:var(--cyn2);border:1px solid rgba(0,212,255,.3);color:var(--cyn);
                       padding:4px 12px;border-radius:20px;font-family:var(--mono);font-size:11px;
                       display:flex;align-items:center;gap:6px">
            ${esc(t)}
            <span style="cursor:pointer;color:var(--txt3)" onclick="removeTagUI(this,'${esc(t)}')">×</span>
          </span>`).join('')}
      </div>
      <div style="display:flex;gap:8px">
        <input id="new-tag-input" type="text" placeholder="Nuevo tag (MAYÚSCULAS)"
          style="flex:1;background:var(--bg3);border:1px solid var(--bdr2);color:var(--txt);
                 padding:8px 12px;border-radius:var(--r);font-family:var(--mono);font-size:12px"
          onkeydown="if(event.key==='Enter') addTagUI(${agentId})"/>
        <button class="btn btn-primary" onclick="addTagUI(${agentId})">+ Agregar</button>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:16px">
        <button class="btn btn-primary" onclick="saveTagsV23(${agentId})">💾 Guardar Tags</button>
      </div>
    </div>`;
    window._currentTags = [...tags];
  }
}

window.removeTagUI = (el, tag) => {
  el.parentElement.remove();
  window._currentTags = (window._currentTags||[]).filter(t => t !== tag);
};
window.addTagUI = (agentId) => {
  const inp = id('new-tag-input');
  if (!inp) return;
  const tag = inp.value.trim().toUpperCase();
  if (!tag) return;
  if ((window._currentTags||[]).includes(tag)) { toast('Tag ya existe', 'warning'); return; }
  window._currentTags = [...(window._currentTags||[]), tag];
  const chips = id('tag-chips');
  if (chips) chips.innerHTML += `
    <span style="background:var(--cyn2);border:1px solid rgba(0,212,255,.3);color:var(--cyn);
                 padding:4px 12px;border-radius:20px;font-family:var(--mono);font-size:11px;
                 display:flex;align-items:center;gap:6px">
      ${esc(tag)}
      <span style="cursor:pointer;color:var(--txt3)" onclick="removeTagUI(this,'${esc(tag)}')">×</span>
    </span>`;
  inp.value = '';
};
async function saveTagsV23(agentId) {
  const r = await apiPut(`/api/agents/${agentId}/tags`, { tags: window._currentTags || [] });
  if (r) { toast('✅ Tags guardados', 'success'); closeModal(); }
  else   { toast('Error guardando tags', 'error'); }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 4 — DISPOSITIVOS SNMP
   Nueva vista: loadSNMP()  →  llamar desde showView('snmp')
   ═══════════════════════════════════════════════════════════════════════════ */

async function loadSNMP() {
  const el = id('view-snmp');
  if (!el) return;
  const devs = await apiGet('/api/snmp') || [];

  const typeIcon = { switch:'🔀', router:'🌐', firewall:'🔥', ups:'⚡', printer:'🖨', other:'📡' };
  const stColor  = { online:'var(--grn)', offline:'var(--red)', unknown:'var(--txt3)' };

  el.innerHTML = `
  <div class="ph">
    <div><h2>🔀 Dispositivos SNMP</h2>
      <p>Switches, routers, firewalls — monitoreo sin agente</p></div>
    <div class="ph-actions">
      ${['admin','it'].includes(currentUser?.role) ? `
      <button class="btn btn-primary" onclick="openSNMPModal()">+ Agregar dispositivo</button>` : ''}
      <button class="btn btn-ghost btn-sm" onclick="loadSNMP()">↻ Actualizar</button>
    </div>
  </div>

  ${devs.length === 0 ? `
  <div style="text-align:center;padding:60px 20px;color:var(--txt3)">
    <div style="font-size:48px;margin-bottom:12px">🔌</div>
    <div style="font-size:16px;margin-bottom:6px">Sin dispositivos SNMP configurados</div>
    <div style="font-size:12px;font-family:var(--mono)">Agrega switches, routers o firewalls para monitorearlos</div>
  </div>` : `
  <div class="grid-cards">
    ${devs.map(d => `
    <div class="card" style="border-left:3px solid ${stColor[d.status]||'var(--txt3)'}">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px">
        <div>
          <div style="font-size:22px">${typeIcon[d.device_type]||'📡'}</div>
          <div style="font-size:14px;font-weight:700;color:var(--txt);margin-top:4px">${esc(d.name)}</div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--cyn)">${esc(d.ip_address)}</div>
        </div>
        <span style="background:${d.status==='online'?'var(--grn2)':'var(--red2)'};
                     color:${stColor[d.status]||'var(--txt3)'};
                     border:1px solid ${stColor[d.status]||'var(--bdr)'};
                     padding:2px 10px;border-radius:20px;font-size:10px;font-family:var(--mono)">
          ● ${d.status.toUpperCase()}
        </span>
      </div>
      ${d.sys_name ? `<div style="font-size:11px;color:var(--txt2);margin-bottom:4px">🏷 ${esc(d.sys_name)}</div>` : ''}
      ${d.sys_descr ? `<div style="font-size:10px;color:var(--txt3);font-family:var(--mono);margin-bottom:8px;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(d.sys_descr)}">
                            ${esc(d.sys_descr.substring(0,80))}</div>` : ''}
      <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--txt3);font-family:var(--mono);margin-bottom:12px">
        ${d.if_count ? `<span>🔌 ${d.if_count} interfaces</span>` : ''}
        ${d.sys_uptime ? `<span>⏱ ${Math.floor(d.sys_uptime/86400)}d uptime</span>` : ''}
        ${d.last_polled ? `<span>🕐 ${ago(d.last_polled)}</span>` : ''}
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="forceSNMPPoll(${d.id},'${esc(d.name)}')">🔄 Poll</button>
        <button class="btn btn-ghost btn-sm" onclick="openSNMPModal(${d.id})">✏️</button>
        <button class="btn btn-danger btn-sm" onclick="deleteSNMP(${d.id},'${esc(d.name)}')">🗑</button>
      </div>
    </div>`).join('')}
  </div>`}`;
}

async function forceSNMPPoll(id_, name) {
  const r = await apiPost(`/api/snmp/${id_}/poll`, {});
  if (r?.error) toast(r.error, 'error');
  else { toast(`🔄 Polling SNMP a ${name}...`, 'info'); setTimeout(loadSNMP, 4000); }
}

async function deleteSNMP(id_, name) {
  if (!confirm(`¿Eliminar ${name}?`)) return;
  const r = await apiDelete(`/api/snmp/${id_}`);
  if (r?.deleted) { toast('Eliminado', 'success'); loadSNMP(); }
}

function openSNMPModal(editId = null) {
  const title = editId ? 'Editar dispositivo SNMP' : '+ Nuevo dispositivo SNMP';
  openModal(title, `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      ${formField('Nombre', 'snmp-name', 'text', 'Core-Switch-01')}
      ${formField('IP', 'snmp-ip', 'text', '192.168.1.1')}
      <div class="form-group">
        <label>Tipo de dispositivo</label>
        <select id="snmp-type" class="form-input">
          ${['switch','router','firewall','ups','printer','other'].map(t =>
            `<option value="${t}">${{switch:'🔀 Switch',router:'🌐 Router',firewall:'🔥 Firewall',
              ups:'⚡ UPS',printer:'🖨 Impresora',other:'📡 Otro'}[t]}</option>`).join('')}
        </select>
      </div>
      ${formField('Community', 'snmp-community', 'text', 'public')}
      <div class="form-group">
        <label>Versión SNMP</label>
        <select id="snmp-version" class="form-input">
          <option value="2c">v2c (recomendado)</option>
          <option value="1">v1</option>
          <option value="3">v3</option>
        </select>
      </div>
      ${formField('Puerto', 'snmp-port', 'number', '161')}
    </div>
    ${formField('Ubicación', 'snmp-location', 'text', 'Rack-01, Piso 2')}
    ${formField('Notas', 'snmp-notes', 'text', '')}
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="saveSNMP(${editId || 'null'})">💾 Guardar</button>
    </div>
  `);
}

async function saveSNMP(editId) {
  const val = (x) => (id(x)?.value || '').trim();
  const data = {
    name: val('snmp-name'), ip_address: val('snmp-ip'),
    device_type: val('snmp-type'), community: val('snmp-community') || 'public',
    snmp_version: val('snmp-version') || '2c',
    port: parseInt(val('snmp-port')) || 161,
    location: val('snmp-location'), notes: val('snmp-notes'),
  };
  if (!data.name || !data.ip_address) { toast('Nombre e IP son requeridos', 'error'); return; }
  const r = editId
    ? await apiPut(`/api/snmp/${editId}`, data)
    : await apiPost('/api/snmp', data);
  if (r?.id || r?.updated) { toast('✅ Guardado', 'success'); closeModal(); loadSNMP(); }
  else toast('Error guardando', 'error');
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 5 — DISPOSITIVOS PING
   Nueva vista: loadPingDevices()  →  llamar desde showView('ping-devices')
   ═══════════════════════════════════════════════════════════════════════════ */

async function loadPingDevices() {
  const el = id('view-ping-devices');
  if (!el) return;
  const devs = await apiGet('/api/ping-devices') || [];

  const typeIcon = {
    printer:'🖨', camera:'📷', ap:'📶', tv:'📺',
    monitor:'🖥', phone:'📱', other:'📡'
  };
  const stColor = { online:'var(--grn)', offline:'var(--red)', unknown:'var(--txt3)' };

  el.innerHTML = `
  <div class="ph">
    <div><h2>📡 Dispositivos Ping</h2>
      <p>Impresoras, cámaras, APs, pantallas — solo ping ICMP</p></div>
    <div class="ph-actions">
      <button class="btn btn-primary" onclick="openPingModal()">+ Agregar</button>
      <button class="btn btn-ghost btn-sm" onclick="scanAllPing()">🔄 Escanear todos</button>
      <button class="btn btn-ghost btn-sm" onclick="loadPingDevices()">↻ Actualizar</button>
    </div>
  </div>

  <!-- Resumen rápido -->
  <div class="sg" style="margin-bottom:20px">
    ${[
      ['Total', devs.length, 'registrados', 'var(--cyn)'],
      ['Online', devs.filter(d=>d.status==='online').length, 'activos', 'var(--grn)'],
      ['Offline', devs.filter(d=>d.status==='offline').length, 'sin respuesta', 'var(--red)'],
      ['Desconocido', devs.filter(d=>d.status==='unknown').length, 'sin poll', 'var(--txt3)'],
    ].map(([l,v,s,c]) => `
    <div class="sc"><div class="sc-lbl">${l}</div>
      <div class="sc-val" style="color:${c}">${v}</div>
      <div class="sc-sub">${s}</div></div>`).join('')}
  </div>

  ${devs.length === 0 ? `
  <div style="text-align:center;padding:60px;color:var(--txt3)">
    <div style="font-size:48px;margin-bottom:12px">📡</div>
    <div>Sin dispositivos ping configurados</div>
  </div>` : `
  <div style="overflow-x:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>Dispositivo</th>
          <th>IP</th>
          <th>Estado</th>
          <th>RTT</th>
          <th>Último ping</th>
          <th>Fallos</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        ${devs.map(d => `
        <tr>
          <td>
            <span style="font-size:18px">${typeIcon[d.device_type]||'📡'}</span>
            <span style="margin-left:8px;font-weight:600">${esc(d.name)}</span>
            ${d.location ? `<span style="font-size:10px;color:var(--txt3);font-family:var(--mono);margin-left:6px">${esc(d.location)}</span>` : ''}
          </td>
          <td><code style="font-family:var(--mono);color:var(--cyn)">${esc(d.ip_address)}</code></td>
          <td>
            <span style="background:${d.status==='online'?'var(--grn2)':d.status==='offline'?'var(--red2)':'var(--bg3)'};
                         color:${stColor[d.status]};border:1px solid ${stColor[d.status]};
                         padding:2px 10px;border-radius:20px;font-size:10px;font-family:var(--mono)">
              ● ${d.status.toUpperCase()}
            </span>
          </td>
          <td style="font-family:var(--mono);font-size:11px;color:var(--txt2)">
            ${d.response_time_ms != null ? `${d.response_time_ms.toFixed(1)} ms` : '—'}
          </td>
          <td style="font-family:var(--mono);font-size:11px;color:var(--txt3)">${ago(d.last_ping)}</td>
          <td style="font-family:var(--mono);font-size:11px;color:${d.consecutive_failures>2?'var(--red)':'var(--txt3)'}">
            ${d.consecutive_failures || 0}
          </td>
          <td>
            <div style="display:flex;gap:6px">
              <button class="btn btn-ghost btn-sm" onclick="openPingModal(${d.id})">✏️</button>
              <button class="btn btn-danger btn-sm" onclick="deletePingDevice(${d.id},'${esc(d.name)}')">🗑</button>
            </div>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>`}`;
}

async function scanAllPing() {
  const r = await apiPost('/api/ping-devices/scan-all', {});
  if (r) {
    toast(`🔄 Escaneando ${r.scanning} dispositivos...`, 'info');
    setTimeout(loadPingDevices, 5000);
  }
}

function openPingModal(editId = null) {
  openModal(editId ? 'Editar dispositivo' : '+ Nuevo dispositivo Ping', `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      ${formField('Nombre', 'ping-name', 'text', 'Impresora HP Piso 2')}
      ${formField('IP', 'ping-ip', 'text', '192.168.1.50')}
      <div class="form-group">
        <label>Tipo</label>
        <select id="ping-type" class="form-input">
          ${['printer','camera','ap','tv','monitor','phone','other'].map(t =>
            `<option value="${t}">${{printer:'🖨 Impresora',camera:'📷 Cámara',ap:'📶 Access Point',
              tv:'📺 TV/Pantalla',monitor:'🖥 Monitor',phone:'📱 Teléfono/PDA',other:'📡 Otro'}[t]}</option>`
          ).join('')}
        </select>
      </div>
      ${formField('Ubicación', 'ping-location', 'text', 'Piso 2, Sala de juntas')}
    </div>
    ${formField('Notas', 'ping-notes', 'text', '')}
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="savePingDevice(${editId || 'null'})">💾 Guardar</button>
    </div>
  `);
}

async function savePingDevice(editId) {
  const val = (x) => (id(x)?.value || '').trim();
  const data = {
    name: val('ping-name'), ip_address: val('ping-ip'),
    device_type: val('ping-type'), location: val('ping-location'),
    notes: val('ping-notes'),
  };
  if (!data.name || !data.ip_address) { toast('Nombre e IP son requeridos', 'error'); return; }
  const r = editId
    ? await apiPut(`/api-ping-devices/${editId}`, data)
    : await apiPost('/api/ping-devices', data);
  if (r?.id || r?.updated) { toast('✅ Guardado', 'success'); closeModal(); loadPingDevices(); }
  else toast('Error guardando', 'error');
}

async function deletePingDevice(id_, name) {
  if (!confirm(`¿Eliminar ${name}?`)) return;
  const r = await apiDelete(`/api/ping-devices/${id_}`);
  if (r?.deleted) { toast('Eliminado', 'success'); loadPingDevices(); }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 6 — HELPER para inputs de formulario (reutilizable)
   ═══════════════════════════════════════════════════════════════════════════ */

function formField(label, elId, type = 'text', placeholder = '') {
  return `
  <div class="form-group">
    <label>${label}</label>
    <input id="${elId}" type="${type}" placeholder="${placeholder}"
      class="form-input" style="font-family:var(--mono);font-size:12px"/>
  </div>`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 7 — CSS extra (inyectar al DOM)
   ═══════════════════════════════════════════════════════════════════════════ */

(function injectV23Styles() {
  const style = document.createElement('style');
  style.textContent = `
    .form-input {
      width: 100%;
      background: var(--bg3);
      border: 1px solid var(--bdr2);
      color: var(--txt);
      padding: 8px 12px;
      border-radius: var(--r);
      font-size: 13px;
      font-family: var(--ui);
      transition: border-color .2s;
    }
    .form-input:focus {
      outline: none;
      border-color: var(--grn);
      box-shadow: 0 0 0 2px rgba(0,200,100,.1);
    }
    .grid-cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 14px;
    }
    .card {
      background: var(--bg2);
      border: 1px solid var(--bdr);
      border-radius: var(--rl);
      padding: 16px;
      transition: border-color .2s;
    }
    .card:hover { border-color: var(--bdr2); }
    .mini-stat {
      background: var(--bg3);
      border: 1px solid var(--bdr);
      border-radius: var(--r);
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      font-family: var(--mono);
    }
    .mini-stat strong { color: var(--txt); }
    .data-table {
      width: 100%;
      border-collapse: collapse;
    }
    .data-table th {
      background: var(--bg2);
      color: var(--txt3);
      font-family: var(--mono);
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--bdr);
      text-align: left;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .data-table td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--bdr);
      color: var(--txt2);
      font-size: 12px;
    }
    .data-table tr:hover td { background: var(--bg3); }
    .th {
      background: var(--bg2);
      color: var(--txt3);
      font-family: var(--mono);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 1px;
      padding: 8px 10px;
      border-bottom: 1px solid var(--bdr);
    }
    .btn-sm { padding: 5px 10px !important; font-size: 11px !important; }
  `;
  document.head.appendChild(style);
})();

/* ═══════════════════════════════════════════════════════════════════════════
   SECCIÓN 8 — REGISTRAR NUEVAS VISTAS EN showView
   Agregar en el mapa de vistas del showView() existente:
       snmp:        loadSNMP,
       'ping-devices': loadPingDevices,
   ═══════════════════════════════════════════════════════════════════════════ */

// Parchar showView para incluir las nuevas vistas
const _origShowView = typeof showView === 'function' ? showView : null;
window.showView = function(view) {
  // Crear divs de vista si no existen
  if (!id(`view-${view}`)) {
    const main = document.querySelector('.main-content');
    if (main) {
      const div = document.createElement('div');
      div.id        = `view-${view}`;
      div.className = 'view';
      main.appendChild(div);
    }
  }
  if (_origShowView) _origShowView(view);
  // Cargar vistas nuevas
  if (view === 'snmp')         loadSNMP();
  if (view === 'ping-devices') loadPingDevices();
};

log && log('✅ InfraWatch v2.3 frontend cargado — software, SNMP, ping, umbrales');
