# Seed Card Extraction Prompt

You are an expert archive researcher analyzing historical newspaper page text from Chronicling America (Library of Congress, pre-1930).
OCR text from 100+ year old newspapers can be messy, fragmented, or noisy.

Your job is to identify whether this page contains a compelling, human-centered story, ad, price item, advice letter, or curious incident suitable for modern readers, and extract a structured Seed Card.

## Criteria for Selection:
- Must have a clear human need or emotional core (debt, pride, lonely hearts, bizarre dispute, bargain, strange invention).
- Must have a natural modern mirror (modern equivalent that readers relate to today).
- Reject any content with graphic violence, harm to children, racial ridicule, or derogatory period slurs.

## OCR Page Text:
"""
{{ocr_text}}
"""

## Output Format:
If the text contains no usable or safe item, return:
```json
{
  "usable": false,
  "reason": "Explanation why no usable item was found"
}
```

If usable, return:
```json
{
  "usable": true,
  "format": "true_retelling | price | old_ad | advice | guess_year | story_sunday",
  "pillar": "money | love_family | strange_true | same_human",
  "title_headline": "Headline or brief title of the incident",
  "date": "YYYY-MM-DD or Year",
  "place": "City, State, or Country",
  "facts": [
    "Fact 1 in plain words",
    "Fact 2 in plain words",
    "Fact 3 in plain words"
  ],
  "exact_ocr_quotes": [
    "exact verbatim phrase 1 from OCR text",
    "exact verbatim phrase 2 from OCR text"
  ],
  "human_need": "Core psychological driver (e.g. fear of looking broke, wanting to be noticed)",
  "modern_mirror": "The modern behavior that mirrors this",
  "price_data": {
    "item": "e.g. winter coat or lb of beef (or null if not price format)",
    "price_cents": 400,
    "unit": "each",
    "year": 1903
  },
  "ad_crop_clues": "Description of ad location if identifiable",
  "safety_flags": []
}
```
