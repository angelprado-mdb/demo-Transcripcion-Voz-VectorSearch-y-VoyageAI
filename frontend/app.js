/* =========================================================
   Voice Demo — Wizard App
   ========================================================= */

const API = 'http://localhost:8000';

const state = {
  selectedDocId: null,
  selectedDoc: null,
  llamadas: [],
  chatHistory: [],
  llmModelos: {},
  searchDone: false,
};

// =========================================================
// INIT
// =========================================================

document.addEventListener('DOMContentLoaded', async () => {
  await checkHealth();
  await loadLlamadas();
  initUpload();
  initLLMConfig();
});

// =========================================================
// NAVEGACION WIZARD
// =========================================================

function goStep(n) {
  document.querySelectorAll('.wiz-step').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('step-' + n);
  if (target) target.classList.add('active');

  // Acciones al llegar a cada paso
  if (n === 2) renderStep2();
  if (n === 5) renderLlamadasTable();
  if (n === 6) renderEmbedSelector();
}

// =========================================================
// HEALTH
// =========================================================

async function checkHealth() {
  try {
    const res = await fetch(`${API}/health`);
    const d = await res.json();
    const dot = document.getElementById('health-dot');
    const lbl = document.getElementById('health-label');
    if (d.status === 'ok') {
      dot.classList.add('ok');
      lbl.textContent = `${d.documentos} docs · ${d.embeddings?.total_embeddings ?? '?'} embeddings`;
    } else {
      dot.classList.add('error');
      lbl.textContent = 'Sin conexion';
    }
  } catch (e) {
    document.getElementById('health-dot').classList.add('error');
    document.getElementById('health-label').textContent = 'Sin conexion';
  }
}

// =========================================================
// CARGAR LLAMADAS
// =========================================================

async function loadLlamadas() {
  try {
    const res = await fetch(`${API}/api/llamadas/?limite=100`);
    const d = await res.json();
    state.llamadas = d.llamadas || [];
    renderExistingList();
  } catch (e) {}
}

function renderExistingList() {
  const container = document.getElementById('existing-list');
  if (!state.llamadas.length) {
    container.innerHTML = '<div class="loading-inline" style="color:var(--dim)">No hay llamadas aun. Sube un archivo JSON.</div>';
    return;
  }
  container.innerHTML = state.llamadas.map(d => {
    const id = d.id_llamada || d._id;
    const res = d.resultado_llamada || 'N/A';
    return `<div class="existing-card" onclick="selectExisting('${d._id}', this)" data-id="${d._id}">
      <div>
        <div class="existing-card-id">${id}</div>
        <div class="existing-card-result">${res}</div>
      </div>
      <span class="existing-card-btn">Seleccionar &rarr;</span>
    </div>`;
  }).join('');
}

function selectExisting(id, el) {
  document.querySelectorAll('.existing-card').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  state.selectedDocId = id;
  const doc = state.llamadas.find(d => d._id === id);
  state.selectedDoc = doc || null;
  setTimeout(() => goStep(2), 300);
}

// =========================================================
// PASO 1: UPLOAD
// =========================================================

function initUpload() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  const confirmBtn = document.getElementById('upload-confirm');
  let parsedData = null;

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => { if (input.files[0]) handleFile(input.files[0]); });

  function handleFile(file) {
    if (!file.name.endsWith('.json')) { toast('Solo se aceptan archivos .json', 'error'); return; }
    const reader = new FileReader();
    reader.onload = e => {
      try {
        parsedData = JSON.parse(e.target.result);
        const count = Array.isArray(parsedData) ? parsedData.length : 1;
        document.getElementById('upload-file-info').innerHTML = `
          <div class="alert alert-info" style="margin-bottom:0.5rem">
            <span>&#128196;</span>
            <span><strong>${file.name}</strong> &mdash; ${count} llamada${count !== 1 ? 's' : ''} detectada${count !== 1 ? 's' : ''}</span>
          </div>`;
        confirmBtn.disabled = false;
      } catch (err) {
        toast('JSON invalido: ' + err.message, 'error');
        parsedData = null; confirmBtn.disabled = true;
      }
    };
    reader.readAsText(file);
  }

  confirmBtn.addEventListener('click', async () => {
    if (!parsedData) return;
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Insertando...';

    try {
      const res = await fetch(`${API}/api/llamadas/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsedData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error al insertar');

      // Seleccionar el primer ID insertado
      state.selectedDocId = data.ids[0];

      document.getElementById('upload-result').innerHTML = `
        <div class="alert alert-success">
          <span>&#10003;</span>
          <div><strong>${data.insertados} llamada${data.insertados !== 1 ? 's' : ''} insertada${data.insertados !== 1 ? 's' : ''}</strong><br>
          <span style="font-family:var(--mono);font-size:0.75rem">${data.ids.join(', ')}</span></div>
        </div>`;

      await checkHealth();
      await loadLlamadas();
      setTimeout(() => goStep(2), 800);
    } catch (err) {
      document.getElementById('upload-result').innerHTML = `<div class="alert alert-error"><span>&#10007;</span>${err.message}</div>`;
      toast(err.message, 'error');
    } finally {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Insertar en MongoDB';
    }
  });
}

// =========================================================
// PASO 2: TRANSCRIPCION + EMBEDDING
// =========================================================

async function renderStep2() {
  if (!state.selectedDocId) { goStep(1); return; }

  // Cargar el documento completo
  try {
    const res = await fetch(`${API}/api/llamadas/${state.selectedDocId}`);
    if (!res.ok) throw new Error('No encontrado');
    const doc = await res.json();
    state.selectedDoc = doc;

    // Badge con el ID
    const badge = document.getElementById('call-id-badge');
    badge.textContent = doc.id_llamada || doc._id;

    // Renderizar transcripcion
    renderTranscripcion(doc.transcripcion || []);

    // Cargar embedding
    loadEmbeddingForStep2(state.selectedDocId);

  } catch (err) {
    document.getElementById('transcripcion-view').innerHTML = `<div class="alert alert-error"><span>&#10007;</span>${err.message}</div>`;
  }
}

function renderTranscripcion(transcripcion) {
  const container = document.getElementById('transcripcion-view');
  if (!transcripcion || !transcripcion.length) {
    container.innerHTML = '<div class="loading-inline" style="color:var(--dim)">Sin transcripcion disponible</div>';
    return;
  }
  container.innerHTML = transcripcion.map(t => {
    const rol = (t.rol || t.hablante || '').toLowerCase();
    const esAgente = rol.includes('agente');
    const tiempo = t.tiempo_marca ? `<span class="turno-tiempo">[${t.tiempo_marca}]</span>` : '';
    return `<div class="turno">
      <span class="turno-hablante ${esAgente ? 'agente' : 'cliente'}">${t.hablante || t.rol || '?'}</span>
      <span class="turno-texto">${tiempo}${escHtml(t.texto || '')}</span>
    </div>`;
  }).join('');
}

async function loadEmbeddingForStep2(docId) {
  const container = document.getElementById('embed-view');
  container.innerHTML = '<div class="loading-inline"><span class="spinner-sm"></span> Recuperando embedding de __mdb_internal_search...</div>';

  // Reintentar hasta 3 veces con espera (el embedding puede tardar segundos en generarse)
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(`${API}/api/llamadas/${docId}/embedding`);
      const emb = await res.json();

      if (res.ok && emb.dimensiones) {
        renderEmbedView(container, emb);
        return;
      }

      if (attempt < 2) {
        container.innerHTML = `<div class="loading-inline"><span class="spinner-sm"></span> Generando embedding... (intento ${attempt + 1}/3)</div>`;
        await sleep(3000);
      }
    } catch (err) {
      if (attempt < 2) await sleep(2000);
    }
  }

  // Fallback: mostrar mensaje educativo aunque no haya embedding aun
  container.innerHTML = `
    <div class="alert alert-info" style="margin-bottom:0.75rem">
      <span>&#9432;</span>
      <div>El embedding se esta generando en segundo plano. Atlas lo procesara en unos segundos. Puedes volver a este paso mas tarde para verlo.</div>
    </div>
    <div class="embed-internal-note">
      <span class="enk">base_de_datos:</span> <span class="env">"__mdb_internal_search"</span><br>
      <span class="enk">campo:</span>         <span class="env">"_autoEmbed.transcripcion_texto"</span><br>
      <span class="enk">modelo:</span>        <span class="env">"voyage-4"</span><br>
      <span class="enk">dimensiones:</span>   <span class="env">1024</span>
    </div>`;
}

function renderEmbedView(container, emb) {
  const heatmap = buildHeatmap(emb.primeros_100 || []);
  const vals = (emb.primeros_10 || []).map(v =>
    `<span class="${v >= 0 ? 'ev-pos' : 'ev-neg'}">${v}</span>`
  ).join(', ');

  container.innerHTML = `
    <div class="embed-dim-tag">&#9698; ${emb.dimensiones} dimensiones &middot; ${emb.tipo} &middot; voyage-4</div>

    <div style="font-size:0.72rem;color:var(--muted);margin-bottom:0.3rem">Primeros 10 valores del vector</div>
    <div class="embed-values-preview">
      [ ${vals} , <span class="ev-dim">... ${emb.dimensiones - 10} valores mas</span> ]
    </div>

    <div style="font-size:0.72rem;color:var(--muted);margin-bottom:0.3rem">Mapa de calor &mdash; primeros 100 valores</div>
    ${heatmap}
    <div class="heatmap-legend"><span style="color:var(--green)">&#9632; positivo</span><span style="color:var(--error)">&#9632; negativo</span></div>

    <div class="embed-internal-note" style="margin-top:0.75rem">
      <span class="enk">base_de_datos:</span> <span class="env">"__mdb_internal_search"</span><br>
      <span class="enk">coleccion:</span>      <span class="env">"${emb.mv_collection.substring(0,32)}..."</span><br>
      <span class="enk">campo:</span>          <span class="env">"_autoEmbed.${emb.campo}"</span><br>
      <span class="enk">tipo:</span>           <span class="env">"${emb.tipo}"</span>
    </div>`;
}

function buildHeatmap(values) {
  if (!values.length) return '';
  const max = Math.max(...values.map(Math.abs)) || 1;
  const cells = values.map(v => {
    const intensity = 0.15 + (Math.abs(v) / max) * 0.85;
    const color = v >= 0
      ? `rgba(0,237,100,${intensity.toFixed(2)})`
      : `rgba(255,107,107,${intensity.toFixed(2)})`;
    return `<div class="hcell" style="background:${color}" title="${v}"></div>`;
  }).join('');
  return `<div class="heatmap">${cells}</div>`;
}

// =========================================================
// PASO 3: BUSQUEDA SEMANTICA
// =========================================================

function setQuery(text) {
  document.getElementById('search-input').value = text;
  document.getElementById('search-input').focus();
}

async function runSearch() {
  const query = document.getElementById('search-input').value.trim();
  if (!query) { toast('Escribe una consulta', 'error'); return; }

  const btn = document.getElementById('search-btn');
  const area = document.getElementById('search-results-area');
  btn.disabled = true;
  btn.textContent = 'Buscando...';
  area.innerHTML = '<div class="loading-inline"><span class="spinner-sm"></span> Ejecutando $vectorSearch...</div>';

  try {
    const res = await fetch(`${API}/api/llamadas/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, k: 5, num_candidates: 70 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Error en busqueda');

    if (!data.resultados.length) {
      area.innerHTML = '<div class="loading-inline" style="color:var(--dim)">Sin resultados para esta consulta. Prueba con otra pregunta.</div>';
    } else {
      // Normalizar scores al rango real de resultados para visualizacion
      // Los scores de dotProduct cuantizado caen todos en un rango estrecho (~0.500-0.510)
      // La normalizacion relativa muestra claramente cual es el mas relevante
      const scores = data.resultados.map(r => r.score || 0);
      const maxScore = Math.max(...scores);
      const minScore = Math.min(...scores);
      const scoreRange = maxScore - minScore;

      area.innerHTML = `
        <div style="font-size:0.8rem;color:var(--muted);margin-bottom:0.6rem">
          ${data.total_encontrados} resultado${data.total_encontrados !== 1 ? 's' : ''} para: <strong>"${escHtml(query)}"</strong>
          <span style="margin-left:0.5rem;font-size:0.72rem;color:var(--dim)">
            (score bruto: ${minScore.toFixed(4)} &ndash; ${maxScore.toFixed(4)})
          </span>
        </div>
        ${data.resultados.map((d, i) => buildResultCard(d, i, minScore, scoreRange)).join('')}`;

      // Mostrar pipeline educativo con syntax highlight de Python
      const pp = document.getElementById('pipeline-panel');
      pp.style.display = 'block';
      document.getElementById('pipeline-code').innerHTML = syntaxHLPython(data.pipeline_ejecutado);

      // Mostrar boton siguiente
      document.getElementById('next-to-4').style.display = 'inline-flex';
      state.searchDone = true;
    }
  } catch (err) {
    area.innerHTML = `<div class="alert alert-error"><span>&#10007;</span>${err.message}</div>`;
    toast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Buscar';
  }
}

function buildResultCard(doc, idx, minScore = 0, scoreRange = 1) {
  const scoreRaw = doc.score || 0;

  // Score normalizado relativo: el mas alto = 100%, el mas bajo del set = 0%
  // Esto muestra la diferencia real de relevancia entre resultados
  const scoreNorm = scoreRange > 0
    ? Math.round(((scoreRaw - minScore) / scoreRange) * 100)
    : (idx === 0 ? 100 : Math.max(0, 100 - idx * 20));

  // Posicion ordinal: el #1 es siempre el mas relevante
  const posLabel = idx === 0 ? '1er resultado' : `#${idx + 1}`;
  const color = idx === 0 ? 'var(--green)' : idx === 1 ? '#2e7d50' : 'var(--muted)';
  const barColor = idx === 0 ? 'var(--green)' : idx <= 2 ? '#5aaa80' : 'var(--dim)';

  const agente = doc.agente?.nombre || doc.agente || 'N/A';
  const cliente = doc.cliente?.nombre || doc.cliente || 'N/A';
  const resultado = doc.resultado_llamada || 'N/A';
  const resClass = resultado.toLowerCase().includes('cerrada') ? 'success'
    : resultado.toLowerCase().includes('perdida') ? 'error' : 'warn';

  const tieneTranscripcion = doc.transcripcion && doc.transcripcion.length;

  return `
  <div class="result-card">
    <div class="result-header">
      <div>
        <div class="result-id">${doc.id_llamada || doc._id}</div>
        <div class="result-chips" style="margin-top:0.4rem">
          <span class="rchip">&#128100; ${agente}</span>
          <span class="rchip">&#128222; ${cliente}</span>
          ${doc.fecha ? `<span class="rchip">&#128197; ${doc.fecha}</span>` : ''}
          ${doc.duracion_segundos ? `<span class="rchip">&#9200; ${doc.duracion_segundos}s</span>` : ''}
          <span class="rchip ${resClass}">${resultado}</span>
        </div>
      </div>
      <div class="result-score-wrap">
        <span class="result-score-val" style="color:${color}">${posLabel}</span>
        <div class="score-bar-wrap">
          <div class="score-bar" style="width:${Math.max(scoreNorm, 8)}%;background:${barColor}"></div>
        </div>
        <span class="score-raw">score: ${scoreRaw.toFixed(5)}</span>
        <span class="score-label">Relevancia relativa</span>
      </div>
    </div>
    ${tieneTranscripcion ? `
    <button class="result-trans-toggle" onclick="toggleTrans(this)">&#9654; Ver transcripcion (${doc.transcripcion.length} turnos)</button>
    <div class="result-trans-body" style="display:none">
      ${doc.transcripcion.map(t => {
        const rol = (t.rol || t.hablante || '').toLowerCase();
        const esAgente = rol.includes('agente');
        const tiempo = t.tiempo_marca ? `<span class="turno-tiempo">[${t.tiempo_marca}]</span>` : '';
        return `<div class="turno">
          <span class="turno-hablante ${esAgente ? 'agente' : 'cliente'}">${t.hablante || '?'}</span>
          <span class="turno-texto">${tiempo}${escHtml(t.texto || '')}</span>
        </div>`;
      }).join('')}
    </div>` : ''}
  </div>`;
}

function toggleTrans(btn) {
  const body = btn.nextElementSibling;
  const vis = body.style.display !== 'none';
  body.style.display = vis ? 'none' : 'block';
  btn.textContent = vis
    ? `\u25B6 Ver transcripcion`
    : `\u25BC Ocultar transcripcion`;
}

function copyCode(id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => toast('Copiado', 'success'));
}

// =========================================================
// PASO 5: LISTA DE LLAMADAS
// =========================================================

function renderLlamadasTable() {
  const container = document.getElementById('llamadas-table');
  if (!state.llamadas.length) {
    container.innerHTML = '<div class="loading-inline" style="color:var(--dim)">No hay llamadas.</div>';
    return;
  }
  container.innerHTML = `<table class="llamadas-table">
    <thead>
      <tr>
        <th>ID Llamada</th>
        <th>Agente</th>
        <th>Cliente</th>
        <th>Fecha</th>
        <th>Duracion</th>
        <th>Resultado</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      ${state.llamadas.map(d => {
        const agente = d.agente?.nombre || d.agente || 'N/A';
        const cliente = d.cliente?.nombre || d.cliente || 'N/A';
        return `<tr>
          <td class="call-id">${d.id_llamada || d._id}</td>
          <td>${agente}</td>
          <td>${cliente}</td>
          <td>${d.fecha || '—'}</td>
          <td>${d.duracion_segundos ? d.duracion_segundos + 's' : '—'}</td>
          <td><span style="font-size:0.75rem">${d.resultado_llamada || '—'}</span></td>
          <td>
            <button class="btn btn-ghost btn-sm" onclick="viewCallEmbed('${d._id}')">Ver embedding</button>
          </td>
        </tr>`;
      }).join('')}
    </tbody>
  </table>`;
}

function viewCallEmbed(id) {
  state.selectedDocId = id;
  goStep(6);
}

// =========================================================
// PASO 6: VER EMBEDDINGS
// =========================================================

function renderEmbedSelector() {
  const sels = ['embed-select', 'embed-compare-select'];
  sels.forEach(selId => {
    const sel = document.getElementById(selId);
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = '<option value="">Selecciona una llamada...</option>' +
      state.llamadas.map(d =>
        `<option value="${d._id}">${d.id_llamada || d._id} — ${d.resultado_llamada || ''}</option>`
      ).join('');
    // Si llegamos desde paso 5 con selectedDocId, preseleccionar
    if (state.selectedDocId) sel.value = state.selectedDocId;
    else if (prev) sel.value = prev;
  });
}

async function loadEmbedding() {
  const id = document.getElementById('embed-select').value;
  if (!id) { toast('Selecciona una llamada', 'error'); return; }

  const split = document.getElementById('embed-split');
  split.style.display = 'none';

  try {
    const [docRes, embRes] = await Promise.all([
      fetch(`${API}/api/llamadas/${id}`),
      fetch(`${API}/api/llamadas/${id}/embedding`),
    ]);
    const doc = await docRes.json();
    const emb = await embRes.json();

    if (!embRes.ok) throw new Error(emb.detail || emb.error || 'Error al obtener embedding');

    // Documento JSON (sin transcripcion_texto para que sea limpio)
    const docShow = { ...doc };
    delete docShow.transcripcion_texto;
    document.getElementById('embed-doc-json').innerHTML = syntaxHL(JSON.stringify(docShow, null, 2));

    // Vector
    const vecContainer = document.getElementById('embed-vector-view');
    renderEmbedView(vecContainer, emb);

    split.style.display = 'block';
    state.selectedDocId = id;

    // Actualizar el selector de comparacion
    const compSel = document.getElementById('embed-compare-select');
    if (compSel) compSel.value = '';

  } catch (err) {
    toast(err.message, 'error');
  }
}

async function calcSimilitud() {
  const id1 = document.getElementById('embed-select').value;
  const id2 = document.getElementById('embed-compare-select').value;
  const container = document.getElementById('similitud-result');

  if (!id1 || !id2) { toast('Selecciona dos llamadas', 'error'); return; }
  if (id1 === id2) { toast('Selecciona llamadas diferentes', 'error'); return; }

  container.innerHTML = '<div class="loading-inline"><span class="spinner-sm"></span> Calculando...</div>';

  try {
    const res = await fetch(`${API}/api/llamadas/similitud`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id1, id2 }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || d.error || 'Error');

    const pct = Math.round(d.similitud_coseno * 100);
    const color = pct >= 70 ? 'var(--green)' : pct >= 50 ? 'var(--warn)' : 'var(--error)';

    container.innerHTML = `
      <div class="similitud-result-box">
        <div style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em">Similitud coseno</div>
        <div class="similitud-score" style="color:${color}">${d.similitud_coseno.toFixed(4)}</div>
        <div class="similitud-interp">${d.interpretacion}</div>
        <div class="similitud-formula">${d.formula}</div>
        <div style="display:flex;gap:1.5rem;justify-content:center;margin-top:0.75rem;font-size:0.75rem;color:var(--muted)">
          <span>Dims: <strong>${d.dimensiones}</strong></span>
          <span>‖A‖: <strong>${d.magnitud_1}</strong></span>
          <span>‖B‖: <strong>${d.magnitud_2}</strong></span>
        </div>
      </div>`;
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error"><span>&#10007;</span>${err.message}</div>`;
  }
}

// =========================================================
// PASO 7: CHAT RAG
// =========================================================

const MODELOS = {
  openai:    [{ id:'gpt-4o', label:'GPT-4o' }, { id:'gpt-4o-mini', label:'GPT-4o Mini (recomendado)' }],
  anthropic: [{ id:'claude-3-5-sonnet-20241022', label:'Claude 3.5 Sonnet' }, { id:'claude-3-5-haiku-20241022', label:'Claude 3.5 Haiku' }],
  gemini:    [
    { id:'gemini-2.0-flash',                  label:'Gemini 2.0 Flash (recomendado)' },
    { id:'gemini-2.5-flash-preview-05-20',    label:'Gemini 2.5 Flash Preview' },
    { id:'gemini-1.5-pro-002',                label:'Gemini 1.5 Pro' },
  ],
  huggingface: [
    { id:'meta-llama/Llama-3.1-8B-Instruct',   label:'Llama 3.1 8B Instruct (recomendado)' },
    { id:'meta-llama/Llama-3.1-70B-Instruct',  label:'Llama 3.1 70B Instruct' },
    { id:'mistralai/Mistral-7B-Instruct-v0.3', label:'Mistral 7B Instruct' },
    { id:'Qwen/Qwen2.5-72B-Instruct',          label:'Qwen 2.5 72B Instruct' },
  ],
};

function initLLMConfig() {
  updateModelos();
  const key = sessionStorage.getItem('llm_api_key');
  if (key) document.getElementById('llm-api-key').value = key;
  document.getElementById('llm-api-key').addEventListener('input', e => {
    sessionStorage.setItem('llm_api_key', e.target.value);
  });
}

function updateModelos() {
  const provider = document.getElementById('llm-provider').value;
  const sel = document.getElementById('llm-model');
  const modelos = MODELOS[provider] || [];
  sel.innerHTML = modelos.map(m => `<option value="${m.id}">${m.label}</option>`).join('');

  // Mostrar/ocultar campo de endpoint y ajustar placeholder de API Key
  const isHF = provider === 'huggingface';
  document.getElementById('hf-endpoint-wrapper').style.display = isHF ? 'block' : 'none';
  document.getElementById('llm-api-key').placeholder = isHF ? 'HF Token (hf_...)' : 'Ingresa tu API Key...';
  document.getElementById('api-key-label').textContent = isHF ? 'HF Token' : 'API Key';
}

function toggleKeyVis() {
  const inp = document.getElementById('llm-api-key');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

function setChatQuery(text) {
  document.getElementById('chat-input').value = text;
  document.getElementById('chat-input').focus();
}

function autoGrow(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function setRagState(step, s) {
  const el = document.getElementById('rs-' + step);
  if (!el) return;
  el.className = 'rag-step-item ' + (s || '');
}

async function sendChat() {
  const pregunta     = document.getElementById('chat-input').value.trim();
  const apiKey       = document.getElementById('llm-api-key').value.trim();
  const provider     = document.getElementById('llm-provider').value;
  const model        = document.getElementById('llm-model').value;
  const k            = parseInt(document.getElementById('chat-k').value) || 5;
  const endpointUrl  = (document.getElementById('hf-endpoint-url')?.value || '').trim();

  if (!pregunta) return;
  if (!apiKey)   { toast('Ingresa una API Key del proveedor LLM', 'error'); return; }

  const messages = document.getElementById('chat-messages');
  // Quitar empty state
  const empty = messages.querySelector('.chat-empty');
  if (empty) empty.remove();

  appendMsg('user', pregunta);
  document.getElementById('chat-input').value = '';
  document.getElementById('chat-input').style.height = 'auto';

  const botId = 'msg-' + Date.now();
  appendMsg('bot', null, botId);

  document.getElementById('chat-send').disabled = true;
  setRagState('retrieve', 'active');
  setRagState('augment', '');
  setRagState('generate', '');

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pregunta, k, llm_provider: provider,
        llm_api_key: apiKey, llm_model: model,
        historial: state.chatHistory.slice(-8),
        llm_endpoint_url: endpointUrl,
      }),
    });

    setRagState('retrieve', 'done');
    setRagState('augment', 'active');

    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'Error en RAG');

    setRagState('augment', 'done');
    setRagState('generate', 'active');

    updateMsg(botId, d.respuesta);
    setRagState('generate', 'done');

    state.chatHistory.push({ role: 'user', content: pregunta });
    state.chatHistory.push({ role: 'assistant', content: d.respuesta });

  } catch (err) {
    updateMsg(botId, `**Error:** ${err.message}`, true);
    setRagState('retrieve', '');
    setRagState('augment', '');
    setRagState('generate', '');
    toast(err.message, 'error');
  } finally {
    document.getElementById('chat-send').disabled = false;
  }
}

function appendMsg(role, content, id) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  if (id) div.id = id;

  const avatar = `<div class="chat-avatar ${role}">${role === 'user' ? '&#128100;' : '&#129302;'}</div>`;
  const bubble = content === null
    ? `<div class="chat-bubble"><div class="loading-dots"><span></span><span></span><span></span></div></div>`
    : `<div class="chat-bubble">${role === 'bot' ? marked.parse(content) : escHtml(content)}</div>`;

  div.innerHTML = role === 'user' ? `${bubble}${avatar}` : `${avatar}${bubble}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function updateMsg(id, content, isError) {
  const el = document.getElementById(id);
  if (!el) return;
  const bubble = el.querySelector('.chat-bubble');
  bubble.innerHTML = isError
    ? `<span style="color:var(--error)">${marked.parse(content)}</span>`
    : marked.parse(content);
  el.closest('.chat-messages').scrollTop = 99999;
}

// =========================================================
// EDU PANELS
// =========================================================

function toggleEdu(header) {
  const body = header.nextElementSibling;
  const toggle = header.querySelector('.edu-toggle');
  const isOpen = body.classList.toggle('open');
  if (toggle) toggle.classList.toggle('open', isOpen);
}

// =========================================================
// UTILS
// =========================================================

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function syntaxHL(json) {
  return escHtml(json).replace(
    /("(\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    match => {
      let cls = 'jn';
      if (/^"/.test(match)) { cls = /:$/.test(match) ? 'jk' : 'js'; }
      else if (/true|false/.test(match)) cls = 'jb';
      else if (/null/.test(match)) cls = 'jd';
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

function syntaxHLPython(code) {
  // Syntax highlight basico para Python: keywords, strings, comments, numbers
  const escaped = escHtml(code);
  return escaped
    // Comentarios (#...)
    .replace(/(#[^\n]*)/g, '<span class="py-comment">$1</span>')
    // Strings con comillas dobles o simples
    .replace(/(&quot;[^&]*?&quot;)/g, '<span class="py-str">$1</span>')
    .replace(/(&#x27;[^&#]*?&#x27;)/g, '<span class="py-str">$1</span>')
    // Keywords Python
    .replace(/\b(from|import|as|def|class|return|for|in|if|else|elif|not|and|or|True|False|None|print|list)\b/g,
      '<span class="py-kw">$1</span>')
    // Numeros
    .replace(/\b(\d+)\b/g, '<span class="py-num">$1</span>')
    // Nombres de funciones comunes del driver
    .replace(/\b(MongoClient|aggregate|find|insert_one|insert_many)\b/g,
      '<span class="py-fn">$1</span>');
}

function toast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${type === 'success' ? '&#10003;' : '&#10007;'}</span><span>${msg}</span>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
