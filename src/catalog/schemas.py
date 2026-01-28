from __future__ import annotations
from typing import Tuple, Dict, Any
from .models import ItemType

def _default_for(spec: dict) -> Any:
    if "default" in spec:
        return spec["default"]
    t = spec.get("type")
    if t == "string":  return ""
    if t == "integer": return None
    if t == "number":  return None
    if t == "boolean": return False
    return None

def _coerce_type(val: Any, typ: str):
    if val is None: return None
    try:
        if typ == "string":  return str(val)
        if typ == "integer": return int(val)
        if typ == "number":  return float(val)
        if typ == "boolean":
            if isinstance(val, bool): return val
            s = str(val).strip().lower()
            if s in ("1","true","yes","y","t"): return True
            if s in ("0","false","no","n","f"): return False
            return bool(val)
    except Exception:
        return val
    return val

def validate_and_fill_attributes_for_type(item_type: ItemType, attrs: Dict[str,Any]) -> Tuple[Dict[str,list], Dict[str,Any]]:
    """
    Zwraca: (errors, attrs_filled)
    - errors: {"field": ["msg", ...], ...}
    - attrs_filled: uzupełnione o defaulty/konwersje typów
    """
    schema = getattr(item_type, "schema_json", None) or {}
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    errors: Dict[str, list] = {}
    out: Dict[str, Any] = {}

    # najpierw przepisz tylko pola zdefiniowane w properties
    for key, spec in props.items():
        raw = attrs.get(key, None)
        val = _coerce_type(raw, spec.get("type"))
        # enum
        if "enum" in spec and val is not None and val not in spec["enum"]:
            errors.setdefault(key, []).append(f"musi być jednym z: {', '.join(map(str, spec['enum']))}")
        # min/max
        if val is not None:
            if "minimum" in spec and isinstance(val, (int,float)) and val < spec["minimum"]:
                errors.setdefault(key, []).append(f"min {spec['minimum']}")
            if "maximum" in spec and isinstance(val, (int,float)) and val > spec["maximum"]:
                errors.setdefault(key, []).append(f"max {spec['maximum']}")
        # required
        if key in required and (val is None or val == "" or (isinstance(val, (list, dict)) and not val)):
            errors.setdefault(key, []).append("wymagane")
        # defaulty
        if (val is None or val == "") and key not in required:
            val = _default_for(spec)
        out[key] = val

    unknown = set(attrs.keys()) - set(props.keys())
    for u in unknown:
        errors.setdefault(u, []).append("nieznane pole (nie w schemacie)")

    return errors, out
