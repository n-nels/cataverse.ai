"""Pointer nodes for the files that live in S3.

The graph holds where a file is and what kind it is; the bytes stay in the
bucket. This is Level 1 of spec.md 5g.

**Built from the bucket listing, not from the share.** A `RawFile` node exists
only if the object does, so a pointer cannot go stale or promise a file that was
never uploaded - which is also what makes the deferred "reconcile S3 against the
graph" job unnecessary. It needs `ListBucket` and nothing else, so the
write-only `cataverse-uploader` key is enough; no `GetObject` is involved.

Nothing here reads an object's contents.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..common import ids
from ..common.model import Edge, IntendedGraph, Node
from ..common.s3 import StoredObject, content_type_for
from .source import ISOTOPIC_MARKER

#: The file kinds that become `RawFile` nodes.
#:
#: Deliberately a subset of what the bucket holds. The backup uploads the whole
#: share on the grounds that a curated backup is one you regret; the graph
#: models only what a question can be asked about, per 5g's out-of-scope table.
#: PeakHeight (three variants), subIFGfiles, README and monomerMax are out.
#: expParams is out for a different reason - it is already in the graph as
#: Pretreatment and ExpConditions nodes, so a blob adds nothing.
MODELLED_KINDS = frozenset(
    {
        "CarbonylPeakArea",
        "CarbonylPeakFitParams",
        "CarbonylFitResidual",
        "CarbonylFitBaseline",
        "pressureLog",
    }
)

#: Spectra: `<base_name>.0000` through `.0129`. A four-digit extension no MIME
#: table recognises, which is also why the uploader sets text/plain explicitly.
SPECTRUM = re.compile(r"^(?P<base>.+)\.(?P<index>\d{4})$")

#: Everything else: `<timestamp>_<sample>-<run>_<kind>.<ext>`. The base is
#: anchored on the timestamp so that a `_` inside the kind cannot be mistaken
#: for the separator.
NAMED = re.compile(
    r"^(?P<base>\d{8}_\d{6}_.+?)_(?P<kind>[A-Za-z]+)\.(?P<ext>csv|json|txt|md)$"
)

#: `OpusReadParams/<folder>/<base_name>.txt` - one line per spectrum, carrying
#: the timestamps. There is no `_<kind>` in the name, so NAMED cannot match it.
#: Recognised but not modelled: it is the source for a SpectrumSeries' first_at
#: and last_at, which is Level 1 work not yet done.
OPUS_PARAMS = re.compile(r"^(?P<base>\d{8}_\d{6}_.+)\.txt$")

#: Every modelled file is named for the experiment that produced it. A file
#: that is not - a calibration curve, a per-sample monomerMax - has no Filename
#: node to hang off, so Level 1 as specified has nowhere to put it.
EXPERIMENT_NAMED = re.compile(r"^\d{8}_\d{6}_")

#: Written by check_s3.py to prove the credentials work. Not data.
CHECK_PREFIX = "_check/"


def _is_isotopic(name: str) -> bool:
    """Isotopic runs are excluded from the data graph (data/source.py).

    They are in the bucket - 197 spectrum series and ~500 OpusReadParams files -
    because the backup takes everything. Modelling them here would put a class
    of experiment in the graph that the rest of the graph deliberately omits.
    """
    return ISOTOPIC_MARKER in name.lower()


def build(
    stored: dict[str, StoredObject],
    known_base_names: set[str] | None = None,
) -> IntendedGraph:
    """Turn a bucket listing into pointer nodes.

    `known_base_names` is the set of experiments the data graph holds. Objects
    whose base name is not among them are counted and reported rather than
    modelled: a `RawFile` with no `Filename` to hang off is unreachable, and a
    silent drop is how you fail to notice the two stores drifting apart. Pass
    None to model everything, which is what the tests and ad-hoc inspection do.
    """
    graph = IntendedGraph()
    series: dict[str, dict] = {}
    skipped: dict[str, int] = defaultdict(int)
    unmatched: set[str] = set()

    for key in sorted(stored):
        obj = stored[key]
        if key.startswith(CHECK_PREFIX):
            skipped["connectivity check"] += 1
            continue

        parts = key.split("/")
        if len(parts) < 2:
            skipped["key has no directory"] += 1
            continue
        filename = parts[-1]
        prefix = "/".join(parts[:-1]) + "/"

        if _is_isotopic(filename):
            skipped["isotopic"] += 1
            continue

        spectrum = SPECTRUM.match(filename)
        if spectrum:
            base = spectrum.group("base")
            if known_base_names is not None and base not in known_base_names:
                unmatched.add(base)
                skipped["no Filename node"] += 1
                continue
            entry = series.setdefault(
                base, {"prefix": prefix + base + ".", "count": 0, "bytes": 0}
            )
            entry["count"] += 1
            entry["bytes"] += obj.bytes
            continue

        named = NAMED.match(filename)
        if not named:
            if OPUS_PARAMS.match(filename):
                skipped["kind not modelled: OpusReadParams"] += 1
            elif not EXPERIMENT_NAMED.match(filename):
                skipped["not named for an experiment"] += 1
            else:
                skipped["filename not recognised"] += 1
            continue

        kind = named.group("kind")
        if kind not in MODELLED_KINDS:
            skipped[f"kind not modelled: {kind}"] += 1
            continue

        base = named.group("base")
        if known_base_names is not None and base not in known_base_names:
            unmatched.add(base)
            skipped["no Filename node"] += 1
            continue

        graph.nodes.append(
            Node(
                id=ids.raw_file_id(key),
                label="RawFile",
                properties={
                    "kind": kind,
                    "base_name": base,
                    "bytes": obj.bytes,
                    "content_type": content_type_for(Path(filename)),
                    "uploaded_at": obj.last_modified,
                },
            )
        )
        graph.edges.append(
            Edge("HAS_RAW_FILE", ids.filename_id(base), ids.raw_file_id(key))
        )

    for base, entry in sorted(series.items()):
        graph.nodes.append(
            Node(
                id=ids.spectrum_series_id(base),
                label="SpectrumSeries",
                properties={
                    "prefix": entry["prefix"],
                    "count": entry["count"],
                    "bytes": entry["bytes"],
                },
            )
        )
        graph.edges.append(
            Edge("HAS_SPECTRA", ids.filename_id(base), ids.spectrum_series_id(base))
        )

    for reason, count in sorted(skipped.items(), key=lambda kv: -kv[1]):
        graph.warnings.append(f"not modelled - {reason}: {count} object(s)")
    if unmatched:
        sample = ", ".join(sorted(unmatched)[:3])
        graph.warnings.append(
            f"{len(unmatched)} base name(s) in the bucket have no Filename node "
            f"in the data graph (e.g. {sample}). Their files were not modelled."
        )

    return graph
