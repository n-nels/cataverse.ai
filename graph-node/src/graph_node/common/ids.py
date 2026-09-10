"""Deterministic node identifiers.

Every node gets an `id` derived only from its content, never from a counter or
a database-assigned value. That is what makes a rebuild idempotent: running it
twice produces the same ids, so MERGE matches the existing node and updates it
instead of creating a duplicate.

These are carried over unchanged from the original `load_graph.py`, because the
graph already in Aura was built with them. Changing any of these functions
orphans every node it applies to - the rebuild would MERGE new nodes under new
ids and the sweep would then delete the old ones. That is recoverable, but it
is a migration, not a refactor. `tests/test_ids.py` pins them against the ids
actually present in the database.
"""

from __future__ import annotations

import hashlib

#: How each label is identified in the database, as (property, id prefix).
#:
#: Not uniform, and deliberately left that way: these are the keys the stored
#: graph already uses. Filename is keyed on `base_name` and KineticChain on
#: `chain_id`; neither carries an `id` property at all. Assuming `id`
#: everywhere makes a rebuild think all 6 chains and all 249 filenames are new,
#: which then makes the sweep delete the originals.
IDENTITY: dict[str, tuple[str, str]] = {
    "Material": ("id", ""),
    "Filename": ("base_name", "fn_"),
    "Pretreatment": ("id", ""),
    "ExpConditions": ("id", ""),
    "AdsParams": ("id", ""),
    "KineticChain": ("chain_id", "kc_"),
    # Pointers into S3. RawFile is keyed on the object key itself, which is
    # globally unique and already stable, so there is nothing to prefix it
    # with. SpectrumSeries shares `base_name` with Filename, so it needs its
    # own prefix to keep the two labels' synthetic ids apart.
    "RawFile": ("key", ""),
    "SpectrumSeries": ("base_name", "ss_"),
    # Knowledge. Only ModelParameter carries an `id`; the rest are keyed on
    # their natural name, which is what the YAML authors them by.
    "ChemConcept": ("name", "cc_"),
    "ChemSpecies": ("formula", "sp_"),
    "PyFunction": ("name", "pf_"),
    "KineticModel": ("name", "km_"),
    "ModelParameter": ("id", ""),
    # Level 2. DataColumn is keyed on `<file type>.<column>` because column
    # names repeat across types - `File` and `Peak_Name` appear in two.
    "DataFileType": ("name", "dft_"),
    "DataColumn": ("id", ""),
    "PeakGroup": ("name", "pg_"),
}


def node_id_from_stored(label: str, stored_value: str) -> str:
    """The synthetic node id corresponding to a stored identity value."""
    _, prefix = IDENTITY[label]
    return f"{prefix}{stored_value}"


def material_key(material: dict) -> str:
    """The natural key for a Material: what physically distinguishes a sample.

    Confirmed during the original build (data_graph_instructions §9c) and
    expected to yield exactly two materials.
    """
    return (
        f"{material['metal']}|{material['metal_loading']}"
        f"|{material['support']}|{material['support_sa']}"
    )


def chain_hash(mat_key: str, started_at: str) -> str:
    """Short stable hash identifying one unbroken run of experiments.

    A chain has no natural name, so it is identified by what starts it: the
    material, and when the first experiment on that sample ran.
    """
    return hashlib.md5(f"{mat_key}|{started_at}".encode()).hexdigest()[:12]


def material_id(material: dict) -> str:
    # Dots become 'p' so the id stays readable as a single token:
    # mat_pd_0p04983_ceo2_54 rather than mat_pd_0.04983_ceo2_54.
    safe = material_key(material).replace("|", "_").replace(".", "p")
    return f"mat_{safe}"


def filename_id(base_name: str) -> str:
    return f"fn_{base_name}"


def pretreatment_id(base_name: str, step_index: int) -> str:
    return f"pre_{base_name}_{step_index}"


def conditions_id(base_name: str) -> str:
    return f"ec_{base_name}"


def adsparams_id(base_name: str, peak_name: str = "monomer_sum") -> str:
    """AdsParams is keyed on (experiment, peak).

    Only monomer_sum is loaded today, but the id already carries the peak name
    so widening to cluster_sum / Peak_1975 / Peak_2093 needs no migration.
    """
    return f"ap_{base_name}_{peak_name}"


def chain_id(chain_hash_value: str) -> str:
    return f"kc_{chain_hash_value}"


def raw_file_id(key: str) -> str:
    """The S3 object key is the identity. No prefix, nothing derived."""
    return key


def spectrum_series_id(base_name: str) -> str:
    return f"ss_{base_name}"


def concept_id(name: str) -> str:
    return f"cc_{name}"


def species_id(formula: str) -> str:
    return f"sp_{formula}"


def py_function_id(name: str) -> str:
    return f"pf_{name}"


def kinetic_model_id(name: str) -> str:
    return f"km_{name}"


def model_parameter_id(model_name: str, name: str) -> str:
    return f"mp_{model_name}_{name}"


def data_file_type_id(name: str) -> str:
    return f"dft_{name}"


def data_column_id(file_type: str, column: str) -> str:
    """Keyed on the pair. `Peak_Name` alone is not unique across file types."""
    return f"{file_type}.{column}"


def peak_group_id(name: str) -> str:
    return f"pg_{name}"
