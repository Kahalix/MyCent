window.app = window.app || {};

(function(){
  const TOKEN_UP = {
    gb:"GB", tb:"TB", mb:"MB",
    hz:"Hz", khz:"kHz", mhz:"MHz", ghz:"GHz",
    mah:"mAh", w:"W", kw:"kW", mp:"MP", db:"dB",
    mm:"mm", cm:"cm", m:"m", lm:"lm", l:"L", ah:"Ah"
  };

  const ALIASES = {
      brand:"Marka",
      model:"Model",
      cpu:"CPU", gpu:"GPU", os:"System",
      ram_gb:"Pamięć RAM", storage_gb:"Pamięć", ssd_gb:"Dysk SSD", hdd_gb:"Dysk HDD",
      capacity_gb:"Pojemność", battery_mah:"Bateria", battery_ah:"Bateria",
      screen_inches:"Przekątna ekranu", size_inches:"Przekątna",
      screen_refresh_hz:"Częstotliwość odświeżania", refresh_hz:"Częstotliwość odświeżania",
      camera_mp:"Aparat",
      five_g:"5G", dual_sim:"Dual SIM", power_w:"Moc",
      length_cm:"Długość", width_cm:"Szerokość", height_cm:"Wysokość",
      brightness_lm:"Jasność", case_diameter_mm:"Średnica koperty",
      water_resistance_m:"Wodoszczelność", wheel_inches:"Rozmiar koła",
      capacity_l:"Pojemność", vram_gb:"VRAM",
      channels:"Kanały", edition:"Edycja", waterproof:"Wodoodporność",
      mic:"Mikrofon", noise_cancelling:"Aktywna redukcja szumów (ANC)",
      smart_tv:"Smart TV", hdr:"HDR", panel:"Panel", resolution:"Rozdzielczość",
      mount:"Bagnet", ibis:"IBIS", stabilization:"Stabilizacja", throw_ratio:"Throw ratio",
      movement:"Mechanizm", focal_mm:"Ogniskowa", aperture:"Przysłona",
      frame_size:"Rozmiar ramy", speeds:"Biegi"
    };

  const UNITS = {
    ram_gb:"GB", storage_gb:"GB", ssd_gb:"GB", hdd_gb:"GB", capacity_gb:"GB", vram_gb:"GB",
    battery_mah:"mAh", battery_ah:"Ah",
    screen_inches:"cal", size_inches:"cal", wheel_inches:"cal",
    screen_refresh_hz:"Hz", refresh_hz:"Hz", camera_mp:"MP", power_w:"W",
    length_cm:"cm", width_cm:"cm", height_cm:"cm",
    brightness_lm:"lm", case_diameter_mm:"mm", water_resistance_m:"m",
    capacity_l:"L"
  };

  function labelFromKey(key){
    if (!key) return "";
    const parts = String(key).trim().split(/[_\s]+/);
    return parts.map(p=>{
      const up = TOKEN_UP[p.toLowerCase()]; if (up) return up;
//      if (p.length <= 3) return p.toUpperCase();
      return p[0].toUpperCase() + p.slice(1);
    }).join(" ");
  }

  function prettyLabel(key, ui){
    if (ui && ui.labels && ui.labels[key]) return ui.labels[key];
    if (ALIASES[key]) return ALIASES[key];
    return labelFromKey(key);
  }

  function prettyValue(key, val, ui){
    if (val === null || val === undefined || val === "") return "";
    const unit = (ui && ui.units && ui.units[key]) || UNITS[key] || null;
    if (typeof val === "boolean") return val ? "Tak" : "Nie";
    if (typeof val === "number" && unit) return `${val} ${unit}`;
    return String(val);
  }

  function attrsPairs(attrs, ui){
    attrs = attrs || {};
    const order = (ui && Array.isArray(ui.order)) ? ui.order : null;
    const keys = order
      ? order.filter(k => k in attrs).concat(Object.keys(attrs).filter(k => !order.includes(k)))
      : Object.keys(attrs);
    const out = [];
    for (const k of keys){
      const v = prettyValue(k, attrs[k], ui);
      if (v !== "") out.push([ prettyLabel(k, ui), v ]);
    }
    return out;
  }

  function attrsInline(attrs, ui){
    return attrsPairs(attrs, ui).map(([k,v]) => `${k}=${v}`).join(" | ");
  }

  window.app.attrLabel = prettyLabel;
  window.app.attrValue = prettyValue;
  window.app.attrPairs = attrsPairs;
  window.app.attrInline = attrsInline;
})();
