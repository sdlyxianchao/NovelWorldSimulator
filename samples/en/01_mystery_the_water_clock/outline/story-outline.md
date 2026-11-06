# The Water Clock — Story Outline

> Tang-dynasty Chang'an. A clerk who tends the water clocks solves crimes by asking how fast the water ran. One case per ward, each standing alone — and one thread running underneath.

## 1. Story line (four acts)

**Act I** | The night drum of Pingkang Ward is a full quarter-hour early. Two "accidents"
that night: a musician falls from a balcony; a merchant drowns in his own well. Both
inquests are closed as accidents. Only Shen Yan notices that **that night the water ran
fast by a quarter-hour**.

**Act II** | Shen Yan reads backward through the water. In three years there have been
seven "clock changes," and each lines up with a case that could not be closed. He puts
the seven on one sheet of paper. The lines cross at a single moment: one rainy night
ten years ago.

**Act III** | That was his first year in the Room. The Room's ledger is missing exactly
one page — the page bearing his own first signature. The culprit is his senior: the man
who once took the blame for him, and now uses the same craft to build a **timetable for
the whole city** — who dies when, who goes blind when, all scheduled. He does not want
money. He wants Chang'an to run on his clock.

**Ending** | Shen Yan uses the only trick he has — slow the water by a quarter-hour —
and wrecks the timetable. The price is putting that missing page back on the table:
he has to confess it himself. The case closes. As his senior is led away he looks back
and says: "You changed the clock too."

## 2. The order of the reveals (what the reader knows, and when)

> This section is written for the **reader**. Saying a thing three beats early or three
> beats late changes the taste of the whole book.

- **Opening**: the reader knows the drum is early — **not why**.
- **Station 2**: two accidents side by side. Show the **pattern** first; no explanation.
- **Station 3**: the water ran a quarter-hour fast. The reader gets the **first key**.
- **Middle**: seven clock changes laid out. The reader starts to suspect that "change"
  and "unsolved case" are the same thing — but **do not say it**.
- **Seven tenths**: the timetable surfaces (who dies when, who goes blind when).
- **Nine tenths**: the missing page — the trimmed edge, and his own name in the
  signature column.
- **Never told**: why the senior took that entry for him. Leave it for the next book.

## 3. Length plan (the program sizes the run from this)

> ★ Added 2026-10-27. `Chapters` is a **hard gate** (the station may not advance until
>   it has produced this many chapters, even when the criterion is already met);
>   `Total words` is a **soft target** (the per-day goal handed to the writers).
>   Omitting both still works (the length tier falls back).
>
> ⚠ One chapter = one day = one draft the program produces, so "total chapters" is how
>   many days you intend to run.

- **Total chapters**: 21
- **Total words**: 42000
- **Words per chapter**: 2000

9 stations, 21 chapters, about 42k words.
This is the **short trial setting** (`full` 3 / `normal` 2 / `brief` 1 / `in passing` 1)
-- for a longer book, raise each station's `Chapters` and update the two totals.

## 4. Station list (the simulation walks this — one thing per station)

> **One thing per station.** The program asks the model, beat by beat, whether the
> `Done when` line has happened, and only then moves on. Bundle two tasks into one
> station and that station can never be completed.
>
> - `Span`: how much story time this station covers — `one scene` / `the same day` /
>   `three days` / `a fortnight` / `six months`
> - `Length`: how thick this station is written — `full` / `normal` / `brief` / `in passing`
> - `Chapters`: a positive integer -- **how many chapters this station must run** (it may not advance before that, even when the criterion is met).
> - `Beats`: the steps to walk through **before** the station's high point, in order.
>   **Write concrete things that happen**, not states like "the mood changed" —
>   the simulation follows these steps, and that is what keeps it on track.
>
> (The program stores these as fixed words; either language is understood on input.)

### Station 1 · The early drum

- **Span**: one scene
- **Length**: normal
- **Chapters**: 2
- **Summary**: Shen Yan is on night duty. The Pingkang drum is a full quarter-hour ahead
  of the clock; he goes down to check, and the water level is right. So the drum was not
  struck wrong — **the water ran fast**.
- **Done when**: Shen Yan confirms the drum was a quarter-hour early while the water level was not off.
- **Beats** (3 units):
  1. The night drum of Pingkang Ward is a quarter-hour early
  2. He goes down and checks — the water level on the copper pot is right
  3. He scrapes a water mark on the inside of the wall with his thumbnail and
     compares it with yesterday's scale: a finger's width higher
- **Climax**: Shen Yan climbs the copper pot on a ladder, scrapes a water mark on the
  inside of the wall with his thumbnail, and compares it with yesterday's scale — a
  finger's width higher. He wipes his hand on his sleeve.

### Station 2 · Two accidents

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: Two deaths the same night: a musician falls from a balcony, a merchant
  drowns in his own well. Both inquests are closed as accidents and the ward accepts
  it. Only Shen Yan finds two accidents on one night wrong.
- **Done when**: Shen Yan learns both deaths were ruled accidents and objects to it.
- **Beats** (3 units):
  1. A musician falls from a balcony; the inquest is closed as an accident
  2. A merchant drowns in his own well the same night; closed as an accident too
  3. Shen Yan lays the two reports side by side on the duty-room board, one finger
     on each word "accident"
- **Climax**: Shen Yan lays the two inquest reports side by side on the duty-room
  board, keeps one finger on each word "accident," and pushes one of them half an inch
  toward the warden: "These two did not come out of the same place."

### Station 3 · A quarter-hour fast

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: Shen Yan goes back to the Room alone. He compares that night's watermark
  against the scale inch by inch: the water ran fast — while every change must be
  recorded, signed and sealed. That night there is nothing at all.
- **Done when**: Shen Yan establishes that the clock ran a quarter-hour fast with no change on record.
- **Beats** (3 units):
  1. He goes back to the Room alone and checks the water against the old scale
  2. Inch by inch, the water ran fast by a quarter-hour
  3. He works through three years of calibration ledgers, fingertip along each seam —
     all seven signatures that should be there are blank
- **Climax**: Shen Yan works through the ledgers of three years, running his fingertip
  along each seam — all seven signatures that should be there are blank. He closes the
  topmost book and does not put it back on the shelf.

### Station 4 · Seven changes

- **Span**: three days
- **Length**: brief
- **Chapters**: 1
- **Summary**: He goes through three years of records: seven clock changes in the city,
  each dated to a case that was never closed. All seven were recorded, each under a
  different signature.
- **Done when**: Shen Yan finds the seven clock changes and that each maps to an unsolved case.
- **Beats** (3 units):
  1. Three years of records: seven clock changes, each under a different signature
  2. He copies the seven dates onto one sheet of paper
  3. He lays the seven unsolved cases out beside it and matches them one to one
- **Climax**: Shen Yan copies the seven dates onto one sheet, lays the seven unsolved
  cases out beside it, and matches them one to one; then he goes to blow out the lamp
  and stops halfway.

### Station 5 · Seven lines cross

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: He plots the seven moments on one sheet and pulls the lines both ways —
  they cross at one moment: a rainy night ten years ago. After that night the city's
  clocks changed keeper once.
- **Done when**: Shen Yan traces the seven changes back to one rainy night ten years ago.
- **Beats** (3 units):
  1. He plots the seven moments on one sheet of paper
  2. He pulls the lines both ways; they cross at a single moment
  3. One rainy night ten years ago — after that night the city's clocks changed
     keeper once
- **Climax**: Shen Yan lines up seven copies of old cases by date, reads them from the
  first to the last, then slides the middle ones apart — the slot left open is empty.

### Station 6 · The missing page

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: He calls up the ledger from ten years back. That page is blank, with a
  trimmed edge where it was cut out. And the signature column of that volume carries his
  own name: his first year, his first clock check.
- **Done when**: Shen Yan finds the missing page was his own signed first clock check.
- **Beats** (3 units):
  1. He calls up the ledger from ten years back; that page is blank
  2. The edge shows where it was cut out, and the signature column carries his own name
  3. He holds the cut page up to the lamp and does not touch the signature line
- **Climax**: Shen Yan holds the cut page up to the lamp; the torn fibres turn white in
  the light. He does not touch the line with the signature; he closes the book and
  presses it back onto the desk.

### Station 7 · My senior's timetable

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: His senior comes to him and does not deny it; he explains that year —
  he took the blame. He does not want money. He wants Chang'an to run on his timetable:
  who dies when, who goes blind when.
- **Done when**: the senior admits to Shen Yan's face that the timetable is his.
- **Beats** (3 units):
  1. His senior comes to him, and does not deny it
  2. He explains that year — that entry was his, not Shen Yan's
  3. He pushes the finished sheet of paper across and keeps one finger on the top line
- **Climax**: The senior pushes the finished sheet of paper across to Shen Yan and keeps
  one finger on the top line without looking up: "Look at this hour — it is yours."

### Station 8 · Slow the water

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: One night left. His only trick is to slow the water a quarter-hour and
  wreck the timetable. But there are other roads: take it to the Bureau, or use Liu
  Niang's messengers to move the listed people first.
- **Done when**: Shen Yan settles on a way to wreck the timetable and begins to act.
- **Beats** (3 units):
  1. One night left, and only the trick of slowing the water by a quarter-hour
  2. He plugs the copper pot's intake with a cloth, half a finger's width
  3. One incense stick later, the first night drum outside the ward is late
- **Climax**: Shen Yan plugs the copper pot's intake with a cloth, half a finger's
  width, and watches the water line drop. One incense stick later, the first night
  drum outside the ward is late.
- **Choices**: slow the water / take it to the Bureau / use the messengers
  - slow the water: he slows the clock a quarter-hour and every hour on the list slips.
  - take it to the Bureau: he hands up all seven records at once, betting they dare not
    bury it.
  - use the messengers: Liu Niang carries word by night; he asks her to clear the listed
    people out in one night.

### Station 9 · Confess it himself

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: The timetable is wrecked and the man is taken. But the charge cannot
  stick unless that page from ten years ago goes back on the table — and it carries his
  own name. Shen Yan confesses.
- **Done when**: Shen Yan publicly admits he made that clock change ten years ago, and the case closes.
- **Beats** (3 units):
  1. The timetable is wrecked, and the senior is taken
  2. The charge cannot stick unless the page from ten years ago goes back on the table
  3. He lays the page down, its corner on an old crease — the crease lines up with
     his own name
- **Climax**: Shen Yan lays the page from ten years ago on the desk, its corner on an
  old crease — and the crease lines up exactly with his own name. He says: "This entry
  was mine."
