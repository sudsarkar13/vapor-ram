# v1.0.7-beta.2 — Beta Release

## 🔄 What's Changed (v1.0.7-beta.1 ➔ v1.0.7-beta.2)

Reasoning works, and adding it exposed a much older bug.

### The prompt format was wrong in every request ever sent

`build_prompt` used `<start_of_turn>` / `<end_of_turn>`. Checked against the
GGUF vocabulary, **those strings are not in this model's vocabulary at all** —
they tokenised as literal text. The real markers are `<|turn>` (token 105) and
`<turn|>` (106, which is also EOS). The stop sequences had the same defect and
never matched a real token. The template also opens a `<|turn>system` turn, so
folding system instructions into the first user message was wrong too.

This had been quietly degrading every response since the beginning.

### Reasoning

`gemma-4-E4B-it` supports it natively: its chat template takes an
`enable_thinking` flag, injects `<|think|>` (token 98) at the top of the system
turn, and emits the thought process inside `<|channel>thought … <channel|>`.

Support is detected by reading the template out of the GGUF, so the switch only
appears when it would actually do something. On by default.

```bash
vapor serve --no-think      # off for this server
vapor run --think "..."     # on for one prompt
vapor chat                  # /think toggles mid-session
```

Per request: `{"thinking": false}`. Over the API reasoning streams on its own
`delta.reasoning_content` field, so a client that ignores it gets the answer
alone rather than the thoughts mixed in.

In the dashboard the reasoning appears above each reply, animating as it
streams and **open by default** so it can be read while it arrives.

### Also fixed

- **No cache headers were sent for the dashboard.** Browsers applied their own
  heuristic caching to `index.html` and could keep serving a previous build
  after an upgrade — new UI would simply never appear. `index.html` is now
  `no-cache`; content-hashed assets are `immutable`.
- **Timings counted only answer tokens**, which made a 19-second reasoning pass
  read as "0.22 tok/s". `reasoning_tokens` and `first_answer_ms` are reported
  separately and throughput covers everything produced.
- **Reasoning shares the `max_tokens` budget** with the answer and can consume
  all of it on a hard question. That is detected and explained rather than
  returning an empty reply.

### Correction to the v1.0.7-alpha.6 notes

Those notes called `<|think|>` "not a Gemma control token" and removed it from
the presets on that basis. That was wrong. It is token 98 and is this model's
real reasoning token. It genuinely did nothing before — but because it sat
inside a preset's `system_instruction` that the old prompt builder folded into
a user turn, not because the token was meaningless.

## ⚠️ Known Limitations

- **RAM ceiling unmet**: 6.8–8.1 GB measured against a 1.5 GB target. The C
  streamer is a measurement path, not the token path.
- The model decides whether a question warrants reasoning; simple prompts are
  answered directly, so a Thinking block will not appear every time.
- Per-kernel attribution is not instrumented, so it is omitted rather than
  estimated.

## 📦 Install

```bash
pip install --pre vapor-ram==1.0.7b2
```
