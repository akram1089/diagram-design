# Privacy

Diagram Design is a set of instructions, HTML templates, and small local scripts that run inside the AI agent you install it in. It has no server, no accounts, and no telemetry, and it sends nothing to the maintainer.

## What uses the network

- **Fonts.** Generated diagrams and the templates load their fonts from Google Fonts (`fonts.googleapis.com` and `fonts.gstatic.com`) when a browser opens them. Google receives the viewer's IP address and browser details under [its privacy policy](https://policies.google.com/privacy). PNG export renders in a local headless browser, which makes the same request, and standalone SVG export keeps the same font import.
- **Brand onboarding.** If you give the skill a website to take a brand from, your agent fetches a few pages from that site with its own browsing tools. Nothing is fetched unless you ask.
- **Your agent.** Your prompts, files, and diagrams are processed by the agent you use, under that provider's terms. Diagram Design does not change how your agent handles data.

## What stays on your machine

- The draw.io, Mermaid, and Excalidraw importers, the SVG export helper, and the verifiers read and write local files only. They make no network requests.
- Saved brand profiles live in `~/.diagram-design/profiles/`.

## Contact

Ask questions in [GitHub issues](https://github.com/cathrynlavery/diagram-design/issues). Report security problems privately, as described in [SECURITY.md](SECURITY.md).

Last updated 2026-10-01.
