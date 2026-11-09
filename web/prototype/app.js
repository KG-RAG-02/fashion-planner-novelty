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
  const raw = Object.fromEntries(new FormData(form).entries());
  const values = { request_id: raw.request_id, schema_version: 'internal-prototype-0' };
  try {
    for (const key of ['planning_request', 'trend_result', 'inventory_product_result']) values[key] = JSON.parse(raw[key]);
    values.sales_market_result = raw.sales_market_result.trim() ? JSON.parse(raw.sales_market_result) : null;
    values.generate_image = form.elements.generate_image.checked;
    values.image_model = 'gpt-image-2.5-flare';
    values.generate_planning_board = form.elements.generate_image.checked;
    values.planning_board_model = 'gpt-image-2.5-sunburst';
  } catch (error) {
    $('#draft-results').innerHTML = `<p class="error">JSON 입력을 확인해 주세요: ${esc(error.message)}</p>`;
    return;
  }
  $('#draft-results').innerHTML = '<p class="loading">네 가지 입력과 허가된 기획 참고자료를 검토하고 있습니다.</p>';
  try {
    const result = await request('/api/planning-draft', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(values) });
    const d = result.draft;
    const claim = (item) => item?.value ? `<p><b>${esc(item.kind)}</b> · ${esc(item.value)}${item.evidence_ids?.length ? `<small>Evidence: ${esc(item.evidence_ids.join(', '))}</small>` : ''}</p>` : '<p>미정 · 입력 근거 없음</p>';
    const attrs = (d.attributes || []).map((item) => `<li><b>${esc(item.name)}:</b> ${esc(item.value)} <span>${esc(item.kind)}</span>${item.evidence_ids?.length ? `<small>Evidence: ${esc(item.evidence_ids.join(', '))}</small>` : ''}</li>`).join('');
    const sales = d.sales_market_result ? JSON.stringify(d.sales_market_result, null, 2) : '미제공 (not_provided)';
    const evidenceSections = Object.entries(result.input_evidence || {}).map(([name, item]) => `## ${name} · ${item.status}\nEvidence IDs: ${item.evidence_ids.join(', ') || '없음'}\n\n\`\`\`json\n${JSON.stringify(item.payload, null, 2)}\n\`\`\``).join('\n\n');
    const evidenceHtml = Object.entries(result.input_evidence || {}).map(([name, item]) => `<details class="input-evidence"><summary>${esc(name)} · ${esc(item.status)} · Evidence ${esc(item.evidence_ids.join(', ') || '없음')}</summary><pre>${esc(JSON.stringify(item.payload, null, 2))}</pre></details>`).join('');
    const retrievalResults = result.planning_knowledge?.by_purpose || [];
    const retrievalMarkdown = retrievalResults.map((item) => `### ${item.purpose} · ${item.status}\n${(item.evidence || []).map((ref) => `- ${ref.source_name || ref.source_id}: ${ref.quote || '인용문 없음'} (Evidence: ${ref.evidence_id}; 위치: ${ref.locator || '미제공'})`).join('\n') || '- 인용 가능한 참고자료 없음'}\n${(item.limitations || []).map((value) => `- 제한: ${value}`).join('\n')}`).join('\n\n');
    const retrievalHtml = `<h3>기획 RAG 참고자료</h3>${retrievalResults.map((item) => `<details class="input-evidence"><summary>${esc(item.purpose)} · ${esc(item.status)}</summary><ul>${(item.evidence || []).map((ref) => `<li><b>${esc(ref.source_name || ref.source_id)}</b>: ${esc(ref.quote || '인용문 없음')}<small>Evidence: ${esc(ref.evidence_id)} · 위치: ${esc(ref.locator || '미제공')}</small></li>`).join('') || '<li>인용 가능한 참고자료 없음</li>'}</ul>${(item.limitations || []).map((value) => `<p>${esc(value)}</p>`).join('')}</details>`).join('') || '<p>검색 결과 없음</p>'}`;
    const imageMarkdown = result.image?.image_url
      ? `\n\n## 신제품 예시 · AI 디자인 시뮬레이션\n\n![신제품 콘셉트 예시](${location.origin}${result.image.image_url})\n\nMD 검토용 시안 · 모델: ${result.image.model} · Evidence: ${result.image.evidence_ids.join(', ') || '없음'}\n`
      : `\n\n## 신제품 예시 · AI 디자인 시뮬레이션\n\n${result.image ? `이미지 생성 상태: ${result.image.status} (${result.image.error_code || '추가 정보 없음'})` : '이미지 생성 요청 안 함'}\n`;
    const imageHtml = result.image ? (result.image.image_url
      ? `<section class="new-product-example"><div class="new-product-example-copy"><p class="eyebrow">NEW PRODUCT EXAMPLE</p><h3>신제품 예시 · AI 디자인 시뮬레이션</h3><p>입력된 기획 조건과 Evidence를 반영한 MD 검토용 콘셉트 시안입니다. 확정 사양이나 생산 지시가 아닙니다.</p><small>모델: ${esc(result.image.model)} · Evidence: ${esc(result.image.evidence_ids.join(', ') || '없음')}</small></div><img class="planning-image" src="${esc(result.image.image_url)}" alt="기획 Evidence를 반영한 신제품 콘셉트 예시"></section>`
      : `<section class="new-product-example new-product-example-pending"><div><p class="eyebrow">NEW PRODUCT EXAMPLE</p><h3>신제품 예시 · AI 디자인 시뮬레이션</h3><p>이미지 생성 상태: ${esc(result.image.status)} · ${esc(result.image.error_code || '')}</p></div></section>`) : '';
    const board = result.planning_board;
    const boardMarkdown = board?.image_url
      ? `\n\n## 이미지 기획안 보드 · 별도 모델\n\n![신제품 이미지를 포함한 기획안 보드](${location.origin}${board.image_url})\n\n모델: ${board.model} · Evidence: ${board.evidence_ids?.join(', ') || '없음'}\n`
      : board ? `\n\n## 이미지 기획안 보드 · 별도 모델\n\n상태: ${board.status} (${board.error_code || '추가 정보 없음'})\n` : '';
    const boardHtml = board ? (board.image_url
      ? `<section class="planning-board-example"><div><p class="eyebrow">PLANNING BOARD · SECOND IMAGE MODEL</p><h3>기획안 보드 이미지</h3><p>신제품 예시 이미지를 포함해 입력 내용을 한 장의 검토 보드로 요약했습니다. 텍스트 초안이 근거의 원본입니다.</p><small>모델: ${esc(board.model)} · Evidence: ${esc(board.evidence_ids?.join(', ') || '없음')}</small></div><img src="${esc(board.image_url)}" alt="신제품 이미지를 포함한 AI 생성 기획안 보드"></section>`
      : `<section class="planning-board-example planning-board-pending"><div><p class="eyebrow">PLANNING BOARD · SECOND IMAGE MODEL</p><h3>기획안 보드 이미지</h3><p>상태: ${esc(board.status)} · ${esc(board.error_code || '')}</p></div></section>`) : '';
    const markdown = `# ${d.title}\n\n> 검토 상태: MD 검토 필요 · 입력 상태: ${JSON.stringify(result.input_statuses)}\n\n## 요청 요약\n${d.season || '시즌 미정'} · ${d.category || '카테고리 미정'} · ${d.market?.join(', ') || '시장 미정'} · ${d.channel?.join(', ') || '채널 미정'}\n\n## 기회 및 콘셉트\n${d.opportunity.value}\n\n## 제품 정의\n${d.product_definition.value || '미정'}${imageMarkdown}${boardMarkdown}\n## 제안 속성\n${(d.attributes || []).map(x => `- ${x.name}: ${x.value} (${x.kind}; Evidence: ${x.evidence_ids.join(', ') || '없음'})`).join('\n')}\n\n## 판매·시장 분석 전달값\n\`\`\`json\n${sales}\n\`\`\`\n\n## 자사 상품 관계\n${(d.relation_to_own_products || []).map(x=>`- ${x.value} (Evidence: ${x.evidence_ids.join(', ')})`).join('\n') || '확인 가능한 관계 없음'}\n\n## 기획 RAG 참고자료\n${retrievalMarkdown || '검색 결과 없음'}\n\n## 입력 원문과 전체 Evidence\n\n${evidenceSections}\n\n## 리스크 및 제한사항\n${(result.limitations || []).map(x=>`- ${x}`).join('\n') || '- 추가 제한사항 없음'}\n\n## 확인 질문\n${(result.questions_for_validation || []).map(x=>`- ${x}`).join('\n') || '- 없음'}\n`;
    const sections = `<div class="draft-banner">${esc(result.status)} · MD 검토 필요 · request_id: ${esc(result.request_id)}</div><h3>기획 요청</h3><p>${esc(d.season || '시즌 미정')} · ${esc(d.category || '카테고리 미정')} · ${esc((d.market || []).join(', ') || '시장 미정')} · ${esc((d.channel || []).join(', ') || '채널 미정')}</p><p>제약: ${esc((d.request_constraints || []).join(' · ') || '미입력')}</p><h3>기회 및 콘셉트</h3>${claim(d.opportunity)}<h3>제품 정의</h3>${claim(d.product_definition)}${imageHtml}${boardHtml}<h3>트렌드·제안 속성</h3><ul>${attrs || '<li>사용 가능한 속성 없음</li>'}</ul><h3>자사 상품·재고 관계</h3>${(d.relation_to_own_products || []).map(claim).join('') || '<p>확인 가능한 관계 없음</p>'}<h3>판매·시장성 분석 전달</h3><p>상태: ${esc(result.input_statuses.sales_market_result)}</p><pre>${esc(sales)}</pre>${retrievalHtml}<h3>전체 입력 및 Evidence 추적</h3>${evidenceHtml}<h3>제한사항 및 충돌</h3><ul>${[...(result.limitations || []), ...(result.conflicts || []).map(x=>x.message)].map(x=>`<li>${esc(x)}</li>`).join('') || '<li>추가 제한사항 없음</li>'}</ul><h3>MD 확인 질문</h3><ul>${(result.questions_for_validation || []).map(x=>`<li>${esc(x)}</li>`).join('') || '<li>없음</li>'}</ul><details><summary>구조화 응답 원문</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details><button id="download-draft" class="secondary-button" type="button">Markdown 다운로드</button>`;
    $('#draft-results').innerHTML = `<article class="draft-document">${sections}</article>`;
    $('#download-draft').addEventListener('click', () => {
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${d.title || 'planning-draft'}.md`; link.click(); URL.revokeObjectURL(link.href);
    });
  } catch (error) {
    $('#draft-results').innerHTML = `<p class="error">초안 생성 실패: ${esc(error.message)}</p>`;
  }
});

loadDemo();
loadImageStatus();
