#!/usr/bin/env python3
"""
VaporRAM — Interactive Configuration Wizard
Guides users through setting up model parameters, LAN host IPs, ports, and RAM limits.
"""
import os, sys, json

CONFIG_PATH = "vapor.json"

def run_wizard():
    print("=== VaporRAM Configuration Wizard ===")
    print("Set up default options for VaporRAM. Press Enter to accept defaults.\n")

    current = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                current = json.load(f)
        except Exception:
            pass

    def ask(key, default, prompt_text):
        cur_val = current.get(key, default)
        user_val = input(f" {prompt_text} [{cur_val}]: ").strip()
        if not user_val:
            return cur_val
        if isinstance(default, float):
            return float(user_val)
        if isinstance(default, int):
            return int(user_val)
        if isinstance(default, bool):
            return user_val.lower() in ("true", "1", "yes", "y")
        return user_val

    new_cfg = {}
    new_cfg["model_id"] = ask("model_id", "google/gemma-4-E4B-it", "Model Identifier")
    new_cfg["model_dir"] = ask("model_dir", "./models/gemma-4-E4B-it", "Model Weights Directory")
    new_cfg["ram_ceiling_gb"] = ask("ram_ceiling_gb", 1.5, "RAM Ceiling Limit (GB)")
    new_cfg["max_seq_len"] = ask("max_seq_len", 2048, "Max Context Sequence Length")
    new_cfg["host"] = ask("host", "0.0.0.0", "LAN Host Binding IP")
    new_cfg["port"] = ask("port", 8000, "Server Port Number")
    new_cfg["api_key"] = ask("api_key", "", "API Key Authorization (leave blank for none)") or None

    with open(CONFIG_PATH, "w") as f:
        json.dump(new_cfg, f, indent=2)

    print(f"\n[Success] Configuration saved to {CONFIG_PATH}")
    print(json.dumps(new_cfg, indent=2))

if __name__ == "__main__":
    run_wizard()
