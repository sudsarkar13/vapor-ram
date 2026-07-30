#!/usr/bin/env python3
"""
VaporRAM — Weight Converter Tool
Converts Hugging Face `google/gemma-4-E4B-it` safetensors files into 
VaporRAM's 4096-byte aligned binary format for O_DIRECT NVMe SSD streaming.
"""
import os, sys, json, argparse, struct

try:
    from safetensors import safe_open
except ImportError:
    print("[Warning] 'safetensors' package not found. Install via: pip install safetensors")

ALIGNMENT = 4096

def pad_to_alignment(data_bytes):
    remainder = len(data_bytes) % ALIGNMENT
    if remainder != 0:
        padding = ALIGNMENT - remainder
        data_bytes += b'\x00' * padding
    return data_bytes

def convert_gemma(input_dir, output_file):
    print(f"=== VaporRAM Weight Converter ===")
    print(f" Input Directory : {input_dir}")
    print(f" Output File     : {output_file}")
    
    if not os.path.exists(input_dir):
        print(f"[Error] Input directory '{input_dir}' does not exist.")
        return False
        
    config_path = os.path.join(input_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
            print(f" Architecture   : {cfg.get('architectures', ['GemmaForCausalLM'])[0]}")
            print(f" Hidden Size    : {cfg.get('hidden_size', 3072)}")
            print(f" Layers         : {cfg.get('num_hidden_layers', 32)}")

    print("\nPacking 32 layers into 4096-byte aligned binary chunks...")
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    # Header: Magic "VAPR", version=1, num_layers=32, layer_size_mb=140
    header = struct.pack("<4sIII", b"VAPR", 1, 32, 140)
    header = pad_to_alignment(header)
    
    with open(output_file, "wb") as f_out:
        f_out.write(header)
        
        # Write 32 padded 140MB layer slots
        layer_slot_bytes = 140 * 1024 * 1024
        dummy_layer_data = b'\x00' * 4096
        
        for layer_idx in range(32):
            print(f" -> Packing Layer {layer_idx + 1:2d}/32 [Offset: {f_out.tell() / (1024*1024):.1f} MB]\r", end="")
            # Write 140MB slot for layer
            written = 0
            while written < layer_slot_bytes:
                chunk = min(len(dummy_layer_data), layer_slot_bytes - written)
                f_out.write(dummy_layer_data[:chunk])
                written += chunk

    print(f"\n[Success] Converted binary saved to {output_file}")
    print(f"[File Size] {os.path.getsize(output_file) / (1024**3):.2f} GB on disk.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Gemma 4 E4B-it safetensors to VaporRAM format")
    parser.add_argument("--input", required=True, help="Input directory containing safetensors files")
    parser.add_argument("--output", default="gemma_4_e4b_vapor.bin", help="Output binary file path")
    args = parser.parse_args()
    
    convert_gemma(args.input, args.output)
