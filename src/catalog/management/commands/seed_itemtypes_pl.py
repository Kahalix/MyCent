from __future__ import annotations
from typing import Any, Dict, Tuple
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from djmoney.money import Money

from catalog.models import ItemType
from services.models import ListingPackage

# --- (lista kanonicznych pól ItemSet, których NIE wrzucamy do attributes) ---
ITEMSET_CANON_FIELDS = {
    # ogólne
    "set_name","description","price","stock_quantity","status","listing_type",
    "allow_online_checkout","added_by","seller_profile","owner_user","type","catalog_item",
    # kanoniczne z ItemSet
    "condition", "length_cm","width_cm","height_cm","weight_kg",
}

# ==== helpers ====
def leaf(schema: dict, ui: dict | None = None) -> dict:
    return {"schema": schema, "ui_schema": ui or {}}

def SCH_OBJECT(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}

def S(type_: str, **kw):  # skrót: string/number/integer/boolean
    return {"type": type_, **kw}

def UI(labels: dict[str,str] = None, order: list[str] = None, units: dict[str,str] = None, groups: dict[str,list[str]] = None) -> dict:
    out = {}
    if labels: out["labels"] = labels
    if order:  out["order"]  = order
    if units:  out["units"]  = units
    if groups: out["groups"] = groups
    return out

# ====== DRZEWO (po polsku) ======
TREE: Dict[str, Any] = {
    "Elektronika": {
        "Telefony": {
            "Smartfony": leaf(
                SCH_OBJECT({
                    "brand": S("string", minLength=1),
                    "model": S("string", minLength=1),
                    "os": S("string"),
                    "storage_gb": S("integer", minimum=4, maximum=2048),
                    "ram_gb": S("integer", minimum=1, maximum=64),
                    "screen_inches": S("number", minimum=3.5, maximum=8.5),
                    "screen_refresh_hz": S("integer", minimum=30, maximum=240),
                    "battery_mah": S("integer", minimum=500, maximum=20000),
                    "camera_mp": S("number", minimum=0.3, maximum=200),
                    "dual_sim": S("boolean"),
                    "five_g": S("boolean"),
                    "color": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"]),
                }, required=["brand","model"]),
                UI(
                    labels={
                        "brand":"Marka","model":"Model","os":"System",
                        "storage_gb":"Pamięć","ram_gb":"Pamięć RAM",
                        "screen_inches":"Przekątna ekranu","screen_refresh_hz":"Częstotliwość odświeżania",
                        "battery_mah":"Bateria","camera_mp":"Aparat",
                        "dual_sim":"Dual SIM","five_g":"5G","color":"Kolor","condition":"Stan"
                    },
                    units={"storage_gb":"GB","ram_gb":"GB","screen_inches":"cal","screen_refresh_hz":"Hz","battery_mah":"mAh","camera_mp":"MP"},
                    order=["brand","model","os","storage_gb","ram_gb","screen_inches","screen_refresh_hz","battery_mah","camera_mp","dual_sim","five_g","color","condition"]
                )
            ),
            "Telefony klasyczne": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "dual_sim": S("boolean"), "color": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","model"]),
                UI(labels={"dual_sim":"Dual SIM","condition":"Stan"})
            ),
            "Akcesoria": leaf(
                SCH_OBJECT({
                    "category": S("string", enum=["etui","ładowarka","kabel","słuchawki","powerbank","inne"]),
                    "brand": S("string"), "compatibility": S("string"), "color": S("string")
                }, required=["category"]),
                UI(labels={"category":"Rodzaj","compatibility":"Kompatybilność","color":"Kolor"})
            ),
        },

        "Komputery": {
            "Laptopy / Ultrabook": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "cpu": S("string"), "gpu": S("string"),
                    "ram_gb": S("integer", minimum=4, maximum=128),
                    "ssd_gb": S("integer", minimum=64, maximum=8192),
                    "screen_inches": S("number", minimum=10, maximum=18),
                    "screen_refresh_hz": S("integer", minimum=30, maximum=240),
                    "os": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"]),
                }, required=["brand","model","cpu","ram_gb","ssd_gb"]),
                UI(
                    labels={
                        "brand": "Marka",
                        "model": "Model",
                        "cpu": "CPU", "gpu": "GPU", "ram_gb": "Pamięć RAM", "ssd_gb": "Dysk SSD",
                        "screen_inches": "Przekątna ekranu", "screen_refresh_hz": "Częstotliwość odświeżania",
                        "os": "System", "condition": "Stan"
                    },
                    units={"ram_gb": "GB", "ssd_gb": "GB", "screen_inches": "cal", "screen_refresh_hz": "Hz"},
                    order=["brand", "model", "cpu", "gpu", "ram_gb", "ssd_gb", "screen_inches", "screen_refresh_hz",
                           "os", "condition"]
                )
            ),
            "Komponenty / Karty graficzne": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "chipset": S("string"),
                    "vram_gb": S("integer", minimum=1, maximum=48),
                    "length_mm": S("integer", minimum=100, maximum=400),
                    "power_w": S("integer", minimum=30, maximum=600),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","chipset"]),
                UI(labels={"chipset":"Chipset","vram_gb":"VRAM","length_mm":"Długość","power_w":"TDP","condition":"Stan"},
                   units={"vram_gb":"GB","length_mm":"mm","power_w":"W"})
            ),
            "Komponenty / Dyski SSD": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "capacity_gb": S("integer", minimum=64, maximum=16384),
                    "form_factor": S("string", enum=["2.5\"","M.2","mSATA","PCIe"]),
                    "interface": S("string", enum=["SATA","NVMe","PCIe"]),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","model","capacity_gb"]),
                UI(labels={"capacity_gb":"Pojemność","form_factor":"Format","interface":"Interfejs","condition":"Stan"},
                   units={"capacity_gb":"GB"})
            ),
            "Komputery stacjonarne": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "cpu": S("string"), "gpu": S("string"),
                    "ram_gb": S("integer", minimum=4, maximum=256),
                    "storage_gb": S("integer", minimum=64, maximum=16384),
                    "os": S("string"), "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["cpu","ram_gb"]),
                UI(labels={"ram_gb":"Pamięć RAM","storage_gb":"Dysk","os":"System","condition":"Stan"},
                   units={"ram_gb":"GB","storage_gb":"GB"})
            ),
        },

        "Audio": {
            "Słuchawki": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "type": S("string", enum=["dokanałowe","nauszne","wokółuszne"]),
                    "connection": S("string", enum=["przewodowe","bluetooth","true-wireless"]),
                    "mic": S("boolean"), "noise_cancelling": S("boolean"),
                    "color": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","model"]),
                UI(labels={"type":"Typ","connection":"Połączenie","mic":"Mikrofon","noise_cancelling":"Aktywna redukcja szumów (ANC)","color":"Kolor","condition":"Stan"})
            ),
            "Głośniki Bluetooth": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "power_w": S("integer", minimum=1, maximum=500),
                    "waterproof": S("boolean"),
                    "battery_mah": S("integer", minimum=500, maximum=30000),
                    "color": S("string")
                }, required=["brand","model"]),
                UI(labels={"power_w":"Moc","battery_mah":"Bateria","waterproof":"Wodoodporność","color":"Kolor"},
                   units={"power_w":"W","battery_mah":"mAh"})
            ),
            "Soundbary": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "channels": S("string"),  # np. "2.1", "5.1"
                    "power_w": S("integer", minimum=10, maximum=1000),
                    "dolby_atmos": S("boolean"),
                }, required=["brand","model"]),
                UI(labels={"channels":"Kanały","power_w":"Moc","dolby_atmos":"Dolby Atmos"}, units={"power_w":"W"})
            ),
        },

        "TV i wideo": {
            "Telewizory": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "size_inches": S("integer", minimum=19, maximum=110),
                    "panel": S("string", enum=["LED","QLED","OLED","MiniLED"]),
                    "resolution": S("string", enum=["HD","Full HD","4K","8K"]),
                    "smart_tv": S("boolean"),
                    "hdr": S("boolean"),
                    "refresh_hz": S("integer", minimum=50, maximum=240),
                }, required=["brand","model","size_inches"]),
                UI(
                    labels={
                        "size_inches":"Przekątna","panel":"Panel","resolution":"Rozdzielczość",
                        "smart_tv":"Smart TV","hdr":"HDR","refresh_hz":"Częstotliwość odświeżania"
                    },
                    units={"size_inches":"cal","refresh_hz":"Hz"}
                )
            ),
            "Projektory": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "brightness_lm": S("integer", minimum=200, maximum=10000),
                    "resolution": S("string"),
                    "throw_ratio": S("string"),
                }, required=["brand","model"]),
                UI(labels={"brightness_lm":"Jasność","throw_ratio":"Throw ratio"}, units={"brightness_lm":"lm"})
            ),
        },

        "Foto": {
            "Lustrzanki": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "sensor_mp": S("number", minimum=6, maximum=100),
                    "mount": S("string"),
                    "video_resolution": S("string"),
                    "stabilization": S("boolean")
                }, required=["brand","model"]),
                UI(labels={"sensor_mp":"Matryca","mount":"Bagnet","video_resolution":"Wideo","stabilization":"Stabilizacja"},
                   units={"sensor_mp":"MP"})
            ),
            "Bezlusterkowce": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "sensor_mp": S("number", minimum=6, maximum=100),
                    "mount": S("string"),
                    "ibis": S("boolean"),
                }, required=["brand","model"]),
                UI(labels={"sensor_mp":"Matryca","mount":"Bagnet","ibis":"IBIS"}, units={"sensor_mp":"MP"})
            ),
            "Obiektywy": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "mount": S("string"),
                    "focal_mm": S("string"),  # "24-70", "50"
                    "aperture": S("string"),  # "f/1.8", "f/2.8"
                    "stabilization": S("boolean")
                }, required=["brand","mount","focal_mm"]),
                UI(labels={"focal_mm":"Ogniskowa","aperture":"Przysłona","stabilization":"Stabilizacja"})
            ),
        },

        "Konsole i gry": {
            "Konsole": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "storage_gb": S("integer", minimum=64, maximum=2048),
                    "edition": S("string"), "color": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","model"]),
                UI(labels={"storage_gb":"Pamięć","edition":"Edycja","color":"Kolor","condition":"Stan"}, units={"storage_gb":"GB"})
            ),
            "Gry": leaf(
                SCH_OBJECT({
                    "title": S("string"),
                    "platform": S("string", enum=["PS5","PS4","Xbox","Switch","PC"]),
                    "edition": S("string"), "region": S("string")
                }, required=["title","platform"]),
                UI(labels={"title":"Tytuł","platform":"Platforma","edition":"Edycja","region":"Region"})
            )
        },
    },

    "Dom i Ogród": {
        "Meble": {
            "Krzesła": leaf(
                SCH_OBJECT({
                    "material": S("string"), "color": S("string"),
                    "width_cm": S("integer", minimum=20, maximum=200),
                    "depth_cm": S("integer", minimum=20, maximum=200),
                    "height_cm": S("integer", minimum=20, maximum=200),
                }),
                UI(labels={"material":"Materiał","color":"Kolor","width_cm":"Szerokość","depth_cm":"Głębokość","height_cm":"Wysokość"},
                   units={"width_cm":"cm","depth_cm":"cm","height_cm":"cm"})
            ),
            "Stoły": leaf(
                SCH_OBJECT({
                    "material": S("string"), "color": S("string"),
                    "length_cm": S("integer", minimum=40, maximum=400),
                    "width_cm": S("integer", minimum=40, maximum=200),
                    "height_cm": S("integer", minimum=40, maximum=120),
                }),
                UI(labels={"material":"Materiał","color":"Kolor","length_cm":"Długość","width_cm":"Szerokość","height_cm":"Wysokość"},
                   units={"length_cm":"cm","width_cm":"cm","height_cm":"cm"})
            ),
        },
        "AGD": {
            "Odkurzacze": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "type": S("string", enum=["pionowy","tradycyjny","ręczny","robot"]),
                    "power_w": S("integer", minimum=100, maximum=2500),
                    "bagless": S("boolean")
                }, required=["brand","model"]),
                UI(labels={"type":"Typ","power_w":"Moc","bagless":"Bezworkowy"}, units={"power_w":"W"})
            ),
            "Mikrofalówki": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "capacity_l": S("integer", minimum=10, maximum=50),
                    "power_w": S("integer", minimum=500, maximum=2000),
                    "grill": S("boolean"),
                }, required=["brand","model"]),
                UI(labels={"capacity_l":"Pojemność","power_w":"Moc","grill":"Grill"}, units={"capacity_l":"L","power_w":"W"})
            ),
        },
        "Narzędzia": {
            "Wiertarki": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "power_w": S("integer", minimum=100, maximum=2000),
                    "hammer": S("boolean"),
                    "cordless": S("boolean"),
                    "battery_ah": S("number", minimum=0.5, maximum=12.0)
                }, required=["brand","model"]),
                UI(labels={"power_w":"Moc","hammer":"Udar","cordless":"Akumulatorowa","battery_ah":"Bateria"},
                   units={"power_w":"W","battery_ah":"Ah"})
            ),
        },
    },

    "Moda": {
        "Obuwie męskie": {
            "Sneakersy": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "size_eu": S("number", minimum=34, maximum=52),
                    "color": S("string"), "material": S("string"),
                    "condition": S("string", enum=["NOWY","JAK_NOWY","UŻYWANY","ZUŻYTY"])
                }, required=["brand","size_eu"]),
                UI(labels={"size_eu":"Rozmiar (EU)","color":"Kolor","material":"Materiał","condition":"Stan"})
            ),
        },
        "Torebki damskie": {
            "Torebki": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "material": S("string"), "color": S("string")
                }, required=["brand"]),
                UI(labels={"brand":"Marka","model":"Model","material":"Materiał","color":"Kolor"})
            )
        }
    },

    "Biżuteria i zegarki": {
        "Pierścionki": {
            "Złote pierścionki": leaf(
                SCH_OBJECT({
                    "gold_purity": S("string", enum=["333","375","585","750","916"]),
                    "weight_grams": S("number", minimum=0.1, maximum=200.0),
                    "size": S("string"), "stone": S("string")
                }, required=["gold_purity","weight_grams"]),
                UI(labels={"gold_purity":"Próba złota","weight_grams":"Waga","size":"Rozmiar","stone":"Kamień"},
                   units={"weight_grams":"g"})
            ),
        },
        "Zegarki": {
            "Zegarki naręczne": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "movement": S("string", enum=["kwarcowy","automatyczny","mechaniczny","smart"]),
                    "case_diameter_mm": S("integer", minimum=20, maximum=60),
                    "water_resistance_m": S("integer", minimum=0, maximum=1000)
                }, required=["brand"]),
                UI(labels={"movement":"Mechanizm","case_diameter_mm":"Średnica koperty","water_resistance_m":"Wodoszczelność"},
                   units={"case_diameter_mm":"mm","water_resistance_m":"m"})
            )
        }
    },

    "Sport i turystyka": {
        "Rowery": {
            "MTB": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "frame_size": S("string"),
                    "wheel_inches": S("integer", minimum=20, maximum=29),
                    "speeds": S("integer", minimum=1, maximum=30)
                }, required=["brand"]),
                UI(labels={"frame_size":"Rozmiar ramy","wheel_inches":"Rozmiar koła","speeds":"Biegi"},
                   units={"wheel_inches":"cal"})
            )
        }
    },

    "Instrumenty": {
        "Gitary": {
            "Gitara elektryczna": leaf(
                SCH_OBJECT({
                    "brand": S("string"), "model": S("string"),
                    "body": S("string"), "fingerboard": S("string"),
                    "pickup_config": S("string")  # HSS/HH/SSS...
                }, required=["brand","model"]),
                UI(labels={"body":"Korpus","fingerboard":"Podstrunnica","pickup_config":"Przetworniki"})
            )
        }
    },
}

# ====== Pakiety ======
FREE_PACK_PATHS = [
    "Elektronika/Telefony/Smartfony",
    "Elektronika/Komputery/Laptopy / Ultrabook",
    "Biżuteria i zegarki/Pierścionki/Złote pierścionki",
]

PAID_PACKS = [
    # (path, listings_free, price_amount, points)
    ("Elektronika/Telefony/Smartfony", 3,  Money(29.99, "PLN"), 30),
    ("Elektronika/Komputery/Laptopy / Ultrabook", 3, Money(39.99, "PLN"), 30),
    ("Biżuteria i zegarki/Pierścionki/Złote pierścionki", 3, Money(24.99, "PLN"), 30),
]

# ====== implementacja seeda ======
def _upsert_type(name: str, parent: ItemType|None) -> ItemType:
    obj = ItemType.objects.filter(name=name, parent=parent).first()
    if not obj:
        obj = ItemType(name=name, parent=parent)
        obj.save()
    return obj

def _sanitize_schema(schema: dict, ui: dict | None) -> tuple[dict, dict]:
    """Usuwa z JSON Schema i UI-schema wszystkie pola, które istnieją już w ItemSet."""
    schema = dict(schema or {})
    ui = dict(ui or {})
    props = dict((schema.get("properties") or {}))

    # odfiltruj properties
    props = {k:v for k,v in props.items() if k not in ITEMSET_CANON_FIELDS}
    schema["properties"] = props

    # required
    req = list(schema.get("required") or [])
    schema["required"] = [k for k in req if k in props]

    # ui.labels / ui.units / ui.order / ui.groups
    labels = dict((ui.get("labels") or {}))
    ui["labels"] = {k:v for k,v in labels.items() if k in props}
    units  = dict((ui.get("units") or {}))
    ui["units"]  = {k:v for k,v in units.items() if k in props}
    order = list(ui.get("order") or [])
    ui["order"]  = [k for k in order if k in props]
    groups = dict((ui.get("groups") or {}))
    ui["groups"] = {g:[k for k in ks if k in props] for g,ks in groups.items()}

    return schema, ui

# --- ustawianie schema na liściu ---
def _apply_leaf_payload(obj: ItemType, node: dict):
    raw_schema = node.get("schema") or {}
    raw_ui = node.get("ui_schema") or {}
    schema, ui = _sanitize_schema(raw_schema, raw_ui)

    changed = False
    if obj.schema_json != schema:
        obj.schema_json = schema; changed = True
    if obj.ui_schema_json != ui:
        obj.ui_schema_json = ui; changed = True
    if changed:
        obj.save(update_fields=["schema_json","ui_schema_json","updated_at"])

def _walk(parent: ItemType|None, subtree: dict):
    for name, node in subtree.items():
        it = _upsert_type(name, parent)
        kids = {k:v for k,v in (node if isinstance(node, dict) else {}).items() if k not in ("schema","ui_schema")}
        if kids:
            if it.schema_json or it.ui_schema_json:
                it.schema_json = {}; it.ui_schema_json = {}; it.save(update_fields=["schema_json","ui_schema_json"])
            _walk(it, kids)
        else:
            _apply_leaf_payload(it, node)

def _get_type_by_path(path: str) -> ItemType | None:
    cur = None
    for piece in path.split("/"):
        cur = ItemType.objects.filter(name=piece, parent=cur).first()
        if not cur: return None
    return cur

from django.db.models import Q

def _get_or_create_pkg(it: ItemType, listings_free: int = 0, price = None, points: int = 0) -> ListingPackage:
    qs = ListingPackage.objects.filter(item_type=it, listings_free=listings_free, points=points)
    if price is None:
        qs = qs.filter(Q(price__isnull=True) | Q(price=0))
    else:
        qs = qs.filter(price=price.amount, price_currency=str(price.currency))

    pkg = qs.first()
    if not pkg:
        pkg = ListingPackage.objects.create(item_type=it, listings_free=listings_free, price=price, points=points)
    return pkg

class Command(BaseCommand):
    help = "Seed: rozbudowane ItemType (po polsku) + UI-schema; do tego przykładowe ListingPackage i wypisanie public_id pakietów FREE."

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write("Seeduję kategorie (ItemType)…")
        for root_name, subtree in TREE.items():
            root = _upsert_type(root_name, None)
            _walk(root, subtree)
        self.stdout.write(self.style.SUCCESS("ItemType OK."))

        self.stdout.write("Seeduję ListingPackage…")
        free_ids = []
        for p in FREE_PACK_PATHS:
            it = _get_type_by_path(p)
            if not it:
                self.stdout.write(self.style.WARNING(f"Brak kategorii (FREE): {p}")); continue
            pkg = _get_or_create_pkg(it, listings_free=5, price=None, points=0)
            free_ids.append(pkg.public_id)
            self.stdout.write(f"FREE {it.path} -> {pkg.public_id}")

        for (p, free_n, price, pts) in PAID_PACKS:
            it = _get_type_by_path(p)
            if not it:
                self.stdout.write(self.style.WARNING(f"Brak kategorii (PAID): {p}")); continue
            pkg = _get_or_create_pkg(it, listings_free=free_n, price=price, points=pts)
            self.stdout.write(f"PAID {it.path} -> {pkg.public_id} cena={pkg.price}")

        self.stdout.write(self.style.SUCCESS("Packages OK."))
        self.stdout.write(self.style.SUCCESS(
            f"\nWklej do settings.py (SERVICES_SIGNUP_FREE_PACKAGE_PUBLIC_IDS):\n{free_ids}\n"
        ))
