"""Simple Langfuse integration test.

Verifies that:
1. Langfuse client connects to the self-hosted instance
2. Traces and spans are created and flushed
3. OpenAI calls are traced via langfuse.openai drop-in
4. SDK SessionTracer works

Run: LANGFUSE_SECRET_KEY=... LANGFUSE_PUBLIC_KEY=... LANGFUSE_BASE_URL=... python tests/test_langfuse.py
"""

import os
import sys


def test_langfuse_trace():
    """Create a simple trace with a span and generation using v4 API."""
    from langfuse import Langfuse

    langfuse = Langfuse()

    # Auth check
    ok = langfuse.auth_check()
    print(f"Auth check: {ok}")

    # Create a trace with a span using context manager
    with langfuse.start_as_current_observation(
        as_type="span",
        name="sdk-integration-test",
        metadata={"test": True, "source": "debaterhub-sdk"},
    ) as trace_span:
        print(f"Trace span created")

        # Nested generation (simulated LLM call)
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="test-generation",
            model="gpt-4o-mini",
            input=[{"role": "user", "content": "Say hello"}],
        ) as gen:
            gen.update(
                output="Hello! This is a test generation.",
                usage={"input": 10, "output": 8},
            )
            print("Generation logged")

        trace_span.update(output={"result": "test completed"})

    # Flush
    langfuse.flush()
    print("Flushed to Langfuse")

    trace_id = langfuse.get_current_trace_id()
    return trace_id


def test_openai_traced():
    """Make a real OpenAI call traced by Langfuse."""
    from langfuse.openai import openai

    print("\nMaking traced OpenAI call...")
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "What is 2+2? Answer in one word."}],
        max_tokens=10,
    )
    print(f"OpenAI response: {response.choices[0].message.content}")

    # Flush langfuse
    from langfuse import Langfuse
    lf = Langfuse()
    lf.flush()
    print("OpenAI trace flushed to Langfuse")


def test_session_tracer():
    """Test the SDK's SessionTracer directly."""
    # Import just the observability module without pulling in the full SDK
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "observability",
        os.path.join(os.path.dirname(__file__), "..", "src", "debaterhub", "observability.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    SessionTracer = mod.SessionTracer

    print("\nTesting SessionTracer...")
    tracer = SessionTracer(
        session_id="test-session-001",
        metadata={"human_side": "aff", "resolution": "Test resolution"},
    )
    print(f"SessionTracer active: {tracer.active}")

    tracer.event("session_connected")
    tracer.event("speech_submitted", metadata={
        "speech_type": "AC",
        "word_count": 150,
        "duration_seconds": 60.0,
    })
    tracer.event("session_disconnected")
    tracer.end()
    print("SessionTracer events flushed")


if __name__ == "__main__":
    # Check env vars
    required = ["LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_BASE_URL"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print("=== Test 1: Basic Langfuse trace ===")
    test_langfuse_trace()
    print("SUCCESS\n")

    print("=== Test 2: Traced OpenAI call ===")
    if os.environ.get("OPENAI_API_KEY"):
        test_openai_traced()
        print("SUCCESS\n")
    else:
        print("SKIPPED (no OPENAI_API_KEY)\n")

    print("=== Test 3: SDK SessionTracer ===")
    test_session_tracer()
    print("SUCCESS\n")

    print(f"All tests passed! Check https://langfuse.my-desk.ai for traces.")
