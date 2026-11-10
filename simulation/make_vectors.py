"""
Generates the shared test vectors used to prove the Python port and the Kotlin
SrsScheduler produce identical results.

Writes:
  app/src/test/resources/srs_vectors.json
  simulation/expected_vectors.json

The Kotlin unit test (SrsSchedulerParityTest) reads the vectors and asserts
the same values the Python implementation produces. If the two ever diverge,
that test fails -- so the simulation can never silently drift away from the
app it is supposed to model.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import srs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Sequences of ratings applied to a single card, with the clock advancing
# between reviews. Each sequence exercises a different path through the
# state machine.
SEQUENCES = {
    "straight_good": ["GOOD"] * 8,
    "always_again": ["AGAIN"] * 6,
    "mixed": ["GOOD", "HARD", "AGAIN", "GOOD", "EASY", "GOOD", "GOOD", "HARD"],
    "sloppy": ["AGAIN", "AGAIN", "HARD", "GOOD", "AGAIN", "EASY", "HARD", "GOOD", "GOOD"],
    "easy_streak": ["EASY"] * 7,
    "recover": ["AGAIN", "AGAIN", "GOOD", "GOOD", "GOOD", "GOOD", "GOOD"],
    "harsh": ["HARD", "HARD", "HARD", "HARD", "HARD", "GOOD"],
    "late_good": ["GOOD", "GOOD", "GOOD", "GOOD", "AGAIN", "GOOD", "GOOD", "GOOD", "GOOD"],
}

NOW_START = 1_700_000_000_000
NOW_STEP = 86_400_000  # one day between reviews


def build():
    vectors = {}
    expected = {}
    for name, ratings in SEQUENCES.items():
        steps = []
        state = None
        now = NOW_START
        for rating in ratings:
            state = srs.schedule(state, rating, now)
            steps.append({
                "rating": rating,
                "now": now,
                "dueAt": state.due_at,
                "stability": round(state.stability, 9),
                "difficulty": round(state.difficulty, 9),
                "reps": state.reps,
                "lapses": state.lapses,
                "state": state.state,
            })
            now += NOW_STEP
        vectors[name] = {"ratings": ratings, "steps": steps}
        expected[name] = steps

    return vectors, expected


def main():
    vectors, expected = build()

    kotlin_dir = ROOT / "android" / "app" / "src" / "test" / "resources"
    kotlin_dir.mkdir(parents=True, exist_ok=True)
    (kotlin_dir / "srs_vectors.json").write_text(
        json.dumps(vectors, indent=2), encoding="utf-8"
    )
    (ROOT / "simulation" / "expected_vectors.json").write_text(
        json.dumps(expected, indent=2), encoding="utf-8"
    )

    total = sum(len(v["steps"]) for v in vectors.values())
    print(f"Wrote {total} test steps across {len(vectors)} sequences")
    for name, v in vectors.items():
        final = v["steps"][-1]
        print(f"  {name:<16} final state={final['state']} reps={final['reps']} "
              f"lapses={final['lapses']} stability={final['stability']:.4f}")
    print(f"  -> {kotlin_dir / 'srs_vectors.json'}")
    print(f"  -> {ROOT / 'simulation' / 'expected_vectors.json'}")


if __name__ == "__main__":
    main()
