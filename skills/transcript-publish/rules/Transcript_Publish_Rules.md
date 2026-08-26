# Transcript Publish Rules

This file defines the publish-step editing rules that are not already covered
by the JSON schema fields in `headings.md` (sections, paragraph breaks,
doubled words). It is injected into that prompt at runtime via the
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

## Rule 3 — The Publish Step Never Adds Text

**Nothing may be added to the words on the page at this step.** The publish
step restructures a transcript — sections, paragraphs, speaker labels,
non-speech markers, doubled-word removal — and makes no other change to the
text. There is no field for adding text, and the pipeline will not render one.

This rule is the verbatim standard of `Caption_Cleanup_Rules.md` carried into
the publish step: *never insert a word that was not spoken — not even in
square brackets.*

Specifically, three things this step formerly did are now prohibited:

| Removed | Was | Why |
|---|---|---|
| `[sic]` marks | Flagged a speaker grammar error a reader might read as a typo | Editorial annotation the speaker did not utter; it also passes judgment on how a person speaks, in front of their students |
| Bracketed clarifications | Added context, e.g. `section 117 [referring to §117(a)]` | Supplies an interpretation as though it were part of the record |
| Dropped-word insertions | Restored a missing function word, e.g. `put it out [in] different forms` | Puts a word on the page the speaker may not have said; "obvious from context" is a guess about audio nobody re-listened to |

**What happens instead when a word is missing:** nothing, at this step. The
gap was already handled upstream —

- a dropped word that makes the meaning unclear was **flagged for human
  review** at the cleanup step (Cleanup Rule 3), and the reviewer either
  restores it from the audio or leaves it;
- a word the recognizer could not recover already reads as
  `[unintelligible]` (Cleanup Rules 1d and 3a).

So a sentence that reads oddly at publish time is either awaiting a human who
has the audio, or already carries the marker that says so. Leave it exactly as
it is. Do not repair it, and do not remove or guess behind an existing
`[unintelligible]` marker.

Bracketed text still appears in published transcripts in exactly two forms,
neither of which is an insertion of speech: `[unintelligible]`, which records
that no word could be recovered, and non-speech labels such as `[Applause]`
under Rule 2, which describe sound rather than words.

---

## Rule 4 — Do Not Alter Meaning

- Edits under Rules 1-2 must only improve readability and accessibility —
  never change what the speaker said or implied
- Preserve all technical terms, proper nouns, and citations exactly as
  spoken
- Do not add words, rephrase for clarity, or substitute a "better" word for
  the speaker's word
- When genuinely uncertain whether a turn change or non-speech event
  applies, omit it rather than guess

---

## Summary Table

| Action | Rule |
|---|---|
| Mark new speaker turns with `speaker_turns` | Where applicable |
| Mark non-speech audio cues with `non_speech` | Where applicable |
| Remove auto-caption doubled words | The only text edit at this step |
| Leave an existing `[unintelligible]` marker untouched | Always (Rule 3) |
| Mark a speaker grammar error with `[sic]` | ✗ Never (Rule 3) |
| Add a bracketed clarification | ✗ Never (Rule 3) |
| Restore a dropped word, even an obvious one, even in brackets | ✗ Never (Rule 3) |
| Add, substitute, or reorder content words | ✗ Never |
| Use these fields to fix grammar or style | ✗ Never |
