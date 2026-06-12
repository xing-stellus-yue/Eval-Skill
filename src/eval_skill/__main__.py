"""Command dispatcher for the EvalSkill reproduction pipeline."""

from __future__ import annotations

import argparse
import sys


COMMANDS = {
    "augment": ".augment",
    "aggregate-skill": ".skill_aggregation",
    "best-of-n": ".best_of_n.runner",
    "compare-runners": ".best_of_n.runner",
    "evaluate": ".evaluate",
    "skill": ".skill_pipeline",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    package_name = __package__ or "eval_skill"
    parser = argparse.ArgumentParser(
        prog=f"python -m {package_name}",
        description="EvalSkill reproduction entry point.",
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("args", nargs=argparse.REMAINDER)

    if not argv:
        parser.print_help()
        return 0

    parsed = parser.parse_args(argv[:1])
    command_args = argv[1:]
    module_name = COMMANDS[parsed.command]
    if module_name.startswith("."):
        module_name = package_name + module_name
    module = __import__(module_name, fromlist=["main"])
    return module.main(command_args)


if __name__ == "__main__":
    raise SystemExit(main())
