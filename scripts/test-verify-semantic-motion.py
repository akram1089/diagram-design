#!/usr/bin/env python3
"""Regression tests for verify-semantic-motion.py.

Covers the two entry points (verify_markdown, verify_example) against the
shipped skill docs / animated example, plus a handful of adversarial cases
that mirror the pattern used by test-verify-docs-sync.py and
test-verify-motion.py for the other verifiers in this repo.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-semantic-motion.py"


def load_verifier():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        "diagram_design_verify_semantic_motion", VERIFIER
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-semantic-motion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_verifier()

    # Shipped docs and example must pass as-is.
    markdown_errors = module.verify_markdown()
    if markdown_errors:
        raise AssertionError(f"shipped skill docs failed verify_markdown: {markdown_errors}")
    print("OK: shipped SKILL.md / semantic-patterns.md / animation.md pass verify_markdown")

    example_errors = module.verify_example()
    if example_errors:
        raise AssertionError(f"shipped example failed verify_example: {example_errors}")
    print("OK: shipped policy-trace example passes verify_example")

    original_skill = module.SKILL
    try:
        with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-") as temp_dir:
            scratch = Path(temp_dir)

            # Missing semantic-pattern router link must be rejected.
            missing_router = scratch / "missing-router.md"
            missing_router.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "semantic-patterns.md", "patterns.md"
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_router
            errors = module.verify_markdown()
            if not any("must link to semantic-patterns.md" in error for error in errors):
                raise AssertionError(f"missing semantic router was accepted: {errors}")
            print("OK: missing semantic-pattern router link is rejected")

            # Dropping one of the nine named patterns must be rejected.
            missing_pattern = scratch / "missing-pattern.md"
            missing_pattern.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "Fan-in queue / bottleneck", "Fan-in queue removed"
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_pattern
            errors = module.verify_markdown()
            if not any(
                "does not route semantic pattern: Fan-in queue / bottleneck" in error
                for error in errors
            ):
                raise AssertionError(f"missing semantic pattern was accepted: {errors}")
            print("OK: missing semantic-pattern name is rejected")

            # The new lifecycle route must remain discoverable from SKILL.md.
            missing_lifecycle = scratch / "missing-lifecycle.md"
            missing_lifecycle.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "**Lifecycle phase map** → State Machine",
                    "**Generic lifecycle** → State Machine",
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_lifecycle
            errors = module.verify_markdown()
            if not any(
                "does not route semantic pattern: Lifecycle phase map" in error
                for error in errors
            ):
                raise AssertionError(f"missing lifecycle route was accepted: {errors}")
            print("OK: missing lifecycle phase-map route is rejected")

            # The byte cap is inclusive and measures LF-normalized bytes, so a
            # checkout with core.autocrlf=true measures the same as the
            # committed file (#246). Pad the real SKILL.md after its final
            # newline so every other check still reads the shipped content,
            # and run each boundary with LF and CRLF line endings.
            skill_bytes = original_skill.read_bytes().replace(b"\r\n", b"\n")
            if len(skill_bytes) > 40_000:
                raise AssertionError(
                    f"shipped SKILL.md is already {len(skill_bytes)} bytes; "
                    "the boundary cases need it at or under 40000"
                )
            if skill_bytes.count(b"\n") < 100:
                raise AssertionError("shipped SKILL.md has too few lines to test CRLF")
            for size, expected in (
                (None, []),
                (40_000, []),
                (40_001, ["SKILL.md exceeds 40000 bytes: 40001 bytes"]),
            ):
                lf = skill_bytes if size is None else skill_bytes + b" " * (size - len(skill_bytes))
                for label, content in (("LF", lf), ("CRLF", lf.replace(b"\n", b"\r\n"))):
                    padded = scratch / f"skill-{size}-{label}.md"
                    padded.write_bytes(content)
                    module.SKILL = padded
                    errors = module.verify_markdown()
                    if errors != expected:
                        raise AssertionError(
                            f"SKILL.md byte cap, {label}, "
                            f"{size or 'shipped'} normalized bytes: expected {expected}, got {errors}"
                        )
            # Mixed endings normalize the same way and still fail past the cap.
            over = skill_bytes + b" " * (40_001 - len(skill_bytes))
            head, tail = over[: len(over) // 2], over[len(over) // 2 :]
            mixed = scratch / "skill-mixed.md"
            mixed.write_bytes(head.replace(b"\n", b"\r\n") + tail)
            module.SKILL = mixed
            if module.verify_markdown() != ["SKILL.md exceeds 40000 bytes: 40001 bytes"]:
                raise AssertionError(f"mixed line endings loosened the cap: {module.verify_markdown()}")
            print(
                "OK: SKILL.md passes at 40000 LF-normalized bytes and is rejected at "
                "40001, with LF, CRLF, and mixed line endings alike"
            )

            # The repository pins SKILL.md to LF, so the committed file is what
            # the cap measures. Dropping the pin must fail the gate.
            module.SKILL = original_skill
            unpinned = scratch / "gitattributes"
            unpinned.write_text("*.png binary\n", encoding="utf-8")
            original_attributes = module.GITATTRIBUTES
            module.GITATTRIBUTES = unpinned
            try:
                errors = module.verify_markdown()
            finally:
                module.GITATTRIBUTES = original_attributes
            if not any(".gitattributes must pin" in error for error in errors):
                raise AssertionError(f"missing LF pin for SKILL.md was accepted: {errors}")
            print("OK: .gitattributes must pin SKILL.md to LF")
    finally:
        module.SKILL = original_skill

    # A duplicated HTML/SVG id in the animated example must be rejected.
    with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-example-") as temp_dir:
        source = module.EXAMPLE.read_text(encoding="utf-8")
        first_id_start = source.find(' id="')
        if first_id_start < 0:
            raise AssertionError("shipped example unexpectedly has no id attributes to duplicate")
        # Re-use an existing id value on a second, unrelated element to force a collision.
        quote_start = first_id_start + len(' id="')
        quote_end = source.find('"', quote_start)
        duplicated_id = source[quote_start:quote_end]
        insertion_point = source.rfind("</body>")
        if insertion_point < 0:
            raise AssertionError("shipped example unexpectedly has no </body> to anchor the test")
        broken = (
            source[:insertion_point]
            + f'<div id="{duplicated_id}"></div>'
            + source[insertion_point:]
        )
        broken_path = Path(temp_dir) / "duplicate-id.html"
        broken_path.write_text(broken, encoding="utf-8")
        errors = module.verify_example(broken_path)
        if not any("duplicate HTML/SVG IDs" in error for error in errors):
            raise AssertionError(f"duplicate id was accepted: {errors}")
        print("OK: duplicate HTML/SVG id in the animated example is rejected")

    print("All semantic-motion verifier tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
