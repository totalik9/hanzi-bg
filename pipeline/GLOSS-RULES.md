# The rules of a hand-written Bulgarian gloss

This is the contract for `curriculum/21_glosses_hsk2to4.json` — the
Bulgarian gloss of every word of the HSK 2-4 path.

The gloss is what the learner reads on the card. It is the ONE
meaning the word has in the lesson that teaches it.

## The rules the checker enforces

`pipeline/_check_gloss_slice.py <slice.json> <glosses.json>` says
whether a slice is good. A rule that fails is an error; a rule that
only warns is a hint.

1. **Every word of the slice has a gloss.** Not one may be missing.
2. **At most 45 characters.** The HSK-1 glosses have a median of 8
   and a maximum of 29. A gloss that needs a sentence is a gloss that
   says nothing.
3. **No "/" and no parenthesis.** The learner reads ONE meaning on a
   card, not four. The machine translation lists every sense a
   dictionary has — "бяло / бял / реакционен / антикомунистически"
   — and that shape is exactly what a hand-written gloss must not
   have. When a word has two senses that both matter, use a
   semicolon: "обличам се; нося дрехи".
4. **No two words of the SAME LESSON may carry the same gloss.** The
   card offers the right answer and three wrong ones; two words with
   the same meaning make a question with two right answers. This
   happened for real on 2026-11-23: 二 "два" and 两 "два, когато
   броим предмети" — the learner picked the everyday word and was
   told it was wrong.
5. **A hint, not an error:** two words of the same lesson whose
   glosses start with the same three letters cannot test each other,
   because the app refuses a twin of the answer as a distractor. The
   warning says the two meanings are too close to be told apart — pick
   a different wording for one of them.

## What the gloss is NOT

- **Not a description of the word.** "измерителна дума за книги"
  describes 本; "книга" says what it means. The classifier words are
  the exception the HSK-1 file already made: 本, 件, 些, 个 and 只
  have no other meaning, so they are named for what they count.
- **Not a dictionary dump.** One sense, in the words a teacher would
  use with a beginner.
- **Not the English.** It is Bulgarian, in the vocabulary of the
  HSK-1 glosses (which is the vocabulary the learner already has).

## The style of the HSK-1 glosses

Read `curriculum/20_glosses_hsk1.json` — it is the reference. Its
shape:

```
爸爸=татко          好=добър           吃=ям
茶=чай              车=автомобил       穿=обличам се; нося дрехи
医院=болниница      时间=време          自行车=велосипед
不=отрицание 'не'   的=структурна частица
```

- Lower case, no full stop.
- A noun is a noun. A verb is the verb in the infinitive: "ям",
  "пия", "чета".
- Two senses that both matter are joined by a semicolon: "обличам
  се; нося дрехи", "стая; между".
- A particle is named for what it does: "структурна частица",
  "отрицание 'не'", "въпросителна дума".
- The word the HSK list teaches is the word that is written down.
  When the English meaning names two senses, take the one the LEVEL
  teaches: 快乐 at HSK 2 is "happy; joyful", so "радлив" — not the
  full dictionary range.

## The sense comes from the English meaning

The slice gives the English meaning of the official HSK list for each
word. That is the SENSE: the word is taught in that sense, and the
Bulgarian gloss must say that sense and not another one.

    万  wàn   "ten thousand; a huge number"   ->  десет хиляди
    时  shí   "time; hour; period"           ->  час
    累  lèi   "tired; weary"                 ->  уморен

When the English meaning is a range, take the part the level teaches.
When it names a technical sense, keep it — but find the everyday
Bulgarian word for it first ("план" for "plan", not "проект").

## The output

A JSON object, the word as the key and the gloss as the value:

```json
{"万": "десет хиляди", "帮": "помагам", "累": "уморен"}
```

Write it with `write_file` to the path the task names, then run the
checker and fix what it reports.
