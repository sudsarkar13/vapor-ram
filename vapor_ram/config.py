#!/usr/bin/env python3
"""
VaporRAM — Configuration Manager
Handles default options, environment variables, and vapor.json config file.
"""
import os, json

DEFAULT_CONFIG = {
    "model_id": "google/gemma-4-E4B-it",
    "model_dir": "./models/gemma-4-E4B-it",
    "ram_ceiling_gb": 1.5,
    "max_seq_len": 2048,
    "n_ctx": 8192,
    "host": "0.0.0.0",
    "port": 8000,
    "api_key": None,
    "quant_type": "int8_kv_int4_weights",
    "enable_thinking": True
}

def load_config(config_path="vapor.json"):
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                user_cfg = json.load(f)
                config.update(user_cfg)
        except Exception as e:
            print(f"[Warning] Failed to parse {config_path}: {e}")
    return config

def save_default_config(config_path="vapor.json"):
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"[Created] Default configuration saved to {config_path}")

if __name__ == "__main__":
    save_default_config()
