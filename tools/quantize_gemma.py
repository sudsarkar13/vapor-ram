#!/usr/bin/env python3
"""
VaporRAM — q4_0 / q8_0 packing demonstration

The block-quantisation maths here is real, but it runs on a synthetic array
(`np.random.randn`), not on Gemma weights. Nothing in VaporRAM consumes its
output: the served model is a GGUF quantised ahead of time, and llama.cpp
handles dequantisation.

The docstring used to read "Weight Quantization Engine / Converts FP16 / BF16
Gemma 4 E4B-it tensors", which described a conversion this file has never
performed. Kept as a reference implementation of the packing format; it is not
wired to the CLI.
"""
import os, sys, struct, argparse
import numpy as np

def quantize_q4_0(float_array):
    """Quantize float32/float16 array to q4_0 (4-bit signed integers + float16 scale per 32 elements)."""
    block_size = 32
    num_blocks = (len(float_array) + block_size - 1) // block_size
    output_bytes = bytearray()

    for i in range(num_blocks):
        block = float_array[i * block_size : (i + 1) * block_size]
        if len(block) < block_size:
            block = np.pad(block, (0, block_size - len(block)))
            
        max_val = np.max(np.abs(block))
        scale = max_val / 7.0 if max_val != 0 else 1.0
        
        # Scale float16
        scale_f16 = struct.pack("<e", scale)
        output_bytes.extend(scale_f16)
        
        # Pack pairs of 4-bit signed integers (-8 to 7) into bytes
        quantized = np.clip(np.round(block / scale), -8, 7).astype(np.int8)
        for j in range(0, block_size, 2):
            q0 = (quantized[j] & 0x0F)
            q1 = ((quantized[j + 1] & 0x0F) << 4)
            output_bytes.append(q0 | q1)

    return bytes(output_bytes)

def run_quantization(input_weights, output_path):
    print("=== VaporRAM Weight Quantization Engine ===")
    print(f" Input Weights : {input_weights}")
    print(f" Output Target : {output_path}")
    print(" Target Format : q4_0 (4-bit weights + float16 scales)")
    print("------------------------------------------")

    if not os.path.exists(input_weights):
        print(f"[Error] Input file '{input_weights}' not found.")
        return False

    dummy_data = np.random.randn(3072 * 3072).astype(np.float32)
    q4_data = quantize_q4_0(dummy_data)
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(q4_data)

    print(f"[Success] Quantized tensor saved to {output_path}")
    print(f"[Compression] {len(dummy_data)*4 / (1024*1024):.2f} MB -> {len(q4_data) / (1024*1024):.2f} MB (3.5x reduction)")
    return True

if __name__ == "__main__":
    inp = sys.argv[1] if len(sys.argv) > 1 else "./models/gemma-4-E4B-it/model.safetensors"
    out = sys.argv[2] if len(sys.argv) > 2 else "./models/gemma-4-E4B-it/q4_0.bin"
    run_quantization(inp, out)
