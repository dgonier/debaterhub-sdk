# Debate Formats

The SDK supports IPDA, Lincoln-Douglas (LD), and Public Forum (PF). Each is selected via `DebateConfig.format`. This guide covers speech orders, timings, and integration patterns.

---

## IPDA (default)

7-speech format with interleaved cross-examination.

| # | Speech | Side | Time | CX? |
|---|--------|------|------|-----|
| 1 | AC | AFF | 5:00 | — |
| 2 | AC-CX | NEG asks | 3:00 | ✓ |
| 3 | NC | NEG | 6:00 | — |
| 4 | NC-CX | AFF asks | 3:00 | ✓ |
| 5 | 1AR | AFF | 5:00 | — |
| 6 | NR | NEG | 5:00 | — |
| 7 | 2AR | AFF | 3:00 | — |

```python
from debaterhub import DebateConfig
cfg = DebateConfig(topic="Resolved: X", human_side="aff")  # format="ipda" by default
```

---

## Lincoln-Douglas (LD)

Value-based one-on-one. Same 7-speech structure as IPDA, different timings and philosophical emphasis.

| # | Speech | Side | Time | CX? |
|---|--------|------|------|-----|
| 1 | AC (1AC) | AFF | 6:00 | — |
| 2 | AC-CX | NEG asks | 3:00 | ✓ |
| 3 | NC (1NC) | NEG | 7:00 | — |
| 4 | NC-CX | AFF asks | 3:00 | ✓ |
| 5 | 1AR | AFF | 4:00 | — |
| 6 | NR | NEG | 6:00 | — |
| 7 | 2AR | AFF | 3:00 | — |

Prep time: 4 minutes flex per side.

```python
cfg = DebateConfig(
    topic="Resolved: Justice requires the recognition of animal rights.",
    format="ld",
    human_side="aff",
)
```

**Expected style:** The AFF presents a VALUE (justice, autonomy, rights) and VALUE CRITERION (how we evaluate the value). The NEG may propose competing frameworks. Philosophical grounding (Kant, Mill, Rawls, Aristotle) is typical.

**Common quirks:**
- The 1AR is the hardest speech — 4 minutes to cover 7 minutes of NC
- The NR collapses to the strongest NEG ballot story

---

## Public Forum (PF)

Lay-judge-friendly, topical, with paired crossfires. 11 speeches.

| # | Speech | Side | Time | CX? |
|---|--------|------|------|-----|
| 1 | PF-AC | AFF | 4:00 | — |
| 2 | PF-NC | NEG | 4:00 | — |
| 3 | PF-CF1 | both | 3:00 | ✓ |
| 4 | PF-AR | AFF | 4:00 | — |
| 5 | PF-NR | NEG | 4:00 | — |
| 6 | PF-CF2 | both | 3:00 | ✓ |
| 7 | PF-ASUM | AFF | 3:00 | — |
| 8 | PF-NSUM | NEG | 3:00 | — |
| 9 | PF-GCF | both | 3:00 | ✓ |
| 10 | PF-AFF-FF | AFF | 2:00 | — |
| 11 | PF-NEG-FF | NEG | 2:00 | — |

Prep time: 3 minutes per side.

```python
cfg = DebateConfig(
    topic="Resolved: The United States should prioritize renewable energy over fossil fuels.",
    format="pf",
    human_side="aff",
    pf_first_speaker="aff",   # result of coin flip
)
```

### Crossfire semantics

PF crossfires are **bidirectional**: both sides can ask and answer. The SDK's `DebateTurnTracker` reports `is_human_turn=True` during any crossfire regardless of which side the human is on.

```python
if session.tracker.is_cx and session.tracker.current_speech in ("PF-CF1", "PF-CF2", "PF-GCF"):
    # Either participant can send cx_question or cx_answer
    await session.submit_cx_question("Why is your evidence more recent?")
```

### PF limitations (v1)

- `pf_first_speaker="neg"` is accepted by `DebateConfig` but the current backend always runs AFF-first. NEG-first support is tracked for v2.
- Grand Crossfire (PF-GCF) is modeled as a 1v1 exchange here, not a 4-person round.

---

## Switching formats mid-session

Not supported. A session is created with one format; to change, close the session and create a new one.

---

## Format constants reference

```python
from debaterhub import get_format_spec

ipda = get_format_spec("ipda")
print(ipda.speech_ids)            # ['AC', 'AC-CX', 'NC', 'NC-CX', '1AR', 'NR', '2AR']
print(ipda.speech_time_limits)    # {'AC': 300, ...}

ld = get_format_spec("ld")
print(ld.speech_time_limits["AC"])   # 360 (6 min, differs from IPDA 300)

pf = get_format_spec("pf")
print(len(pf.speech_order))       # 11
print(pf.first_speaker_configurable)  # True
```

---

## Quality note (IMPORTANT)

The current backend model (`dgonier/ipda-iter3-grpo-final`) was trained on IPDA. LD and PF support is implemented via **prompt engineering only** — no format-specific fine-tuning has been done.

Expected quality ranking (as of 2026-04):
- **IPDA**: Production quality
- **LD**: Acceptable for practice; philosophical depth may be shallow
- **PF**: Acceptable for practice; crossfire quality is weakest area

Planned next steps: format-specific SFT + GRPO training runs on LD and PF exemplars.

---

## Worked Examples

### Example 1: LD round with the human on NEG

```python
import asyncio
from debaterhub import DebateClient, DebateConfig, DebateEventHandler


class LDHandler(DebateEventHandler):
    async def on_debate_ready(self, event):
        print(f"LD round ready: {event.topic}, human is NEG")
        print(f"Speech order: {event.speech_order}")

    async def on_turn_signal(self, event):
        print(f"Turn: {event.speech_type} ({event.speaker}), {event.time_limit}s")

    async def on_speech_text(self, event):
        print(f"  [{event.speech_type}] AI said {event.word_count} words")


async def main():
    client = DebateClient("wss://lk.example.com", "key", "secret")
    config = DebateConfig(
        topic="Resolved: A just society ought not use the death penalty.",
        format="ld",
        human_side="neg",
    )
    handler = LDHandler()
    session = await client.create_managed_session(config, handler)

    # Wait through AI's AC (the human's first turn is AC-CX — asking NEG CX questions)
    while not session.tracker.is_complete:
        await asyncio.sleep(1)

    await session.disconnect()
    await client.close()


asyncio.run(main())
```

### Example 2: PF round with custom event handling

```python
import asyncio
from debaterhub import (
    DebateClient, DebateConfig, DebateEventHandler, get_format_spec,
)


class PFHandler(DebateEventHandler):
    def __init__(self, session_ref):
        self._session = session_ref

    async def on_turn_signal(self, event):
        if event.speech_type.startswith("PF-CF") or event.speech_type == "PF-GCF":
            print(f"=== CROSSFIRE: {event.speech_type} ===")


async def main():
    client = DebateClient("wss://lk.example.com", "key", "secret")
    config = DebateConfig(
        topic="Resolved: Developed nations have a moral obligation to accept refugees.",
        format="pf",
        human_side="aff",
        pf_first_speaker="aff",
    )

    session_ref = [None]
    handler = PFHandler(session_ref)
    session = await client.create_managed_session(config, handler)
    session_ref[0] = session

    spec = get_format_spec("pf")
    print(f"PF round with {len(spec.speech_order)} speeches")

    while not session.tracker.is_complete:
        await asyncio.sleep(1)

    await session.disconnect()
    await client.close()


asyncio.run(main())
```
