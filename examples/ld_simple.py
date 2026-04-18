"""Minimal LD round via the SDK — observer-only (AI generates both sides).

Usage:
    export LIVEKIT_URL=wss://...
    export LIVEKIT_API_KEY=...
    export LIVEKIT_API_SECRET=...
    python examples/ld_simple.py
"""

import asyncio
import os

from debaterhub import DebateClient, DebateConfig, DebateEventHandler


class Observer(DebateEventHandler):
    async def on_debate_ready(self, event):
        print(f"LD round ready: {event.topic}")
        print(f"Speech order: {event.speech_order}")

    async def on_turn_signal(self, event):
        print(f"-> {event.speech_type} ({event.speaker}) [{event.time_limit}s]")

    async def on_speech_text(self, event):
        preview = (event.text or "")[:80].replace("\n", " ")
        print(f"  {event.speech_type}: {event.word_count}w - {preview}...")

    async def on_judge_result(self, event):
        print(f"\nWINNER: {event.winner} ({event.margin})")


async def main():
    client = DebateClient(
        os.environ["LIVEKIT_URL"],
        os.environ["LIVEKIT_API_KEY"],
        os.environ["LIVEKIT_API_SECRET"],
    )
    config = DebateConfig(
        topic="Resolved: Justice requires the recognition of animal rights.",
        format="ld",
        debate_mode="ai_ai",   # observer mode - both sides AI
        coaching_enabled=False,
        evidence_enabled=False,
    )
    session = await client.create_managed_session(config, Observer())

    while not session.tracker.is_complete:
        await asyncio.sleep(5)

    await session.disconnect()
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
