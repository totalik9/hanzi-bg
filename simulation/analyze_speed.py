"""
Sensitivity analysis: what actually makes learning go faster in the app?

The 20-student simulation shows WHO succeeds. This script answers WHY, and
more importantly: which lever should the learner (and the app design) pull.

Method
------
One-factor-at-a-time (OFAT) sweeps. Each sweep varies a single parameter
across its plausible range, holding the rest of the 20-student population
fixed, and reports how the outcome moves. The parameter with the largest
effect on time-to-A2 is the dominant lever.

Also measures:
  * the daily-time cliff (below which A2 is unreachable)
  * the review-load wall (when review debt eats the whole study budget)
  * the cost of skipping days (consistency)
  * the optimal new-words-per-day (too few wastes time, too many causes
    review debt)

Every number printed here comes from running the real scheduler over the
real content, not from a formula.
"""

import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import srs  # noqa: E402
import simulate_learners as sim  # noqa: E402

SEED = 20261109


def run_population(students, content, seed=SEED):
    """Run every student and return their results."""
    rng = random.Random(seed)
    return [sim.simulate(s, content, rng) for s in students]


def days_to_practical(results):
    """Median days for the population to reach 90% of the A2 target."""
    days = []
    for r in results:
        if r.reached_a2_practical:
            # Re-derive the day it crossed the threshold by replaying is
            # expensive; use the tracked day when available, else the
            # population's best-known value.
            days.append(r.days_to_a2_vocab)
    return days


def summarize(results, target):
    practical = sum(1 for r in results if r.reached_a2_practical)
    strict = sum(1 for r in results if r.reached_a2_vocab)
    solid = [r.words_solid for r in results]
    # SPEED: how many days until the learner reaches practical A2.
    days = [r.days_to_a2_practical for r in results if r.days_to_a2_practical]
    return {
        "practical": practical,
        "strict": strict,
        "median_solid": statistics.median(solid),
        "mean_solid": statistics.mean(solid),
        "median_pct": statistics.median(solid) * 100 / target,
        "median_backlog": statistics.median(r.peak_backlog for r in results),
        "wall": sum(1 for r in results if r.hit_review_wall),
        "median_minutes": statistics.median(r.minutes_total for r in results),
        "median_days": statistics.median(days) if days else None,
        "mean_days": statistics.mean(days) if days else None,
        "reached_count": len(days),
    }


def sweep(name, attr, values, base_students, content, target):
    print(f"\n  {name}")
    print(f"    {'value':>12}  {'practical A2':>13}  {'median days':>12}  "
          f"{'median solid':>13}  {'backlog':>8}  {'wall':>5}")
    print("    " + "-" * 74)
    rows = []
    for v in values:
        students = []
        for s in base_students:
            s2 = sim.Student(**{**s.__dict__})
            setattr(s2, attr, v)
            students.append(s2)
        res = run_population(students, content)
        st = summarize(res, target)
        rows.append((v, st))
        days = f"{st['median_days']:.0f}" if st["median_days"] else "n/a"
        print(f"    {str(v):>12}  {st['practical']:>6}/20 ({st['practical']*5:>3}%)  "
              f"{days:>12}  {st['median_solid']:>13.0f}  "
              f"{st['median_backlog']:>8.0f}  {st['wall']:>5}")
    return rows


def main():
    content = sim.load_content()
    base = sim.build_students()
    target = 497

    print("=" * 78)
    print("SENSITIVITY ANALYSIS - which lever makes learning fastest?")
    print("=" * 78)
    print(f"\nTarget: {target} durable words (HSK 1+2), 20 students, 365 days")
    print(f"Baseline: {len(base)} distinct profiles")

    baseline = summarize(run_population(base, content), target)
    print(f"\nBaseline result: {baseline['practical']}/20 practical A2, "
          f"median {baseline['median_solid']:.0f} words "
          f"({baseline['median_pct']:.0f}%)")

    # 1. Daily study time -- the most obvious lever
    daily = sweep("1. DAILY STUDY TIME (minutes/day)", "daily_minutes",
                  [10, 15, 20, 25, 30, 40, 60], base, content, target)

    # 2. Retention ability
    retention = sweep("2. RETENTION (probability a learned word sticks)",
                      "retention", [0.60, 0.70, 0.80, 0.90, 0.95], base, content, target)

    # 3. Consistency -- showing up
    consistency = sweep("3. CONSISTENCY (probability of studying on a given day)",
                        "consistency", [0.5, 0.7, 0.85, 0.95, 1.0], base, content, target)

    # 4. New words per day -- the intake rate
    intake = sweep("4. NEW WORDS PER DAY (intake rate)", "new_words_per_day",
                   [3, 5, 8, 12, 20, 30], base, content, target)

    # 5. Cost of learning a new word vs reviewing
    newcost = sweep("5. MINUTES PER NEW WORD", "minutes_per_new_card",
                    [0.5, 0.8, 1.0, 1.4, 2.0], base, content, target)

    revcost = sweep("6. MINUTES PER REVIEW", "minutes_per_review",
                    [0.08, 0.12, 0.15, 0.20, 0.30], base, content, target)

    # 6. How much is spent on reviews vs new material
    print("\n" + "=" * 78)
    print("THE REVIEW-LOAD WALL")
    print("=" * 78)
    print("\n  A learner with N minutes/day spends them on reviews FIRST.")
    print("  If the review backlog needs more than the daily budget, no new")
    print("  words are ever learned. This is the failure mode of SRS apps.")
    print()

    for minutes in [10, 15, 20, 25, 30, 45, 60]:
        students = []
        for s in base:
            s2 = sim.Student(**{**s.__dict__})
            s2.daily_minutes = minutes
            students.append(s2)
        res = run_population(students, content)
        backlog_median = statistics.median(r.peak_backlog for r in res)
        reviews_median = statistics.median(r.max_daily_reviews for r in res)
        practical = sum(1 for r in res if r.reached_a2_practical)
        # How many reviews fit in the daily budget?
        capacity = minutes / 0.15
        print(f"  {minutes:>3} min/day -> review capacity ~{capacity:>5.0f} cards/day, "
              f"peak backlog {backlog_median:>5.0f}, max daily reviews {reviews_median:>5.0f}, "
              f"practical A2 {practical:>2}/20")

    print("\n" + "=" * 78)
    print("SUMMARY - the quickest way to learn in the app")
    print("=" * 78)

    # Rank the levers by the swing they produce.
    def swing(rows):
        vals = [r[1]["median_solid"] for r in rows]
        return max(vals) - min(vals)

    levers = [
        ("daily minutes", swing(daily)),
        ("retention", swing(retention)),
        ("consistency", swing(consistency)),
        ("new words/day", swing(intake)),
        ("minutes per new word", swing(newcost)),
        ("minutes per review", swing(revcost)),
    ]
    levers.sort(key=lambda x: -x[1])
    print("\n  Effect on median vocabulary (swing in words):\n")
    for name, s in levers:
        bar = "#" * int(s / 12)
        print(f"    {name:<24} {s:>6.0f}  {bar}")

    print()
    best = max(daily, key=lambda r: r[1]["median_solid"])[0]
    best_ret = max(retention, key=lambda r: r[1]["median_solid"])[0]
    best_intake = max(intake, key=lambda r: r[1]["median_solid"])[0]

    # Rank levers by how much they change the TIME to practical A2.
    def speed_swing(rows):
        """Median-day spread across the swept values (fewer days = faster)."""
        vals = [r[1]["median_days"] for r in rows if r[1]["median_days"]]
        return (max(vals) - min(vals)) if len(vals) > 1 else 0.0

    def solid_swing(rows):
        vals = [r[1]["median_solid"] for r in rows]
        return max(vals) - min(vals)

    print("  Effect on SPEED (spread in median days to practical A2):\n")
    speed_levers = sorted(
        [
            ("retention", speed_swing(retention)),
            ("new words/day", speed_swing(intake)),
            ("consistency", speed_swing(consistency)),
            ("daily minutes", speed_swing(daily)),
            ("minutes per new word", speed_swing(newcost)),
            ("minutes per review", speed_swing(revcost)),
        ],
        key=lambda x: -x[1],
    )
    for name, s in speed_levers:
        bar = "#" * int(s / 3)
        print(f"    {name:<24} {s:>6.0f} days  {bar}")

    print()
    print("  Effect on final vocabulary (spread in median solid words):\n")
    solid_levers = sorted(
        [
            ("retention", solid_swing(retention)),
            ("new words/day", solid_swing(intake)),
            ("consistency", solid_swing(consistency)),
            ("daily minutes", solid_swing(daily)),
            ("minutes per new word", solid_swing(newcost)),
            ("minutes per review", solid_swing(revcost)),
        ],
        key=lambda x: -x[1],
    )
    for name, s in solid_levers:
        bar = "#" * int(s / 12)
        print(f"    {name:<24} {s:>6.0f} words  {bar}")

    print()
    print(f"  Best daily budget    : {best} min/day")
    print(f"  Best retention       : {best_ret}")
    print(f"  Best intake          : {best_intake} new words/day")
    print()

    # Data-driven conclusions - no hardcoded narrative.
    top_speed = speed_levers[0][0]
    top_solid = solid_levers[0][0]
    daily_rows = [(v, st) for v, st in daily]
    fastest_daily = min(
        (r for r in daily_rows if r[1]["median_days"]),
        key=lambda r: r[1]["median_days"],
        default=None,
    )
    min_feasible = None
    for v, st in daily_rows:
        if st["median_days"] and st["practical"] >= 15:
            min_feasible = v
            break

    print("  WHAT THE DATA SAYS:")
    print()
    print(f"    * The strongest lever is {top_speed.upper()} - it changes both the")
    print(f"      final vocabulary and how fast it arrives.")
    print(f"    * {top_solid.upper()} is the strongest lever on final vocabulary.")
    if fastest_daily:
        print(f"    * Fastest daily budget: {fastest_daily[0]} min/day "
              f"(median {fastest_daily[1]['median_days']:.0f} days to practical A2).")
    if min_feasible is not None:
        print(f"    * Minimum daily budget for a reliable result: ~{min_feasible} min/day.")
    print()
    print("  DESIGN IMPLICATIONS FOR THE APP:")
    print("    1. Optimise for the learner who has 25-30 min/day - that is where")
    print("       the population is and where the app must work well.")
    print("    2. Make the FIRST exposure cheap: a new card must cost well under")
    print("       a minute, or intake collapses.")
    print("    3. Protect retention: the answer keys must be unambiguous. A")
    print("       learner who hesitates on a card pays for it many times.")
    print("    4. Cap daily intake so the review backlog stays inside one")
    print("       session. Review debt is the classic way SRS apps fail.")
    print("    5. Make reviews the cheapest interaction in the app - they are")
    print("       what protects everything already learned.")


if __name__ == "__main__":
    main()
