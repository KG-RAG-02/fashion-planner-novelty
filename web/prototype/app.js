const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `요청 실패 (${response.status})`);
  return payload;
}

async function loadDemo() {
  try {
    const result = await request('/api/trend-planning-demo');
    $('#demo-status').textContent = '검토용 fixture';
    const trends = (result.evaluated_trends || []).map((item) => `<li><b>${esc(item.name || item.normalized_name)}</b><span>${esc(item.status || '평가 결과')}</span></li>`).join('');
    const candidates = (result.top_candidates || result.candidate_examples || result.candidates || []).slice(0, 5).map((item) => `<article class="candidate"><b>${esc(item.title || item.name || '상품 후보')}</b><span>${esc(item.category_id || item.category || '')} · ${esc(item.candidate_type || '')}</span><small>점수 순위가 아닌 검토 예시입니다. Evidence와 미확정 사항은 fixture 원문에서 확인하세요.</small></article>`).join('');
    $('#demo-content').innerHTML = `<div class="demo-grid"><div><h3>트렌드 평가</h3><ul>${trends || '<li>데이터 없음</li>'}</ul></div><div><h3>상품 후보</h3>${candidates || '<p>적격 후보가 없습니다.</p>'}</div></div><details><summary>응답 원문</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details>`;
  } catch (error) {
    $('#demo-status').textContent = '예시 없음';
    $('#demo-content').textContent = error.message;
  }
}

async function loadImageStatus() {
  try {
    const status = await request('/api/image-generation-status');
    $('#image-status').textContent = status.enabled && status.api_key_present ? `사용 가능 · ${status.model}` : '서버에서 비활성';
  } catch {
    $('#image-status').textContent = '상태 확인 불가';
  }
}

$('#concept-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  values.confirm_image_generation = form.elements.confirm_image_generation.checked;
  values.models = ['gpt-image-2'];
  $('#image-results').innerHTML = '<p class="loading">요청을 처리하고 있습니다.</p>';
  try {
    const result = await request('/api/concept-image', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(values) });
    $('#image-results').innerHTML = (result.results || []).map((item) => item.image_url
      ? `<article class="image-result"><img src="${esc(item.image_url)}" alt="검토용 상품 시안"><div><b>${esc(item.model)}</b><p>${esc(item.status)} · ${esc((item.evidence_ids || []).join(', '))}</p><small>${esc((item.limitations || []).join(' · '))}</small></div></article>`
      : `<p class="error">${esc(item.error_code || result.error || item.status)}</p>`).join('') || `<p class="error">${esc(result.error || '시안 결과가 없습니다.')}</p>`;
  } catch (error) {
    $('#image-results').innerHTML = `<p class="error">생성 실패: ${esc(error.message)}</p>`;
  }
});

loadDemo();
loadImageStatus();
