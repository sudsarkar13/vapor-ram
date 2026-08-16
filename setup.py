"""
VaporRAM packaging.

The runtime assets (static dashboard, presets, C engine, helper tools) live at
the repository root, which is where the Makefile, the Next.js build and the
release SOP expect them. setuptools can only ship data that lives *inside* a
package, so `stage_assets` copies those trees into vapor_ram/ at build time.

Without this, `pip install vapor-ram` produced a package with no dashboard, no
presets and no engine binary.
"""
import os
import shutil
import subprocess

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py as _build_py

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = "vapor_ram"

# (source relative to repo root, destination relative to the package)
ASSET_TREES = [
    (os.path.join("web", "dist"), os.path.join("web", "dist")),
    ("presets", "presets"),
    ("tools", "tools"),
]

IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.o", "node_modules", ".next", ".yarn", "*.tsbuildinfo",
)


def build_c_engine():
    """Compile the C SIMD engine. Best-effort: absence is not fatal, since the
    GGUF backend is what actually generates tokens."""
    c_dir = os.path.join(HERE, "c")
    if not os.path.isdir(c_dir):
        return
    try:
        subprocess.check_call(["make", "-C", c_dir])
    except Exception as e:
        print(f"[!] Warning: C engine build skipped on this host ({e})")


class build_py(_build_py):
    """Stage runtime assets into the package tree before the build copies it."""

    def run(self):
        build_c_engine()
        target_root = os.path.join(HERE, PKG)

        staged = []
        for src_rel, dst_rel in ASSET_TREES:
            src = os.path.join(HERE, src_rel)
            dst = os.path.join(target_root, dst_rel)
            if not os.path.isdir(src):
                print(f"[!] Warning: {src_rel} not found; it will be missing from the package.")
                continue
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=IGNORE)
            staged.append(dst_rel)

        engine_src = os.path.join(HERE, "c", "vapor_engine")
        if os.path.exists(engine_src):
            engine_dst_dir = os.path.join(target_root, "c")
            os.makedirs(engine_dst_dir, exist_ok=True)
            shutil.copy2(engine_src, os.path.join(engine_dst_dir, "vapor_engine"))
            staged.append("c/vapor_engine")

        print(f"[vapor-ram] staged into {PKG}/: {', '.join(staged) or 'nothing'}")
        super().run()


setup(
    name="vapor-ram",
    version="1.0.7-beta.1",
    description="Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it",
    long_description=open("README.md", encoding="utf-8").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Sudeepta Sarkar (sudsarkar13)",
    author_email="sudsarkar13@gmail.com",
    license="Apache-2.0",
    python_requires=">=3.9",
    packages=find_packages(include=["vapor_ram", "vapor_ram.*"]),
    cmdclass={"build_py": build_py},
    include_package_data=True,
    package_data={
        PKG: [
            "web/dist/*",
            "web/dist/**/*",
            "presets/*.json",
            "tools/*.py",
            "c/vapor_engine",
        ]
    },
    entry_points={"console_scripts": ["vapor = vapor_ram.cli:main"]},
    install_requires=[
        "numpy>=1.20.0",
        "llama-cpp-python>=0.2.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    project_urls={
        "Homepage": "https://github.com/sudsarkar13/vapor-ram",
        "Repository": "https://github.com/sudsarkar13/vapor-ram",
        "Bug Tracker": "https://github.com/sudsarkar13/vapor-ram/issues",
        "Changelog": "https://github.com/sudsarkar13/vapor-ram/blob/main/CHANGELOG.md",
    },
)
