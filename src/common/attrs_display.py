from __future__ import annotations
import re
from typing import Dict, Any

# skróty / jednostki w etykietach wyciąganych z kluczy
TOKEN_UP = {
    "gb":"GB","tb":"TB","mb":"MB","hz":"Hz","khz":"kHz","mhz":"MHz","ghz":"GHz",
    "mah":"mAh","w":"W","kw":"kW","mp":"MP","db":"dB","mm":"mm","cm":"cm","m":"m",
    "lm":"lm","l":"L","ah":"Ah"
}

# polskie aliasy znanych kluczy
ALIASES = {
    "cpu":"CPU","gpu":"GPU","os":"System",
    "ram_gb":"Pamięć RAM","storage_gb":"Pamięć","ssd_gb":"Dysk SSD","hdd_gb":"Dysk HDD",
    "capacity_gb":"Pojemność","battery_mah":"Bateria","screen_inches":"Przekątna ekranu",
    "screen_refresh_hz":"Częstotliwość odświeżania","camera_mp":"Aparat",
    "five_g":"5G","dual_sim":"Dual SIM","power_w":"Moc",
    "length_cm":"Długość","width_cm":"Szerokość","height_cm":"Wysokość",
    "brightness_lm":"Jasność","case_diameter_mm":"Średnica koperty",
    "water_resistance_m":"Wodoszczelność","wheel_inches":"Rozmiar koła",
    "size_inches":"Przekątna","capacity_l":"Pojemność","battery_ah":"Bateria"
}

# domyślne jednostki po polsku
UNITS = {
    "ram_gb":"GB","storage_gb":"GB","ssd_gb":"GB","hdd_gb":"GB","capacity_gb":"GB",
    "battery_mah":"mAh","screen_inches":"cal","size_inches":"cal","wheel_inches":"cal",
    "screen_refresh_hz":"Hz","camera_mp":"MP","power_w":"W",
    "length_cm":"cm","width_cm":"cm","height_cm":"cm",
    "brightness_lm":"lm","case_diameter_mm":"mm","water_resistance_m":"m",
    "capacity_l":"L","battery_ah":"Ah","vram_gb":"GB","refresh_hz":"Hz",
}

def _label_from_key(key: str) -> str:
    parts = re.split(r"[_\s]+", key.strip())
    out = []
    for p in parts:
        up = TOKEN_UP.get(p.lower())
        if up: out.append(up)
        elif len(p) <= 3: out.append(p.upper())
        else: out.append(p.capitalize())
    return " ".join(out)

def pretty_label(key: str, ui_schema: dict|None = None) -> str:
    if ui_schema and isinstance(ui_schema, dict):
        lbl = (ui_schema.get("labels") or {}).get(key)
        if lbl: return lbl
    if key in ALIASES: return ALIASES[key]
    return _label_from_key(key)

def pretty_value(key: str, value: Any, ui_schema: dict|None = None) -> str:
    if value is None or value == "": return ""
    unit = None
    if ui_schema and isinstance(ui_schema, dict):
        unit = (ui_schema.get("units") or {}).get(key)
    if unit is None:
        unit = UNITS.get(key)
    if isinstance(value, bool):
        return "Tak" if value else "Nie"
    if isinstance(value, (int, float)) and unit:
        return f"{value} {unit}"
    return str(value)

def attrs_pairs(attrs: Dict[str,Any] | None, ui_schema: dict|None = None) -> list[tuple[str,str]]:
    if not attrs: return []
    order = None
    if ui_schema and isinstance(ui_schema, dict):
        order = ui_schema.get("order")
    keys = list(attrs.keys())
    if order:
        keys = [k for k in order if k in attrs] + [k for k in keys if k not in order]
    pairs = []
    for k in keys:
        v = pretty_value(k, attrs.get(k), ui_schema)
        if v != "":
            pairs.append((pretty_label(k, ui_schema), v))
    return pairs

def attrs_inline(attrs: Dict[str,Any] | None, ui_schema: dict|None = None) -> str:
    return " | ".join(f"{k}={v}" for k,v in attrs_pairs(attrs, ui_schema))
