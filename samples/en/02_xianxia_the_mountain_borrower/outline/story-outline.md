# The Mountain Borrower — Story Outline

> In the cultivation world nothing is taken — everything is borrowed. Mountains, rivers, years of life. What you borrow must be returned, and the ledger is written on your own skin.

## 1. Story line (four acts)

**Act I** | A great calamity is coming for the Cloudbrook Sect. The only way to turn it
aside is to borrow the *form* of **Guanyun Mountain**, the peak behind the sect. The sect
dares not borrow it itself — the debt would land on its founder. So they hire Lu Xingzhou
and write the contract: seven days; on return, the mountain must be **as it was when
borrowed**.

**Act II** | Lu Xingzhou climbs. A Ruo blocks him, and he stops her with one sentence:
"I am not borrowing the mountain. I am borrowing its shadow." For seven days he does
absurdly small work — measuring the seams in the rock, counting the folds in the stream,
noting at which hour each tree casts which shadow. A Ruo follows, more confused by the
hour: he knows this mountain better than its keeper does.

**Act III** | On the fourth day, the people inside begin to get lost. Leave the mountain
and they forget where they came from — they cannot even say which way their own door
faces. A Ruo panics for the first time. She asks him: "While the mountain is gone —
where am I?" He does not answer. He only counts his marks again, left hand to right,
and comes out one over.

**Ending** | On the seventh day Lu Xingzhou returns the mountain's shadow. The mountain
is intact; the contract is fulfilled. But he does not leave. He sits down at the pass to
wait for the sect to settle accounts — because A Ruo came back with the mountain, and
among the contract's lines there is a small clause he crossed out himself:
*the keeper is not included in this.*

## 2. The order of the reveals (what the reader knows, and when)

> This section is written for the **reader**. Saying a thing three beats early or three
> beats late changes the taste of the whole book.

- **Opening**: the reader knows Guanyun Mountain is lent for seven days — **not that the
  shadow is what goes**.
- **Station 2**: one line gives it away — "I am borrowing its shadow". The reader is
  half a step ahead of A Ruo.
- **Middle (day four)**: the **symptom** first (people lose their way), the **rule**
  after ("when the shadow is borrowed too long, the mountain forgets its way home").
  Reverse them and the dread is gone.
- **Six tenths**: A Ruo answers off the point — what she says is often what "the
  mountain" thinks, not what she thinks. The reader starts to suspect; **do not say it**.
- **Nine tenths**: the crossed-out clause. Only now does the reader understand why he
  stayed on the seventh day.
- **Never told**: what the slow count of the marks means. Leave it for the next book.

## 3. Length plan (the program sizes the run from this)

> ★ Added 2026-10-27. `Chapters` is a **hard gate** (the station may not advance until
>   it has produced this many chapters, even when the criterion is already met);
>   `Total words` is a **soft target** (the per-day goal handed to the writers).
>   Omitting both still works (the length tier falls back).
>
> ⚠ One chapter = one day = one draft the program produces, so "total chapters" is how
>   many days you intend to run.

- **Total chapters**: 19
- **Total words**: 38000
- **Words per chapter**: 2000

8 stations, 19 chapters, about 38k words.
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

### Station 1 · The contract

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: The Cloudbrook Sect lays out the mountain-borrowing contract: seven days,
  and on return the mountain must be "as it was". Lu Xingzhou reads it line by line,
  stops at that clause, and asks one question. They do not answer.
- **Done when**: Lu Xingzhou signs the mountain-borrowing contract for a term of seven days.
- **Beats** (3 units):
  1. The sect lays out the contract: seven days, and the mountain must come back "as it
     was when borrowed"
  2. Lu Xingzhou reads it line by line, stops at that clause, and asks "may I borrow the
     form, not the mountain?"
  3. They do not answer; he asks no price, signs, and folds the contract into his sleeve
- **Climax**: Lu Xingzhou reads the contract from end to end, stops at the line "as it
  was when borrowed", dips his brush, presses it down at the signature block — and does
  not look up.

### Station 2 · Barred at the pass

- **Span**: one scene
- **Length**: normal
- **Chapters**: 2
- **Summary**: At the pass A Ruo blocks him and asks what he wants. He says he is not
  borrowing the mountain: "I am borrowing its shadow." She steps aside — and afterwards
  never leaves his side.
- **Done when**: A Ruo lets Lu Xingzhou into the mountain and begins to follow him.
- **Beats** (3 units):
  1. A Ruo blocks the path at the pass and asks what he wants, and for whom
  2. He says "I am borrowing its shadow" and steps straight in
  3. She moves out of the path but does not move off it, and follows him in half a pace behind
- **Climax**: A Ruo steps aside from the path, but she does not step off it — she comes
  in half a pace behind Lu Xingzhou and enters the mountain with him.

### Station 3 · Seven days of work

- **Span**: three days
- **Length**: brief
- **Chapters**: 1
- **Summary**: Measuring the seams in the rock, counting the folds in the stream, noting
  at which hour each tree casts which shadow. A Ruo watches and grows more confused: he
  knows this mountain better than its keeper.
- **Done when**: Lu Xingzhou finishes measuring every seam, fold and shadow on the mountain.
- **Beats** (4 units):
  1. Along the stream, counting every fold: where it bends, and how many times
  2. Measuring each seam in the rock, driving in a bamboo marker, twice a day
  3. Noting which tree casts which shadow on which stone, and at what hour
  4. A Ruo asks what he is writing it all down for; he says "for the return"
- **Climax**: Beside the last stone, Lu Xingzhou drives in the seventh bamboo marker,
  gathers the markers one by one into a handful, and holds it without moving.

### Station 4 · The people lose their way

- **Span**: the same day
- **Length**: full
- **Chapters**: 3
- **Summary**: On the fourth day people who leave begin to forget: where they came from,
  which way their own door faces. Outsiders call it a haunting; those inside stop going
  out. A Ruo, who has lived here thirty years, cannot answer.
- **Done when**: People leaving the mountain begin to forget where they came from, and both A Ruo and Lu Xingzhou see it.
- **Beats** (4 units):
  1. An old man gathering herbs stops at the pass and asks A Ruo which way his own door opens
  2. She cannot answer; more people stop at the crossroads, unable to say which road they came by
  3. Outsiders call it a haunting; inside the mountain, people stop going out
  4. Lu Xingzhou watches from the ridge a long time; one marker is missing from his hand, and he tells no one
- **Climax**: At the crossroads an old man asks A Ruo which way his own door opens, and
  she cannot answer. Lu Xingzhou looks at him once, then puts his eyes back on the mountain.

### Station 5 · Where am I

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: A Ruo panics for the first time and asks: "While the mountain is gone —
  where am I?" Lu Xingzhou does not answer. He only counts the marks on his hands, left
  to right, and comes out one over.
- **Done when**: A Ruo asks to his face where she is while the mountain is gone, and Lu Xingzhou gives no answer.
- **Beats** (3 units):
  1. A Ruo seizes his sleeve and asks "while the mountain is gone, where am I?"
  2. He does not answer; he turns his wrist over and shows her the marks
  3. Left hand to right: one more than yesterday. He looks up at her and says nothing
- **Climax**: A Ruo turns Lu Xingzhou's wrist over and counts the marks one by one — one
  more than yesterday. She lets go of his hand and does not ask a second time.

### Station 6 · Return the shadow

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: On the seventh day he returns the shadow, putting back what he recorded,
  one place at a time. The mountain is intact and the contract is fulfilled — but
  counting his marks, he slows once.
- **Done when**: Lu Xingzhou returns the shadow in full and the mountain is as it was.
- **Beats** (4 units):
  1. Putting back the folds of the stream — the sound changes back, note by note
  2. Pressing the tree-shadows back into place, one tree at a time, starting from the first in the east
  3. Pulling the bamboo markers out of the seams; he pauses at the seventh
  4. He sits and counts the marks on his hands, and slows once
- **Climax**: Lu Xingzhou presses the last tree-shadow back into place and the sound of
  the stream comes back at the pass; then he sits on the rock and counts the marks on his
  hands — and slows once, halfway.

### Station 7 · The crossed-out line

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: He stays at the pass to wait for the sect — A Ruo came back with the
  mountain, being the form it took, and nearly went with it. One clause, "the keeper is
  not included", he crossed out himself.
- **Done when**: Lu Xingzhou states that A Ruo is the form the mountain took, and that he crossed out the clause excluding her.
- **Beats** (3 units):
  1. A Ruo asks why she came back with the mountain; he answers "because you are the form it took"
  2. He lays the contract on his knee, turns to the last line, and touches the crossed-out clause
  3. He says "the keeper is not included in this — that line is mine"; the ink of the stroke is newer than the rest
- **Climax**: Lu Xingzhou lays the contract on his knee and touches the crossed-out line
  with one finger: "The keeper is not included in this — that line is mine."

### Station 8 · Settling at the pass

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: The sect comes to settle. The contract is fulfilled but the account is not
  closed: whether A Ruo counts as part of the mountain is a line he crossed out himself,
  so it has to be said face to face.
- **Done when**: Lu Xingzhou and the sect settle the matter of A Ruo on the spot.
- **Beats** (3 units):
  1. The sect arrives at the pass and checks the term and the shape of the mountain, item by item
  2. Lu Xingzhou turns the contract to its last page and turns the blank space where A Ruo's entry should be toward them
  3. He says "this entry gets settled today", and waits for them to speak first
- **Climax**: Lu Xingzhou turns the contract to its last page in front of the sect and
  turns the blank space where A Ruo's entry should be toward them: "This entry gets
  settled today."
- **Choices**: demand they name her / take her down the mountain / put himself up again
  - demand they name her: he makes the sect acknowledge A Ruo as a person, not part of the mountain.
  - take her down the mountain: the post of keeper ends there, and he takes her away from Guanyun.
  - put himself up again: he spends what is left of his own lifespan to let her keep the mountain.
