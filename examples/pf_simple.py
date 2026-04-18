"""Minimal PF round — observer-only."""

import asyncio
import os

from debaterhub import DebateClient, DebateConfig, DebateEventHandler, get_format_spec


class Observer(DebateEventHandler):
    async def on_debate_ready(self, event):
        spec = get_format_spec("pf")
        print(f"PF round ready: {event.topic}")
        print(f"Speech count: {len(spec.speech_order)}")

    async def on_turn_signal(self, event):
        kind = "CX" if event.is_cx else "speech"
        print(f"-> {event.speech_type} ({event.speaker}) [{kind}, {event.time_limit}s]")

    async def on_speech_text(self, event):
        preview = (event.text or "")[:80].replace("\n", " ")
        print(f"  {event.speech_type}: {event.word_count}w - {preview}...")

    async def on_judge_result(self, event):
        print(f"\nWINNER: {event.winner}")


async def main():
    client = DebateClient(
        os.environ["LIVEKIT_URL"],
        os.environ["LIVEKIT_API_KEY"],
        os.environ["LIVEKIT_API_SECRET"],
    )
    config = DebateConfig(
        topic="Resolved: Developed nations have a moral obligation to accept refugees.",
        format="pf",
        debate_mode="ai_ai",
        pf_first_speaker="aff",
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
