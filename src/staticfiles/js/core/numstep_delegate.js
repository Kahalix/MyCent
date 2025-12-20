(function (root) {
  if (root.__lownNumstepInited) return; // idempotent
  root.__lownNumstepInited = true;

  const timers = new WeakMap(); // btn -> {hold:Timeout, rep:Interval}

  function decs(n) { if (n == null || n === 'any') return 0; n = String(n); const p = n.split('.')[1]; return p ? p.length : 0; }
  function num(s)  { if (s === '' || s == null) return null; const n = Number(s); return Number.isFinite(n) ? n : null; }

  function stepValue(input, dir) {
    const typeAttr = input.getAttribute('data-ssf-type');
    const isInt = typeAttr === 'integer' || input.type === 'number' && (input.step === '1' || input.getAttribute('step') === '1');

    const stepAttr = input.getAttribute('step') || (isInt ? '1' : 'any');
    const minAttr  = input.getAttribute('min');
    const maxAttr  = input.getAttribute('max');

    let cur = num(input.value);
    const min = num(minAttr);
    const max = num(maxAttr);

    let step = stepAttr === 'any' ? (isInt ? 1 : 1) : Number(stepAttr);
    if (!Number.isFinite(step) || step <= 0) step = (isInt ? 1 : 1);

    const prec = Math.max(decs(stepAttr), decs(minAttr), decs(input.value || ''));
    const pow = Math.pow(10, prec || 0);

    if (cur === null) cur = (min != null ? min : 0);
    cur = cur + dir * step;

    if (min != null && cur < min) cur = min;
    if (max != null && cur > max) cur = max;
    if (isInt) cur = Math.round(cur);

    return Math.round(cur * pow) / pow;
  }

  function applyAndEmit(input, v) {
    const prev = input.value;
    input.value = (v == null ? '' : String(v));
    if (input.value !== prev) {
      input.dispatchEvent(new Event('input',  { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function nearestBtn(target) { return target && target.closest ? target.closest('.numstep__btn') : null; }
  function nearestInput(btn)  { return btn && btn.closest ? btn.closest('.numstep')?.querySelector('.numstep__input') : null; }

  function stepOnce(btn, dir) {
    const input = nearestInput(btn);
    if (!input || input.disabled) return;
    applyAndEmit(input, stepValue(input, dir));
    try { input.focus({ preventScroll: true }); } catch {}
  }

  // --- pointer handlers (CAPTURE) ---
  function onPointerDown(e) {
    const btn = nearestBtn(e.target);
    if (!btn) return;
    // przejmij kontrolę — blokujemy inne listenery na przycisku (np. stare SSF)
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();

    const dir = btn.classList.contains('numstep__btn--up') ? +1 : -1;
    stepOnce(btn, dir);

    const hold = setTimeout(() => {
      const rep = setInterval(() => stepOnce(btn, dir), 110);
      timers.set(btn, { hold: null, rep });
    }, 320);
    timers.set(btn, { hold, rep: null });

    try { btn.setPointerCapture(e.pointerId); } catch {}
  }

  function clearTimers(btn) {
    const t = timers.get(btn);
    if (!t) return;
    if (t.hold) clearTimeout(t.hold);
    if (t.rep)  clearInterval(t.rep);
    timers.delete(btn);
  }

  function onPointerUpLike(e) {
    const btn = nearestBtn(e.target);
    if (!btn) return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    clearTimers(btn);
  }

  // --- click guard (CAPTURE) — żeby nie odpalały się stare „click” handlery
  function onClickCapture(e) {
    if (nearestBtn(e.target)) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); }
  }

  // --- klawiatura na inputach
  function onKeydown(e) {
    const el = e.target;
    if (!el || !el.classList || !el.classList.contains('numstep__input')) return;
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const dir = e.key === 'ArrowUp' ? +1 : -1;
      applyAndEmit(el, stepValue(el, dir));
    }
  }

  // init
  function init() {
    document.addEventListener('pointerdown',  onPointerDown,   true); // capture
    document.addEventListener('pointerup',    onPointerUpLike,  true);
    document.addEventListener('pointerleave', onPointerUpLike,  true);
    document.addEventListener('pointercancel',onPointerUpLike,  true);
    document.addEventListener('click',        onClickCapture,   true);
    document.addEventListener('keydown',      onKeydown,        false);
  }

  // API (na wszelki wypadek)
  root.lownNumstep = { init };

  // auto-init
  init();
})(window);
