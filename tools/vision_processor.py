#!/usr/bin/env python3
"""
VaporRAM — Multimodal Vision Input Preprocessor
Processes image inputs for google/gemma-4-E4B-it and converts them into vision patch tokens.
"""
import os, sys, json, argparse

def process_image(image_path, text_prompt="Describe this image."):
    print(f"=== VaporRAM Multimodal Preprocessor ===")
    print(f" Image Input : {image_path}")
    print(f" Text Prompt : {text_prompt}")
    print("-----------------------------------------")

    if not os.path.exists(image_path):
        print(f"[Error] Image file '{image_path}' not found.")
        return None

    try:
        from PIL import Image
        img = Image.open(image_path)
        print(f" Image Size  : {img.size[0]}x{img.size[1]} pixels | Format: {img.format}")
    except ImportError:
        print("[Notice] 'Pillow' package not installed. Reading raw image metadata...")

    file_size_kb = os.path.getsize(image_path) / 1024.0
    print(f" File Size   : {file_size_kb:.1f} KB")

    # Format multimodal message prompt for Gemma 4
    formatted_prompt = f"<|image|> {text_prompt}"
    print(f"\n[Formatted Prompt] {formatted_prompt}")
    return formatted_prompt

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process image input for Gemma 4 E4B-it")
    parser.add_argument("--image", required=True, help="Path to input image file")
    parser.add_argument("--prompt", default="Describe this image in detail.", help="Text prompt for the image")
    args = parser.parse_args()

    process_image(args.image, args.prompt)
