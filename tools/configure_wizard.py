#!/usr/bin/env python3
"""
VaporRAM — Interactive Configuration Wizard

Guides users through model parameters, LAN host/port and the RAM ceiling target.

Two behaviours here are deliberate, and both fix bugs that shipped through
v1.0.7-beta.3:

1. The wizard MERGES into the existing config. It used to build a fresh dict
   and overwrite the file, which silently discarded every key it does not ask
   about (`n_ctx`, `enable_thinking`, `reasoning_effort`).

2. The API key is written to ~/.vapor-ram/api_key via the same helper the
   server uses, not into vapor.json. The server only ever reads the key from
   that path, so a key entered here previously had no effect at all — the user
   was told authorization was configured when it was not.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vapor_ram import paths
from vapor_ram.config import DEFAULT_CONFIG

CONFIG_PATH = paths.config_path()


def run_wizard():
    print("=== VaporRAM Configuration Wizard ===")
    print(f"Editing {CONFIG_PATH}")
    print("Press Enter to keep the current value.\n")

    current = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                current = json.load(f)
        except Exception as e:
            print(f"[Warning] Could not parse existing config ({e}); starting from defaults.")

    def ask(key, prompt_text):
        default = DEFAULT_CONFIG.get(key)
        cur_val = current.get(key, default)
        user_val = input(f" {prompt_text} [{cur_val}]: ").strip()
        if not user_val:
            return cur_val
        # bool before int: bool is a subclass of int in Python.
        if isinstance(default, bool):
            return user_val.lower() in ("true", "1", "yes", "y", "on")
        if isinstance(default, float):
            return float(user_val)
        if isinstance(default, int):
            return int(user_val)
        return user_val

    # Start from what is already on disk so unasked keys survive.
    new_cfg = dict(current)
    new_cfg["model_id"] = ask("model_id", "Model Identifier")
    new_cfg["model_dir"] = ask("model_dir", "Model Weights Directory")
    new_cfg["ram_ceiling_gb"] = ask("ram_ceiling_gb", "RAM Ceiling Target (GB)")
    new_cfg["n_ctx"] = ask("n_ctx", "Context Window (tokens)")
    new_cfg["host"] = ask("host", "LAN Host Binding IP")
    new_cfg["port"] = ask("port", "Server Port Number")
    new_cfg["enable_thinking"] = ask("enable_thinking", "Enable reasoning by default (true/false)")
    new_cfg["reasoning_effort"] = ask("reasoning_effort", "Reasoning effort (low/medium/high/xhigh)")

    # Never persist a secret into vapor.json.
    new_cfg.pop("api_key", None)

    with open(CONFIG_PATH, "w") as f:
        json.dump(new_cfg, f, indent=2)
        f.write("\n")

    print(f"\n[Success] Configuration saved to {CONFIG_PATH}")
    print(json.dumps(new_cfg, indent=2))

    answer = input("\n Generate a network-sharing API key now? [y/N]: ").strip().lower()
    if answer in ("y", "yes"):
        from vapor_ram.openai_server import rotate_api_key
        key = rotate_api_key()
        print(f"\n[Success] API key written to {paths.api_key_path()} (mode 0600)")
        print(f"  {key}")
    else:
        print(f"\n No key generated. The server creates one on first shared start,")
        print(f" or run: vapor share --new-key")


if __name__ == "__main__":
    run_wizard()
