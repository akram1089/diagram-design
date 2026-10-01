# Privacy Policy

Diagram Design is published by LittleMight (Cathryn Lavery). This policy covers the Diagram Design plugin and skill in every host it is installed in, including ChatGPT, Codex, and Claude Code.

Effective 2026-10-01.

Diagram Design is a set of instructions, HTML templates, and small local scripts that run inside the AI agent you install it in. It has no server, no accounts, no analytics, and no telemetry. LittleMight does not receive any data from your use of it.

## Personal data collected

LittleMight collects no personal data through Diagram Design.

When you use it, the plugin works with what you give your agent: a description of the diagram you want, files you ask it to redraw (draw.io, Mermaid, or Excalidraw), and, if you ask for brand onboarding, a website address. That content stays in your agent session and on your machine. The plugin does not ask for payment details, health data, government identifiers, passwords, or other sensitive data, and it does not need any.

## How data is used

The content you provide is used only to produce the diagram you asked for: to choose a diagram type, lay it out, apply your brand colors and fonts, and write the HTML, SVG, or PNG file. It is not used for advertising, profiling, or training, and it is not combined with other data.

## Who receives data

- **Your AI agent's provider.** Your prompts and files are processed by the agent you use (for example OpenAI for ChatGPT and Codex) under that provider's own privacy policy. Diagram Design does not change how your agent handles data.
- **Google Fonts.** Generated diagrams and the templates load their fonts from Google Fonts (`fonts.googleapis.com` and `fonts.gstatic.com`) when a browser opens them. PNG export renders the diagram in a local headless browser, which makes the same request, and standalone SVG export keeps the same font import. Google receives the viewer's IP address and browser details, and may receive the address of the page that loads the fonts, under [Google's privacy policy](https://policies.google.com/privacy). The request names the fonts; it does not contain your diagram's content.
- **Websites you choose for onboarding.** If you ask the plugin to take a brand from a website, your agent fetches a few pages from that site with its own browsing tools. That site sees the request as it would any visit. Nothing is fetched unless you ask.
- **LittleMight.** Nothing. There is no server to send data to.

## Data retention

LittleMight retains no data, because it receives none. Diagrams you generate and brand profiles you save (in `~/.diagram-design/profiles/`) stay on your machine until you delete them. Your agent provider and Google retain data under their own policies.

## Your controls

- Delete generated diagrams and saved profiles at any time; they are ordinary files on your machine.
- Skip brand onboarding, or give it a local folder instead of a website, and no website is fetched.
- Remove the Google Fonts link from a generated file, or open it offline, and it renders with your system's fonts instead. Every font in the templates falls back to a system font.
- Uninstall the plugin at any time from your agent.

## Changes and contact

Changes to this policy are published here with a new effective date, and the full history is in this repository's git log. Ask questions in [GitHub issues](https://github.com/cathrynlavery/diagram-design/issues). Report security problems privately, as described in [SECURITY.md](SECURITY.md).
