# Caption Cleanup Rules

This file defines all editing rules for the Caption Cleanup workflow. It is referenced by `Skill-Caption_Cleanup.md` and should be read in full before cleaning any caption file. Rules here apply to every file regardless of course or speaker.

---

## Verbatim Standard

These captions follow a **verbatim standard**: the goal is to preserve exactly what the speaker said. All edits must serve the purpose of accurately representing the spoken words — not improving the speaker's grammar or style.

- Speaker grammar errors, awkward phrasing, and non-standard constructions are **preserved as spoken** — do not correct, rephrase, reorder, or editorially annotate them in the caption file
- **Never insert a word that was not spoken** — not even in square brackets, and not even to make a sentence grammatical or complete. But *do* restore a word that was clearly spoken and misrecognized (e.g. "we'll" mangled into "will"): that is a recognition correction, not an insertion. If a truly dropped word makes the meaning unclear, flag it for human review; do not supply it. (See Rule 3.)
- Auto-caption doubled words (e.g., *"the the"*, *"encode encode"*) are **preserved verbatim** in the caption file — do not remove them here; they are cleaned during the Transcript Publish step
- The file header declares: *"Auto-generated transcript. Edits have been applied for clarity."* — this covers only recognition corrections and filler removal, not editorial changes to the speaker's language

---

## Correction Confidence Framework

Every apparent auto-caption error requires a confidence judgment before deciding how to handle it.

### ≥ 90% Confident — Apply the correction
Correct the text directly in the cleaned file. Log the correction in the **Corrections Applied** section of the flag log for transparency.

Apply a correction when:
- The misrecognized word is phonetically similar to the correct word AND the correct word is unambiguous from context
- The pattern is a known, recurring auto-caption error type (see High-Confidence Patterns below)
- Only one plausible reading exists given the surrounding content

### < 90% Confident — Keep original, flag for review
Leave the source text unchanged in the cleaned file. Log the entry in the **Entries Requiring Human Review** section.

Flag when:
- Multiple plausible readings exist
- The correct word requires outside knowledge not inferable from the transcript alone
- The phrase is too garbled to form a confident reading

### Speaker grammatical error — Keep verbatim, no annotation
When the auto-caption appears to have captured the spoken words accurately, but the speaker used grammatically incorrect phrasing, **preserve the text exactly as spoken**. Do not correct the grammar and do not add any annotation. Caption files are verbatim records — editorial notes like `[sic]` are applied during the Transcript Publish step, not here.

---

## Editing Rules

### Rule 1 — Correct Punctuation
- Fix run-on sentences, missing commas, and incorrect sentence breaks from auto-captioning
- **Capitalize the first word of every sentence**, including a new sentence starting mid-entry
- **Sentence continues into the next entry:** do NOT add terminal punctuation at the end of the current entry; if the auto-captioner added a period, remove or replace it with a comma as appropriate
- **Sentence ends within an entry:** close it with a period, question mark, or exclamation mark as appropriate
- **Scan adjacent entries:** when reviewing an entry, always check whether its final word and the opening of the next entry form a continuous sentence. Entries beginning with subordinating conjunctions (*While, Although, Because, Since, When, Whereas, Though, Even though*) are dependent clauses and cannot stand alone — if such an entry ends with a period, that period is almost certainly wrong
- Add commas where natural clause boundaries exist
- Hyphens: add where compound modifiers require them (high-volume, rule-based, three-way, end-to-end, right-of-use, time-consuming, audit-proof, etc.)
- **Do not split one spoken sentence into two with an interior period.** If a sentence reads with a stray mid-sentence break (e.g., `And there's my. Text.`), join it — do not leave or create a nonsensical sentence stop. (See Worked Examples.)

| Source | ✗ Wrong | ✓ Correct |
|---|---|---|
| `And there's my. Text.` | `And there's my. Text.` (leave the bad break) | `And there's my text.` |

### Rule 1b — Capitalization of Common Nouns

Only capitalize words that are genuinely proper nouns or the first word of a sentence. Auto-captioners frequently over-capitalize ordinary nouns mid-sentence — **lowercase them**.

| Source | Corrected | Note |
|---|---|---|
| `Go back up here to my Web page.` | `Go back up here to my web page.` | "web page" is a common noun |
| `click on Share, it'll ask you to publish` | (depends) | Keep "Share" only if it names a literal UI button label; otherwise lowercase |
| `open the canvas course site` | `open the Canvas course site` | "Canvas" (the LMS) **is** a proper noun — capitalize |

Apply consistently within a file: if a common noun is lowercased once, lowercase it throughout.

### Rule 1c — Remove Consecutive Punctuation Marks

Only one punctuation mark may appear at a time. This is handled automatically by the pipeline's deterministic clean step — before cues are sent to the AI for judgment. The AI therefore never sees doubled punctuation and does not need to flag or correct it. Documented here for reference only.

**Same mark repeated:** collapse to one.

| Source | Corrected |
|---|---|
| `the amount,, which was due` | `the amount, which was due` |
| `Section 61,, gross income` | `Section 61, gross income` |
| `Yes.. that's correct.` | `Yes. That's correct.` |
| `really?? I don't think so` | `really? I don't think so` |

**Mixed adjacent marks:** keep one, remove the other. Terminal punctuation (`.` `?` `!`) takes priority over a comma; when two terminals appear together keep the first.

| Source | Corrected | Reason |
|---|---|---|
| `the amount., which was due` | `the amount, which was due` | period + comma → keep comma (mid-sentence) |
| `the amount,. Next section` | `the amount. Next section` | comma + period → keep period (sentence ends) |
| `Is that right?, I think so` | `Is that right? I think so` | `?,` → keep `?` |
| `Is that right.?` | `Is that right?` | `.?` → keep `?` |
| `Yes!. Let's continue` | `Yes! Let's continue` | `!.` → keep `!` |

**Do not collapse intentional ellipses** (`...`) — those are a single punctuation unit and should be left alone.

### Rule 2 — Remove Vocal Hesitations and Fillers

Delete the following without replacement:

| Type | Examples |
|---|---|
| Hesitation sounds | *um, uh, ah, er* |

**Apply as a global pass across every entry** — not just entries with other corrections.

**Do NOT remove** the following — preserve verbatim as spoken:
- *so, you know, I mean, right, well* — even when used as openers or fillers. These are part of the speaker's natural voice and must be kept.

### Rule 3 — Never Insert Words; Do Restore Misrecognized Words

**Never use square brackets, and never insert a word that the speaker did not say.** But distinguish two situations that look similar:

- **Pure insertion (✗ never):** the recognizer produced nothing where you would be *adding* a word the speaker may not have said. There is no wrong token to fix — you would simply be supplying a word to make the sentence read better. Do not do this. If the omission obscures meaning, **flag it for human review**.
- **Misrecognition / substitution (✓ apply at ≥ 90%):** the recognizer produced the *wrong* token for a word the speaker almost certainly *did* say — including cases where a contraction was split or its subject was swallowed (e.g., "we'll" heard as "will" or as "or"). This is a recognition correction under the confidence framework: replace the wrong token with the right one directly (no brackets) and log it in **Corrections Applied**.

**The test:** *Did the speaker probably say this word?*
- Yes, and you are ≥ 90% confident → correct the misrecognition (substitute the right token). No brackets.
- No / uncertain → leave verbatim, or flag if meaning is lost. Never insert.

| Source (as captioned) | Action | Result |
|---|---|---|
| `Is there term the Adobe Express term for a link?` | Pure insertion — nothing was misheard as "a"; ✗ do not add | leave verbatim (flag if needed) |
| `it'll ask you to publish and share link.` | Pure insertion — ✗ do not add "a" | leave verbatim (flag if needed) |
| `we need make sure` | Pure insertion — ✗ do not add "to" | leave verbatim (flag if needed) |
| `for the sake of this next unit, will be asking you` | Misrecognition — "will" ≈ "we'll"; ✓ correct + log | `...this next unit, we'll be asking you` |
| `In this module or dissect` | Misrecognition — "or" ≈ "we'll"; ✓ correct + log | `In this module, we'll dissect` |

Note the difference between rows 1–3 and rows 4–5: in the first three there is no token that was misheard — adding a word is pure insertion. In the last two, an actual spoken word ("we'll") was mangled into "will"/"or", so restoring it is a recognition correction, not an insertion.

### Rule 4 — Words: What May and May Not Change

| Action | Rule |
|---|---|
| Remove hesitation sounds (*um, uh, ah, er*) — global pass | ✓ Always |
| Fix punctuation and hyphenation | ✓ Always |
| Lowercase over-capitalized common nouns | ✓ Always (Rule 1b) |
| Apply high-confidence recognition corrections (≥ 90%) | ✓ Apply + log in Corrections Applied |
| Preserve speaker grammar errors verbatim — no annotation | ✓ Always (flag log note optional if ambiguous) |
| Preserve auto-caption doubled words verbatim | ✓ Always — cleaned at Transcript Publish step |
| Restore a misrecognized word at ≥ 90% (e.g. "will" → "we'll") | ✓ Apply + log in Corrections Applied (Rule 3) |
| **Insert a word the speaker did not say — or any bracketed insertion** | ✗ **Never** (Rule 3) — flag instead |
| Add, substitute, or reorder content words | ✗ Never |
| Correct speaker's factual claims | ✗ Never |
| Fix speaker's grammar | ✗ Never |
| Remove or paraphrase speaker's words | ✗ Never |
| Use [sic] in caption files | ✗ Never |

### Rule 5 — Do Not Alter Meaning
- Preserve all technical terms, proper nouns, and legal citations exactly as spoken
- When genuinely uncertain, keep the original and flag it

### Rule 6 — Preserve Entry Numbers and Timecodes
- Do not change, merge, split, delete, or reorder entry numbers or timecodes
- Every entry in the source must appear in the output with the same number and timecode
- Only the text lines within each entry are edited

---

## Sentence Continuation Across Entries

When a sentence clearly continues from one entry into the next, remove any incorrect terminal punctuation at the entry break and leave the line open. Also check that the first word of the continuing entry is lowercased if it is not a proper noun.

**This is the single most common cleanup miss.** Before finalizing, scan *every* adjacent entry pair and ask: does the next entry begin with a word that grammatically continues the current one? Watch especially for next-entries that start with a coordinating conjunction (*and, but, or, so, yet*) or a subordinating conjunction (*while, although, because, since, when, whereas, though*) — these almost always continue the previous entry, so the previous entry's terminal period is wrong and the conjunction should be lowercased.

**Real failure example (must be fixed):**

```
40
00:04:46.950 --> 00:04:50.580
And I can go down to one that maybe has a little more developed.   ← ✗ wrong: period stops a continuing sentence

41
00:04:53.020 --> 00:04:56.650
And show you what some of the layout options look like.            ← ✗ wrong: capital "And", terminal period
```

**Corrected:**

```
40
00:04:46.950 --> 00:04:50.580
And I can go down to one that maybe has a little more developed     ← ✓ no terminal period; sentence continues

41
00:04:53.020 --> 00:04:56.650
and show you what some of the layout options look like.             ← ✓ lowercase "and"; sentence closes here
```

Note that entry 40 itself opens with "And" (capitalized) because it begins a new sentence — but entry 41's "and" is mid-sentence and is lowercased. Judge each entry by whether it *starts* a sentence, not by whether it starts with a conjunction.

**Source (SRT):**
```
3
00:00:07,500 --> 00:00:11,000
While the previous chapters focused on targeting big groups.

4
00:00:11,000 --> 00:00:14,500
This chapter talks about getting the message across to individuals.
```

**Cleaned (VTT):**
```
3
00:00:07.500 --> 00:00:11.000
While the previous chapters focused on targeting big groups,

4
00:00:11.000 --> 00:00:14.500
this chapter talks about getting the message across to individuals.
```

---

## High-Confidence Correction Patterns (≥ 90%)

These patterns recur across auto-captioned course content and may be corrected directly.

### "I" → "AI" misrecognition
The auto-captioner consistently mishears "AI" as the pronoun "I" when the speaker says "A.I." or "ay-eye." Correct whenever context makes the referent unambiguous.

| Source | Corrected | Note |
|---|---|---|
| `The I didn't create the bias.` | `The AI didn't create the bias.` | Subject is clearly the technology |
| `I is only as unbiased as the data` | `AI is only as unbiased as the data` | Subject-verb mismatch is the speaker's own grammar — preserve as spoken |
| `how I process their data` | `how AI process their data` | "I"→"AI" corrected; "process" is speaker grammar — preserve verbatim |
| `A's confidence score` | `AI's confidence score` | Possessive misrecognition |

**Important:** Correct "I"→"AI" but **do not fix subject-verb agreement errors that result.** If the speaker said "AI process" (not "processes"), correct the misrecognition and leave the grammar exactly as spoken — no annotation in the caption file.

### Accounting standards misrecognition

| Source | Corrected |
|---|---|
| `ACA 42` | `ASC 842` |
| `I for 16` | `IFRS 16` |
| `AK 42` | `ASC 842` |
| `Sox 404` | `SOX 404` |
| `SoC`, `SoCs` | `SOC` (note if context suggests SOC 1/SOC 2) |

### Clear phonetic misrecognition with single plausible reading

| Source | Corrected | Confidence basis |
|---|---|---|
| `Black's bog opacity` | `black box opacity` | "black box" is the exact AI/ML term; no other reading fits |
| `In this module or dissect` | `In this module, we'll dissect` | "or" is a misrecognition of "we'll"; the speaker clearly said it — restore (Rule 3 substitution, not insertion) |
| `for the sake of this next unit, will be asking you` | `...this next unit, we'll be asking you` | "will" is a misrecognition of "we'll" — restore |
| `Swae Lee match rule` | `three-way match rule` | Standard AP term taught in the same module |
| `app specialist` / `app Manager` | `AP specialist` / `AP Manager` | AP (Accounts Payable) is the workflow being described |
| `A stock report` | `A SOC report` | Context is AI software vendor auditing |

### False negation drops

| Source | Corrected | Confidence basis |
|---|---|---|
| `you can simply conclude the AI told me so` | `you can't simply conclude the AI told me so` | Following entry confirms the negation |

### Possessive nouns

The auto-captioner often drops the possessive `'s`. When context makes the possessive unambiguous, add the apostrophe-s (this is punctuation, not a new word, so it is permitted under Rule 1).

| Source | Corrected | Confidence basis |
|---|---|---|
| `selected from items communicated to the clients governance group` | `selected from items communicated to the client's governance group` | Singular possessive — one client owns the governance group |

---

## Flag Calibration — Worked Examples

These real examples show when to flag and when to leave text alone. Over-flagging wastes reviewer time; under-flagging lets errors through. Calibrate against these.

### Do NOT flag (false flags to avoid)

The possessive below was correct as captioned — a button legitimately had different photo options. Do not "fix" a possessive that already makes sense.

```
Entry 49 | 00:05:45
  Found:    "You can see the button's different photos that I included in different kinds of imagery."
  ✗ Bad flag: claimed "button's" doesn't fit; proposed "buttons — different photos"
  ✓ Correct action: leave verbatim. The possessive parses fine in context.
```

### DO flag (correct flags)

Garbled course name — clear misrecognition, single plausible reading, but verify against audio:

```
Entry 45 | 00:05:19
  Found:    "...a previous version of this class rhetoric went in and written communication intensive."
  Issue:    "rhetoric went in and" likely misrecognizes the course name
  Possible: "...a previous version of this class, Rhetoric and Written Communication Intensive."
```

Nonsensical phrase that does not parse:

```
Entry 4 | 00:00:20
  Found:    "Both the discreet contact rate, the explosion of the shuttle itself..."
  Issue:    "discreet contact rate" is misrecognized; context is the Challenger rhetorical situation
  Possible: "Both the discrete context, the explosion of the shuttle itself..."
```

```
Entry 7 | 00:00:45
  Found:    "...what kind of audience? Identity is values, experiences."
  Issue:    "Identity is values, experiences" doesn't parse as captioned
  Possible: "...what kind of audience — identity, its values, experiences"
```

```
Entry 11 | 00:01:06
  Found:    "And only purpose. What seems to be the purpose of the speech?"
  Issue:    "And only purpose" likely misrecognizes a transition word
  Possible: "And finally, purpose. What seems to be the purpose of the speech?"
```

**The "Possible:" field — valid values only.** The `Possible:` field is a *suggestion for the human reviewer*, not a correction applied to the caption file. The cleaned VTT keeps the original verbatim text until a human accepts it (Rule 3). The flag log is where judgment lives; the caption file stays verbatim.

`Possible:` must contain EXACTLY ONE of:
- A **replacement string** — the corrected text the reviewer should substitute for the `Found:` text if they accept it. Write it as a ready-to-apply substitution.
- The exact phrase **"Listen to verify"** — use this when the correct reading cannot be determined from context, or when the text appears correct as verbatim speech and only needs a human to confirm it against the audio.

**Never write editorial commentary or instructions in `Possible:`.** The Apply Flag Log skill reads this field literally and will insert it directly into the VTT if it is not skipped. Commentary masquerading as a replacement will corrupt the caption file.

| `Possible:` value | Valid? | Why |
|---|---|---|
| `"Thomson Reuters"` | ✓ | Direct replacement |
| `"Listen to verify"` | ✓ | Signals skip — reviewer checks audio |
| `"Amy? Yes, please. There you go."` | ✓ | Same as Found: = keep verbatim |
| `"Retain verbatim"` | ✗ | Editorial commentary — will be inserted literally |
| `"Retain verbatim or confirm identity of speaker"` | ✗ | Instruction, not a replacement |
| `"Confirm with speaker"` | ✗ | Instruction, not a replacement |

**When text seems correct but needs human confirmation** (e.g. an unfamiliar proper name, or verbatim off-screen speech you cannot identify): write `"Listen to verify"` — not a note. The `Issue:` field is the right place for context and explanation.

### Auto-generated header lines
Some caption source files include a header line as part of entry 1 text:
`[Auto-generated transcript. Edits may have been applied for clarity.]`

Strip this line from the entry text. If it is the only text on entry 1, skip that entry entirely (do not write a blank entry to the VTT). The actual caption text will be on the following line of the same entry block.
