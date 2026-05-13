/* ═══════════════════════════════════════════════════════════════════════
   KOBİ AI — application logic
   Preserves all original backend endpoints:
     /health, /api/chat, /api/history, /api/session/:id/messages, /api/rerun
   Adds optional best-effort hits to:
     /api/auth/login, /api/auth/logout, /api/customer/chat
   ─────────────────────────────────────────────────────────────────────── */

const API = '';

let CLIENT_ID = localStorage.getItem('kobi_client_id');
if (!CLIENT_ID) {
  CLIENT_ID = 'client_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('kobi_client_id', CLIENT_ID);
}

let SESSION_ID         = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
let isLoading          = false;
let analyticalMode     = false;
let pendingSuggestions = null;
let chartInstances     = {};
let msgCount           = 0;
let currentRole        = 'admin';
let currentTab         = 'overview';

/* ─── View routing ─────────────────────────────────────────────────────── */
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(name + 'View').classList.add('active');
  if (name === 'dashboard') {
    initDashboardOnce();
    checkHealth();
    loadSessionHistory();
  }
}
function showLanding() { showView('landing'); }

function openLogin() {
  const m = document.getElementById('loginModal');
  m.classList.remove('hidden'); m.classList.add('flex');
}
function closeLogin() {
  const m = document.getElementById('loginModal');
  m.classList.add('hidden'); m.classList.remove('flex');
}

function setRole(r) {
  currentRole = r;
  const a = document.getElementById('roleAdmin'), c = document.getElementById('roleCustomer');
  if (r === 'admin') {
    a.style.background = 'var(--ink)'; a.style.color = 'white'; a.classList.remove('text-[var(--text-2)]');
    c.style.background = 'transparent'; c.style.color = ''; c.classList.add('text-[var(--text-2)]');
  } else {
    c.style.background = 'var(--ink)'; c.style.color = 'white'; c.classList.remove('text-[var(--text-2)]');
    a.style.background = 'transparent'; a.style.color = ''; a.classList.add('text-[var(--text-2)]');
  }
}

function handleLogin(e) {
  e && e.preventDefault();
  const isAdmin = currentRole === 'admin';
  document.getElementById('userEmail').textContent = isAdmin ? 'yonetici@kobi.ai' : 'musteri@kobi.ai';
  document.getElementById('userName').textContent  = isAdmin ? 'Yönetici' : 'Müşteri';
  document.getElementById('greetingName').textContent = isAdmin ? 'Yönetici' : 'Müşteri';
  closeLogin();
  showView(isAdmin ? 'dashboard' : 'customer');
}
function enterAsCustomer() { currentRole = 'customer'; handleLogin(); }
function enterAsAdmin()    { currentRole = 'admin';    handleLogin(); }
function enterDemo()       { enterAsCustomer(); }
function logout() {
  localStorage.removeItem('kobi_token');
  dashInited = false;
  analyticsRendered = false;
  overviewRendered = false;
  showView('landing');
}

/* ─── Tab switching ────────────────────────────────────────────────────── */
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  const panel = document.getElementById('tab-' + tab);
  panel.classList.remove('hidden');
  // chat tab needs flex
  if (tab === 'chat') panel.classList.add('flex');
  if (tab === 'comms') panel.classList.add('flex');

  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  const titles = {
    overview:'Genel Bakış', comms:'Müşteri Mesajları', orders:'Siparişler',
    cargo:'Kargo', stock:'Stok', tasks:'Görev Akışları', analytics:'Analitik & İçgörü',
    chat:'AI Chat'
  };
  document.getElementById('headerTitle').textContent = titles[tab];

  if (tab === 'analytics') renderAnalyticsCharts();
  if (tab === 'overview')  renderOverviewCharts();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
}

function toggleAnalytical() {
  analyticalMode = !analyticalMode;
  const lbl = document.getElementById('analyticalLabel');
  lbl.textContent = analyticalMode ? 'Açık' : 'Kapalı';
  lbl.style.color = analyticalMode ? 'var(--success)' : '';
}

/* ─── Dashboard init ───────────────────────────────────────────────────── */
let dashInited = false;
async function initDashboardOnce() {
  if (dashInited) return;
  dashInited = true;
  // Gerçek API'den veri çek
  await fillSummaryKPIs();
  await fillOrderTabCounts();
  await fillOrders();
  await fillCargo();
  await fillStock();
  await fillTopProducts();
  await fillForecast();
  await fillTasksByAssignee();
  fillConversations();        // mock — müşteri mesajları
  fillOverviewComms();
  await fillOverviewTasks();
  renderOverviewCharts();
  setInterval(async () => {
    const el = document.getElementById('liveUpdated');
    if (el) el.textContent = 'şimdi';
    await fillSummaryKPIs();  // KPI'ları periyodik güncelle
  }, 30000);
}

async function fillOrderTabCounts() {
  try {
    const durumlar = [
      {id:'tabCountAll',    durum:''},
      {id:'tabCountPending',durum:'Hazırlanıyor'},
      {id:'tabCountCargo',  durum:'Kargoya Verildi'},
      {id:'tabCountDone',   durum:'Teslim Edildi'},
      {id:'tabCountCancel', durum:'İptal'},
    ];
    await Promise.all(durumlar.map(async ({id, durum}) => {
      const url = API + '/api/orders?limit=1' + (durum ? '&durum=' + encodeURIComponent(durum) : '');
      const r = await fetch(url);
      if (!r.ok) return;
      const d = await r.json();
      setText(id, d.total ?? '—');
    }));
  } catch(e) {}
}

/* ─── KPI Özet ──────────────────────────────────────────────────────────── */
async function fillSummaryKPIs() {
  try {
    const r = await fetch(API + '/api/dashboard/summary');
    if (!r.ok) return;
    const d = await r.json();
    setText('kpiOrders',   d.bugun_siparis     ?? '—');
    setText('kpiCargo',    d.kargodaki         ?? '—');
    setText('kpiDelayed',  d.geciken_kargo      ?? '—');
    setText('kpiStock',    d.kritik_stok_urun  ?? '—');
    setText('kpiCiro',     d.bugun_ciro ? '₺' + d.bugun_ciro.toLocaleString('tr-TR', {maximumFractionDigits:0}) : '—');
    // Sipariş sayfası tile'ları
    setText('ordKpiToday',    d.bugun_siparis   ?? '—');
    setText('ordKpiWeek',     d.hafta_siparis   ?? '—');
    setText('ordKpiBekleyen', d.bekleyen_siparis ?? '—');
    setText('ordKpiTeslim',   d.teslim_30gun    ?? '—');
    if (d.today) setText('ordKpiDate', d.today);
    // Sidebar nav counts
    setText('navCountOrders', d.bugun_siparis   ?? '—');
    setText('navCountCargo',  d.geciken_kargo   ?? '—');
    setText('navCountStock',  d.kritik_stok_urun ?? '—');
    // Ticker
    const tv = { tickerOrders: d.bugun_siparis ?? '—', tickerOrders2: d.bugun_siparis ?? '—',
                 tickerStock: d.kritik_stok_urun ?? '—', tickerStock2: d.kritik_stok_urun ?? '—',
                 tickerCargo: d.geciken_kargo ?? '—', tickerCargo2: d.geciken_kargo ?? '—' };
    Object.entries(tv).forEach(([id, v]) => setText(id, v));

    // Sabah Briflemesi — veriden üret
    const briefEl = document.getElementById('morningBriefText');
    if (briefEl) {
      const siparis  = d.bugun_siparis   || 0;
      const geciken  = d.geciken_kargo   || 0;
      const kritik   = d.kritik_stok_urun || 0;
      const bekleyen = d.bekleyen_siparis || 0;
      const tarih    = d.today ? new Date(d.today).toLocaleDateString('tr-TR', {day:'numeric', month:'long'}) : 'bugün';
      let brief = `${tarih} itibarıyla <strong class="neon-text">${siparis} sipariş</strong> sisteme alındı.`;
      if (bekleyen > 0) brief += ` <strong class="neon-text">${bekleyen} sipariş</strong> hazırlanma aşamasında.`;
      if (geciken > 0) brief += ` <strong style="color:var(--warn)">${geciken} kargo</strong> gecikiyor — müşteri bildirimi için kargo sayfasını kontrol et.`;
      if (kritik > 0) brief += ` <strong style="color:var(--lime)">${kritik} ürün</strong> kritik stok seviyesine düştü; tedarikçiye taslak mail hazırlanabilir.`;
      briefEl.innerHTML = brief;
    }
    const briefTime = document.getElementById('morningBriefTime');
    if (briefTime) {
      const now = new Date();
      briefTime.textContent = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0') + ' · Güncel';
    }
  } catch(e) {}
}
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }

/* ─── Mock data ────────────────────────────────────────────────────────── */
const fakeOrders = [
  ['#SP-23914', 'Ayşe Yılmaz',   'Trendyol',    '₺1.249,00', 'success', 'Teslim Edildi', '13 May 11:24'],
  ['#SP-23913', 'Mehmet Koç',    'HepsiBurada', '₺874,50',   'orange',  'Kargoda',       '13 May 10:58'],
  ['#SP-23912', 'Zeynep Demir',  'N11',         '₺2.180,00', 'warn',    'Hazırlanıyor',  '13 May 10:42'],
  ['#SP-23911', 'Ali Şahin',     'Trendyol',    '₺459,00',   'orange',  'Kargoda',       '13 May 10:31'],
  ['#SP-23910', 'Fatma Aktaş',   'CSP',         '₺3.420,00', 'success', 'Teslim Edildi', '13 May 09:55'],
  ['#SP-23909', 'Burak Yıldız',  'Trendyol',    '₺189,90',   'danger',  'İptal',         '13 May 09:20'],
  ['#SP-23908', 'Selin Polat',   'HepsiBurada', '₺1.876,00', 'warn',    'Hazırlanıyor',  '13 May 08:48'],
  ['#SP-23907', 'Emre Doğan',    'Trendyol',    '₺612,30',   'success', 'Teslim Edildi', '13 May 08:12'],
  ['#SP-23906', 'Pelin Acar',    'Amazon',      '₺945,00',   'orange',  'Kargoda',       '13 May 07:55'],
];
let _currentOrderDurum = null;
async function fillOrders(durum) {
  _currentOrderDurum = durum || null;
  // Tab aktif/pasif görünümü güncelle
  document.querySelectorAll('.order-filter-tab').forEach(b => {
    const d = b.dataset.durum || '';
    const active = (!durum && !d) || d === (durum || '');
    b.classList.toggle('active', active);
    b.style.borderBottomColor = active ? 'var(--primary)' : 'transparent';
    b.style.color = active ? 'var(--ink)' : '';
    b.style.fontWeight = active ? '600' : '';
  });
  const body = document.getElementById('ordersBody');
  if (!body) return;
  body.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-[var(--text-3)]">Yükleniyor…</td></tr>';
  try {
    let url = API + '/api/orders?limit=50';
    if (durum) url += '&durum=' + encodeURIComponent(durum);
    const r = await fetch(url);
    if (!r.ok) throw new Error();
    const d = await r.json();
    const orders = d.orders || [];
    if (!orders.length) { body.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-[var(--text-3)]">Sipariş bulunamadı</td></tr>'; return; }
    const durumBadge = (s) => {
      if (!s) return 'badge-warn';
      if (s.includes('Teslim')) return 'badge-success';
      if (s.includes('Kargo')) return 'badge-orange';
      if (s.includes('İptal')) return 'badge-danger';
      return 'badge-warn';
    };
    body.innerHTML = orders.map(o => `
      <tr class="cursor-pointer hover:bg-[var(--bg-2)] transition" onclick="openOrderDetail('${escHtml(o.sip_no||'')}')">
        <td class="mono font-medium text-[var(--ink)]">${escHtml(o.sip_no || '—')}</td>
        <td>${escHtml(o.musteri || '—')}</td>
        <td><span class="text-[var(--text-2)]">${escHtml(o.kanal || '—')}</span></td>
        <td class="font-semibold text-[var(--ink)]">₺${(o.tutar||0).toLocaleString('tr-TR',{maximumFractionDigits:2})}</td>
        <td><span class="badge ${durumBadge(o.sip_durum)}"><span class="badge-dot" style="background:currentColor"></span>${escHtml(o.sip_durum||'—')}</span></td>
        <td class="text-[var(--text-3)] mono text-xs">${(o.sip_tarih||'').slice(0,10)}</td>
        <td class="text-right"><button class="text-[var(--text-3)] hover:text-[var(--ink)] p-1"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg></button></td>
      </tr>`).join('');
  } catch(e) { body.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-[var(--danger)]">Veri yüklenemedi</td></tr>'; }
}

function openOrderDetail(sipNo) {
  if (!sipNo) return;
  const modal = document.getElementById('orderDetailModal');
  if (!modal) return;
  document.getElementById('orderDetailNo').textContent = sipNo;
  fetch(API + '/api/orders?limit=200').then(r=>r.json()).then(d=>{
    const o = (d.orders||[]).find(x=>x.sip_no===sipNo);
    if (!o) return;
    const el = document.getElementById('orderDetailBody');
    if (el) el.innerHTML = `
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div><span class="text-[var(--text-3)]">Müşteri</span><div class="font-semibold mt-1">${escHtml(o.musteri||'—')}</div></div>
        <div><span class="text-[var(--text-3)]">Kanal</span><div class="font-semibold mt-1">${escHtml(o.kanal||'—')}</div></div>
        <div><span class="text-[var(--text-3)]">Durum</span><div class="font-semibold mt-1">${escHtml(o.sip_durum||'—')}</div></div>
        <div><span class="text-[var(--text-3)]">Tutar</span><div class="font-semibold mt-1">₺${(o.tutar||0).toLocaleString('tr-TR',{maximumFractionDigits:2})}</div></div>
        <div><span class="text-[var(--text-3)]">Kargo Firma</span><div class="font-semibold mt-1">${escHtml(o.kargo_firma||'—')}</div></div>
        <div><span class="text-[var(--text-3)]">Takip No</span><div class="font-semibold mt-1 mono">${escHtml(o.kargo_takip_no||'—')}</div></div>
        <div><span class="text-[var(--text-3)]">Tarih</span><div class="font-semibold mt-1">${(o.sip_tarih||'').slice(0,10)}</div></div>
        <div><span class="text-[var(--text-3)]">Kargo Durum</span><div class="font-semibold mt-1">${escHtml(o.kargo_durum||'—')}</div></div>
      </div>`;
  }).catch(()=>{});
  modal.classList.remove('hidden'); modal.classList.add('flex');
}
function closeOrderDetail() {
  const modal = document.getElementById('orderDetailModal');
  if (modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }
}

function filterOrders(durum) { fillOrders(durum || null); }

function searchOrders() {
  const q = (document.getElementById('orderSearch')?.value || '').toLowerCase().trim();
  if (!q) { fillOrders(_currentOrderDurum); return; }
  const rows = document.querySelectorAll('#ordersBody tr');
  rows.forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function exportOrders() {
  const rows = [['Sipariş No','Müşteri','Kanal','Tutar','Durum','Tarih']];
  document.querySelectorAll('#ordersBody tr').forEach(tr => {
    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
    if (cells.length >= 6) rows.push(cells.slice(0,6));
  });
  const csv = rows.map(r => r.map(c => '"' + c.replace(/"/g,'""') + '"').join(',')).join('\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,﻿' + encodeURIComponent(csv);
  a.download = 'siparisler_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}

const fakeCargo = [
  { id:'#KRG-9821', customer:'Mert Aydın',   product:'Kadın Pijama Takımı M/L (2 adet)',  carrier:'Aras Kargo',    delayed:true,  steps:[1,1,1,0], lastUpdate:'11 May · 14:30', hours:54 },
  { id:'#KRG-9820', customer:'Deniz Çelik',  product:'Oversize Kapüşonlu Sweat XL',       carrier:'Yurtiçi Kargo', delayed:true,  steps:[1,1,0,0], lastUpdate:'10 May · 17:12', hours:68 },
  { id:'#KRG-9819', customer:'Selma Arslan', product:'Erkek Slim Fit Gömlek (3 renk)',     carrier:'MNG Kargo',     delayed:true,  steps:[1,1,1,0], lastUpdate:'11 May · 09:55', hours:50 },
  { id:'#KRG-9818', customer:'Cem Erdem',    product:'Kadın Yüksek Bel Tayt S',           carrier:'Aras Kargo',    delayed:false, steps:[1,1,1,1], lastUpdate:'13 May · 11:02', hours:1  },
  { id:'#KRG-9817', customer:'Tuba Yıldız',  product:'Unisex Basic Tişört (2 adet)',       carrier:'Yurtiçi Kargo', delayed:false, steps:[1,1,1,0], lastUpdate:'13 May · 09:14', hours:5  },
];
async function fillCargo(durum) {
  const list = document.getElementById('cargoList');
  if (!list) return;
  list.innerHTML = '<div class="text-center py-8 text-[var(--text-3)]">Yükleniyor…</div>';
  try {
    let url = API + '/api/cargo?limit=30';
    if (durum) url += '&durum=' + encodeURIComponent(durum);
    const r = await fetch(url);
    if (!r.ok) throw new Error();
    const d = await r.json();
    const items = d.items || [];
    const total = d.total || 0;

    // Kargo summary güncelle
    const delayedCount = items.filter(c => c.kargo_gecikme_flag === 1).length;
    const cargoAlert = document.getElementById('cargoAlert');
    const cargoAlertText = document.getElementById('cargoAlertText');
    if (cargoAlert) cargoAlert.classList.toggle('hidden', delayedCount === 0);
    if (cargoAlertText) cargoAlertText.textContent = `${delayedCount} kargo gecikmiş durumda`;

    if (!items.length) { list.innerHTML = '<div class="text-center py-8 text-[var(--text-3)]">Aktif kargo kaydı bulunamadı</div>'; return; }
    const stepLabels = ['Hazırlandı','Kargoya verildi','Yolda','Teslim edildi'];
    list.innerHTML = items.map(c => {
      const delayed = c.kargo_gecikme_flag === 1;
      const dur     = c.kargo_durum || '';
      // Adım hesabı: Hazırlanıyor=1, Kargoda/Gecikti=2, Yolda=3, Teslim=4
      const stepIdx = dur === 'Teslim Edildi' ? 4 : dur === 'Kargoda' ? 2 : dur === 'Gecikti' ? 2 : dur === 'Hazırlanıyor' ? 1 : 1;
      const steps   = [1, stepIdx>=2?1:0, stepIdx>=3?1:0, stepIdx>=4?1:0];
      const stepHtml = steps.map((done, i) => {
        const isActive = done && (i === steps.length-1 || !steps[i+1]);
        const cls = delayed && done ? 'step-done' : done ? (isActive ? 'step-active' : 'step-done') : 'step-pending';
        const icon = done ? '<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>' : (i+1);
        const lineColor = done && steps[i+1] ? 'var(--ink)' : 'var(--line)';
        return `<div class="flex-1 flex items-center gap-2">
          <div class="step-dot ${cls}">${icon}</div>
          <div class="text-[11px] ${done ? 'font-medium text-[var(--ink)]' : 'text-[var(--text-3)]'}">${stepLabels[i]}</div>
          ${i < 3 ? `<div class="flex-1 h-px" style="background:${lineColor}"></div>` : ''}
        </div>`;
      }).join('');
      const bildirildi = c.kargo_musteri_bilgilendirildi === 1;
      return `<div class="surface p-5" ${delayed ? 'style="border-color:rgba(255,90,31,0.35);box-shadow:0 0 0 1px rgba(255,90,31,0.15)"' : ''}>
        <div class="flex items-start justify-between mb-4 flex-wrap gap-3">
          <div>
            <div class="flex items-center gap-2 mb-1 flex-wrap">
              <span class="mono text-sm font-semibold text-[var(--ink)]">#KRG-${c.kargo_id||'—'}</span>
              ${delayed ? '<span class="badge badge-danger"><span class="badge-dot bg-red-500"></span>GECİKMİŞ</span>' : dur === 'Kargoda' ? '<span class="badge badge-orange"><span class="badge-dot" style="background:var(--warn)"></span>KARGODA</span>' : '<span class="badge badge-success"><span class="badge-dot" style="background:var(--success)"></span>YOLUNDA</span>'}
              ${bildirildi ? '<span class="badge badge-success" style="font-size:10px">✓ BİLDİRİLDİ</span>' : ''}
            </div>
            <div class="text-sm text-[var(--ink)] font-medium">Sipariş: ${escHtml(c.kargo_sip_no||'—')}</div>
            <div class="text-xs text-[var(--text-2)] mt-0.5">${escHtml(c.musteri||'Müşteri')} · ${escHtml(c.kargo_firma||'—')} · Beklenen: ${(c.kargo_beklenen_teslim||'').slice(0,10)}</div>
          </div>
          ${delayed && !bildirildi
            ? `<button onclick="notifyCargoCustomer(${c.kargo_id}, this)" class="btn-neon text-xs py-2 px-3 flex items-center gap-1.5"><svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>Müşteriyi Bilgilendir</button>`
            : `<button onclick="alert('Sipariş: ${escHtml(c.kargo_sip_no||'')}\\nTakip: ${escHtml(c.kargo_takip_no||'')}\\nFirma: ${escHtml(c.kargo_firma||'')}\\nDurum: ${escHtml(dur)}')" class="btn-ghost text-xs py-2 px-3">Detay</button>`}
        </div>
        <div class="flex items-center gap-1">${stepHtml}</div>
      </div>`;
    }).join('');
  } catch(e) { list.innerHTML = '<div class="text-center py-8 text-[var(--danger)]">Veri yüklenemedi</div>'; }
}

async function notifyCargoCustomer(cargoId, btn) {
  btn.disabled = true; btn.textContent = 'Gönderiliyor…';
  try {
    const r = await fetch(API + '/api/cargo/' + cargoId + '/notify', {method:'POST'});
    const d = await r.json();
    btn.textContent = '✓ Gönderildi';
    btn.className = 'btn-ghost text-xs py-2 px-3';
    showToast(d.message || 'Müşteri bilgilendirildi', 'success');
  } catch(e) { btn.disabled = false; btn.textContent = 'Müşteriyi Bilgilendir'; }
}

async function notifyAllDelayed() {
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.textContent = 'Gönderiliyor…'; }
  try {
    const r = await fetch(API + '/api/cargo/notify-all', {method:'POST'});
    const d = await r.json();
    showToast(d.message, 'success');
    await fillCargo();
  } catch(e) { showToast('Hata oluştu', 'error'); }
  if (btn) { btn.disabled = false; btn.textContent = 'Tümüne Bildirim Gönder'; }
}

const fakeStock = [
  { name:'Kadın Pijama Takımı M',   sku:'STK-PJM-014', current:12,  min:50,  unit:'ad', level:'crit' },
  { name:'Erkek Slim Fit Gömlek L', sku:'STK-GMK-027', current:18,  min:40,  unit:'ad', level:'crit' },
  { name:'Kadın Yüksek Bel Tayt',   sku:'STK-TYT-033', current:24,  min:60,  unit:'ad', level:'crit' },
  { name:'Unisex Kapüşonlu Sweat',  sku:'STK-SWT-019', current:38,  min:60,  unit:'ad', level:'warn' },
  { name:'Kadın Triko Kazak',       sku:'STK-KZK-041', current:41,  min:50,  unit:'ad', level:'warn' },
  { name:'Erkek Chino Pantolon',    sku:'STK-PNT-052', current:67,  min:80,  unit:'ad', level:'warn' },
  { name:'Kadın Oversize Tişört',   sku:'STK-TST-008', current:184, min:100, unit:'ad', level:'ok'   },
];
async function fillStock() {
  const el = document.getElementById('stockList');
  if (!el) return;
  el.innerHTML = '<div class="text-center py-8 text-[var(--text-3)]">Yükleniyor…</div>';
  // Fetch stock stats for tile counts
  try {
    const sr = await fetch(API + '/api/stock/stats');
    if (sr.ok) {
      const s = await sr.json();
      setText('stockKritik',   s.kritik   ?? '—');
      setText('stockDusuk',    s.dusuk    ?? '—');
      setText('stockSaglikli', s.saglikli ?? '—');
    }
  } catch(e) {}
  try {
    const r = await fetch(API + '/api/stock/critical');
    if (!r.ok) throw new Error();
    const d = await r.json();
    const items = d.items || [];
    if (!items.length) {
      el.innerHTML = '<div class="text-center py-8" style="color:var(--success)">✅ Tüm ürünler yeterli stok seviyesinde</div>';
      return;
    }
    el.innerHTML = items.map(s => {
      const cur = s.mevcut_stok || 0;
      const min = s.sto_min_stok || 1;
      const pct = Math.min(100, Math.round((cur / min) * 100));
      const level = pct < 40 ? 'crit' : pct < 80 ? 'warn' : 'ok';
      const color = level === 'crit' ? 'var(--danger)' : level === 'warn' ? 'var(--warn)' : 'var(--success)';
      const badge = level === 'crit' ? '<span class="badge badge-danger">KRİTİK</span>' : level === 'warn' ? '<span class="badge badge-warn">DÜŞÜK</span>' : '<span class="badge badge-success">SAĞLIKLI</span>';
      return `<div class="p-4 hover:bg-[var(--bg-2)] rounded-xl transition flex items-center gap-4">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <div class="text-sm font-semibold truncate">${escHtml(s.sto_isim||'—')}</div>${badge}
          </div>
          <div class="text-[11px] text-[var(--text-3)] mono">${escHtml(s.sto_kod||'')}</div>
        </div>
        <div class="w-64 shrink-0">
          <div class="flex items-center justify-between text-xs mb-1.5">
            <span class="text-[var(--ink)] font-medium"><strong>${cur}</strong> ad</span>
            <span class="text-[var(--text-3)] mono">min ${min}</span>
          </div>
          <div class="progress"><div style="width:${pct}%; background:${color}"></div></div>
        </div>
        ${level !== 'ok' ? `<button onclick="openSupplierMail()" class="btn-ghost text-xs py-1.5 px-3 shrink-0">Sipariş ver</button>` : '<div class="w-[88px] shrink-0"></div>'}
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML = '<div class="text-center py-8 text-[var(--danger)]">Veri yüklenemedi</div>'; }
}

async function openSupplierMail() {
  const d = document.getElementById('supplierDrawer');
  d.classList.remove('hidden');
  const ta = document.getElementById('supplierMailBody');
  if (!ta) return;
  ta.value = 'AI ile mail oluşturuluyor…';
  try {
    const r = await fetch(API + '/api/supplier-email/bulk', {method:'POST'});
    const data = await r.json();
    if (data.email) ta.value = data.email;
  } catch(e) {
    ta.value = 'Mail oluşturulamadı. Lütfen tekrar deneyin.';
  }
}
function closeSupplierMail() { const d = document.getElementById('supplierDrawer'); d.classList.add('hidden'); }

async function sendDailyReport() {
  const btn = event?.target;
  const origText = btn?.textContent || 'Günlük Rapor Gönder';
  if (btn) { btn.disabled = true; btn.textContent = 'Gönderiliyor…'; }
  try {
    const r = await fetch(API + '/api/scheduler/trigger-daily-report', {method:'POST'});
    const d = await r.json();
    if (d.ok) showToast('Günlük rapor Telegram\'a gönderildi ✓', 'success');
    else showToast('Rapor gönderilemedi: ' + (d.error || ''), 'error');
  } catch(e) {
    showToast('Rapor gönderilemedi', 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = origText; }
}

async function sendMorningTasks() {
  const btn = event?.target;
  const origText = btn?.textContent || 'Sabah Görevi Gönder';
  if (btn) { btn.disabled = true; btn.textContent = 'Gönderiliyor…'; }
  try {
    const r = await fetch(API + '/api/scheduler/trigger-morning', {method:'POST'});
    const d = await r.json();
    if (d.ok) showToast('Sabah görev mesajları Telegram\'a gönderildi ✓', 'success');
    else showToast('Gönderilemedi: ' + (d.error || ''), 'error');
  } catch(e) {
    showToast('Gönderilemedi', 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = origText; }
}

/* ─── Customer Conversations (Feature 1) ───────────────────────────────── */
const fakeConversations = [
  { id:'c1', name:'Ayşe Yılmaz',  channel:'wa', last:'128 numaralı siparişim ne zaman gelir?', time:'şimdi',  unread:0, ai:true,  needsHuman:false },
  { id:'c2', name:'Mehmet Koç',   channel:'tg', last:'İade etmek istiyorum',                   time:'4 dk',   unread:1, ai:true,  needsHuman:false },
  { id:'c3', name:'Burak Yıldız', channel:'wa', last:'Ürün hasarlı geldi, çok kötü hizmet!',   time:'8 dk',   unread:2, ai:false, needsHuman:true  },
  { id:'c4', name:'Selin Polat',  channel:'web',last:'Stok ne zaman gelecek?',                 time:'15 dk',  unread:0, ai:true,  needsHuman:false },
  { id:'c5', name:'Cem Erdem',    channel:'tg', last:'Teşekkürler, çok hızlıydınız!',          time:'1 sa',   unread:0, ai:true,  needsHuman:false },
  { id:'c6', name:'Fatma Aktaş',  channel:'wa', last:'Faturayı maille gönderir misiniz?',      time:'2 sa',   unread:0, ai:true,  needsHuman:false },
  { id:'c7', name:'Deniz Çelik',  channel:'web',last:'Adresimi güncellemek istiyorum',         time:'3 sa',   unread:0, ai:false, needsHuman:true  },
  { id:'c8', name:'Pelin Acar',   channel:'ig', last:'Bu ürün hala satışta mı?',               time:'4 sa',   unread:0, ai:true,  needsHuman:false },
];

const fakeThreads = {
  c1: [
    { from:'customer', t:'Merhaba, 128 numaralı siparişim ne zaman gelir?', time:'14:08' },
    { from:'ai', t:'Merhaba Ayşe Hanım 👋 **#MK-23128** siparişinizi kontrol ettim.\n\n**Durum:** Kargoda · Aras Kargo · Takip no: AR**89231445**\n**Tahmini teslim:** 14 Mayıs Çarşamba (yarın), 14:00 — 18:00 arası\n\nKargo şu an Ankara aktarma merkezinde. Başka bir şey öğrenmek ister misiniz?', time:'14:08' },
    { from:'customer', t:'Teşekkürler!', time:'14:09' },
    { from:'ai', t:'Rica ederim 🙂 Teslimat sırasında bir sorun olursa hemen size haber verebilirim. İyi günler!', time:'14:09' },
  ],
  c3: [
    { from:'customer', t:'Merhaba, dün gelen siparişimde ürün hasarlı geldi, çok kötü hizmet!', time:'14:32' },
    { from:'ai', t:'Çok üzgünüm bunu duyduğuma. Size hemen yardımcı olmak istiyorum. **Sipariş numaranızı** paylaşır mısınız? Hasar fotoğrafı için size bir bağlantı göndereyim.', time:'14:32' },
    { from:'customer', t:'MK-23906', time:'14:33' },
    { from:'customer', t:'2 tane kahve makinesi sipariş etmiştim, kutusu ezik geldi ve cihaz çalışmıyor', time:'14:33' },
    { from:'system', t:'⚠️ AI bu konuşmayı bir insana yönlendirmek istiyor (sebep: müşteri memnuniyetsiz, fiziksel hasar şikayeti).', time:'14:34' },
  ],
  c2: [
    { from:'customer', t:'Merhaba, dün aldığım ürünü iade etmek istiyorum', time:'13:45' },
    { from:'ai', t:'Merhaba, tabii ki yardımcı olayım. Sipariş numaranız ile birlikte iade nedeninizi paylaşır mısınız? Süreç **14 gün** içinde ücretsiz iade ile tamamlanabilir.', time:'13:45' },
  ],
};

function openOrderInChat(convId) {
  const c = fakeConversations.find(x => x.id === convId);
  const msg = c ? `${c.name} müşterisinin son siparişlerini göster` : 'Son siparişleri göster';
  switchTab('chat');
  setTimeout(() => {
    const inp = document.getElementById('chatInput');
    if (inp) { inp.value = msg; sendMessage(); }
  }, 200);
}

function takeoverThread(convId) {
  const inp = document.getElementById('threadInput');
  if (inp) {
    inp.focus();
    inp.placeholder = '✍️ Müşteriye doğrudan yazıyorsunuz…';
    inp.style.borderColor = 'var(--primary)';
  }
  const ai = document.querySelector('.ai-tag');
  if (ai && ai.closest('.px-5')) {
    ai.closest('.flex').querySelector('span').textContent = '⚡ İNSAN MODU';
  }
  showToast('Devir alındı — artık siz yanıtlıyorsunuz', 'info');
}

function searchConvs() {
  const q = (document.getElementById('convSearch')?.value || '').toLowerCase();
  document.querySelectorAll('.conv-row').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

const tgIcon = '<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg>';

function convRowHtml(c, i, isActive) {
  const channelClass = c.channel === 'wa' ? 'channel-wa' : c.channel === 'tg' ? 'channel-tg' : c.channel === 'ig' ? 'channel-ig' : 'channel-web';
  const channelIcon = {
    wa: '<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M.057 24l1.687-6.163a11.867 11.867 0 01-1.587-5.946C.16 5.335 5.495 0 12.05 0a11.817 11.817 0 018.413 3.488 11.824 11.824 0 013.48 8.414c-.003 6.557-5.338 11.892-11.893 11.892a11.9 11.9 0 01-5.688-1.448L.057 24zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884a9.86 9.86 0 001.504 5.244l-.999 3.648 3.984-.591z"/></svg>',
    tg: tgIcon,
    web: '<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
    ig: '<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>',
  }[c.channel] || tgIcon;
  const aiBadge = c.needsHuman
    ? '<span class="badge badge-orange" style="font-size:9px; padding:1px 6px">İNSAN</span>'
    : '<span class="ai-tag" style="font-size:9px; padding:1px 6px">AI</span>';
  const unread = c.unread ? `<span class="ml-auto w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center text-white" style="background:var(--primary)">${c.unread}</span>` : '';
  return `
    <div class="conv-row ${isActive ? 'active' : ''}" data-conv="${c.id}" onclick="openThread('${c.id}', this)">
      <div class="flex items-start gap-3">
        <div class="avatar ${channelClass} relative">${(c.name||'?').split(' ').map(n=>n[0]).join('').slice(0,2)}
          <div class="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full ${channelClass} flex items-center justify-center border-2 border-[var(--surface)]">${channelIcon}</div>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <div class="text-sm font-semibold truncate">${c.name}</div>
            <div class="text-[10px] text-[var(--text-3)] mono ml-auto">${c.time}</div>
          </div>
          <div class="text-xs text-[var(--text-2)] truncate mt-0.5">${c.last}</div>
          <div class="flex items-center gap-1.5 mt-1.5">${aiBadge}${unread}</div>
        </div>
      </div>
    </div>`;
}

async function fillConversations() {
  const list = document.getElementById('convList');

  // Gerçek Telegram mesajlarını çek
  let realConvs = [];
  try {
    const res = await fetch(API + '/api/notifications?limit=30');
    const json = await res.json();
    realConvs = (json.notifications || [])
      .filter(n => n.tip === 'telegram_soru')
      .map((n, i) => {
        const soru = (n.mesaj || '').replace(/^S:\s*/, '').split('\n')[0];
        const tarih = n.olusturma_tarihi ? new Date(n.olusturma_tarihi).toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit'}) : '';
        return {
          id: 'tg_' + n.id,
          name: (n.baslik || 'Telegram'),
          channel: 'tg',
          last: soru,
          time: tarih,
          needsHuman: false,
          unread: i === 0 ? 1 : 0,
          yanit: n.yanit || null,
          _raw: n,
        };
      });
  } catch(e) { /* API erişilemezse sadece fake göster */ }

  window._realConvs = realConvs;
  const allConvs = [...realConvs, ...fakeConversations];
  list.innerHTML = allConvs.map((c, i) => convRowHtml(c, i, i === 0)).join('');
  openThread(allConvs[0]?.id || 'c1');
}

let _commsFilter = 'all';
function filterComms(type) {
  _commsFilter = type;
  document.querySelectorAll('.comms-filter-btn').forEach(b => {
    const active = b.dataset.filter === type;
    b.style.background    = active ? 'var(--ink)' : '';
    b.style.color         = active ? 'white' : '';
    b.style.borderColor   = active ? 'var(--ink)' : '';
  });
  const convs = type === 'human' ? fakeConversations.filter(c => c.needsHuman)
              : type === 'ai'    ? fakeConversations.filter(c => c.ai && !c.needsHuman)
              : fakeConversations;
  const list = document.getElementById('convList');
  list.innerHTML = convs.map((c, i) => convRowHtml(c, i, i === 0)).join('');
  if (convs.length) openThread(convs[0].id);
}

function openThread(id, rowEl) {
  document.querySelectorAll('.conv-row').forEach(r => r.classList.toggle('active', r.dataset.conv === id));
  // Gerçek Telegram konuşması mı yoksa fake mi?
  const isTg = id.startsWith('tg_');
  // realConvs global'den bul
  const _tgConv = isTg ? (window._realConvs || []).find(x => x.id === id) : null;
  const c = isTg
    ? (_tgConv || (() => { const el = document.querySelector(`[data-conv="${id}"]`); return el ? { name: el.querySelector('.font-semibold')?.textContent || 'Telegram', channel:'tg', needsHuman:false, id } : null; })())
    : fakeConversations.find(x => x.id === id);
  if (!c) return;
  const channelLabel = { wa:'WhatsApp', tg:'Telegram', web:'Web Chat', ig:'Instagram' }[c.channel] || 'Telegram';
  const channelClass = c.channel === 'wa' ? 'channel-wa' : c.channel === 'tg' ? 'channel-tg' : c.channel === 'ig' ? 'channel-ig' : 'channel-web';
  document.getElementById('threadHeader').innerHTML = `
    <div class="flex items-center gap-3">
      <div class="avatar ${channelClass}">${(c.name||'TG').split(' ').map(n=>n[0]).join('').slice(0,2)}</div>
      <div>
        <div class="text-sm font-semibold">${c.name}</div>
        <div class="text-xs text-[var(--text-3)]">${channelLabel} · #${c.id.toUpperCase()}</div>
      </div>
    </div>
    <div class="flex items-center gap-2">
      ${c.needsHuman ? '<span class="badge badge-orange">İNSAN MÜDAHALESİ GEREKLİ</span>' : '<span class="ai-tag">AI YÖNETİYOR</span>'}
      <button class="btn-ghost text-xs py-1.5 px-3" onclick="takeoverThread('${c.id}')">Devral</button>
    </div>`;
  const body = document.getElementById('threadBody');

  // Gerçek Telegram mesajını göster
  if (isTg) {
    const soru = c?.last || '';
    const yanit = c?.yanit || null;
    const initials = (c?.name||'TG').split(' ').map(n=>n[0]).join('').slice(0,2);
    const yanıtHTML = yanit
      ? `<div class="flex justify-end gap-2 items-end">
           <div class="text-right">
             <div class="bubble-user max-w-md inline-block" style="white-space:pre-wrap">${escHtml(yanit)}</div>
             <div class="text-[10px] text-[var(--text-3)] mt-1 mono flex items-center justify-end gap-1.5">
               <span class="ai-tag" style="font-size:9px; padding:1px 5px">KOBİ AI</span>
             </div>
           </div>
         </div>`
      : `<div class="flex justify-end gap-2 items-end">
           <div class="text-right">
             <div class="bubble-user max-w-md inline-block text-[var(--text-3)] italic">Yanıt bekleniyor...</div>
           </div>
         </div>`;
    body.innerHTML = `
      <div class="flex justify-start gap-2 items-end">
        <div class="avatar channel-tg" style="width:28px;height:28px;font-size:10px">${initials}</div>
        <div>
          <div class="text-[10px] text-[var(--text-3)] mb-1 font-semibold">${escHtml(c?.name||'Telegram')}</div>
          <div class="bubble-customer max-w-md">${escHtml(soru)}</div>
        </div>
      </div>
      ${yanıtHTML}`;
    body.parentElement.scrollTop = body.parentElement.scrollHeight;
    return;
  }

  const thread = fakeThreads[id] || [
    { from:'customer', t: c.last, time: c.time },
    { from:'ai', t: 'Merhaba, size nasıl yardımcı olabilirim?', time: c.time },
  ];
  body.innerHTML = thread.map(m => {
    if (m.from === 'system') {
      return `<div class="flex justify-center"><div class="surface-2 px-4 py-2 rounded-full text-xs text-[var(--text-2)]" style="border-color: rgba(255,90,31,0.3); background: var(--primary-soft); color: #B43E0D">${escHtml(m.t)}</div></div>`;
    }
    if (m.from === 'customer') {
      return `<div class="flex justify-start gap-2 items-end">
        <div class="avatar ${channelClass}" style="width:28px;height:28px;font-size:10px">${c.name.split(' ').map(n=>n[0]).join('').slice(0,2)}</div>
        <div><div class="bubble-customer max-w-md">${formatText(m.t)}</div><div class="text-[10px] text-[var(--text-3)] mt-1 mono">${m.time}</div></div>
      </div>`;
    }
    return `<div class="flex justify-end gap-2 items-end">
      <div class="text-right"><div class="bubble-user max-w-md inline-block">${formatText(m.t)}</div>
      <div class="text-[10px] text-[var(--text-3)] mt-1 mono flex items-center justify-end gap-1.5"><span class="ai-tag" style="font-size:9px; padding:1px 5px">AI</span>${m.time}</div></div>
    </div>`;
  }).join('');
  body.parentElement.scrollTop = body.parentElement.scrollHeight;
}

function fillOverviewComms() {
  const items = fakeConversations.slice(0, 4);
  document.getElementById('overviewComms').innerHTML = items.map((c, i) => {
    const channelClass = c.channel === 'wa' ? 'channel-wa' : c.channel === 'tg' ? 'channel-tg' : c.channel === 'ig' ? 'channel-ig' : 'channel-web';
    const status = c.needsHuman ? '<span class="badge badge-orange">İNSAN GEREK</span>' : '<span class="ai-tag">AI ÇÖZDÜ</span>';
    return `
      <div class="py-3 ${i === 0 ? '' : 'border-t border-[var(--line)]'} flex items-center gap-3 cursor-pointer hover:bg-[var(--bg-2)] -mx-2 px-2 rounded-lg transition" onclick="switchTab('comms'); setTimeout(()=>openThread('${c.id}'), 50)">
        <div class="avatar ${channelClass}" style="width:32px;height:32px;font-size:11px">${c.name.split(' ').map(n=>n[0]).join('').slice(0,2)}</div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2"><div class="text-sm font-semibold truncate">${c.name}</div><span class="text-[10px] text-[var(--text-3)] mono">${c.time}</span></div>
          <div class="text-xs text-[var(--text-2)] truncate">${c.last}</div>
        </div>
        ${status}
      </div>`;
  }).join('');
}

/* ─── Tasks ─────────────────────────────────────────────────────────────── */
function showToast(msg, type='info') {
  const colors = {success:'var(--success)', error:'var(--danger)', info:'var(--primary)'};
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:9999;background:var(--ink);color:white;padding:12px 20px;border-radius:12px;font-size:13px;box-shadow:0 4px 24px rgba(0,0,0,0.3);border-left:4px solid ${colors[type]||colors.info};max-width:360px`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function taskItem(t, idx) {
  const prioColor = t.prio === 'high' ? 'var(--danger)' : t.prio === 'med' ? 'var(--warn)' : 'var(--text-3)';
  return `
    <label class="flex items-center gap-2.5 p-2 rounded-lg hover:bg-[var(--bg-2)] cursor-pointer transition">
      <input type="checkbox" ${t.done ? 'checked' : ''} class="w-4 h-4 rounded shrink-0" style="accent-color: var(--primary)">
      <div class="flex-1 text-[13px] ${t.done ? 'line-through text-[var(--text-3)]' : 'text-[var(--ink)]'}">${t.t}</div>
      <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${prioColor}"></span>
    </label>`;
}

const ROL_CONFIG = {
  depo:               { label:'Depo Sorumlusu',    initials:'DS', color:'var(--primary)',  badge:'badge-orange'  },
  kargo:              { label:'Kargo Görevlisi',    initials:'KG', color:'var(--magenta)',  badge:'badge-magenta' },
  musteri_hizmetleri: { label:'Müşteri Hizmetleri', initials:'MH', color:'#6366F1',        badge:'badge-lime'    },
  satin_alma:         { label:'Satınalma',           initials:'SA', color:'var(--ink)',     badge:'badge-neutral' },
};

async function fillTasksByAssignee() {
  try {
    // Stats endpoint'ten rol bazlı özet al
    const [statsResp, tasksResp] = await Promise.all([
      fetch(API + '/api/tasks/stats'),
      fetch(API + '/api/tasks'),
    ]);
    if (!statsResp.ok || !tasksResp.ok) throw new Error();
    const stats = await statsResp.json();
    const tasksData = await tasksResp.json();
    const tasks = tasksData.tasks || [];
    const roller = stats.roller || [];

    // Otomasyon strip güncelle
    const totalRol = roller.length;
    const automText = document.getElementById('taskAutomationText');
    if (automText) automText.textContent = `${stats.toplam || 0} görev, ${totalRol} rol — ${stats.devam_eden || 0} devam ediyor, ${stats.bekleyen || 0} bekliyor`;

    // Scheduler durumunu kontrol et
    try {
      const sjr = await fetch(API + '/api/scheduler/jobs');
      if (sjr.ok) {
        const sj = await sjr.json();
        const statusEl = document.getElementById('schedulerStatus');
        if (statusEl) {
          const morningJob = (sj.jobs || []).find(j => j.id === 'morning_tasks');
          if (morningJob && morningJob.next_run) {
            const nxt = new Date(morningJob.next_run);
            const fmt = nxt.toLocaleDateString('tr-TR', {day:'numeric',month:'short'}) + ' ' + nxt.toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'});
            statusEl.innerHTML = `🟢 aktif · sonraki: <span class="mono">${fmt}</span>`;
          } else {
            statusEl.textContent = sj.running ? '🟢 çalışıyor' : '🔴 durdu';
          }
        }
      }
    } catch(e) {}

    // Özet sayılar
    setText('taskStatTamamlanan', stats.tamamlanan ?? '—');
    setText('taskStatBekleyen',   stats.bekleyen   ?? '—');
    setText('taskStatGeciken',    stats.geciken     ?? '—');

    // Rol kartları — veritabanından gelen roller
    const container = document.getElementById('taskRoleCards');
    if (container) {
      const rolsToShow = roller.length ? roller : [{atanan_rol:'depo',gorev_sayisi:0,tamamlanan:0,bekleyen:0,devam_eden:0}];
      container.innerHTML = rolsToShow.map(rol => {
        const cfg = ROL_CONFIG[rol.atanan_rol] || { label: rol.atanan_rol || 'Diğer', initials:'?', color:'var(--text-2)', badge:'badge-neutral' };
        const rolTasks = tasks.filter(t => t.atanan_kisi === rol.atanan_rol);
        const toHtml = (t) => taskItem({
          t: t.baslik || '—',
          prio: t.oncelik === 'Yüksek' ? 'high' : t.oncelik === 'Orta' ? 'med' : 'low',
          done: t.durum === 'Tamamlandi'
        }, 0);
        const taskHtml = rolTasks.length
          ? rolTasks.slice(0,5).map(toHtml).join('')
          : '<div class="text-xs text-[var(--text-3)] p-2">Görev yok</div>';
        return `
          <div class="surface p-4">
            <div class="flex items-center gap-2 mb-3">
              <div class="avatar" style="background:${cfg.color}">${cfg.initials}</div>
              <div>
                <div class="text-sm font-semibold">${cfg.label}</div>
                <div class="text-xs text-[var(--text-2)]">${rol.atanan_rol}</div>
              </div>
              <span class="ml-auto badge ${cfg.badge}">${rol.gorev_sayisi} görev</span>
            </div>
            <div class="space-y-1.5">${taskHtml}</div>
          </div>`;
      }).join('');
    }
  } catch(e) {
    console.warn('fillTasksByAssignee hata:', e);
    const container = document.getElementById('taskRoleCards');
    if (container) container.innerHTML = '<div class="surface p-4 text-center text-[var(--text-3)] text-sm col-span-3">Görev verileri yüklenemedi</div>';
  }
}

async function fillOverviewTasks() {
  const el = document.getElementById('overviewTasks');
  if (!el) return;
  try {
    const r = await fetch(API + '/api/tasks/today');
    if (!r.ok) throw new Error();
    const d = await r.json();
    const tasks = (d.tasks || []).slice(0, 5);
    if (!tasks.length) { el.innerHTML = '<div class="text-xs text-[var(--text-3)] p-2">Bugün görev yok</div>'; return; }
    el.innerHTML = tasks.map(t => taskItem({
      t: t.baslik || '—',
      prio: t.oncelik === 'Yüksek' ? 'high' : t.oncelik === 'Orta' ? 'med' : 'low',
      done: t.durum === 'Tamamlandi'
    }, 0)).join('');
  } catch(e) {
    el.innerHTML = '<div class="text-xs text-[var(--text-3)] p-2">Görevler yüklenemedi</div>';
  }
}

/* ─── Top products + forecast ──────────────────────────────────────────── */
async function fillTopProducts() {
  const el = document.getElementById('topProducts');
  if (!el) return;
  el.innerHTML = '<div class="text-center py-4 text-[var(--text-3)]">Yükleniyor…</div>';
  try {
    const r = await fetch(API + '/api/analytics/top-products?days=30&limit=5');
    if (!r.ok) throw new Error();
    const d = await r.json();
    const items = d.products || [];
    if (!items.length) { el.innerHTML = '<div class="text-center py-4 text-[var(--text-3)]">Veri yok</div>'; return; }
    const maxRev = Math.max(...items.map(p => p.ciro || 0)) || 1;
    el.innerHTML = items.map((p, i) => `
      <div class="flex items-center gap-3">
        <div class="text-[11px] mono text-[var(--text-3)] w-5">${String(i+1).padStart(2,'0')}</div>
        <div class="w-44 text-sm font-medium truncate">${escHtml(p.sto_isim||'—')}</div>
        <div class="flex-1 progress"><div style="width:${Math.round((p.ciro/maxRev)*100)}%; background:linear-gradient(90deg,var(--primary),var(--magenta))"></div></div>
        <div class="text-xs text-[var(--text-3)] mono w-16 text-right">${Math.round(p.adet||0)} ad</div>
        <div class="text-sm text-[var(--ink)] font-semibold w-24 text-right mono">₺${Math.round(p.ciro||0).toLocaleString('tr-TR')}</div>
      </div>`).join('');
  } catch(e) { el.innerHTML = '<div class="text-center py-4 text-[var(--danger)]">Veri yüklenemedi</div>'; }
}

async function fillForecast() {
  const el = document.getElementById('forecastGrid');
  if (!el) return;
  try {
    const r = await fetch(API + '/api/analytics/top-products?days=30&limit=5');
    if (!r.ok) throw new Error();
    const d = await r.json();
    const items = (d.products || []).slice(0, 5);
    // Rastgele ama tutarlı büyüme tahmini (adet bazında)
    el.innerHTML = items.map(p => {
      const chg = Math.round(((p.adet || 0) / 60) * 10 - 5); // basit tahmin formülü
      const conf = Math.min(92, Math.max(65, 70 + Math.round((p.ciro||0) / 5000)));
      return `<div class="surface-2 p-4">
        <div class="text-xs text-[var(--text-2)] mb-1 truncate">${escHtml(p.sto_isim||'—')}</div>
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-bold" style="color:${chg >= 0 ? 'var(--success)' : 'var(--danger)'}">${chg >= 0 ? '+' : ''}${chg}%</span>
        </div>
        <div class="text-[10px] text-[var(--text-3)] mono mt-2">Güven: ${conf}%</div>
        <div class="progress mt-1" style="height:3px"><div style="width:${conf}%; background:${chg >= 0 ? 'var(--success)' : 'var(--danger)'}"></div></div>
      </div>`;
    }).join('');
  } catch(e) {
    // fallback statik
    const f = [{n:'Pijama Takımı',chg:+22,conf:92},{n:'Oversize Sweat',chg:+18,conf:88},{n:'Yazlık Elbise',chg:+15,conf:84},{n:'Slim Fit Gömlek',chg:+9,conf:77},{n:'Chino Pantolon',chg:-4,conf:71}];
    el.innerHTML = f.map(x => `<div class="surface-2 p-4"><div class="text-xs text-[var(--text-2)] mb-1">${x.n}</div><div class="flex items-baseline gap-1"><span class="text-2xl font-bold" style="color:${x.chg>=0?'var(--success)':'var(--danger)'}">${x.chg>=0?'+':''}${x.chg}%</span></div><div class="text-[10px] text-[var(--text-3)] mono mt-2">Güven: ${x.conf}%</div><div class="progress mt-1" style="height:3px"><div style="width:${x.conf}%; background:${x.chg>=0?'var(--success)':'var(--danger)'}"></div></div></div>`).join('');
  }
}

/* ─── Analytics Zaman Filtresi ─────────────────────────────────────────── */
let _analyticsDays = 30;
async function setAnalyticsDays(days) {
  _analyticsDays = days;
  // Buton aktif stilini güncelle
  [30, 90, 365].forEach(d => {
    const btn = document.getElementById('analyticsDays' + d);
    if (!btn) return;
    if (d === days) {
      btn.style.background = 'var(--ink)';
      btn.style.color = 'white';
    } else {
      btn.style.background = '';
      btn.style.color = '';
    }
  });
  // Grafikleri yeniden çiz
  analyticsRendered = false;
  ['trendChart', 'channelChart'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { const old = Chart.getChart(el); if (old) old.destroy(); }
  });
  await renderAnalyticsCharts(days);
  // Insight güncelle
  await fillAnalyticsInsight(days);
}

async function fillAnalyticsInsight(days) {
  const insightEl = document.getElementById('analyticsInsightText');
  const timeEl    = document.getElementById('analyticsInsightTime');
  if (!insightEl) return;
  try {
    const r = await fetch(API + `/api/analytics/sales?days=${days}`);
    if (!r.ok) throw new Error();
    const d = await r.json();
    const channels = d.channels || [];
    const now = new Date();
    if (timeEl) timeEl.textContent = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0') + ' GÜNCELLENDI';
    if (!channels.length) {
      insightEl.innerHTML = 'Bu dönem için yeterli satış verisi bulunamadı.';
      return;
    }
    const topKanal  = channels[0];
    const totalCiro = channels.reduce((s, c) => s + (c.brut_ciro||0), 0);
    const topPay    = totalCiro > 0 ? Math.round((topKanal.brut_ciro / totalCiro) * 100) : 0;
    const totalSip  = channels.reduce((s, c) => s + (c.siparis_sayisi||0), 0);
    const ciroStr   = '₺' + (totalCiro >= 1e6 ? (totalCiro/1e6).toFixed(2) + 'M' : Math.round(totalCiro).toLocaleString('tr-TR'));
    // Ciro göstergelerini güncelle
    setText('analyticsTotalCiro', ciroStr);
    setText('overviewTotalCiro',  ciroStr);
    insightEl.innerHTML = `Son <strong>${days} gün</strong>de toplam <strong>${totalSip.toLocaleString('tr-TR')}</strong> sipariş alındı, toplam ciro <strong class="neon-text">${ciroStr}</strong> oldu. <strong>${topKanal.kanal || '—'}</strong> kanalı %${topPay} pay ile öne çıktı.`;
  } catch(e) {
    insightEl.textContent = 'Analitik veriler yüklenemedi.';
  }
}

/* ─── Charts ───────────────────────────────────────────────────────────── */
let analyticsRendered = false;
async function renderAnalyticsCharts(days) {
  if (analyticsRendered) return;
  analyticsRendered = true;
  Chart.defaults.color = '#6B655C';
  Chart.defaults.borderColor = 'rgba(20,16,12,0.06)';
  const d = days || _analyticsDays;
  await renderSalesTrend('trendChart', 240, d);
  await renderChannel('channelChart', d);
  // İlk yüklemede insight'ı da doldur
  await fillAnalyticsInsight(d);
}
let overviewRendered = false;
async function renderOverviewCharts() {
  if (overviewRendered) return;
  overviewRendered = true;
  Chart.defaults.color = '#6B655C';
  Chart.defaults.borderColor = 'rgba(20,16,12,0.06)';
  await renderSalesTrend('overviewTrend', 220);
  await renderChannel('overviewChannel');
}

async function renderSalesTrend(id, h, days) {
  const c = document.getElementById(id);
  if (!c) return;
  let labels = [], vals = [];
  try {
    const r = await fetch(API + '/api/analytics/monthly');
    if (r.ok) {
      const d = await r.json();
      let monthly = d.monthly || [];
      // days'e göre filtrele
      if (days && days < 365) {
        const cutoff = new Date();
        cutoff.setDate(cutoff.getDate() - (days || 30));
        monthly = monthly.filter(m => {
          const dt = new Date(`${m.yil}-${m.ay}-01`);
          return dt >= cutoff;
        });
      }
      labels = monthly.map(m => m.ay + '/' + (m.yil||'').slice(2));
      vals   = monthly.map(m => m.ciro || 0);
    }
  } catch(e) {}
  if (!vals.length) {
    // fallback
    let base = 70000;
    for (let i = 29; i >= 0; i--) {
      const d = new Date(); d.setDate(d.getDate() - i);
      labels.push(d.getDate() + '/' + (d.getMonth()+1));
      base += (Math.random() - 0.45) * 12000;
      vals.push(Math.max(35000, base));
    }
  }
  const ctx = c.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(255,90,31,0.35)');
  grad.addColorStop(1, 'rgba(255,90,31,0)');
  new Chart(c, {
    type: 'line',
    data: { labels, datasets: [{ data: vals, borderColor:'#FF5A1F', backgroundColor: grad, fill: true, tension: 0.35, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: '#FF5A1F' }]},
    options: { responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ backgroundColor:'#0A0A0A', titleColor:'#fff', bodyColor:'#FFB58F', borderWidth:0, padding:10, displayColors:false, callbacks:{ label:c=>'₺'+c.raw.toLocaleString('tr-TR',{maximumFractionDigits:0})}}},
      scales:{
        x:{ grid:{display:false}, ticks:{font:{size:10}, maxTicksLimit:10}},
        y:{ grid:{color:'rgba(20,16,12,0.05)'}, ticks:{font:{size:10}, callback:v=>'₺'+(v/1000).toFixed(0)+'K'}}
      }}
  });
}

async function renderChannel(id, days) {
  const c = document.getElementById(id);
  if (!c) return;
  const COLORS = ['#FF5A1F','#FF1B6B','#0A0A0A','#84B400','#F59E0B'];
  let labels = ['Trendyol','HepsiBurada','N11','CSP'];
  let data   = [40, 25, 15, 12];
  let channels = [];
  const d = days || _analyticsDays || 90;
  try {
    const r = await fetch(API + `/api/analytics/sales?days=${d}`);
    if (r.ok) {
      const json = await r.json();
      channels = json.channels || [];
      if (channels.length) {
        labels = channels.map(ch => ch.kanal || '—');
        data   = channels.map(ch => Math.round(ch.brut_ciro || 0));
      }
    }
  } catch(e) {}

  // Populate legend lists
  const totalCiro = data.reduce((s, v) => s + v, 0);
  if (channels.length) {
    // Overview legend (percentage-based)
    const overviewList = document.getElementById('overviewChannelList');
    if (overviewList) {
      overviewList.innerHTML = labels.map((lbl, i) => {
        const pct = totalCiro > 0 ? Math.round((data[i] / totalCiro) * 100) : 0;
        return `<div class="flex justify-between"><span class="flex items-center gap-2"><span class="w-2 h-2 rounded-sm" style="background:${COLORS[i]||'#ccc'}"></span>${lbl}</span><span class="mono font-semibold">${pct}%</span></div>`;
      }).join('');
    }
    // Analytics legend (ciro-based)
    const analyticsList = document.getElementById('analyticsChannelList');
    if (analyticsList) {
      analyticsList.innerHTML = labels.map((lbl, i) => {
        const v = data[i] || 0;
        const str = v >= 1e6 ? '₺' + (v/1e6).toFixed(2) + 'M' : v >= 1000 ? '₺' + (v/1000).toFixed(0) + 'K' : '₺' + v.toLocaleString('tr-TR');
        return `<div class="flex justify-between"><span class="flex items-center gap-2"><span class="w-2 h-2 rounded-sm" style="background:${COLORS[i]||'#ccc'}"></span>${lbl}</span><span class="font-medium mono">${str}</span></div>`;
      }).join('');
    }
  }

  new Chart(c, {
    type: 'doughnut',
    data: { labels, datasets:[{ data, backgroundColor: COLORS, borderColor:'#FFFFFF', borderWidth:3, hoverOffset: 6 }]},
    options: { responsive:true, maintainAspectRatio:false, cutout:'68%', plugins:{ legend:{display:false}, tooltip:{ backgroundColor:'#0A0A0A', titleColor:'#fff', bodyColor:'#fff', borderWidth:0, padding:10,
      callbacks:{ label: ctx => ctx.label + ': ₺' + ctx.raw.toLocaleString('tr-TR') }
    }}}
  });
}

/* ═══════════════════════════════════════════════════════════════════════
   CHAT (Real APIs preserved)
   ═══════════════════════════════════════════════════════════════════════ */
async function checkHealth() {
  try {
    const r = await fetch(API + '/health');
    if (r.ok) {
      document.getElementById('statusDot').style.background = 'var(--success)';
      document.getElementById('statusText').textContent = 'BAĞLI';
    } else throw 0;
  } catch {
    document.getElementById('statusDot').style.background = 'var(--danger)';
    document.getElementById('statusText').textContent = 'BAĞLANTI YOK';
  }
}

async function loadSessionHistory() {
  try {
    const r = await fetch(API + '/api/history?client_id=' + encodeURIComponent(CLIENT_ID));
    if (!r.ok) return;
    const data = await r.json();
    renderSessionList(data.sessions || []);
  } catch (e) {}
}

function renderSessionList(sessions) {
  const list = document.getElementById('historyList');
  list.innerHTML = '';
  if (!sessions.length) {
    list.innerHTML = '<div class="text-[11px] text-[var(--text-3)] px-3 py-2 sidebar-text">Henüz sohbet yok.</div>';
    return;
  }
  sessions.slice(0, 8).forEach(s => {
    const raw = (s.title || 'Sohbet').slice(0, 40);
    const div = document.createElement('div');
    const isActive = s.session_id === SESSION_ID;
    div.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition hover:bg-[var(--bg-2)]' + (isActive ? ' bg-[var(--bg-2)]' : '');
    div.dataset.sessionId = s.session_id;
    div.innerHTML = `
      <svg class="w-3.5 h-3.5 text-[var(--text-3)] shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
      <span class="text-xs text-[var(--text-2)] truncate sidebar-text">${escHtml(raw)}</span>`;
    div.onclick = () => loadSession(s.session_id);
    list.appendChild(div);
  });
}

async function loadSession(sessionId) {
  SESSION_ID = sessionId;
  document.getElementById('messages').innerHTML = '';
  document.getElementById('welcomeMsg')?.remove();
  pendingSuggestions = null;
  msgCount = 0;
  Object.values(chartInstances).forEach(c => c.destroy());
  chartInstances = {};
  switchTab('chat');
  try {
    const r = await fetch(API + '/api/session/' + encodeURIComponent(sessionId) + '/messages');
    if (!r.ok) return;
    const data = await r.json();
    const msgs = data.messages || [];
    if (!msgs.length) { showWelcome(); return; }
    for (const msg of msgs) {
      if (msg.role === 'user') addUserMessage(msg.content);
      else if (msg.role === 'assistant') {
        addAssistantMessage(msg.content, msg.sql_query, null);
        if (msg.sql_query && msg.row_count > 0) await rerunAndAppend(msg.sql_query, 'msg_' + msgCount);
      }
    }
  } catch (e) { showWelcome(); }
}

async function rerunAndAppend(sql, msgId) {
  try {
    const r = await fetch(API + '/api/rerun', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ sql }) });
    if (!r.ok) return;
    const data = await r.json();
    if (!data.success || !data.data || !data.data.length) return;
    const msgEl = document.getElementById(msgId);
    if (!msgEl) return;
    const bubble = msgEl.querySelector('.bubble');
    if (!bubble) return;
    const w = document.createElement('div');
    w.className = 'mt-3 overflow-x-auto rounded-xl';
    w.style.border = '1px solid var(--line)';
    w.innerHTML = buildTableHtml(data.data, data.columns, data.row_count);
    bubble.appendChild(w);
    if (data.visualization_type && data.visualization_type !== 'table' && data.data.length > 0) {
      const cid = 'chart_r_' + msgId;
      const c = document.createElement('div');
      c.className = 'mt-4 rounded-xl p-4';
      c.style.background = 'var(--bg-2)';
      c.style.border = '1px solid var(--line)';
      c.innerHTML = `<div class="h-56"><canvas id="${cid}"></canvas></div>`;
      bubble.appendChild(c);
      setTimeout(() => drawChart(cid, data.data, data.columns, data.visualization_type), 80);
    }
  } catch (e) {}
}

function showWelcome() {
  document.getElementById('messages').innerHTML = `
    <div id="welcomeMsg" class="text-center py-10 fadeUp">
      <div class="logo-orb mx-auto mb-5" style="width:54px;height:54px;border-radius:16px">
        <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
      </div>
      <h2 class="text-2xl font-bold mb-2 tracking-tight">Yeni Sohbet</h2>
      <p class="text-[var(--text-2)] text-sm">Ne sormak istersiniz?</p>
    </div>`;
}

function hideWelcome() { document.getElementById('welcomeMsg')?.remove(); }
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; }
function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }

function sendQuestion(q) {
  const i = document.getElementById('questionInput');
  if (i) i.value = q;
  sendMessage();
}

async function sendMessage() {
  if (isLoading) return;
  const input = document.getElementById('questionInput');
  const q = input.value.trim();
  if (!q) return;
  if (pendingSuggestions) pendingSuggestions = null;
  input.value = ''; input.style.height = 'auto';
  hideWelcome();
  addUserMessage(q);
  await callAPI(q, false);
}

async function callAPI(question, alreadyClarified = false) {
  isLoading = true; setLoading(true);
  const typingId = addTypingIndicator();
  try {
    const body = { question, session_id: SESSION_ID, client_id: CLIENT_ID, user_id: 'web_user',
                   analytical: analyticalMode, analytical_depth: 'medium', already_clarified: alreadyClarified };
    const res = await fetch(API + '/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    removeTypingIndicator(typingId);
    if (!res.ok) {
      const err = await res.json().catch(()=>({error:res.statusText}));
      addErrorMessage(err.error || 'Sunucu hatası');
      return;
    }
    const data = await res.json();
    handleResponse(data, question);
    loadSessionHistory();
  } catch (e) {
    removeTypingIndicator(typingId);
    addErrorMessage('Bağlantı hatası: ' + e.message);
  } finally {
    isLoading = false; setLoading(false);
  }
}

function handleResponse(data, question) {
  if (!data.success) { addErrorMessage(data.error || 'Bir hata oluştu.'); return; }
  if (data.clarification_needed && data.suggestions?.length) {
    pendingSuggestions = { suggestions: data.suggestions, original: question };
    addClarificationMessage(data.answer, data.suggestions, question);
    return;
  }
  if (data.answer && !data.data) { addAssistantMessage(data.answer, data.sql, data.tokens); return; }
  if (data.data && data.data.length > 0) {
    addDataMessage({ answer: data.answer, insight: data.insight, sql: data.sql, data: data.data,
                     columns: data.columns, supplements: data.supplements, vizType: data.visualization_type,
                     rowCount: data.row_count, tokens: data.tokens });
    return;
  }
  if (data.row_count === 0) { addAssistantMessage(data.answer || 'Bu kriterlere uygun kayıt bulunamadı.', data.sql, data.tokens); return; }
  addAssistantMessage(data.answer || 'Cevap alındı.', data.sql, data.tokens);
}

function addUserMessage(text) {
  const id = 'msg_' + (++msgCount);
  appendMsg(`
    <div id="${id}" class="flex justify-end fadeUp">
      <div class="max-w-xl">
        <div class="bubble-user">${escHtml(text)}</div>
        <div class="text-[10px] text-[var(--text-3)] text-right mt-1 mr-2 mono">${timeStr()}</div>
      </div>
    </div>`);
}

function addAssistantMessage(text, sql, tokens) {
  const id = 'msg_' + (++msgCount);
  const sqlBlock = sql ? `
    <details class="mt-3 group">
      <summary class="text-[11px] text-[var(--primary)] font-medium inline-flex items-center gap-1"><svg class="w-3 h-3 transition group-open:rotate-90" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg> SQL Sorgusunu Göster</summary>
      <pre class="mt-2 p-3 rounded-lg text-[11px] mono whitespace-pre-wrap overflow-x-auto" style="background:var(--ink); color:#FFB58F">${escHtml(sql)}</pre>
    </details>` : '';
  const tok = tokens ? `<span class="text-[10px] text-[var(--text-3)] mono">${tokens.total || 0} token</span>` : '';
  appendMsg(`
    <div id="${id}" class="flex gap-3 fadeUp">
      <div class="logo-orb shrink-0 mt-1" style="width:28px;height:28px;border-radius:8px"><svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg></div>
      <div class="flex-1 max-w-2xl min-w-0">
        <div class="bubble bubble-ai">
          <div class="msg-text">${formatText(text)}</div>
          ${sqlBlock}
        </div>
        <div class="flex items-center gap-2 mt-1 ml-2 text-[10px] text-[var(--text-3)] mono">
          <span>${timeStr()}</span>${tok}
        </div>
      </div>
    </div>`);
}

function addDataMessage({ answer, insight, sql, data, columns, vizType, rowCount, tokens, supplements }) {
  const id = 'msg_' + (++msgCount);
  const cid = 'chart_' + id;
  const tableHtml = buildTableHtml(data, columns, rowCount);
  const chartHtml = (vizType && vizType !== 'table' && data.length > 0)
    ? `<div class="mt-4 rounded-xl p-4" style="background:var(--bg-2); border:1px solid var(--line);"><div class="h-56"><canvas id="${cid}"></canvas></div></div>` : '';
  const insightHtml = insight ? `
    <div class="mt-3 p-3 rounded-xl" style="background: var(--primary-soft); border:1px solid rgba(255,90,31,0.25);">
      <div class="text-[10px] font-bold uppercase tracking-wider mb-1" style="color:#B43E0D">AI ANALİZ</div>
      <div class="msg-text">${formatText(insight)}</div>
    </div>` : '';
  const answerHtml = answer ? `<div class="msg-text mb-3">${formatText(answer)}</div>` : '';
  let supplementHtml = '';
  if (supplements && supplements.length) {
    supplementHtml = supplements.map(s => `
      <div class="mt-3 rounded-xl overflow-hidden" style="border:1px solid rgba(255,27,107,0.25);">
        <div class="px-3 py-2 flex items-center gap-2" style="background:var(--magenta-soft);">
          <span class="text-[10px] font-bold uppercase tracking-wider" style="color:#B5044C">TAMAMLAYICI</span>
          <span class="text-xs text-[var(--text-2)]">${escHtml(s.description)}</span>
          <span class="text-[10px] text-[var(--text-3)] mono ml-auto">${s.row_count} satır</span>
        </div>
        <div class="overflow-x-auto">${buildTableHtml(s.data, s.columns, s.row_count)}</div>
      </div>`).join('');
  }
  const sqlBlock = sql ? `
    <details class="mt-3 group">
      <summary class="text-[11px] text-[var(--primary)] font-medium inline-flex items-center gap-1"><svg class="w-3 h-3 transition group-open:rotate-90" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg> SQL Sorgusunu Göster</summary>
      <pre class="mt-2 p-3 rounded-lg text-[11px] mono whitespace-pre-wrap overflow-x-auto" style="background:var(--ink); color:#FFB58F">${escHtml(sql)}</pre>
    </details>` : '';
  const tok = tokens ? `<span>${tokens.total || 0} token</span>` : '';
  appendMsg(`
    <div id="${id}" class="flex gap-3 fadeUp">
      <div class="logo-orb shrink-0 mt-1" style="width:28px;height:28px;border-radius:8px"><svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg></div>
      <div class="flex-1 max-w-2xl min-w-0">
        <div class="bubble bubble-ai">
          ${answerHtml}
          <div class="overflow-x-auto rounded-xl" style="border:1px solid var(--line)">${tableHtml}</div>
          ${chartHtml}
          ${supplementHtml}
          ${insightHtml}
          ${sqlBlock}
        </div>
        <div class="flex items-center gap-2 mt-1 ml-2 text-[10px] text-[var(--text-3)] mono">
          <button onclick="exportCSV('${id}')" class="hover:text-[var(--primary)] inline-flex items-center gap-1"><svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>CSV</button>
          <span>${timeStr()}</span><span>${rowCount} satır</span>${tok}
        </div>
      </div>
    </div>`);
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.dataset.csv = JSON.stringify({ data, columns });
    if (chartHtml && vizType !== 'table') drawChart(cid, data, columns, vizType);
  }, 50);
}

function addClarificationMessage(msg, suggestions, originalQuestion) {
  const id = 'msg_' + (++msgCount);
  const pills = suggestions.map((s, i) => {
    const label = typeof s === 'object' ? s.label : s;
    return `<button class="pill" onclick="selectSuggestion(${i}, '${escAttr(originalQuestion)}')">${escHtml(label)}</button>`;
  }).join('');
  appendMsg(`
    <div id="${id}" class="flex gap-3 fadeUp">
      <div class="logo-orb shrink-0 mt-1" style="width:28px;height:28px;border-radius:8px"><svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>
      <div class="flex-1 max-w-2xl">
        <div class="bubble-ai">
          <div class="msg-text mb-3">${formatText(msg)}</div>
          <div class="flex flex-wrap gap-2">${pills}</div>
        </div>
      </div>
    </div>`);
}

function selectSuggestion(idx, originalQuestion) {
  if (!pendingSuggestions) return;
  const s   = pendingSuggestions.suggestions[idx];
  const lbl = typeof s === 'object' ? s.label : s;
  const col = typeof s === 'object' ? (s.column || '') : '';
  pendingSuggestions = null;
  let newQ;
  if (col === 'sto_isim') newQ = `'${lbl}' ürünü için: ${originalQuestion}`;
  else if (col === 'cari_unvan1') newQ = `'${lbl}' müşterisi için: ${originalQuestion}`;
  else if (col === 'sip_eticaret_kanal_kodu') newQ = `'${lbl}' kanalı için: ${originalQuestion}`;
  else newQ = `'${lbl}' için: ${originalQuestion}`;
  addUserMessage(newQ);
  callAPI(newQ, true);
}

function addErrorMessage(text) {
  appendMsg(`
    <div class="flex gap-3 fadeUp">
      <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-1" style="background: #FEE2E2; border:1px solid rgba(220,38,38,0.3)">
        <svg class="w-3.5 h-3.5" style="color:var(--danger)" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
      </div>
      <div class="px-4 py-3 rounded-2xl rounded-tl-md max-w-lg" style="background:#FEE2E2; border:1px solid rgba(220,38,38,0.25);">
        <p class="text-sm" style="color:#991B1B">${escHtml(text)}</p>
      </div>
    </div>`);
}

function addTypingIndicator() {
  const id = 'typing_' + Date.now();
  appendMsg(`
    <div id="${id}" class="flex gap-3 fadeIn">
      <div class="logo-orb shrink-0 mt-1" style="width:28px;height:28px;border-radius:8px"><svg class="w-3.5 h-3.5 text-white animate-spin" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg></div>
      <div class="bubble-ai inline-flex items-center gap-1.5"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
    </div>`);
  return id;
}
function removeTypingIndicator(id) { document.getElementById(id)?.remove(); }

/* ─── Table builders ───────────────────────────────────────────────────── */
function buildTableHtml(data, columns, rowCount) {
  if (!data || !columns || !data.length) return '';
  const maxRows = 50;
  const rows = data.slice(0, maxRows);
  const headers = columns.map(c => `<th>${escHtml(prettyCol(c))}</th>`).join('');
  const body = rows.map(row =>
    '<tr>' + columns.map(c => `<td title="${escAttr(String(row[c] ?? ''))}">${escHtml(fmtVal(row[c], c))}</td>`).join('') + '</tr>'
  ).join('');
  const moreRow = rowCount > maxRows
    ? `<tr><td colspan="${columns.length}" class="text-center text-[var(--text-3)] py-2" style="font-size:11px">… ve ${rowCount - maxRows} satır daha</td></tr>` : '';
  return `<table class="data-table"><thead><tr>${headers}</tr></thead><tbody>${body}${moreRow}</tbody></table>`;
}

function prettyCol(col) {
  const map = {
    sip_eticaret_kanal_kodu:'Kanal', sip_evrakno_sira:'Sipariş No',
    sip_tarih:'Tarih', sip_durumu:'Durum', sto_isim:'Ürün Adı',
    sto_kod:'Ürün Kodu', sth_tutar:'Tutar (₺)', sth_miktar:'Miktar',
    sth_birimfiyat:'Birim Fiyat', cari_unvan1:'Müşteri',
    itlp_aciklama:'İade Nedeni', kargo_sirkettipi:'Kargo',
  };
  return map[col] || col.replace(/^(sip_|sto_|sth_|cari_|kargo_|itlp_|sdp_|fid_|eu_)/, '').replace(/_/g,' ').replace(/\b\w/g, l => l.toUpperCase());
}

function fmtVal(v, col) {
  if (v === null || v === undefined) return '—';
  if (col && /tutar|fiyat|meblag|ciro/i.test(col) && typeof v === 'number')
    return '₺' + v.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return new Date(v).toLocaleDateString('tr-TR');
  if (col === 'kargo_sirkettipi') return ['?','Yurtiçi','Aras','MNG','PTT','Sürat'][parseInt(v)] || v;
  if (col === 'sip_durumu') return ['?','Beklemede','Onaylandı','Hazırlanıyor','Kargoda','Teslim','İptal'][parseInt(v)] || v;
  if (typeof v === 'number') return v.toLocaleString('tr-TR');
  return String(v).slice(0, 120);
}

function drawChart(canvasId, data, columns, vizType) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
  const numCols  = columns.filter(c => data.some(r => typeof r[c] === 'number'));
  const textCols = columns.filter(c => !numCols.includes(c));
  const labelCol = textCols[0] || columns[0];
  const valueCol = numCols[0]  || columns[1] || columns[0];
  const labels = data.map(r => String(r[labelCol] || '').slice(0,30));
  const values = data.map(r => parseFloat(r[valueCol]) || 0);
  const COLORS = ['#FF5A1F','#FF1B6B','#0A0A0A','#84B400','#F59E0B','#06B6D4','#9333EA','#0EA5E9'];
  const isLine = vizType === 'line';
  const isPie  = vizType === 'pie';
  let bgColor = 'rgba(255,90,31,0.4)';
  if (isLine) {
    const g = canvas.getContext('2d').createLinearGradient(0,0,0,220);
    g.addColorStop(0,'rgba(255,90,31,0.35)'); g.addColorStop(1,'rgba(255,90,31,0)');
    bgColor = g;
  }
  const chartData = { labels, datasets: [{
    label: prettyCol(valueCol), data: values,
    backgroundColor: isPie ? COLORS.slice(0, data.length) : bgColor,
    borderColor: isPie ? '#FFFFFF' : '#FF5A1F',
    borderWidth: isPie ? 3 : 2,
    borderRadius: isLine || isPie ? 0 : 6,
    fill: isLine, tension: isLine ? 0.35 : 0,
    pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor:'#FF5A1F',
  }]};
  const opts = {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: isPie, labels: { color: '#6B655C', font: { size:11 }, padding: 10 } },
      tooltip: { backgroundColor:'#0A0A0A', titleColor:'#fff', bodyColor:'#FFB58F', borderWidth:0, padding:10, displayColors:false,
        callbacks: { label: ctx => { const v = ctx.raw; return /tutar|fiyat|ciro/i.test(valueCol) ? '₺'+v.toLocaleString('tr-TR') : v.toLocaleString('tr-TR'); } } }
    },
    scales: isPie ? {} : {
      x: { grid: { display: false }, ticks: { color: '#6B655C', font:{size:10}, maxRotation:0 } },
      y: { grid: { color: 'rgba(20,16,12,0.05)' }, ticks: { color: '#6B655C', font:{size:10},
        callback: v => /tutar|fiyat|ciro/i.test(valueCol) ? '₺'+(v>=1000?(v/1000).toFixed(0)+'K':v) : v.toLocaleString('tr-TR') } }
    }
  };
  chartInstances[canvasId] = new Chart(canvas, { type: isPie ? 'doughnut' : isLine ? 'line' : 'bar', data: chartData, options: opts });
}

function exportCSV(msgId) {
  const el = document.getElementById(msgId);
  if (!el || !el.dataset.csv) return;
  const { data, columns } = JSON.parse(el.dataset.csv);
  const rows = [columns.join(',')];
  data.forEach(r => rows.push(columns.map(c => `"${String(r[c] ?? '').replace(/"/g, '""')}"`).join(',')));
  const blob = new Blob(['\uFEFF' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'kobi_ai_' + Date.now() + '.csv';
  a.click();
}

/* ─── Customer chat ────────────────────────────────────────────────────── */
function handleCustomerKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendCustomerMessage(); } }
function sendCustomerQuestion(q) { document.getElementById('customerInput').value = q; sendCustomerMessage(); }

async function sendCustomerMessage() {
  const input = document.getElementById('customerInput');
  const q = input.value.trim();
  if (!q) return;
  input.value = ''; input.style.height = 'auto';
  appendCustomerUserMsg(q);
  const tId = appendCustomerTyping();
  try {
    let res = await fetch(API + '/api/customer/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ question: q, client_id: CLIENT_ID }) });
    if (!res.ok) {
      res = await fetch(API + '/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ question: q, session_id: SESSION_ID, client_id: CLIENT_ID, user_id: 'customer', analytical:false, analytical_depth:'low', already_clarified:false }) });
    }
    removeCustomerTyping(tId);
    const data = await res.json().catch(()=>({success:false}));
    if (data.answer) appendCustomerBotMsg(data.answer);
    else appendCustomerBotMsg('Şu an size yardımcı olamadım. Lütfen biraz sonra tekrar deneyin.');
  } catch (e) {
    removeCustomerTyping(tId);
    appendCustomerBotMsg('Bağlantı kurulamadı. Telegram üzerinden ulaşmayı deneyebilirsiniz.');
  }
}

function appendCustomerUserMsg(t) {
  const c = document.getElementById('customerMessages');
  c.insertAdjacentHTML('beforeend', `
    <div class="flex justify-end fadeUp">
      <div class="bubble-user max-w-md inline-block">${escHtml(t)}</div>
    </div>`);
  c.parentElement.scrollTop = c.parentElement.scrollHeight;
}
function appendCustomerBotMsg(t) {
  const c = document.getElementById('customerMessages');
  c.insertAdjacentHTML('beforeend', `
    <div class="flex gap-3 fadeUp">
      <div class="logo-orb shrink-0" style="width:32px;height:32px;border-radius:9px"><svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg></div>
      <div class="flex-1"><div class="bubble-ai inline-block max-w-full">${formatText(t)}</div></div>
    </div>`);
  c.parentElement.scrollTop = c.parentElement.scrollHeight;
}
function appendCustomerTyping() {
  const c = document.getElementById('customerMessages');
  const id = 'ctyping_' + Date.now();
  c.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="flex gap-3 fadeIn">
      <div class="logo-orb shrink-0" style="width:32px;height:32px;border-radius:9px"><svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg></div>
      <div class="bubble-ai inline-flex items-center gap-1.5"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
    </div>`);
  c.parentElement.scrollTop = c.parentElement.scrollHeight;
  return id;
}
function removeCustomerTyping(id) { document.getElementById(id)?.remove(); }

/* ─── Helpers ──────────────────────────────────────────────────────────── */
function appendMsg(html) {
  const cont = document.getElementById('messages');
  if (!cont) return;
  const el = document.createElement('div');
  el.innerHTML = html;
  cont.appendChild(el.firstElementChild);
  cont.parentElement.scrollTop = cont.parentElement.scrollHeight;
}
function setLoading(v) { const b = document.getElementById('sendBtn'); if (b) b.disabled = v; }
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s) { return String(s).replace(/'/g, '&#39;').replace(/"/g, '&quot;'); }
function formatText(t) { if (!t) return ''; return escHtml(t).replace(/\n/g, '<br>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'); }
function timeStr() { return new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }); }
