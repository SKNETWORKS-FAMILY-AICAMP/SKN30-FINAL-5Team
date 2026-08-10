# Multi-agent domain rules

- Primary owner: development and data lead.
- Agents are deterministic Python/Pydantic logical components, not independent services or free-form personas.
- Each required agent returns one structured proposal with evidence references and version.
- Agents select or constrain approved candidates; they do not invent catalog items.
- The coordinator selects candidate IDs and cannot remove a safety veto.
- Missing or failed required proposals make the decision `FAILED`.
- Store proposals separately from coordinator and final decision records.
- Changes require unit, golden scenario, reproducibility, and safety veto tests.
