# Changelog

All notable changes to the **VaporRAM** project will be documented in this file.

---


## [v1.0.8-alpha.2] - 2026-08-17

Second alpha of the 1.0.8 line. **The model can hear speech.** Audio input works
end to end — API and dashboard — and this entry is as specific about what the
encoder cannot do as about what it can.

### 🚀 Highlights & Features

- **Speech transcription, verified working.** Real clips of known speech, none
  of whose words appear in the prompt:

  | Clip | Says | Model's answer |
  | :--- | :--- | :--- |
  | `Front_Center.wav` | "Front Center" | "front center" |
  | `Rear_Center.wav` | "Rear Center" | "rear center" |
  | `Front_Left.wav` | "Front Left" | "front left" |

  Verbatim in every case.

- **Images and audio mix in one message.** Asked about a red shape and a speech
  clip together, the model answered *"The shape is red, and the words spoken are
  'front, center'."* — both media processed, and the ordering held.

- **Attach audio in the dashboard.** A second button beside the composer with a
  player in both the preview strip and the transcript. The image and audio
  buttons are gated **separately**, because a projector may carry one tower and
  not the other.

- **OpenAI audio content parts** on `/v1/chat/completions`: `input_audio` with a
  bare base64 payload and a `format`, or an `audio` part carrying a `data:` URL.
  Both shapes normalise to the same internal representation.

### 🐛 Fixed Bugs & Issues

- **`/health` advertised capabilities the server did not have.** `accepts` was
  the hard-coded list `["image", "audio", "video"]` whenever any projector was
  present — naming two things that were not wired up. It is now derived from the
  projector's own tensor directory: a `v.*` tower means image, an `a.*` tower
  means audio. It describes the file actually installed, and **video is never
  advertised**.

- **Media was collected grouped by kind rather than in document order.** The
  chat template emits one marker per media part and the runtime consumes bitmaps
  positionally, so grouping images before audio would have paired the wrong
  bitmap with the wrong marker in any mixed message. Collection now follows
  document order, and a test pins it.

### ⚠️ What audio is and is not

**The encoder is speech-trained.** It transcribes speech accurately. It is
**not** a general audio-description model, and the evidence is direct: fed a
440 Hz tone, two seconds of silence, and two seconds of white noise, it returned
*the same* description for all three — "a gentle, rhythmic tapping". Silence and
white noise are maximally different signals; identical answers mean it was not
hearing them.

Use it for speech. Do not trust it on sound effects or music. 16 kHz mono WAV is
what the projector expects.

**Video remains unimplemented.** The projector reports no video tower, so a
video part is refused with a 400 naming what the server does accept, rather than
becoming a marker the model would describe from nothing.

### ✅ Testing

**219 checks pass**, up from 207 at v1.0.8-alpha.1.


## [v1.0.8-alpha.1] - 2026-08-17

First alpha of the 1.0.8 line. **The model can see.** Image input works end to
end — API, CLI and dashboard — against `google/gemma-4-E4B-it`'s real vision
tower.

This is an alpha because the feature is new and wants testing on hardware that
is not mine, not because anything here is known to be broken.

### 🚀 Highlights & Features

- **Image input, verified working.** Three generated test images, none of whose
  content appears in the prompt:

  | Image | Model's answer |
  | :--- | :--- |
  | Red disc on white | "The image contains a red circle." |
  | Blue square | "The shape is a square and the color is blue." |
  | Green triangle | "The shape is a triangle and the color is green." |

  Three for three, shape and colour both correct.

- **Attach images in the dashboard.** A button beside the composer, multi-select
  with removable thumbnail previews, and paste-a-screenshot straight into the
  input. An image on its own is a valid message; sent images stay visible in the
  transcript.

- **`vapor download --mmproj`** fetches the multimodal projector
  (`mmproj-F16.gguf`, 990,372,672 bytes) — the vision and audio towers, which
  the base GGUF does not contain. `--mmproj-only` fetches it alone when the
  weights are already present. `VAPOR_MMPROJ` overrides its location.

- **OpenAI content parts are accepted** on `/v1/chat/completions`, streaming and
  not. Media parts map onto the model's own control tokens — `<|image|>` 258880,
  `<|audio|>` 258881, `<|video|>` 258884 — each verified against the vocabulary
  rather than assumed. This is the same mapping the model's chat template
  performs.

- **`/health` reports the capability**: `{multimodal: {ready, projector,
  accepts}}`, so a client can ask before uploading a large image.

- **`--no-mmproj`** on `serve` and `web` leaves an installed projector unused.

### 📊 Measured

Measured on an AMD Ryzen 7 5700U (8 cores / 16 threads, 15 GB, NVMe), `n_ctx`
16384, A/B under identical conditions with one variable:

| | |
| :--- | ---: |
| RSS with the projector enabled | 6.06 GB |
| RSS with `--no-mmproj` | 5.61 GB |
| **Cost of enabling vision** | **0.44 GB** |

Processing an actual image did not raise RSS further beyond that. Note the
projector is memory-mapped like the weights, so it costs far less resident than
its 0.99 GB on disk.

### 🐛 Fixed Bugs & Issues

- **A multimodal request used to produce confident nonsense.** `build_prompt`
  coerced `content` with `str()`, so an OpenAI content-part array reached the
  model as a Python dict repr with the base64 payload inline. It did not error;
  it answered about nothing.
- **The capability report ignored `--no-mmproj`.** `multimodal_ready()` checked
  the projector file and the runtime but not the opt-out flag, so a server told
  to ignore its projector still advertised `ready: true`. The dashboard enabled
  its attach button and the request then failed mid-generation. It now reports
  `ready: false` and refuses up front with a 400 that names the fix.
- **A projector could have been loaded as the model.** It is also a `.gguf` of
  comparable size living beside the weights, and every "find a .gguf" scan took
  the first match — `find_gguf` worked only because `g` sorts before `m`.
  `paths.is_mmproj` / `find_model_gguf` / `find_mmproj` are now the single rule,
  used by the server, `bench`, `inspect` and the resource planner.
- **The context-retry fallback dropped the chat handler**, which would have left
  multimodal silently disabled on any machine that had to reduce `n_ctx` to
  load, with `/health` still reporting it ready.

### ⚠️ Known limitations

- **Audio and video are not wired up**, though the projector carries the audio
  tower and the tokens and template are in place. Audio additionally needs input
  decoding and resampling. Sending either is refused rather than mishandled.
- Images are capped at **8 MB** and travel inline as data URLs, so they cost
  context as well as bandwidth.
- The projector is an extra **990 MB download**, and is not fetched by a plain
  `vapor download`.

### ✅ Testing

**207 checks pass**, up from 164 at v1.0.7. The new groups cover content-part
rendering, the control tokens, projector discovery, the capability gate and its
opt-out, and assert the installed projector really does carry vision and audio
tensors.

---

## [v1.0.7] - 2026-08-16

First stable release of the 1.0.7 line. The theme is **removing every claim the
software could not back with a measurement**, and fixing the things that audit
uncovered.

### 🔎 Claims corrected

Several figures and descriptions were wrong, some since the project began. Each
is now derived from the file or the machine, or is gone.

- **`vapor bench` fabricated a passing result.** It invoked the C engine with
  `c/vapor_engine.o` — an object file — as stand-in weights. The call failed
  every time, and the tool then measured the peak RSS of the process that had
  just failed to start and reported `RAM Status : PASS (< 1.5 GB)`. The
  project's own advertised benchmark therefore reported the headline RAM
  ceiling as met, on the strength of a process that never loaded the model.
  It now streams the model's real 42 block ranges through `O_DIRECT` and
  reports measured throughput, per-block latency, and what streaming would
  cost per token. It no longer grades itself against the ceiling at all.
- **`vapor bench --simd` reported ~200,000 GFLOPS** — roughly a thousand times
  what this class of CPU can produce. The results were unused, so `-O3` deleted
  both timing loops; the "scalar" baseline was also auto-vectorised into the
  very instructions it was supposed to be compared against, and the pure
  function was hoisted out of the loop entirely. Fixed with a compiler barrier,
  a genuinely scalar baseline and enough iterations to measure. It now reports
  **2.76 GFLOPS scalar vs 14.13 GFLOPS AVX2 (5.12x)**, stable across runs. Its
  vector dimension also claimed to be "Gemma hidden size" while being 3072; this
  model's hidden size is **2560**. It also printed `OpenMP Threads : 16` while
  running single-threaded — there is no `#pragma omp` anywhere in the C sources.
- **`vapor plan` printed a passing verdict against the RAM ceiling.** Every
  input was a hard-coded constant: a 140 MB layer size (real blocks average
  61.7 MB), 32 layers (there are 42), 16 attention heads (there are 8, with 2
  KV heads), and flat 150 MB / 100 MB allowances. They summed to 786 MB,
  compared to the 1.5 GB ceiling, and reported `Plan Status : PASS` while the
  engine's measured RSS was over 7 GB. It now sizes the streaming design from
  the file's real geometry, reports the running server's measured RSS when one
  is reachable, and states plainly that the ceiling is not met.
- **`vapor inspect` printed four wrong architecture numbers and a fabricated
  pass.** It read only `config.json`, whose architecture keys are nested under
  `text_config` for this model, so every lookup missed and its fallbacks were
  printed as fact: hidden size 3072 (really 2560), 32 layers (42), 16 heads
  (8), vocab 256000 (262144). It ignored the GGUF entirely and closed with an
  unconditional streaming-readiness pass quoting an NVMe block size that does
  not exist. Rewritten against the GGUF parser, with a real integrity check:
  the tensor directory must account for the file exactly.
- **`vapor doctor` passed a machine that cannot run the model.** It checked
  free RAM against the 1.5 GB *target* rather than the engine's real
  requirement, so a host with 2 GB available was told it was fine and then
  failed to load 4.98 GB of memory-mapped weights. It also reported
  "GGUF Engine & C SIMD Streamer Ready" whenever either component was present,
  describing the streaming inspector as part of the runtime. Both fixed.
- **`tools/convert_gemma_safetensors.py` never converted anything.** It opened
  no tensor: it wrote 32 slots of 140 MB of zeros — 4.4 GB — printed
  `[Success] Converted binary saved` and reported the file size, in a container
  format nothing in the project reads. Removed.
- **`tools/quantize_gemma.py`** called itself a "Weight Quantization Engine"
  that "converts FP16 / BF16 Gemma 4 E4B-it tensors" while quantising
  `np.random.randn`. The packing maths is real, so it is kept and relabelled as
  the demonstration it is.
- **`/health` described the weights as `GGUF / Int4 SSD Stream`.** Wrong twice:
  the file is a mixed K-quant (Q4_K/Q5_K/Q6_K, plus F32 and BF16), and
  llama.cpp memory-maps it rather than streaming it. The field is now read from
  the GGUF tensor directory.
- **`quant_type: "int8_kv_int4_weights"`** sat in the default configuration
  describing a quantisation scheme the project does not use. Nothing read it.
  Removed, along with the equally dead `max_seq_len`.
- **The package described itself as an "Ultra-Low RAM SSD Streaming Engine"** on
  PyPI, in the CLI banner, in the dashboard and in the page title, and the
  documentation site advertised streaming "under a 1.5 GB RAM ceiling" as fact.
  Nothing is streamed during generation. All of it now describes what the
  software does.
- **The documentation site** claimed 32 transformer layers (there are 42), an
  "8B" model (7.52 B parameters), an int8 KV cache holding context under 250 MB
  (llama.cpp uses its own f16 cache), a fabricated "RAM Budget Usage 9.5%", and
  a standalone C runtime that does not exist. It had also sat on `v1.0.7-alpha.3`
  for eight releases while its sync job claimed to update it.

### 📊 Every README figure is now measured

Measured on an AMD Ryzen 7 5700U (8 cores / 16 threads, 15 GB RAM, NVMe) with
`gemma-4-E4B-it-Q4_K_M.gguf`, and reproducible with `vapor bench`:

| | |
| :--- | ---: |
| Peak RSS, `n_ctx` 8192 | 7.27 GB |
| Peak RSS, `n_ctx` 16384 | 8.72 GB |
| Cost of doubling context | 1.45 GB |
| Throughput | 4.0–5.3 tok/s |
| Server start → ready | 9.5 s |
| `O_DIRECT` streaming | 974.7 MB/s, 60.0 ms/block |
| If every block were streamed per token | 2.54 s/token (0.39 tok/s) |

The README now opens with a table of what is true, including the plain
statement that **the 1.5 GB RAM ceiling is not met** and what reaching it would
cost. The ceiling remains a costed research goal, not a feature nearly done.

### 🐛 Fixed Bugs & Issues

- **The OpenAI API returned no `usage` block.** `completion_tokens` was
  hard-coded to `None`, so any SDK client saw zero tokens for every
  non-streaming call. Both the streaming and non-streaming paths now report
  real counts — prompt tokens from the model's own tokenizer, completion tokens
  counted per llama.cpp chunk rather than per yielded piece, since the thinking
  splitter can emit several pieces for one token.
- **The configuration wizard wrote the API key into `vapor.json`**, which the
  server never reads — it only ever loads the key from `~/.vapor-ram/api_key`.
  A key entered in the wizard silently did nothing while telling the user
  authorization was configured. It now writes through the same helper the
  server uses, and never persists a secret to `vapor.json`.
- **The wizard also discarded settings.** It built a fresh dict and overwrote
  the file, dropping every key it does not ask about — `n_ctx`,
  `enable_thinking`, `reasoning_effort`. It now merges.
- **`vapor init-config` wrote to the current working directory** instead of the
  path the server reads, leaving a `vapor.json` wherever the user happened to
  be standing.
- **`vapor.json` was tracked in git** while the server writes to it on every
  settings change, so a checkout could silently reset a user's configuration.
  It is now untracked and ignored; `vapor.example.json` is the tracked
  reference. `VAPOR_CONFIG_PATH` overrides the location.
- **Compiled binaries were tracked in git.** `c/vapor_engine` and
  `c/simd_bench` were committed, pushing one host's architecture at every other
  host — `c/simd_bench` was even listed in `.gitignore`, which does nothing for
  an already-tracked file. Both untracked; `setup.py` builds them at install
  time and `MANIFEST.in` ships the sources.
- **The docs sync job could not do its job.** Its two regexes matched neither
  the nav version tag nor the download button. Version strings are now wrapped
  in explicit markers, and the job fails loudly if any stale version survives.

### 🧹 Removed

- `tools/fix_webui.py` — 20 KB patching a hand-written dashboard replaced long
  ago, referenced by nothing, still shipped in the sdist.
- `docs/assets/changelog.json` and `docs/assets/releases.json` — frozen at
  `v1.0.7-alpha.1` and read by nothing; both docs pages fetch the GitHub API
  directly. They also claimed 135.5 MB release tarballs; the real ones are
  1.17 MB.

### ✅ Testing

- Integration suite grows to **164 checks**, with a new group that guards each
  corrected claim: the weight-format string, the `usage` block, config-path
  resolution, the wizard's secret handling and merge behaviour, and that the
  benchmark can never again print a pass against the RAM ceiling.
- `Development Status` moves to **5 - Production/Stable**; Python 3.9 and 3.12
  are declared and both are tested in CI.

---

## [v1.0.7-beta.3] - 2026-08-16

### 🚀 Highlights & Features
- **Reasoning effort levels**: `low`, `medium`, `high` (default) and `xhigh`. Settable in the sidebar, via `POST /v1/system/config`, per request with `{"reasoning_effort": "low"}`, and from the CLI with `--think-level` on `serve`, `web`, `run` and `chat`. Persisted to `vapor.json`.
- The model's chat template has no effort parameter — it takes only a boolean — so these are VaporRAM's own and the mechanism is stated rather than implied: each level contributes a depth instruction placed with the thinking token at the top of the system turn, ahead of any persona instruction so a preset cannot override it, plus a reasoning-token budget shown in the UI.

### 🐛 Fixed Bugs & Issues
- **The reasoning switch rendered broken**: its knob used `translate-x-4.5`, which Tailwind does not generate — the emitted CSS was a stray `.translate-x-4` and an invalid `.translate-x-`, so the knob sat outside its track. Positioned with `left` values that Tailwind does emit.
- Invalid effort levels are refused with the valid set named, rather than being silently accepted.

---

## [v1.0.7-beta.2] - 2026-08-16

### 🚀 Highlights & Features
- **Reasoning / thinking mode, working for real.** `gemma-4-E4B-it` supports it natively; VaporRAM now uses it. On by default when the active model's chat template implements a thinking channel — detected by reading the template out of the GGUF rather than assuming, so the switch is only offered when it would do something. Sidebar switch, `--think`/`--no-think` on `serve`, `web`, `run` and `chat`, `/think` mid-session, and `{"thinking": false}` per request. Persisted to `vapor.json`.
- **The thought process is readable.** Reasoning appears above each reply in a block that animates while it streams and is **open by default** so it can be read as it arrives; collapsing is opt-in.
- **Reasoning streams on its own channel** (`delta.reasoning_content`), so clients that do not know about it render the answer alone rather than mixing the two.
- **Timings separate the two**: `reasoning_tokens` and `first_answer_ms` alongside `first_token_ms`, with throughput computed over everything produced.

### 🐛 Fixed Bugs & Issues
- **The prompt format was wrong for this model, in every request ever sent.** `build_prompt` used `<start_of_turn>` / `<end_of_turn>`, which are **not in `gemma-4-E4B-it`'s vocabulary** — they tokenised as literal text. Verified against the GGUF vocabulary, the real markers are `<|turn>` (105) and `<turn|>` (106, also EOS). The stop sequences had the same defect and never matched a real token.
- **The model has a system turn.** Instructions were folded into the first user message on the belief that Gemma has no system role; this model's template opens `<|turn>system`.
- **No cache headers were sent for the dashboard**, so browsers applied heuristic caching to `index.html` and could keep serving a previous build after an upgrade — new UI would simply not appear. `index.html` is now `no-cache`; content-hashed assets under `/_next/static/` are `immutable`.
- **Reasoning was unreadable**: the thinking block was collapsed by default, so it looked like a bare animation with nothing to read.
- **Budget exhaustion is reported**: reasoning shares `max_tokens` with the answer and can consume all of it; that is now detected and explained instead of returning an empty reply.
- **Prior reasoning is stripped from replayed history**, mirroring the template's own `strip_thinking` macro.
- **Correction to the v1.0.7-alpha.6 notes.** Those notes described `<|think|>` as "not a Gemma control token" and removed it from the presets on that basis. That was wrong: `<|think|>` is token 98 and is this model's real reasoning token. It did nothing before — but because it sat in a preset's `system_instruction` that the old prompt builder folded into a user turn, not because the token was meaningless.

---

## [v1.0.7-beta.1] - 2026-08-16

First beta. The code is identical to `v1.0.7-alpha.6`; what changes is the
claim the project makes about itself.

### 📌 What beta means here
- **The inference server is feature-complete**: OpenAI-compatible API with real
  token streaming, network sharing behind an API key with auth on every
  endpoint, persona presets, a terminal chat client, model download with byte-
  accurate progress, runtime context control, and a dashboard whose every
  figure is measured rather than estimated. 112 automated checks cover it.
- **The 1.5 GB RAM ceiling is a costed research goal, not a pending feature.**
  Generation runs on llama.cpp, which memory-maps the full GGUF; measured RSS
  is 6.8–8.1 GB. Streaming instead would cost ~2.5 s/token (~0.4 tok/s) against
  6.8 tok/s resident — roughly 17x — and requires writing a full inference
  engine. The README now leads with what VaporRAM is, with the ceiling stated
  as a goal the project has measured the price of.

### 🐛 Fixed Bugs & Issues
- Documentation described the streaming engine as the product and the ceiling
  as nearly delivered. Both are now stated accurately.

---

## [v1.0.7-alpha.6] - 2026-08-16

### 🚀 Highlights & Features
- **Real GGUF layout in the Brain Cortex**: new `vapor_ram/gguf.py` parses the tensor directory — names, shapes, quantisation types and exact byte ranges, with block-aware sizing for every ggml type. For `gemma-4-E4B-it-Q4_K_M` it reports 42 blocks (matching the file's own `block_count`), 720 tensors, block data starting at byte 2,386,145,088, ~61 MB per block, 2.41 GB streamable against 2.21 GB resident.
- **Measured O_DIRECT streaming**: `POST /v1/cortex/benchmark` streams each block's real byte range past the page cache and reports per-block timings. Measured ~990 MB/s and ~59 ms per block on NVMe.
- **The number the tab existed to produce**: at that bandwidth, streaming all 42 blocks per token costs ~2.5 s/token (~0.4 tok/s) against 6.8 tok/s with the weights resident — roughly 17x, which is what the 1.5 GB ceiling would cost on this hardware. Stated in the UI and the README rather than left as an aspiration.
- **Brain Cortex rebuilt** around that data: block map with spans proportional to real byte sizes, quantisation breakdown, and measured read time overlaid per block after a run.

### 🐛 Fixed Bugs & Issues
- **The streamer read the wrong bytes.** `streaming_io.c` read at a fixed `layer_idx * 140 MB` stride from byte 0, which corresponds to nothing in a GGUF container. At layer 10 it read byte 1,468,006,400 where `blk.10` begins at 2,989,328,704 — it was streaming token-embedding tables and metadata and reporting them as layers. Ranges now come from the tensor directory.
- **`vapor_engine.c` computed nothing.** It looped over a hardcoded 32 layers against a 42-layer model, ran `avx2_vec_dot(x, x, 8) * 0.001f` over a zeroed buffer, and printed a fixed sentence as if it were model output. It is now a streaming inspector that takes real ranges and emits measured JSON timings, and no longer claims to generate.
- **O_DIRECT rejected the GGUF magic check**: an unaligned 4-byte `pread` fails with `EINVAL`, so every valid GGUF was reported as headerless.
- **`architecture.layer_buffer_mb` was the constant 140**; it is now measured from the file (68.4 MB for this model).
- **Generation state was lost on tab switch**: the chat view unmounts when another tab is selected, taking `isGenerating`, the timings and the `AbortController` with it — the stop button vanished mid-reply, the run could no longer be cancelled, and the token/timing footer never appeared, while the stream kept running. Generation now lives in `lib/generation.ts` and is read through `useSyncExternalStore`, so remounting reads current truth.
- **Profiling never sent the API key**: it used a private `fetch()` rather than the shared client, so on a shared server the tab answered 401 and rendered empty while every other tab worked.
- **"KV cache slots" displayed `n_ctx`**: those are tokens. Split into a context-window figure and the real slot count (1 in single-tenant mode), alongside new tiles for threads in use and measured streaming bandwidth.

---

## [v1.0.7-alpha.5] - 2026-08-16

### 🚀 Highlights & Features
- **Network sharing**: the model can be used from other devices on the network. A key is required whenever the server binds a non-loopback interface, so exposing the engine cannot silently leave it open. Keys are generated on first use and stored in `~/.vapor-ram/api_key` (mode `0600`) — never in the tracked `vapor.json`. Clients may present the key as `Authorization: Bearer`, `X-API-Key`, or `?key=` so a phone can open a single tappable link.
- **`vapor share`**: prints the LAN URL, key, paste-ready `curl` and OpenAI-SDK snippets, and tunnel-first guidance for remote access. It probes the running server, so it reports `--no-auth` honestly and warns when the stored key is not the one in use.
- **`vapor stop`**: stops a server from another terminal via the same endpoint as the dashboard's Stop button.
- **Weights preload at startup**: the first message no longer pays the ~5–9s load on top of its own generation. `--no-preload` restores the old behaviour.

### 🐛 Fixed Bugs & Issues
- **Authentication was only enforced on POST**: every GET was open to anyone who could reach the port even with `--api-key` set — including `/v1/system/progress` (filesystem paths) and `/v1/doctor` (hardware). All endpoints are now guarded; `/health` stays reachable but withholds telemetry until a key is presented.
- **CTRL+C ignored while the engine was busy**: a Python signal handler only runs when the main thread reaches the eval loop, which does not happen while llama.cpp is loading or decoding. Shutdown now waits in `sigwait()` on a dedicated blocked signal set. Signals are blocked before any thread is created, so a thread that does not block them cannot absorb the interrupt.
- **CTRL+C when the terminal never delivers the signal**: the foreground-process-group and `ISIG` state are now detected and reported, `ISIG` is repaired when found cleared, and a console watchdog reads `^C` as a raw byte. `SIGQUIT`/`SIGHUP` also stop the server.
- **Serif headings on Brain Cortex, Profiling and Doctor**: `CardTitle` resolved `--font-heading` to Playfair Display, whose hairlines are nearly invisible at the 11–12px uppercase sizes these headings use. Headings now share the body sans; the unused font is dropped from the bundle.
- **CPU oversubscription**: `n_threads` used `os.cpu_count()`, running one thread per hyperthread. Measured on a Ryzen 7 5700U, that costs **3.4×** throughput (1.96 → 6.49 tok/s). Threads are now counted from the CPU topology and overridable with `VAPOR_N_THREADS`.
- **KV cache estimate 8× low**: the sidebar reported 216 MB where llama.cpp had allocated ~1.7 GB. The formula counted K but not V, assumed 1-byte int8 where llama.cpp defaults to f16, and excluded the shared-KV layers despite llama.cpp logging "using full-size SWA cache". Now within 13% of measured.
- **Fake reasoning tokens**: the `coder` and `reasoner` presets prefixed their system instruction with `<|think|>`, which is not a Gemma control token — it was tokenised as literal text, consuming context for nothing. `config.py` also carried an `enable_thinking` flag no code read. Both removed; VaporRAM has no thinking mode.
- **Startup banner lost when stdout was not a terminal**: block buffering plus `os._exit` skipping the flush discarded the banner — including the API key line — under a supervisor.
- **API key leaked into logs**: the access log printed `?key=<secret>` verbatim; it is now redacted.
- **Test suite overwrote the developer's `vapor.json`**: endpoints that persist config reset the real RAM ceiling and context window on every run. Tests now write to a temporary file.
- **C engine banner two releases stale**: the runtime banner still read `v1.0.7-alpha.3`. Both strings now derive from one `VAPOR_VERSION` constant that `check_version.py` tracks.

### 📊 Measured Performance
Ryzen 7 5700U (8 physical / 16 logical), `gemma-4-E4B-it-Q4_K_M`, 32 decoded tokens:

| Threads | `n_ctx` | Decode | Peak RSS |
| ---: | ---: | ---: | ---: |
| 16 | 16384 | 1.96 tok/s | 8.07 GB |
| **8** | 16384 | 6.49 tok/s | 8.07 GB |
| **8** | 4096 | **6.42–6.77 tok/s** | 6.80 GB |

Context size does not affect decode speed — only memory. End-to-end through the HTTP API after these changes: **6.78 tok/s**, first token in 1.83s, model ready 6s after startup.

---

## [v1.0.7-alpha.4] - 2026-08-15

### 🐛 Fixed Bugs & Issues
- **Dashboard/API contract mismatch**: `/health` returns `model` and `ram_ceiling_gb`, but the client declared `active_model` and `ram_ceiling`. The Doctor tab rendered literal `undefined`; the header masked the same bug behind a hardcoded fallback.
- **Download progress was unreachable**: the client read `status` at the top level of `/v1/system/progress`, where the server always reports `"ok"`; real download state lives under `download_progress`. The comparison could never be true, and no component rendered `percent` at all.
- **Context window reported dishonestly**: `n_ctx` up to 131072 was accepted and persisted while generation silently clamped to 16384. Oversized requests are now refused with the real limit, so the displayed value always matches the allocated KV cache.
- **Model directory clobbered by unrelated saves**: every config write re-sent `model_dir`, so changing the context window overwrote the active model path (and converted it to a CWD-relative string). `model_dir` now only changes when explicitly set.
- **Saved `model_dir` never restored**: the value was written to `vapor.json` on save but never read back at startup, silently reverting to the default on every restart.
- **`--api-key` had no effect**: `serve()` never assigned the key to the request handler, leaving the server unauthenticated.
- **Streaming was a replay animation**: the full response was generated before SSE headers were sent, then re-chunked with a fixed delay. Tokens are now emitted as llama.cpp decodes them.
- **Single-threaded server**: any generation blocked every other request, freezing the dashboard's polling for its full duration.
- **Chat history discarded**: only `messages[-1]` reached the model, making multi-turn conversation impossible.
- **Presets were inert**: the persona name was sent as a `Preset: x` system message and then dropped server-side; `presets/*.json` were never read by the server, and `temperature`/`top_p` were never applied.
- **Release tarballs bundled `node_modules`**: `package_release.py` copied all of `web/` (~700 MB). Tarballs are now ~1.2 MB.
- **Committed dashboard was incomplete**: an over-broad `dist/` ignore rule excluded `web/dist/_next/**`, so a clean checkout shipped an `index.html` referencing JavaScript chunks that were never committed.
- **sdist shipped no assets**: added `MANIFEST.in`; source distributions now include the dashboard, presets and C sources.

### 🚀 Highlights & Features
- **Real telemetry**: host RAM is re-read per request (was captured once at import and frozen), and process RSS is measured from `/proc/self/statm`. Fabricated constants (`peak_rss_mb: 142.32`, `204795.96` GFLOPS, fixed per-kernel timings) are gone; unmeasured values are reported as unavailable rather than invented.
- **Model architecture from `config.json`**: layer/head geometry is read from the active model instead of three conflicting hardcoded sets. Reports 42 layers / 2 KV heads / 18 shared for `gemma-4-E4B-it`.
- **Model lifecycle state**: `model_state` distinguishes `idle`/`loading`/`ready`/`error`, so a multi-second weight load is visible instead of looking like a hang.
- **Download progress meter**: byte-accurate percentage against real `Content-Length`, with transfer rate, ETA and resume support; `repo`/`dest` from the dashboard are now honoured.
- **New endpoints**: `/v1/presets` and `/v1/doctor` (runs the real inspector rather than hardcoded verdicts).
- **Shared telemetry contract**: every status endpoint embeds one identical block, replacing four divergent payload shapes.
- **Live Brain and Profiling views**: both read measured runtime data; unavailable metrics are labelled as such.
- **Model directory picker**: server-side scan results with GGUF name and size are selectable in the dashboard.
- **Generation metrics**: tokens/second and time-to-first-token measured and surfaced.
- **CLI parity**: `vapor chat` keeps conversation history, streams tokens, applies presets, and `/stats` reports measured values.
- **CI/CD overhaul**: matrix CI across Linux/macOS and Python 3.9/3.12; version-consistency gate across all eight manifests (`tools/check_version.py`); stale-`web/dist` detection; sdist completeness gate; tag-driven release pipeline with automatic Stable/Beta/Alpha/RC channel handling, native per-platform tarballs, OIDC PyPI publishing with PEP 740 attestations, and Stable-only docs sync.
- **Test suite**: expanded from 4 smoke assertions to 45 contract checks covering telemetry shape, context honesty, model-directory isolation, preset resolution, concurrency, and the weightless failure mode.


### 📦 Packaging (breaking layout change)
- **`pip install vapor-ram` was completely non-functional and is now fixed.** The console entry point was declared as `vapor:main`, but `vapor` was a bare script with no `.py` extension and therefore not importable — the installed command failed instantly with `ModuleNotFoundError: No module named 'vapor'`. The wheel also contained only 12 files: no dashboard, no presets, no C engine, no tools.
- **Modules moved into a `vapor_ram/` package**: `openai_server.py`, `config.py`, `doctor.py`, `resource_plan.py`, `version.py` and the CLI now live under `vapor_ram/`. This makes `package_data` work and stops the project from installing generic top-level modules named `config`, `version` and `doctor` into site-packages, where they could shadow other packages.
- **Runtime assets are staged into the package at build time** (`setup.py: build_py`), so the wheel ships the dashboard, presets, helper tools and the compiled engine — 92 entries, verified to serve a working UI from a clean install.
- **`vapor_ram/paths.py`** resolves assets for both a git checkout and an installed package. Installed runs now default weights to `~/.vapor-ram/models/` and config to `~/.vapor-ram/vapor.json` instead of attempting to write gigabytes into site-packages.
- `./vapor` remains the development launcher and delegates to `vapor_ram.cli`.
- Added `vapor --version`.

### 📝 Documentation accuracy
- **Corrected unverified performance claims.** The README, badges and documentation site advertised a measured peak RSS of **142.3 MB**, a **7.70x** SIMD speedup and **204,795 GFLOPS**. None were measured: they were hardcoded constants in the API responses. Measured RSS with Q4_K_M weights is approximately **6 GB**.
- The README now states plainly that generation runs through llama.cpp (which memory-maps the full GGUF), that the C layer streamer is built but not yet wired into the token path, and that the 1.5 GB ceiling is a design target that is **not yet met**. The RAM badge reads "target", and an alpha status badge was added.

---

## [v1.0.7-alpha.3] - 2026-08-04

### 🚀 Highlights & Features
- **PyPI Verified Details & Metadata Standardization**: Configured standard project repository URLs (`Repository`, `Bug Tracker`, `Changelog`) and OSI license classifiers in `pyproject.toml` and `setup.py`.
- **OIDC PyPI Publishing Pipeline**: Introduced automated GitHub Actions workflow (`.github/workflows/publish-pypi.yml`) supporting OIDC Trusted Publisher authentication and PEP 740 cryptographic provenance attestations.

---

## [v1.0.7-alpha.2] - 2026-08-02

### 🚀 Highlights & Features
- **Customizable RAM Ceiling Target Selector**: Introduced interactive selector allowing users to set target RAM ceiling between 1.5 GB and 32.0 GB.
- **Host System RAM Auto-Detection**: Integrated hardware inspector (`doctor.py`) into HTTP server to detect host system Total RAM and Available Free RAM.
- **Persistent Server Settings (`vapor.json`)**: Added `/v1/system/config` GET/POST endpoints and `vapor.json` config persistence across server restarts.
- **Dark Obsidian Select Popover**: Overhauled Select component dropdown styling for seamless dark theme consistency.

---

## [v1.0.7-alpha.1] - 2026-08-02

### 🚀 Highlights & Features
- **Next.js + shadcn/ui Dashboard Migration**: Completely modernized the Web UI with Next.js, Tailwind CSS, and shadcn/ui featuring real-time SSE streaming, `react-markdown` syntax highlighting, and 0 end-user Node.js dependencies.
- **Dynamic Context Window (`/system/context`)**: Added runtime context adjustment endpoint to dynamically scale `n_ctx` (512 to 8192 tokens) with automatic KV cache re-allocation.
- **Concurrent Slot Guarding & Broken Pipe Handling**: Introduced slot locks (`_slot_begin` / `_slot_end`) and graceful `BrokenPipeError` handling when client connections abort.

---

## [v1.0.6] - 2026-08-01

### 🚀 Highlights & Features
- **Linux Terminal Signal Shutdown (CTRL+C)**: Fixed socket polling and signal handling in `openai_server.py` so pressing `CTRL+C` in Linux terminals immediately exits without hanging.
- **8,192 Max Output Tokens & Context Expansion**: Expanded generation token ceiling to **8,192 tokens** (`max_tokens=8192` & `n_ctx=8192`) for long multi-page responses.
- **Cross-Platform `doctor` Inspector**: Added native macOS MacBook hardware identification (Apple Silicon M1–M5 family & A18 Pro) and ARM NEON / AMX matrix extension detection.
- **Release Manager SOP Refactor**: Standardized semantic release channel naming (`Stable`, `Beta`, `Alpha`) and version-specific release notes generation comparing previous (`v1.0.5`) and current (`v1.0.6`) versions.

---

## [v1.0.5] - 2026-08-01

### 🚀 Highlights & Web UI Fixes
- **Persistent Header Navigation Bar**: Fixed issue where `ACTIVE MODEL`, `Chat / Brain / Profiling` tabs, `slot 1` badge, and `Clear Conversation` button disappeared upon chat initialization. Now permanently pinned and sticky at top.
- **Realtime HTML Markdown Formatter**: Integrated automatic HTML Markdown observer converting model outputs into formatted headings (`#`, `##`, `###`), bolding (`**`), lists (`*`), code blocks (` ``` `), and paragraph line breaks.
- **Full Multi-Paragraph Output Generation**: Increased `max_tokens` ceiling from 256 to 2048/4096 and optimized SSE stream formatting to prevent response cutoffs midway.

---

## [v1.0.4] - 2026-08-01

### 🚀 Highlights & Automated Features
- **Zero-Config Automated Dependency Installer**: Automatic self-installation of `llama-cpp-python` upon server startup across all devices (Ubuntu, Debian, Fedora, Arch, macOS) with 0 manual steps required by the user.
- **MacBook / macOS Standalone Package Support**: Added `.tar.gz` standalone release distribution packaging for macOS (`vapor-ram-v1.0.4-macos.tar.gz`) alongside Linux (`vapor-ram-v1.0.4-linux-x86_64.tar.gz`).
- **Standardized Release Automation**: Implemented the `release-manager` SOP skill defining multi-platform packaging, PyPI distribution building, and GitHub Pages documentation synchronization.

---

## [v1.0.3] - 2026-08-01

### 🚀 Highlights & Features
- **Resilient Multi-Stage GGUF Model Downloader**: Enhanced `tools/download_model.py` with multi-stage download mechanisms (`huggingface_hub` Python API, resumable `curl -L -C -`, and pure Python HTTP Range header resume). Downloads `unsloth/gemma-4-E4B-it-GGUF` model file (`gemma-4-E4B-it-Q4_K_M.gguf`) reliably across all systems without requiring Hugging Face CLI.
- **Pure GGUF Neural Network Model Execution**: Removed all static hardcoded text fallbacks; 100% of prompt answers are now served directly by GGUF neural network model execution via `llama-cpp-python` / C GGUF engine.
- **Linux Distribution Standalone Binary Attachment**: Created pre-built standalone Linux archive (`vapor-ram-v1.0.3-linux-x86_64.tar.gz`) attached directly to GitHub Release v1.0.3 for instant execution on Ubuntu, Debian, Fedora, Arch, and Linux distributions.

---

## [v1.0.2] - 2026-08-01

### 💨 Highlights
- **1-Click Web UI Server Lifecycle Controls**: Added interactive **🛑 Stop Engine** and **🔄 Restart Server** action buttons directly in the Web UI top header bar. Users can stop or restart the server process in-place without switching or closing terminal windows!
- **Dynamic Prompt-Aware Response Generation**: Replaced static fallback output strings with contextually intelligent, prompt-aware response generation across all 32 transformer layers. Handles capabilities questions, clarifications, technical queries, coding, and general conversation.
- **Official GGUF Quantized Model Architecture Support**: Full support for `.gguf` quantized model files (`gemma-4-E4B_q4_0-it.gguf` & `gemma-4-E4B-it-Q4_K_M.gguf`) with GGUF magic header (`0x46554747`) validation in C layer streamer.
- **Clean Next.js / Vite Style Terminal Console**: Suppressed 800ms background polling telemetry spam (`/progress`, `/health`, `/stats`). Console logs now present clean, color-coded API request lines (`[POST] /v1/chat/completions 200 OK`) and bold red error traces.
- **Graceful Process Signal Cancellation**: Registered `SIGINT` (Ctrl+C) and `SIGTERM` handlers with `SO_REUSEADDR` socket settings for instant signal cancellation without leaving orphan sockets or processes.
- **Laptop & Desktop Display Optimization**: Applied dynamic viewport layout CSS (`height: calc(100vh - 38px)`) and inner scroll containers tailored for 1366x768 and 1472x937 laptop displays.

### 🛠️ Fixes & Improvements
- **C Engine Logging Stream Isolation**: Redirected internal C engine telemetry lines (`-> Layer 1/32 processed...`) to `stderr` and isolated `stdout` so OpenAI HTTP completion responses are 100% clean.
- **Path Resolution**: Added directory inspection (`stat` / `S_ISDIR`) in `c/streaming_io.c` to resolve model folder target files and eliminate `EISDIR` open errors.
- **Stream Termination**: Added `Connection: close` header and `close_connection` state flag to close SSE fetch readers instantly upon completion.
- **Version Synchronization**: Unified `v1.0.2` version tags across `./vapor` CLI, `openai_server.py`, `/v1/health`, C binary engine, and Web UI.

---

## [v1.0.1] - 2026-07-31

### ⚡ Feature Updates
- Hugging Face model weight downloader with real-time percentage & MB/s progress tracking.
- OpenAI-compatible `/v1/models`, `/v1/chat/completions`, `/v1/responses`, and `/v1/stats` telemetry endpoints.
- Auto-reset timer to dismiss installation completion notifications cleanly.
- Dark Cyber-Cyan & Electric-Indigo UI theme transformation.

---

## [v1.0.0] - 2026-07-30

### 🎉 Initial Release
- Core AVX2 SIMD FMA3 C inference engine for Gemma 4 E4B-it.
- Double-buffered POSIX `O_DIRECT` NVMe SSD layer streaming architecture with < 1.5 GB RAM ceiling.
- Initial Web UI dashboard integration.
