#!/usr/bin/env python3
"""Keep maintainer policy aligned with package manifests and CI truth.

``gates.local_commands`` in ``.maintainer-policy.json`` must list exactly the
gates that ``.github/workflows/ci.yml`` runs, so the local suite a maintainer
runs on a pull request head is the same suite CI enforces. The set of CI gates
is derived from the workflow's ``run:`` steps with these rules:

- Every ``python``/``python3`` invocation of a ``.py`` file is one gate, even
  inside ``$(...)`` or an ``if`` branch. ``python`` is spelled ``python3``
  locally. Steps that only install or print tools (``pip install``,
  ``playwright install``, ``python -c``, ``echo``) are not gates.
- A line starting with ``npx`` is one gate (the Claude plugin validator).
- A ``git diff ... --exit-code`` line checks what the command before it in
  the same step generated, so it joins that command with ``&&`` (the
  build-icons freshness gate). Backslash continuations are joined first.
- Matrix legs and ``if:`` guards (for example the ubuntu/3.12-only steps) do
  not matter: a step that runs on any leg is a gate.
- The version gate depends on the event. Pull requests run
  ``verify-plugin-package.py --require-no-bump <base>`` against a base that
  only exists in CI (``"$BASE_REF"`` or ``HEAD^1``); pushes run
  ``--current-only``. Locally the policy runs ``--require-no-bump
  origin/main``, which performs the current-tree checks plus the base
  comparison. All of these forms are the same gate.
- Any other CI command that mentions ``scripts/`` fails this test until the
  rules above say how it maps to a local command.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / ".maintainer-policy.json"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"

EXPECTED_MANIFESTS = {
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".factory-plugin/plugin.json",
}

REQUIRED_COMMANDS = {
    "python3 scripts/test-maintainer-policy.py",
    "python3 scripts/test-verify-semantic-motion.py",
    "python3 scripts/test-verify-sequence-oauth.py",
    "python3 scripts/test-verify-doctor.py",
    "python3 scripts/test-verify-polar.py",
    "python3 scripts/verify-polar.py",
    "python3 scripts/verify-sankey.py --all",
    "python3 scripts/test-verify-sankey.py",
    "python3 scripts/verify-streamgraph.py --all",
    "python3 scripts/test-verify-streamgraph.py",
    "python3 scripts/verify-bump.py --all",
    "python3 scripts/test-verify-bump.py",
    "python3 scripts/verify-marimekko.py --all",
    "python3 scripts/test-verify-marimekko.py",
    "python3 scripts/verify-beeswarm.py --all",
    "python3 scripts/test-verify-beeswarm.py",
    "python3 scripts/verify-skin-polarity.py --all",
    "python3 scripts/test-verify-skin-polarity.py",
    "python3 scripts/lint-render.py --self-test",
    "python3 scripts/lint-render.py --all",
}

VERSION_GATE = "python3 scripts/verify-plugin-package.py --require-no-bump <base-ref>"

RUN_KEY = re.compile(r"^(?P<prefix>\s*(?:-\s+)?)run:\s*(?P<value>.*?)\s*$")
PYTHON_SCRIPT = re.compile(
    r"(?<![\w./-])python3?\s+(?P<script>[\w./-]+\.py)(?P<args>(?:[ \t]+[^\s;&|()<>]+)*)"
)


def normalize(command: str) -> str:
    """Canonical form shared by CI commands and policy entries."""
    command = " ".join(command.split())
    command = re.sub(r"^python(?=\s)", "python3", command)
    if command.startswith("python3 scripts/verify-plugin-package.py "):
        rest = command[len("python3 scripts/verify-plugin-package.py ") :]
        if rest == "--current-only" or re.fullmatch(r"--require-no-bump \S+", rest):
            return VERSION_GATE
    return command


def run_blocks(workflow: str) -> list[list[str]]:
    """Return the shell lines of every ``run:`` step, without YAML parsing."""
    lines = workflow.splitlines()
    blocks: list[list[str]] = []
    index = 0
    while index < len(lines):
        match = RUN_KEY.match(lines[index])
        index += 1
        if match is None:
            continue
        value = match.group("value")
        if not value.startswith(("|", ">")):
            blocks.append([value])
            continue
        key_column = len(match.group("prefix"))
        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= key_column:
                break
            body.append(line)
            index += 1
        if value.startswith(">"):
            body = [" ".join(line.strip() for line in body if line.strip())]
        blocks.append(body)
    return blocks


def logical_lines(block: list[str]) -> list[str]:
    """Join backslash continuations and drop blank and comment lines."""
    joined: list[str] = []
    pending = ""
    for raw in block:
        line = raw.strip()
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        line = (pending + line).strip()
        pending = ""
        if line and not line.startswith("#"):
            joined.append(line)
    if pending.strip():
        joined.append(pending.strip())
    return joined


def ci_gates(workflow: str) -> tuple[set[str], list[str]]:
    """Return (normalized CI gate commands, CI lines this test cannot map)."""
    gates: set[str] = set()
    unmapped: list[str] = []
    for block in run_blocks(workflow):
        commands: list[str] = []
        for line in logical_lines(block):
            if line.startswith("git diff") and "--exit-code" in line:
                if commands:
                    commands[-1] = f"{commands[-1]} && {line}"
                else:
                    commands.append(line)
                continue
            if line.startswith("npx "):
                commands.append(line)
                continue
            commands.extend(match.group(0) for match in PYTHON_SCRIPT.finditer(line))
            if "scripts/" in PYTHON_SCRIPT.sub("", line):
                unmapped.append(line)
        gates.update(normalize(command) for command in commands)
    return gates, unmapped


def policy_failures(policy: dict, workflow: str) -> list[str]:
    manifests = {entry["path"] for entry in policy["versioning"]["manifests"]}
    commands = set(policy["gates"]["local_commands"])

    failures = []
    if manifests != EXPECTED_MANIFESTS:
        failures.append(
            "versioning.manifests must be exactly {}; found {}".format(
                sorted(EXPECTED_MANIFESTS), sorted(manifests)
            )
        )
    missing_commands = sorted(REQUIRED_COMMANDS - commands)
    if missing_commands:
        failures.append(
            "gates.local_commands omits current CI gates: {}".format(
                ", ".join(missing_commands)
            )
        )

    gates, unmapped = ci_gates(workflow)
    local = {normalize(command) for command in commands}
    for line in unmapped:
        failures.append(
            "ci.yml runs a command this test cannot map to a local gate "
            "(extend scripts/test-maintainer-policy.py): {}".format(line)
        )
    unregistered = sorted(gates - local)
    if unregistered:
        failures.append(
            "gates.local_commands omits gates that ci.yml runs: {}".format(
                ", ".join(unregistered)
            )
        )
    stale = sorted(local - gates)
    if stale:
        failures.append(
            "gates.local_commands lists commands that ci.yml does not run: {}".format(
                ", ".join(stale)
            )
        )
    return failures


SYNTHETIC_POLICY_COMMANDS = [
    "python3 scripts/test-maintainer-policy.py",
    "python3 scripts/verify-plugin-package.py --require-no-bump origin/main",
    "npx --yes @anthropic-ai/claude-code@2.1.229 plugin validate . --strict",
    "python3 scripts/test-lint-a11y.py",
    "python3 scripts/lint-skin.py --all --baseline",
    "python3 scripts/test-verify-polar.py",
    "python3 scripts/verify-polar.py",
    "python3 scripts/test-build-readme-thumbs.py",
    "python3 scripts/build-readme-thumbs.py --check",
    "python3 scripts/lint-render.py --self-test",
    "python3 scripts/lint-render.py --all",
    "python3 scripts/build-icons.py && git diff --ignore-space-at-eol --exit-code -- "
    "skills/diagram-design/assets/icons.html "
    "skills/diagram-design/references/primitive-icons.md",
]

SYNTHETIC_CI = """\
jobs:
  plugin-package:
    steps:
      - name: Verify maintainer policy tracks package and CI truth
        run: python3 scripts/test-maintainer-policy.py

      - name: Forbid manifest version changes in pull requests
        env:
          BASE_REF: ${{ github.event.pull_request.base.sha || '' }}
        shell: bash
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            python3 scripts/verify-plugin-package.py --require-no-bump "$BASE_REF"
          else
            python3 scripts/verify-plugin-package.py --current-only
          fi

      - name: Validate Claude marketplace package without warnings
        run: npx --yes @anthropic-ai/claude-code@2.1.229 plugin validate . --strict

  validate:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - name: Verify accessible SVG contract
        if: always()
        run: python scripts/test-lint-a11y.py

      - name: Run skin linter
        run: python scripts/lint-skin.py --all --baseline

      - name: Verify quantitative polar chart
        shell: bash
        run: |
          python scripts/test-verify-polar.py
          python scripts/verify-polar.py

      - name: Install Pillow for README thumbnail verification
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        run: |
          pip install "Pillow==${PILLOW_VERSION}"
          python -c "import PIL; print('Pillow', PIL.__version__)"

      - name: Verify README thumbnails
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        run: |
          python scripts/test-build-readme-thumbs.py
          python scripts/build-readme-thumbs.py --check

      - name: Install Playwright Chromium
        run: |
          pip install "playwright==${PLAYWRIGHT_VERSION}"
          playwright install --with-deps chromium

      - name: Verify render linter checks
        run: python scripts/lint-render.py --self-test

      - name: Run render linter
        run: python scripts/lint-render.py --all

      - name: Verify generated icon assets
        shell: bash
        run: |
          python scripts/build-icons.py
          git diff --ignore-space-at-eol --exit-code -- \\
            skills/diagram-design/assets/icons.html \\
            skills/diagram-design/references/primitive-icons.md

      - name: Generate CI execution summary table
        run: |
          echo "| Verification Gate | Outcome |" >> $GITHUB_STEP_SUMMARY
"""

MERGE_PARENT_VERSION_GATE = """\
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            if ! git rev-parse -q --verify HEAD^2 >/dev/null; then
              echo "expected the pull request merge commit at HEAD" >&2
              exit 1
            fi
            python3 scripts/verify-plugin-package.py --require-no-bump HEAD^1
          else
            python3 scripts/verify-plugin-package.py --current-only
          fi
"""

EXTRA_GATE_STEP = """
      - name: Verify standalone SVG export
        if: always()
        run: python scripts/test-export-svg-standalone.py
"""

SUBSTITUTED_GATE_STEP = """
      - name: Verify export snippet stalled-load fallback
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        shell: bash
        run: |
          out="$(python scripts/test-export-wait.py)"
          echo "$out" | grep -q "All export-wait cases passed"
"""

UNMAPPED_STEP = """
      - name: Verify something with a shell script
        run: bash scripts/check-something.sh
"""


def synthetic_policy(commands: list[str]) -> dict:
    return {
        "versioning": {"manifests": [{"path": path} for path in sorted(EXPECTED_MANIFESTS)]},
        "gates": {"local_commands": list(REQUIRED_COMMANDS | set(commands))},
    }


def synthetic_ci(extra: str = "") -> str:
    """The synthetic workflow, plus a step running every REQUIRED_COMMANDS gate."""
    required = "".join(
        "\n      - name: Required gate\n        run: {}\n".format(command)
        for command in sorted(REQUIRED_COMMANDS)
    )
    return SYNTHETIC_CI + required + extra


def self_test() -> list[str]:
    """Check the CI-to-policy mapping rules on synthetic workflows."""
    problems: list[str] = []
    old_version_step = SYNTHETIC_CI[
        SYNTHETIC_CI.index("        run: |\n          if [") : SYNTHETIC_CI.index(
            "      - name: Validate Claude"
        )
    ]
    if old_version_step.count("--require-no-bump") != 1:
        return ["self-test fixture drifted: version gate step not found"]
    icons_command = SYNTHETIC_POLICY_COMMANDS[-1]
    cases: list[tuple[str, str, list[str], str | None]] = [
        ("matching workflow and policy", synthetic_ci(), SYNTHETIC_POLICY_COMMANDS, None),
        (
            "HEAD^1 version gate",
            synthetic_ci().replace(old_version_step, MERGE_PARENT_VERSION_GATE + "\n"),
            SYNTHETIC_POLICY_COMMANDS,
            None,
        ),
        (
            "CI gate missing from policy",
            synthetic_ci(EXTRA_GATE_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            "gates.local_commands omits gates that ci.yml runs: "
            "python3 scripts/test-export-svg-standalone.py",
        ),
        (
            "CI gate inside command substitution missing from policy",
            synthetic_ci(SUBSTITUTED_GATE_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            "gates.local_commands omits gates that ci.yml runs: "
            "python3 scripts/test-export-wait.py",
        ),
        (
            "policy command CI does not run",
            synthetic_ci(),
            SYNTHETIC_POLICY_COMMANDS + ["python3 scripts/test-retired.py"],
            "gates.local_commands lists commands that ci.yml does not run: "
            "python3 scripts/test-retired.py",
        ),
        (
            "policy drops the version gate",
            synthetic_ci(),
            [c for c in SYNTHETIC_POLICY_COMMANDS if "verify-plugin-package" not in c],
            "gates.local_commands omits gates that ci.yml runs: " + VERSION_GATE,
        ),
        (
            "icons diff flags drift from CI",
            synthetic_ci(),
            [c for c in SYNTHETIC_POLICY_COMMANDS if c != icons_command]
            + [icons_command.replace("--ignore-space-at-eol ", "")],
            "gates.local_commands lists commands that ci.yml does not run: "
            "python3 scripts/build-icons.py && git diff --exit-code",
        ),
        (
            "unmapped CI command",
            synthetic_ci(UNMAPPED_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            "cannot map to a local gate (extend scripts/test-maintainer-policy.py): "
            "bash scripts/check-something.sh",
        ),
    ]
    for name, workflow, commands, expected in cases:
        failures = policy_failures(synthetic_policy(commands), workflow)
        if expected is None and failures:
            problems.append(f"self-test '{name}': expected no failures, got {failures}")
        elif expected is not None and not any(expected in failure for failure in failures):
            problems.append(f"self-test '{name}': expected {expected!r}, got {failures}")
    return problems


def main() -> int:
    problems = self_test()
    if problems:
        print("FAIL maintainer policy self-test")
        for problem in problems:
            print("  - " + problem)
        return 1

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    failures = policy_failures(policy, workflow)
    if failures:
        print("FAIL maintainer policy")
        for failure in failures:
            print("  - " + failure)
        return 1

    gates, _unmapped = ci_gates(workflow)
    print(
        "OK maintainer policy: {} manifests, {} required current gates, "
        "{} CI gates registered in local_commands".format(
            len(EXPECTED_MANIFESTS), len(REQUIRED_COMMANDS), len(gates)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
