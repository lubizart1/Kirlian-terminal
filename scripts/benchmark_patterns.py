# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure pure frame generation; excludes Textual, terminal output and music IO."""

import json
import statistics
import time

from kirlian_terminal.animations import CATALOG, Variation


def measure(variation, width, characters, frames=20):
    start = time.perf_counter()
    for frame in range(frames):
        variation.ribbon_frame(frame / 10, width, characters)
    return (time.perf_counter() - start) * 1000 / frames


def main():
    results = []
    for width in (76, 156, 400):
        for characters in ("dots", "ascii"):
            timings = [(measure(v, width, characters), v.label) for v in CATALOG]
            slowest, label = max(timings)
            results.append(
                {
                    "columns": width,
                    "characters": characters,
                    "catalog_mean_ms": round(statistics.mean(t[0] for t in timings), 3),
                    "slowest_pattern_mean_ms": round(slowest, 3),
                    "slowest_pattern": label,
                    "legacy_filament_mean_ms": round(
                        measure(Variation("filaments", 17), width, characters), 3
                    ),
                }
            )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
