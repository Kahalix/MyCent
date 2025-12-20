# from __future__ import annotations
# import csv
# import io
# from pawns.models import Pawn
#
# def _build_csv_bytes(rows: list[list[str]]) -> bytes:
#     out = io.StringIO(newline="")
#     w = csv.writer(out)
#     for r in rows:
#         w.writerow(r)
#     return out.getvalue().encode("utf-8-sig")  # BOM dla Excela
#
# def pawn_csv_row(p: Pawn) -> list[str]:
#     full_name = (p.customer_snapshot.get("first_name","") + " " + p.customer_snapshot.get("last_name","")).strip()
#     return [
#         p.public_id, p.status, str(p.principal), str(p.appraisal_total),
#         str(p.start_date), str(p.due_date), full_name,
#     ]
#
# def export_pawns_csv(pawns) -> bytes:
#     rows = [["public_id","status","principal","appraisal_total","start_date","due_date","customer"]]
#     for p in pawns:
#         rows.append(pawn_csv_row(p))
#     return _build_csv_bytes(rows)
