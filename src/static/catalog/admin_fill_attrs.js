(function () {
  var $ = (window.django && window.django.jQuery) || window.jQuery;

  function jsonParse(s){ try { return JSON.parse(s); } catch(e){ return null; } }
  async function fetchJSON(url){
    try{ var r = await fetch(url, { credentials: "same-origin" }); return r.ok ? r.json() : null; }
    catch(e){ return null; }
  }
  function normalizeSchema(schema){
    var s = schema || {};
    if (typeof s !== "object" || Array.isArray(s)) return { type:"object", properties:{} };
    if (!s.type) {
      if (s.properties) s = { type:"object", properties:s.properties };
      else if (s.items)  s = { type:"array",  items:s.items };
      else s = { type:"object", properties:{} };
    }
    if (s.type === "object" && !s.properties) s.properties = {};
    return s;
  }
  function skeletonFrom(schema){
    var S = normalizeSchema(schema), props = S.properties || {}, out = {};
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

  // lock/unlock TYPE overlay
  function ensureLockStyles(){
    if (document.getElementById("ssf-lock-style")) return;
    var css = ".ssf-lock-wrap{position:relative}"+
              ".ssf-lock-overlay{position:absolute;inset:0;z-index:2;background:rgba(0,0,0,.06)}";
    var st = document.createElement("style"); st.id="ssf-lock-style"; st.textContent=css; document.head.appendChild(st);
  }
  function lockSelect2(el, locked){
    if (!el) return;
    ensureLockStyles();
    var row = (el.closest(".form-row")||el.closest(".field-type")||el.parentNode); if (!row) return;
    row.classList.add("ssf-lock-wrap");
    var overlay = row.querySelector(".ssf-lock-overlay");
    if (locked){
      if (!overlay){ overlay = document.createElement("div"); overlay.className = "ssf-lock-overlay"; row.appendChild(overlay); }
      if ($) $(el).on("select2:opening.ssflock", function(e){ e.preventDefault(); });
      el.dataset.locked="1";
    } else {
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if ($) $(el).off("select2:opening.ssflock");
      el.dataset.locked="";
    }
  }
  function setSelect2Value(el, id, text){
    if (!el) return;
    var val = String(id), found = false;
    for (var i=0;i<el.options.length;i++) if (String(el.options[i].value)===val){ found=true; break; }
    if (!found){ var opt = new Option(text||val, val, true, true); el.add(opt); } else { el.value = val; }
    if ($) $(el).trigger("change"); else el.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function attrInput(){ return document.getElementById("id_attributes"); }

  // ===== CatalogItem admin =====
  async function onTypeChanged_CatalogItem(){
    var typeSel = document.getElementById("id_type");
    var hidden  = attrInput();
    if (!typeSel || !hidden) return;

    if (!typeSel.value){
      SSF.swapSchema(hidden, {type:"object",properties:{}}, {});
      return;
    }
    var data = await fetchJSON("/admin/catalog/itemtype/schema/" + encodeURIComponent(typeSel.value) + "/");
    if (!data || !data.is_leaf) return;

    var schema = normalizeSchema(data.schema || {});
    var current = jsonParse(hidden.value) || {};
    var merged  = Object.keys(current).length ? reconcileAttrs(current, schema) : skeletonFrom(schema);
    SSF.swapSchema(hidden, schema, merged);
  }

  function initCatalogItemAdmin(){
    var typeSel = document.getElementById("id_type");
    if (!typeSel) return;
    if ($){ $(typeSel).on("select2:select", onTypeChanged_CatalogItem); $(typeSel).on("select2:clear", onTypeChanged_CatalogItem); }
    typeSel.addEventListener("change", onTypeChanged_CatalogItem);
    // init
    if (typeSel.value) onTypeChanged_CatalogItem();
  }

  // ===== ItemSet admin =====
  async function onCatalogItemSelected_ItemSet(){
    var catSel  = document.getElementById("id_catalog_item");
    var typeSel = document.getElementById("id_type");
    var hidden  = attrInput();
    if (!catSel || !typeSel || !hidden) return;

    var id = catSel.value;
    if (!id){
      // odblokuj TYPE i przeładuj schema z TYPE
      lockSelect2(typeSel, false);
      await onTypeChanged_ItemSet();
      return;
    }

    var data = await fetchJSON("/admin/catalog/catalogitem/attrs/" + encodeURIComponent(id) + "/");
    if (!data) return;

    if (data.type_id){
      setSelect2Value(typeSel, data.type_id, data.type_path || data.type_id);
      lockSelect2(typeSel, true);

      var t = await fetchJSON("/admin/catalog/itemtype/schema/" + encodeURIComponent(data.type_id) + "/");
      var schema = normalizeSchema((t && t.schema) || {});
      var attrs  = data.attributes || {};
      var merged = reconcileAttrs(attrs, schema);
      SSF.swapSchema(hidden, schema, merged);
    }
  }

  async function onTypeChanged_ItemSet(){
    var catSel  = document.getElementById("id_catalog_item");
    var typeSel = document.getElementById("id_type");
    var hidden  = attrInput();
    if (!typeSel || !hidden) return;
    if (catSel && catSel.value) return; // steruje katalog

    if (!typeSel.value){
      SSF.swapSchema(hidden, {type:"object",properties:{}}, {});
      return;
    }
    var data = await fetchJSON("/admin/catalog/itemtype/schema/" + encodeURIComponent(typeSel.value) + "/");
    if (!data || !data.is_leaf) return;

    var schema  = normalizeSchema(data.schema || {});
    var current = jsonParse(hidden.value) || {};
    var merged  = Object.keys(current).length ? reconcileAttrs(current, schema) : skeletonFrom(schema);
    SSF.swapSchema(hidden, schema, merged);
  }

  function bindSelect2(el, handler){
    if (!el) return;
    if ($){ $(el).on("select2:select", handler); $(el).on("select2:clear", handler); }
    el.addEventListener("change", handler);
  }

  function initItemSetAdmin(){
    var typeSel = document.getElementById("id_type");
    var catSel  = document.getElementById("id_catalog_item");
    if (typeSel) bindSelect2(typeSel, onTypeChanged_ItemSet);
    if (catSel)  bindSelect2(catSel,  onCatalogItemSelected_ItemSet);

    // init stanu
    if (catSel && catSel.value) onCatalogItemSelected_ItemSet();
    else if (typeSel && typeSel.value) onTypeChanged_ItemSet();
    else SSF.swapSchema(attrInput(), {type:"object",properties:{}}, {});
  }

  function ready(fn){ if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn); else fn(); }
  ready(function(){
    if (document.getElementById("id_item_name")) initCatalogItemAdmin(); // CatalogItem
    if (document.getElementById("id_set_name"))  initItemSetAdmin();     // ItemSet
  });
})();
