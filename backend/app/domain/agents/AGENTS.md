# Multi-agent domain rules

- Primary owner: development and data lead.
- V1/V2 production agents remain deterministic Python/Pydantic logical components.
- The accepted V3 target uses structured LLM specialist agents behind framework-independent contracts;
  deterministic SafetyPolicyEngine, validation, and fallback remain authoritative.
- Each required agent returns one structured proposal with evidence references and version.
- Agents select or constrain approved candidates; they do not invent catalog items.
- The coordinator selects candidate IDs and cannot remove a safety veto.
- Missing or failed required proposals fail closed through the accepted version's deterministic fallback or
  terminal status; partial proposals never bypass safety.
- Store proposals separately from coordinator and final decision records.
- Changes require unit, golden scenario, reproducibility, and safety veto tests.
