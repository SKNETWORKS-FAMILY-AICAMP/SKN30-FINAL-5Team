# Frontend working rules

- Primary owner: frontend engineer.
- Read `docs/API_CONTRACT.md`, `docs/DOMAIN_RULES.md`, and the current task before editing.
- Do not reproduce safety, duration, return-mode, or coordinator logic in the client.
- Use typed API contracts and stable machine codes; Korean labels belong in presentation resources.
- The client shows a count-up elapsed timer from zero and preserves temporary block progress; elapsed time never decides completion.
- Completion comes only from explicit exercise-block actions and is synchronized through the item-completion API.
- The workout screen keeps elapsed time at the top, the current mascot animation in the center, and ordered exercise blocks at the bottom.
- Home is the signed-in entry point: today's state, the check-in, and the server's final routine stay on that one screen instead of separate check-in and decision screens.
- Home renders the server's decision; the check-in sheet must keep every input a safety decision needs, including discomfort severity and adverse reactions.
- Check-in defaults come from the server's defaults endpoint. The profile is a fallback for that call failing, not a second place to compute the same value.
- Provide loading, empty, network error, auth error, permission-denied, stale-context, non-selectable, and safety-stop states.
- Pain and adverse-reaction screens use serious tone and suppress playful mascot animation.
- Never persist or log auth tokens, emails, full names, or raw health/wearable records.
- API contract changes require backend review and mock/client updates in the same change.
