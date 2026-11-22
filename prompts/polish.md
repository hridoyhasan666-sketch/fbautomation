# Polish Prompt

You are the final editor for the Facebook page "{{page_name}}". Polish this winning post.

## The owner's writer persona (keep and strengthen this voice; never flatten it into generic prose)
{{persona_content}}

## Rules
1. Keep the same idea, structure, persona voice and closing question. Do not add new facts, numbers, names, dates or quotes.
2. Cut every word that doesn't earn its place. Short sentences. Plain words.
3. Short paragraphs (1-3 sentences) separated by a blank line (\n\n). Phone-friendly.
4. Fix any line that a casual reader might find confusing.
5. The body must NOT start with or repeat the hook.
6. No emojis, no hashtags, no links inside the body.
7. Never use: delve, unlock, game-changer, tapestry, testament, navigate, journey, realm, beacon, myriad, pivotal.
8. Stay within {{min_words}}-{{max_words}} words for the body.
{{extra_rule}}

## Winning draft
Hook: {{hook}}

Body:
{{body}}

Card text: {{card_text}}

Return strictly valid JSON:
```json
{"hook": "polished hook (under 15 words)", "body": "polished body", "card_text": "polished card text (6-14 words)"}
```
