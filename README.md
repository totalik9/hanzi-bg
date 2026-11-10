# Ханзи BG

Приложение за изучаване на китайски (мандарин) **от български**.
Android 16+ (API 36), Kotlin + Jetpack Compose, напълно офлайн.

```
hanzi-bg/
├── PLAN.md          планът за изграждане + резултат от симулацията
├── pipeline/        Python: сваляне и извличане на съдържанието
├── data/            генерирани данни (не се версионират)
├── simulation/      симулация на 20 ученици → може ли A2 да се научи?
└── android/         Android проект
```

---

## Състояние

| Компонент | Статус |
|---|---|
| Инструментна верига (AGP 8.10.1, Gradle 8.11.1, JDK 17, Build Tools 36.0.0) | работеща |
| Android скелет: 5 екрана, Room, Hilt, Media3 | работещ |
| SRS планировчик (SM-2, FSRS-съвместим) | работещ + unit тестове |
| Типография с CJK мащаб (1.8× за йероглифи) | работеща |
| Pipeline за съдържание (8 скрипта) | в процес |
| Симулация на 20 ученици за A2 | работеща |

---

## Изисквания

- JDK 17+
- Android SDK: platform 36, build-tools 36.0.0
- `local.properties` → `sdk.dir=<път до SDK>`
- Python 3.10+ за pipeline-а

---

## Как се пуска

### 1. Съдържание

```bash
cd pipeline
python 01_fetch_sources.py        # сваля източниците (CC-CEDICT, Make Me a Hanzi,
                                  # HSK 3.0 CSV, Grammar Wiki, Tatoeba, pinyin-data)
python 02_build_dictionary.py      # -> data/hanzi.db (125 397 речникови реда,
                                  #    9 574 знака, 112 617 щриха)
python 03_build_vocab.py           # -> data/vocab_hsk.json (10 896 HSK 3.0 думи)
python 04_build_grammar.py         # -> data/grammar.json
python 05_build_sentences.py       # -> data/sentences.json
python 06_build_audio.py           # -> data/audio/*.mp3 (Edge TTS)
python 07_translate_bulgarian.py   # -> български глоси
python 08_build_content_db.py      # -> data/content.db
```

Всички скриптове са **безопасни за повторно изпълнение** — прескачат
вече свалените файлове и вече генерираното аудио.

### 2. Приложение

```bash
cd ../android
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 3. Симулация

```bash
cd ../simulation
python test_simulation.py          # самопроверки на модела
python make_vectors.py             # генерира тестови вектори
python simulate_learners.py        # 20 ученици → A2 постижим ли е?
```

---

## Архитектура

**Две бази, по две причини:**

| База | Съдържание | Мутация |
|---|---|---|
| `content.db` (asset, read-only) | речник, думи, граматика, изречения, йероглифи | никога |
| `hanzi_user.db` (Room) | SRS карти, статистика | да |

`content.db` се копира от assets при първо стартиране — assets не могат да
се четат от SQLite. Копието се валидира по размер, за да се презапише при
нова версия на съдържанието.

**Без native код** → изискването на Google Play за 16 KB page size се
изпълнява автоматично.

**Един споделен ExoPlayer** за всички аудио клипове — създаването на
играч на клип харчи ~10 MB памет, което се усеща на 8 GB устройство.

---

## Източници и лицензи

| Източник | Лиценз |
|---|---|
| [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cedict) | CC BY-SA 4.0 |
| [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) | Arphic Public License |
| [HSK 3.0 word lists](https://literatelanguages.com/chinese/hsk-vocabulary/) | виж източника |
| [Chinese Grammar Wiki](https://resources.allsetlearning.com/chinese/grammar/Main_Page) | Creative Commons |
| [Tatoeba](https://tatoeba.org/en/downloads) | CC BY 2.0 FR |
| [pinyin-data](https://github.com/mozillazg/pinyin-data) | MIT |
| [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) | CC-BY-NC (български превод) |

Атрибуцията трябва да се запази при разпространение.
