/* session.js — drives the session page (word list + all exercise types) */

'use strict';

// SESSION_ID injected by the template
const _sid = window.SESSION_ID;

// ============================================================
// Utilities
// ============================================================

function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function langName(code) {
  return { en: 'English', de: 'German', es: 'Spanish', ja: 'Japanese' }[code] || code;
}

function catLabel(cat) {
  return { N: 'noun', V: 'verb', A: 'adj', Adv: 'adv' }[cat] || cat || '';
}

function diffLabel(d) {
  return ['', 'A1', 'A2', 'B1', 'B2', 'C1'][d] || String(d);
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Tokenise a sentence into word-like chunks (preserves punctuation as separate tokens) */
function tokenize(sentence) {
  return (sentence.match(/[\w''äöüÄÖÜßàáâãéêëíîïôõùûúñçæœ]+|[^\s\w]/gu) || []);
}

async function apiGet(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

async function apiPost(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrf(),
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

// ============================================================
// State
// ============================================================

const state = {
  session:     null,
  words:       [],
  knownFns:    new Set(),
  exercises:   [],
  currentIdx:  0,
  score:       { correct: 0, total: 0 },
  phase:       'loading',   // loading | words | exercises | done
  tileState:   null,
  startTime:   null,
  pollTimer:   null,
};

// ============================================================
// Phase: loading — poll session status
// ============================================================

function startPolling() {
  pollOnce();
  state.pollTimer = setInterval(pollOnce, 2500);
}

async function pollOnce() {
  try {
    const session = await apiGet(`/api/sessions/${_sid}/`);
    state.session = session;

    const st = session.status;
    document.getElementById('status-text').textContent =
      `Status: ${st}${st === 'pending' ? ' — this may take a minute…' : ''}`;

    if (st === 'words_ready' || st === 'complete') {
      clearInterval(state.pollTimer);
      if (state.phase === 'loading') {
        await enterWordsPhase();
      }
      if (st === 'complete') {
        enableExercisesButton();
      } else {
        // Still building sentences — re-poll until complete
        state.pollTimer = setInterval(async () => {
          const s2 = await apiGet(`/api/sessions/${_sid}/`);
          state.session = s2;
          if (s2.status === 'complete') {
            clearInterval(state.pollTimer);
            enableExercisesButton();
          }
        }, 3000);
      }
    } else if (st === 'failed') {
      clearInterval(state.pollTimer);
      showPageError('Lesson build failed. Please try again.');
    }
  } catch (e) {
    console.error('poll error', e);
  }
}

// ============================================================
// Phase: words
// ============================================================

async function enterWordsPhase() {
  state.phase = 'words';
  try {
    const words = await apiGet(`/api/sessions/${_sid}/words/`);
    state.words = words;
    renderWordList(words);
    document.getElementById('loading-section').classList.add('d-none');
    document.getElementById('words-section').classList.remove('d-none');
    const s = state.session;
    document.getElementById('words-heading').textContent =
      `Vocabulary — ${langName(s.source_lang)} → ${langName(s.target_lang)}`;
  } catch (e) {
    showPageError('Failed to load word list: ' + e.message);
  }
}

function renderWordList(words) {
  const container = document.getElementById('word-list');
  container.innerHTML = '';

  if (!words.length) {
    container.innerHTML = '<p class="text-muted">No vocabulary found in this document.</p>';
    return;
  }

  const tgt = state.session.target_lang;

  words.forEach(lw => {
    const entry      = lw.entry;
    const trans      = (entry.translations && entry.translations[tgt]) || '—';
    const cat        = catLabel(entry.gf_cat);
    const freq       = lw.source_count;

    const col = document.createElement('div');
    col.className = 'col-sm-6 col-md-4 col-lg-3';
    col.innerHTML = `
      <div class="word-card card h-100 shadow-sm" data-fn="${escHtml(entry.gf_function)}">
        <div class="card-body d-flex flex-column">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <span class="fw-semibold fs-5">${escHtml(entry.word)}</span>
            ${cat ? `<span class="badge bg-secondary ms-1" style="font-size:.7rem">${escHtml(cat)}</span>` : ''}
          </div>
          <span class="text-muted mb-1">${escHtml(trans)}</span>
          ${freq > 1 ? `<small class="text-muted mb-2">${freq}× in text</small>` : '<div class="mb-2"></div>'}
          <button class="btn btn-sm btn-outline-secondary mt-auto know-btn" data-fn="${escHtml(entry.gf_function)}">
            I know this
          </button>
        </div>
      </div>`;
    container.appendChild(col);
  });

  container.querySelectorAll('.know-btn').forEach(btn => {
    btn.addEventListener('click', () => toggleKnown(btn));
  });
}

function toggleKnown(btn) {
  const fn   = btn.dataset.fn;
  const card = btn.closest('.word-card');
  if (state.knownFns.has(fn)) {
    state.knownFns.delete(fn);
    btn.className = 'btn btn-sm btn-outline-secondary mt-auto know-btn';
    btn.textContent = 'I know this';
    card.classList.remove('known');
  } else {
    state.knownFns.add(fn);
    btn.className = 'btn btn-sm btn-success mt-auto know-btn';
    btn.textContent = '✓ Known';
    card.classList.add('known');
  }
}

function enableExercisesButton() {
  const btn     = document.getElementById('start-exercises-btn');
  const spinner = document.getElementById('ex-spinner');
  const badge   = document.getElementById('build-badge');
  spinner.classList.add('d-none');
  badge.classList.add('d-none');
  btn.disabled = false;
  btn.textContent = 'Start exercises →';
}

// ============================================================
// Phase: exercises
// ============================================================

async function startExercises() {
  const known = [...state.knownFns].join(',');
  const url   = `/api/sessions/${_sid}/exercises/?n=20${known ? '&known=' + encodeURIComponent(known) : ''}`;
  try {
    const exercises = await apiGet(url);
    if (!exercises.length) {
      showPageError('No exercises available — try unmarking some known words.');
      return;
    }
    state.exercises  = exercises;
    state.currentIdx = 0;
    state.score      = { correct: 0, total: 0 };
    state.phase      = 'exercises';

    document.getElementById('words-section').classList.add('d-none');
    document.getElementById('exercise-section').classList.remove('d-none');
    document.getElementById('score-bar').style.display = '';

    renderExercise(exercises[0]);
  } catch (e) {
    showPageError('Failed to load exercises: ' + e.message);
  }
}

function renderExercise(ex) {
  state.startTime  = Date.now();
  const total      = state.exercises.length;
  const idx        = state.currentIdx;

  document.getElementById('ex-progress').style.width = `${(idx / total) * 100}%`;
  document.getElementById('ex-counter').textContent  = `${idx + 1} / ${total}`;
  updateScoreBar();

  const container = document.getElementById('exercise-container');
  container.innerHTML = '';

  switch (ex.exercise_type) {
    case 'word_translation_mc': renderWordMC(container, ex);         break;
    case 'sentence_mc':         renderSentenceMC(container, ex);     break;
    case 'sentence_translation':renderSentenceTiles(container, ex);  break;
    default:
      container.innerHTML = `<div class="alert alert-warning">Unknown exercise type: ${escHtml(ex.exercise_type)}</div>`;
  }
}

// ---- Word translation MC ----

function renderWordMC(container, ex) {
  const diff = diffLabel(ex.difficulty);
  container.innerHTML = `
    <div class="exercise-card">
      <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="text-muted small">Word translation</span>
        <span class="badge bg-primary">${escHtml(diff)}</span>
      </div>
      <p class="text-muted mb-1">How do you say</p>
      <div class="prompt-word mb-2">${escHtml(ex.prompt)}</div>
      <p class="text-muted mb-4">in ${escHtml(langName(ex.target_lang))}?</p>
      <div class="choices-grid" id="choices"></div>
    </div>`;
  buildMCChoices(ex);
}

// ---- Sentence MC ----

function renderSentenceMC(container, ex) {
  const diff = diffLabel(ex.difficulty);
  container.innerHTML = `
    <div class="exercise-card">
      <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="text-muted small">Choose the correct translation</span>
        <span class="badge bg-primary">${escHtml(diff)}</span>
      </div>
      <div class="prompt-sentence mb-4">${escHtml(ex.prompt)}</div>
      <div class="choices-grid" id="choices"></div>
    </div>`;
  buildMCChoices(ex);
}

function buildMCChoices(ex) {
  const grid = document.getElementById('choices');
  (ex.choices || []).forEach(choice => {
    const btn = document.createElement('button');
    btn.className   = 'choice-btn btn btn-outline-primary';
    btn.textContent = choice;
    btn.addEventListener('click', () => handleMCAnswer(ex, choice, btn));
    grid.appendChild(btn);
  });
}

function handleMCAnswer(ex, chosen, btn) {
  document.querySelectorAll('.choice-btn').forEach(b => { b.disabled = true; });
  const isCorrect = chosen === ex.correct;
  btn.classList.add(isCorrect ? 'correct' : 'incorrect');
  if (!isCorrect) {
    document.querySelectorAll('.choice-btn').forEach(b => {
      if (b.textContent === ex.correct) b.classList.add('correct');
    });
  }
  showFeedback(ex, isCorrect);
}

// ---- Sentence translation — word tiles ----

function renderSentenceTiles(container, ex) {
  const diff          = diffLabel(ex.difficulty);
  const correctTokens = tokenize(ex.correct);

  // Gather distractor words from other exercises
  const distWords = pickDistractors(ex, correctTokens, 4);

  // Build tile objects indexed by id so duplicates are handled safely
  const allWords  = shuffle([...correctTokens, ...distWords]);
  const tiles     = allWords.map((word, i) => ({ id: i, word, location: 'bank' }));

  state.tileState = { ex, correctTokens, tiles, answerIds: [] };

  container.innerHTML = `
    <div class="exercise-card">
      <div class="d-flex justify-content-between align-items-center mb-4">
        <span class="text-muted small">Arrange the words</span>
        <span class="badge bg-primary">${escHtml(diff)}</span>
      </div>
      <div class="prompt-sentence mb-4">${escHtml(ex.prompt)}</div>
      <div class="tile-answer-area mb-3" id="tile-answer">
        <span id="tile-placeholder" class="tile-placeholder text-muted fst-italic small">
          Tap words below to build your answer
        </span>
      </div>
      <hr class="my-3">
      <div class="tile-bank" id="tile-bank"></div>
      <div class="mt-4 d-flex gap-2">
        <button class="btn btn-primary" id="check-tiles" disabled>Check</button>
        <button class="btn btn-link text-muted px-0" id="clear-tiles">Clear</button>
      </div>
    </div>`;

  renderAllTiles();

  document.getElementById('clear-tiles').addEventListener('click', clearTiles);
  document.getElementById('check-tiles').addEventListener('click', () => checkTiles());
}

function renderAllTiles() {
  const { tiles, answerIds } = state.tileState;
  const answerArea = document.getElementById('tile-answer');
  const bankArea   = document.getElementById('tile-bank');
  const placeholder = document.getElementById('tile-placeholder');

  // Clear both areas
  answerArea.innerHTML = '';
  bankArea.innerHTML   = '';

  // Re-add placeholder if answer is empty
  if (answerIds.length === 0) {
    const ph = document.createElement('span');
    ph.id          = 'tile-placeholder';
    ph.className   = 'tile-placeholder text-muted fst-italic small';
    ph.textContent = 'Tap words below to build your answer';
    answerArea.appendChild(ph);
    answerArea.classList.remove('has-tiles');
  } else {
    answerArea.classList.add('has-tiles');
  }

  // Render answer tiles in order
  answerIds.forEach(id => {
    const tile = tiles.find(t => t.id === id);
    if (!tile) return;
    answerArea.appendChild(makeTileBtn(tile, 'answer'));
  });

  // Render bank tiles (those not in answer)
  const usedIds = new Set(answerIds);
  tiles.filter(t => !usedIds.has(t.id)).forEach(tile => {
    bankArea.appendChild(makeTileBtn(tile, 'bank'));
  });

  // Enable/disable check
  document.getElementById('check-tiles').disabled = answerIds.length === 0;
}

function makeTileBtn(tile, location) {
  const btn = document.createElement('button');
  btn.className   = location === 'answer'
    ? 'tile-btn btn btn-secondary in-answer'
    : 'tile-btn btn btn-outline-secondary';
  btn.textContent = tile.word;
  btn.dataset.id  = tile.id;
  btn.addEventListener('click', () => toggleTile(tile.id, location));
  return btn;
}

function toggleTile(id, location) {
  const ts = state.tileState;
  if (location === 'bank') {
    ts.answerIds.push(id);
  } else {
    ts.answerIds = ts.answerIds.filter(i => i !== id);
  }
  renderAllTiles();
}

function clearTiles() {
  state.tileState.answerIds = [];
  renderAllTiles();
}

function checkTiles() {
  const { ex, correctTokens, tiles, answerIds } = state.tileState;

  // Disable interaction
  document.querySelectorAll('.tile-btn').forEach(b => { b.disabled = true; });
  document.getElementById('check-tiles').disabled   = true;
  document.getElementById('clear-tiles').disabled   = true;

  const answerWords  = answerIds.map(id => tiles.find(t => t.id === id)?.word ?? '');
  const isCorrect    = answerWords.join(' ') === correctTokens.join(' ');

  const answerArea = document.getElementById('tile-answer');
  answerArea.classList.add(isCorrect ? 'check-correct' : 'check-incorrect');

  showFeedback(ex, isCorrect);
}

function pickDistractors(ex, correctTokens, count) {
  const correctSet = new Set(correctTokens.map(w => w.toLowerCase()));
  const candidates = [];
  state.exercises.forEach(other => {
    if (other === ex || !other.correct) return;
    tokenize(other.correct).forEach(w => {
      if (!correctSet.has(w.toLowerCase())) candidates.push(w);
    });
  });
  // Deduplicate, sample randomly
  const uniq = [...new Set(candidates)];
  return shuffle(uniq).slice(0, count);
}

// ============================================================
// Feedback strip + Next button
// ============================================================

function showFeedback(ex, isCorrect) {
  const ms        = Date.now() - state.startTime;
  state.score.total++;
  if (isCorrect) state.score.correct++;
  updateScoreBar();

  // Submit to API (fire-and-forget; don't block UX)
  submitAttempt(ex, isCorrect, ms).catch(console.warn);

  const container = document.getElementById('exercise-container').querySelector('.exercise-card');
  const strip      = document.createElement('div');
  strip.className  = `feedback-strip ${isCorrect ? 'correct' : 'incorrect'}`;

  const isLast = state.currentIdx >= state.exercises.length - 1;
  strip.innerHTML = `
    <span>${isCorrect ? '✓ Correct' : `✗ Correct answer: ${escHtml(ex.correct)}`}</span>
    <button class="btn btn-sm ${isCorrect ? 'btn-success' : 'btn-danger'} ms-3" id="next-btn">
      ${isLast ? 'Finish' : 'Next →'}
    </button>`;
  container.appendChild(strip);

  document.getElementById('next-btn').addEventListener('click', () => {
    if (isLast) {
      enterDonePhase();
    } else {
      state.currentIdx++;
      renderExercise(state.exercises[state.currentIdx]);
    }
  });
}

// ============================================================
// Phase: done
// ============================================================

function enterDonePhase() {
  state.phase = 'done';
  document.getElementById('exercise-section').classList.add('d-none');
  document.getElementById('done-section').classList.remove('d-none');
  const { correct, total } = state.score;
  document.getElementById('final-score').textContent = `${correct} / ${total}`;
  document.getElementById('retry-btn').addEventListener('click', () => {
    state.currentIdx = 0;
    state.score      = { correct: 0, total: 0 };
    state.phase      = 'exercises';
    document.getElementById('done-section').classList.add('d-none');
    document.getElementById('exercise-section').classList.remove('d-none');
    renderExercise(state.exercises[0]);
  });
}

// ============================================================
// API — submit attempt
// ============================================================

async function submitAttempt(ex, isCorrect, responseMs) {
  const session = state.session;
  const body    = {
    session_id:       _sid,
    exercise_type:    ex.exercise_type,
    difficulty:       ex.difficulty,
    pattern:          ex.metadata?.pattern || {},
    gf_function:      ex.metadata?.gf_function || '',
    gf_cat:           ex.metadata?.gf_cat || '',
    prompt:           ex.prompt,
    prompt_lang:      ex.prompt_lang,
    target_lang:      ex.target_lang,
    correct_answer:   ex.correct,
    user_answer:      _lastUserAnswer(ex),
    is_correct:       isCorrect,
    response_time_ms: Math.round(responseMs),
  };
  return apiPost('/api/attempts/', body);
}

function _lastUserAnswer(ex) {
  // Reconstruct user's answer for logging
  if (state.tileState && state.tileState.ex === ex) {
    const { tiles, answerIds } = state.tileState;
    return answerIds.map(id => tiles.find(t => t.id === id)?.word ?? '').join(' ');
  }
  // For MC: look for the selected (correct or incorrect) button
  const wrong = document.querySelector('.choice-btn.incorrect');
  if (wrong) return wrong.textContent;
  const right = document.querySelector('.choice-btn.correct');
  return right ? right.textContent : '';
}

// ============================================================
// Score bar
// ============================================================

function updateScoreBar() {
  document.getElementById('score-val').textContent = state.score.correct;
  document.getElementById('score-tot').textContent = state.score.total;
}

// ============================================================
// Error display
// ============================================================

function showPageError(msg) {
  document.getElementById('loading-section').innerHTML =
    `<div class="alert alert-danger">${escHtml(msg)}</div>`;
  document.getElementById('loading-section').classList.remove('d-none');
}

// ============================================================
// Event bindings
// ============================================================

document.getElementById('start-exercises-btn').addEventListener('click', startExercises);
document.getElementById('back-to-words').addEventListener('click', () => {
  document.getElementById('exercise-section').classList.add('d-none');
  document.getElementById('words-section').classList.remove('d-none');
  state.phase = 'words';
});

// ============================================================
// Boot
// ============================================================

startPolling();
