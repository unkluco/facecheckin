// ─── STATE ─────────────────────────────────────────────
let currentClass = null;
let currentSession = null;
let wsConnected = false;
let dashboardRefreshInterval = null;
let attendanceRefreshInterval = null;
let ws = null;

// Dynamic server base URL — works both on localhost and when accessed from another device via IP
const SERVER_BASE = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
let API_TOKEN = new URLSearchParams(window.location.search).get('token') || localStorage.getItem('facecheckin_token') || '';
if (API_TOKEN) localStorage.setItem('facecheckin_token', API_TOKEN);

function setApiToken(token) {
  if (!token) return;
  if (API_TOKEN === token) return;
  API_TOKEN = token;
  localStorage.setItem('facecheckin_token', API_TOKEN);
}

function authHeaders(extra = {}) {
  return API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}`, ...extra } : extra;
}

function withToken(url) {
  if (!API_TOKEN) return url;
  const absolute = url.startsWith('http') ? url : `${SERVER_BASE}${url}`;
  const u = new URL(absolute);
  u.searchParams.set('token', API_TOKEN);
  return u.toString();
}

// ─── API HELPERS ────────────────────────────────────────
async function fetchAPI(endpoint, options = {}) {
  try {
    const url = endpoint.startsWith('http') ? endpoint : `${SERVER_BASE}/api${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: authHeaders({ 'Content-Type': 'application/json', ...options.headers })
    });

    if (!response.ok) {
      console.error(`API Error: ${response.status} ${response.statusText}`);
      showToast('API Error: Server offline or invalid request', 'error');
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error('Fetch error:', error);
    showToast('Connection Error: Cannot reach server', 'error');
    return null;
  }
}

// ─── UI HELPERS ─────────────────────────────────────────
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

function showGlobalLoading(title = 'Đang xử lý...', message = 'Vui lòng chờ trong giây lát, hệ thống đang hoàn tất tác vụ.') {
  const overlay = document.getElementById('globalLoadingOverlay');
  const titleEl = document.getElementById('globalLoadingTitle');
  const messageEl = document.getElementById('globalLoadingMessage');
  const progressEl = document.getElementById('globalLoadingProgress');
  if (titleEl) titleEl.textContent = title;
  if (messageEl) messageEl.textContent = message;
  if (progressEl) progressEl.classList.remove('active');
  if (overlay) overlay.classList.add('active');
}

function setGlobalLoadingProgress({ studentsDone = 0, studentsTotal = 0, facesDone = 0, facesTotal = 0 } = {}) {
  const progressEl = document.getElementById('globalLoadingProgress');
  const studentCountEl = document.getElementById('globalProgressStudentsCount');
  const faceCountEl = document.getElementById('globalProgressFacesCount');
  const studentFillEl = document.getElementById('globalProgressStudentsFill');
  const faceFillEl = document.getElementById('globalProgressFacesFill');
  const safeStudentTotal = Math.max(0, Number(studentsTotal) || 0);
  const safeFaceTotal = Math.max(0, Number(facesTotal) || 0);
  const rawStudentsDone = Math.max(0, Number(studentsDone) || 0);
  const rawFacesDone = Math.max(0, Number(facesDone) || 0);
  const cappedStudentsDone = Math.min(rawStudentsDone, safeStudentTotal || rawStudentsDone);
  const cappedFacesDone = Math.min(rawFacesDone, safeFaceTotal || rawFacesDone);
  const studentPct = safeStudentTotal ? Math.round((cappedStudentsDone / safeStudentTotal) * 100) : 0;
  const facePct = safeFaceTotal ? Math.round((cappedFacesDone / safeFaceTotal) * 100) : 0;
  if (studentCountEl) studentCountEl.textContent = `${rawStudentsDone} / ${safeStudentTotal}`;
  if (faceCountEl) faceCountEl.textContent = `${rawFacesDone} / ${safeFaceTotal}`;
  if (studentFillEl) studentFillEl.style.width = `${studentPct}%`;
  if (faceFillEl) faceFillEl.style.width = `${facePct}%`;
  if (progressEl) progressEl.classList.add('active');
}

function hideGlobalLoading() {
  const overlay = document.getElementById('globalLoadingOverlay');
  if (overlay) overlay.classList.remove('active');
}

function applyTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  const toggle = document.getElementById('uiDarkMode');
  if (toggle) toggle.checked = isDark;
}

function toggleDarkMode(enabled) {
  const theme = enabled ? 'dark' : 'light';
  localStorage.setItem('facecheckin_theme', theme);
  applyTheme(theme);
}

function loadThemePreference() {
  let theme = 'light';
  try { theme = localStorage.getItem('facecheckin_theme') || 'light'; } catch (e) {}
  applyTheme(theme);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

function jsStringAttr(value) {
  return escapeAttr(JSON.stringify(String(value ?? '')));
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove('active');
  if (modalId === 'addStudentModal') {
    const sel2 = document.getElementById('studentClassSelect2');
    const classGroup = sel2 ? sel2.closest('.form-group') : null;
    if (classGroup) classGroup.style.display = '';
  }
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.add('active');
  if (!modal.dataset.boundOverlayClose) {
    modal.addEventListener('click', function(e) {
      if (e.target === this) closeModal(modalId);
    });
    modal.dataset.boundOverlayClose = '1';
  }
}

function switchScreen(screenId, evt = null) {
  if (screenId !== 'lophoc' && !confirmLeaveLophocDraft()) return;
  if (screenId !== 'attendance') {
    closeLocalCamera();
    stopRealtimeAttendance();
  }
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const screenEl = document.getElementById(`screen-${screenId}`);
  if (screenEl) screenEl.classList.add('active');
  const navEl = evt?.target?.closest('.nav-item') || document.querySelector(`.nav-item[data-screen="${screenId}"]`);
  if (navEl) navEl.classList.add('active');
  if (screenId === 'lessons') {
    loadLessons();
  } else if (screenId === 'students') {
    loadStudentsGrid();
  } else if (screenId === 'lophoc') {
    loadLophoc();
  } else if (screenId === 'settings') {
    loadSettings();
  }
}

function updateClock() {
  const now = new Date();
  const clock = document.getElementById('clock');
  if (clock) clock.textContent = now.toLocaleTimeString('vi-VN');
}

function formatTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString('vi-VN');
}

function formatDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleDateString('vi-VN');
}

// ─── INITIALIZATION ─────────────────────────────────────
async function init() {
  loadThemePreference();
  updateClock();
  setInterval(updateClock, 1000);
  const today = new Date().toISOString().split('T')[0];
  const ldEl = document.getElementById('lessonDate');
  if (ldEl) ldEl.value = today;
  await loadServerInfo();
  await loadClasses();
  await loadLessons();
  connectWebSocket();
  updateConnectionStatus();
  loadRealtimeSettingsIntoUi();
}

// ─── CLASS MANAGEMENT ───────────────────────────────────
async function loadClasses() {
  const classes = await fetchAPI('/classes');
  if (!classes) return;

  // Auto-select the first class if none is set yet
  if (!currentClass && classes.length > 0) {
    currentClass = classes[0].id;
  }
  // Populate all modal/filter selects
  await loadClassesForModal();
}

async function loadClassesForModal() {
  const classes = await fetchAPI('/classes');
  if (!classes) return;

  [
    document.getElementById('studentClassSelect2'),
    document.getElementById('studentClassSelect'),
    document.getElementById('historyClassFilter'),
    document.getElementById('studentClassFilter')
  ].filter(Boolean).forEach(select => {
    const oldValue = select.value;
    select.innerHTML = '<option value="">Tất cả lớp</option>';
    classes.forEach(c => {
      const option = document.createElement('option');
      option.value = c.id; option.textContent = c.name;
      select.appendChild(option);
    });
    select.value = oldValue;
  });

  // Lesson class select (no "All" option)
  const lcs = document.getElementById('lessonClassSelect');
  if (lcs) {
    lcs.innerHTML = '';
    classes.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id; opt.textContent = c.name;
      lcs.appendChild(opt);
    });
  }
}


async function saveClass() {
  const name = document.getElementById('className').value.trim();
  const descEl = document.getElementById('classDescription');
  const desc = descEl ? descEl.value.trim() : '';

  if (!name) {
    showToast('Please enter class name', 'error');
    return;
  }

  const result = await fetchAPI('/classes', {
    method: 'POST',
    body: JSON.stringify({ name, description: desc || null })
  });

  if (result) {
    showToast('Đã tạo lớp học', 'success');
    closeModal('addClassModal');
    document.getElementById('className').value = '';
    if (document.getElementById('classDescription')) document.getElementById('classDescription').value = '';
    await loadClasses();
    await loadClassesForModal();
    // Refresh lophoc if active
    const lophocScreen = document.getElementById('screen-lophoc');
    if (lophocScreen && lophocScreen.classList.contains('active')) loadLophoc();
  }
}

async function deleteClass(id) {
  if (!confirm('Xóa lớp học này? Toàn bộ sinh viên trong lớp cũng sẽ bị xóa.')) return;
  const result = await fetchAPI(`/classes/${id}`, { method: 'DELETE' });
  if (result !== null) {
    showToast('Đã xóa lớp học', 'success');
    await loadClasses();
    await loadClassesForModal();
    // Refresh lophoc screen if it is active
    const lophocScreen = document.getElementById('screen-lophoc');
    if (lophocScreen && lophocScreen.classList.contains('active')) {
      loadLophoc();
    }
  }
}

// ─── LESSONS ──────────────────────────────────────────────
let currentLessonId = null;
let _fillParsedRows = [];

async function loadLessons() {
  const lessons = await fetchAPI('/lessons');
  const container = document.getElementById('lessonsList');
  if (!container) return;
  if (!lessons || !lessons.length) {
    container.innerHTML = '<div style="text-align:center; color:var(--text3); padding:40px; font-size:13px;">Chưa có tiết học nào. Bấm "+ Tạo tiết học" để bắt đầu.</div>';
    return;
  }
  container.innerHTML = lessons.map(l => {
    const dateStr = l.date ? new Date(l.date + 'T00:00').toLocaleDateString('vi-VN') : '';
    return `
    <div class="lesson-card">
      <div style="flex:1; min-width:0;">
        <div class="lesson-card-title">${escapeHtml(l.name)}</div>
        <div class="lesson-card-meta">${escapeHtml(l.class_name || '')} · ${escapeHtml(dateStr)}</div>
        <div class="lesson-card-count">Điểm danh: ${l.attended}/${l.total_students}</div>
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn btn-primary" style="font-size:12px; padding:8px 13px;" onclick="enterLesson(${l.id})">Vào tiết</button>
        <button class="btn btn-danger" style="font-size:12px; padding:8px 13px;" onclick="deleteLesson(${l.id})">Xóa</button>
      </div>
    </div>`;
  }).join('');
}

async function createLesson() {
  const name = document.getElementById('lessonName').value.trim();
  const classId = parseInt(document.getElementById('lessonClassSelect').value);
  const date = document.getElementById('lessonDate').value;
  if (!name || !classId) { showToast('Vui lòng nhập đủ thông tin', 'error'); return; }
  const result = await fetchAPI('/lessons', {
    method: 'POST',
    body: JSON.stringify({ name, class_id: classId, date })
  });
  if (result) {
    showToast('Đã tạo tiết học', 'success');
    document.getElementById('lessonName').value = '';
    closeModal('createLessonModal');
    await loadLessons();
  }
}

async function deleteLesson(id) {
  if (!confirm('Xóa tiết học này và toàn bộ điểm danh?')) return;
  await fetchAPI(`/lessons/${id}`, { method: 'DELETE' });
  const feedKey = lessonFeedHistoryKey(id);
  if (feedKey) localStorage.removeItem(feedKey);
  showToast('Đã xóa tiết học', 'success');
  await loadLessons();
}

async function enterLesson(lessonId) {
  closeLocalCamera();
  stopRealtimeAttendance();
  currentLessonId = lessonId;
  const lessons = await fetchAPI('/lessons');
  const lesson = (lessons || []).find(l => l.id === lessonId);
  if (!lesson) return;
  // Auto-start lesson on server so active_lesson_id is set → attendance gets recorded
  await fetchAPI(`/lessons/${lessonId}/start`, { method: 'POST' });
  // Update UI header
  document.getElementById('lessonTitle').textContent = lesson.name;
  document.getElementById('lessonSubtitle').textContent = `${lesson.class_name} · ${lesson.date}`;
  // Switch to attendance screen, default to camera tab
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('screen-attendance').classList.add('active');
  switchAttendanceTab('camera');
  // Restore previous capture feed for this lesson and clear current tags.
  loadLessonFeedHistory(lessonId);
  const tagsEl = document.getElementById('lessonStudentTags');
  if (tagsEl) tagsEl.innerHTML = '';
  // Load existing attendance stats
  await refreshLessonStats();
  // Update export link
  const exportLink = document.getElementById('exportCsvLink');
  if (exportLink) exportLink.href = withToken(`/api/lessons/${lessonId}/export/csv`);
  loadServerInfo();
  updateLocalCameraUi(false);
}

async function refreshLessonStats() {
  if (!currentLessonId) return;
  const records = await fetchAPI(`/lessons/${currentLessonId}/attendance`);
  const lessons = await fetchAPI('/lessons');
  const lesson = (lessons || []).find(l => l.id === currentLessonId);
  document.getElementById('lessonAttendedCount').textContent = records?.length ?? 0;
  document.getElementById('lessonTotalCount').textContent = `/ ${lesson?.total_students ?? 0} sinh viên`;
  // Render student name tags
  const tagsEl = document.getElementById('lessonStudentTags');
  if (tagsEl) {
    if (!records || records.length === 0) {
      tagsEl.innerHTML = '<span style="font-size:11px; color:var(--text3); font-style:italic;">Chưa có sinh viên nào điểm danh</span>';
    } else {
      tagsEl.innerHTML = records.map(r =>
        `<span style="font-size:11px; background:rgba(204,120,92,.12); color:var(--teal); border:1px solid rgba(204,120,92,.3); border-radius:14px; padding:3px 10px; white-space:nowrap; cursor:default;" title="${r.folder_name}">${r.full_name || r.folder_name}</span>`
      ).join('');
    }
  }
}

// ─── ATTENDANCE SUB-TABS ────────────────────────────────
let _manualStudentsAll = []; // cache for filter
const manualPending = new Set();
let isCapturing = false;
let currentAttendanceTab = 'camera';

function switchAttendanceTab(tab) {
  const camPanel  = document.getElementById('tabPanelCamera');
  const manPanel  = document.getElementById('tabPanelManual');
  const realtimePanel = document.getElementById('tabPanelRealtime');
  const camBtn    = document.getElementById('tabBtnCamera');
  const manBtn    = document.getElementById('tabBtnManual');
  const realtimeBtn = document.getElementById('tabBtnRealtime');
  if (!camPanel || !manPanel || !realtimePanel) return;

  if (currentAttendanceTab === 'camera' && tab !== 'camera') {
    closeLocalCamera();
  }
  if (currentAttendanceTab === 'realtime' && tab !== 'realtime') {
    stopRealtimeAttendance();
  }
  currentAttendanceTab = tab;

  camPanel.style.display = tab === 'camera' ? 'flex' : 'none';
  manPanel.style.display = tab === 'manual' ? 'flex' : 'none';
  realtimePanel.style.display = tab === 'realtime' ? 'flex' : 'none';

  camBtn.className = tab === 'camera' ? 'btn btn-primary attendance-tab-btn' : 'btn btn-ghost attendance-tab-btn';
  manBtn.className = tab === 'manual' ? 'btn btn-primary attendance-tab-btn' : 'btn btn-ghost attendance-tab-btn';
  realtimeBtn.className = tab === 'realtime' ? 'btn btn-primary attendance-tab-btn' : 'btn btn-ghost attendance-tab-btn';

  if (tab === 'camera') {
    updateLocalCameraUi(!!localStream);
  } else if (tab === 'manual') {
    loadManualAttendance();
  } else if (tab === 'realtime') {
    loadRealtimeSettingsIntoUi();
  }
}

async function loadManualAttendance() {
  if (!currentLessonId) return;
  const list = document.getElementById('manualAttendanceList');
  if (list) list.innerHTML = '<div style="text-align:center; color:var(--text3); padding:40px;">Đang tải...</div>';

  // Fetch lesson info + attendance records + all students in class in parallel
  const [records, lessonArr] = await Promise.all([
    fetchAPI(`/lessons/${currentLessonId}/attendance`),
    fetchAPI('/lessons')
  ]);
  const lesson = (lessonArr || []).find(l => l.id === currentLessonId);
  if (!lesson) return;
  const students = await fetchAPI(`/students?class_id=${lesson.class_id}`);
  if (!students) return;

  const attendedIds = new Set((records || []).map(r => r.student_id));
  _manualStudentsAll = students.map(s => ({ ...s, attended: attendedIds.has(s.id) }));

  // Update counter
  document.getElementById('manualAttendedCount').textContent = attendedIds.size;
  document.getElementById('manualTotalCount').textContent = `/ ${students.length}`;

  renderManualList(_manualStudentsAll);
}

function renderManualList(students) {
  const list = document.getElementById('manualAttendanceList');
  if (!list) return;
  if (!students.length) {
    list.innerHTML = '<div style="text-align:center; color:var(--text3); padding:40px; font-size:13px;">Không có sinh viên nào trong lớp</div>';
    return;
  }
  list.innerHTML = students.map(s => {
    const checked = s.attended;
    return `
    <div id="manual-row-${s.id}" style="display:flex; align-items:center; gap:12px; padding:8px 12px; background:#fff; border-radius:8px; border:1px solid ${checked ? 'rgba(204,120,92,.45)' : 'var(--border)'}; box-shadow:0 1px 4px rgba(204,120,92,.08); transition:border-color .15s; cursor:pointer;" onclick="toggleManualAttendance(${s.id})">
      <div style="width:28px; height:28px; border-radius:50%; border:2px solid ${checked ? 'var(--teal)' : 'var(--border2)'}; background:${checked ? 'var(--teal-dim)' : 'transparent'}; display:flex; align-items:center; justify-content:center; flex-shrink:0; transition:all .2s;">
        ${checked ? '<span style="color:var(--teal); font-size:14px; font-weight:700;">✓</span>' : ''}
      </div>
      <div style="flex:1; min-width:0;">
        <div style="font-size:13px; font-weight:${checked ? '600' : '400'}; color:${checked ? 'var(--text1)' : 'var(--text2)'}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${s.full_name || '—'}</div>
        <div style="font-size:11px; color:var(--text3); font-family:monospace;">${s.folder_name || '—'}</div>
      </div>
      <span style="font-size:11px; font-weight:600; color:${checked ? 'var(--teal)' : 'var(--text3)'}; flex-shrink:0;">${checked ? 'Có mặt' : 'Vắng'}</span>
    </div>`;
  }).join('');
}

function filterManualList() {
  const q = (document.getElementById('manualSearchInput')?.value || '').toLowerCase();
  const status = document.getElementById('manualStatusFilter')?.value || 'all';
  const filtered = _manualStudentsAll.filter(s => {
    const matchText = !q ||
      (s.full_name || '').toLowerCase().includes(q) ||
      (s.folder_name || '').toLowerCase().includes(q);
    const matchStatus =
      status === 'all' ||
      (status === 'attended' && s.attended) ||
      (status === 'absent' && !s.attended);
    return matchText && matchStatus;
  });
  renderManualList(filtered);
}

async function toggleManualAttendance(studentId) {
  if (!currentLessonId || manualPending.has(studentId)) return;
  const lessonId = currentLessonId;
  const student = _manualStudentsAll.find(s => s.id === studentId);
  if (!student) return;

  manualPending.add(studentId);
  try {
    let result;
    if (student.attended) {
      result = await fetchAPI(`/lessons/${lessonId}/attendance/${studentId}`, { method: 'DELETE' });
      if (!result) return;
      if (lessonId !== currentLessonId) return;
      student.attended = false;
      showToast(`Đã bỏ điểm danh: ${student.full_name || student.folder_name}`, 'warning');
    } else {
      result = await fetchAPI(`/lessons/${lessonId}/attendance/manual`, {
        method: 'POST',
        body: JSON.stringify({ student_id: studentId })
      });
      if (!result) return;
      if (lessonId !== currentLessonId) return;
      student.attended = true;
      showToast(`Đã điểm danh: ${student.full_name || student.folder_name}`, 'success');
    }

    const attendedCount = _manualStudentsAll.filter(s => s.attended).length;
    document.getElementById('manualAttendedCount').textContent = attendedCount;
    await refreshLessonStats();
    filterManualList();
  } finally {
    manualPending.delete(studentId);
  }
}

// Keep these stubs so any old references don't crash
async function startCurrentLesson() {}
async function stopCurrentLesson() {}

async function exitAttendance() {
  const lessonId = currentLessonId;
  closeLocalCamera();
  stopRealtimeAttendance();
  if (lessonId) {
    const stopped = await fetchAPI(`/lessons/${lessonId}/stop`, { method: 'POST' });
    if (!stopped) {
      showToast('Không thể dừng tiết học trên server', 'error');
      return;
    }
  }
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-lessons').classList.add('active');
  document.querySelectorAll('.nav-item')[0]?.classList.add('active');
  currentLessonId = null;
  loadLessons();
}

// ─── EXPORT LESSON ─────────────────────────────────────
function openExportModal() {
  if (!currentLessonId) { showToast('Chưa chọn tiết học', 'error'); return; }
  setExportMode('new');
  openModal('exportLessonModal');
}

function setExportMode(mode) {
  document.getElementById('exportModeNew').style.display = mode === 'new' ? '' : 'none';
  document.getElementById('exportModeFill').style.display = mode === 'fill' ? '' : 'none';
  document.getElementById('exportModeNewBtn').className = mode === 'new' ? 'btn btn-primary' : 'btn btn-ghost';
  document.getElementById('exportModeFillBtn').className = mode === 'fill' ? 'btn btn-primary' : 'btn btn-ghost';
  document.getElementById('exportModeNewBtn').style.flex = '1';
  document.getElementById('exportModeFillBtn').style.flex = '1';
  document.getElementById('exportModeNewBtn').style.fontSize = '12px';
  document.getElementById('exportModeFillBtn').style.fontSize = '12px';
}

async function exportLessonCsvWithTick() {
  // Tạo CSV mới với tick symbol đã chọn (giống XLSX nhưng định dạng CSV)
  if (!currentLessonId) return;
  const records = await fetchAPI(`/lessons/${currentLessonId}/attendance`);
  const lessons = await fetchAPI('/lessons');
  const lesson = (lessons || []).find(l => l.id === currentLessonId);
  const students = lesson ? (await fetchAPI(`/students?class_id=${lesson.class_id}`) || []) : [];
  const attendedSet = new Set((records || []).map(r => r.folder_name));
  const lessonDate = lesson?.date || 'Điểm danh';
  const tickSym = document.getElementById('newTickSymbol')?.value || '✓';
  const rows = [['MSSV', 'Họ tên', lessonDate]];
  students.forEach(s => {
    rows.push([s.folder_name, s.full_name, attendedSet.has(s.folder_name) ? tickSym : '']);
  });
  const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], {type: 'text/csv'}));
  a.download = `${lesson?.name || 'diemdanh'}.csv`;
  a.click();
}

async function exportLessonXlsx() {
  if (!currentLessonId || typeof XLSX === 'undefined') {
    showToast('Thư viện XLSX chưa sẵn sàng, thử xuất CSV', 'error'); return;
  }
  const records = await fetchAPI(`/lessons/${currentLessonId}/attendance`);
  const lessons = await fetchAPI('/lessons');
  const lesson = (lessons || []).find(l => l.id === currentLessonId);
  const students = lesson ? (await fetchAPI(`/students?class_id=${lesson.class_id}`) || []) : [];
  const attendedSet = new Set((records || []).map(r => r.folder_name));
  // Header: cột điểm danh = ngày tiết học
  const lessonDate = lesson?.date || 'Điểm danh';
  const tickSym = document.getElementById('newTickSymbol')?.value || '✓';
  const rows = [['MSSV', 'Họ tên', lessonDate]];
  students.forEach(s => {
    rows.push([s.folder_name, s.full_name, attendedSet.has(s.folder_name) ? tickSym : '']);
  });
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(rows);
  XLSX.utils.book_append_sheet(wb, ws, 'Điểm danh');
  XLSX.writeFile(wb, `${lesson?.name || 'diemdanh'}.xlsx`);
}

function previewFillFile(input) {
  const file = input.files[0];
  if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext === 'xlsx' || ext === 'xls') {
    if (typeof XLSX === 'undefined') { showToast('XLSX chưa tải, dùng CSV', 'error'); return; }
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        _fillParsedRows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' }).map(r => r.map(c => String(c ?? '').trim()));
        _renderFillPreview(_fillParsedRows);
      } catch(err) { showToast('Lỗi đọc XLSX: ' + err.message, 'error'); }
    };
    reader.readAsArrayBuffer(file);
  } else {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        _fillParsedRows = _parseCSVText(e.target.result);
        _renderFillPreview(_fillParsedRows);
      } catch(err) { showToast('Lỗi đọc CSV: ' + err.message, 'error'); }
    };
    reader.readAsText(file, 'UTF-8');
  }
}

function _renderFillPreview(rows) {
  const preview = rows.slice(0, 5).filter(r => r.some(c => c));
  if (!preview.length) return;
  const numCols = Math.max(...preview.map(r => r.length));
  const options = Array.from({length: numCols}, (_, i) => {
    const h = preview[0][i] || '';
    return `<option value="${i}">Cột ${i+1}${h ? ' — ' + h : ''}</option>`;
  }).join('');

  const mssvSel = document.getElementById('fillMssvCol');
  const attSel  = document.getElementById('fillAttCol');
  mssvSel.innerHTML = options;
  // fillAttCol: thêm lựa chọn "Cột mới (sau cột cuối)" ở đầu danh sách
  attSel.innerHTML = `<option value="-1">📌 Cột mới (thêm sau cột cuối)</option>` + options;
  // Mặc định chọn "Cột mới"
  attSel.value = '-1';

  // Render preview table với id cho từng cell để có thể highlight
  const tbl = document.getElementById('fillPreviewTable');
  tbl.innerHTML = preview.map((row, ri) => {
    const tag = ri === 0 ? 'th' : 'td';
    return `<tr>${Array.from({length: numCols}, (_, ci) => {
      const c = row[ci] ?? '';
      return `<${tag} id="fillcell_${ri}_${ci}" style="padding:2px 8px;border:1px solid var(--border);white-space:nowrap;max-width:120px;overflow:hidden;text-overflow:ellipsis;font-size:11px;" title="${c}">${c}</${tag}>`;
    }).join('')}</tr>`;
  }).join('');

  // Hàm highlight cột đang chọn
  function _highlightFillCols() {
    const mc = parseInt(mssvSel.value);
    const ac = parseInt(attSel.value);
    for (let ri = 0; ri < preview.length; ri++) {
      for (let ci = 0; ci < numCols; ci++) {
        const cell = document.getElementById(`fillcell_${ri}_${ci}`);
        if (!cell) continue;
        const base = ri === 0 ? 'var(--surface2)' : (ri % 2 ? '' : 'rgba(204,120,92,.04)');
        if (ci === mc)       cell.style.background = 'rgba(0,200,150,.2)';   // xanh lá = MSSV
        else if (ci === ac)  cell.style.background = 'rgba(255,160,50,.25)'; // cam = điểm danh
        else                 cell.style.background = base;
      }
    }
  }

  mssvSel.onchange = _highlightFillCols;
  attSel.onchange  = _highlightFillCols;
  _highlightFillCols();

  document.getElementById('fillColumnPicker').style.display = 'block';
}

async function downloadFilledFile() {
  if (!_fillParsedRows.length) { showToast('Vui lòng chọn file trước', 'error'); return; }
  const mssvCol = parseInt(document.getElementById('fillMssvCol').value);
  const attColRaw = document.getElementById('fillAttCol').value;
  const attCol = (attColRaw === '-1') ? -1 : parseInt(attColRaw);
  const hasHeader = parseInt(document.getElementById('fillHasHeader').value);
  const skipRows = parseInt(document.getElementById('fillSkipRows').value || '0');
  const prependRows = parseInt(document.getElementById('fillPrependRows').value || '0');
  const tickSymbol = document.getElementById('fillTickSymbol').value || '✓';
  const result = await fetchAPI(`/lessons/${currentLessonId}/export/fill`, {
    method: 'POST',
    body: JSON.stringify({
      rows: _fillParsedRows,
      mssv_col: mssvCol,
      att_col: attCol,
      has_header: !!hasHeader,
      skip_rows: skipRows,
      prepend_rows: prependRows,
      tick_symbol: tickSymbol
    })
  });
  if (!result) return;
  const outRows = result.rows;
  if (typeof XLSX !== 'undefined') {
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(outRows);
    XLSX.utils.book_append_sheet(wb, ws, 'Điểm danh');
    XLSX.writeFile(wb, 'filled_attendance.xlsx');
  } else {
    // Fallback: download as CSV
    const csv = outRows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], {type: 'text/csv'}));
    a.download = 'filled_attendance.csv'; a.click();
  }
  showToast(`Đã điền ${result.matched} bản ghi`, 'success');
}

// ─── DASHBOARD ──────────────────────────────────────────
async function loadDashboard() {
  if (!currentClass) return;

  const today = new Date().toISOString().split('T')[0];
  const stats = await fetchAPI(`/stats?class_id=${currentClass}&date=${today}`);
  if (!stats) return;

  // Use both alias names for max compatibility
  animateCounter('stat-today', parseInt(stats.today ?? stats.present ?? 0));
  animateCounter('stat-total', parseInt(stats.total ?? stats.total_students ?? 0));
  const pct = stats.percentage ?? Math.round((stats.attendance_rate || 0) * 100);
  document.getElementById('stat-percentage').textContent = `${pct}%`;
  animateCounter('stat-detections', parseInt(stats.detections ?? stats.present ?? 0));

  // Load real-time attendance table (records come from stats OR separate call)
  const attendance = stats.records?.length
    ? stats.records
    : (await fetchAPI(`/attendance/today?class_id=${currentClass}`) || []);

  const tbody = document.getElementById('attendanceTableBody');
  if (!attendance.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text2)">Chưa có điểm danh hôm nay</td></tr>';
    return;
  }
  tbody.innerHTML = attendance.slice(0, 10).map(record => `
    <tr>
      <td class="name-col">${record.name || record.full_name || 'Unknown'}</td>
      <td class="time-col">${formatTime(record.timestamp)}</td>
      <td><span style="color: var(--teal); font-size: 10px;">✓ Present</span></td>
      <td>${record.confidence ? (record.confidence * 100).toFixed(0) : '-'}%</td>
    </tr>
  `).join('');
}

function animateCounter(elementId, targetValue) {
  const element = document.getElementById(elementId);
  const currentValue = parseInt(element.textContent) || 0;
  const increment = Math.ceil((targetValue - currentValue) / 10);
  let displayValue = currentValue;

  const counter = setInterval(() => {
    displayValue += increment;
    if (
      (increment > 0 && displayValue >= targetValue) ||
      (increment < 0 && displayValue <= targetValue)
    ) {
      displayValue = targetValue;
      clearInterval(counter);
    }
    element.textContent = displayValue;
  }, 50);
}

// ─── ATTENDANCE (legacy stubs — kept for backward compat) ─
async function startSession() { showToast('Hãy sử dụng tiết học để điểm danh', 'error'); }
async function stopSession() {}
function onAttendanceClassChange() {}
async function loadLatestAttendanceImage() { /* no-op */ }

// ─── STUDENT GRID (Search screen) ───────────────────────
let _allStudentsCache = [];

async function loadStudentsGrid() {
  await loadClassesForModal(); // populate filter dropdown

  const grid = document.getElementById('studentGrid');
  if (!grid) return;
  grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text3);padding:60px;font-size:13px;">Đang tải...</div>';

  // Fetch all students across all classes
  const classes = await fetchAPI('/classes');
  if (!classes) { grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text3);padding:60px;">Lỗi tải dữ liệu</div>'; return; }

  const allStudents = [];
  await Promise.all(classes.map(async cls => {
    try {
      const students = await fetchAPI(`/students?class_id=${cls.id}`);
      (students || []).forEach(s => allStudents.push({ ...s, class_name: cls.name }));
    } catch {}
  }));

  _allStudentsCache = allStudents;
  renderStudentGrid(allStudents);
}

function renderStudentGrid(students) {
  const grid = document.getElementById('studentGrid');
  const countEl = document.getElementById('studentGridCount');
  if (!grid) return;
  if (countEl) countEl.textContent = `${students.length} sinh viên`;

  if (!students.length) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text3);padding:60px;font-size:13px;">Không tìm thấy sinh viên nào</div>';
    return;
  }

  grid.innerHTML = students.map(s => {
    const folder = encodeURIComponent(s.folder_name || '');
    const imgSrc = s.folder_name ? withToken(`/api/face-image/${folder}/_first`) + (withToken(`/api/face-image/${folder}/_first`).includes('?') ? '&' : '?') + `t=${Date.now()}` : '';
    const initial = (s.full_name || s.folder_name || '?').charAt(0).toUpperCase();
    return `
    <div class="student-card" onclick="openFaceRegistration(${s.id},'${(s.full_name||'').replace(/'/g,"\\'")}','${(s.folder_name||'').replace(/'/g,"\\'")}', true)">
      <div class="student-card-photo" style="position:relative; overflow:hidden;">
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:38px;font-weight:700;color:var(--teal);font-family: var(--font-sans);">${initial}</div>
        ${s.folder_name ? `<img src="${imgSrc}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;" onerror="this.remove()">` : ''}
      </div>
      <div class="student-card-info">
        <div class="student-card-name" title="${s.full_name||''}">${s.full_name||'—'}</div>
        <div class="student-card-sub">${s.folder_name||'—'}</div>
        <div style="font-size:10px;color:var(--teal);opacity:.75;margin-top:5px;">📚 ${s.class_name||'—'}</div>
      </div>
    </div>`;
  }).join('');
}

function onStudentSearch() {
  const query = (document.getElementById('studentSearchInput')?.value || '').toLowerCase();
  const classFilter = document.getElementById('studentClassFilter')?.value || '';
  let filtered = _allStudentsCache;
  if (query) filtered = filtered.filter(s =>
    (s.full_name||'').toLowerCase().includes(query) ||
    (s.folder_name||'').toLowerCase().includes(query)
  );
  if (classFilter) filtered = filtered.filter(s => String(s.class_id) === String(classFilter));
  renderStudentGrid(filtered);
}

// ─── STUDENTS (legacy table — still used internally) ─────
async function loadStudents() {
  const sel = document.getElementById('studentClassSelect');
  // Nếu chưa có giá trị, tự động chọn currentClass
  if (sel && !sel.value && currentClass) sel.value = String(currentClass);
  const classId = sel?.value || currentClass;

  const tbody = document.getElementById('studentsTableBody');
  if (!classId) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text3); padding:40px;">Chọn lớp để xem sinh viên</td></tr>';
    return;
  }

  const students = await fetchAPI(`/students?class_id=${classId}`);
  if (!students) return;

  const countEl = document.getElementById('studentCount');
  if (countEl) countEl.textContent = `${students.length} sinh viên`;

  if (!tbody) return;
  if (!students.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text3); padding:40px;">Chưa có sinh viên trong lớp này</td></tr>';
    return;
  }
  tbody.innerHTML = students.map((s, idx) => `
    <tr style="border-bottom:1px solid var(--border); ${idx % 2 === 0 ? '' : 'background:rgba(204,120,92,.04);'}">
      <td style="padding:8px 12px; color:var(--text3);">${s.id}</td>
      <td style="padding:8px 12px; color:var(--text1); font-weight:500;">${s.full_name || s.name || '—'}</td>
      <td style="padding:8px 12px; font-family:monospace; font-size:11px; color:var(--text2);">${s.folder_name || '-'}</td>
      <td style="padding:6px 12px;">
        <div style="display:flex; gap:5px; flex-wrap:wrap;">
          <button class="btn btn-ghost" style="font-size:11px; padding:3px 8px; border:1px solid var(--teal); color:var(--teal);" onclick="openFaceRegistration(${s.id}, '${(s.full_name || s.name || '').replace(/'/g,"\\'")}', '${(s.folder_name || '').replace(/'/g,"\\'")}')">📷 Ảnh</button>
          <button class="btn btn-danger" style="font-size:11px; padding:3px 8px;" onclick="deleteStudent('${s.id}')">Xóa</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function onStudentsClassChange() {
  loadStudents();
}

async function saveStudent() {
  const studentCode = document.getElementById('studentId')?.value.trim() || '';
  const name = document.getElementById('studentName').value.trim();
  const classId = document.getElementById('studentClassSelect2').value;
  const folder = studentCode;

  if (!studentCode || !name || !classId) {
    showToast('Vui lòng nhập mã sinh viên, tên và chọn lớp', 'error');
    return;
  }

  if (_lophocCurrentClassId && String(classId) === String(_lophocCurrentClassId) && _lophocDraft) {
    const tempId = _lophocDraft.nextTempId--;
    _lophocDraft.students.push({
      id: tempId,
      full_name: name,
      folder_name: folder,
      class_id: _lophocCurrentClassId,
      _draftNew: true,
    });
    markLophocDraftDirty();
    closeModal('addStudentModal');
    document.getElementById('studentId') && (document.getElementById('studentId').value = '');
    document.getElementById('studentName').value = '';
    renderLophocDraftDetail();
    showToast('Đã thêm sinh viên vào bản nháp', 'success');
    return;
  }

  const result = await fetchAPI('/students', {
    method: 'POST',
    body: JSON.stringify({
      full_name: name,
      class_id: parseInt(classId),
      folder_name: folder
    })
  });

  if (result) {
    showToast('Đã thêm sinh viên', 'success');
    closeModal('addStudentModal');
    document.getElementById('studentId') && (document.getElementById('studentId').value = '');
    document.getElementById('studentName').value = '';
    // Refresh whichever view is active
    if (_lophocCurrentClassId) await refreshLophocDetail();
    else loadStudentsGrid();
  }
}

async function deleteStudent(id) {
  if (!confirm('Xóa sinh viên này?')) return;
  const result = await fetchAPI(`/students/${id}`, { method: 'DELETE' });
  if (result !== null) {
    showToast('Đã xóa sinh viên', 'success');
    if (_lophocCurrentClassId) await refreshLophocDetail();
    else loadStudentsGrid();
  }
}

function editStudent(id) {
  // Placeholder - implement full edit modal if needed
  showToast('Edit functionality coming soon', 'warning');
}

// ─── LỚP HỌC SCREEN ─────────────────────────────────────
let _lophocCurrentClassId = null;
let _lophocCurrentClassName = '';
let _lophocDraft = null;

function resetLophocDraft() {
  _lophocDraft = {
    baseStudents: [],
    students: [],
    deletedIds: new Set(),
    faceChanges: new Map(),
    dirty: false,
    nextTempId: -1,
  };
  updateLophocDraftUi();
}

function updateLophocDraftUi() {
  const dirtyBadge = document.getElementById('lophocDraftDirtyBadge');
  const actionBar = document.getElementById('lophocDraftActionBar');
  if (dirtyBadge) dirtyBadge.style.display = _lophocDraft?.dirty ? 'inline-flex' : 'none';
  if (actionBar) actionBar.style.display = _lophocDraft?.dirty ? 'flex' : 'none';
}

function markLophocDraftDirty() {
  if (_lophocDraft) _lophocDraft.dirty = true;
  updateLophocDraftUi();
}

function ensureFaceChange(studentId) {
  const key = String(studentId);
  if (!_lophocDraft.faceChanges.has(key)) {
    _lophocDraft.faceChanges.set(key, { addFiles: [], deleteFiles: new Set() });
  }
  return _lophocDraft.faceChanges.get(key);
}

function hasUnsavedLophocChanges() {
  return !!(_lophocCurrentClassId && _lophocDraft?.dirty);
}

function confirmLeaveLophocDraft() {
  if (!hasUnsavedLophocChanges()) return true;
  showToast('Bạn có thay đổi chưa lưu. Hãy bấm Lưu thay đổi hoặc Hủy thay đổi trước.', 'warning');
  return false;
}

async function loadLophoc() {
  _lophocCurrentClassId = null;
  showLophocView('list');
  const listView = document.getElementById('lophocListView');
  if (!listView) return;
  listView.innerHTML = '<div style="text-align:center;color:var(--text3);padding:40px;font-size:13px;">Đang tải...</div>';

  const classes = await fetchAPI('/classes');
  if (!classes) { listView.innerHTML = '<div style="text-align:center;color:var(--text3);padding:40px;">Lỗi tải dữ liệu</div>'; return; }

  if (!classes.length) {
    listView.innerHTML = '<div style="text-align:center;color:var(--text3);padding:40px;font-size:13px;">Chưa có lớp nào. Bấm "+ Tạo lớp trống" để bắt đầu.</div>';
    return;
  }

  // Fetch student counts
  const counts = {};
  await Promise.all(classes.map(async c => {
    try { const s = await fetchAPI(`/students?class_id=${c.id}`); counts[c.id] = s?.length ?? 0; } catch { counts[c.id] = 0; }
  }));

  listView.innerHTML = classes.map(c => {
    const className = escapeHtml(c.name || '');
    const classNameArg = jsStringAttr(c.name || '');
    const description = c.description ? ' · ' + escapeHtml(c.description) : '';
    const csvUrl = escapeAttr(withToken(`/api/classes/${c.id}/export/csv`));
    const facesUrl = escapeAttr(withToken(`/api/classes/${c.id}/export/faces`));
    return `
    <div class="class-row" style="padding:14px 16px; gap:12px; justify-content:space-between;" onclick="enterClassDetail(${c.id}, ${classNameArg}, ${counts[c.id]||0})">
      <div style="display:flex; align-items:center; gap:12px; flex:1; min-width:0;">
        <div style="width:38px;height:38px;border-radius:10px;background:var(--teal-dim);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;">🏫</div>
        <div style="min-width:0;">
          <div style="font-size:13px;font-weight:600;color:var(--text1);">${className}</div>
          <div style="font-size:11px;color:var(--text3);margin-top:1px;">${counts[c.id]||0} sinh viên${description}</div>
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;" onclick="event.stopPropagation()">
        <a href="${csvUrl}" download
           class="btn btn-ghost" style="font-size:10px;padding:4px 10px;text-decoration:none;">📄 CSV</a>
        <a href="${facesUrl}" download
           class="btn btn-ghost" style="font-size:10px;padding:4px 10px;text-decoration:none;">🖼 Ảnh</a>
        <button class="btn btn-danger" style="font-size:10px;padding:4px 10px;" onclick="deleteClass(${c.id})">Xóa</button>
      </div>
      <span style="color:var(--text3);font-size:16px;pointer-events:none;">›</span>
    </div>`;
  }).join('');
}

function showLophocView(view) {
  const listV = document.getElementById('lophocListView');
  const detailV = document.getElementById('lophocDetailView');
  const detailTools = document.getElementById('lophocDetailTools');
  const listH = document.getElementById('lophocListHeader');
  const detailH = document.getElementById('lophocDetailHeader');
  if (!listV || !detailV || !listH || !detailH) return;
  if (view === 'list') {
    listV.style.display = 'flex';
    detailV.style.display = 'none';
    if (detailTools) detailTools.style.display = 'none';
    listH.style.display = 'flex';
    detailH.style.display = 'none';
  } else {
    listV.style.display = 'none';
    detailV.style.display = 'flex';
    if (detailTools) detailTools.style.display = 'block';
    listH.style.display = 'none';
    detailH.style.display = 'flex';
  }
}

async function enterClassDetail(classId, className, studentCount) {
  _lophocCurrentClassId = classId;
  _lophocCurrentClassName = className;
  document.getElementById('lophocDetailTitle').textContent = className;
  document.getElementById('lophocDetailSub').textContent = `${studentCount} sinh viên`;
  const searchInput = document.getElementById('lophocDetailSearchInput');
  if (searchInput) searchInput.value = '';
  showLophocView('detail');
  await refreshLophocDetail();
}

async function refreshLophocDetail() {
  const view = document.getElementById('lophocDetailView');
  if (!view || !_lophocCurrentClassId) return;
  view.innerHTML = '<div style="text-align:center;color:var(--text3);padding:40px;font-size:13px;">Đang tải...</div>';

  const students = await fetchAPI(`/students?class_id=${_lophocCurrentClassId}`);
  if (!students) { view.innerHTML = '<div style="text-align:center;color:var(--text3);padding:40px;">Lỗi tải dữ liệu</div>'; return; }
  resetLophocDraft();
  _lophocDraft.baseStudents = students.map(s => ({ ...s }));
  _lophocDraft.students = students.map(s => ({ ...s, _draftNew: false }));
  renderLophocDraftDetail();
}

function renderLophocDraftDetail() {
  const view = document.getElementById('lophocDetailView');
  if (!view || !_lophocDraft) return;
  const query = (document.getElementById('lophocDetailSearchInput')?.value || '').toLowerCase().trim();
  const allVisibleStudents = _lophocDraft.students.filter(s => !_lophocDraft.deletedIds.has(String(s.id)));
  const students = query
    ? allVisibleStudents.filter(s =>
        (s.full_name || '').toLowerCase().includes(query) ||
        (s.folder_name || '').toLowerCase().includes(query))
    : allVisibleStudents;
  // Update subtitle
  document.getElementById('lophocDetailSub').textContent = query
    ? `${students.length}/${allVisibleStudents.length} sinh viên`
    : `${allVisibleStudents.length} sinh viên`;
  updateLophocDraftUi();

  if (!students.length) {
    view.innerHTML = `<div style="text-align:center;color:var(--text3);padding:40px;font-size:13px;">${query ? 'Không tìm thấy sinh viên phù hợp' : 'Chưa có sinh viên nào trong lớp này'}</div>`;
    return;
  }

  view.innerHTML = students.map(s => {
    const folder = encodeURIComponent(s.folder_name || '');
    const faceChange = _lophocDraft.faceChanges.get(String(s.id));
    const stagedPreview = faceChange?.addFiles?.[0]?.url || '';
    const tokenized = s.folder_name ? withToken(`/api/face-image/${folder}/_first`) : '';
    const imgSrc = stagedPreview || (tokenized ? tokenized + (tokenized.includes('?') ? '&' : '?') + `t=${Date.now()}` : '');
    const initial = escapeHtml((s.full_name || s.folder_name || '?').charAt(0).toUpperCase());
    const fullName = escapeHtml(s.full_name || '—');
    const folderName = escapeHtml(s.folder_name || '—');
    const fullNameArg = jsStringAttr(s.full_name || '');
    const folderNameArg = jsStringAttr(s.folder_name || '');
    const draftBadge = s._draftNew ? '<span style="font-size:10px;color:var(--teal);background:var(--teal-dim);border-radius:999px;padding:2px 7px;margin-left:6px;">Mới</span>' : '';
    const faceBadge = faceChange ? '<span style="font-size:10px;color:#c8860a;background:rgba(255,180,0,.14);border-radius:999px;padding:2px 7px;margin-left:6px;">Ảnh nháp</span>' : '';
    return `
    <div style="background:var(--surface2);border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:12px;${s._draftNew ? 'border:1px solid rgba(204,120,92,.35);' : ''}">
      <div class="lophoc-student-avatar" style="background:var(--teal-dim);position:relative;overflow:hidden;flex-shrink:0;">
        ${imgSrc ? `<img src="${escapeAttr(imgSrc)}" alt="" style="width:100%;height:100%;object-fit:cover;position:absolute;inset:0;" onerror="this.style.display='none'">` : ''}
        <span style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;color:var(--teal);font-family: var(--font-sans);">${initial}</span>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;color:var(--text1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${fullName}${draftBadge}${faceBadge}</div>
        <div style="font-size:11px;color:var(--text3);font-family:monospace;">${folderName}</div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0;">
        <button class="btn btn-ghost" style="font-size:11px;padding:4px 10px;border:1px solid var(--teal);color:var(--teal);"
          onclick="openFaceRegistration(${s.id},${fullNameArg},${folderNameArg})">📷 Ảnh</button>
        <button class="btn btn-danger" style="font-size:11px;padding:4px 10px;"
          onclick="deleteLophocStudent(${s.id})">Xóa</button>
      </div>
    </div>`;
  }).join('');
}

async function deleteLophocStudent(id) {
  if (!confirm('Xóa sinh viên này khỏi bản nháp?')) return;
  _lophocDraft.deletedIds.add(String(id));
  markLophocDraftDirty();
  renderLophocDraftDetail();
}

function backToClassList() {
  if (!confirmLeaveLophocDraft()) return;
  _lophocCurrentClassId = null;
  _lophocDraft = null;
  loadLophoc();
}

function openAddStudentInClass() {
  const sel2 = document.getElementById('studentClassSelect2');
  const classGroup = sel2 ? sel2.closest('.form-group') : null;

  if (sel2 && _lophocCurrentClassId) {
    // Ensure the option for this class exists in the select
    if (!sel2.querySelector(`option[value="${_lophocCurrentClassId}"]`)) {
      const opt = document.createElement('option');
      opt.value = String(_lophocCurrentClassId);
      opt.textContent = _lophocCurrentClassName || String(_lophocCurrentClassId);
      sel2.appendChild(opt);
    }
    sel2.value = String(_lophocCurrentClassId);
    // Hide the class dropdown — user is already inside a class
    if (classGroup) classGroup.style.display = 'none';
  } else {
    if (classGroup) classGroup.style.display = '';
  }
  openModal('addStudentModal');
}

function openImportCsvInClass() {
  openImportCsvModal(_lophocCurrentClassId, _lophocCurrentClassName);
}

function openImportCsvModal(classId = null, className = '') {
  window._importCsvTargetClassId = classId || null;
  const file = document.getElementById('csvFile');
  const result = document.getElementById('importCsvResult');
  const context = document.getElementById('importCsvContext');
  const info = document.getElementById('importCsvFormatInfo');
  if (file) file.value = '';
  if (result) { result.textContent = ''; result.classList.remove('show'); result.style.display = 'none'; }
  if (context) {
    context.style.display = classId ? 'block' : 'none';
    context.textContent = classId ? `Import sinh viên vào lớp hiện tại: ${className || classId}` : '';
  }
  if (info) {
    info.innerHTML = classId
      ? '<strong>Format CSV:</strong><br>MSSV,Họ tên<br>hoặc<br>Họ tên,MSSV<br><br><button class="csv-template-link" onclick="downloadCsvTemplate()">⬇️ Tải file mẫu</button>'
      : '<strong>Format CSV:</strong><br>Họ tên,Tên lớp<br>hoặc<br>Họ tên,folder_name,Tên lớp<br><br><button class="csv-template-link" onclick="downloadCsvTemplate()">⬇️ Tải file mẫu</button>';
  }
  openModal('importCsvModal');
}

async function uploadDraftFaceFiles(studentId, files) {
  if (!files?.length) return;
  const formData = new FormData();
  files.forEach(face => formData.append('files', face.file, face.filename));
  const resp = await fetch(withToken(`/api/students/${studentId}/faces`), {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });
  const result = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(result.error || 'Upload face failed');
}

async function saveLophocDraft() {
  if (!_lophocCurrentClassId || !_lophocDraft) return;
  if (!_lophocDraft.dirty) { showToast('Không có thay đổi để lưu', 'warning'); return; }
  showGlobalLoading('Đang lưu thay đổi lớp...', 'Hệ thống đang áp dụng thêm/xóa sinh viên, cập nhật ảnh khuôn mặt và rebuild cache lớp.');
  try {
    const idMap = new Map();

    for (const student of _lophocDraft.students) {
      if (!student._draftNew || _lophocDraft.deletedIds.has(String(student.id))) continue;
      const created = await fetchAPI('/students', {
        method: 'POST',
        body: JSON.stringify({
          full_name: student.full_name,
          class_id: _lophocCurrentClassId,
          folder_name: student.folder_name || undefined,
        })
      });
      if (!created?.id) throw new Error(`Không tạo được sinh viên ${student.full_name}`);
      idMap.set(String(student.id), created.id);
    }

    for (const [rawId, change] of _lophocDraft.faceChanges.entries()) {
      const realId = idMap.get(rawId) || rawId;
      if (_lophocDraft.deletedIds.has(String(realId)) || _lophocDraft.deletedIds.has(rawId)) continue;
      for (const filename of change.deleteFiles || []) {
        if (Number(realId) > 0) {
          await fetchAPI(`/students/${realId}/faces/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        }
      }
      await uploadDraftFaceFiles(realId, change.addFiles || []);
    }

    for (const rawId of _lophocDraft.deletedIds) {
      if (Number(rawId) > 0) {
        await fetchAPI(`/students/${rawId}`, { method: 'DELETE' });
      }
    }

    await fetchAPI('/recognition/cache/rebuild', {
      method: 'POST',
      body: JSON.stringify({ class_id: _lophocCurrentClassId })
    });

    showToast('Đã lưu thay đổi lớp', 'success');
    await refreshLophocDetail();
    await loadClassesForModal();
  } catch (e) {
    showToast('Lưu thay đổi thất bại: ' + e.message, 'error');
  } finally {
    hideGlobalLoading();
  }
}

async function cancelLophocDraft() {
  if (!_lophocCurrentClassId || !_lophocDraft) return;
  if (_lophocDraft.dirty && !confirm('Hủy toàn bộ thay đổi chưa lưu?')) return;
  _lophocDraft.faceChanges.forEach(change => {
    (change.addFiles || []).forEach(face => { if (face.url) URL.revokeObjectURL(face.url); });
  });
  showToast('Đã hủy thay đổi nháp', 'warning');
  await refreshLophocDetail();
}

// Override saveStudent/deleteStudent to also refresh lophoc detail if open
const _origSaveStudent = window.saveStudent;
const _origDeleteStudent = window.deleteStudent;

// ─── HISTORY ────────────────────────────────────────────
async function loadHistory() {
  const classId = document.getElementById('historyClassFilter').value;
  const dateFilter = document.getElementById('historyDateFilter').value;

  // Build query params
  const params = new URLSearchParams();
  if (classId) params.set('class_id', classId);
  if (dateFilter) params.set('date', dateFilter);
  const qs = params.toString();
  const endpoint = '/attendance' + (qs ? '?' + qs : '');

  const records = await fetchAPI(endpoint);
  if (!records) return;

  const tbody = document.getElementById('historyTableBody');
  if (!records.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text2)">Không có bản ghi nào</td></tr>';
    return;
  }
  tbody.innerHTML = records.map(record => `
    <tr>
      <td class="name-col">${escapeHtml(record.name || record.full_name || 'Unknown')}</td>
      <td>${escapeHtml(record.class_name || record.class_id || '-')}</td>
      <td>${escapeHtml(formatDate(record.timestamp))}</td>
      <td class="time-col">${escapeHtml(formatTime(record.timestamp))}</td>
      <td>${escapeHtml(record.confidence ? (record.confidence * 100).toFixed(0) + '%' : '-')}</td>
    </tr>
  `).join('');
}

function applyHistoryFilter() {
  loadHistory();
}

function exportHistoryCSV() {
  const table = document.getElementById('historyTable');
  const rows = Array.from(table.querySelectorAll('tr'));

  const csv = rows.map(row => {
    return Array.from(row.querySelectorAll('th, td'))
      .map(cell => `"${cell.textContent.trim()}"`)
      .join(',');
  }).join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);

  link.setAttribute('href', url);
  link.setAttribute('download', `attendance_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  showToast('CSV exported successfully', 'success');
}

// ─── SETTINGS ───────────────────────────────────────────
async function loadSettings() {
  await loadRecognitionClasses();
  try {
    const classId = document.getElementById('recCacheClass')?.value;
    const data = await fetchAPI('/recognition/settings' + (classId ? `?class_id=${encodeURIComponent(classId)}` : ''));
    applyRecognitionSettings(data.settings || {});
    renderRecognitionStatus(data.status || null);
  } catch (e) {
    showToast('Không tải được cấu hình nhận diện', 'error');
  }
}

function applyRecognitionSettings(settings) {
  const model = document.getElementById('recModelPack');
  const threshold = document.getElementById('recThreshold');
  if (!model || !threshold) return;
  model.value = settings.model_pack || 'buffalo_l';
  threshold.value = settings.threshold ?? 0.35;
  document.getElementById('recThresholdValue').textContent = threshold.value;
  document.getElementById('recDetSize').value = settings.det_size ?? 640;
  document.getElementById('recCtxId').value = settings.ctx_id ?? -1;
  document.getElementById('recDrawBoxRatio').value = settings.draw_box_thickness_ratio ?? 0.004;
  document.getElementById('recDrawFontRatio').value = settings.draw_font_scale_ratio ?? 0.0018;
  document.getElementById('recDrawTextThicknessRatio').value = settings.draw_text_thickness_ratio ?? 0.0032;
  document.getElementById('recDrawPaddingRatio').value = settings.draw_text_padding_ratio ?? 0.006;
  document.getElementById('recMultiFace').checked = settings.multi_face !== false;
  document.getElementById('recRegistrationCrop').checked = settings.registration_crop !== false;
  loadRealtimeSettingsIntoUi();
}

async function loadRecognitionClasses() {
  const select = document.getElementById('recCacheClass');
  if (!select) return;
  const current = select.value;
  const classes = await fetchAPI('/classes');
  select.innerHTML = classes.map(cls => `<option value="${cls.id}">${escapeHtml(cls.name)}</option>`).join('');
  if (current) select.value = current;
  else if (classes.length) select.value = classes[0].id;
}

async function saveRecognitionSettings() {
  saveRealtimeSettingsFromUi();
  const payload = {
    model_pack: document.getElementById('recModelPack').value,
    threshold: parseFloat(document.getElementById('recThreshold').value),
    det_size: parseInt(document.getElementById('recDetSize').value || '640', 10),
    ctx_id: parseInt(document.getElementById('recCtxId').value || '-1', 10),
    draw_box_thickness_ratio: parseFloat(document.getElementById('recDrawBoxRatio').value || '0.004'),
    draw_font_scale_ratio: parseFloat(document.getElementById('recDrawFontRatio').value || '0.0018'),
    draw_text_thickness_ratio: parseFloat(document.getElementById('recDrawTextThicknessRatio').value || '0.0032'),
    draw_text_padding_ratio: parseFloat(document.getElementById('recDrawPaddingRatio').value || '0.006'),
    multi_face: document.getElementById('recMultiFace').checked,
    registration_crop: document.getElementById('recRegistrationCrop').checked,
  };
  try {
    const data = await fetchAPI('/recognition/settings', { method: 'PUT', body: JSON.stringify(payload) });
    applyRecognitionSettings(data.settings || payload);
    showToast('Đã lưu cấu hình nhận diện');
    await loadRecognitionCacheStatus();
  } catch (e) {
    showToast('Lưu cấu hình thất bại', 'error');
  }
}

async function loadRecognitionCacheStatus() {
  const classId = document.getElementById('recCacheClass')?.value;
  const endpoint = '/recognition/cache/status' + (classId ? `?class_id=${encodeURIComponent(classId)}` : '');
  try {
    renderRecognitionStatus(await fetchAPI(endpoint));
  } catch (e) {
    renderRecognitionStatus({ error: e.message });
  }
}

function renderRecognitionStatus(status) {
  const box = document.getElementById('recCacheStatus');
  if (!box) return;
  if (!status) { box.textContent = 'Chưa có dữ liệu cache.'; return; }
  if (status.error) { box.textContent = status.error; return; }
  const built = status.built_at ? new Date(status.built_at * 1000).toLocaleString('vi-VN') : 'chưa build';
  box.innerHTML = `Engine: <b>${escapeHtml(status.engine || 'insightface')}</b><br>` +
    `Cache: <b style="color:${status.ready ? 'var(--teal)' : 'var(--orange)'}">${status.ready ? 'sẵn sàng' : (status.dirty ? 'cần rebuild' : 'chưa có')}</b><br>` +
    `Sinh viên indexed: ${status.students_with_embeddings || 0} - Ảnh hợp lệ: ${status.images_indexed || 0}<br>` +
    `Ảnh lỗi: ${status.error_count || 0} - Build: ${escapeHtml(built)}`;
}

async function rebuildRecognitionCache() {
  const classId = document.getElementById('recCacheClass')?.value;
  if (!classId) { showToast('Hãy tạo/chọn lớp trước khi rebuild cache', 'error'); return; }
  try {
    showGlobalLoading('Đang rebuild cache lớp...', 'Hệ thống đang đọc ảnh khuôn mặt và tạo lại dữ liệu nhận diện. Vui lòng chờ.');
    const data = await fetchAPI('/recognition/cache/rebuild', {
      method: 'POST',
      body: JSON.stringify({ class_id: classId || null })
    });
    renderRecognitionStatus(data);
    showToast('Rebuild cache hoàn tất');
  } catch (e) {
    showToast('Rebuild cache thất bại', 'error');
  } finally {
    hideGlobalLoading();
  }
}

// ─── CSV / XLSX PREVIEW ──────────────────────────────────
let _parsedImportRows = [];  // full parsed rows (all columns), stored globally for upload

// Pure-JS CSV parser — no external library needed
function _parseCSVText(text) {
  const rows = [];
  // detect delimiter: tab > semicolon > comma
  const sample = text.slice(0, 2000);
  const delim = (sample.match(/\t/g)||[]).length > (sample.match(/;/g)||[]).length
    ? ((sample.match(/\t/g)||[]).length > (sample.match(/,/g)||[]).length ? '\t' : ',')
    : ((sample.match(/;/g)||[]).length > (sample.match(/,/g)||[]).length ? ';' : ',');

  let cur = [], field = '', inQ = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"') { if (text[i+1] === '"') { field += '"'; i++; } else { inQ = false; } }
      else { field += ch; }
    } else {
      if (ch === '"') { inQ = true; }
      else if (ch === delim) { cur.push(field); field = ''; }
      else if (ch === '\n') { cur.push(field); field = ''; if (cur.some(c=>c)) rows.push(cur); cur = []; }
      else if (ch !== '\r') { field += ch; }
    }
  }
  cur.push(field);
  if (cur.some(c=>c)) rows.push(cur);
  return rows;
}

function previewCsvColumns(input) {
  const file = input.files[0];
  if (!file) return;
  const display = document.getElementById('importCsvFileDisplay');
  if (display) { display.textContent = file.name; display.style.color = 'var(--text1)'; }
  const ext = file.name.split('.').pop().toLowerCase();

  if (ext === 'xlsx' || ext === 'xls') {
    if (typeof XLSX === 'undefined') {
      showToast('Thư viện XLSX chưa tải xong, vui lòng thử lại sau vài giây hoặc dùng file CSV', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const allRows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
        _parsedImportRows = allRows.map(r => r.map(c => String(c ?? '').trim()));
        _renderImportPreview(_parsedImportRows);
      } catch(err) {
        showToast('Lỗi đọc file XLSX: ' + err.message, 'error');
      }
    };
    reader.readAsArrayBuffer(file);
  } else {
    // CSV / TXT — pure JS parser, no external library
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const allRows = _parseCSVText(e.target.result);
        _parsedImportRows = allRows.map(r => r.map(c => String(c ?? '').trim()));
        _renderImportPreview(_parsedImportRows);
      } catch(err) {
        showToast('Lỗi đọc file CSV: ' + err.message, 'error');
      }
    };
    reader.readAsText(file, 'UTF-8');
  }
}

function _renderImportPreview(allRows) {
  // Filter out completely empty rows
  const rows = allRows.filter(r => r.some(c => c !== ''));
  if (!rows.length) return;

  const previewRows = rows.slice(0, 6);
  const numCols = Math.max(...previewRows.map(r => r.length));

  document.getElementById('csvColumnPicker').style.display = 'block';

  // Preview table
  const tbl = document.getElementById('csvPreviewTable');
  tbl.innerHTML = previewRows.map((row, ri) => {
    const cells = Array.from({length: numCols}, (_, ci) => {
      const val = String(row[ci] ?? '');
      return val;
    });
    const tag = ri === 0 ? 'th' : 'td';
    const baseBg = ri === 0 ? 'var(--surface2)' : (ri % 2 ? '' : 'rgba(204,120,92,.04)');
    return `<tr>${cells.map((c, ci) =>
      `<${tag} id="prevcell_${ri}_${ci}" style="background:${baseBg}; padding:3px 8px; border:1px solid var(--border); white-space:nowrap; max-width:160px; overflow:hidden; text-overflow:ellipsis;" title="${escapeAttr(c)}">${escapeHtml(c)}</${tag}>`
    ).join('')}</tr>`;
  }).join('');

  // Column selector options
  const headerRow = previewRows[0];
  const options = Array.from({length: numCols}, (_, i) => {
    const label = headerRow[i] ? `Cột ${i+1} — ${headerRow[i]}` : `Cột ${i+1}`;
    return `<option value="${i}">${escapeHtml(label)}</option>`;
  }).join('');

  const mssvSel = document.getElementById('csvMssvCol');
  const nameSel = document.getElementById('csvNameCol');
  mssvSel.innerHTML = options;
  nameSel.innerHTML = options;

  // Auto-detect column by header text
  let mssvGuess = 0, nameGuess = 1;
  headerRow.forEach((h, i) => {
    const hl = h.toLowerCase();
    if (hl.includes('mssv') || hl.includes('msv') || hl.includes('mã sv') || hl === 'id') mssvGuess = i;
    if (hl.includes('tên') || hl.includes('name') || hl.includes('họ')) nameGuess = i;
  });
  mssvSel.value = mssvGuess;
  nameSel.value = nameGuess;

  // Highlight columns
  function highlightCols() {
    const mc = parseInt(mssvSel.value), nc = parseInt(nameSel.value);
    previewRows.forEach((_, ri) => {
      for (let ci = 0; ci < numCols; ci++) {
        const cell = document.getElementById(`prevcell_${ri}_${ci}`);
        if (!cell) continue;
        const base = ri === 0 ? 'var(--surface2)' : (ri%2 ? '' : 'rgba(204,120,92,.04)');
        if (ci === mc) cell.style.background = 'rgba(0,200,150,.2)';
        else if (ci === nc) cell.style.background = 'rgba(80,150,255,.2)';
        else cell.style.background = base;
      }
    });
  }
  mssvSel.onchange = highlightCols;
  nameSel.onchange = highlightCols;
  highlightCols();
}

// ─── IMPORT CLASS ─────────────────────────────────────────
async function pickFaceFolder() {
  const btn = document.querySelector('[onclick="pickFaceFolder()"]');
  const orig = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '⏳ Đang mở...';
  try {
    const resp = await fetch(withToken('/api/pick-folder'), { headers: authHeaders() });
    const data = await resp.json();
    if (data.path) {
      document.getElementById('importFaceFolder').value = data.path;
      document.getElementById('importFaceFolderDisplay').textContent = data.path;
      document.getElementById('importFaceFolderDisplay').style.color = 'var(--text1)';
    } else {
      document.getElementById('importFaceFolderDisplay').textContent = 'Chưa chọn';
      document.getElementById('importFaceFolderDisplay').style.color = 'var(--text2)';
    }
  } catch(e) {
    document.getElementById('importFaceFolderDisplay').textContent = 'Lỗi: ' + e.message;
  } finally {
    btn.disabled = false; btn.innerHTML = orig;
  }
}

async function importClass() {
  const className = document.getElementById('importClassName').value.trim();
  const fileInput = document.getElementById('importCsvFile');
  const faceFolder = document.getElementById('importFaceFolder').value.trim();
  const resultEl = document.getElementById('importClassResult');
  const btn = document.getElementById('importClassBtn');

  if (!className) { showToast('Vui lòng nhập tên lớp', 'error'); return; }
  if (!fileInput.files || !fileInput.files[0]) { showToast('Vui lòng chọn file CSV', 'error'); return; }

  // Get user-selected column indices
  const mssvCol = parseInt(document.getElementById('csvMssvCol')?.value ?? 0);
  const nameCol = parseInt(document.getElementById('csvNameCol')?.value ?? 1);
  const hasHeader = parseInt(document.getElementById('csvHasHeader')?.value ?? 1);

  if (!_parsedImportRows.length) { showToast('Vui lòng chọn file CSV/XLSX', 'error'); return; }

  btn.disabled = true; btn.textContent = '⏳ Đang import...';
  resultEl.style.display = 'none';

  // Build student list client-side from parsed rows
  // Skip header row if needed. Count non-empty rows as the source list total,
  // even when MSSV/name is missing and the server will not create a student.
  const dataRows = hasHeader ? _parsedImportRows.slice(1) : _parsedImportRows;
  const importListRows = dataRows.filter(row =>
    Array.isArray(row) && row.some(cell => String(cell ?? '').trim())
  );
  const students = [];
  let skippedClient = 0;
  for (const row of importListRows) {
    const mssv = (row[mssvCol] ?? '').trim();
    const name = (row[nameCol] ?? '').trim();
    if (!mssv) { skippedClient++; continue; }   // bỏ qua hàng không có MSSV
    if (!name) { skippedClient++; continue; }    // bỏ qua hàng không có tên
    students.push({ mssv, full_name: name });
  }

  if (!students.length) {
    showToast(`Không có sinh viên hợp lệ. Bỏ qua ${skippedClient} hàng trống MSSV.`, 'error');
    btn.disabled = false; btn.innerHTML = '📥 Import';
    return;
  }

  try {
    const importJobId = `import_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const totalImportRows = importListRows.length;
    window.currentImportClassJobId = importJobId;
    showGlobalLoading(
      'Đang import lớp học...',
      faceFolder
        ? 'Hệ thống đang tạo lớp, thêm sinh viên, sao chép ảnh khuôn mặt và rebuild cache nhận diện.'
        : 'Hệ thống đang tạo lớp và thêm danh sách sinh viên.'
    );
    setGlobalLoadingProgress({
      studentsDone: 0,
      studentsTotal: totalImportRows,
      facesDone: 0,
      facesTotal: 0
    });
    const payload = {
      class_name: className,
      students,   // [{mssv, full_name}, ...]
      face_folder: faceFolder || null,
      skipped_client: skippedClient,
      total_rows: totalImportRows,
      import_job_id: importJobId
    };

    const resp = await fetch(withToken('/api/classes/import'), {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload)
    });
    const result = await resp.json();

    if (!resp.ok) throw new Error(result.error || 'Import thất bại');

    resultEl.style.display = 'block';
    resultEl.style.background = 'rgba(0,200,150,.1)';
    resultEl.style.color = 'var(--teal)';
    resultEl.textContent = `✓ Đã tạo lớp ${result.class_name} — ${result.imported_students} sinh viên` +
      (result.imported_faces ? `, ${result.imported_faces} ảnh` : '') +
      (result.skipped ? ` (bỏ qua ${result.skipped})` : '');

    showToast(`Import xong: ${result.imported_students} sinh viên`, 'success');
    await loadClasses();
    await loadClassesForModal();
    // Refresh lophoc if active
    const lophocScreen = document.getElementById('screen-lophoc');
    if (lophocScreen && lophocScreen.classList.contains('active')) loadLophoc();
    // Reset form
    document.getElementById('importClassName').value = '';
    fileInput.value = '';
    document.getElementById('importFaceFolder').value = '';
    document.getElementById('importFaceFolderDisplay').textContent = 'Chưa chọn';
    document.getElementById('importFaceFolderDisplay').style.color = 'var(--text2)';
    document.getElementById('csvColumnPicker').style.display = 'none';
    resultEl.style.display = 'none';
    closeModal('importClassModal');
  } catch(e) {
    resultEl.style.display = 'block';
    resultEl.style.background = 'rgba(255,80,80,.1)';
    resultEl.style.color = 'var(--red)';
    resultEl.textContent = '✗ Lỗi: ' + e.message;
    showToast('Import lỗi: ' + e.message, 'error');
  } finally {
    window.currentImportClassJobId = null;
    hideGlobalLoading();
    btn.disabled = false; btn.innerHTML = '📥 Import';
  }
}

// ─── WEBSOCKET ──────────────────────────────────────────
function connectWebSocket() {
  try {
    ws = new WebSocket(withToken('/ws'));

    ws.onopen = () => {
      wsConnected = true;
      updateConnectionStatus();
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'attendance_batch') {
          if (currentLessonId && data.lesson_id && data.lesson_id !== currentLessonId) return;
          const time = formatTime(data.timestamp);
          const imageUrl = data.image_url ? withToken(data.image_url) + (withToken(data.image_url).includes('?') ? '&' : '?') + 't=' + Date.now() : null;
          addFeedItemBatch({ faces: data.faces || [], time, imageUrl });
          refreshLessonStats();

        } else if (data.type === 'import_class_progress') {
          if (data.job_id && data.job_id !== window.currentImportClassJobId) return;
          setGlobalLoadingProgress({
            studentsDone: data.students_done || 0,
            studentsTotal: data.students_total || 0,
            facesDone: data.faces_done || 0,
            facesTotal: data.faces_total || 0
          });

        } else if (data.type === 'attendance') {
          // legacy single-person broadcast (kept for compatibility)
          const name = data.name || 'Unknown';
          const mssv = data.mssv || '';
          const conf = data.confidence ? (data.confidence * 100).toFixed(0) + '%' : '—';
          const time = formatTime(data.timestamp);
          const imageUrl = data.image_url ? withToken(data.image_url) + (withToken(data.image_url).includes('?') ? '&' : '?') + 't=' + Date.now() : null;
          const recognized = data.recognized !== false;
          const recorded = data.lesson_recorded;
          addFeedItem({ name, mssv, conf, time, imageUrl, recognized, recorded });
          refreshLessonStats();

        } else if (data.type === 'lesson_started' || data.type === 'lesson_stopped') {
          loadLessons();
        }
      } catch(e) { console.error('WS parse error', e); }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      wsConnected = false;
      updateConnectionStatus();
    };

    ws.onclose = () => {
      wsConnected = false;
      updateConnectionStatus();
      // Attempt to reconnect after 3 seconds
      setTimeout(connectWebSocket, 3000);
    };
  } catch (error) {
    console.error('WebSocket connection failed:', error);
    wsConnected = false;
  }
}

function updateConnectionStatus() {
  const badge = document.getElementById('connectionBadge');
  const dot = document.getElementById('connectionDot');
  const text = document.getElementById('connectionText');
  const connStatus = document.getElementById('connStatus');
  const wsStatusElem = document.getElementById('wsStatus');

  if (wsConnected) {
    if (badge) badge.classList.remove('offline');
    if (dot) dot.classList.remove('offline');
    if (text) text.textContent = 'Online';
    if (connStatus) connStatus.textContent = 'Online';
    if (wsStatusElem) wsStatusElem.textContent = 'Connected';
  } else {
    if (badge) badge.classList.add('offline');
    if (dot) dot.classList.add('offline');
    if (text) text.textContent = 'Offline';
    if (connStatus) connStatus.textContent = 'Offline';
    if (wsStatusElem) wsStatusElem.textContent = 'Disconnected';
  }
}

// ─── STARTUP ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);

// ─── TASK 2: Face Registration ────────────────────────────
let currentFaceStudentId = null;
let currentFaceClassId = null;
let faceRegistrationDirty = false;
let faceRegistrationReadonly = false;

async function openFaceRegistration(studentId, studentName, folderName, readonly = false) {
  currentFaceStudentId = studentId;
  currentFaceClassId = null;
  faceRegistrationDirty = false;
  faceRegistrationReadonly = !!readonly;
  document.getElementById('faceRegStudentName').textContent = studentName;
  document.getElementById('faceRegFolderName').textContent = folderName || '(not set)';
  updateFaceRegistrationMode();
  if (!faceRegistrationReadonly) switchFaceRegTab('upload'); // always start on upload tab
  openModal('faceRegistrationModal');
  await loadStudentFaces(studentId);
}

function updateFaceRegistrationMode() {
  const note = document.getElementById('faceRegReadonlyNote');
  const editTabs = document.getElementById('faceRegEditTabs');
  const uploadTab = document.getElementById('faceRegUploadTab');
  const camTab = document.getElementById('faceRegCamTab');
  if (note) note.style.display = faceRegistrationReadonly ? 'block' : 'none';
  if (editTabs) editTabs.style.display = faceRegistrationReadonly ? 'none' : 'flex';
  if (uploadTab) uploadTab.style.display = faceRegistrationReadonly ? 'none' : '';
  if (camTab) camTab.style.display = 'none';
  if (faceRegistrationReadonly) closeFaceRegCamera();
}

function isLophocDraftFaceMode() {
  return !!(_lophocCurrentClassId && _lophocDraft && currentFaceStudentId && !faceRegistrationReadonly);
}

function addDraftFaceFile(studentId, file) {
  const change = ensureFaceChange(studentId);
  change.addFiles.push({
    file,
    filename: file.name || `draft_${Date.now()}.jpg`,
    url: URL.createObjectURL(file),
    draft: true,
  });
  markLophocDraftDirty();
}

async function closeFaceRegistrationModal() {
  closeFaceRegCamera(); // stop camera if running
  if (faceRegistrationDirty && currentFaceClassId) {
    try {
      showGlobalLoading('Đang rebuild cache lớp...', 'Hệ thống đang cập nhật dữ liệu khuôn mặt sau khi bạn chỉnh sửa ảnh sinh viên.');
      await fetchAPI('/recognition/cache/rebuild', {
        method: 'POST',
        body: JSON.stringify({ class_id: currentFaceClassId })
      });
      showToast('Đã rebuild cache lớp', 'success');
      await loadRecognitionCacheStatus();
    } catch (e) {
      showToast('Rebuild cache thất bại', 'error');
    } finally {
      hideGlobalLoading();
    }
  }
  closeModal('faceRegistrationModal');
  currentFaceStudentId = null;
  currentFaceClassId = null;
  faceRegistrationDirty = false;
  faceRegistrationReadonly = false;
}

// ─── FACE REG WEBCAM ────────────────────────────────────
let _faceRegStream = null;

function switchFaceRegTab(tab) {
  const uploadTab = document.getElementById('faceRegUploadTab');
  const camTab = document.getElementById('faceRegCamTab');
  const btnUpload = document.getElementById('faceTabUpload');
  const btnCam = document.getElementById('faceTabCam');
  if (!uploadTab || !camTab) return;
  if (tab === 'upload') {
    uploadTab.style.display = '';
    camTab.style.display = 'none';
    btnUpload.className = 'btn btn-primary';
    btnCam.className = 'btn btn-ghost';
    closeFaceRegCamera();
  } else {
    uploadTab.style.display = 'none';
    camTab.style.display = '';
    btnUpload.className = 'btn btn-ghost';
    btnCam.className = 'btn btn-primary';
  }
}

async function openFaceRegCamera() {
  const video = document.getElementById('faceRegVideo');
  const placeholder = document.getElementById('faceRegCamPlaceholder');
  const captureBtn = document.getElementById('faceRegCaptureBtn');
  const openBtn = document.getElementById('faceRegOpenCamBtn');
  const statusEl = document.getElementById('faceRegCamStatus');
  if (!video) return;
  try {
    _faceRegStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 640, height: 480 }, audio: false });
    video.srcObject = _faceRegStream;
    if (placeholder) placeholder.style.display = 'none';
    if (captureBtn) captureBtn.disabled = false;
    if (openBtn) openBtn.textContent = '🟢 Camera đang bật';
    if (statusEl) statusEl.textContent = 'Camera đã sẵn sàng. Nhấn "Chụp & Lưu" để đăng ký ảnh.';
  } catch (err) {
    if (statusEl) statusEl.textContent = 'Không thể mở camera: ' + (err.message || err);
    showToast('Không thể mở camera: ' + (err.message || err), 'error');
  }
}

function closeFaceRegCamera() {
  if (_faceRegStream) {
    _faceRegStream.getTracks().forEach(t => t.stop());
    _faceRegStream = null;
  }
  const video = document.getElementById('faceRegVideo');
  const placeholder = document.getElementById('faceRegCamPlaceholder');
  const captureBtn = document.getElementById('faceRegCaptureBtn');
  const openBtn = document.getElementById('faceRegOpenCamBtn');
  const statusEl = document.getElementById('faceRegCamStatus');
  if (video) video.srcObject = null;
  if (placeholder) placeholder.style.display = 'flex';
  if (captureBtn) captureBtn.disabled = true;
  if (openBtn) openBtn.textContent = '🔴 Bật camera';
  if (statusEl) statusEl.textContent = '';
}

async function captureAndUploadFace() {
  if (faceRegistrationReadonly) return;
  const video = document.getElementById('faceRegVideo');
  const canvas = document.getElementById('faceRegCanvas');
  const statusEl = document.getElementById('faceRegCamStatus');
  if (!video || !canvas || !currentFaceStudentId) return;
  if (!_faceRegStream) { showToast('Camera chưa bật', 'error'); return; }

  // Draw video frame to canvas
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  // Convert to blob (JPEG)
  canvas.toBlob(async (blob) => {
    if (!blob) { showToast('Lỗi chụp ảnh', 'error'); return; }
    const filename = `webcam_${Date.now()}.jpg`;
    if (isLophocDraftFaceMode()) {
      addDraftFaceFile(currentFaceStudentId, new File([blob], filename, { type: 'image/jpeg' }));
      if (statusEl) statusEl.textContent = 'Ảnh đã được thêm vào bản nháp. Bấm Lưu thay đổi ở trang lớp để áp dụng.';
      await loadStudentFaces(currentFaceStudentId);
      renderLophocDraftDetail();
      showToast('Đã thêm ảnh camera vào bản nháp', 'success');
      return;
    }
    const formData = new FormData();
    formData.append('files', blob, filename);

    if (statusEl) statusEl.textContent = 'Đang tải lên...';
    try {
      const response = await fetch(withToken(`/api/students/${currentFaceStudentId}/faces`), {
        method: 'POST',
        headers: authHeaders(),
        body: formData
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        showToast('Lỗi upload: ' + (result.error || response.statusText), 'error');
        if (statusEl) statusEl.textContent = 'Lỗi tải lên ảnh.';
        return;
      }
      const savedCount = Array.isArray(result.saved) ? result.saved.length : 0;
      const invalidCount = Array.isArray(result.invalid_no_face) ? result.invalid_no_face.length : 0;
      if (savedCount > 0 && invalidCount === 0) {
        showToast('Đã lưu ảnh từ camera', 'success');
        if (statusEl) statusEl.textContent = 'Ảnh đã được lưu! Tiếp tục chụp nếu cần.';
      } else if (savedCount > 0 && invalidCount > 0) {
        showToast(`Lưu ${savedCount} ảnh, bỏ ${invalidCount} ảnh không phát hiện khuôn mặt`, 'warning');
        if (statusEl) statusEl.textContent = 'Một số ảnh bị bỏ do không phát hiện khuôn mặt.';
      } else {
        showToast('Không phát hiện khuôn mặt trong ảnh chụp, vui lòng chụp lại rõ mặt hơn', 'error');
        if (statusEl) statusEl.textContent = 'Không phát hiện khuôn mặt.';
      }
      if (savedCount > 0) faceRegistrationDirty = true;
      await loadStudentFaces(currentFaceStudentId);
    } catch (err) {
      showToast('Lỗi kết nối: ' + err.message, 'error');
      if (statusEl) statusEl.textContent = 'Lỗi kết nối.';
    }
  }, 'image/jpeg', 0.92);
}

async function loadStudentFaces(studentId) {
  const isDraftMode = isLophocDraftFaceMode();
  const isTempStudent = Number(studentId) < 0;
  const data = isTempStudent ? null : await fetchAPI(`/students/${studentId}/faces`);
  const grid = document.getElementById('faceGrid');
  const countEl = document.getElementById('faceCountInfo');

  // API returns {student, faces: [...], count}
  let faceList = (data && Array.isArray(data.faces)) ? data.faces : [];
  if (data?.student?.class_id) currentFaceClassId = data.student.class_id;
  if (isDraftMode) {
    const change = _lophocDraft.faceChanges.get(String(studentId));
    const deleted = change?.deleteFiles || new Set();
    faceList = faceList.filter(face => !deleted.has(face.filename));
    if (change?.addFiles?.length) faceList = faceList.concat(change.addFiles);
  }

  if (faceList.length === 0) {
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text3); padding: 20px;">Chưa có ảnh đăng ký</div>';
    countEl.textContent = 'Có 0 ảnh đã đăng ký';
    return;
  }

  // Face images are served via /api/face-image/{folder}/{filename}
  const folder = data.student?.folder_name || '';
  grid.innerHTML = faceList.map((face, idx) => `
    <div class="face-thumbnail">
      <img src="${face.draft ? escapeAttr(face.url) : withToken(`/api/face-image/${encodeURIComponent(folder)}/${encodeURIComponent(face.filename)}`)}${face.draft ? '' : (withToken(`/api/face-image/${encodeURIComponent(folder)}/${encodeURIComponent(face.filename)}`).includes('?') ? '&' : '?') + 't=' + Date.now()}"
           alt="Face ${idx+1}" style="width:100%;height:100%;object-fit:cover;">
      ${faceRegistrationReadonly ? '' : `<button class="face-thumbnail-delete" onclick="deleteFace(${studentId}, '${face.filename}')" title="Xóa">×</button>`}
    </div>
  `).join('');

  countEl.textContent = `Có ${faceList.length} ảnh đã đăng ký`;
}

async function uploadFaces(studentId) {
  if (faceRegistrationReadonly) return;
  const fileInput = document.getElementById('faceFileInput');
  const files = fileInput.files;
  
  if (!files || files.length === 0) {
    showToast('Vui lòng chọn ảnh', 'error');
    return;
  }

  if (isLophocDraftFaceMode()) {
    Array.from(files).forEach(file => addDraftFaceFile(studentId, file));
    fileInput.value = '';
    await loadStudentFaces(studentId);
    renderLophocDraftDetail();
    showToast(`Đã thêm ${files.length} ảnh vào bản nháp`, 'success');
    return;
  }

  const formData = new FormData();
  for (let file of files) {
    formData.append('files', file);
  }

  try {
    const response = await fetch(withToken(`/api/students/${studentId}/faces`), {
      method: 'POST',
      headers: authHeaders(),
      body: formData
      // NOTE: do NOT set Content-Type — browser sets multipart boundary automatically
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      showToast('Lỗi upload: ' + (result.error || response.statusText), 'error');
      return;
    }

    const savedCount = Array.isArray(result.saved) ? result.saved.length : 0;
    const invalidCount = Array.isArray(result.invalid_no_face) ? result.invalid_no_face.length : 0;
    if (savedCount > 0 && invalidCount === 0) {
      showToast(`Đã tải lên ${savedCount} ảnh`, 'success');
    } else if (savedCount > 0 && invalidCount > 0) {
      showToast(`Tải lên ${savedCount} ảnh, bỏ ${invalidCount} ảnh không phát hiện khuôn mặt`, 'warning');
    } else {
      showToast('Không phát hiện khuôn mặt trong ảnh đã tải lên', 'error');
    }
    if (savedCount > 0) faceRegistrationDirty = true;
    fileInput.value = '';
    await loadStudentFaces(studentId);
  } catch (error) {
    console.error('Upload error:', error);
    showToast('Lỗi kết nối: ' + error.message, 'error');
  }
}

async function deleteFace(studentId, filename) {
  if (faceRegistrationReadonly) return;
  if (!confirm('Xóa ảnh này?')) return;

  if (isLophocDraftFaceMode()) {
    const change = ensureFaceChange(studentId);
    const stagedIndex = change.addFiles.findIndex(face => face.filename === filename);
    if (stagedIndex >= 0) {
      const [removed] = change.addFiles.splice(stagedIndex, 1);
      if (removed?.url) URL.revokeObjectURL(removed.url);
    } else {
      change.deleteFiles.add(filename);
    }
    markLophocDraftDirty();
    await loadStudentFaces(studentId);
    renderLophocDraftDetail();
    showToast('Đã xóa ảnh khỏi bản nháp', 'success');
    return;
  }
  
  const result = await fetchAPI(`/students/${studentId}/faces/${filename}`, {
    method: 'DELETE'
  });
  
  if (result !== null) {
    showToast('Ảnh đã xóa', 'success');
    faceRegistrationDirty = true;
    await loadStudentFaces(studentId);
  }
}

function handleFaceFileSelect() {
  const fileInput = document.getElementById('faceFileInput');
  const uploadArea = document.getElementById('uploadArea');
  
  uploadArea.style.borderColor = 'var(--teal)';
  uploadArea.style.background = 'var(--teal-glow)';
  
  // Trigger upload
  setTimeout(() => {
    uploadFaces(currentFaceStudentId);
    setTimeout(() => {
      uploadArea.style.borderColor = 'var(--border2)';
      uploadArea.style.background = 'var(--bg3)';
    }, 500);
  }, 200);
}

// Drag and drop for upload area
document.addEventListener('DOMContentLoaded', function() {
  const uploadArea = document.getElementById('uploadArea');
  
  if (uploadArea) {
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      
      const files = e.dataTransfer.files;
      document.getElementById('faceFileInput').files = files;
      uploadFaces(currentFaceStudentId);
    });
  }
});

// ─── TASK 3: Import CSV ───────────────────────────────────
async function importCSV() {
  const fileInput = document.getElementById('csvFile');
  const file = fileInput?.files?.[0];
  const targetClassId = window._importCsvTargetClassId || null;

  if (!file) {
    showToast('Vui lòng chọn file CSV', 'error');
    return;
  }

  if (targetClassId && targetClassId === _lophocCurrentClassId && _lophocDraft) {
    try {
      const text = await file.text();
      const rows = _parseCSVText(text);
      let imported = 0;
      let skipped = 0;
      rows.forEach((row, idx) => {
        if (idx === 0 && row.join(' ').toLowerCase().includes('họ')) return;
        const first = (row[0] || '').trim();
        const second = (row[1] || '').trim();
        if (!first || !second) { skipped++; return; }
        const looksMssvFirst = /\d/.test(first) && first.length <= 32;
        const folderName = looksMssvFirst ? first : second;
        const fullName = looksMssvFirst ? second : first;
        _lophocDraft.students.push({
          id: _lophocDraft.nextTempId--,
          full_name: fullName,
          folder_name: folderName,
          class_id: _lophocCurrentClassId,
          _draftNew: true,
        });
        imported++;
      });
      markLophocDraftDirty();
      renderLophocDraftDetail();
      if (fileInput) fileInput.value = '';
      const resultDiv = document.getElementById('importCsvResult');
      if (resultDiv) {
        resultDiv.textContent = `✓ Đã thêm vào bản nháp ${imported} sinh viên, bỏ qua ${skipped}`;
        resultDiv.style.display = 'block';
        resultDiv.classList.add('show');
      }
      showToast('Đã import CSV vào bản nháp', 'success');
      setTimeout(() => closeModal('importCsvModal'), 800);
    } catch (error) {
      showToast('Import CSV vào bản nháp lỗi: ' + error.message, 'error');
    }
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  if (targetClassId) formData.append('class_id', String(targetClassId));

  try {
    const response = await fetch(withToken('/api/import/csv'), {
      method: 'POST',
      headers: authHeaders(),
      body: formData
    });
    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      showToast(result.error || 'Import failed', 'error');
      return;
    }

    if (fileInput) fileInput.value = '';

    const resultDiv = document.getElementById('importCsvResult');
    if (resultDiv) {
      resultDiv.textContent = `✓ Đã import ${result.imported || 0} sinh viên, bỏ qua ${result.skipped || 0}`;
      resultDiv.style.display = 'block';
      resultDiv.classList.add('show');
    }

    showToast('Import thành công', 'success');

    await loadStudents();
    if (targetClassId && targetClassId === _lophocCurrentClassId) {
      await refreshLophocDetail();
      await loadClassesForModal();
    }

    setTimeout(() => {
      closeModal('importCsvModal');
      if (resultDiv) resultDiv.classList.remove('show');
    }, 2000);
  } catch (error) {
    console.error('Import error:', error);
    showToast('Import error', 'error');
  }
}

function downloadCsvTemplate() {
  const csv = 'Họ tên,Tên lớp\nNguyen Van A,Class A1\nTran Thi B,Class A1';
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.setAttribute('href', URL.createObjectURL(blob));
  link.setAttribute('download', 'students_template.csv');
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast('Template downloaded', 'success');
}

// ─── TASK 4: Import Database Folder ──────────────────────
async function importDatabase() {
  const path = document.getElementById('importDbPath').value.trim();
  
  if (!path) {
    showToast('Vui lòng nhập đường dẫn', 'error');
    return;
  }

  const result = await fetchAPI('/import/database', {
    method: 'POST',
    body: JSON.stringify({ source_path: path })
  });

  if (result) {
    const resultDiv = document.getElementById('importDbResult');
    resultDiv.textContent = `✓ Đã import ${result.imported_people || 0} người, ${result.imported_faces || 0} ảnh`;
    resultDiv.classList.add('show');
    
    showToast('Import database thành công', 'success');
    
    setTimeout(() => {
      resultDiv.classList.remove('show');
    }, 4000);
  }
}

// ─── Server Info + QR Code ───────────────────────────────────────────────────
async function loadServerInfo() {
  try {
    const response = await fetch(`${SERVER_BASE}/api/server/info`);
    const info = response.ok ? await response.json() : null;
    if (info?.token) setApiToken(info.token);
    if (!info || !info.urls || info.urls.length === 0) {
      document.getElementById('serverUrls').textContent = 'localhost:' + (info?.port || 8080);
      return;
    }
    const urlsDiv = document.getElementById('serverUrls');
    const tokenForLan = API_TOKEN || info.token || '';
    const addToken = (url) => {
      if (!tokenForLan) return url;
      const u = new URL(url);
      u.searchParams.set('token', tokenForLan);
      return u.toString();
    };
    urlsDiv.innerHTML = '';
    const copyText = async (label, value) => {
      try {
        await navigator.clipboard.writeText(value);
        showToast(`Đã copy ${label}`, 'success');
      } catch (e) {
        prompt(`Copy ${label}:`, value);
      }
    };
    const dashboardUrl = addToken(info.urls[0]);
    const dashboardBtn = document.createElement('button');
    dashboardBtn.type = 'button';
    dashboardBtn.className = 'btn btn-ghost';
    dashboardBtn.textContent = 'Copy dashboard';
    dashboardBtn.style.cssText = 'padding:6px 10px;font-size:11px;white-space:nowrap;';
    dashboardBtn.onclick = () => copyText('link dashboard', dashboardUrl);
    urlsDiv.appendChild(dashboardBtn);

    const lanUrls = info.urls.filter(u => {
      try {
        const host = new URL(u).hostname;
        return host !== 'localhost' && host !== '127.0.0.1' && host !== '::1';
      } catch (e) {
        return false;
      }
    });
    const primaryUrl = lanUrls[0] || info.urls[0];
    const mobileBase = primaryUrl.replace(/\/?$/, '') + '/mobile';
    const mobileUrlObj = new URL(addToken(mobileBase));
    if (currentLessonId) mobileUrlObj.searchParams.set('lesson_id', String(currentLessonId));
    const mobileUrl = mobileUrlObj.toString();
    const qrDiv = document.getElementById('qrCanvas');
    qrDiv.innerHTML = `<img src="${escapeAttr(withToken('/api/qr?data=' + encodeURIComponent(mobileUrl)))}" width="110" height="110" style="border-radius:4px;" title="Mở trên điện thoại" onerror="this.remove()">`;
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'btn btn-primary';
    copyBtn.textContent = 'Copy mobile LAN';
    copyBtn.style.cssText = 'padding:7px 12px;font-size:11px;white-space:nowrap;';
    copyBtn.onclick = () => copyText('link mobile', mobileUrl);
    urlsDiv.appendChild(copyBtn);
  } catch(e) {
    console.error('loadServerInfo error', e);
  }
}

// ─── Feed items ──────────────────────────────────────────────────────────────
const ATTENDANCE_FEED_HISTORY_PREFIX = 'facecheckin_attendance_feed_v1';
const ATTENDANCE_FEED_HISTORY_LIMIT = 80;

function lessonFeedHistoryKey(lessonId = currentLessonId) {
  return lessonId ? `${ATTENDANCE_FEED_HISTORY_PREFIX}_${lessonId}` : null;
}

function readLessonFeedHistory(lessonId = currentLessonId) {
  const key = lessonFeedHistoryKey(lessonId);
  if (!key) return [];
  try {
    const items = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(items) ? items : [];
  } catch (e) {
    console.warn('Could not read attendance feed history', e);
    return [];
  }
}

function writeLessonFeedHistory(items, lessonId = currentLessonId) {
  const key = lessonFeedHistoryKey(lessonId);
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(items.slice(-ATTENDANCE_FEED_HISTORY_LIMIT)));
  } catch (e) {
    console.warn('Could not save attendance feed history', e);
  }
}

function updateFeedHistoryControls(count = null) {
  const feed = document.getElementById('imageFeed');
  const total = count == null ? (feed?.children.length || 0) : count;
  const countEl = document.getElementById('feedHistoryCount');
  const clearBtn = document.getElementById('clearFeedHistoryBtn');
  if (countEl) countEl.textContent = String(total);
  if (clearBtn) clearBtn.style.display = total > 0 ? 'inline-flex' : 'none';
}

function rememberLessonFeedCapture(capture) {
  if (!currentLessonId) return;
  const history = readLessonFeedHistory(currentLessonId);
  history.push(capture);
  writeLessonFeedHistory(history, currentLessonId);
  updateFeedHistoryControls(history.length);
}

function loadLessonFeedHistory(lessonId = currentLessonId) {
  const feed = document.getElementById('imageFeed');
  if (!feed) return;
  feed.innerHTML = '';
  const history = readLessonFeedHistory(lessonId);
  history.forEach(capture => renderFeedCapture(capture));
  updateFeedHistoryControls(history.length);
  feed.scrollTop = feed.scrollHeight;
}

function clearCurrentLessonFeedHistory() {
  if (!currentLessonId) return;
  const history = readLessonFeedHistory(currentLessonId);
  if (!history.length) return;
  if (!confirm('Xóa danh sách ảnh chụp điểm danh cũ của tiết này? Dữ liệu điểm danh đã ghi sẽ không bị xóa.')) return;
  const key = lessonFeedHistoryKey(currentLessonId);
  if (key) localStorage.removeItem(key);
  const feed = document.getElementById('imageFeed');
  if (feed) feed.innerHTML = '';
  updateFeedHistoryControls(0);
  showToast('Đã xóa ảnh chụp cũ khỏi danh sách hiển thị', 'success');
}

function feedThumb(url, fallback = '?', title = '') {
  if (!url) return `<div class="feed-face-thumb" title="${escapeAttr(title)}">${escapeHtml(fallback)}</div>`;
  return `
    <div class="feed-face-thumb" title="${escapeAttr(title)}">
      <img src="${escapeAttr(withToken(url))}" alt="" onerror="this.parentElement.textContent='${escapeAttr(fallback)}'">
    </div>`;
}

function feedStatusBadge(face) {
  if (face.recognized === false) {
    return '<span class="feed-status-badge unknown">Không nhận ra</span>';
  }
  if (face.lesson_recorded) {
    return '<span class="feed-status-badge recorded">✓ Đã ghi</span>';
  }
  return '<span class="feed-status-badge duplicate">↩ Đã điểm danh</span>';
}

function renderFeedCapture({ faces = [], time = '', imageUrl = '' }) {
  const feed = document.getElementById('imageFeed');
  if (!feed) return;
  const item = document.createElement('div');
  item.className = 'feed-item';

  const peopleRows = faces.map(f => {
    const conf = f.confidence != null ? (f.confidence * 100).toFixed(0) + '%' : '—';
    const displayName = f.recognized === false ? 'Không nhận ra' : (f.name || 'Không rõ');
    const mssv = f.recognized === false ? 'unknown' : (f.mssv || '—');
    const registeredFallback = f.recognized === false ? '?' : '—';
    return `
      <div class="feed-person-row">
        <div class="feed-face-pair">
          ${feedThumb(f.detected_face_url, '?', 'Khuôn mặt phát hiện trong ảnh điểm danh')}
          <span class="feed-face-separator">↔</span>
          ${feedThumb(f.registered_face_url, registeredFallback, 'Ảnh đăng ký đầu tiên')}
        </div>
        <div class="feed-person-main">
          <div class="feed-person-name">${escapeHtml(displayName)}</div>
          <div class="feed-person-meta">${escapeHtml(mssv)} · Độ khớp ${escapeHtml(conf)}</div>
        </div>
        ${feedStatusBadge(f)}
      </div>`;
  }).join('');
  const summaryText = faces.length > 0 ? `📸 ${faces.length} khuôn mặt` : '📸 Không phát hiện khuôn mặt';
  const emptyText = faces.length > 0 ? '' : '<div style="font-size:12px;color:var(--text3);padding:0 14px 12px;">Ảnh vẫn được lưu để kiểm tra vùng nhận diện.</div>';

  item.innerHTML = `
    <div class="feed-item-header" style="justify-content:space-between;">
      <div style="font-size:12px;font-weight:700;color:var(--text1);">${summaryText}</div>
      <div class="feed-item-time">${escapeHtml(time)}</div>
    </div>
    ${peopleRows ? `<div class="feed-people-list">${peopleRows}</div>` : ''}
    ${emptyText}
    ${imageUrl ? `<img class="feed-main-image" src="${escapeAttr(imageUrl)}" alt="" onerror="this.style.display='none'">` : ''}
  `;
  feed.appendChild(item);
  updateFeedHistoryControls();
  return item;
}

function addFeedItemBatch({ faces, time, imageUrl }) {
  const feed = document.getElementById('imageFeed');
  if (!feed) return;
  const capture = {
    faces: Array.isArray(faces) ? faces : [],
    time: time || '',
    imageUrl: imageUrl || '',
    createdAt: Date.now(),
  };
  renderFeedCapture(capture);
  rememberLessonFeedCapture(capture);
  feed.scrollTop = feed.scrollHeight;
}

function addFeedItem({ name, mssv, conf, time, imageUrl, recognized, recorded }) {
  const feed = document.getElementById('imageFeed');
  if (!feed) return;
  const item = document.createElement('div');
  item.className = 'feed-item';
  let badge;
  if (!recognized) {
    badge = `<span style="font-size:10px; background:rgba(255,80,80,.15); color:var(--red); border-radius:4px; padding:2px 6px;">Không nhận ra</span>`;
  } else if (recorded) {
    badge = `<span style="font-size:10px; background:rgba(0,200,150,.15); color:var(--teal); border-radius:4px; padding:2px 6px;">✓ Đã ghi</span>`;
  } else {
    badge = `<span style="font-size:10px; background:rgba(255,180,0,.15); color:#c8860a; border-radius:4px; padding:2px 6px;">↩ Đã điểm danh</span>`;
  }
  item.innerHTML = `
    <div class="feed-item-header">
      <div>
        <div class="feed-item-name">${escapeHtml(name)}</div>
        <div style="font-size:10px; color:var(--text3);">${escapeHtml(mssv)} · ${escapeHtml(conf)}</div>
      </div>
      ${badge}
      <div class="feed-item-time">${escapeHtml(time)}</div>
    </div>
    ${imageUrl ? `<img class="feed-main-image" src="${escapeAttr(imageUrl)}" alt="" onerror="this.style.display='none'">` : ''}
  `;
  feed.appendChild(item);
  // Scroll to bottom (newest)
  feed.scrollTop = feed.scrollHeight;
}

// ─── Local Webcam ──────────────────────────────────────────────────────────
let localStream = null;
let localCameraOpening = false;
let autoCaptureTimer = null;
let realtimeStream = null;
let realtimeTimer = null;
let realtimeProcessing = false;
let realtimeFrameCount = 0;

const REALTIME_SETTINGS_KEY = 'facecheckin_realtime_settings';

function getRealtimeSettings() {
  const defaults = { intervalMs: 2500, frameWidth: 720, jpegQuality: 0.75, mirrorPreview: true };
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem(REALTIME_SETTINGS_KEY) || '{}') };
  } catch (e) {
    return defaults;
  }
}

function setRealtimeStatus(isOn, text) {
  const dot = document.getElementById('realtimeStatusDot');
  const status = document.getElementById('realtimeStatusText');
  const placeholder = document.getElementById('realtimePlaceholder');
  const startBtn = document.getElementById('realtimeStartBtn');
  const stopBtn = document.getElementById('realtimeStopBtn');
  if (dot) dot.classList.toggle('on', !!isOn);
  if (status) status.textContent = text || (isOn ? 'Đang quét' : 'Đang tắt');
  if (placeholder) placeholder.style.display = isOn ? 'none' : 'flex';
  if (startBtn) startBtn.style.display = isOn ? 'none' : 'inline-flex';
  if (stopBtn) stopBtn.style.display = isOn ? 'inline-flex' : 'none';
}

function renderRealtimeSettingsSummary() {
  const settings = getRealtimeSettings();
  const summary = document.getElementById('realtimeSettingsSummary');
  if (!summary) return;
  summary.innerHTML =
    `Interval: <b>${settings.intervalMs}ms</b><br>` +
    `Frame width: <b>${settings.frameWidth}px</b><br>` +
    `JPEG quality: <b>${settings.jpegQuality}</b><br>` +
    `Preview: <b>${settings.mirrorPreview ? 'lat guong' : 'binh thuong'}</b>`;
}

function loadRealtimeSettingsIntoUi() {
  const settings = getRealtimeSettings();
  const interval = document.getElementById('rtFrameInterval');
  const width = document.getElementById('rtFrameWidth');
  const quality = document.getElementById('rtJpegQuality');
  const mirror = document.getElementById('rtMirrorPreview');
  if (interval) interval.value = settings.intervalMs;
  if (width) width.value = settings.frameWidth;
  if (quality) quality.value = settings.jpegQuality;
  if (mirror) mirror.checked = settings.mirrorPreview !== false;
  const video = document.getElementById('realtimeVideo');
  if (video) video.style.transform = settings.mirrorPreview ? 'scaleX(-1)' : '';
  renderRealtimeSettingsSummary();
}

function saveRealtimeSettingsFromUi() {
  const settings = {
    intervalMs: Math.max(500, parseInt(document.getElementById('rtFrameInterval')?.value || '2500', 10)),
    frameWidth: Math.max(320, parseInt(document.getElementById('rtFrameWidth')?.value || '720', 10)),
    jpegQuality: Math.min(1, Math.max(0.3, parseFloat(document.getElementById('rtJpegQuality')?.value || '0.75'))),
    mirrorPreview: document.getElementById('rtMirrorPreview')?.checked !== false,
  };
  localStorage.setItem(REALTIME_SETTINGS_KEY, JSON.stringify(settings));
  loadRealtimeSettingsIntoUi();
  return settings;
}

function updateLocalCameraUi(isOn) {
  const camPanel = document.getElementById('camPanel');
  const camControls = document.getElementById('camControlsNoSplit');
  if (camPanel) camPanel.style.display = '';
  if (camControls) camControls.style.display = 'none';

  const placeholder = document.getElementById('localCameraPlaceholder');
  const panelOpenBtn = document.getElementById('panelOpenCameraBtn');
  const panelCloseBtn = document.getElementById('panelCloseCameraBtn');
  const panelCaptureBtn = document.getElementById('panelCaptureBtn');
  const panelAutoLine = document.getElementById('panelAutoCaptureLine');

  if (placeholder) placeholder.style.display = isOn ? 'none' : 'flex';
  if (panelOpenBtn) panelOpenBtn.style.display = isOn ? 'none' : 'inline-flex';
  if (panelCloseBtn) panelCloseBtn.style.display = isOn ? 'inline-flex' : 'none';
  if (panelCaptureBtn) panelCaptureBtn.style.display = isOn ? 'inline-flex' : 'none';
  if (panelAutoLine) panelAutoLine.style.display = isOn ? 'flex' : 'none';

  const openCameraBtn = document.getElementById('openCameraBtn');
  const closeCameraBtn = document.getElementById('closeCameraBtn');
  const captureBtn = document.getElementById('captureBtn');
  const autoCaptureLine = document.getElementById('autoCaptureLine');
  if (openCameraBtn) openCameraBtn.style.display = 'none';
  if (closeCameraBtn) closeCameraBtn.style.display = 'none';
  if (captureBtn) captureBtn.style.display = 'none';
  if (autoCaptureLine) autoCaptureLine.style.display = 'none';
}

function isLocalCameraTabActive() {
  const attendanceScreen = document.getElementById('screen-attendance');
  const cameraPanel = document.getElementById('tabPanelCamera');
  return !!(
    attendanceScreen?.classList.contains('active') &&
    currentAttendanceTab === 'camera' &&
    cameraPanel &&
    cameraPanel.style.display !== 'none'
  );
}

async function openLocalCamera() {
  if (localStream || localCameraOpening) return;
  localCameraOpening = true;
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Trình duyệt không hỗ trợ camera hoặc chưa chạy trên HTTPS/localhost');
    }
    localStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    if (!isLocalCameraTabActive()) {
      localStream.getTracks().forEach(t => t.stop());
      localStream = null;
      updateLocalCameraUi(false);
      return;
    }
    const video = document.getElementById('localVideo');
    video.srcObject = localStream;
    updateLocalCameraUi(true);
  } catch(e) {
    showToast('Không thể mở camera: ' + e.message, 'error');
  } finally {
    localCameraOpening = false;
  }
}

function closeLocalCamera() {
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop());
    localStream = null;
  }
  if (autoCaptureTimer) { clearInterval(autoCaptureTimer); autoCaptureTimer = null; }
  const video = document.getElementById('localVideo');
  if (video) { video.srcObject = null; }

  ['autoCaptureCheck', 'autoCaptureCheck2'].forEach(id => {
    const el = document.getElementById(id); if (el) el.checked = false;
  });
  updateLocalCameraUi(false);
}

async function startRealtimeAttendance() {
  if (realtimeStream) return;
  const settings = saveRealtimeSettingsFromUi();
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Trình duyệt không hỗ trợ camera hoặc chưa chạy trên HTTPS/localhost');
    }
    realtimeStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: Math.max(settings.frameWidth, 640) }, height: { ideal: 720 } }
    });
    const video = document.getElementById('realtimeVideo');
    if (video) video.srcObject = realtimeStream;
    realtimeFrameCount = 0;
    const frameEl = document.getElementById('realtimeFrameCount');
    const lastEl = document.getElementById('realtimeLastScan');
    if (frameEl) frameEl.textContent = '0';
    if (lastEl) lastEl.textContent = '—';
    setRealtimeStatus(true, 'Đang quét');
    realtimeTimer = setInterval(sendRealtimeFrame, settings.intervalMs);
    setTimeout(sendRealtimeFrame, 600);
  } catch(e) {
    stopRealtimeAttendance();
    showToast('Không thể mở realtime camera: ' + e.message, 'error');
  }
}

function stopRealtimeAttendance() {
  if (realtimeTimer) { clearInterval(realtimeTimer); realtimeTimer = null; }
  if (realtimeStream) {
    realtimeStream.getTracks().forEach(track => track.stop());
    realtimeStream = null;
  }
  realtimeProcessing = false;
  const video = document.getElementById('realtimeVideo');
  if (video) video.srcObject = null;
  setRealtimeStatus(false, 'Đang tắt');
}

async function sendRealtimeFrame() {
  if (!realtimeStream || realtimeProcessing) return;
  const video = document.getElementById('realtimeVideo');
  if (!video || !video.videoWidth) return;
  realtimeProcessing = true;
  setRealtimeStatus(true, 'Đang xử lý...');
  const settings = getRealtimeSettings();
  const canvas = document.getElementById('realtimeCanvas');
  const scale = Math.min(1, settings.frameWidth / video.videoWidth);
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  try {
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(b => b ? resolve(b) : reject(new Error('Canvas toBlob failed')), 'image/jpeg', settings.jpegQuality);
    });
    await sendAttendanceImage(blob, 'realtime_' + Date.now() + '.jpg', currentLessonId);
    realtimeFrameCount += 1;
    const frameEl = document.getElementById('realtimeFrameCount');
    const lastEl = document.getElementById('realtimeLastScan');
    if (frameEl) frameEl.textContent = String(realtimeFrameCount);
    if (lastEl) lastEl.textContent = new Date().toLocaleTimeString('vi-VN');
    const flash = document.getElementById('realtimeFlash');
    if (flash) { flash.style.opacity = '0.35'; setTimeout(() => flash.style.opacity = '0', 120); }
  } catch(e) {
    console.error('sendRealtimeFrame error:', e);
    showToast('Realtime lỗi: ' + e.message, 'error');
  } finally {
    realtimeProcessing = false;
    if (realtimeStream) setRealtimeStatus(true, 'Đang quét');
  }
}

function clearAutoCapture() {
  if (autoCaptureTimer) { clearInterval(autoCaptureTimer); autoCaptureTimer = null; }
}

function toggleAutoCapture2() {
  const checked = document.getElementById('autoCaptureCheck2').checked;
  clearAutoCapture();
  if (checked) {
    const other = document.getElementById('autoCaptureCheck');
    if (other) other.checked = false;
    const secs = parseInt(document.getElementById('autoCaptureInterval2').value) || 5;
    autoCaptureTimer = setInterval(captureAndSend, secs * 1000);
  }
}

async function captureAndSend() {
  if (isCapturing) return;
  if (!localStream) { showToast('Camera chưa được mở', 'error'); return; }
  const lessonId = currentLessonId;
  const video = document.getElementById('localVideo');
  if (!video.videoWidth) { showToast('Camera chưa sẵn sàng, thử lại', 'error'); return; }
  isCapturing = true;

  // Flash effect
  const flash = document.getElementById('captureFlash');
  if (flash) { flash.style.opacity = '0.8'; setTimeout(() => flash.style.opacity = '0', 150); }

  const btn = document.getElementById('panelCaptureBtn') || document.getElementById('captureBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Đang xử lý...'; }

  const canvas = document.getElementById('captureCanvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);

  try {
    // Convert canvas to blob using Promise wrapper
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(b => b ? resolve(b) : reject(new Error('Canvas toBlob failed')), 'image/jpeg', 0.92);
    });

    await sendAttendanceImage(blob, 'capture_' + Date.now() + '.jpg', lessonId);
  } catch(e) {
    console.error('captureAndSend error:', e);
    showToast('Lỗi: ' + e.message, 'error');
  } finally {
    isCapturing = false;
    if (btn) { btn.disabled = false; btn.innerHTML = '<span>📸</span> Chụp & Điểm danh'; }
  }
}

async function sendAttendanceImage(imageBlob, filename, lessonId = currentLessonId) {
  const formData = new FormData();
  formData.append('image', imageBlob, filename);
  if (lessonId) formData.append('lesson_id', String(lessonId));

  const resp = await fetch(withToken('/api/recognize'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Server ${resp.status}: ${errText.slice(0,100)}`);
  }

  const resultHdr = resp.headers.get('X-Recognition-Result');
  await resp.blob();
  if (!resultHdr) return;

  try {
    const res = JSON.parse(resultHdr);
    if (res.known && res.known.length > 0) {
      showToast('✓ ' + res.known.join(', '), 'success');
    } else if (res.error) {
      showToast('Lỗi: ' + res.error, 'error');
    } else {
      showToast('Không nhận ra khuôn mặt', 'error');
    }
  } catch(e) {
    console.warn('Parse X-Recognition-Result failed', e);
  }
}

async function uploadAttendanceImage() {
  if (isCapturing) return;
  const input = document.getElementById('attendanceImageInput');
  const file = input?.files?.[0];
  if (!file) return;

  if (!file.type.startsWith('image/')) {
    showToast('Vui lòng chọn file ảnh', 'error');
    input.value = '';
    return;
  }

  const maxSize = 10 * 1024 * 1024;
  if (file.size > maxSize) {
    showToast('Ảnh quá lớn, vui lòng chọn ảnh dưới 10MB', 'error');
    input.value = '';
    return;
  }

  isCapturing = true;
  const btn = document.getElementById('attendanceImageUploadBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Đang xử lý ảnh...'; }

  try {
    await sendAttendanceImage(file, file.name || ('upload_' + Date.now() + '.jpg'), currentLessonId);
  } catch(e) {
    console.error('uploadAttendanceImage error:', e);
    showToast('Lỗi upload ảnh: ' + e.message, 'error');
  } finally {
    isCapturing = false;
    if (btn) { btn.disabled = false; btn.textContent = '⬆️ Chọn ảnh & Điểm danh'; }
    if (input) input.value = '';
  }
}

function toggleAutoCapture() {
  const checked = document.getElementById('autoCaptureCheck').checked;
  clearAutoCapture();
  if (checked) {
    const other = document.getElementById('autoCaptureCheck2');
    if (other) other.checked = false;
    const secs = parseInt(document.getElementById('autoCaptureInterval').value) || 5;
    autoCaptureTimer = setInterval(captureAndSend, secs * 1000);
    showToast(`Tự động chụp mỗi ${secs} giây`, 'success');
  }
}
