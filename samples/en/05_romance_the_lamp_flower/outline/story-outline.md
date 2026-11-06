# The Lamp Flower — Story Outline

> A river town in Jiangnan. A ferryman and an embroiderer meet exactly once a year — on the last crossing of the Lantern Festival.

## 1. Story line (four acts)

**Act I** | The first Lantern Festival. A Su is nineteen, packs up late, and reaches the
landing with only the last crossing left. Chen Du takes her aboard. They say almost nothing
all night — except at one bend in the river, where A Su points at the water and says,
"That lantern's reflection is broken." Chen Du says, "The bridge pier cuts it." They come
ashore at dawn. Neither mentions it.

**Act II** | The second year, the third, the fourth. Every festival, the last crossing, the
same two people. What they say on the boat gets shorter every year, and what they do gets
longer: mending the oars, reading the stars, noting which stretch of riverbed has old piles
in it.

**Act III** | In the seventh year, A Su's sight is almost gone. She rushes to finish one
last batch of lamp flowers before the festival, each missing a petal — she is embroidering
the lanterns whose reflections are broken. She does not tell Chen Du; she only asks him,
"What is it hanging on your awning?"

**Ending** | The eighth festival, A Su does not come. Chen Du unhooks the lanterns from the
awning one by one and sets them on the landing steps — seven of them. He does not wait for
anyone; he rows out empty and stays the whole night at the bend she once pointed at. At
dawn he comes back, and there is one more lamp on the steps — the eighth, embroidered,
missing a petal.

## 2. The order of the reveals (what the reader knows, and when)

> This section is written for the **reader**. This book is **slow**: the whole weight of it
> rests on "once a year", and rushing a beat ruins it.

- **Opening**: the reader knows they meet once a year — **not what she is embroidering**.
- **Station 2**: the broken reflection. The reader keeps the image; **do not explain**
  what it is.
- **Station 3**: year after year. Each year gets **one thing done together** (mending
  oars, reading stars, noting old piles) and **no dialogue** — the quieter this station
  is, the heavier the loss later.
- **Middle (seventh year)**: her sight is going. The reader knows before either of them.
- **Seven tenths**: every flower missing a petal. The reader starts counting.
- **Nine tenths**: the lantern on the awning — it is hung **for her sake**. Never say it
  outright.
- **Never told**: where the eighth lamp came from; what the ash in her flowers is.

## 3. Length plan (the program sizes the run from this)

> ★ Added 2026-10-27. `Chapters` is a **hard gate** (the station may not advance until
>   it has produced this many chapters, even when the criterion is already met);
>   `Total words` is a **soft target** (the per-day goal handed to the writers).
>   Omitting both still works (the length tier falls back).
>
> ⚠ One chapter = one day = one draft the program produces, so "total chapters" is how
>   many days you intend to run.

- **Total chapters**: 20
- **Total words**: 40000
- **Words per chapter**: 2000

8 stations, 20 chapters, about 40k words.
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

### Station 1 · The last crossing

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: The first Lantern Festival. A Su packs up late and reaches the landing with
  only the last crossing left. Chen Du takes her aboard and waits a moment before casting
  off.
- **Done when**: A Su boards Chen Du's last crossing of the Lantern Festival.
- **Beats** (3 units):
  1. A Su packs up late and hurries down to the landing; one lamp is left burning there
  2. Chen Du casts off, then coils the rope again to wait for her
  3. She steps aboard, and only then does he push off with the oar
- **Climax**: A Su reaches the landing with only the last crossing left; Chen Du casts off
  the rope, coils it again to wait, and only when she is aboard does he push the oar.

### Station 2 · A broken reflection

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: At one bend A Su points at the water: "That lantern's reflection is broken."
  Chen Du says, "The bridge pier cuts it." They say nothing more; they come ashore at dawn
  and neither mentions it.
- **Done when**: A Su points out to his face that one lantern's reflection on the river is broken.
- **Beats** (3 units):
  1. The boat rounds a bend and A Su suddenly points at the water
  2. "That lantern's reflection is broken" — the reflection breaks in the middle of the bend
  3. Chen Du says "the bridge pier cuts it"; she does not ask a second question
- **Climax**: A Su points at the water where one lantern's reflection breaks off in the
  middle of the bend. Chen Du says "the bridge pier cuts it", and she asks nothing further.

### Station 3 · Once a year

- **Span**: six months
- **Length**: brief
- **Chapters**: 1
- **Summary**: The second year, the third, the fourth. Every festival the last crossing
  carries the same two people. What they say gets shorter every year, what they do gets
  longer: mending oars, reading stars, noting old piles in the riverbed.
- **Done when**: For several years running the two of them take the same last crossing.
- **Beats** (3 units):
  1. The second year, the third, the fourth — the same last crossing every festival
  2. Mending the oars, reading the stars, noting old piles in the riverbed
  3. In the third year he hands her the oar and she takes it; they row the bend in turn, and nobody mentions last year
- **Climax**: At the third festival Chen Du hands her the oar — she takes it, and they
  row the bend one after the other, and neither mentions the year before, or the one before that.

### Station 4 · Her sight failing

- **Span**: six months
- **Length**: normal
- **Chapters**: 2
- **Summary**: In the seventh year A Su's sight is almost gone: first the stitches blur,
  then the colours go. She tells nobody; she only draws the shop curtain closer.
- **Done when**: A Su herself confirms her sight has failed to the point where she cannot see her stitches.
- **Beats** (3 units):
  1. First the stitches blur, then the colours go
  2. She draws the shop curtain closer and tells nobody
  3. She holds the frame up to the lamp and misses the needle hole three times
- **Climax**: A Su holds the embroidery frame up to the lamp and misses the needle hole
  three times; she sets the frame down and touches the corner of her own eye.

### Station 5 · The last lamp flowers

- **Span**: three days
- **Length**: normal
- **Chapters**: 2
- **Summary**: Before the festival she finishes one last batch of lamp flowers. Each is
  missing a petal — she is embroidering the lanterns whose reflections are broken. Then she
  puts the needle away and does not take it out again.
- **Done when**: A Su finishes the last batch of lamp flowers, each missing a petal.
- **Beats** (3 units):
  1. She hurries to finish the last batch of lamp flowers before the festival, each missing a petal
  2. What she is embroidering is the lanterns whose reflections are broken
  3. She puts the needle in the box, closes the lid, and pushes it to the back of the cupboard
- **Climax**: A Su finishes the last lamp flower, each missing a petal, puts the needle into
  the sewing box, closes the lid, and pushes it to the back of the cupboard.

### Station 6 · What hangs on your awning

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: That festival night she does not mention her eyes; she asks only, "What is
  it hanging on your awning?" Chen Du says, "So I can see the river at night." She says,
  "You're lying," and asks nothing more.
- **Done when**: A Su asks to his face what hangs on the awning, and calls his answer a lie.
- **Beats** (3 units):
  1. That festival night she does not mention her eyes
  2. She looks up at the lamp on his awning and asks "what is it hanging on your awning?"
  3. He says "so I can see the river at night"; she says "you're lying" and asks nothing more
- **Climax**: A Su looks at the lamp on the awning and asks: "What is it hanging on your
  awning?" Chen Du says "So I can see the river at night." She says "You're lying," and then
  asks nothing more.

### Station 7 · She did not come

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: The eighth festival: the last crossing waits until midnight and A Su does
  not come. Chen Du unhooks the lanterns from the awning one by one and sets them on the
  landing steps — seven of them.
- **Done when**: A Su fails to appear on the eighth festival and Chen Du leaves the seven lanterns at the landing.
- **Beats** (3 units):
  1. The last crossing waits until midnight, and A Su does not come
  2. He unhooks the lanterns from the awning one by one
  3. He sets them in a row on the landing steps — seven of them
- **Climax**: The last crossing waits until midnight and A Su does not come; Chen Du
  unhooks the lanterns from his awning one by one and sets them in a row on the landing
  steps — seven of them.

### Station 8 · The eighth lamp

- **Span**: one scene
- **Length**: full
- **Chapters**: 3
- **Summary**: He rows out empty and stays the whole night at the bend she once pointed at.
  At dawn he comes back: there is one more lamp on the steps — the eighth, embroidered,
  missing a petal.
- **Done when**: Chen Du spends the night at the bend, returns, and finds an embroidered lamp added to the steps.
- **Beats** (3 units):
  1. He rows out empty and stays the whole night at the bend she once pointed at
  2. At dawn he comes back: there is one more lamp on the steps
  3. Embroidered, missing a petal — the eighth
- **Climax**: Chen Du rows the empty boat back from the bend, and it is just light; at
  the first glance he sees one more lamp on the steps — embroidered, missing a petal.
- **Choices**: stay and wait / follow the water / take the lamps and go
  - stay and wait: he hangs all eight lamps on the awning and keeps running the last crossing every festival.
  - follow the water: he follows the broken reflections downstream to find where the embroidered lamp came from.
  - take the lamps and go: he stows all eight in the cabin and stops hanging lamps, and stops waiting.
