"""Generate deterministic, synthetic prescription-style OCR training strings."""

from __future__ import annotations

import argparse
import random
from pathlib import Path


def read_values(config_dir: Path, name: str) -> list[str]:
    return [line.strip() for line in (config_dir / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def generate(count: int, seed: int, config_dir: Path) -> list[str]:
    rng = random.Random(seed)
    medicines = read_values(config_dir, "medicines.txt")
    forms = read_values(config_dir, "forms.txt")
    units = read_values(config_dir, "units.txt")
    frequencies = read_values(config_dir, "frequencies.txt")
    durations = read_values(config_dir, "durations.txt")
    instructions = read_values(config_dir, "instructions.txt")
    strengths = [5, 10, 20, 40, 250, 500, 625, 650]
    lines = []
    for _ in range(count):
        parts = []
        if rng.random() < 0.75:
            parts.append(rng.choice(forms))
        parts.extend([rng.choice(medicines), str(rng.choice(strengths)), rng.choice(units)])
        parts.append(rng.choice(frequencies))
        if rng.random() < 0.7:
            parts.append(rng.choice(durations))
        if rng.random() < 0.35:
            parts.append(rng.choice(instructions))
        separator = rng.choice([" ", "  ", " "])
        lines.append(separator.join(parts))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lines = generate(args.count, args.seed, root / "configs")
    content = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
