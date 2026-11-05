const state = { analysis: null, hmAnalysis: null, brief: null, briefVersions: [], variants: [], evaluations: [], dirty: false, selected: new Set() };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `요청 실패 (${response.status})`);
  return data;
}

function sourceMarkup(source) {
  return `<div class="evidence-item"><button class="evidence-open" type="button" data-record-id="${escapeHtml(source.record_id)}">${escapeHtml(source.label || source.record_id)} · ${escapeHtml(source.record_id)} ↗</button><span>${escapeHtml(source.source_name)} · ${escapeHtml(source.period)}</span><span>버전 ${escapeHtml(source.version)} · 기준일 ${escapeHtml(source.as_of)}</span><span class="permission">권한: ${escapeHtml(source.permission)}</span></div>`;
}

function renderKpis(analysis) {
  $('#kpiGrid').innerHTML = analysis.kpis.map((kpi, index) => `<article class="kpi-card"><div class="kpi-top"><span>${escapeHtml(kpi.label)}</span><span>0${index + 1}</span></div><div class="kpi-value">${escapeHtml(kpi.value)}</div><div class="kpi-unit">${escapeHtml(kpi.unit)}</div><div class="kpi-period">${escapeHtml(kpi.period)} · ${escapeHtml(kpi.source_ids.join(', '))}</div><button class="kpi-evidence" type="button" data-record-id="${escapeHtml(kpi.record_id)}">집계 근거 보기 ↗</button></article>`).join('');
  $('#periodLabel').textContent = `판매 관측 ${analysis.period.start} — ${analysis.period.end} · ${analysis.period.weeks}주`;
}

function renderOpportunities(analysis) {
  $('#opportunityGrid').innerHTML = analysis.opportunities.map((item, index) => `<article class="opportunity-card">
    <header><span class="type-chip">${escapeHtml(item.kind)}</span><span class="opportunity-value">${escapeHtml(item.value)}</span></header>
    <h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.summary)}</p>
    <div class="caveat">${escapeHtml(item.caveat)}</div>
    <button class="evidence-toggle" type="button" aria-expanded="false" data-evidence="op-${index}">근거 ${item.evidence.length}개 보기 ＋</button>
    <div class="evidence-list" id="op-${index}" hidden>${item.evidence.map(sourceMarkup).join('')}</div>
  </article>`).join('');
  $$('.evidence-toggle').forEach(button => button.addEventListener('click', () => {
    const box = document.getElementById(button.dataset.evidence);
    const open = box.hidden;
    box.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    button.textContent = open ? '근거 숨기기 −' : `근거 ${box.children.length}개 보기 ＋`;
  }));
}

function renderProducts(analysis) {
  $('#productRows').innerHTML = analysis.products.map(product => `<tr>
    <td>${escapeHtml(product.style_id)}</td>
    <td><span class="product-name">${escapeHtml(product.name)}</span><span class="product-attrs">${escapeHtml(product.color)} · ${escapeHtml(product.material)} · ${escapeHtml(product.fit)} · ${escapeHtml(product.size_range)} · ₩${product.price_krw.toLocaleString()}</span></td>
    <td class="number">${product.units.toLocaleString()} units</td>
    <td>₩${product.revenue_krw.toLocaleString()}</td><td>${(product.discount_rate * 100).toFixed(0)}%</td>
    <td>${(product.return_rate * 100).toFixed(1)}%</td><td>${escapeHtml(product.channel)}</td><td>${product.on_hand_units.toLocaleString()} units</td><td>${product.inbound_units.toLocaleString()} units</td><td>${product.cover_weeks}주</td><td>${product.lead_time_days}일</td><td>${product.stockout_days}일</td>
    <td><button class="tiny-link" data-product-evidence="${escapeHtml(product.style_id)}">근거 보기</button></td>
  </tr><tr class="product-evidence-row" id="product-evidence-${escapeHtml(product.style_id)}" hidden><td colspan="13">${product.evidence.map(sourceMarkup).join('')}</td></tr>`).join('');
  $$('[data-product-evidence]').forEach(button => button.addEventListener('click', () => {
    const row = document.getElementById(`product-evidence-${button.dataset.productEvidence}`);
    row.hidden = !row.hidden;
    button.textContent = row.hidden ? '근거 보기' : '근거 숨기기';
  }));
  $('#analysisNotes').innerHTML = analysis.analysis_notes.map(note => `<span>${escapeHtml(note)}</span>`).join('');
}

function renderDocuments(results, query) {
  $('#searchResults').innerHTML = results.length ? results.map(result => `<article class="search-result">
    <h4>${escapeHtml(result.title)}</h4><div class="result-section">${escapeHtml(result.section)} · ${escapeHtml(result.season)} · ${escapeHtml(result.document_version)} · relevance ${result.score}</div>
    <p>${escapeHtml(result.text)}</p>${sourceMarkup(result.source)}
  </article>`).join('') : `<div class="empty-result">“${escapeHtml(query)}”와 일치하는 문서 근거를 찾지 못했습니다. 추측으로 보완하지 말고 “자료에서 근거를 찾지 못함”으로 남겨 주세요.</div>`;
}

function fillBrief(brief) {
  state.brief = brief;
  const form = $('#briefForm');
  for (const [key, value] of Object.entries(brief.payload)) {
    const field = form.elements.namedItem(key);
    if (field) field.value = value;
  }
  $('#briefVersion').textContent = `v${brief.version}`;
  $('#generationVersion').textContent = `v${brief.version}`;
  const evidence = state.analysis.opportunities.flatMap(item => item.evidence);
  const unique = [...new Map(evidence.map(item => [item.record_id, item])).values()];
  $('#briefEvidence').innerHTML = unique.map(sourceMarkup).join('');
  state.dirty = false;
}

function briefPayload() {
  const payload = Object.fromEntries(new FormData($('#briefForm')).entries());
  return payload;
}

function renderVariants() {
  const grid = $('#variantGrid');
  if (!state.variants.length) {
    grid.innerHTML = `<div class="empty-card"><span>✧</span><b>아직 시안이 없습니다</b><p>브리프를 확인한 뒤 여러 방향을 생성해 비교해 보세요.</p></div>`;
    return;
  }
  grid.innerHTML = state.variants.map(variant => `<article class="variant-card ${state.selected.has(variant.variant_id) ? 'selected' : ''}" data-variant-card="${escapeHtml(variant.variant_id)}">
    <img class="variant-image" src="${escapeHtml(variant.image_url)}" alt="${escapeHtml(variant.title)} 목업 시안">
    <div class="variant-body"><div class="variant-title-row"><h4>${escapeHtml(variant.title)}</h4><label><input type="checkbox" data-select-variant="${escapeHtml(variant.variant_id)}" ${state.selected.has(variant.variant_id) ? 'checked' : ''}> 비교</label></div>
      <div class="variant-meta">${variant.image_source === 'model_generated' ? 'ImageGen · 실사 콘셉트 사진' : '로컬 SVG 목업'} · ${escapeHtml(variant.image_type === 'product' ? '상품 단독' : '착장 콘셉트')} · Brief v${variant.brief_version} · ${escapeHtml(variant.model)} · ${escapeHtml(variant.created_at)}</div>
      <details class="prompt-details"><summary>사용 입력과 생성 정보</summary><p>${escapeHtml(variant.prompt)}</p></details>
      <details class="eval-form"><summary>이 시안 평가하기</summary><form data-eval-form="${escapeHtml(variant.variant_id)}">
        <div class="eval-grid">${ratingField('brand_fit','브랜드 적합성')}${ratingField('customer_need','고객 니즈')}${ratingField('differentiation','차별성')}${ratingField('price_feasibility','가격 검토')}${ratingField('production_feasibility','생산 검토')}</div>
        <label class="adopt-row"><input type="checkbox" name="adopted"> 채택 후보로 표시</label>
        <textarea name="feedback" rows="2" placeholder="수정 요청 또는 검토 의견"></textarea>
        <button class="primary-button" type="submit">검토 기록 저장</button><span class="inline-status" aria-live="polite"></span>
      </form></details>
    </div>
  </article>`).join('');
  wireImageFallbacks(grid);
  $$('[data-select-variant]').forEach(input => input.addEventListener('change', () => {
    input.checked ? state.selected.add(input.dataset.selectVariant) : state.selected.delete(input.dataset.selectVariant);
    updateCompare();
    renderVariants();
  }));
  $$('[data-eval-form]').forEach(form => form.addEventListener('submit', saveEvaluation));
  updateCompare();
}

function ratingField(name, label) {
  return `<label class="rating-field">${label}<select name="${name}" required><option value="">1–5</option>${[1,2,3,4,5].map(n => `<option value="${n}">${n}</option>`).join('')}</select></label>`;
}

function updateCompare() {
  const ids = [...state.selected];
  $('#selectedCount').textContent = ids.length ? `${ids.length}개 시안을 선택했습니다` : '비교할 시안을 선택하세요';
  $('#compareButton').disabled = ids.length < 2;
  const selected = state.variants.filter(variant => state.selected.has(variant.variant_id));
  if ($('#comparePanel').hidden) return;
  $('#comparePanel').innerHTML = `<h4>시안 나란히 비교 · ${selected.length}개</h4><div class="compare-grid">${selected.map(item => `<figure><img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title)}"><figcaption><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.image_type === 'product' ? '상품 단독' : '착장')} · Brief v${item.brief_version}</span></figcaption></figure>`).join('')}</div>`;
  wireImageFallbacks($('#comparePanel'));
}

function renderEvaluations(items) {
  $('#evaluationList').innerHTML = items.length ? items.map(item => `<article class="evaluation-card">
    ${item.image_url ? `<img class="evaluation-thumb" src="${escapeHtml(item.image_url)}" alt="">` : ''}
    <div class="evaluation-info"><h4>${escapeHtml(item.variant_title || item.variant_id)} · Brief v${item.brief_version}</h4>
      <p>${escapeHtml(item.feedback || '추가 의견 없음')}<br><span>${escapeHtml(item.created_at)}</span></p>
      <div class="score-row"><span class="score-pill">브랜드 ${item.brand_fit}/5</span><span class="score-pill">고객 ${item.customer_need}/5</span><span class="score-pill">차별성 ${item.differentiation}/5</span><span class="score-pill">가격 ${item.price_feasibility}/5</span><span class="score-pill">생산 ${item.production_feasibility}/5</span><span class="${item.adopted ? 'adopted' : 'rejected'}">${item.adopted ? '채택 후보' : '추가 검토'}</span></div>
    </div></article>`).join('') : `<div class="empty-card"><span>◷</span><b>아직 검토 기록이 없습니다</b><p>이미지 시안 카드에서 평가를 남겨 보세요.</p></div>`;
  wireImageFallbacks($('#evaluationList'));
}

function renderHmAnalysis(report) {
  state.hmAnalysis = report;
  const period = report.observation_period;
  const kpis = [
    { label: '거래 구매 행', value: report.purchase_rows.toLocaleString(), unit: 'purchase rows', period: `${period.start}–${period.end}` },
    { label: '상품 코드 수', value: report.product_code_count.toLocaleString(), unit: 'product_code', period: '상품 마스터 전체' },
    { label: '상품 article ID', value: report.article_catalog_count.toLocaleString(), unit: 'article_id', period: '상품 마스터 전체' },
    { label: '거래 집계 행', value: report.weekly_article_channel_aggregate_rows.toLocaleString(), unit: 'week × article × channel', period: '월요일 시작 주 기준' },
  ];
  $('#hmKpiGrid').innerHTML = kpis.map((item,index) => `<article class="kpi-card"><div class="kpi-top"><span>${escapeHtml(item.label)}</span><span>0${index+1}</span></div><div class="kpi-value">${escapeHtml(item.value)}</div><div class="kpi-unit">${escapeHtml(item.unit)}</div><div class="kpi-period">${escapeHtml(item.period)} · ${escapeHtml(report.source_ids.articles)} / ${escapeHtml(report.source_ids.transactions)}</div></article>`).join('');
  const maxGroup = Math.max(...report.top_product_groups.map(group => group.purchase_rows));
  $('#hmGroups').innerHTML = report.top_product_groups.map(group => `<div class="hm-group-row"><div class="hm-group-label"><b>${escapeHtml(group.product_group_name)}</b><span>${group.purchase_rows.toLocaleString()} · ${(group.share_of_purchase_rows*100).toFixed(1)}%</span></div><progress max="100" value="${(group.purchase_rows/maxGroup*100).toFixed(2)}"></progress></div>`).join('');
  $('#hmChannels').innerHTML = report.channels.map(channel => `<article class="channel-card"><span>CHANNEL ID ${escapeHtml(channel.sales_channel_id)}</span><b>${channel.purchase_rows.toLocaleString()}</b><small>구매 행 · ${channel.unique_article_count.toLocaleString()} article IDs · ${channel.unique_product_code_count.toLocaleString()} product codes</small></article>`).join('');
  $('#hmStyleRows').innerHTML = report.top_styles.slice(0,10).map(style => `<tr><td class="number">${escapeHtml(style.product_code)}</td><td><span class="product-name">${escapeHtml(style.representative_prod_name)}</span><span class="product-attrs">대표 article ${escapeHtml(style.representative_article_id)} · ${style.article_id_count} article IDs</span></td><td>${escapeHtml(style.product_group_name)}<span class="product-attrs">${escapeHtml(style.product_type_name)}</span></td><td>${escapeHtml(style.representative_colour_group_name)}</td><td class="number">${style.purchase_rows.toLocaleString()}</td><td>${escapeHtml(style.price_mean_source_units)}</td><td>${escapeHtml(style.top_sales_channel_id)}</td></tr>`).join('');
  $('#hmSourceLine').textContent = `${report.source_ids.articles} + ${report.source_ids.transactions} · ${period.start}–${period.end}`;
  $('#hmLimitations').innerHTML = report.limitations.map(note => `<span>${escapeHtml(note)}</span>`).join('');
  $('#hmAnalysisStatus').textContent = `분석 완료 · ${report.data_status.replaceAll('_',' ')} · report v${report.analysis_version} · 생성 ${report.generated_at_utc}`;
}

async function loadHmAnalysis() {
  try {
    const report = await request('/api/hm-analysis');
    renderHmAnalysis(report);
    const planning = await request('/api/hm-planning-analysis');
    renderHmPlanningAnalysis(planning);
  } catch (error) {
    $('#hmAnalysisStatus').textContent = error.message;
    $('#hmKpiGrid').innerHTML = `<div class="empty-result">H&amp;M 요약 산출물이 아직 없습니다. 문서의 수집·처리 명세를 실행하면 이 영역이 채워집니다.</div>`;
  }
}

function renderHmPlanningAnalysis(report) {
  state.hmPlanningAnalysis = report;
  const colors = new Map();
  for (const row of report.color_mix) {
    const key = `${row.product_group_name}\u0000${row.product_type_name}`;
    const values = colors.get(key) || [];
    values.push(row);
    colors.set(key, values);
  }
  const seasonality = new Map(report.seasonality_and_growth.map(row => [`${row.product_group_name}\u0000${row.product_type_name}`, row]));
  const concentration = new Map(report.style_concentration.map(row => [`${row.product_group_name}\u0000${row.product_type_name}`, row]));
  $('#hmTypeRows').innerHTML = report.product_types.slice(0, 131).map(row => {
    const key = `${row.product_group_name}\u0000${row.product_type_name}`;
    const topColors = (colors.get(key) || []).slice(0, 3).map(item => `${item.colour_group_name} ${(item.share_within_type * 100).toFixed(0)}%`).join(' · ');
    const months = (seasonality.get(key)?.monthly_peak_week_start_months || []).map(month => `${month}월`).join(' · ');
    const top5 = concentration.get(key)?.top_5_style_share;
    return `<tr><td>${escapeHtml(row.product_group_name)}</td><td>${escapeHtml(row.product_type_name)}</td><td class="number">${row.purchase_rows.toLocaleString()}</td><td>${(row.share_of_joined_purchase_rows * 100).toFixed(2)}%</td><td>${row.unique_product_code_count.toLocaleString()}</td><td>${row.unique_article_count.toLocaleString()}</td><td>${escapeHtml(topColors)}</td><td>${escapeHtml(months)}</td><td>${top5 == null ? '—' : `${(top5 * 100).toFixed(1)}%`}</td></tr>`;
  }).join('');
  $('#hmOpportunityCards').innerHTML = report.opportunity_candidates.slice(0, 10).map(item => `<article class="hm-opportunity-card"><b>${escapeHtml(item.category.product_group_name)} · ${escapeHtml(item.category.product_type_name)}</b><span>${Number(item.observations.observed_purchase_rows).toLocaleString()} 구매 행 · 과거 규모 기준</span><small>${(item.observations.top_observed_colors || []).map(color => `${escapeHtml(color.name)} ${(color.share * 100).toFixed(0)}%`).join(' · ')}</small><small>관측 월 ${escapeHtml((item.observations.observed_month_peaks_by_week_start || []).join(', '))} · 상위 스타일 집중도 ${item.observations.top_5_style_share == null ? '미확인' : `${(item.observations.top_5_style_share * 100).toFixed(1)}%`}</small><small class="hm-caveat">${escapeHtml(item.limits.join(' '))}</small></article>`).join('');
  $('#hmPromptTemplate').textContent = JSON.stringify({
    brief: report.planning_brief_template,
    selected_opportunity_example: report.opportunity_candidates[0] || null,
  }, null, 2);
  $('#hmPlanningStatus').textContent = `${report.product_types.length}개 유형 · ${report.purchase_rows.toLocaleString()} 구매 행 · Article 기준 · 미매칭 ${report.unmatched_weekly_rows}`;
}

function wireImageFallbacks(container) {
  $$('img', container).forEach(image => image.addEventListener('error', () => {
    const fallback = document.createElement('div');
    fallback.className = 'image-fallback';
    fallback.textContent = '시안 이미지를 불러오지 못했습니다. 다시 생성하거나 브리프와 서버 상태를 확인해 주세요.';
    image.replaceWith(fallback);
  }, { once: true }));
}

function renderBriefHistory(items) {
  state.briefVersions = items;
  const container = $('#briefHistory');
  if (!items.length) {
    container.innerHTML = `<div class="history-empty">저장된 버전이 없습니다. 브리프를 수정하고 저장하면 버전 이력이 남습니다.</div>`;
    return;
  }
  container.innerHTML = items.map(item => `<article class="history-card"><div><span class="history-version">v${item.version}</span><b>${escapeHtml(item.payload.title)}</b><small>${escapeHtml(item.created_at)}</small></div><p>${escapeHtml(item.payload.color_pattern)} · ${escapeHtml(item.payload.silhouette_fit)}</p><button class="secondary-button" data-load-brief="${item.version}">불러와 새 버전으로 편집</button></article>`).join('');
  $$('[data-load-brief]').forEach(button => button.addEventListener('click', () => {
    const selected = state.briefVersions.find(item => item.version === Number(button.dataset.loadBrief));
    if (!selected) return;
    for (const [key, value] of Object.entries(selected.payload)) {
      const field = $('#briefForm').elements.namedItem(key);
      if (field) field.value = value;
    }
    state.dirty = true;
    $('#briefStatus').textContent = `v${selected.version} 내용을 불러왔습니다. 현재 버전은 보존됩니다. 수정 후 새 버전으로 저장하세요.`;
    $('#brief').scrollIntoView({ behavior: 'smooth' });
  }));
}

async function bootstrap() {
  try {
    const payload = await request('/api/bootstrap');
    state.analysis = payload.analysis;
    state.variants = payload.variants;
    state.evaluations = payload.evaluations;
    renderBriefHistory(payload.brief_versions);
    $('#fixtureNotice').textContent = payload.analysis.fixture_notice;
    $('#categorySelect').innerHTML = `<option>${escapeHtml(payload.analysis.scope.category)}</option>`;
    $('#seasonSelect').innerHTML = `<option>${escapeHtml(payload.analysis.scope.season)}</option>`;
    renderKpis(payload.analysis);
    renderOpportunities(payload.analysis);
    renderProducts(payload.analysis);
    fillBrief(payload.brief);
    renderVariants();
    renderEvaluations(payload.evaluations);
    $('#searchQuery').value = '27SS utility 색상 기능';
    const search = await request(`/api/search?q=${encodeURIComponent($('#searchQuery').value)}`);
    renderDocuments(search.results, search.query);
    $('#searchStatus').textContent = `${search.results.length}개 구절 · 합성 문서 · 로컬 키워드 검색`;
    await loadHmAnalysis();
  } catch (error) {
    $('#opportunityGrid').innerHTML = `<div class="empty-result">앱 초기화 실패: ${escapeHtml(error.message)}. 서버가 실행 중인지 확인하고 페이지를 새로고침하세요.</div>`;
  }
}

async function saveBrief(event) {
  event.preventDefault();
  const status = $('#briefStatus');
  status.textContent = '저장 중…';
  try {
    const result = await request('/api/brief', { method: 'POST', body: JSON.stringify(briefPayload()) });
    fillBrief(result);
    state.briefVersions = [{ version: result.version, payload: result.payload, created_at: result.created_at }, ...state.briefVersions];
    renderBriefHistory(state.briefVersions);
    status.textContent = `v${result.version} 저장 완료 · ${result.created_at}`;
  } catch (error) { status.textContent = error.message; }
}

async function generateVariants() {
  const status = $('#variantStatus');
  if (state.dirty) {
    status.textContent = '수정한 브리프를 먼저 저장해 버전을 만든 뒤 시안을 생성하세요.';
    $('#brief').scrollIntoView({ behavior: 'smooth' });
    return;
  }
  status.textContent = '로컬 목업 시안 생성 중…';
  $('#generateButton').disabled = true;
  try {
    const result = await request('/api/variants', { method: 'POST', body: JSON.stringify({ brief_version: state.brief.version, image_type: $('#imageType').value, count: Number($('#variantCount').value), ...briefPayload() }) });
    state.variants = [...result.variants, ...state.variants];
    renderVariants();
    status.textContent = `${result.variants.length}개 로컬 목업 생성 완료. 시안은 실제 상품 샘플이 아닙니다.`;
  } catch (error) { status.textContent = error.message; }
  finally { $('#generateButton').disabled = false; }
}

async function saveEvaluation(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $('.inline-status', form);
  status.textContent = '저장 중…';
  const values = Object.fromEntries(new FormData(form).entries());
  values.variant_id = form.dataset.evalForm;
  values.adopted = form.elements.namedItem('adopted').checked;
  try {
    await request('/api/evaluations', { method: 'POST', body: JSON.stringify(values) });
    const data = await request('/api/bootstrap');
    state.evaluations = data.evaluations;
    renderEvaluations(state.evaluations);
    status.textContent = '검토 기록을 저장했습니다.';
    form.reset();
  } catch (error) { status.textContent = error.message; }
}

async function searchDocuments(event) {
  event.preventDefault();
  const query = $('#searchQuery').value.trim();
  $('#searchStatus').textContent = '문서를 검색하고 있습니다…';
  $('#searchResults').innerHTML = '';
  try {
    const result = await request(`/api/search?q=${encodeURIComponent(query)}`);
    renderDocuments(result.results, query);
    $('#searchStatus').textContent = result.results.length ? `${result.results.length}개 구절 · 합성 문서 · 로컬 키워드 검색` : '일치하는 근거 없음';
  } catch (error) { $('#searchStatus').textContent = error.message; }
}

async function showEvidence(recordId) {
  const dialog = $('#evidenceDialog');
  $('#evidenceTitle').textContent = `근거 기록 · ${recordId}`;
  $('#evidenceContent').innerHTML = '<p class="loading">근거를 여는 중…</p>';
  dialog.showModal();
  try {
    const item = await request(`/api/evidence/${encodeURIComponent(recordId)}`);
    const allSources = [item.source, ...(item.related_sources || [])];
    $('#evidenceContent').innerHTML = `${allSources.map(source => `<div class="evidence-modal-meta"><b>${escapeHtml(source.name)}</b><span>${escapeHtml(item.kind)} · ${escapeHtml(source.period)}</span><span>버전 ${escapeHtml(source.version)} · 기준일 ${escapeHtml(source.as_of)}</span><span>권한: ${escapeHtml(source.permission)}</span></div>`).join('')}<pre class="evidence-json">${escapeHtml(JSON.stringify(item.record, null, 2))}</pre>`;
  } catch (error) {
    $('#evidenceContent').innerHTML = `<p class="empty-result">${escapeHtml(error.message)}</p>`;
  }
}

function bindUI() {
  $('#briefForm').addEventListener('submit', saveBrief);
  $('#briefForm').addEventListener('input', () => {
    state.dirty = true;
    $('#briefStatus').textContent = '저장하지 않은 수정사항이 있습니다.';
  });
  $('#generateButton').addEventListener('click', generateVariants);
  $('#searchForm').addEventListener('submit', searchDocuments);
  $('#compareButton').addEventListener('click', () => {
    const panel = $('#comparePanel');
    panel.hidden = !panel.hidden;
    updateCompare();
    if (!panel.hidden) panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  const dialog = $('#helpDialog');
  $('#helpButton').addEventListener('click', () => dialog.showModal());
  $('#closeHelp').addEventListener('click', () => dialog.close());
  $('#closeEvidence').addEventListener('click', () => $('#evidenceDialog').close());
  document.addEventListener('click', event => {
    const sourceButton = event.target.closest('[data-record-id]');
    if (sourceButton) showEvidence(sourceButton.dataset.recordId);
  });
  $$('.step').forEach(button => button.addEventListener('click', () => {
    $$('.step').forEach(item => item.classList.toggle('active', item === button));
    document.getElementById(button.dataset.target).scrollIntoView({ behavior: 'smooth' });
  }));
  const sections = $$('.section-block');
  const observer = new IntersectionObserver(entries => {
    const visible = entries.filter(entry => entry.isIntersecting).sort((a,b) => b.intersectionRatio-a.intersectionRatio)[0];
    if (visible) $$('.step').forEach(button => button.classList.toggle('active', button.dataset.target === visible.target.id));
  }, { rootMargin: '-22% 0px -60% 0px', threshold: [0,.25,.6] });
  sections.forEach(section => observer.observe(section));
}

bindUI();
bootstrap();
