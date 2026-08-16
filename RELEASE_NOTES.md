# v1.0.8-alpha.1 — Alpha Release

## 🔄 What's Changed (v1.0.7 ➔ v1.0.8-alpha.1)

**The model can see.** Image input works end to end — API, CLI and dashboard.

This is an alpha because the feature is new and wants testing on hardware that
is not mine, not because anything here is known to be broken. Everything below
was verified against the real model.

## 👁️ Image input

`google/gemma-4-E4B-it` is multimodal upstream, but the GGUF everyone downloads
is a text-only conversion — of its 720 tensors, none are vision or audio. The
missing piece is a **projector** file, and it turns out to have been sitting in
the same repository as the weights all along.

```bash
vapor download --mmproj      # 990 MB: the vision and audio towers
vapor web                    # attach button appears in the composer
```

Verified with three generated images, none of whose content appears in the
prompt:

| Image | Model's answer |
| :--- | :--- |
| Red disc on white | *"The image contains a red circle."* |
| Blue square | *"The shape is a square and the color is blue."* |
| Green triangle | *"The shape is a triangle and the color is green."* |

Three for three, shape and colour both correct.

### In the dashboard

An attach button beside the composer — multi-select, removable thumbnail
previews, and **pasting a screenshot straight into the input works**. An image
on its own is a valid message, and sent images stay visible in the transcript.

### Over the API

Standard OpenAI content parts, streaming and not:

```json
{"messages": [{"role": "user", "content": [
  {"type": "text", "text": "What is in this image?"},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
]}]}
```

Ask before uploading — `/health` reports what the server can actually accept:

```json
{"multimodal": {"ready": true, "projector": "mmproj-F16.gguf",
                "accepts": ["image", "audio", "video"]}}
```

## 📊 What it costs

Measured A/B on an AMD Ryzen 7 5700U (8c/16t, 15 GB, NVMe) at `n_ctx` 16384,
identical conditions with one variable:

| | |
| :--- | ---: |
| RSS with the projector enabled | 6.06 GB |
| RSS with `--no-mmproj` | 5.61 GB |
| **Cost of enabling vision** | **0.44 GB** |

Processing an actual image did not raise it further. The projector is
memory-mapped like the weights, so it costs far less resident than its 990 MB on
disk. `--no-mmproj` on `serve` and `web` gets that back.

## 🐛 Fixed

- **A multimodal request used to produce confident nonsense.** `build_prompt`
  coerced `content` with `str()`, so a content-part array reached the model as a
  Python dict repr with the base64 inline. It did not error — it answered about
  nothing.
- **The capability report ignored `--no-mmproj`**, so a server told to ignore
  its projector still advertised `ready: true`. The dashboard enabled its attach
  button and the request failed mid-generation. Caught while testing the gate.
- **A projector could have been loaded as the model** — it is also a `.gguf` of
  comparable size sitting beside the weights, and `find_gguf` took the first
  match, working only because `g` sorts before `m`.
- **The context-retry fallback dropped the chat handler**, which would have
  disabled multimodal silently on any machine that had to reduce `n_ctx`.

## ⚠️ Known limitations

- **Audio and video are not wired up.** The projector carries the audio tower
  and the tokens and template are in place, but audio needs input decoding and
  resampling first. Sending either is refused rather than mishandled.
- Images are capped at **8 MB** and travel inline as data URLs, so they cost
  context as well as bandwidth.
- The projector is a separate **990 MB** download.

## ✅ Testing

**207 checks pass**, up from 164 at v1.0.7.

## 📦 Install

```bash
pip install vapor-ram==1.0.8a1
vapor download --mmproj
```

Stable users are unaffected — `pip install vapor-ram` still resolves to v1.0.7.
