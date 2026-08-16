"""
VaporRAM — GGUF container parser.

Reads the tensor directory of a GGUF file: every tensor's name, shape,
quantisation type and exact byte range. Nothing here loads weights or
allocates anything large; it reads the header and returns a map.

This exists because the streaming engine needs to know where each
transformer layer actually lives in the file. The previous streamer assumed
a fixed 140 MB stride from byte 0, which does not correspond to anything in
a real GGUF -- in gemma-4-E4B-it-Q4_K_M the first block starts 2.37 GB in,
after the token embedding tables, and spans ~61 MB.
"""
import os
import struct

GGUF_MAGIC = b"GGUF"

# ggml type id -> (name, elements per block, bytes per block).
# Quantised types are stored in fixed-size blocks, so a tensor's byte size is
# (elements / block_elems) * block_bytes, not elements * some width.
GGML_TYPES = {
    0: ("F32", 1, 4),        1: ("F16", 1, 2),
    2: ("Q4_0", 32, 18),     3: ("Q4_1", 32, 20),
    6: ("Q5_0", 32, 22),     7: ("Q5_1", 32, 24),
    8: ("Q8_0", 32, 34),     9: ("Q8_1", 32, 40),
    10: ("Q2_K", 256, 84),   11: ("Q3_K", 256, 110),
    12: ("Q4_K", 256, 144),  13: ("Q5_K", 256, 176),
    14: ("Q6_K", 256, 210),  15: ("Q8_K", 256, 292),
    16: ("IQ2_XXS", 256, 66), 17: ("IQ2_XS", 256, 74),
    18: ("IQ3_XXS", 256, 98), 19: ("IQ1_S", 256, 50),
    20: ("IQ4_NL", 32, 18),  21: ("IQ3_S", 256, 110),
    22: ("IQ2_S", 256, 82),  23: ("IQ4_XS", 256, 136),
    24: ("I8", 1, 1),        25: ("I16", 1, 2),
    26: ("I32", 1, 4),       27: ("I64", 1, 8),
    28: ("F64", 1, 8),       29: ("IQ1_M", 256, 56),
    30: ("BF16", 1, 2),
}

_SCALARS = {
    0: "<b", 1: "<B", 2: "<h", 3: "<H", 4: "<i", 5: "<I",
    6: "<f", 7: "<?", 10: "<q", 11: "<Q", 12: "<d",
}
_TYPE_STRING = 8
_TYPE_ARRAY = 9


class GGUFError(RuntimeError):
    """Raised when a file is not a usable GGUF container."""


class _Reader:
    def __init__(self, fh):
        self.fh = fh

    def raw(self, n):
        data = self.fh.read(n)
        if len(data) != n:
            raise GGUFError("unexpected end of file while reading header")
        return data

    def scalar(self, fmt):
        return struct.unpack(fmt, self.raw(struct.calcsize(fmt)))[0]

    def string(self):
        return self.raw(self.scalar("<Q")).decode("utf-8", "replace")

    def value(self, type_id):
        if type_id == _TYPE_STRING:
            return self.string()
        if type_id == _TYPE_ARRAY:
            element_type = self.scalar("<I")
            count = self.scalar("<Q")
            # Vocabularies run to hundreds of thousands of entries; the caller
            # only ever needs the length of those, so cap what is materialised.
            if count > 4096:
                self._skip_array(element_type, count)
                return {"array_len": count, "truncated": True}
            return [self.value(element_type) for _ in range(count)]
        fmt = _SCALARS.get(type_id)
        if fmt is None:
            raise GGUFError(f"unknown metadata value type {type_id}")
        return self.scalar(fmt)

    def _skip_array(self, element_type, count):
        if element_type in _SCALARS:
            self.fh.seek(struct.calcsize(_SCALARS[element_type]) * count, os.SEEK_CUR)
            return
        for _ in range(count):
            self.value(element_type)


def tensor_nbytes(dims, type_id):
    """Byte size of a tensor, honouring the block layout of quantised types."""
    elements = 1
    for d in dims:
        elements *= d
    entry = GGML_TYPES.get(type_id)
    if entry is None:
        return None
    _, block_elems, block_bytes = entry
    if elements % block_elems:
        # Round up: a partial block still occupies a whole block on disk.
        blocks = elements // block_elems + 1
    else:
        blocks = elements // block_elems
    return blocks * block_bytes


def type_name(type_id):
    entry = GGML_TYPES.get(type_id)
    return entry[0] if entry else f"type{type_id}"


def read_gguf(path):
    """Parse `path` and return its metadata plus the full tensor directory.

    Tensor offsets in the file are relative to the start of the data section,
    which begins after the header, aligned to general.alignment. Absolute
    offsets are resolved here so callers can read directly.
    """
    with open(path, "rb") as fh:
        r = _Reader(fh)
        if r.raw(4) != GGUF_MAGIC:
            raise GGUFError(f"{os.path.basename(path)} is not a GGUF file")
        version = r.scalar("<I")
        if version not in (2, 3):
            raise GGUFError(f"unsupported GGUF version {version}")
        n_tensors = r.scalar("<Q")
        n_kv = r.scalar("<Q")

        metadata = {}
        for _ in range(n_kv):
            key = r.string()
            metadata[key] = r.value(r.scalar("<I"))

        tensors = []
        for _ in range(n_tensors):
            name = r.string()
            n_dims = r.scalar("<I")
            dims = [r.scalar("<Q") for _ in range(n_dims)]
            type_id = r.scalar("<I")
            rel_offset = r.scalar("<Q")
            tensors.append({
                "name": name,
                "dims": dims,
                "type_id": type_id,
                "type": type_name(type_id),
                "rel_offset": rel_offset,
                "nbytes": tensor_nbytes(dims, type_id),
            })

        alignment = int(metadata.get("general.alignment", 32) or 32)
        header_end = fh.tell()
        data_start = (header_end + alignment - 1) // alignment * alignment

    for t in tensors:
        t["offset"] = data_start + t["rel_offset"]

    return {
        "path": path,
        "version": version,
        "architecture": metadata.get("general.architecture"),
        "file_size": os.path.getsize(path),
        "alignment": alignment,
        "data_start": data_start,
        "n_tensors": n_tensors,
        "metadata": metadata,
        "tensors": tensors,
    }


def layer_map(parsed):
    """Group tensors into transformer blocks and resolve each block's extent.

    Returns one entry per `blk.N.*` group with the contiguous byte range that
    covers it, which is what the streamer needs to read a layer, plus the
    non-block tensors (embeddings, output norm) reported separately since they
    are resident rather than streamed per token.
    """
    import re
    blocks = {}
    shared = []
    pattern = re.compile(r"^blk\.(\d+)\.")

    for t in parsed["tensors"]:
        m = pattern.match(t["name"])
        if not m:
            shared.append(t)
            continue
        blocks.setdefault(int(m.group(1)), []).append(t)

    layers = []
    for idx in sorted(blocks):
        group = blocks[idx]
        start = min(t["offset"] for t in group)
        end = max(t["offset"] + t["nbytes"] for t in group)
        quants = sorted({t["type"] for t in group})
        layers.append({
            "layer": idx,
            "offset": start,
            "nbytes": end - start,
            "tensor_count": len(group),
            "quant_types": quants,
            "tensors": [
                {"name": t["name"], "dims": t["dims"], "type": t["type"],
                 "offset": t["offset"], "nbytes": t["nbytes"]}
                for t in sorted(group, key=lambda x: x["offset"])
            ],
        })

    shared_bytes = sum(t["nbytes"] for t in shared)
    return {
        "layers": layers,
        "n_layers": len(layers),
        "layer_bytes_total": sum(l["nbytes"] for l in layers),
        "resident_bytes": shared_bytes,
        "resident_tensors": [
            {"name": t["name"], "dims": t["dims"], "type": t["type"],
             "offset": t["offset"], "nbytes": t["nbytes"]}
            for t in sorted(shared, key=lambda x: -x["nbytes"])[:12]
        ],
    }
