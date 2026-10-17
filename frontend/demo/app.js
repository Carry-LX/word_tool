'use strict';
const $ = id => document.getElementById(id);
let bootstrap, job = null, timer = null, current = null, samples = [], viewed = null, viewMode = 'pages', pageIndex = 0;
let generation = 0;
let followStage = true, selectedStage = null, resultKey = '', resultImageId = null;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 409 && data.job) { job = data.job; renderJob(); schedulePoll(); }
    throw new Error(data.error || '请求失败，请稍后重试。');
  }
  return data;
}
function notice(message) { $('notice').hidden = !message; $('notice').textContent = message || ''; }
function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
function busy() { return job && ['pending', 'running'].includes(job.status); }
function currentLabel() {
  if (!current) return;
  const isThisJob = job?.status === 'success' && job.report?.id === current.id;
  $('current-label').textContent = current.origin === 'current' ? (isThisJob ? '本次生成' : '上次生成') : '已验收报告示例';
  $('current-label').className = `label ${isThisJob ? 'current' : ''}`;
  $('current-status').textContent = current.origin === 'current' ? (isThisJob ? '本次真实运行结果 · 页面检查通过' : '此前运行结果 · 可预览并下载') : '历史已验收结果 · 可打开完整页面检查';
}
function updateSubject() {
  const subject = bootstrap.subjects.find(row => row.code === $('subject').value);
  $('subject-details').textContent = subject ? `${subject.code} · ${subject.college || bootstrap.university}` : '';
  $('esi-note').hidden = !(bootstrap.esi_subject_codes || ['0830', '0805', '0703', '0812', '1002', '1007']).includes($('subject').value);
}
function metricText(node) {
  const m = node.metrics || {};
  if (node.status !== 'success') return '';
  return ({data: () => `${m.checked_inputs || 0} 项输入已检查`, resolve: () => `${m.ranking_records || 0} 条排名记录`, sources: () => `${m.available_sources || 0} 个可用榜单`, artifacts: () => `${m.generated_artifacts || 0} 项素材已生成`, word: () => 'Word 文件已保存', qa: () => `${m.page_count || 0} 页 · ${m.chart_count || 0} 张分析图`}[node.id] || (() => ''))();
}
function renderJob() {
  const stages = job ? job.stages : bootstrap.stages.map(row => ({...row, status: 'pending', message: row.description}));
  $('nodes').replaceChildren(...stages.map((node, index) => {
    const container = element('article', `node ${node.status}`);
    container.dataset.stage = node.id; container.dataset.status = node.status;
    container.setAttribute('role', 'button'); container.tabIndex = 0;
    const selectNode = () => {followStage = false; selectedStage = node.id; resultKey = ''; resultImageId = null; renderStageResult();};
    container.addEventListener('click', selectNode);
    container.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); selectNode();}});
    const top = element('div', 'node-top');
    top.append(element('span', 'node-icon', node.status === 'success' ? '✓' : node.status === 'error' ? '!' : `${index + 1}`), element('h3', '', node.name));
    container.append(top, element('p', '', node.status === 'pending' ? node.description : node.message), element('div', 'node-metric', metricText(node)));
    return container;
  }));
  const active = stages.find(row => row.status === 'running');
  const completed = stages.filter(row => row.status === 'success').length;
  const statusLabel = !job ? '等待开始' : job.status === 'success' ? '已完成' : job.status === 'error' ? '运行中断' : `进行中 ${completed} / ${stages.length}`;
  $('job-badge').textContent = statusLabel; $('job-badge').className = `badge ${job?.status || ''}`;
  $('start').disabled = !!busy(); $('subject').disabled = !!busy();
  $('start').querySelector('span').textContent = busy() ? '正在生成报告…' : '开始生成报告';
  $('activity-icon').textContent = job?.status === 'success' ? '✓' : job?.status === 'error' ? '!' : '→';
  $('activity-title').textContent = active ? active.name : job?.status === 'success' ? '报告已生成并完成页面检查' : job?.status === 'error' ? '本次生成未完成' : '准备开始';
  $('activity-message').textContent = job?.status === 'error' ? job.error : active ? active.message : job?.status === 'success' ? `${job.subject.name} · 可在下方预览并下载 Word` : '选定学科后，点击左侧按钮运行。';
  const events = job?.events || [];
  $('event-count').textContent = `${events.length} 条`;
  $('event-list').replaceChildren(...events.map(event => {
    const item = element('li'); item.append(element('time', '', event.at.slice(11, 19)), document.createTextNode(event.message)); return item;
  }));
  $('log-link').hidden = !job;
  if (job) $('log-link').href = `/api/jobs/${job.id}/log`;
  renderElapsed();
  currentLabel();
  renderStageResult();
}
function renderStageResult() {
  const stages = job?.stages || bootstrap.stages;
  if (followStage) selectedStage = stages.find(node => node.status === 'running')?.id || stages.filter(node => node.status === 'success').at(-1)?.id || stages[0].id;
  const node = stages.find(node => node.id === selectedStage) || stages[0];
  document.querySelectorAll('.node').forEach(card => {const selected = card.dataset.stage === node.id; card.classList.toggle('selected', selected); card.setAttribute('aria-pressed', String(selected));});
  $('follow-stage').setAttribute('aria-pressed', String(followStage)); $('follow-stage').textContent = followStage ? '跟随运行 ●' : '跟随运行 ○';
  $('stage-result-label').textContent = `${node.name} · ${node.status === 'success' ? '已完成' : node.status === 'running' ? '运行中' : '节点结果'}`;
  let result = node.result;
  if (!result && job?.report && node.id === 'qa') result = {title: '页面检查通过', summary: '已生成的报告页面', images: [{id: 'first', url: `/api/files/${job.report.id}/page/0`, label: '报告首页'}, {id: 'last', url: `/api/files/${job.report.id}/page/${job.report.page_count - 1}`, label: 'ESI 与精简建议'}]};
  const key = JSON.stringify([job?.id, node.id, result, resultImageId]);
  if (key === resultKey) return;
  resultKey = key;
  const body = $('stage-result-content');
  const images = result?.images || [];
  body.parentElement.classList.toggle('with-images', !!images.length);
  if (!result || (!result.rows?.length && !images.length && !result.stats?.length)) {
    const empty = element('div', 'stage-empty'); empty.append(element('span', '', '↗'), element('h3', '', job ? (node.status === 'pending' ? '此步骤尚未运行' : '正在准备本步骤的结果') : '当前步骤的结果会显示在这里'), element('p', '', node.description));
    empty.querySelector('h3').id = 'stage-result-title'; body.replaceChildren(empty); return;
  }
  const title = element('h3', 'stage-title', result.title); title.id = 'stage-result-title';
  const stats = element('div', 'stage-stats');
  (result.stats || []).forEach(stat => {const item = element('div', 'stage-stat'); item.append(element('strong', '', String(stat.value)), element('span', '', stat.label)); stats.append(item);});
  body.replaceChildren(title, element('p', 'stage-summary', result.summary), stats);
  if (images.length) {
    const selected = images.find(item => item.id === resultImageId) || images.at(-1);
    const picture = element('div', 'stage-picture'), image = element('img'); image.src = selected.url; image.alt = selected.label; picture.append(image); body.append(picture);
    const thumbs = element('div', 'stage-thumbs');
    images.forEach(item => {const button = element('button', item.id === selected.id ? 'selected' : ''); button.title = item.label; button.setAttribute('aria-label', item.label); const img = element('img'); img.src = item.url; img.alt = ''; button.append(img); button.addEventListener('click', () => {resultImageId = item.id; resultKey = ''; renderStageResult();}); thumbs.append(button);});
    body.append(thumbs);
  } else if (result.rows?.length) {
    const table = element('table', 'stage-table'), head = element('thead'), row = element('tr'); (result.columns || []).forEach(text => row.append(element('th', '', text))); head.append(row); table.append(head);
    const rows = element('tbody'); result.rows.forEach(values => {const row = element('tr'); values.forEach(text => row.append(element('td', '', String(text)))); rows.append(row);}); table.append(rows); body.append(table);
  }
}
function renderElapsed() {
  let seconds = job?.started_at ? Math.max(0, Math.floor(((job.finished_at ? Date.parse(job.finished_at) : Date.now()) - Date.parse(job.started_at)) / 1000)) : 0;
  $('elapsed').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
async function showCurrent(report) {
  const detail = await api(`/api/reports/${report.id}`);
  current = detail;
  currentLabel();
  $('current-pages').textContent = `${report.page_count} 页`;
  $('current-code').textContent = `${bootstrap.university} · ${report.code}`;
  $('current-name').textContent = report.name;
  $('current-meta').textContent = `${report.sources.join(' / ')} · ${report.chart_count} 张分析图`;
  $('current-tags').replaceChildren(...[...report.sources, ...(report.has_esi ? ['ESI 趋势'] : [])].map(text => element('span', '', text)));
  const cover = element('img'); cover.src = detail.pages[0]; cover.alt = `${report.name}报告首页`;
  $('current-cover').replaceChildren(cover); $('current-cover').disabled = false;
  $('preview').disabled = false; $('download').hidden = false; $('download').href = detail.docx_url;
  currentLabel();
}
async function sampleReports() {
  $('sample').disabled = true;
  try {
    const result = await api('/api/sample', {count: bootstrap.sample_count, exclude: samples.map(row => row.id)});
    samples = result.reports;
    $('sample-rule').textContent = result.rule;
    $('sample-pool').textContent = `从 ${result.pool_size} 份完整报告中随机抽取 ${samples.length} 份 · 点击可查看全部页面`;
    $('samples').replaceChildren(...samples.map(report => {
      const button = element('button', 'sample-card'); button.dataset.reportId = report.id;
      button.setAttribute('aria-label', `预览${report.name}，${report.page_count}页`);
      const thumbnail = element('div', 'sample-thumb');
      const cover = element('img'); cover.src = `/api/files/${report.id}/page/0`; cover.alt = `${report.name}报告首页`; cover.loading = 'lazy';
      thumbnail.append(cover);
      button.append(thumbnail, element('h4', '', report.name), element('p', '', `${report.page_count} 页 · ${report.sources.length} 个榜单 · ${report.origin === 'current' ? '本次生成' : '历史抽查'}`));
      button.addEventListener('click', () => openViewer(report)); return button;
    }));
  } finally { $('sample').disabled = false; }
}
function schedulePoll() { clearTimeout(timer); if (busy()) timer = setTimeout(pollJob, 900); }
async function pollJob() {
  try {
    job = (await api(`/api/jobs/${job.id}`)).job; renderJob();
    if (job.status === 'success') {
      await showCurrent(job.report); await sampleReports();
      const rows = await api('/api/reports'); $('report-count').textContent = rows.reports.length;
    } else if (job.status === 'error') notice(job.error);
  } catch (error) { notice(`进度连接暂时中断：${error.message} 页面会继续尝试读取本次任务。`); }
  schedulePoll();
}
async function startJob() {
  if (busy()) return;
  notice(''); $('start').disabled = true;
  followStage = true; resultImageId = null; resultKey = '';
  try {
    job = (await api('/api/jobs', {subject_code: $('subject').value})).job;
    renderJob(); schedulePoll();
  } catch (error) { notice(error.message); if (!busy()) $('start').disabled = false; }
}
async function openViewer(report) {
  const token = ++generation;
  try {
    const detail = await api(`/api/reports/${report.id}`);
    if (token !== generation) return;
    viewed = detail; viewMode = 'pages'; pageIndex = 0;
    $('viewer-title').textContent = `${report.name} · 学科发展分析报告`;
    $('viewer-origin').textContent = report.origin === 'current' ? '本次生成' : '历史已验收报告';
    $('viewer-download').href = detail.docx_url;
    $('charts-tab').disabled = !detail.charts.length;
    renderViewer(true);
    if (!$('viewer').open) $('viewer').showModal();
  } catch (error) { notice(error.message); }
}
function renderViewer(rebuild = false) {
  const images = viewed[viewMode];
  pageIndex = Math.min(Math.max(pageIndex, 0), images.length - 1);
  $('pages-tab').setAttribute('aria-selected', String(viewMode === 'pages'));
  $('charts-tab').setAttribute('aria-selected', String(viewMode === 'charts'));
  $('page-total').textContent = `/ ${images.length}`; $('page-number').value = pageIndex + 1; $('page-number').max = images.length;
  $('previous').disabled = pageIndex === 0; $('next').disabled = pageIndex === images.length - 1;
  $('last-page').hidden = viewMode !== 'pages';
  $('image-state').textContent = '正在读取页面…';
  $('page-image').src = images[pageIndex];
  $('page-image').alt = `${viewed.name} ${viewMode === 'pages' ? '第' : '图'} ${pageIndex + 1} ${viewMode === 'pages' ? '页' : ''}`;
  $('image-stage').classList.toggle('chart', viewMode === 'charts');
  $('image-stage').scrollTo(0, 0);
  if (rebuild) {
    $('thumbnails').replaceChildren(...images.map((url, index) => {
      const button = element('button'); const image = element('img');
      image.src = url; image.alt = ''; image.loading = 'lazy';
      button.append(image, document.createTextNode(`${viewMode === 'pages' ? '第' : '图'} ${index + 1}${viewMode === 'pages' ? ' 页' : ''}`));
      button.setAttribute('aria-label', `查看${viewMode === 'pages' ? '第' : '图'}${index + 1}${viewMode === 'pages' ? '页' : ''}`);
      button.addEventListener('click', () => {pageIndex = index; renderViewer();}); return button;
    }));
  }
  Array.from($('thumbnails').children).forEach((button, index) => {button.classList.toggle('selected', index === pageIndex); button.setAttribute('aria-current', String(index === pageIndex));});
}
function movePage(offset) { if (!viewed) return; pageIndex += offset; renderViewer(); }
$('subject').addEventListener('change', () => {updateSubject(); if (job && !busy()) {job = null; renderJob(); notice('');}});
$('follow-stage').addEventListener('click', () => {followStage = !followStage; resultKey = ''; resultImageId = null; renderStageResult();});
$('start').addEventListener('click', startJob);
$('sample').addEventListener('click', () => sampleReports().catch(error => notice(error.message)));
$('preview').addEventListener('click', () => current && openViewer(current));
$('current-cover').addEventListener('click', () => current && openViewer(current));
$('close-viewer').addEventListener('click', () => $('viewer').close());
$('previous').addEventListener('click', () => movePage(-1)); $('next').addEventListener('click', () => movePage(1));
$('last-page').addEventListener('click', () => {pageIndex = viewed.pages.length - 1; renderViewer();});
$('fit-page').addEventListener('click', () => {const fit = $('image-stage').classList.toggle('fit-page'); $('fit-page').textContent = fit ? '放大阅读' : '查看整页';});
$('page-number').addEventListener('change', () => {pageIndex = Number($('page-number').value) - 1 || 0; renderViewer();});
['pages', 'charts'].forEach(mode => $(`${mode}-tab`).addEventListener('click', () => {viewMode = mode; pageIndex = 0; renderViewer(true);}));
$('page-image').addEventListener('load', () => {$('image-state').textContent = '';});
$('page-image').addEventListener('error', () => {$('image-state').textContent = '页面读取失败，请切换后重试。';});
$('viewer').addEventListener('keydown', event => {if (event.target.tagName === 'INPUT') return; if (event.key === 'ArrowLeft') movePage(-1); if (event.key === 'ArrowRight') movePage(1);});
setInterval(() => {if (busy()) renderElapsed();}, 1000);

(async function init() {
  try {
    bootstrap = await api('/api/bootstrap');
    $('university').textContent = `${bootstrap.university} · 学科发展分析`;
    $('report-count').textContent = bootstrap.report_count;
    $('subject').replaceChildren(...bootstrap.subjects.map(row => {const option = element('option', '', `${row.name} (${row.code})`); option.value = row.code; return option;}));
    $('subject').value = bootstrap.default_subject_code; $('subject').disabled = false; updateSubject();
    const fresh = new URLSearchParams(location.search).get('new') === '1';
    job = fresh && !['pending', 'running'].includes(bootstrap.latest_job?.status) ? null : bootstrap.latest_job;
    if (job) {$('subject').value = job.subject.code; updateSubject();}
    renderJob(); $('sample').disabled = false;
    const rows = (await api('/api/reports')).reports;
    const example = job?.report || rows.find(row => row.code === bootstrap.default_subject_code) || rows[0];
    if (example) await showCurrent(example);
    await sampleReports(); schedulePoll();
  } catch (error) {notice(`工作台未能初始化：${error.message}`);}
})();
