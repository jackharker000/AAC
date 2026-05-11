/* ── AAC Copilot — Main Application JS ──────────────────────────────────────
   Single-file app with no framework dependencies.
   All state is held in `state` object.
   ─────────────────────────────────────────────────────────────────────────── */

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  conversationId: null,
  locationId: null,
  locationName: '',
  selectedPeopleIds: [],
  activePlanId: null,
  ws: null,
  mediaRecorder: null,
  isRecording: false,
  isPaused: false,
  people: [],
  locations: [],
  plans: [],
  currentPersonId: null,
  selectedSpeakerLabel: null,   // for speaker labelling modal
  pendingSpeakerConfirm: null,  // {detected_name, current_label}
  planChips: { topics: [], say: [], ask: [] },
  pendingMemories: [],          // unconfirmed memories after conversation end
  currentMemoryFilter: 'all',
  selectedVoiceId: localStorage.getItem('elevenlabs_voice_id') || '',
  elevenLabsAvailable: false,  // set on startup from /tts/available
};

// ── Initialisation ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Check ElevenLabs availability once on startup
  try {
    const res = await fetch('/tts/available');
    const data = await res.json();
    state.elevenLabsAvailable = data.available;
  } catch (e) {
    state.elevenLabsAvailable = false;
  }
  loadSetupData();
  loadVoices();
  showScreen('setup');
});

// ── Screen navigation ─────────────────────────────────────────────────────────
function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

  const el = document.getElementById(`screen-${name}`);
  if (el) el.classList.add('active');

  const btn = document.querySelector(`.nav-btn[data-screen="${name}"]`);
  if (btn) btn.classList.add('active');

  if (name !== 'setup') {
    document.getElementById('top-nav').style.display = 'flex';
  }

  if (name === 'people') loadPeople();
  if (name === 'memories') loadMemories();
  if (name === 'history') loadHistory();
  if (name === 'plans') loadPlans();
  if (name === 'settings') loadVoices();
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }
  const ct = res.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return res.json();
  return res;
}

// ── Toast notifications ───────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Setup Screen ──────────────────────────────────────────────────────────────
async function loadSetupData() {
  try {
    const [people, locations, plans] = await Promise.all([
      api('GET', '/people'),
      api('GET', '/locations'),
      api('GET', '/plans/today'),
    ]);
    state.people = people;
    state.locations = locations;
    state.plans = plans;
    renderSetupPeople();
    renderSetupLocations();
    renderSetupPlans();
  } catch (e) {
    toast('Could not load setup data: ' + e.message, 'error');
  }
}

function renderSetupPeople() {
  const container = document.getElementById('setup-people-selector');
  container.innerHTML = '';
  state.people.forEach(p => {
    const pill = document.createElement('button');
    pill.className = 'person-pill' + (state.selectedPeopleIds.includes(p.id) ? ' selected' : '');
    pill.innerHTML = `<span class="avatar">${p.name[0].toUpperCase()}</span>${p.name}`;
    pill.onclick = () => toggleSetupPerson(p.id, pill);
    container.appendChild(pill);
  });
}

function toggleSetupPerson(id, el) {
  if (state.selectedPeopleIds.includes(id)) {
    state.selectedPeopleIds = state.selectedPeopleIds.filter(x => x !== id);
    el.classList.remove('selected');
  } else {
    state.selectedPeopleIds.push(id);
    el.classList.add('selected');
  }
}

function renderSetupLocations() {
  const sel = document.getElementById('setup-location-select');
  sel.innerHTML = '<option value="">— choose a location —</option>';
  state.locations.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.id;
    opt.textContent = l.name;
    sel.appendChild(opt);
  });
}

function onLocationSelect() {
  const val = document.getElementById('setup-location-select').value;
  if (val) {
    document.getElementById('setup-location-new').value = '';
    state.locationId = parseInt(val);
    const loc = state.locations.find(l => l.id === state.locationId);
    state.locationName = loc ? loc.name : '';
  }
}

function renderSetupPlans() {
  const container = document.getElementById('setup-plans-list');
  const noMsg = document.getElementById('no-plans-msg');
  container.innerHTML = '';
  if (!state.plans.length) {
    noMsg.style.display = 'block';
    return;
  }
  noMsg.style.display = 'none';
  state.plans.forEach(plan => {
    const div = document.createElement('div');
    div.className = 'plan-option' + (state.activePlanId === plan.id ? ' selected' : '');
    div.innerHTML = `<div class="plan-title">${plan.title}</div>
      <div class="plan-meta">${plan.tone} · ${plan.topics_expected.length} topics · ${plan.things_to_say.length} things to say</div>`;
    div.onclick = () => {
      state.activePlanId = state.activePlanId === plan.id ? null : plan.id;
      document.querySelectorAll('.plan-option').forEach(el => el.classList.remove('selected'));
      if (state.activePlanId === plan.id) div.classList.add('selected');
    };
    container.appendChild(div);
  });
}

async function addPersonFromSetup() {
  const input = document.getElementById('setup-new-person-input');
  const name = input.value.trim();
  if (!name) return;
  try {
    const person = await api('POST', '/people', { name });
    state.people.push(person);
    state.selectedPeopleIds.push(person.id);
    input.value = '';
    renderSetupPeople();
    toast(`${person.name} added`, 'success');
  } catch (e) {
    toast('Could not add person: ' + e.message, 'error');
  }
}

async function startConversation() {
  const btn = document.getElementById('start-conv-btn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  // Resolve location
  let locationId = state.locationId;
  const newLocName = document.getElementById('setup-location-new').value.trim();
  if (!locationId && newLocName) {
    try {
      const loc = await api('POST', '/locations', { name: newLocName });
      state.locations.push(loc);
      locationId = loc.id;
      state.locationName = loc.name;
    } catch (e) { /* ignore */ }
  } else if (locationId) {
    const selected = document.getElementById('setup-location-select').value;
    if (selected) {
      const loc = state.locations.find(l => l.id === parseInt(selected));
      state.locationName = loc ? loc.name : '';
    }
  }

  try {
    const conv = await api('POST', '/conversations', {
      location_id: locationId || null,
      people_present: state.selectedPeopleIds,
    });
    state.conversationId = conv.id;
    state.locationId = locationId;

    // Link plan to conversation
    if (state.activePlanId) {
      await api('PATCH', `/plans/${state.activePlanId}`, { conversation_id: conv.id });
    }

    renderConversationHeader();
    await startRecording();

    document.getElementById('top-nav').style.display = 'flex';
    showScreen('conversation');

    if (state.activePlanId) {
      loadActivePlan(state.activePlanId);
    }
  } catch (e) {
    toast('Could not start conversation: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Start Recording';
  }
}

function renderConversationHeader() {
  const tagsEl = document.getElementById('conv-people-tags');
  tagsEl.innerHTML = '';
  state.selectedPeopleIds.forEach(pid => {
    const p = state.people.find(x => x.id === pid);
    if (!p) return;
    const tag = document.createElement('div');
    tag.className = 'conv-person-tag';
    tag.innerHTML = `<span class="avatar" style="width:18px;height:18px;font-size:0.6rem;border-radius:50%;background:var(--accent);color:white;display:inline-flex;align-items:center;justify-content:center;font-weight:700;">${p.name[0]}</span>${p.name}`;
    tagsEl.appendChild(tag);
  });
  document.getElementById('conv-location-name').textContent = state.locationName || '—';
}

async function loadActivePlan(planId) {
  try {
    const plan = await api('GET', `/plans/${planId}`);
    const panel = document.getElementById('plan-panel');
    panel.style.display = '';
    document.getElementById('plan-panel-title').textContent = plan.title;

    const list = document.getElementById('plan-checklist');
    list.innerHTML = '';
    const items = [
      ...plan.things_to_say.map(t => ({ text: t, type: 'say' })),
      ...plan.questions_to_ask.map(q => ({ text: q, type: 'ask' })),
    ];
    items.forEach((item, i) => {
      const li = document.createElement('li');
      li.id = `plan-item-${i}`;
      li.innerHTML = `<span class="check-icon"></span><span>${item.text}</span>`;
      li.onclick = () => li.classList.toggle('done');
      list.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}

function togglePlanPanel() {
  const panel = document.getElementById('plan-panel');
  panel.classList.toggle('open');
  document.getElementById('plan-panel-toggle').textContent =
    panel.classList.contains('open') ? '▾' : '▸';
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWebSocket() {
  if (!state.conversationId) return;
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${location.host}/ws/${state.conversationId}`);

  ws.onopen = () => { state.ws = ws; };

  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'transcript') handleTranscriptMsg(msg);
    else if (msg.type === 'prompts') handlePromptsMsg(msg);
    else if (msg.type === 'confirm_speaker') handleSpeakerConfirm(msg);
    else if (msg.type === 'error') toast(msg.message, 'error');
  };

  ws.onerror = () => toast('Connection error — retrying…', 'error');

  ws.onclose = () => {
    state.ws = null;
    if (state.isRecording && !state.isPaused) {
      // Auto-reconnect after 2s
      setTimeout(connectWebSocket, 2000);
    }
  };
}

// ── Audio recording (Web Audio API → WAV — works on all browsers including Safari) ──
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    connectWebSocket();
    state.isRecording = true;
    state.isPaused = false;
    updateRecIndicator();

    const chunkSeconds = parseInt(document.getElementById('chunk-size-select')?.value) || 3;
    const sampleRate = 16000;

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const audioCtx = new AudioCtx({ sampleRate });
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    let pcmSamples = [];
    const samplesPerChunk = sampleRate * chunkSeconds;

    processor.onaudioprocess = (e) => {
      if (state.isPaused) return;
      const input = e.inputBuffer.getChannelData(0);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcmSamples.push(s < 0 ? s * 0x8000 : s * 0x7FFF);
      }
      if (pcmSamples.length >= samplesPerChunk) {
        const chunk = pcmSamples.splice(0, samplesPerChunk);
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          const wav = _encodeWAV(chunk, sampleRate);
          const b64 = _arrayBufferToBase64(wav);
          state.ws.send(JSON.stringify({ action: 'audio_chunk', mime_type: 'audio/wav', data: b64 }));
        }
      }
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);

    // Expose a stop/pause/resume shim so the rest of the code works unchanged
    state.mediaRecorder = {
      stop() {
        processor.disconnect();
        source.disconnect();
        audioCtx.close();
        stream.getTracks().forEach(t => t.stop());
      },
      pause()  { state.isPaused = true; },
      resume() { state.isPaused = false; },
    };
  } catch (e) {
    toast('Microphone access denied or unavailable: ' + e.message, 'error');
    throw e;
  }
}

function _encodeWAV(samples, sampleRate) {
  const dataBytes = samples.length * 2;
  const buf = new ArrayBuffer(44 + dataBytes);
  const v = new DataView(buf);
  const ws = (off, s) => { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); };
  ws(0,  'RIFF'); v.setUint32(4,  36 + dataBytes, true);
  ws(8,  'WAVE'); ws(12, 'fmt '); v.setUint32(16, 16, true);
  v.setUint16(20, 1,          true); // PCM
  v.setUint16(22, 1,          true); // mono
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true); // byte rate
  v.setUint16(32, 2,          true); // block align
  v.setUint16(34, 16,         true); // bits per sample
  ws(36, 'data'); v.setUint32(40, dataBytes, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) { v.setInt16(off, samples[i], true); off += 2; }
  return buf;
}

function _arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let bin = '';
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function toggleRecording() {
  const btn = document.getElementById('pause-btn');
  if (state.isPaused) {
    state.mediaRecorder?.resume();
    state.isPaused = false;
    btn.textContent = '⏸ Pause';
    btn.classList.remove('paused');
    toast('Recording resumed');
  } else {
    state.mediaRecorder?.pause();
    state.isPaused = true;
    btn.textContent = '▶ Resume';
    btn.classList.add('paused');
    toast('Recording paused');
  }
  updateRecIndicator();
}

function updateRecIndicator() {
  const el = document.getElementById('rec-indicator');
  const label = document.getElementById('rec-label');
  if (state.isPaused) {
    el.classList.add('paused');
    label.textContent = 'Paused';
  } else {
    el.classList.remove('paused');
    label.textContent = 'Recording';
  }
}

// ── Transcript ────────────────────────────────────────────────────────────────
function handleTranscriptMsg(msg) {
  const scroll = document.getElementById('transcript-scroll');
  const seg = document.createElement('div');
  seg.className = 'transcript-seg';
  seg.id = `seg-${msg.id}`;
  const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  seg.innerHTML = `
    <div class="seg-meta">
      <span class="seg-speaker" onclick="openSpeakerLabelModal('${escHtml(msg.speaker)}')">${escHtml(msg.speaker)}</span>
      <span class="seg-time">${time}</span>
      <button class="speaker-label-btn" onclick="openSpeakerLabelModal('${escHtml(msg.speaker)}')">Label</button>
    </div>
    <div class="seg-text">${escHtml(msg.text)}</div>`;
  scroll.appendChild(seg);
  scroll.scrollTop = scroll.scrollHeight;

  // Detect if someone said their name ("I'm Sarah", "It's Jane", "My name is...")
  detectNameInTranscript(msg.text, msg.speaker);
}

function appendJamesOutput(text) {
  const scroll = document.getElementById('transcript-scroll');
  const seg = document.createElement('div');
  seg.className = 'james-output-seg transcript-seg';
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  seg.innerHTML = `
    <div class="seg-meta">
      <span class="seg-speaker" style="color:var(--accent);">James</span>
      <span class="seg-time">${time}</span>
    </div>
    <div class="seg-text">${escHtml(text)}</div>`;
  scroll.appendChild(seg);
  scroll.scrollTop = scroll.scrollHeight;
}

function detectNameInTranscript(text, speaker) {
  if (speaker.toLowerCase() === 'james') return;
  const patterns = [
    /(?:i['']m|i am|my name(?:'?s| is))\s+([A-Z][a-z]+)/,
    /(?:it['']s|this is)\s+([A-Z][a-z]+)/,
    /(?:hi|hello),?\s+james[.,]?\s+(?:i['']m|it['']s|this is)\s+([A-Z][a-z]+)/i,
  ];
  for (const pat of patterns) {
    const m = text.match(pat);
    if (m) {
      const detected = m[1];
      // Check if we already know this person
      const existing = state.people.find(p => p.name.toLowerCase() === detected.toLowerCase());
      if (existing) {
        showSpeakerConfirmBanner(`Is this ${detected}?`, speaker, existing.id, detected);
      } else if (state.selectedPeopleIds.length === 0 || !state.people.some(p => state.selectedPeopleIds.includes(p.id))) {
        showSpeakerConfirmBanner(`Did someone say their name is ${detected}?`, speaker, null, detected);
      }
      break;
    }
  }
}

function showSpeakerConfirmBanner(msg, currentLabel, personId, detectedName) {
  state.pendingSpeakerConfirm = { currentLabel, personId, detectedName };
  document.getElementById('speaker-confirm-msg').textContent = msg;
  document.getElementById('speaker-confirm-banner').classList.add('visible');
}

async function confirmSpeaker(yes) {
  document.getElementById('speaker-confirm-banner').classList.remove('visible');
  if (!yes || !state.pendingSpeakerConfirm) return;
  const { currentLabel, personId, detectedName } = state.pendingSpeakerConfirm;
  try {
    if (personId) {
      await api('POST', `/conversations/${state.conversationId}/confirm-speaker`, {
        current_label: currentLabel,
        person_id: personId,
      });
    } else {
      await api('POST', `/conversations/${state.conversationId}/label-speaker`, {
        speaker_label: currentLabel,
        create_person: true,
        new_person_name: detectedName,
      });
    }
    toast(`Speaker labelled as ${detectedName}`, 'success');
    state.pendingSpeakerConfirm = null;
  } catch (e) {
    toast('Could not label speaker: ' + e.message, 'error');
  }
}

function handleSpeakerConfirm(msg) {
  showSpeakerConfirmBanner(
    `Did someone say their name is ${msg.detected_name}?`,
    msg.current_label,
    null,
    msg.detected_name
  );
}

// ── Prompts ───────────────────────────────────────────────────────────────────
function handlePromptsMsg(msg) {
  renderPrompts(msg.suggestions);
}

function renderPrompts(suggestions) {
  const scroll = document.getElementById('prompts-scroll');
  const noMsg = document.getElementById('no-prompts-msg');
  const loading = document.getElementById('prompts-loading');
  loading.classList.remove('visible');

  if (!suggestions || !suggestions.length) {
    scroll.innerHTML = '';
    scroll.appendChild(noMsg);
    noMsg.style.display = 'flex';
    return;
  }
  noMsg.style.display = 'none';

  scroll.innerHTML = '';
  suggestions.forEach((s, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'prompt-btn-wrap';

    const catClass = `cat-${s.category.replace(/[^a-z-]/g, '')}`;
    const catLabel = s.category.replace(/-/g, ' ');

    wrap.innerHTML = `
      <button class="prompt-btn" onclick="speakPrompt(${i}, '${escAttr(s.text)}', '${escAttr(s.category)}')" id="prompt-btn-${i}">
        <span class="cat-badge ${catClass}">${catLabel}</span><br>
        ${escHtml(s.text)}
      </button>
      <div class="prompt-actions">
        <button class="rating-btn" id="rate-up-${i}" onclick="ratePrompt(${i}, 1, '${escAttr(s.text)}', '${escAttr(s.category)}')">👍</button>
        <button class="rating-btn" id="rate-down-${i}" onclick="ratePrompt(${i}, -1, '${escAttr(s.text)}', '${escAttr(s.category)}')">👎</button>
        <button class="more-like-btn" onclick="morePromptLike('${escAttr(s.category)}')">More like this</button>
      </div>`;
    scroll.appendChild(wrap);
  });
}

async function speakPrompt(idx, text, category) {
  const btn = document.getElementById(`prompt-btn-${idx}`);
  if (btn) btn.classList.add('speaking');

  await speakText(text);

  if (btn) btn.classList.remove('speaking');
  appendJamesOutput(text);

  // Save output
  if (state.conversationId) {
    try {
      await api('POST', `/conversations/${state.conversationId}/outputs`, {
        suggested_prompt: text,
        final_spoken_text: text,
        was_spoken: true,
        was_edited: false,
        category,
      });
    } catch (e) { /* silent */ }
  }

  // Clear the text input if it had the same text
  const inputEl = document.getElementById('text-input');
  if (inputEl.value.trim() === text) inputEl.value = '';
}

async function speakTextInput() {
  const inputEl = document.getElementById('text-input');
  const text = inputEl.value.trim();
  if (!text) return;
  await speakText(text);
  appendJamesOutput(text);
  if (state.conversationId) {
    try {
      await api('POST', `/conversations/${state.conversationId}/outputs`, {
        typed_input: text,
        final_spoken_text: text,
        was_spoken: true,
        was_edited: true,
        category: 'typed',
      });
    } catch (e) { /* silent */ }
  }
  inputEl.value = '';
  autoResize(inputEl);
}

async function speakText(text) {
  // Skip ElevenLabs entirely if not configured — go straight to browser TTS
  if (!state.elevenLabsAvailable) {
    browserSpeak(text);
    return;
  }

  const audioEl = document.getElementById('tts-audio');
  const voiceId = state.selectedVoiceId;

  try {
    const res = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: voiceId || undefined }),
    });
    if (!res.ok) throw new Error('TTS failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    audioEl.src = url;
    await audioEl.play();
    audioEl.onended = () => URL.revokeObjectURL(url);
  } catch (e) {
    browserSpeak(text);
  }
}

function browserSpeak(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 0.95;
  window.speechSynthesis.speak(utt);
}

async function refreshPrompts() {
  if (!state.conversationId) return;
  document.getElementById('prompts-loading').classList.add('visible');
  try {
    const planParam = state.activePlanId ? `?plan_id=${state.activePlanId}` : '';
    const suggestions = await api('GET', `/conversations/${state.conversationId}/prompts${planParam}`);
    renderPrompts(suggestions);
  } catch (e) {
    document.getElementById('prompts-loading').classList.remove('visible');
    toast('Could not refresh prompts: ' + e.message, 'error');
  }
}

function askNamePrompt() {
  speakPrompt(-1, "I don't think I know your name. Could you please tell me your name?", 'social');
}

async function ratePrompt(idx, rating, text, category) {
  const upBtn = document.getElementById(`rate-up-${idx}`);
  const downBtn = document.getElementById(`rate-down-${idx}`);
  if (upBtn) upBtn.classList.toggle('rated-up', rating === 1);
  if (downBtn) downBtn.classList.toggle('rated-down', rating === -1);

  if (state.conversationId) {
    try {
      const output = await api('POST', `/conversations/${state.conversationId}/outputs`, {
        suggested_prompt: text,
        final_spoken_text: text,
        was_spoken: false,
        was_edited: false,
        category,
        rating,
      });
      // Update rating immediately
      await api('PATCH', `/conversations/${state.conversationId}/outputs/${output.id}/rating`, { rating });
    } catch (e) { /* silent */ }
  }
}

function morePromptLike(category) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    refreshPrompts();
    return;
  }
  state.ws.send(JSON.stringify({ action: 'refresh_prompts', bias_category: category }));
  document.getElementById('prompts-loading').classList.add('visible');
}

// ── End conversation ──────────────────────────────────────────────────────────
async function endConversation() {
  if (!state.conversationId) return;
  if (!confirm('End this conversation? Memories will be extracted automatically.')) return;

  state.mediaRecorder?.stop();
  state.isRecording = false;
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }

  try {
    await api('POST', `/conversations/${state.conversationId}/end`);
    toast('Conversation ended. Extracting memories…');
    // Poll for summary
    await showSummaryModal();
  } catch (e) {
    toast('Error ending conversation: ' + e.message, 'error');
  }
}

async function showSummaryModal() {
  const convId = state.conversationId;
  // Wait a moment for memory extraction to run
  await sleep(3000);
  try {
    const conv = await api('GET', `/conversations/${convId}`);
    document.getElementById('summary-text').value = conv.summary || '';

    const memories = await api('GET', `/memories?conversation_id=${convId}&confirmed=false`);
    state.pendingMemories = memories;
    renderMemoryReviewList(memories);

    document.getElementById('modal-summary').classList.add('open');
  } catch (e) {
    toast('Could not load summary: ' + e.message, 'error');
  }
}

function renderMemoryReviewList(memories) {
  const list = document.getElementById('memory-review-list');
  if (!memories.length) {
    list.innerHTML = '<p style="color:var(--text-muted);font-size:0.88rem;">No new memories were extracted from this conversation.</p>';
    return;
  }
  list.innerHTML = '<h3 style="font-size:0.85rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim);margin-bottom:10px;">Review Memories</h3>';
  memories.forEach(mem => {
    const card = document.createElement('div');
    card.className = 'memory-card';
    card.id = `review-mem-${mem.id}`;
    const importanceStars = [1,2,3,4,5].map(n =>
      `<span class="imp-star ${n <= mem.importance ? 'lit' : ''}" onclick="setMemImportance(${mem.id}, ${n})">★</span>`
    ).join('');
    card.innerHTML = `
      <div class="mem-text">
        <div>${escHtml(mem.memory_text)}</div>
        <div class="mem-type">${mem.memory_type.replace(/_/g,' ')}</div>
        <div class="mem-importance">${importanceStars}</div>
      </div>
      <div class="mem-actions">
        <button class="mem-btn confirm" onclick="confirmReviewMemory(${mem.id})">Keep</button>
        <button class="mem-btn discard" onclick="discardReviewMemory(${mem.id})">Discard</button>
      </div>`;
    list.appendChild(card);
  });
}

async function confirmReviewMemory(id) {
  try {
    await api('POST', `/memories/${id}/confirm`);
    const card = document.getElementById(`review-mem-${id}`);
    if (card) {
      card.style.opacity = '0.4';
      card.querySelector('.mem-actions').innerHTML = '<span style="color:var(--green);font-size:0.8rem;">Saved ✓</span>';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function discardReviewMemory(id) {
  try {
    await api('DELETE', `/memories/${id}`);
    const card = document.getElementById(`review-mem-${id}`);
    if (card) card.remove();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function setMemImportance(id, importance) {
  try {
    await api('PATCH', `/memories/${id}`, { importance });
    // Update stars UI
    const card = document.getElementById(`review-mem-${id}`);
    if (card) {
      card.querySelectorAll('.imp-star').forEach((star, i) => {
        star.classList.toggle('lit', i < importance);
      });
    }
  } catch (e) { /* silent */ }
}

async function closeSummaryModal() {
  // Save edited summary
  const summaryText = document.getElementById('summary-text').value.trim();
  if (summaryText && state.conversationId) {
    try {
      await api('PATCH', `/conversations/${state.conversationId}`, { summary: summaryText });
    } catch (e) { /* silent */ }
  }
  document.getElementById('modal-summary').classList.remove('open');
  // Return to setup for next conversation
  state.conversationId = null;
  state.locationId = null;
  state.selectedPeopleIds = [];
  state.activePlanId = null;
  await loadSetupData();
  showScreen('setup');
  document.getElementById('top-nav').style.display = 'none';
}

// ── Speaker label modal ───────────────────────────────────────────────────────
function openSpeakerLabelModal(currentLabel) {
  state.selectedSpeakerLabel = currentLabel;
  document.getElementById('label-speaker-name').textContent = `"${currentLabel}"`;
  document.getElementById('label-new-name').value = '';

  const container = document.getElementById('label-existing-people');
  container.innerHTML = '';
  state.people.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'person-pill';
    btn.style.marginBottom = '6px';
    btn.innerHTML = `<span class="avatar">${p.name[0]}</span>${p.name}`;
    btn.onclick = () => {
      // Quick-confirm this person
      saveSpeakerLabelAs(p.id, p.name);
    };
    container.appendChild(btn);
  });

  document.getElementById('modal-speaker-label').classList.add('open');
}

async function saveSpeakerLabel() {
  const newName = document.getElementById('label-new-name').value.trim();
  if (!newName) return;
  await saveSpeakerLabelAs(null, newName, true);
}

async function saveSpeakerLabelAs(personId, name, createNew = false) {
  closeModal('modal-speaker-label');
  if (!state.conversationId) return;
  try {
    await api('POST', `/conversations/${state.conversationId}/label-speaker`, {
      speaker_label: state.selectedSpeakerLabel,
      person_id: personId || undefined,
      create_person: createNew,
      new_person_name: createNew ? name : undefined,
    });
    // Update all matching speaker spans in UI
    document.querySelectorAll('.seg-speaker').forEach(el => {
      if (el.textContent === state.selectedSpeakerLabel) {
        el.textContent = name;
        el.setAttribute('onclick', `openSpeakerLabelModal('${escAttr(name)}')`);
      }
    });
    toast(`Speaker labelled as ${name}`, 'success');

    if (!state.people.find(p => p.name === name)) {
      const updated = await api('GET', '/people');
      state.people = updated;
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── Save note modal ───────────────────────────────────────────────────────────
function openSaveNoteModal() {
  const sel = document.getElementById('note-person-select');
  sel.innerHTML = '<option value="">— nobody specific —</option>';
  state.people.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    sel.appendChild(opt);
  });
  document.getElementById('note-text-input').value = '';
  document.getElementById('modal-save-note').classList.add('open');
}

async function saveNote() {
  const text = document.getElementById('note-text-input').value.trim();
  if (!text) return;
  const personId = document.getElementById('note-person-select').value;
  try {
    await api('POST', '/memories', {
      memory_text: text,
      person_id: personId ? parseInt(personId) : null,
      conversation_id: state.conversationId,
      confirmed: true,
      memory_type: 'personal_fact',
    });
    toast('Note saved', 'success');
    closeModal('modal-save-note');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── People Screen ─────────────────────────────────────────────────────────────
async function loadPeople() {
  try {
    const people = await api('GET', '/people');
    state.people = people;
    renderPeopleGrid(people);
  } catch (e) {
    toast('Could not load people', 'error');
  }
}

function renderPeopleGrid(people) {
  const grid = document.getElementById('people-grid');
  if (!people.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><div class="empty-icon">👥</div><p>No people saved yet. Add someone to get started.</p></div>`;
    return;
  }
  grid.innerHTML = '';
  people.forEach(p => {
    const card = document.createElement('div');
    card.className = 'person-card';
    card.onclick = () => openPersonDetail(p.id);
    const lastSeen = p.last_seen_date
      ? `Last seen: ${new Date(p.last_seen_date).toLocaleDateString()}`
      : 'Never seen yet';
    card.innerHTML = `
      <div class="person-card-header">
        <div class="person-avatar">${p.name[0].toUpperCase()}</div>
        <div>
          <div class="person-card-name">${escHtml(p.name)}</div>
          <div class="person-card-rel">${escHtml(p.relation || '—')}</div>
        </div>
      </div>
      <div class="person-card-meta">${lastSeen}</div>
      ${p.notes ? `<div class="person-card-meta" style="margin-top:4px;">${escHtml(p.notes.slice(0, 80))}${p.notes.length > 80 ? '…' : ''}</div>` : ''}`;
    grid.appendChild(card);
  });
}

function filterPeople(query) {
  const q = query.toLowerCase();
  const filtered = state.people.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.relation || '').toLowerCase().includes(q) ||
    (p.notes || '').toLowerCase().includes(q)
  );
  renderPeopleGrid(filtered);
}

async function openPersonDetail(id) {
  state.currentPersonId = id;
  const person = state.people.find(p => p.id === id);
  if (!person) return;

  document.getElementById('detail-avatar').textContent = person.name[0].toUpperCase();
  document.getElementById('detail-name').textContent = person.name;
  document.getElementById('detail-rel').textContent = person.relation || '—';
  document.getElementById('detail-notes').textContent = person.notes || 'No notes yet.';

  document.getElementById('person-detail').classList.add('open');

  // Load memories and conversations
  const [memories, conversations] = await Promise.all([
    api('GET', `/people/${id}/memories`),
    api('GET', `/people/${id}/conversations`),
  ]);

  const memEl = document.getElementById('detail-memories');
  memEl.innerHTML = '';
  if (!memories.length) {
    memEl.innerHTML = '<p style="font-size:0.82rem;color:var(--text-dim);">No memories yet.</p>';
  } else {
    memories.slice(0, 8).forEach(m => {
      const div = document.createElement('div');
      div.style.cssText = 'padding:8px 0;border-bottom:1px solid var(--border);font-size:0.85rem;';
      div.innerHTML = `<span style="color:var(--amber);">★</span> ${escHtml(m.memory_text)} <span style="color:var(--text-dim);font-size:0.72rem;">(${m.memory_type.replace(/_/g,' ')})</span>`;
      memEl.appendChild(div);
    });
  }

  const convEl = document.getElementById('detail-conversations');
  convEl.innerHTML = '';
  if (!conversations.length) {
    convEl.innerHTML = '<p style="font-size:0.82rem;color:var(--text-dim);">No conversations recorded yet.</p>';
  } else {
    conversations.slice(0, 5).forEach(c => {
      const div = document.createElement('div');
      div.style.cssText = 'padding:6px 0;border-bottom:1px solid var(--border);font-size:0.82rem;color:var(--text-muted);cursor:pointer;';
      div.textContent = new Date(c.start_time).toLocaleDateString('en-AU', { day:'numeric', month:'short', year:'numeric' });
      div.onclick = () => { closePersonDetail(); showScreen('history'); };
      convEl.appendChild(div);
    });
  }
}

function closePersonDetail() {
  document.getElementById('person-detail').classList.remove('open');
  state.currentPersonId = null;
}

function editCurrentPerson() {
  const person = state.people.find(p => p.id === state.currentPersonId);
  if (!person) return;
  openPersonModal(person);
  closePersonDetail();
}

async function deleteCurrentPerson() {
  if (!confirm('Delete this person? Their memories will also be deleted.')) return;
  try {
    await api('DELETE', `/people/${state.currentPersonId}?cascade_memories=true`);
    state.people = state.people.filter(p => p.id !== state.currentPersonId);
    closePersonDetail();
    renderPeopleGrid(state.people);
    toast('Person deleted');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function openPersonModal(person = null) {
  document.getElementById('person-modal-title').textContent = person ? 'Edit Person' : 'Add Person';
  document.getElementById('person-modal-id').value = person ? person.id : '';
  document.getElementById('person-name-input').value = person ? person.name : '';
  document.getElementById('person-rel-input').value = person ? person.relation : '';
  document.getElementById('person-notes-input').value = person ? person.notes : '';
  document.getElementById('modal-person').classList.add('open');
}

async function savePerson() {
  const id = document.getElementById('person-modal-id').value;
  const data = {
    name: document.getElementById('person-name-input').value.trim(),
    relation: document.getElementById('person-rel-input').value.trim(),
    notes: document.getElementById('person-notes-input').value.trim(),
  };
  if (!data.name) return;
  try {
    if (id) {
      const updated = await api('PATCH', `/people/${id}`, data);
      const idx = state.people.findIndex(p => p.id === parseInt(id));
      if (idx !== -1) state.people[idx] = updated;
    } else {
      const created = await api('POST', '/people', data);
      state.people.push(created);
    }
    closeModal('modal-person');
    renderPeopleGrid(state.people);
    toast('Saved', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── Memories Screen ───────────────────────────────────────────────────────────
async function loadMemories() {
  try {
    const memories = await api('GET', '/memories?limit=200');
    renderMemories(memories);
  } catch (e) {
    toast('Could not load memories', 'error');
  }
}

function setMemoryFilter(filter, btn) {
  state.currentMemoryFilter = filter;
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  loadMemoriesFiltered();
}

async function loadMemoriesFiltered() {
  try {
    let url = '/memories?limit=200';
    if (state.currentMemoryFilter === 'unreviewed') url += '&confirmed=false';
    else if (state.currentMemoryFilter !== 'all') url += `&memory_type=${state.currentMemoryFilter}`;
    const memories = await api('GET', url);
    renderMemories(memories);
  } catch (e) { toast('Error loading memories', 'error'); }
}

function filterMemories(query) {
  const q = query.toLowerCase();
  const cards = document.querySelectorAll('#memories-content .memory-card');
  cards.forEach(card => {
    const text = card.querySelector('.mem-text')?.textContent?.toLowerCase() || '';
    card.style.display = text.includes(q) ? '' : 'none';
  });
}

function renderMemories(memories) {
  const content = document.getElementById('memories-content');
  if (!memories.length) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">💭</div><p>No memories found. They are extracted automatically after conversations end.</p></div>`;
    return;
  }
  content.innerHTML = '';

  // Group by person
  const byPerson = {};
  const noPerson = [];
  memories.forEach(m => {
    if (m.person_id) {
      (byPerson[m.person_id] = byPerson[m.person_id] || []).push(m);
    } else {
      noPerson.push(m);
    }
  });

  const renderGroup = (label, mems) => {
    const title = document.createElement('div');
    title.className = 'memories-section-title';
    title.textContent = label;
    content.appendChild(title);
    mems.forEach(m => content.appendChild(buildMemoryCard(m)));
  };

  Object.entries(byPerson).forEach(([pid, mems]) => {
    const person = state.people.find(p => p.id === parseInt(pid));
    renderGroup(person ? person.name : `Person #${pid}`, mems);
  });
  if (noPerson.length) renderGroup('General', noPerson);
}

function buildMemoryCard(m) {
  const card = document.createElement('div');
  card.className = 'memory-card';
  card.id = `mem-card-${m.id}`;
  const importanceStars = [1,2,3,4,5].map(n =>
    `<span class="imp-star ${n <= m.importance ? 'lit' : ''}" onclick="setMemImportance(${m.id},${n})">★</span>`
  ).join('');
  card.innerHTML = `
    <div class="mem-text">
      <div contenteditable="true" id="mem-edit-${m.id}" onblur="saveMemoryEdit(${m.id}, this)">${escHtml(m.memory_text)}</div>
      <div class="mem-type">${m.memory_type.replace(/_/g,' ')}${!m.confirmed ? ' · <span style="color:var(--amber);">unreviewed</span>' : ''}</div>
      <div class="mem-importance">${importanceStars}</div>
    </div>
    <div class="mem-actions">
      ${!m.confirmed ? `<button class="mem-btn confirm" onclick="confirmMemCard(${m.id})">Confirm</button>` : ''}
      <button class="mem-btn discard" onclick="deleteMemCard(${m.id})">Delete</button>
    </div>`;
  return card;
}

async function saveMemoryEdit(id, el) {
  const text = el.textContent.trim();
  if (!text) return;
  try {
    await api('PATCH', `/memories/${id}`, { memory_text: text });
  } catch (e) { /* silent */ }
}

async function confirmMemCard(id) {
  try {
    await api('POST', `/memories/${id}/confirm`);
    const card = document.getElementById(`mem-card-${id}`);
    if (card) {
      const typeEl = card.querySelector('.mem-type');
      if (typeEl) typeEl.innerHTML = typeEl.innerHTML.replace(/·\s*<span[^>]*>unreviewed<\/span>/, '');
      const confirmBtn = card.querySelector('.mem-btn.confirm');
      if (confirmBtn) confirmBtn.remove();
    }
    toast('Memory confirmed', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function deleteMemCard(id) {
  try {
    await api('DELETE', `/memories/${id}`);
    document.getElementById(`mem-card-${id}`)?.remove();
    toast('Memory deleted');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function openAddMemoryModal() {
  const sel = document.getElementById('mem-person-select');
  sel.innerHTML = '<option value="">— nobody specific —</option>';
  state.people.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    sel.appendChild(opt);
  });
  document.getElementById('mem-text-input').value = '';
  document.getElementById('modal-add-memory').classList.add('open');
}

async function saveNewMemory() {
  const text = document.getElementById('mem-text-input').value.trim();
  if (!text) return;
  const personId = document.getElementById('mem-person-select').value;
  const type = document.getElementById('mem-type-select').value;
  try {
    await api('POST', '/memories', {
      memory_text: text,
      person_id: personId ? parseInt(personId) : null,
      memory_type: type,
      confirmed: true,
    });
    closeModal('modal-add-memory');
    loadMemories();
    toast('Memory saved', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── History Screen ────────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const conversations = await api('GET', '/conversations?limit=50');
    renderHistory(conversations);
  } catch (e) {
    toast('Could not load history', 'error');
  }
}

async function searchHistory(query) {
  try {
    const conversations = await api('GET', `/conversations?search=${encodeURIComponent(query)}&limit=50`);
    renderHistory(conversations);
  } catch (e) { /* silent */ }
}

function renderHistory(convs) {
  const list = document.getElementById('history-list');
  if (!convs.length) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><p>No conversations recorded yet. Start one from the setup screen.</p></div>`;
    return;
  }
  list.innerHTML = '';
  convs.forEach(c => {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.onclick = () => openConversationDetail(c.id);

    const date = new Date(c.start_time);
    const dateStr = date.toLocaleDateString('en-AU', { day:'numeric', month:'short' });
    const timeStr = date.toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' });

    const duration = c.end_time
      ? `${Math.round((new Date(c.end_time) - date) / 60000)}m`
      : 'ongoing';

    const people = (c.people_present || [])
      .map(pid => { const p = state.people.find(x => x.id === pid); return p ? p.name : `#${pid}`; })
      .join(', ');

    item.innerHTML = `
      <div class="history-date">${dateStr}<br><small>${timeStr}</small></div>
      <div class="history-info">
        <div class="history-title">${people || 'Unknown'} · ${duration}</div>
        <div class="history-summary">${escHtml((c.summary || 'No summary yet.').slice(0, 120))}</div>
        <div class="history-tags">
          ${people ? `<span class="history-tag">👥 ${people}</span>` : ''}
          <span class="history-tag">⏱ ${duration}</span>
        </div>
      </div>`;
    list.appendChild(item);
  });
}

async function openConversationDetail(convId) {
  try {
    const conv = await api('GET', `/conversations/${convId}`);
    // Show in a modal-like overlay using the summary modal reuse
    const summaryModal = document.getElementById('modal-summary');
    document.getElementById('summary-text').value = conv.summary || '';

    const memList = document.getElementById('memory-review-list');
    const date = new Date(conv.start_time).toLocaleDateString('en-AU', { weekday:'long', day:'numeric', month:'long', year:'numeric' });
    memList.innerHTML = `<div style="margin-bottom:12px;"><strong>${date}</strong></div>`;

    if (conv.segments?.length) {
      const transcriptDiv = document.createElement('div');
      transcriptDiv.style.cssText = 'max-height:300px;overflow-y:auto;background:var(--bg-input);border-radius:8px;padding:12px;font-size:0.85rem;margin-bottom:12px;';
      conv.segments.forEach(s => {
        const line = document.createElement('p');
        line.style.marginBottom = '6px';
        const time = new Date(s.timestamp).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' });
        line.innerHTML = `<span style="color:var(--text-muted);">[${time}]</span> <strong>${escHtml(s.speaker_label)}:</strong> ${escHtml(s.text)}`;
        transcriptDiv.appendChild(line);
      });
      memList.appendChild(transcriptDiv);
    }

    // Export button
    const exportBtn = document.createElement('button');
    exportBtn.className = 'btn-secondary';
    exportBtn.textContent = 'Export as text';
    exportBtn.style.marginRight = '8px';
    exportBtn.onclick = () => window.open(`/conversations/${convId}/export`, '_blank');
    memList.appendChild(exportBtn);

    summaryModal.classList.add('open');
  } catch (e) {
    toast('Could not load conversation: ' + e.message, 'error');
  }
}

// ── Plans Screen ──────────────────────────────────────────────────────────────
async function loadPlans() {
  try {
    const plans = await api('GET', '/plans');
    state.plans = plans;
    renderPlans(plans);
  } catch (e) {
    toast('Could not load plans', 'error');
  }
}

function renderPlans(plans) {
  const content = document.getElementById('plans-content');
  if (!plans.length) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">📋</div><p>No plans yet. Create one to prepare for an upcoming conversation.</p></div>`;
    return;
  }
  content.innerHTML = '';
  plans.forEach(plan => {
    const card = document.createElement('div');
    card.className = 'plan-card';
    card.onclick = () => openPlanModal(plan);
    const date = plan.planned_date
      ? new Date(plan.planned_date).toLocaleDateString('en-AU', { day:'numeric', month:'short', year:'numeric' })
      : 'No date set';
    const people = (plan.people_expected || [])
      .map(pid => { const p = state.people.find(x => x.id === pid); return p ? p.name : `#${pid}`; })
      .join(', ');
    card.innerHTML = `
      <div class="plan-card-header">
        <div>
          <div class="plan-card-title">${escHtml(plan.title)}</div>
          <div class="plan-card-date">${date}${people ? ' · ' + people : ''}</div>
        </div>
        <span class="plan-card-tone">${plan.tone}</span>
      </div>
      <div class="chip-list" style="margin-top:8px;">
        ${(plan.topics_expected || []).map(t => `<span class="chip">${escHtml(t)}</span>`).join('')}
      </div>
      <div style="font-size:0.78rem;color:var(--text-dim);margin-top:8px;">
        ${plan.things_to_say?.length || 0} things to say · ${plan.questions_to_ask?.length || 0} questions
      </div>`;
    content.appendChild(card);
  });
}

function openPlanModal(plan = null) {
  // Reset chip state
  state.planChips = { topics: [], say: [], ask: [] };

  document.getElementById('plan-modal-title').textContent = plan ? 'Edit Plan' : 'New Conversation Plan';
  document.getElementById('plan-modal-id').value = plan ? plan.id : '';
  document.getElementById('plan-title-input').value = plan ? plan.title : '';
  document.getElementById('plan-date-input').value = plan?.planned_date ? new Date(plan.planned_date).toISOString().slice(0,16) : '';
  document.getElementById('plan-location-input').value = plan ? plan.location_expected : '';
  document.getElementById('plan-tone-input').value = plan ? plan.tone : 'friendly';
  document.getElementById('plan-notes-input').value = plan ? plan.notes : '';

  if (plan) {
    state.planChips.topics = [...(plan.topics_expected || [])];
    state.planChips.say = [...(plan.things_to_say || [])];
    state.planChips.ask = [...(plan.questions_to_ask || [])];
  }

  renderPlanChips('topics');
  renderPlanChips('say');
  renderPlanChips('ask');
  document.getElementById('modal-plan').classList.add('open');
}

function addChip(type, event) {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  const inputId = `plan-${type}-input`;
  const val = document.getElementById(inputId)?.value.trim();
  if (!val) return;
  state.planChips[type].push(val);
  document.getElementById(inputId).value = '';
  renderPlanChips(type);
}

function renderPlanChips(type) {
  const container = document.getElementById(`plan-${type}-chips`);
  const input = document.getElementById(`plan-${type}-input`);
  container.innerHTML = '';
  state.planChips[type].forEach((item, i) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.innerHTML = `${escHtml(item)}<span class="chip-remove" onclick="removeChip('${type}',${i})">✕</span>`;
    container.appendChild(chip);
  });
  container.appendChild(input);
}

function removeChip(type, idx) {
  state.planChips[type].splice(idx, 1);
  renderPlanChips(type);
}

async function savePlan() {
  const id = document.getElementById('plan-modal-id').value;
  const dateVal = document.getElementById('plan-date-input').value;
  const data = {
    title: document.getElementById('plan-title-input').value.trim(),
    planned_date: dateVal ? new Date(dateVal).toISOString() : null,
    location_expected: document.getElementById('plan-location-input').value.trim(),
    tone: document.getElementById('plan-tone-input').value,
    notes: document.getElementById('plan-notes-input').value.trim(),
    topics_expected: state.planChips.topics,
    things_to_say: state.planChips.say,
    questions_to_ask: state.planChips.ask,
  };
  if (!data.title) return;
  try {
    if (id) {
      await api('PATCH', `/plans/${id}`, data);
    } else {
      await api('POST', '/plans', data);
    }
    closeModal('modal-plan');
    loadPlans();
    toast('Plan saved', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function previewPlan() {
  const id = document.getElementById('plan-modal-id').value;
  if (!id) {
    toast('Save the plan first before previewing', 'info');
    return;
  }
  const btn = document.getElementById('plan-preview-btn');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  try {
    const suggestions = await api('POST', `/plans/${id}/preview-prompts`);
    btn.disabled = false;
    btn.textContent = 'Preview prompts';
    closeModal('modal-plan');
    // Show prompts in a simple overlay
    renderPrompts(suggestions);
    showScreen('conversation');
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Preview prompts';
    toast('Error: ' + e.message, 'error');
  }
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadVoices() {
  const sel = document.getElementById('voice-select');
  if (!sel) return;

  if (!state.elevenLabsAvailable) {
    sel.innerHTML = '<option value="">ElevenLabs not configured — using browser voice</option>';
    sel.disabled = true;
    document.getElementById('voice-section')?.classList.add('tts-unavailable');
    return;
  }

  try {
    const data = await api('GET', '/tts/voices');
    sel.innerHTML = '<option value="">— select a voice —</option>';
    (data.voices || []).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.voice_id;
      opt.textContent = `${v.name}${v.category ? ' (' + v.category + ')' : ''}`;
      opt.selected = v.voice_id === state.selectedVoiceId;
      sel.appendChild(opt);
    });
    if (!data.voices?.length) {
      sel.innerHTML = '<option value="">No voices found — check ElevenLabs API key</option>';
    }
  } catch (e) { /* silent */ }
}

function saveVoiceSetting() {
  const voiceId = document.getElementById('voice-select').value;
  state.selectedVoiceId = voiceId;
  localStorage.setItem('elevenlabs_voice_id', voiceId);
  toast('Voice saved', 'success');
}

async function previewVoice() {
  const voiceId = document.getElementById('voice-select').value;
  if (!voiceId) { toast('Select a voice first', 'info'); return; }
  try {
    const res = await fetch('/tts/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Hi, I'm James. Nice to meet you.", voice_id: voiceId }),
    });
    if (!res.ok) throw new Error('Preview failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audioEl = document.getElementById('tts-audio');
    audioEl.src = url;
    await audioEl.play();
    audioEl.onended = () => URL.revokeObjectURL(url);
  } catch (e) {
    toast('Preview failed: ' + e.message, 'error');
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escAttr(str) {
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// Close modals on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.remove('open');
  });
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
    closePersonDetail();
  }
});
