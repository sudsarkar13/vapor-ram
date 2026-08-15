"""
VaporRAM — Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it

Public surface:
    from vapor_ram import openai_server, doctor, resource_plan, config
    from vapor_ram.paths import web_dist, presets_dir, engine_bin
"""
from .version import __version__

__all__ = ["__version__", "paths", "config", "doctor", "resource_plan", "openai_server"]
