# The All-Night Bookshop — Story Outline

> A 24-hour bookshop. Between three and four in the morning, nobody who walks in is just browsing. The owner can hear which books want to be read.

## 1. Story line (four acts)

**Act I** | The shop is served notice: the lease is up and the whole street is coming down.
Zhou Chi decides to close. One thing sticks: the book in the till. He cannot hear it —
and yet it has never gone dim. It is waiting for someone.

**Act II** | In the last month before closing, Lin Xiaoman changes. Her habit has not
changed, but she begins **bringing books back**: one at a time, every one she ever bought,
read and returned. She says, "What your shop is missing doesn't seem to be the ones
I bought."

**Act III** | Zhou Chi finally picks up the book he never sold. On the flyleaf is his own
name — the book he killed, of which fewer than ten copies remain. He cannot understand
why he cannot hear it, until Lin Xiaoman says: "I've seen books like that in the hospital.
It isn't that it doesn't want to be read. It's **waiting for someone who hasn't arrived**."

**Ending** | On the last day Zhou Chi closes the shop but does not move the counter out.
He leaves the book on it and does not lock the door. He stands across the street and
watches — and a window on the third floor comes on.

## 2. The order of the reveals (what the reader knows, and when)

> This section is written for the **reader**. Saying a thing three beats early or three
> beats late changes the taste of the whole book.

- **Opening**: the reader knows the street is coming down — **not what the book in the
  till is**.
- **Station 2**: first the strangeness ("no sound, and never dim"), **no explanation**.
- **Station 3**: Lin Xiaoman starts bringing books back. The reader finds it odd first —
  why return a book you bought?
- **Middle**: "what your shop is missing isn't the ones I bought". The reader and Zhou
  Chi land on it together.
- **Seven tenths**: his own name on the flyleaf. The reader learns it **at the same
  moment as he does** — a beat earlier and the book deflates.
- **Nine tenths**: "it is waiting for someone who hasn't arrived." Keep the sentence
  **hanging**; do not translate it into an explanation.
- **Never told**: who is in the window on the third floor; whether the third character
  of the sign is "book" or "read".

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

### Station 1 · The lease

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: The landlord serves notice: the lease is up, the street is coming down.
  Zhou Chi does not argue — he asks for one month, puts the notice under the counter
  glass, and tells no regular.
- **Done when**: Zhou Chi receives the demolition notice and decides to close in a month.
- **Beats** (3 units):
  1. The landlord hands over the notice: the lease is up, the whole street is coming down
  2. Zhou Chi does not argue; he asks for one month
  3. He slides the notice under the counter glass and tells no regular
- **Climax**: Zhou Chi reads the notice once, slides it under the glass of the counter —
  where it presses down an old bookmark — and says nothing.

### Station 2 · The book that will not sound

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: After closing he runs the shelves and listens, as always. The book in the
  till makes no sound — and yet it has never gone dim. Not sounding and not dimming: it
  is waiting for someone.
- **Done when**: Zhou Chi notices the old book neither sounds nor dims, and stops over it.
- **Beats** (3 units):
  1. After closing he runs the shelves and listens, book by book
  2. The book in the till makes no sound, and yet it has never gone dim
  3. His hand stops, moves away, stops again; he lifts it, looks at the back cover, puts it back
- **Climax**: Zhou Chi's hand stops on the old book, moves away, stops again; at last he
  lifts it, turns it over to look at the back cover, and puts it back where it was.

### Station 3 · She starts returning

- **Span**: three days
- **Length**: brief
- **Chapters**: 1
- **Summary**: Over several Wednesdays Lin Xiaoman buys less and returns more: every book
  she ever bought, read and brought back, one at a time. He does not keep a ledger of it.
- **Done when**: Lin Xiaoman begins returning the books she bought over the years.
- **Beats** (3 units):
  1. Over several Wednesdays, Lin Xiaoman buys less
  2. What comes back is every book she ever bought, one at a time
  3. He does not keep a ledger of it
- **Climax**: Lin Xiaoman pushes a copy of "A City of Southern Tales" across the
  counter; Zhou Chi counts out the change as usual, she does not take it, only says "this
  one is not needed". He does not even open the ledger.

### Station 4 · Not the ones I bought

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: She returns the last one and says: "What your shop is missing doesn't seem
  to be the ones I bought." He asks what is missing; she says, "The one you cannot hear."
- **Done when**: Lin Xiaoman says to his face that what the shop is missing is not the books she bought.
- **Beats** (3 units):
  1. She returns the last one and says "what your shop is missing doesn't seem to be the ones I bought"
  2. Zhou Chi asks what is missing
  3. She says "the one you cannot hear", and looks at the till
- **Climax**: Lin Xiaoman stacks the last returned book on the counter and says: "What
  your shop is missing doesn't seem to be the ones I bought." Zhou Chi asks what is
  missing; she looks at the book in the till.

### Station 5 · His name inside

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: Zhou Chi finally picks up the book he never sold. His own name is on the
  flyleaf — the book he killed, fewer than ten copies left. He reads it three times and
  still hears nothing.
- **Done when**: Zhou Chi opens the old book and confirms his own name is on the flyleaf.
- **Beats** (3 units):
  1. He finally picks up the book he never sold
  2. His own name is on the flyleaf — the book he killed, fewer than ten copies left
  3. He reads it three times and still hears nothing
- **Climax**: Zhou Chi opens the old book to the flyleaf and sees his own name printed
  there; he turns the book he heard nothing in three times back to the first page and
  sets it square again.

### Station 6 · Someone not yet arrived

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: Lin Xiaoman says she has seen such books in the hospital: it is not that it
  will not be read — it is waiting for someone not yet arrived. He asks who; she only
  knows they have not come.
- **Done when**: Lin Xiaoman says the book is waiting for someone who has not arrived, and he understands it.
- **Beats** (3 units):
  1. Lin Xiaoman says she has seen such books in the hospital
  2. "It isn't that it doesn't want to be read — it is waiting for someone who hasn't arrived"
  3. He asks who; she only knows they have not come
- **Climax**: Lin Xiaoman pushes the book back to him: "It isn't that it doesn't want to
  be read — it is waiting for someone who hasn't arrived." Zhou Chi says nothing; he only
  squares the book by half an inch.

### Station 7 · The last day

- **Span**: the same day
- **Length**: normal
- **Chapters**: 2
- **Summary**: The last day before demolition. He boxes, shelves, wipes the counter, one
  thing at a time until all of it is done. The counter he does not move, and the old book
  is not boxed.
- **Done when**: Zhou Chi finishes the last task before closing and decides to leave the counter standing.
- **Beats** (3 units):
  1. Boxing, shelving, wiping the counter, one thing at a time until all of it is done
  2. The counter he does not move; the old book is not boxed
  3. He tapes shut the last carton and writes "keep" on its side
- **Climax**: Zhou Chi tapes shut the last carton and writes "keep" on its side, then
  wipes the counter — the old book is not in the box.

### Station 8 · Door unlocked

- **Span**: one scene
- **Length**: normal
- **Chapters**: 2
- **Summary**: The shop is closed and the door is not locked. The old book stays on the
  counter, the lamp stays on. He crosses the street and looks up at the third floor.
- **Done when**: Zhou Chi leaves the book on the counter, leaves the door unlocked, and walks away from the shop.
- **Beats** (3 units):
  1. The shop is closed and the door is not locked; the old book stays on the counter, the lamp stays on
  2. The key goes in the lock and is not turned
  3. He crosses the street, stands, and looks up at the third floor
- **Climax**: Zhou Chi leaves the old book on the counter, leaves the lamp on, puts the
  key in the lock without turning it; he pulls the door to and stands across the street.
- **Choices**: keep watch / lock it and go / post the book
  - keep watch: he stands across the street until dawn, waiting for the one who has not arrived to walk in.
  - lock it and go: he closes that page, locks the door, and stops listening to books.
  - post the book: he mails it to the old address written inside the cover.
