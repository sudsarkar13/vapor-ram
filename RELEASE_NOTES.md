# v1.0.7-beta.3 — Beta Release

## 🔄 What's Changed (v1.0.7-beta.2 ➔ v1.0.7-beta.3)

### Reasoning effort levels

Reasoning is no longer just on or off. Four levels, defaulting to **High**:

| Level | Behaviour | Budget |
| --- | --- | ---: |
| Low | A few quick steps. Fastest, best for simple questions. | ~256 tokens |
| Medium | Covers the main steps without labouring them. | ~768 tokens |
| **High** | Works through the problem and checks itself. **Default.** | ~2,048 tokens |
| Extra high | Explores alternatives and verifies each step. Slowest. | ~4,096 tokens |

Set it in the sidebar, from the CLI, or per request:

```bash
vapor serve --think-level low
vapor run --think-level xhigh "..."
```

```json
{"messages": [...], "reasoning_effort": "medium"}
```

The setting persists to `vapor.json`, and an invalid level is refused with the
valid set named rather than silently accepted.

**How the levels work, stated plainly.** The model's chat template has no
effort parameter — it takes only a boolean — so these are VaporRAM's own. Each
level contributes a depth instruction placed alongside the thinking token at
the top of the system turn, ahead of any persona instruction so a preset cannot
override it, together with a reasoning-token budget surfaced in the UI. The
instruction is what actually steers depth; nothing here is a model-native knob,
and it is not presented as one.

### Fixed

- **The reasoning switch rendered broken.** Its knob used `translate-x-4.5`,
  which Tailwind does not generate — the emitted CSS was a stray
  `.translate-x-4` plus an invalid `.translate-x-`, leaving the knob sitting
  outside its track. It is now positioned with `left` values Tailwind does
  emit, and the built stylesheet is checked for the rule.

## ⚠️ Known Limitations

- **RAM ceiling unmet**: 6.8–8.1 GB measured against a 1.5 GB target. The C
  streamer is a measurement path, not the token path.
- The model decides whether a question warrants reasoning, so a Thinking block
  will not appear on every reply regardless of level.
- Per-kernel attribution is not instrumented, so it is omitted rather than
  estimated.

## 📦 Install

```bash
pip install --pre vapor-ram==1.0.7b3
```
