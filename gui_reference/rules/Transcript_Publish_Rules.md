# Transcript Publish Rules

This file defines the publish-step editing rules that are not already covered
by the JSON schema fields in `headings.md` (sections, paragraph breaks,
doubled words, `[sic]`). It is injected into that prompt at runtime via the
`{PUBLISH_RULES}` placeholder. Rules here apply to every transcript
regardless of course or speaker.

---

## Rule 1 — Multiple Speakers

When more than one speaker appears in the transcript, mark the start of every
new speaker turn using the `speaker_turns` field, so the pipeline can apply a
`.speaker-label` span at that entry:

```json
{"entry": 5, "speaker": "Dr. Smith"}
```

- Use the speaker's name if known; use a role label (*Student*, *Moderator*,
  *Interviewer*) if not
- Mark a new turn at every speaker change, even if the same speaker returns
  after an intervening turn
- Do not mark a turn for a speaker who is merely quoted or referenced, only
  for an actual change in who is speaking

---

## Rule 2 — Non-Speech Audio

When a cue's content is a non-speech audio event rather than spoken words
(e.g. an auto-captioner's `[APPLAUSE]`, `[MUSIC]`, `[LAUGHTER]` tag), mark it
with the `non_speech` field instead of treating it as prose:

```json
{"entry": 12, "description": "Applause"}
```

- The pipeline renders this as its own paragraph:
  `<span class="non-speech">[Applause]</span>`
- Common descriptions: Applause, Laughter, Music playing, Silence,
  Background noise
- Do not mark a cue as non-speech if it contains any spoken words, even a
  brief interjection alongside the sound

---

## Rule 3 — Bracketed Clarifications

When the prose is genuinely ambiguous without added context, insert a
bracketed clarification using the `clarifications` field:

```json
{"entry": 20, "after": "section 117", "insert": "referring to §117(a)"}
```

- `after` is the exact substring in that entry's text after which the
  clarification should appear
- `insert` is the clarifying text only — the pipeline adds the brackets
- Use sparingly — only when a reader could not otherwise follow the
  reference
- Never use this field to fix grammar, add content words, or restate what
  the speaker already said clearly

---

## Rule 4 — Dropped Words (Bracketed Insertions)

When the auto-captioner has clearly dropped a small function word (a
preposition, article, or auxiliary verb) and the sentence is unintelligible
or misleading without it, restore it using the `dropped_word_insertions`
field:

```json
{"entry": 14, "after": "put it out", "insert": "in"}
```

- `after` is the exact substring in that entry's text after which the
  missing word belongs; `insert` is the missing word only — the pipeline
  adds the brackets
- Apply only when the missing word is unambiguous from context (≥ 90%
  confidence) and the sentence does not make sense without it
- Never use this field to add content words, change meaning, or fix
  grammar — only to restore a clearly dropped function word

| Example | Result |
|---|---|
| `put it out different forms` (missing "in") | `put it out [in] different forms` |
| `we need make sure` (missing "to") | `we need [to] make sure` |
| `this is important understand` (missing "to") | `this is important [to] understand` |

---

## Rule 5 — Do Not Alter Meaning

- Edits under Rules 1-3 must only improve readability and accessibility —
  never change what the speaker said or implied
- Preserve all technical terms, proper nouns, and citations exactly as
  spoken
- Do not add words, rephrase for clarity, or substitute a "better" word for
  the speaker's word
- When genuinely uncertain whether a turn change, non-speech event, or
  clarification applies, omit it rather than guess

---

## Summary Table

| Action | Rule |
|---|---|
| Mark new speaker turns with `speaker_turns` | Where applicable |
| Mark non-speech audio cues with `non_speech` | Where applicable |
| Add `clarifications` for genuinely ambiguous prose | Sparingly |
| Restore a clearly dropped function word with `dropped_word_insertions` | At ≥90% confidence only |
| Add, substitute, or reorder content words | Never |
| Use these fields to fix grammar or style | Never |
