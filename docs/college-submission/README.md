# College Submission Package

Everything here describes the project as it actually exists. Replace the *italic placeholders*
(name, guide, college) and add real screenshots; do not add features or numbers that are not in the
repository or in `reports/FINAL_TEST_REPORT.md`.

| File | Purpose |
|---|---|
| [01-project-report.md](01-project-report.md) | Final project report (abstract to references, 25 sections) |
| [02-synopsis.md](02-synopsis.md) | One-page synopsis |
| [03-presentation-outline.md](03-presentation-outline.md) | 18-slide presentation content with speaker notes |
| [04-demo-script.md](04-demo-script.md) | 12-minute live demonstration script |
| [05-viva-questions.md](05-viva-questions.md) | 25 viva questions with answers |
| [06-screenshot-checklist.md](06-screenshot-checklist.md) | Screenshots to capture yourself |
| [api-reference.md](api-reference.md) | Every route and its permission (generated) |
| [diagrams/](diagrams/) | Mermaid sources: architecture, DFD level 0 and 1, ER diagram, request/RBAC flow |

Render the diagrams with the GitHub preview, <https://mermaid.live>, or `npx @mermaid-js/mermaid-cli`.
To export the report: `pandoc 01-project-report.md -o report.docx` (or print from a Markdown viewer).
Regenerate the ER diagram from the code after schema changes with
`python scripts/generate_er_diagram.py > docs/college-submission/diagrams/er-diagram.mmd`.

> The Mermaid sources were written to follow the standard syntax and the ER diagram is generated from
> the code, but no Mermaid renderer was run in the build environment. If a diagram does not render,
> paste it into <https://mermaid.live> to see the exact line to fix.
