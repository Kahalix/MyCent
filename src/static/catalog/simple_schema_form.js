(function(){
  // Schema Form

  function jsonParse(s){ try { return JSON.parse(s); } catch(e){ return null; } }
  function clone(o){ return o && typeof o === "object" ? JSON.parse(JSON.stringify(o)) : o; }

  function normalizeSchema(schema){
    var s = schema || {};
    if (typeof s !== "object" || Array.isArray(s)) return { type:"object", properties:{} };
    if (!s.type) {
      if (s.properties) s = { type:"object", properties:s.properties };
      else if (s.items)  s = { type:"array", items:s.items };
      else s = { type:"object", properties:{} };
    }
    if (s.type === "object" && !s.properties) s.properties = {};
    return s;
  }

  function skeletonFrom(schema){
    var S = normalizeSchema(schema), out = {}, props = S.properties || {};
    Object.keys(props).forEach(function(k){
      var spec = props[k] || {};
      if ("default" in spec) out[k] = spec.default;
      else if (spec.type === "string") out[k] = "";
      else if (spec.type === "integer" || spec.type === "number") out[k] = null;
      else if (spec.type === "boolean") out[k] = false;
      else out[k] = null;
    });
    return out;
  }

  function reconcileAttrs(current, schema){
    var cur = (current && typeof current === "object") ? current : {};
    var base = skeletonFrom(schema), props = normalizeSchema(schema).properties || {};
    Object.keys(props).forEach(function(k){
      if (Object.prototype.hasOwnProperty.call(cur, k)) base[k] = cur[k];
    });
    return base;
  }

  function makeEl(tag, attrs, children){
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function(k){
      if (k === "class") el.className = attrs[k];
      else if (k === "for") el.htmlFor = attrs[k];
      else if (k === "text") el.textContent = attrs[k];
      else if (k === "html") el.innerHTML = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    (children||[]).forEach(function(ch){ el.appendChild(ch); });
    return el;
  }

  /* ===== numstep helpers ===== */

  // -- clamp liczb do min/max + normalizacja dla integerów (step=1)
  function clampNumberInput(el){
    if (!el || el.type !== 'number') return;

    var raw = (el.value || '').trim();
    if (raw === '') return;

    var v = Number(raw);
    if (!Number.isFinite(v)) return;

    var hasMin = el.hasAttribute('min');
    var hasMax = el.hasAttribute('max');
    var min = hasMin ? Number(el.min) : -Infinity;
    var max = hasMax ? Number(el.max) :  Infinity;

    if (v < min) v = min;
    if (v > max) v = max;

    // dla integerów (step=1) zrzuć do najbliższej liczby całkowitej
    var st = el.getAttribute('step');
    if (st && st !== 'any') {
      var sn = Number(st);
      if (Number.isFinite(sn) && sn === 1) v = Math.round(v);
    }

    var out = String(v);
    if (out !== raw) el.value = out;
  }

  function _decimalsOf(nStr){
    if (!nStr || String(nStr) === 'any') return 0;
    var s = String(nStr);
    if (s.indexOf('e') >= 0 || s.indexOf('E') >= 0) return 6;
    var p = s.split('.')[1];
    return p ? p.length : 0;
  }
  function _parseNum(s){
    if (s==='' || s==null) return null;
    var n = Number(s);
    return Number.isFinite(n) ? n : null;
  }
  function _stepValue(input, dir){
    var type = input.getAttribute('data-ssf-type') || input.type || 'number';
    var stepAttr = input.getAttribute('step') || (type==='integer' ? '1' : 'any');
    var minAttr  = input.getAttribute('min');
    var maxAttr  = input.getAttribute('max');

    var cur = _parseNum(input.value);
    var min = _parseNum(minAttr);
    var max = _parseNum(maxAttr);

    var step = stepAttr==='any' ? (type==='integer' ? 1 : 1) : Number(stepAttr);
    if (!Number.isFinite(step) || step<=0) step = (type==='integer' ? 1 : 1);

    // precyzja zaokrąglania wg step/min/obecnej wartości
    var prec = Math.max(_decimalsOf(stepAttr), _decimalsOf(minAttr), _decimalsOf(input.value));
    var pow = Math.pow(10, prec);

    // gdy pusto zacznij od min (lub 0) i dopiero przesuń o step
    if (cur===null){
      cur = (min!=null ? min : 0);
      if (dir>0){ cur = cur + step; }
      if (dir<0){ cur = cur - step; }
    } else {
      cur = cur + dir * step;
    }

    // twarde domykanie do zakresu
    if (min!=null && cur < min) cur = min;
    if (max!=null && cur > max) cur = max;

    // integer wymusza zaokrąglenie do całkowitych
    if (type==='integer'){ cur = Math.round(cur); }

    // fix float
    cur = Math.round(cur * pow) / pow;
    return cur;
  }
  function _applyAndEmit(input, val){
    var prev = input.value;
    input.value = (val==null ? '' : String(val));
    if (input.value !== prev){
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }
  function _bindNumstep(container, input){
    var up   = container.querySelector('.numstep__btn--up');
    var down = container.querySelector('.numstep__btn--down');
    if (!up || !down) return;

    function stepOnce(dir){
      if (input.disabled) return;
      var v = _stepValue(input, dir);
      _applyAndEmit(input, v);
      try { input.focus({ preventScroll:true }); } catch {}
    }

    function wire(btn, dir){
      let t1=null, t2=null;
      const start = (e)=>{
        e.preventDefault();
        stepOnce(dir);
        t1 = setTimeout(()=>{ t2 = setInterval(()=>stepOnce(dir), 110); }, 320);
        try{ btn.setPointerCapture && btn.setPointerCapture(e.pointerId); }catch{}
      };
      const stop = ()=>{
        if (t1){ clearTimeout(t1); t1=null; }
        if (t2){ clearInterval(t2); t2=null; }
      };
      btn.addEventListener('pointerdown', start);
      btn.addEventListener('pointerup', stop);
      btn.addEventListener('pointerleave', stop);
      btn.addEventListener('pointercancel', stop);
    }
    wire(up,   +1);
    wire(down, -1);

    // sync disabled -> klasa wizualna
    var ro = new MutationObserver(function(){
      container.classList.toggle('is-disabled', !!input.disabled);
    });
    ro.observe(input, { attributes:true, attributeFilter:['disabled'] });
    container.classList.toggle('is-disabled', !!input.disabled);
  }
  /* ===== /numstep helpers ===== */

  function makeInput(name, spec, value, required){
    var type = (spec && spec.type) || "string";
    var id = "ssf_" + name + "_" + Math.random().toString(36).slice(2,8);
    var wrap = makeEl("div", {class:"ssf-field"});

    // etykieta
    var label = makeEl("label", {"for": id, "class":"ssf-label", text: name + (required ? " *" : "")});
    if (required) label.classList.add('is-required');
    wrap.appendChild(label);

    var control;
    var hasEnum = Array.isArray(spec.enum);

    if (hasEnum){
      // select
      control = makeEl("select", {
        "class":"ssf-input select select-bordered w-full fancy-select",
        id:id, "data-ssf-name":name
      });
      if (!required) control.appendChild(makeEl("option", {value:"", text:"—"}));
      (spec.enum || []).forEach(function(opt){
        var text = String(opt);
        var val = typeof opt === "string" ? opt : JSON.stringify(opt);
        var o = makeEl("option", {value: val, text: text});
        if ((value === opt) || (!required && value == null && val === "")) o.selected = true;
        control.appendChild(o);
      });
      if (required) control.required = true;

      wrap.appendChild(control);

    } else if (type === "boolean"){
      // toggle/checkbox
      control = makeEl("input", {
        type:"checkbox", id:id, "data-ssf-name":name,
        "class":"toggle"
      });
      control.checked = !!value;
      control.setAttribute('aria-checked', String(!!value));
      if (required) control.setAttribute('aria-required', 'true');

      wrap.appendChild(control);

    } else {
      // text/number
      var input = makeEl("input", {
        type:"text", id:id,
        "class":"ssf-input input input-bordered w-full fancy-area",
        "data-ssf-name":name
      });

      if (type === "integer"){
        input.type = "number";
        input.step = "1";
        input.setAttribute('data-ssf-type','integer');
      } else if (type === "number"){
        input.type = "number";
        // preferuj multipleOf jako step, inaczej 'any'
        if (typeof spec.multipleOf !== 'undefined' && Number(spec.multipleOf) > 0) input.step = String(spec.multipleOf);
        else input.step = "any";
        input.setAttribute('data-ssf-type','number');
      }

      if (spec && typeof spec.minimum !== "undefined") input.min = String(spec.minimum);
      if (spec && typeof spec.maximum !== "undefined") input.max = String(spec.maximum);
      if (spec && typeof spec.minLength !== "undefined") input.setAttribute("minlength", String(spec.minLength));
      if (spec && typeof spec.maxLength !== "undefined") input.setAttribute("maxlength", String(spec.maxLength));

      if (value !== null && typeof value !== "undefined") input.value = String(value);
      else input.value = "";

      if (required) input.required = true;

      // CLAMP - trzymaj wartość w [min,max] również dla strzałek i scrolla
      var _clampNow = function(){ clampNumberInput(input); };
      input.addEventListener('input', _clampNow);
      input.addEventListener('change', _clampNow);
      input.addEventListener('keydown', function(e){
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          requestAnimationFrame(_clampNow);
        }
      });
      input.addEventListener('wheel', function(){
        requestAnimationFrame(_clampNow);
      }, { passive: true });

      // jeśli to liczba opakuj w .numstep i dołóż przyciski
      if (type === "integer" || type === "number"){
        input.classList.add('numstep__input');
        var box = makeEl("div", {class:"numstep numstep--md"}, [
          input,
          makeEl("button", { type:"button", class:"numstep__btn numstep__btn--up",   "aria-label":"Zwiększ"}, []),
          makeEl("button", { type:"button", class:"numstep__btn numstep__btn--down", "aria-label":"Zmniejsz"}, []),
        ]);
        wrap.appendChild(box);
        _bindNumstep(box, input);
      } else {
        wrap.appendChild(input);
      }
    }

    if (spec && spec.description){
      wrap.appendChild(makeEl("div", {"class":"ssf-help", text:String(spec.description)}));
    }
    return wrap;
  }

  function readValue(container, schema){
    var out = {}, props = normalizeSchema(schema).properties || {};
    Object.keys(props).forEach(function(name){
      var spec = props[name] || {};
      var type = spec.type || "string";
      var input = container.querySelector('[data-ssf-name="'+ CSS.escape(name) +'"]');
      if (!input) return;

      if (Array.isArray(spec.enum)){
        var val = input.value;
        if (val === ""){
          out[name] = null;
        } else {
          try { out[name] = JSON.parse(val); }
          catch(e){ out[name] = val; }
        }
      } else if (type === "boolean"){
        out[name] = !!input.checked;
      } else if (type === "integer"){
        var iv = input.value.trim();
        out[name] = iv === "" ? null : (isNaN(parseInt(iv,10)) ? null : parseInt(iv,10));
      } else if (type === "number"){
        var nv = input.value.trim();
        out[name] = nv === "" ? null : (isNaN(parseFloat(nv)) ? null : parseFloat(nv));
      } else {
        var sv = input.value;
        out[name] = sv === "" ? "" : sv;
      }
    });
    return out;
  }

  function buildUI(hidden, schema, initial){
    var containerId = hidden.id + "__ssf";
    var existing = document.getElementById(containerId);
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

    var container = makeEl("div", {class:"ssf-container", id:containerId, "data-ssf-for": hidden.id});
    hidden.insertAdjacentElement("afterend", container);

    var S = normalizeSchema(schema);
    var props = S.properties || {};
    var required = Array.isArray(S.required) ? new Set(S.required) : new Set();

    if (!Object.keys(props).length){
      container.appendChild(makeEl("div", {"class":"ssf-empty", text:"(Brak pól dla tej kategorii)"}));
      return container;
    }

    Object.keys(props).forEach(function(name){
      var field = makeInput(name, props[name], initial[name], required.has(name));
      container.appendChild(field);
    });
    return container;
  }

  function writeHidden(hidden, obj){
    try { hidden.value = JSON.stringify(obj || {}); }
    catch(e){ hidden.value = "{}"; }
    hidden.dispatchEvent(new Event("input", {bubbles:true}));
    hidden.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function initOne(hidden){
    var schemaStr = hidden.getAttribute("data-ssf-schema");
    var schema = jsonParse(schemaStr) || {type:"object", properties:{}};
    var initial = jsonParse(hidden.value) || {};

    var container = buildUI(hidden, schema, reconcileAttrs(initial, schema));

    // bindowanie
    container.addEventListener("input", function(){
      var val = readValue(container, schema);
      writeHidden(hidden, val);
    });
    container.addEventListener("change", function(){
      var val = readValue(container, schema);
      writeHidden(hidden, val);
    });

    hidden._ssf = {container: container, schema: schema};
  }

  function swapSchema(hidden, newSchema, value){
    var S = normalizeSchema(newSchema || {type:"object",properties:{}});
    var current = value;
    if (typeof current === "undefined"){
      var hval = jsonParse(hidden.value) || {};
      current = reconcileAttrs(hval, S);
    }
    var container = buildUI(hidden, S, current);
    container.addEventListener("input", function(){
      var val = readValue(container, S);
      writeHidden(hidden, val);
    });
    container.addEventListener("change", function(){
      var val = readValue(container, S);
      writeHidden(hidden, val);
    });
    writeHidden(hidden, current);
    hidden._ssf = {container: container, schema: S};
  }

  function getHidden(elOrId){
    return (typeof elOrId === "string") ? document.getElementById(elOrId) : elOrId;
  }

  function initAll(){
    document.querySelectorAll('textarea[data-ssf="1"]').forEach(function(textarea){
      initOne(textarea);
    });
  }

  window.SSF = {
    initAll: initAll,
    swapSchema: function(elOrId, schema, value){ var h = getHidden(elOrId); if (h) swapSchema(h, schema, value); },
    setValue: function(elOrId, obj){ var h = getHidden(elOrId); if (!h || !h._ssf) return; writeHidden(h, obj || {}); },
    getValue: function(elOrId){ var h = getHidden(elOrId); try{ return JSON.parse(h.value || "{}"); } catch(e){ return {}; } },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();
