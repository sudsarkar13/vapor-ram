"""
VaporRAM — Runtime Resource Resolution

The engine needs four asset trees at runtime: the static dashboard (web/dist),
persona presets, the compiled C engine, and the helper tools the CLI imports.

Those live at the repository root during development, but inside the installed
package once distributed. Resolving them from `__file__` alone therefore worked
in a git checkout and silently failed after `pip install` — the server served a
404 dashboard and the CLI could not find its presets.

Every lookup goes through here, checking both layouts in order.
"""
import os
import sys

# .../vapor_ram/paths.py -> .../vapor_ram
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# .../vapor_ram -> repo root (checkout) or site-packages (installed)
PARENT_DIR = os.path.dirname(PACKAGE_DIR)

# Installed layout first: setup.py stages the asset trees into the package at
# build time, so a wheel carries its own copy. Falling back to the parent keeps
# a plain git checkout working without a build step.
_ROOTS = (PACKAGE_DIR, PARENT_DIR)


def _resolve(relative, marker=None):
    """Return the first existing candidate for `relative` across known roots.

    `marker` optionally names a file that must exist inside the candidate for
    it to count, so an empty leftover directory doesn't win over a real one.
    """
    for root in _ROOTS:
        candidate = os.path.join(root, relative)
        if not os.path.exists(candidate):
            continue
        if marker and not os.path.exists(os.path.join(candidate, marker)):
            continue
        return candidate
    # Nothing found: return the preferred location so error messages point at
    # where the asset is expected to be, rather than at an empty string.
    return os.path.join(_ROOTS[0], relative)


def install_root():
    """Directory the asset trees resolve against."""
    return PACKAGE_DIR if os.path.isdir(os.path.join(PACKAGE_DIR, "web")) else PARENT_DIR


def web_dist():
    """Static dashboard export served over HTTP."""
    return _resolve(os.path.join("web", "dist"), marker="index.html")


def presets_dir():
    """Persona preset JSON files."""
    return _resolve("presets")


def tools_dir():
    """Helper modules imported by CLI subcommands."""
    return _resolve("tools")


def engine_bin():
    """Compiled C streaming engine (may legitimately be absent)."""
    return _resolve(os.path.join("c", "vapor_engine"))


# A multimodal projector ("mmproj") ships as a .gguf sitting in the same
# directory as the weights, so every "find a .gguf" scan in the project could
# pick it up and try to generate tokens from a vision tower. These two helpers
# are the single rule for telling them apart; use them rather than globbing.
MMPROJ_MARKERS = ("mmproj", "mm-proj", "projector")


def is_mmproj(filename):
    """True when a .gguf is a multimodal projector rather than model weights."""
    name = os.path.basename(filename).lower()
    return name.endswith(".gguf") and any(m in name for m in MMPROJ_MARKERS)


def find_model_gguf(directory):
    """First .gguf in `directory` that is model weights, not a projector."""
    if not directory or not os.path.isdir(directory):
        return None
    for f in sorted(os.listdir(directory)):
        if f.endswith(".gguf") and not is_mmproj(f):
            return os.path.join(directory, f)
    return None


def find_mmproj(directory=None):
    """The multimodal projector beside the weights, or None if not downloaded.

    VAPOR_MMPROJ overrides the search, so a projector kept outside the model
    directory can still be used.
    """
    override = os.environ.get("VAPOR_MMPROJ")
    if override:
        return override if os.path.isfile(override) else None
    directory = directory or default_model_dir()
    if not directory or not os.path.isdir(directory):
        return None
    for f in sorted(os.listdir(directory)):
        if is_mmproj(f):
            return os.path.join(directory, f)
    return None


def simd_bench_bin():
    """Standalone AVX2/NEON microbenchmark binary (may legitimately be absent).

    This is a dot-product microbenchmark, not part of the token path — see
    tools/simd_bench.c. It is built by `make -C c` alongside the streaming
    inspector.
    """
    return _resolve(os.path.join("c", "simd_bench"))


def default_model_dir():
    """Where downloaded weights land by default.

    Weights are large and user-owned, so they are kept beside the installation
    rather than inside site-packages when running from an installed package.
    """
    if os.path.isdir(os.path.join(PARENT_DIR, "models")):
        return os.path.join(PARENT_DIR, "models", "gemma-4-E4B-it")
    if install_root() == PACKAGE_DIR:
        # Installed: default to the user's home so a pip install doesn't try to
        # write gigabytes into site-packages.
        return os.path.join(os.path.expanduser("~"), ".vapor-ram", "models", "gemma-4-E4B-it")
    return os.path.join(PARENT_DIR, "models", "gemma-4-E4B-it")


def state_dir():
    """Per-user state that must never live inside the repository.

    The API key goes here rather than in vapor.json because vapor.json is
    tracked in git — writing a shared secret into it would stage the secret
    for commit the moment the user changes a setting.
    """
    home = os.path.join(os.path.expanduser("~"), ".vapor-ram")
    os.makedirs(home, exist_ok=True)
    return home


def api_key_path():
    """File holding the persisted network-sharing API key (mode 0600)."""
    return os.path.join(state_dir(), "api_key")


def config_path():
    """Location of vapor.json.

    Writable-by-the-user config belongs outside site-packages once installed.

    VAPOR_CONFIG_PATH overrides the search entirely. Tests use it to avoid
    writing to a developer's real configuration, and it lets one host run
    several servers with independent settings.
    """
    override = os.environ.get("VAPOR_CONFIG_PATH")
    if override:
        parent = os.path.dirname(os.path.abspath(override))
        if parent:
            os.makedirs(parent, exist_ok=True)
        return override

    checkout_cfg = os.path.join(PARENT_DIR, "vapor.json")
    if install_root() != PACKAGE_DIR or os.path.exists(checkout_cfg):
        return checkout_cfg
    cfg_home = os.path.join(os.path.expanduser("~"), ".vapor-ram")
    os.makedirs(cfg_home, exist_ok=True)
    return os.path.join(cfg_home, "vapor.json")


def ensure_tools_importable():
    """Put the tools directory on sys.path for CLI subcommands that import it."""
    tools = tools_dir()
    if os.path.isdir(tools) and tools not in sys.path:
        sys.path.insert(0, tools)
    return tools
