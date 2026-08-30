#!/usr/bin/env python3
"""Stage B: JSON + CSV -> Neo4j exports.

Reads *_expParams.json (Stage A output) from X:\\peakFit\\ and builds:
  exports/nodes.csv           -- neo4j-admin import (primary ingestion)
  exports/relationships.csv   -- neo4j-admin import (primary ingestion)
  exports/graph.cypher        -- MERGE statements (backup / audit)
  exports/schema.arrows.json  -- schema diagram for arrows.app

Also regenerates review/missing_values_review.txt.

Hard-stops (see §5, §7, §10 of instructions.txt):
  * More than 2 distinct Material keys
  * is_new is null on any Filename  (chain-break ambiguous)
  * mass_g differs within a KineticChain

Does NOT connect to a Neo4j instance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PEAKFIT_ROOT = Path(r"X:\peakFit")
EXPORTS_DIR  = Path(r"X:\graphDB\exports")
REVIEW_FILE  = Path(r"X:\graphDB\review\missing_values_review.txt")

EXCL_FOLDER  = "_test"
EXCL_BASE    = "iso"

EXPECTED_MATERIAL_COUNT = 2

# CSV column -> Neo4j property name  (monomer_sum row of *_CarbonylPeakArea.csv)
ADS_MAP: dict[str, str] = {
    "Time (s)":             "time_s",
    "pfo-sec_r^2":          "pfo_sec_r2",
    "pfo-sec_rmse":         "pfo_sec_rmse",
    "pfo-sec_k_a_s-1":      "pfo_sec_k_a",
    "pfo-sec_k_a_stderr":   "pfo_sec_k_a_stderr",
    "pfo-sec_q_e_au":       "pfo_sec_q_e",
    "pfo-sec_q_e_stderr":   "pfo_sec_q_e_stderr",
    "pfo-sec_k_s_s-1":      "pfo_sec_k_s",
    "pfo-sec_k_s_stderr":   "pfo_sec_k_s_stderr",
    "pfo-sec_k_p_s-1":      "pfo_sec_k_p",
    "pfo-sec_k_p_stderr":   "pfo_sec_k_p_stderr",
    "pfo-sec_q_inf_au":     "pfo_sec_q_inf",
    "pfo-sec_q_inf_stderr": "pfo_sec_q_inf_stderr",
    "pfo-sec_q0_au":        "pfo_sec_q0",
}

# (csv_header_with_type_hint, dict_key)  for flat nodes.csv
# Columns are ordered: Material, Filename, shared Pretreatment/ExpConditions,
# AdsParams, KineticChain.  Empty cells are null in neo4j-admin import.
NODE_PROP_COLS: list[tuple[str, str]] = [
    # Material
    ("metal:String",               "metal"),
    ("metal_loading:Float",        "metal_loading"),
    ("support:String",             "support"),
    ("support_sa:Float",           "support_sa"),
    ("notebook:String",            "notebook"),
    ("mfldVol:Float",              "mfldVol"),
    # Filename
    ("base_name:String",           "base_name"),
    ("datetime:String",            "datetime"),
    ("exp_type:String",            "exp_type"),
    ("is_new:Boolean",             "is_new"),
    ("is_reference:Boolean",       "is_reference"),
    ("exp_success:Boolean",        "exp_success"),
    ("has_csv:Boolean",            "has_csv"),
    # Pretreatment / ExpConditions (shared columns)
    ("id:String",                  "id"),
    ("step_index:Int",             "step_index"),
    ("gas:String[]",               "gas"),
    ("pressure_meas_g1:Float",     "pressure_meas_g1"),
    ("pressure_meas_g2:Float",     "pressure_meas_g2"),
    ("pressure_calc:Float[]",      "pressure_calc"),
    ("temp:Float",                 "temp"),
    ("rate:Float",                 "rate"),
    ("duration:Float",             "duration"),
    ("chiller:Boolean",            "chiller"),
    # AdsParams
    ("peak_name:String",           "peak_name"),
    ("time_s:Float",               "time_s"),
    ("pfo_sec_r2:Float",           "pfo_sec_r2"),
    ("pfo_sec_rmse:Float",         "pfo_sec_rmse"),
    ("pfo_sec_k_a:Float",          "pfo_sec_k_a"),
    ("pfo_sec_k_a_stderr:Float",   "pfo_sec_k_a_stderr"),
    ("pfo_sec_q_e:Float",          "pfo_sec_q_e"),
    ("pfo_sec_q_e_stderr:Float",   "pfo_sec_q_e_stderr"),
    ("pfo_sec_k_s:Float",          "pfo_sec_k_s"),
    ("pfo_sec_k_s_stderr:Float",   "pfo_sec_k_s_stderr"),
    ("pfo_sec_k_p:Float",          "pfo_sec_k_p"),
    ("pfo_sec_k_p_stderr:Float",   "pfo_sec_k_p_stderr"),
    ("pfo_sec_q_inf:Float",        "pfo_sec_q_inf"),
    ("pfo_sec_q_inf_stderr:Float", "pfo_sec_q_inf_stderr"),
    ("pfo_sec_q0:Float",           "pfo_sec_q0"),
    # KineticChain
    ("chain_id:String",            "chain_id"),
    ("material_key:String",        "material_key"),
    ("started_at:String",          "started_at"),
    ("length:Int",                 "length"),
    ("mass_g:Float",               "mass_g"),
]


# ---- ID helpers -------------------------------------------------------------

def _mat_key(m: dict) -> str:
    return f"{m['metal']}|{m['metal_loading']}|{m['support']}|{m['support_sa']}"


def _chain_hash(mat_key: str, started_at: str) -> str:
    return hashlib.md5(f"{mat_key}|{started_at}".encode()).hexdigest()[:12]


def _id_mat(m: dict) -> str:
    safe = _mat_key(m).replace("|", "_").replace(".", "p")
    return f"mat_{safe}"


def _id_fn(base: str) -> str:
    return f"fn_{base}"


def _id_pre(base: str, idx: int) -> str:
    return f"pre_{base}_{idx}"


def _id_ec(base: str) -> str:
    return f"ec_{base}"


def _id_ap(base: str, peak_name: str = "monomer_sum") -> str:
    return f"ap_{base}_{peak_name}"


def _id_kc(cid: str) -> str:
    return f"kc_{cid}"


# ---- data loading -----------------------------------------------------------

def discover_jsons() -> list[Path]:
    out: list[Path] = []
    for sub in sorted(p for p in PEAKFIT_ROOT.iterdir() if p.is_dir()):
        if EXCL_FOLDER in sub.name:
            continue
        for jp in sorted(sub.glob("*_expParams.json")):
            if EXCL_BASE in jp.name.lower():
                continue
            out.append(jp)
    return out


def _to_float(s: str) -> float | str:
    try:
        return float(s)
    except ValueError:
        return s


def load_adsparams(base: str, folder: Path) -> dict[str, dict] | None:
    """Return {peak_name: props} from the CSV, one entry per Peak_Name group.

    Picks the row with max Time (s) per group.
    For v1, only 'monomer_sum' rows are included; relax the filter here for
    future peaks (cluster_sum, Peak_1975, etc.) without schema changes.
    Returns None if the CSV is absent or has no matching rows.
    """
    csv_path = folder / f"{base}_CarbonylPeakArea.csv"
    if not csv_path.exists():
        return None
    best: dict[str, tuple[float, dict]] = {}  # peak_name -> (max_t, row)
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            peak = row.get("Peak_Name", "")
            if peak != "monomer_sum":  # v1 filter
                continue
            try:
                t = float(row["Time (s)"])
            except (ValueError, KeyError):
                continue
            if peak not in best or t > best[peak][0]:
                best[peak] = (t, row)
    if not best:
        return None
    return {
        peak: {
            prop: (None if (v := row.get(col, "").strip()) == "" else _to_float(v))
            for col, prop in ADS_MAP.items()
        }
        for peak, (_, row) in best.items()
    }


# ---- kinetic chain building -------------------------------------------------

def build_chains(exps: list[dict]) -> list[dict]:
    """Sort experiments by datetime and group into KineticChains.

    Hard-stops on null is_new or mass_g disagreement within a chain.
    """
    sorted_exps = sorted(exps, key=lambda e: e["datetime"])
    chains: list[dict] = []
    cur: dict | None = None

    for exp in sorted_exps:
        is_new = exp["filename_flags"]["is_new"]
        if is_new is None:
            sys.exit(
                f"\nHARD STOP: is_new is null for '{exp['base_name']}'.\n"
                "Resolve this field (via backfill_is_new_sample.py or manually)\n"
                "before running Stage B."
            )

        if is_new or cur is None:
            cur = {
                "exps": [],
                "mat_key": _mat_key(exp["material"]),
                "started_at": exp["datetime"],
                "mass_g": exp["material"].get("mass_g"),
            }
            chains.append(cur)
        else:
            exp_mass = exp["material"].get("mass_g")
            chain_mass = cur["mass_g"]
            if (exp_mass is not None and chain_mass is not None
                    and abs(float(exp_mass) - float(chain_mass)) > 1e-9):
                sys.exit(
                    f"\nHARD STOP: mass_g mismatch in chain starting "
                    f"'{cur['started_at']}'.\n"
                    f"  Chain mass: {chain_mass}\n"
                    f"  {exp['base_name']}: {exp_mass}\n"
                    "Investigate before running Stage B."
                )

        cur["exps"].append(exp["base_name"])

    for chain in chains:
        chain["length"] = len(chain["exps"])
        chain["cid"] = _chain_hash(chain["mat_key"], chain["started_at"])

    return chains


# ---- graph collection -------------------------------------------------------

def collect_graph(
    exps: list[dict],
    chains: list[dict],
    ads_lookup: dict[str, dict[str, dict] | None],
    review: list[tuple],
) -> tuple[list[dict], list[dict]]:

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_mats: set[str] = set()

    base_to_chain = {b: c for c in chains for b in c["exps"]}
    exp_lookup    = {e["base_name"]: e for e in exps}

    # KineticChain nodes
    for c in chains:
        nodes.append({
            "_id":    _id_kc(c["cid"]),
            "_label": "KineticChain",
            "chain_id":     c["cid"],
            "material_key": c["mat_key"],
            "started_at":   c["started_at"],
            "length":       c["length"],
            "mass_g":       c.get("mass_g"),
        })

    for exp in sorted(exps, key=lambda e: e["datetime"]):
        base  = exp["base_name"]
        mat   = exp["material"]
        flags = exp["filename_flags"]

        # Material (deduped by key)
        mk     = _mat_key(mat)
        mat_id = _id_mat(mat)
        if mk not in seen_mats:
            seen_mats.add(mk)
            nodes.append({
                "_id":    mat_id,
                "_label": "Material",
                "id":             mat_id,
                "metal":          mat["metal"],
                "metal_loading":  mat["metal_loading"],
                "support":        mat["support"],
                "support_sa":     mat["support_sa"],
                "notebook":       mat["notebook"],
                "mfldVol":        mat["mfldVol"],
            })

        # Filename
        fn_id = _id_fn(base)
        nodes.append({
            "_id":    fn_id,
            "_label": "Filename",
            "base_name":   base,
            "datetime":    exp["datetime"],
            "exp_type":    flags["exp_type"],
            "is_new":      flags["is_new"],
            "is_reference": flags["is_reference"],
            "exp_success": flags["exp_success"],
            "has_csv":     flags["has_csv"],
        })
        edges.append({"_from": mat_id, "_to": fn_id, "_type": "HAS_EXPERIMENT"})

        chain = base_to_chain[base]
        edges.append({"_from": fn_id, "_to": _id_kc(chain["cid"]), "_type": "IN_CHAIN"})

        # Pretreatments
        pre_ids: list[str] = []
        for step in exp["pretreatments"]:
            idx    = step["step_index"]
            pre_id = _id_pre(base, idx)
            pre_ids.append(pre_id)
            nodes.append({
                "_id":    pre_id,
                "_label": "Pretreatment",
                "id":     pre_id,
                "step_index":      idx,
                "gas":             step.get("gas"),
                "pressure_meas_g1": step.get("pressure_meas_g1"),
                "pressure_meas_g2": step.get("pressure_meas_g2"),
                "pressure_calc":   step.get("pressure_calc"),
                "temp":            step.get("temp"),
                "rate":            step.get("rate"),
                "duration":        step.get("duration"),
                "chiller":         step.get("chiller"),
            })
            edges.append({"_from": fn_id, "_to": pre_id,
                          "_type": "HAS_STEP", "order": idx})
        for i in range(len(pre_ids) - 1):
            edges.append({"_from": pre_ids[i], "_to": pre_ids[i + 1],
                          "_type": "NEXT_STEP"})

        # ExpConditions + AdsParams only when has_csv
        if flags["has_csv"]:
            ec    = exp["exp_conditions"]
            ec_id = _id_ec(base)
            nodes.append({
                "_id":    ec_id,
                "_label": "ExpConditions",
                "id":     ec_id,
                "gas":             ec.get("gas"),
                "pressure_meas_g1": ec.get("pressure_meas_g1"),
                "pressure_meas_g2": ec.get("pressure_meas_g2"),
                "pressure_calc":   ec.get("pressure_calc"),
                "temp":            ec.get("temp"),
                "chiller":         ec.get("chiller"),
            })
            edges.append({"_from": fn_id, "_to": ec_id, "_type": "CONDUCTED_UNDER"})
            if pre_ids:
                edges.append({"_from": pre_ids[-1], "_to": ec_id, "_type": "NEXT_STEP"})

            ads_by_peak = ads_lookup.get(base)
            if ads_by_peak is None:
                review.append((base, "adsparams", "AdsParams",
                               "has_csv=True but no monomer_sum row found in CSV"))
            else:
                for peak_name, ads in ads_by_peak.items():
                    ap_id = _id_ap(base, peak_name)
                    nodes.append({
                        "_id":    ap_id,
                        "_label": "AdsParams",
                        "id":     ap_id,
                        "peak_name": peak_name,
                        **ads,
                    })
                    edges.append({"_from": ec_id, "_to": ap_id, "_type": "YIELDS"})

    # NEXT_EXP edges within each chain (sorted by datetime)
    for chain in chains:
        bases_sorted = sorted(chain["exps"], key=lambda b: exp_lookup[b]["datetime"])
        for i in range(len(bases_sorted) - 1):
            edges.append({
                "_from": _id_fn(bases_sorted[i]),
                "_to":   _id_fn(bases_sorted[i + 1]),
                "_type": "NEXT_EXP",
            })

    return nodes, edges


# ---- CSV serialization ------------------------------------------------------

def _csv_val(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ";".join("" if x is None else str(x) for x in v)
    return str(v)


def write_nodes_csv(nodes: list[dict], path: Path) -> None:
    header = [":ID", ":LABEL"] + [h for h, _ in NODE_PROP_COLS]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        for n in nodes:
            w.writerow([n["_id"], n["_label"]]
                       + [_csv_val(n.get(k)) for _, k in NODE_PROP_COLS])


def write_rels_csv(edges: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow([":START_ID", ":END_ID", ":TYPE", "order:Int"])
        for e in edges:
            w.writerow([e["_from"], e["_to"], e["_type"],
                        _csv_val(e.get("order"))])


# ---- Cypher generation ------------------------------------------------------

def _cy(v: Any) -> str:
    """Python value -> Cypher literal."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(_cy(x) for x in v) + "]"
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return str(v)


def _cy_props(d: dict, skip: set[str]) -> str:
    pairs = [f"{k}: {_cy(v)}" for k, v in d.items()
             if k not in skip and v is not None]
    return "{" + ", ".join(pairs) + "}"


_SKIP = {"_id", "_label", "_from", "_to", "_type", "order"}


def write_cypher(nodes: list[dict], edges: list[dict], path: Path) -> None:
    out: list[str] = [
        "// Stage B export — generated by load_graph.py",
        "// Paste into Aura query editor or run via cypher-shell.",
        "",
        "// ---- Nodes --------------------------------------------------------",
    ]

    for n in nodes:
        label = n["_label"]
        nid   = n["_id"]
        if label == "Material":
            key = ("{metal: " + _cy(n["metal"]) +
                   ", metal_loading: " + _cy(n["metal_loading"]) +
                   ", support: " + _cy(n["support"]) +
                   ", support_sa: " + _cy(n["support_sa"]) + "}")
            rest = {k: v for k, v in n.items()
                    if k not in _SKIP | {"metal","metal_loading","support","support_sa"}
                    and v is not None}
            tail = (f"\n  ON CREATE SET m += {_cy_props(rest, _SKIP)}" if rest else "")
            out.append(f"MERGE (m:Material {key}){tail};")
        elif label == "Filename":
            key  = "{base_name: " + _cy(n["base_name"]) + "}"
            rest = {k: v for k, v in n.items()
                    if k not in _SKIP | {"base_name"} and v is not None}
            tail = (f"\n  ON CREATE SET f += {_cy_props(rest, _SKIP)}" if rest else "")
            out.append(f"MERGE (f:Filename {key}){tail};")
        elif label == "KineticChain":
            key  = "{chain_id: " + _cy(n["chain_id"]) + "}"
            rest = {k: v for k, v in n.items()
                    if k not in _SKIP | {"chain_id"} and v is not None}
            tail = (f"\n  ON CREATE SET kc += {_cy_props(rest, _SKIP)}" if rest else "")
            out.append(f"MERGE (kc:KineticChain {key}){tail};")
        else:
            # Pretreatment / ExpConditions / AdsParams — merge on generated id
            rest = {k: v for k, v in n.items()
                    if k not in _SKIP and v is not None}
            out.append(f"MERGE (n:{label} {{id: '{nid}'}})\n"
                       f"  ON CREATE SET n += {_cy_props(rest, _SKIP)};")

    out.append("")
    out.append("// ---- Relationships ----------------------------------------")

    for e in edges:
        etype = e["_type"]
        a     = _match_expr(e["_from"], "a")
        b     = _match_expr(e["_to"],   "b")
        if etype == "HAS_STEP":
            out.append(f"MATCH {a}, {b}\n"
                       f"MERGE (a)-[:{etype} {{order: {e['order']}}}]->(b);")
        else:
            out.append(f"MATCH {a}, {b}\nMERGE (a)-[:{etype}]->(b);")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _match_expr(nid: str, var: str) -> str:
    prefix = nid.split("_")[0]
    label  = {"mat": "Material", "fn": "Filename", "pre": "Pretreatment",
              "ec": "ExpConditions", "ap": "AdsParams", "kc": "KineticChain"}.get(prefix, "Node")
    if label == "Filename":
        base = nid[3:]   # strip "fn_"
        return f"({var}:Filename {{base_name: '{base}'}})"
    if label == "KineticChain":
        cid = nid[3:]    # strip "kc_"
        return f"({var}:KineticChain {{chain_id: '{cid}'}})"
    # Material, Pretreatment, ExpConditions, AdsParams — all carry an 'id' property.
    # Material stores it as a convenience match key in addition to its natural key.
    return f"({var}:{label} {{id: '{nid}'}})"


# ---- schema.arrows.json -----------------------------------------------------

def write_schema_arrows(path: Path) -> None:
    """Static schema diagram for arrows.app (no actual data)."""
    NODES = [
        ("n_mat",  "Material",      100,   0,
         ["metal:String", "metal_loading:Float", "support:String",
          "support_sa:Float", "notebook:String", "mfldVol:Float"]),
        ("n_fn",   "Filename",      400,   0,
         ["base_name:String", "datetime:String", "exp_type:String",
          "is_new:Boolean", "is_reference:Boolean",
          "exp_success:Boolean", "has_csv:Boolean"]),
        ("n_pre",  "Pretreatment",  700, -150,
         ["step_index:Int", "gas:String[]", "pressure_meas_g1:Float",
          "pressure_meas_g2:Float", "pressure_calc:Float[]",
          "temp:Float", "rate:Float", "duration:Float", "chiller:Boolean"]),
        ("n_ec",   "ExpConditions", 700,  100,
         ["gas:String[]", "pressure_meas_g1:Float", "pressure_meas_g2:Float",
          "pressure_calc:Float[]", "temp:Float", "chiller:Boolean"]),
        ("n_ap",   "AdsParams",    1000,  100,
         ["peak_name:String",
          "time_s:Float", "pfo_sec_r2:Float", "pfo_sec_rmse:Float",
          "pfo_sec_k_a:Float", "pfo_sec_k_a_stderr:Float",
          "pfo_sec_q_e:Float", "pfo_sec_q_e_stderr:Float",
          "pfo_sec_k_s:Float", "pfo_sec_k_s_stderr:Float",
          "pfo_sec_k_p:Float", "pfo_sec_k_p_stderr:Float",
          "pfo_sec_q_inf:Float", "pfo_sec_q_inf_stderr:Float",
          "pfo_sec_q0:Float"]),
        ("n_kc",   "KineticChain",  400,  300,
         ["chain_id:String", "material_key:String", "started_at:String",
          "length:Int", "mass_g:Float"]),
    ]
    RELS = [
        ("r0",  "n_mat", "n_fn",  "HAS_EXPERIMENT",  []),
        ("r1",  "n_fn",  "n_pre", "HAS_STEP",        ["order:Int"]),
        ("r2",  "n_pre", "n_pre", "NEXT_STEP",        []),
        ("r3",  "n_pre", "n_ec",  "NEXT_STEP",        []),
        ("r4",  "n_fn",  "n_ec",  "CONDUCTED_UNDER",  []),
        ("r5",  "n_ec",  "n_ap",  "YIELDS",           []),
        ("r6",  "n_fn",  "n_kc",  "IN_CHAIN",         []),
        ("r7",  "n_fn",  "n_fn",  "NEXT_EXP",         []),
    ]
    schema = {
        "nodes": [
            {
                "id": nid,
                "position": {"x": x, "y": y},
                "caption": label,
                "labels": [label],
                "properties": [{"id": f"p_{nid}_{i}", "key": p.split(":")[0],
                                "value": p.split(":")[1]}
                               for i, p in enumerate(props)],
                "style": {},
            }
            for nid, label, x, y, props in NODES
        ],
        "relationships": [
            {
                "id": rid,
                "fromId": fid,
                "toId": tid,
                "type": rtype,
                "properties": [{"id": f"rp_{rid}_{i}", "key": p.split(":")[0],
                                 "value": p.split(":")[1]}
                                for i, p in enumerate(rprops)],
                "style": {},
            }
            for rid, fid, tid, rtype, rprops in RELS
        ],
    }
    path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


# ---- review file ------------------------------------------------------------

def write_review(records: list[tuple], path: Path) -> int:
    seen: set[tuple] = set()
    deduped = [r for r in records if r not in seen and not seen.add(r)]  # type: ignore[func-returns-value]
    lines = ["# Missing-value review (Stage B)",
             "# <base_name> | <field_name> | <node_label> | <notes>"]
    lines += [f"{b} | {f} | {n} | {note}" for b, f, n, note in deduped]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(deduped)


# ---- main -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage B: JSON + CSV -> Neo4j export files")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build graph in memory and report stats; do not write exports.")
    args = ap.parse_args(argv)

    if not PEAKFIT_ROOT.is_dir():
        print(f"ERROR: PEAKFIT_ROOT not found: {PEAKFIT_ROOT}", file=sys.stderr)
        return 2

    # Load all JSON experiments
    json_paths = discover_jsons()
    print(f"Discovered {len(json_paths)} in-scope JSON(s).")
    exps: list[dict] = []
    for jp in json_paths:
        exps.append(json.loads(jp.read_text(encoding="utf-8")))

    # Check material count
    mat_keys = {_mat_key(e["material"]) for e in exps}
    if len(mat_keys) != EXPECTED_MATERIAL_COUNT:
        print(
            f"HARD STOP: Expected {EXPECTED_MATERIAL_COUNT} distinct Material keys, "
            f"found {len(mat_keys)}:\n" + "\n".join(f"  {k}" for k in sorted(mat_keys)),
            file=sys.stderr,
        )
        return 1
    print(f"Material check passed: {len(mat_keys)} distinct key(s).")

    # Load AdsParams from CSVs
    ads_lookup: dict[str, dict | None] = {}
    for e in exps:
        base   = e["base_name"]
        folder = next(jp for jp in json_paths if jp.stem.startswith(base)).parent
        ads_lookup[base] = load_adsparams(base, folder)

    n_with_ads = sum(1 for v in ads_lookup.values() if v is not None)
    n_csv_exps = sum(1 for e in exps if e["filename_flags"]["has_csv"])
    print(f"AdsParams loaded: {n_with_ads}/{n_csv_exps} experiments with has_csv=True.")

    # Build kinetic chains
    chains = build_chains(exps)
    print(f"KineticChains: {len(chains)} chain(s) across {len(exps)} experiments.")

    # Collect graph
    review: list[tuple] = []
    nodes, edges = collect_graph(exps, chains, ads_lookup, review)
    print(f"Graph: {len(nodes)} node(s), {len(edges)} edge(s).")

    # Count by label/type
    from collections import Counter
    nc = Counter(n["_label"] for n in nodes)
    ec = Counter(e["_type"]  for e in edges)
    for label, count in sorted(nc.items()):
        print(f"  {label}: {count} node(s)")
    for etype, count in sorted(ec.items()):
        print(f"  :{etype}: {count} edge(s)")

    n_review = write_review(review, REVIEW_FILE)
    print(f"Review: {REVIEW_FILE} ({n_review} record(s))")

    if args.dry_run:
        print("\n--dry-run: export files NOT written.")
        return 0

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_nodes_csv(nodes, EXPORTS_DIR / "nodes.csv")
    write_rels_csv(edges,  EXPORTS_DIR / "relationships.csv")
    write_cypher(nodes, edges, EXPORTS_DIR / "graph.cypher")
    write_schema_arrows(EXPORTS_DIR / "schema.arrows.json")
    print(f"\nExports written to {EXPORTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
