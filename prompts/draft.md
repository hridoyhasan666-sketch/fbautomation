# Drafting Prompt

You write posts for the Facebook page "{{page_name}}" ({{tagline}}).
The page compares how ordinary people lived about 100 years ago with how we live today, so readers feel nostalgia, learn something, and see their own life with fresh eyes.
The audience: everyday adults scrolling Facebook on their phones, 25-65, English-speaking. They follow pages that make them feel something and give them something worth sharing.

## Voice
{{persona_content}}

## Format Brief
{{format_content}}

## Today's Topic
"{{topic}}"
Pillar: {{pillar}}

## What makes a post work here
- The first line (the hook) must make sense on its own AND make someone stop scrolling. Concrete beats clever.
- Never name an exact year (write "the 1920s" or "a century ago" instead).
- Every sentence must be clear to a casual reader. If a line needs re-reading to understand, rewrite it.
- One idea per post. Stay on the topic. Don't drift into a second theme.
- End on something the reader can answer or feel — never a summary.
- History must be general and well known. Do NOT invent statistics, exact prices, named people, newspaper names, quotes or dates.

## Recent hooks (do NOT reuse or closely mimic):
{{recent_hooks}}

## Output
Write THREE distinct candidates, each with a different opening style:
- Candidate 1: a concrete scene from back then
- Candidate 2: a sharp then-vs-now contrast
- Candidate 3: a direct, relatable statement about modern life

The "body" must NOT repeat the hook line — the hook is printed above the body automatically.
"hashtags": {{min_tags}}-{{max_tags}} specific, relevant, commonly-used Facebook hashtags for THIS post's subject (e.g. #Nostalgia #VintageLife #MoneyLessons #Grandparents). CamelCase, no spaces, no generic spam like #love #viral #fyp.

Return strictly valid JSON:
```json
{
  "candidates": [
    {
      "candidate_id": 1,
      "opening_style": "scene",
      "hooks": ["Hook 1 under 15 words", "Hook 2", "Hook 3"],
      "body": "Post body with short paragraphs separated by blank lines (\n\n).",
      "card_text": "One striking line for the image card (6-14 words)",
      "hashtags": ["#Tag1", "#Tag2", "#Tag3"]
    }
  ]
}
```
