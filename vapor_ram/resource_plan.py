#!/usr/bin/env python3
"""
VaporRAM — Resource Planning & RAM Ceiling Calculator
"""
import os, sys, json

def build_plan(ram_budget_gb=1.5, seq_len=2048):
    layer_size_mb = 140.0
    double_buf_mb = layer_size_mb * 2.0
    kv_cache_mb = (seq_len * 32 * 16 * 256 * 1) / (1024 * 1024) # int8 KV
    activation_mb = 150.0
    server_overhead_mb = 100.0
    
    total_est_mb = double_buf_mb + kv_cache_mb + activation_mb + server_overhead_mb
    
    return {
        "model": "google/gemma-4-E4B-it",
        "ram_ceiling_target_gb": ram_budget_gb,
        "estimated_ram_usage_mb": round(total_est_mb, 2),
        "breakdown": {
            "layer_double_buffer_mb": double_buf_mb,
            "int8_kv_cache_mb": round(kv_cache_mb, 2),
            "activation_buffers_mb": activation_mb,
            "server_and_ui_overhead_mb": server_overhead_mb
        },
        "streaming_mode": "O_DIRECT Layer-by-Layer SSD Offloading",
        "status": "PASS" if total_est_mb <= (ram_budget_gb * 1024) else "WARNING"
    }

def format_plan(plan):
    lines = [
        f"=== VaporRAM Resource Plan ({plan['model']}) ===",
        f" Target RAM Ceiling : {plan['ram_ceiling_target_gb']} GB",
        f" Estimated RAM Usage: {plan['estimated_ram_usage_mb']} MB",
        f" Streaming Strategy : {plan['streaming_mode']}",
        f" Plan Status        : {plan['status']}",
        "",
        " Memory Breakdown:",
        f"   - Layer Double Buffer : {plan['breakdown']['layer_double_buffer_mb']} MB",
        f"   - int8 KV Cache       : {plan['breakdown']['int8_kv_cache_mb']} MB",
        f"   - Activation Buffers  : {plan['breakdown']['activation_buffers_mb']} MB",
        f"   - Web UI & Server     : {plan['breakdown']['server_and_ui_overhead_mb']} MB",
    ]
    return "\n".join(lines)

if __name__ == "__main__":
    plan = build_plan()
    print(format_plan(plan))
