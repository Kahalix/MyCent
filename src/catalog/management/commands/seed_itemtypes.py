# src/catalog/management/commands/seed_itemtypes.py
from __future__ import annotations
from typing import Any, Dict
from django.core.management.base import BaseCommand
from django.db import transaction
from catalog.models import ItemType

# Proste drzewo (przykładowe) – schematy wyłącznie na liściach
TREE: Dict[str, Any] = {
    "Elektronika": {
        "Telefony": {
            "Smartfony": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "brand": {"type": "string", "minLength": 1},
                        "model": {"type": "string", "minLength": 1},
                        "storage_gb": {"type": "integer", "minimum": 4, "maximum": 2048},
                        "ram_gb": {"type": "integer", "minimum": 1, "maximum": 64},
                        "color": {"type": "string"},
                        "dual_sim": {"type": "boolean"},
                        "screen_inches": {"type": "number", "minimum": 3.0, "maximum": 8.5}
                    },
                    "required": ["brand","model"]
                },
                "ui_schema": {
                    "order": ["brand", "model", "storage_gb", "ram_gb", "screen_inches", "color", "dual_sim"]
                }
            },
            "Akcesoria do telefonów": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "category": {"type":"string", "enum":["case","charger","cable","earphones","other"]},
                        "brand": {"type":"string"},
                        "compatibility": {"type":"string"}
                    },
                    "required": ["category"]
                },
                "ui_schema": {"order": ["category","brand","compatibility"]}
            }
        },
        "Laptopy": {
            "Ultrabook": {
                "schema": {
                    "type":"object",
                    "properties": {
                        "brand": {"type":"string"},
                        "model": {"type":"string"},
                        "cpu": {"type":"string"},
                        "ram_gb": {"type":"integer","minimum":4,"maximum":128},
                        "ssd_gb": {"type":"integer","minimum":64,"maximum":8192},
                        "screen_inches": {"type":"number","minimum":10,"maximum":18},
                        "gpu": {"type":"string"}
                    },
                    "required": ["brand","model","cpu","ram_gb","ssd_gb"]
                },
                "ui_schema": {"order":["brand","model","cpu","ram_gb","ssd_gb","gpu","screen_inches"]}
            }
        }
    },
    "Dom i Ogród": {
        "Meble": {
            "Krzesła": {
                "schema": {
                    "type":"object",
                    "properties": {
                        "material": {"type":"string"},
                        "color": {"type":"string"},
                        "width_cm": {"type":"integer","minimum":20,"maximum":200},
                        "depth_cm": {"type":"integer","minimum":20,"maximum":200},
                        "height_cm": {"type":"integer","minimum":20,"maximum":200},
                    }
                },
                "ui_schema": {"order":["material","color","width_cm","depth_cm","height_cm"]}
            }
        }
    },
    "Moda": {
        "Obuwie męskie": {
            "Sneakersy": {
                "schema": {
                    "type":"object",
                    "properties": {
                        "brand": {"type":"string"},
                        "size_eu": {"type":"number","minimum":34,"maximum":52},
                        "color": {"type":"string"},
                        "material": {"type":"string"}
                    },
                    "required": ["brand","size_eu"]
                }
            }
        }
    },
    "Biżuteria": {
        "Pierścionki": {
            "Złote pierścionki": {
                "schema": {
                    "type":"object",
                    "properties": {
                        "gold_purity": {"type":"string","enum":["333","375","585","750","916"]},
                        "weight_grams": {"type":"number","minimum":0.1,"maximum":200.0},
                        "size": {"type":"string"}
                    },
                    "required": ["gold_purity","weight_grams"]
                }
            }
        }
    }
}


class Command(BaseCommand):
    help = "Seeds ItemType tree with JSON Schemas on leaf nodes."

    def handle(self, *args, **options):
        with transaction.atomic():
            created, updated = 0, 0

            def upsert(name: str, parent: ItemType|None, node: Any) -> ItemType:
                obj = ItemType.objects.filter(name=name, parent=parent).first()
                if not obj:
                    obj = ItemType(name=name, parent=parent)
                    obj.save()
                    nonlocal created; created += 1
                else:
                    nonlocal updated; updated += 1
                # jeśli node jest dict i zawiera poddrzewo
                if isinstance(node, dict):
                    schema = node.get("schema")
                    ui = node.get("ui_schema", {})
                    # „dzieci” to wszystkie klucze oprócz schema/ui_schema
                    kids = {k:v for k,v in node.items() if k not in ("schema","ui_schema")}
                    if kids:
                        # to nie liść – wyczyść schemat dla pewności
                        if (obj.schema_json or obj.ui_schema_json):
                            obj.schema_json, obj.ui_schema_json = {}, {}
                            obj.save(update_fields=["schema_json","ui_schema_json"])
                        for child_name, child_node in kids.items():
                            upsert(child_name, obj, child_node)
                    else:
                        # liść – ustaw schema
                        if schema is not None:
                            obj.schema_json = schema
                            obj.ui_schema_json = ui or {}
                            obj.save(update_fields=["schema_json","ui_schema_json"])
                return obj

            for root, subtree in TREE.items():
                upsert(root, None, subtree)

            self.stdout.write(self.style.SUCCESS(f"Seed finished. created={created}, updated={updated}"))
