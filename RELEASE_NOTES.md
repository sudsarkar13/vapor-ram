# v1.0.8-alpha.2 — Alpha Release

## 🔄 What's Changed (v1.0.8-alpha.1 ➔ v1.0.8-alpha.2)

**The model can hear speech.** alpha.1 gave it eyes; this one gives it ears —
and is equally specific about what those ears cannot do.

## 🎙️ Speech input

Verified against real clips of known speech, none of whose words appear in the
prompt:

| Clip | Says | Model's answer |
| :--- | :--- | :--- |
| `Front_Center.wav` | "Front Center" | *"front center"* |
| `Rear_Center.wav` | "Rear Center" | *"rear center"* |
| `Front_Left.wav` | "Front Left" | *"front left"* |

Verbatim in every case.

**Images and audio mix.** Asked about a red shape and a speech clip in the same
message, the model answered *"The shape is red, and the words spoken are
'front, center'."* Both processed, and the ordering held — which matters more
than it looks (see below).

### In the dashboard

A second attach button beside the composer, with a player in both the preview
strip and the transcript. The image and audio buttons are gated **separately**,
because a projector may carry one tower and not the other.

### Over the API

The standard OpenAI shape, streaming and not:

```json
{"type": "input_audio", "input_audio": {"data": "<base64 wav>", "format": "wav"}}
```

An `audio` part carrying a `data:` URL works too; both normalise to the same
thing.

## ⚠️ What audio is good for — and what it is not

**The encoder is speech-trained.** It transcribes speech accurately. It is
**not** a general audio-description model.

That is not a hedge, it is a measurement. Fed a 440 Hz tone, two seconds of
silence, and two seconds of white noise, it returned **the same** description
for all three — *"a gentle, rhythmic tapping"*. Silence and white noise are
maximally different signals; identical answers mean it was not hearing them.
That result is what sent us looking for real speech, where it turned out to work
perfectly.

Use it for speech. Do not trust it on sound effects or music. 16 kHz mono WAV is
what the projector expects.

**Video is still not implemented.** The projector reports no video tower, so a
video part is refused with a 400 naming what the server does accept, rather than
becoming a marker the model would describe from nothing.

## 🐛 Fixed

- **`/health` advertised capabilities the server did not have.** `accepts` was
  hard-coded to `["image", "audio", "video"]` whenever any projector was
  present — naming two things that were not wired up. It now reads the
  projector's own tensor directory (`v.*` → image, `a.*` → audio), so it
  describes the file actually installed. Video is never advertised.

- **Media was grouped by kind instead of document order.** The template emits
  one marker per media part and bitmaps are consumed positionally, so grouping
  images ahead of audio would have paired the wrong bitmap with the wrong marker
  in any mixed message. Document order now holds, with a test pinning it.

## ✅ Testing

**219 checks pass**, up from 207 at v1.0.8-alpha.1.

## 📦 Install

```bash
pip install vapor-ram==1.0.8a2
vapor download --mmproj
```

Stable users are unaffected — `pip install vapor-ram` still resolves to v1.0.7,
and the documentation site continues to advertise stable only.
