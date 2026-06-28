"""
Generate wiki images for the Edinburgh campaign using Gemini image models.

Usage:
    python portrait_gen.py --prompt "..." --output "C:/path/to/output.png"
    python portrait_gen.py --prompt "..." --output "C:/path/to/output.png" --aspect-ratio 4:3
    python portrait_gen.py --prompt "..." --output "..." --model gemini-2.5-flash-image

Aspect ratios:
    3:4   Portrait orientation — use for NPCs (default)
    4:3   Landscape orientation — use for locations
    1:1   Square
    16:9  Wide landscape
    9:16  Tall portrait

Models:
    imagen-4.0-generate-001      Dedicated image model, consistent quality (default)
    imagen-4.0-ultra-generate-001  Higher quality Imagen
    gemini-2.5-flash-image       Gemini Flash image generation
    gemini-3.1-flash-image       Gemini 3.1 Flash image generation
    gemini-3-pro-image           Gemini 3 Pro image generation
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

IMAGEN_MODELS = ("imagen",)

ASPECT_RATIO_HINTS = {
    "1:1": "square image",
    "3:4": "portrait orientation, taller than wide",
    "4:3": "landscape orientation, wider than tall",
    "9:16": "tall vertical image",
    "16:9": "wide cinematic landscape image",
}


def generate_imagen(client, model, prompt, aspect_ratio, output_path):
    response = client.models.generate_images(
        model=model,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            safety_filter_level="block_low_and_above",
        )
    )
    if not response.generated_images:
        return False
    with open(output_path, "wb") as f:
        f.write(response.generated_images[0].image.image_bytes)
    return True


def generate_gemini_image(client, model, prompt, aspect_ratio, output_path):
    aspect_hint = ASPECT_RATIO_HINTS.get(aspect_ratio, "")
    full_prompt = f"{prompt} {aspect_hint}".strip()

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            with open(output_path, "wb") as f:
                f.write(part.inline_data.data)
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Generate Edinburgh wiki images via Gemini")
    parser.add_argument("--prompt", required=True, help="Full image generation prompt")
    parser.add_argument("--output", required=True, help="Output file path (.png)")
    parser.add_argument(
        "--aspect-ratio", default="3:4",
        choices=["1:1", "3:4", "4:3", "9:16", "16:9"],
        help="Aspect ratio (default: 3:4 for portraits; use 4:3 for locations)"
    )
    parser.add_argument(
        "--model", default="imagen-4.0-generate-001",
        help="Model to use (default: imagen-4.0-generate-001)"
    )
    args = parser.parse_args()

    load_dotenv(Path(__file__).parent / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Model: {args.model}")
    print(f"Aspect ratio: {args.aspect_ratio}")
    print(f"Output: {output_path}")

    client = genai.Client(api_key=api_key)
    use_imagen = any(tag in args.model for tag in IMAGEN_MODELS)

    if use_imagen:
        success = generate_imagen(client, args.model, args.prompt, args.aspect_ratio, output_path)
    else:
        success = generate_gemini_image(client, args.model, args.prompt, args.aspect_ratio, output_path)

    if not success:
        print("Error: No image was generated. The prompt may have been blocked.", file=sys.stderr)
        sys.exit(1)

    print(f"Done: {output_path}")


if __name__ == "__main__":
    main()
