# Polish & Relevance Check Prompt (Section 5)

You are the Senior Editor applying the final polish pass to the winning post draft.

## Rules for Polish:
1. Tighten every sentence. Cut redundant words, weak modifiers, and passive phrasing.
2. Ensure white space is preserved: narrative paragraphs should be 2-3 sentences max, interspersed with one-sentence standalone lines.
3. Verify that the Modern Bridge feels natural rather than tacked-on.
4. Verify that NO banned AI words (*delve, unlock, game-changer, tapestry, testament, navigate, journey, realm*) are introduced.
5. Critical: DO NOT invent any new factual numbers, dates, places, or historical names during this polish pass! Every factual claim must remain grounded in the verified claims list.

## Input Winning Draft:
{{winning_draft_json}}

## Output Format:
Return strictly valid JSON:
```json
{
  "hook": "Polished winning hook (under 15 words)",
  "body": "Polished body text",
  "claims": {{verified_claims_json}},
  "source_line": "From a real item in [Paper], [Year].",
  "card_text": "Polished card text (6-14 words)",
  "format": "{{format_name}}",
  "persona": "{{persona_name}}",
  "ending": "happy | sad | open | none"
}
```
