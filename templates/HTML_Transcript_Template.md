# HTML Transcript Template

This file contains the CSS and document structure boilerplate used by the Transcript Publish skill. Update here to change styling across all future transcripts.

---

## Document Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>[display title]</title>
  <style>
    body {
      font-family: Arial, Helvetica, sans-serif;
      font-size: 1rem;
      line-height: 1.6;
      max-width: 75ch;
      margin: 0 auto;
      padding: 1rem;
      color: #1a1a1a;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    h2 { font-size: 1.25rem; margin-top: 2rem; margin-bottom: 0.5rem; }
    h3 { font-size: 1.1rem; margin-top: 1.5rem; margin-bottom: 0.5rem; }
    p { margin-bottom: 1em; }
    .speaker-label { font-weight: bold; }
    .meta { font-size: 0.9rem; color: #555555; margin-bottom: 1.5rem; border-bottom: 1px solid #cccccc; padding-bottom: 1rem; }
    .non-speech { color: #555555; font-style: italic; }
    .timecode { font-size: 0.8rem; color: #777777; margin-top: 2rem; margin-bottom: 0.1rem; }
  </style>
</head>
<body>

<h1>[display title]</h1>

<div class="meta">
  <p><strong>Speaker:</strong> [from VTT header, or blank]</p>
  <p><strong>Course:</strong> [from VTT header, or blank]</p>
  <p><strong>Duration:</strong> [N] minutes (approx.)</p>
  <p><em>Auto-generated transcript. Edits have been applied for clarity.</em></p>
</div>

[body content]

</body>
</html>
```

---

## CSS Notes

| Property | Value | Reason |
|---|---|---|
| `font-size` | `1rem` | Never use fixed `px` or `pt` — required for text resize (WCAG 1.4.4) |
| `color` | `#1a1a1a` | Exceeds 4.5:1 contrast ratio on white (WCAG 1.4.3) |
| `max-width` | `75ch` | Prevents horizontal scrolling on mobile (WCAG 1.4.10) |
| `user-scalable` | never restrict | Do not add `user-scalable=no` to the viewport meta tag (WCAG 1.4.4) |
