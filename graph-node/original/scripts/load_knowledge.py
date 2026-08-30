#!/usr/bin/env python3
"""Stage C: Knowledge layer + reference-state drift edges -> Neo4j exports.

Reads:
  knowledge/concepts.yaml
  knowledge/species.yaml
  knowledge/py_functions.yaml
  knowledge/model_parameters.yaml
  knowledge/mappings.yaml
  exports/nodes.csv          (data graph, produced by Stage B)
  exports/relationships.csv  (data graph, produced by Stage B)

Writes:
  exports/knowledge.cypher              (MERGE-based dump for Aura)
  exports/nodes_knowledge.csv           (knowledge-only nodes)
  exports/relationships_knowledge.csv   (knowledge edges incl. INSTANCE_OF,
                                         FIT_BY, RELATIVE_TO, DELTA_FROM)

Does NOT connect to Neo4j. Per §0 hard rules: present for review before running.

Property-name notes:
  * ChemSpecies.role is a list (String[]); a species can carry several roles
    (e.g. 13CO -> ["probe","isotopologue"]).
  * ModelParameter.param_role is a single string ("primary" | "secondary" |
    "initial"). Renamed from the YAML's `role` field at load time so it can
    coexist with ChemSpecies.role in the same wide nodes_knowledge.csv
    without a type conflict. Queries: `WHERE p.param_role = 'primary'`.
  * AdsParams in the data graph stores the q_0 parameter as `pfo_sec_q0`
    (no underscore between q and 0); the DELTA_FROM edge property uses
    the same suffix pattern: `delta_q0`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import yaml
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------------
# Paths & constants
# ----------------------------------------------------------------------------

PROJECT_ROOT  = Path(r"X:\graphDB")
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
EXPORTS_DIR   = PROJECT_ROOT / "exports"

DATA_NODES_CSV = EXPORTS_DIR / "nodes.csv"
DATA_RELS_CSV  = EXPORTS_DIR / "relationships.csv"

OUT_CYPHER     = EXPORTS_DIR / "knowledge.cypher"
OUT_NODES_CSV  = EXPORTS_DIR / "nodes_knowledge.csv"
OUT_RELS_CSV   = EXPORTS_DIR / "relationships_knowledge.csv"

# AdsParams CSV property -> source key on the AdsParams data node
# (used for DELTA_FROM property computation)
DELTA_PROPS: list[tuple[str, str]] = [
    ("delta_ka",   "pfo_sec_k_a"),
    ("delta_qe",   "pfo_sec_q_e"),
    ("delta_ks",   "pfo_sec_k_s"),
    ("delta_kp",   "pfo_sec_k_p"),
    ("delta_qinf", "pfo_sec_q_inf"),
    ("delta_q0",   "pfo_sec_q0"),
    ("delta_time", "time_s"),
]


# ----------------------------------------------------------------------------
# ID helpers (knowledge-side; data-side IDs are read verbatim from nodes.csv)
# ----------------------------------------------------------------------------

def _id_cc(name: str) -> str:        return f"cc_{name}"
def _id_sp(formula: str) -> str:     return f"sp_{formula}"
def _id_pf(name: str) -> str:        return f"pf_{name}"
def _id_km(name: str) -> str:        return f"km_{name}"
def _id_mp(model: str, name: str) -> str:
    return f"mp_{model}_{name}"


# ----------------------------------------------------------------------------
# Data-graph CSV reader
# ----------------------------------------------------------------------------

def _strip_type(header: str) -> str:
    """`metal:String` -> `metal`, `gas:String[]` -> `gas`."""
    return header.split(":", 1)[0]


def _parse_bool(v: str) -> bool | None:
    if v == "":
        return None
    return v.lower() == "true"


def _parse_float(v: str) -> float | None:
    if v == "":
        return None
    return float(v)


def _parse_int(v: str) -> int | None:
    if v == "":
        return None
    return int(v)


def _parse_strlist(v: str) -> list[str]:
    """Semicolon-delimited list; empty string yields []."""
    if v == "":
        return []
    return v.split(";")


def load_data_nodes(path: Path) -> dict[str, dict]:
    """Return {data_node_id: {properties incl. _label}}."""
    nodes: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Build a clean column->raw-header map for type-aware parsing
        raw_by_clean = {_strip_type(h): h for h in reader.fieldnames or []}

        def get(row: dict, clean: str) -> str:
            return row.get(raw_by_clean.get(clean, ""), "")

        for row in reader:
            nid    = row[":ID"]
            label  = row[":LABEL"]
            n: dict[str, Any] = {"_id": nid, "_label": label}

            if label == "Material":
                n["metal"]         = get(row, "metal") or None
                n["metal_loading"] = _parse_float(get(row, "metal_loading"))
                n["support"]       = get(row, "support") or None
                n["support_sa"]    = _parse_float(get(row, "support_sa"))
                n["notebook"]      = get(row, "notebook") or None
                n["mfldVol"]       = _parse_float(get(row, "mfldVol"))
            elif label == "Filename":
                n["base_name"]    = get(row, "base_name")
                n["datetime"]     = get(row, "datetime")
                n["exp_type"]     = get(row, "exp_type") or None
                n["is_new"]       = _parse_bool(get(row, "is_new"))
                n["is_reference"] = _parse_bool(get(row, "is_reference"))
                n["exp_success"]  = _parse_bool(get(row, "exp_success"))
                n["has_csv"]      = _parse_bool(get(row, "has_csv"))
            elif label == "Pretreatment":
                n["step_index"] = _parse_int(get(row, "step_index"))
                n["gas"]        = _parse_strlist(get(row, "gas"))
                n["rate"]       = _parse_float(get(row, "rate"))
                n["duration"]   = _parse_float(get(row, "duration"))
            elif label == "ExpConditions":
                n["gas"] = _parse_strlist(get(row, "gas"))
            elif label == "AdsParams":
                n["peak_name"]      = get(row, "peak_name")
                n["time_s"]         = _parse_float(get(row, "time_s"))
                n["pfo_sec_k_a"]    = _parse_float(get(row, "pfo_sec_k_a"))
                n["pfo_sec_q_e"]    = _parse_float(get(row, "pfo_sec_q_e"))
                n["pfo_sec_k_s"]    = _parse_float(get(row, "pfo_sec_k_s"))
                n["pfo_sec_k_p"]    = _parse_float(get(row, "pfo_sec_k_p"))
                n["pfo_sec_q_inf"]  = _parse_float(get(row, "pfo_sec_q_inf"))
                n["pfo_sec_q0"]     = _parse_float(get(row, "pfo_sec_q0"))
            elif label == "KineticChain":
                n["chain_id"]     = get(row, "chain_id")
                n["material_key"] = get(row, "material_key")
                n["started_at"]   = get(row, "started_at")
                n["length"]       = _parse_int(get(row, "length"))
            else:
                # unknown label — keep _id/_label only
                pass

            nodes[nid] = n
    return nodes


def load_data_rels(path: Path) -> list[dict]:
    rels: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rels.append({
                "_from": row[":START_ID"],
                "_to":   row[":END_ID"],
                "_type": row[":TYPE"],
            })
    return rels


# ----------------------------------------------------------------------------
# Parent / chain lookups
# ----------------------------------------------------------------------------

def build_lookups(rels: list[dict]) -> dict[str, dict]:
    """Build adjacency maps over the data graph for rule evaluation."""
    fn_to_pres: dict[str, list[str]] = defaultdict(list)  # fn -> [pre_ids]
    fn_to_ec:   dict[str, str]       = {}                 # fn -> ec_id
    ec_to_aps:  dict[str, list[str]] = defaultdict(list)  # ec -> [ap_ids]
    fn_to_chain: dict[str, str]      = {}                 # fn -> kc_id

    for r in rels:
        t = r["_type"]
        a, b = r["_from"], r["_to"]
        if t == "HAS_STEP":
            fn_to_pres[a].append(b)
        elif t == "CONDUCTED_UNDER":
            fn_to_ec[a] = b
        elif t == "YIELDS":
            ec_to_aps[a].append(b)
        elif t == "IN_CHAIN":
            fn_to_chain[a] = b

    # Derived: ap -> fn (via the EC that yields it), pre -> fn
    ap_to_fn: dict[str, str]  = {}
    for fn, ec in fn_to_ec.items():
        for ap in ec_to_aps.get(ec, []):
            ap_to_fn[ap] = fn

    pre_to_fn: dict[str, str] = {}
    for fn, pres in fn_to_pres.items():
        for p in pres:
            pre_to_fn[p] = fn

    return {
        "fn_to_pres":  dict(fn_to_pres),
        "fn_to_ec":    fn_to_ec,
        "ec_to_aps":   dict(ec_to_aps),
        "fn_to_chain": fn_to_chain,
        "ap_to_fn":    ap_to_fn,
        "pre_to_fn":   pre_to_fn,
    }


# ----------------------------------------------------------------------------
# Knowledge graph builders
# ----------------------------------------------------------------------------

def build_knowledge_nodes(yamls: dict) -> tuple[list[dict], list[dict]]:
    """Build the YAML-sourced knowledge nodes and the knowledge-internal edges
    (:IMPLEMENTS, :USES_SPECIES, :SUBTYPE_OF, :PARAMETER_OF)."""
    nodes: list[dict] = []
    edges: list[dict] = []

    # ChemConcept nodes + SUBTYPE_OF edges
    for c in yamls["concepts"]:
        nodes.append({
            "_id":    _id_cc(c["name"]),
            "_label": "ChemConcept",
            "name":       c["name"],
            "kind":       c["kind"],
            "definition": c.get("definition"),
            "aliases":    c.get("aliases") or [],
        })
        if c.get("subtype_of"):
            edges.append({
                "_from": _id_cc(c["name"]),
                "_to":   _id_cc(c["subtype_of"]),
                "_type": "SUBTYPE_OF",
            })

    # ChemSpecies nodes
    for s in yamls["species"]:
        nodes.append({
            "_id":    _id_sp(s["formula"]),
            "_label": "ChemSpecies",
            "formula": s["formula"],
            "role":    s.get("role") or [],
        })

    # PyFunction nodes + IMPLEMENTS edges (mappings.yaml.py_to_concept)
    for f in yamls["py_functions"]:
        nodes.append({
            "_id":    _id_pf(f["name"]),
            "_label": "PyFunction",
            "name":            f["name"],
            "signature":       f.get("signature"),
            "parameters_json": json.dumps(f.get("parameters") or []),
            "docstring":       f.get("docstring"),
        })
    py_to_concept = yamls["mappings"]["py_to_concept"]
    for fname, concepts in py_to_concept.items():
        for c in concepts or []:
            edges.append({
                "_from": _id_pf(fname),
                "_to":   _id_cc(c),
                "_type": "IMPLEMENTS",
            })

    # USES_SPECIES edges (mappings.yaml.concept_to_species)
    concept_to_species = yamls["mappings"]["concept_to_species"]
    for cname, formulas in concept_to_species.items():
        for f in formulas or []:
            edges.append({
                "_from": _id_cc(cname),
                "_to":   _id_sp(f),
                "_type": "USES_SPECIES",
            })

    # KineticModel + ModelParameter + PARAMETER_OF edges
    mp_block = yamls["model_parameters"]
    model    = mp_block["model"]
    nodes.append({
        "_id":    _id_km(model["name"]),
        "_label": "KineticModel",
        "name":        model["name"],
        "description": model.get("description"),
        "equations":   model.get("equations") or [],
    })
    for p in mp_block["parameters"]:
        nodes.append({
            "_id":    _id_mp(model["name"], p["name"]),
            "_label": "ModelParameter",
            "name":          p["name"],
            "model_name":    model["name"],
            "definition":    p.get("definition"),
            # Renamed from YAML `role` so it doesn't collide with
            # ChemSpecies.role (which is a list). See header note.
            "param_role":    p["role"],
            "quantity_kind": p.get("quantity_kind"),
            "units":         p.get("units"),
            "fitted":        p.get("fitted"),
        })
        edges.append({
            "_from": _id_mp(model["name"], p["name"]),
            "_to":   _id_km(model["name"]),
            "_type": "PARAMETER_OF",
        })

    return nodes, edges


# ----------------------------------------------------------------------------
# INSTANCE_OF + FIT_BY rule evaluation
# ----------------------------------------------------------------------------

def apply_instance_of_rules(
    data_nodes: dict[str, dict],
    lookups: dict[str, dict],
    yamls: dict,
) -> tuple[list[dict], dict[str, int]]:
    """Evaluate §7 rules against every relevant data node. Returns the
    list of edges and a per-rule fire counter (so we can flag zero-fire rules
    per §16 of the spec)."""
    rules = yamls["mappings"]["instance_of_rules"]
    sp_to_chem: dict[str, list[str]] = {
        k: (v if isinstance(v, list) else [v])
        for k, v in rules["species_to_chemistry"].items()
    }
    fire_counts: dict[str, int] = Counter()
    edges: list[dict] = []

    def emit(src_id: str, concept: str, rule_id: str) -> None:
        edges.append({
            "_from": src_id,
            "_to":   _id_cc(concept),
            "_type": "INSTANCE_OF",
        })
        fire_counts[rule_id] += 1

    # ---- Pretreatment rules R1-R4 ------------------------------------------
    for nid, n in data_nodes.items():
        if n["_label"] != "Pretreatment":
            continue
        gas_list  = n.get("gas") or []
        rate      = n.get("rate")
        duration  = n.get("duration")

        # R1_evacuation
        if any(g in ("RoughPump", "TurboPump") for g in gas_list):
            emit(nid, "evacuation", "R1_evacuation")
        # R2_chemistry: per gas, lookup species_to_chemistry
        for g in gas_list:
            for concept in sp_to_chem.get(g, []):
                emit(nid, concept, "R2_chemistry")
        # R3_ramp
        if rate is not None and rate > 0:
            emit(nid, "thermal_ramp", "R3_ramp")
        # R4_soak
        if rate == 0 and duration is not None and duration > 0:
            emit(nid, "thermal_soak", "R4_soak")

    # ---- ExpConditions rules E1-E2 -----------------------------------------
    co_isotopes = {"CO", "13CO", "12CO"}
    for nid, n in data_nodes.items():
        if n["_label"] != "ExpConditions":
            continue
        gas_list = n.get("gas") or []
        # Find parent Filename via reverse lookup
        fn_id = next(
            (f for f, ec in lookups["fn_to_ec"].items() if ec == nid),
            None,
        )
        if fn_id is None:
            continue
        exp_type = data_nodes[fn_id].get("exp_type")
        has_co   = any(g in co_isotopes for g in gas_list)
        if has_co and exp_type == "adsorption":
            emit(nid, "adsorption_measurement", "E1_adsorption")
        if has_co and exp_type == "isotopic_exchange":
            emit(nid, "isotopic_exchange_measurement", "E2_isotopic")

    # ---- Filename rule F1 --------------------------------------------------
    for nid, n in data_nodes.items():
        if n["_label"] != "Filename":
            continue
        if n.get("is_reference") is True:
            emit(nid, "reference_state", "F1_reference")

    # ---- AdsParams rules A1, A2 (FIT_BY emitted separately) ----------------
    for nid, n in data_nodes.items():
        if n["_label"] != "AdsParams":
            continue
        fn_id = lookups["ap_to_fn"].get(nid)
        if fn_id is not None and data_nodes[fn_id].get("is_reference") is True:
            emit(nid, "reference_state", "A1_reference")

    return edges, fire_counts


def build_fit_by_edges(data_nodes: dict[str, dict], model_name: str) -> list[dict]:
    """A2 (always): every :AdsParams -[:FIT_BY]-> :KineticModel."""
    return [
        {"_from": nid, "_to": _id_km(model_name), "_type": "FIT_BY"}
        for nid, n in data_nodes.items() if n["_label"] == "AdsParams"
    ]


# ----------------------------------------------------------------------------
# v1.5 reference-state drift layer
# ----------------------------------------------------------------------------

def build_drift_edges(
    data_nodes: dict[str, dict],
    lookups: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Implements §11.2 algorithm. Returns (relative_to_edges, delta_from_edges)."""
    fn_to_chain  = lookups["fn_to_chain"]
    fn_to_ec     = lookups["fn_to_ec"]
    ec_to_aps    = lookups["ec_to_aps"]

    # Group filenames by chain
    chain_to_fns: dict[str, list[str]] = defaultdict(list)
    for fn, kc in fn_to_chain.items():
        chain_to_fns[kc].append(fn)

    # AP lookup by (fn_id, peak_name)
    fn_peak_to_ap: dict[tuple[str, str], dict] = {}
    for fn_id, ec_id in fn_to_ec.items():
        for ap_id in ec_to_aps.get(ec_id, []):
            ap = data_nodes[ap_id]
            fn_peak_to_ap[(fn_id, ap.get("peak_name", ""))] = ap

    rel_edges:   list[dict] = []
    delta_edges: list[dict] = []

    for kc_id, fns in chain_to_fns.items():
        # Sort by datetime (string compare works for ISO 8601)
        fns_sorted = sorted(fns, key=lambda f: data_nodes[f]["datetime"])
        current_ref: str | None = None

        for fn in fns_sorted:
            if current_ref is not None:
                rel_edges.append({
                    "_from": fn,
                    "_to":   current_ref,
                    "_type": "RELATIVE_TO",
                })
                # DELTA_FROM: only if both sides have AdsParams for the same peak
                src_aps = {pk: ap for (f, pk), ap in fn_peak_to_ap.items() if f == fn}
                tgt_aps = {pk: ap for (f, pk), ap in fn_peak_to_ap.items() if f == current_ref}
                src_csv = data_nodes[fn].get("has_csv") is True
                tgt_csv = data_nodes[current_ref].get("has_csv") is True
                if src_csv and tgt_csv:
                    for peak in src_aps.keys() & tgt_aps.keys():
                        sap, tap = src_aps[peak], tgt_aps[peak]
                        e = {
                            "_from": sap["_id"],
                            "_to":   tap["_id"],
                            "_type": "DELTA_FROM",
                        }
                        for delta_key, src_key in DELTA_PROPS:
                            sv, tv = sap.get(src_key), tap.get(src_key)
                            e[delta_key] = (sv - tv) if (sv is not None and tv is not None) else None
                        delta_edges.append(e)

            if data_nodes[fn].get("is_reference") is True:
                current_ref = fn

    return rel_edges, delta_edges


# ----------------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------------

# Knowledge nodes_csv columns. Empty cells = null.
NODE_COLS: list[tuple[str, str]] = [
    ("name:String",            "name"),
    ("formula:String",         "formula"),
    ("kind:String",            "kind"),
    ("definition:String",      "definition"),
    ("aliases:String[]",       "aliases"),
    ("role:String[]",          "role"),
    ("param_role:String",      "param_role"),
    ("signature:String",       "signature"),
    ("parameters_json:String", "parameters_json"),
    ("docstring:String",       "docstring"),
    ("description:String",     "description"),
    ("equations:String[]",     "equations"),
    ("model_name:String",      "model_name"),
    ("quantity_kind:String",   "quantity_kind"),
    ("units:String",           "units"),
    ("fitted:Boolean",         "fitted"),
]

# Knowledge relationships_csv columns. Empty cells = null.
REL_COLS: list[tuple[str, str]] = [
    (f"{k}:Float", k) for k, _ in DELTA_PROPS
]


def _csv_val(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ";".join("" if x is None else str(x) for x in v)
    return str(v)


def write_nodes_csv(nodes: list[dict], path: Path) -> None:
    header = [":ID", ":LABEL"] + [h for h, _ in NODE_COLS]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        for n in nodes:
            w.writerow([n["_id"], n["_label"]]
                       + [_csv_val(n.get(k)) for _, k in NODE_COLS])


def write_rels_csv(edges: list[dict], path: Path) -> None:
    header = [":START_ID", ":END_ID", ":TYPE"] + [h for h, _ in REL_COLS]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        for e in edges:
            w.writerow([e["_from"], e["_to"], e["_type"]]
                       + [_csv_val(e.get(k)) for _, k in REL_COLS])


# ---- Cypher generation -----------------------------------------------------

def _cy(v: Any) -> str:
    if v is None:               return "null"
    if isinstance(v, bool):     return "true" if v else "false"
    if isinstance(v, list):     return "[" + ", ".join(_cy(x) for x in v) + "]"
    if isinstance(v, str):      return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return str(v)


_SKIP_PROP_KEYS = {"_id", "_label", "_from", "_to", "_type"}


def _cy_props(d: dict, extra_skip: set[str] = frozenset()) -> str:
    skip = _SKIP_PROP_KEYS | set(extra_skip)
    pairs = [f"{k}: {_cy(v)}" for k, v in d.items()
             if k not in skip and v is not None and v != []]
    return "{" + ", ".join(pairs) + "}"


def _data_match(nid: str, var: str) -> str:
    """Match a data-graph node by its existing :ID convention."""
    prefix = nid.split("_", 1)[0]
    label  = {"mat": "Material", "fn": "Filename", "pre": "Pretreatment",
              "ec": "ExpConditions", "ap": "AdsParams", "kc": "KineticChain"}.get(prefix)
    if label == "Filename":
        return f"({var}:Filename {{base_name: '{nid[3:]}'}})"
    if label == "KineticChain":
        return f"({var}:KineticChain {{chain_id: '{nid[3:]}'}})"
    return f"({var}:{label} {{id: '{nid}'}})"


def _knowledge_match(nid: str, var: str) -> str:
    prefix = nid.split("_", 1)[0]
    if prefix == "cc":
        return f"({var}:ChemConcept {{name: '{nid[3:]}'}})"
    if prefix == "sp":
        return f"({var}:ChemSpecies {{formula: '{nid[3:]}'}})"
    if prefix == "pf":
        return f"({var}:PyFunction {{name: '{nid[3:]}'}})"
    if prefix == "km":
        return f"({var}:KineticModel {{name: '{nid[3:]}'}})"
    if prefix == "mp":
        # mp_<model>_<param>; match on composite id property for safety
        return f"({var}:ModelParameter {{id: '{nid}'}})"
    return f"({var} {{id: '{nid}'}})"


def _match(nid: str, var: str) -> str:
    """Dispatch knowledge vs data IDs by prefix."""
    prefix = nid.split("_", 1)[0]
    if prefix in ("cc", "sp", "pf", "km", "mp"):
        return _knowledge_match(nid, var)
    return _data_match(nid, var)


def write_cypher(
    knowledge_nodes: list[dict],
    knowledge_internal_edges: list[dict],
    instance_of_edges: list[dict],
    fit_by_edges: list[dict],
    relative_to_edges: list[dict],
    delta_from_edges: list[dict],
    path: Path,
) -> None:
    out: list[str] = [
        "// Stage C export — generated by load_knowledge.py",
        "// Paste into Aura query editor or run via cypher-shell.",
        "// Assumes the data graph (Stage B) is already loaded.",
        "",
        "// ---- Knowledge nodes ----------------------------------------------",
    ]

    for n in knowledge_nodes:
        label = n["_label"]
        if label == "ChemConcept":
            key = "{name: " + _cy(n["name"]) + "}"
            rest = _cy_props(n, {"name"})
            out.append(f"MERGE (c:ChemConcept {key})\n  ON CREATE SET c += {rest};")
        elif label == "ChemSpecies":
            key = "{formula: " + _cy(n["formula"]) + "}"
            rest = _cy_props(n, {"formula"})
            out.append(f"MERGE (s:ChemSpecies {key})\n  ON CREATE SET s += {rest};")
        elif label == "PyFunction":
            key = "{name: " + _cy(n["name"]) + "}"
            rest = _cy_props(n, {"name"})
            out.append(f"MERGE (f:PyFunction {key})\n  ON CREATE SET f += {rest};")
        elif label == "KineticModel":
            key = "{name: " + _cy(n["name"]) + "}"
            rest = _cy_props(n, {"name"})
            out.append(f"MERGE (k:KineticModel {key})\n  ON CREATE SET k += {rest};")
        elif label == "ModelParameter":
            # Composite uniqueness via generated id property
            key = "{id: " + _cy(n["_id"]) + "}"
            extras = dict(n)
            extras["id"] = n["_id"]
            rest = _cy_props(extras, {"id"})
            out.append(f"MERGE (p:ModelParameter {key})\n  ON CREATE SET p += {rest};")

    out.append("")
    out.append("// ---- Knowledge-internal edges -------------------------------------")
    for e in knowledge_internal_edges:
        a = _match(e["_from"], "a")
        b = _match(e["_to"],   "b")
        out.append(f"MATCH {a}, {b}\nMERGE (a)-[:{e['_type']}]->(b);")

    out.append("")
    out.append("// ---- INSTANCE_OF (data -> concept) --------------------------------")
    for e in instance_of_edges:
        a = _match(e["_from"], "a")
        b = _match(e["_to"],   "b")
        out.append(f"MATCH {a}, {b}\nMERGE (a)-[:INSTANCE_OF]->(b);")

    out.append("")
    out.append("// ---- FIT_BY (AdsParams -> KineticModel) ---------------------------")
    for e in fit_by_edges:
        a = _match(e["_from"], "a")
        b = _match(e["_to"],   "b")
        out.append(f"MATCH {a}, {b}\nMERGE (a)-[:FIT_BY]->(b);")

    out.append("")
    out.append("// ---- RELATIVE_TO (Filename -> Filename) ---------------------------")
    for e in relative_to_edges:
        a = _match(e["_from"], "a")
        b = _match(e["_to"],   "b")
        out.append(f"MATCH {a}, {b}\nMERGE (a)-[:RELATIVE_TO]->(b);")

    out.append("")
    out.append("// ---- DELTA_FROM (AdsParams -> AdsParams) --------------------------")
    for e in delta_from_edges:
        a = _match(e["_from"], "a")
        b = _match(e["_to"],   "b")
        prop_pairs = [f"{k}: {_cy(e.get(k))}" for k, _ in DELTA_PROPS]
        props = "{" + ", ".join(prop_pairs) + "}"
        out.append(f"MATCH {a}, {b}\nMERGE (a)-[r:DELTA_FROM]->(b)\n  ON CREATE SET r += {props};")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stage C: knowledge layer + drift -> Neo4j exports")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build in memory and report stats; do not write exports.")
    args = ap.parse_args(argv)

    if not KNOWLEDGE_DIR.is_dir():
        print(f"ERROR: knowledge dir not found: {KNOWLEDGE_DIR}", file=sys.stderr)
        return 2
    if not DATA_NODES_CSV.exists() or not DATA_RELS_CSV.exists():
        print(f"ERROR: data graph CSVs not found in {EXPORTS_DIR}.\n"
              "Run Stage B first.", file=sys.stderr)
        return 2

    # Load YAMLs
    yamls = {
        "concepts":         yaml.safe_load((KNOWLEDGE_DIR / "concepts.yaml").read_text(encoding="utf-8")),
        "species":          yaml.safe_load((KNOWLEDGE_DIR / "species.yaml").read_text(encoding="utf-8")),
        "py_functions":     yaml.safe_load((KNOWLEDGE_DIR / "py_functions.yaml").read_text(encoding="utf-8")),
        "model_parameters": yaml.safe_load((KNOWLEDGE_DIR / "model_parameters.yaml").read_text(encoding="utf-8")),
        "mappings":         yaml.safe_load((KNOWLEDGE_DIR / "mappings.yaml").read_text(encoding="utf-8")),
    }
    print(f"Loaded YAMLs: {len(yamls['concepts'])} concepts, "
          f"{len(yamls['species'])} species, "
          f"{len(yamls['py_functions'])} py_functions, "
          f"{len(yamls['model_parameters']['parameters'])} params.")

    # Load data graph
    data_nodes = load_data_nodes(DATA_NODES_CSV)
    data_rels  = load_data_rels(DATA_RELS_CSV)
    label_counts = Counter(n["_label"] for n in data_nodes.values())
    print(f"Data graph loaded: {len(data_nodes)} node(s), {len(data_rels)} edge(s).")
    for lbl, count in sorted(label_counts.items()):
        print(f"  {lbl}: {count}")

    lookups = build_lookups(data_rels)

    # Build knowledge nodes + internal edges
    k_nodes, k_internal = build_knowledge_nodes(yamls)

    # Apply rules
    instance_of_edges, fire_counts = apply_instance_of_rules(data_nodes, lookups, yamls)
    fit_by_edges = build_fit_by_edges(
        data_nodes, yamls["model_parameters"]["model"]["name"],
    )

    # Drift layer
    relative_to_edges, delta_from_edges = build_drift_edges(data_nodes, lookups)

    # Stats
    print(f"\nKnowledge nodes: {len(k_nodes)}")
    for lbl, count in sorted(Counter(n["_label"] for n in k_nodes).items()):
        print(f"  {lbl}: {count}")

    print(f"\nKnowledge edges:")
    print(f"  internal (IMPLEMENTS, USES_SPECIES, SUBTYPE_OF, PARAMETER_OF): {len(k_internal)}")
    print(f"  INSTANCE_OF: {len(instance_of_edges)}")
    print(f"  FIT_BY:      {len(fit_by_edges)}")
    print(f"  RELATIVE_TO: {len(relative_to_edges)}")
    print(f"  DELTA_FROM:  {len(delta_from_edges)}")

    print("\nINSTANCE_OF rule fire counts:")
    for rule_id in ("R1_evacuation", "R2_chemistry", "R3_ramp", "R4_soak",
                    "E1_adsorption", "E2_isotopic", "F1_reference", "A1_reference"):
        n = fire_counts.get(rule_id, 0)
        flag = "  <-- ZERO FIRES; investigate per §16" if n == 0 else ""
        print(f"  {rule_id}: {n}{flag}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_nodes_csv(k_nodes, OUT_NODES_CSV)

    all_edges = (
        k_internal
        + instance_of_edges
        + fit_by_edges
        + relative_to_edges
        + delta_from_edges
    )
    write_rels_csv(all_edges, OUT_RELS_CSV)

    write_cypher(
        k_nodes,
        k_internal,
        instance_of_edges,
        fit_by_edges,
        relative_to_edges,
        delta_from_edges,
        OUT_CYPHER,
    )
    print(f"\nWrote:\n  {OUT_NODES_CSV}\n  {OUT_RELS_CSV}\n  {OUT_CYPHER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
