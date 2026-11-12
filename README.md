# Ханзи BG

Приложение за изучаване на китайски (мандарин) **от български**.
Android 16+ (API 36), Kotlin + Jetpack Compose, напълно офлайн.

```
hanzi-bg/
├── PLAN.md          планът + какво е свършено и какво остава
├── pipeline/        Python: сваляне, извличане, превод, аудио, content.db
├── data/            генерирани данни (не се версионират)
├── simulation/      симулация на 20 ученици → може ли A2 да се научи?
└── android/         Android проект
```

---

## Състояние към 2026-11-10

Всичко е **проверено чрез изпълнение**, не чрез четене.

| Компонент | Статус |
|---|---|
| Инструментна верига (AGP 8.10.1, Gradle 8.11.1, JDK 17, Build Tools 36.0.0) | работеща |
| Android скелет: 6 екрана, Room, Hilt, Media3 | работещ, **build successful** |
| Unit тестове | **38/38 минават** |
| SRS планировчик (SM-2, FSRS-съвместим) | работещ + parity тест с Python |
| Pipeline за съдържание (10 скрипта) | **завършен** |
| `content.db` (19.8 MB) | **в assets на APK-а** |
| Български превод (NLLB-200) | **завършен**: 10 690 думи с глос (92 чисто човешки + 365 човешки+машинни + 10 233 машинни) |
| Покритие с български глос | **10 690 / 10 896 думи (98 %)** |
| Аудио (Edge TTS) | **1 386 клипа** = целият HSK 1–3 |
| Пиньин IME, word order, stroke order, слушане, граматичен тест | **работещи на емулатор** |
| Release build | **минава** (39.2 MB) |
| Симулация на 20 ученици за A2 | работеща; **производство 0/20 → 14/20** |

**Проверено на емулатор (API 34):** `content.db` копиран байт по байт
(19 750 912 → 19 750 912), 1 386 аудио клипа в APK-а, аудиото се
възпроизвежда (44 928 кадъра доставени), **0 крашове**. Подреждането
показва „Правилно!", писането — „Правилни щрихи: 5 / 6".

> **Забележка за машинните преводи.** Поле `gloss_source` във всяка дума
> казва `human`, `machine` или `human+machine`, за да може машинният текст
> да се прегледа и замени. При `human+machine` човешкият глос е първи, а
> машилените смисли, които той не покрива, следват него; приложението
> показва „машинен превод — може да е неточен" и при търсене, и при
> преглед. NLLB е CC-BY-NC — виж „Източници и лицензи" по-долу.

---

## Изисквания

- JDK 17+ (на машината: `C:\tools\jdk-17.0.2`)
- Android SDK: platform 36, build-tools 36.0.0 (`C:\tools\android-sdk`)
- `local.properties` → `sdk.dir=<път до SDK>`
- Python 3.10+ за pipeline-а (3.11 е проверена)
- **За превода:** ~2.5 GB модел `facebook/nllb-200-distilled-600M`

---

## Как се пуска

### 1. Съдържание

```bash
cd pipeline
python 01_fetch_sources.py        # сваля източниците (идемпотентен)
python 02_build_dictionary.py      # -> data/hanzi.db (125 397 реда, 9 574 знака)
python 03_build_vocab.py           # -> data/vocab_hsk.json (10 896 HSK 3.0 думи)
python 04_build_grammar.py         # -> data/grammar.json (506 точки, 3 286 примера)
python 05_build_sentences.py       # -> data/sentences.json (89 254 изречения)
python 06_build_audio.py           # -> data/audio/*.mp3 (Edge TTS)
python 09_clean_glosses.py         # -> чисти английските глоси ПРЕДИ превода
python 07_translate_bulgarian.py   # -> data/bg_translations.json (NLLB-200)
python 08_build_content_db.py      # -> data/content.db
python 10_compare_models.py        # -> сравнява NLLB-200 с M2M-100
```

**Важно:** `08_build_content_db.py` изтрива и пресъздава `content.db`.
Ако файлът е заключен (от отворен sqlite конектор или от емулатора),
скриптът го изпразва на място и продължава — и казва го.

**`07_translate_bulgarian.py` пази кеш на ниво смисъл**
(`data/bg_sense_cache.json`). Пълният превод е 16 135 смисла и отнема
~95 мин на CPU; след първия път само новите смисли се превеждат. Кешът
се самопопълва от предишния файл, така че прекъсване в средата не
губи работа.

**Редът е важен:** `09_clean_glosses.py` трябва да върви **преди**
`07_translate_bulgarian.py` и `08_build_content_db.py`, защото той
пренаписва `data/vocab_hsk.json` — файла, от който преводачът чете
смислите и от който базата данни взима глосовете. При стария ред
(`08` преди `09`) почистването просто не достигаше до базата: тя носеше
126 непочистени английски глоса. Без почистването моделът превежда
смисли, които са шум
(„(CL: )", „Fig.", „(abbr.)"), и чужият текст отива в картата на
ученика. `07` използва същата функция за почистване, така че двете
правила не се разминават.

**`10_compare_models.py`** пъска едни и същи смисли през NLLB-200 и
M2M-100 и записва резултата един до друг в `data/model_compare.json`.
Измерено на 150 смисла: NLLB-200 дава използвам български глос за
**92.0 %** от тях, M2M-100 — за 89.3 %. Остава NLLB-200.

### 2. Приложение

```bash
cd ../android
./gradlew :app:assembleDebug
./gradlew :app:assembleRelease      # иска 39.2 MB, unsigned
./gradlew :app:testDebugUnitTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Gradle task-ът `syncContentDb` копира `data/content.db` и
`data/audio/*.mp3` в assets-ите автоматично. Ако артефактите липсват,
задачата се пропуска и приложението се build-ва без съдържание.

Assets-ите се пишат в `build/generated/assets`, а не в
`app/src/main/assets`. Причината е конкретна: `lintVital` чете assets
папката, ако тя е източник, Gradle вижда едни и същи файлове като вход
и като изход на друга задача, и release build-ът пада с
„uses this output of task ':app:syncContentDb' without declaring an
explicit or implicit dependency".

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
| `content.db` (asset, read-only) | речник, думи, граматика, изречения, знаци, IME индекс | никога |
| `hanzi_user.db` (Room) | SRS карти, статистика | да |

`content.db` се копира от assets при първо стартиране — assets не могат
да се четат от SQLite. Копието е валидирано по размер, за да се
презапише при нова версия на съдържанието.

**Без собствен native код** → изискването на Google Play за 16 KB
page size се изпълнява. (Внимание: APK-то всъщност носи 8 `.so`
библиотеки от транзитивни AndroidX зависимости — всички с
`p_align = 16384`, проверено.)

**Един споделен ExoPlayer** за всички аудио клипове — създаването на
играч на клип харчи ~10 MB памет, което се усеща на 8 GB устройство.

### Учебни режими

Пет режима в раздел „Упражнения“, всеки отговор на конкретна находка
от симулацията:

| Режим | Какво решава |
|---|---|
| Производство (пиньин IME) | „0/20 могат да произвеждат“ |
| Слушане | упражнение за тона и изговорение |
| Подреждане | словоред — оценява се, не само се показва |
| Писане | stroke order + проследяване с пръст |
| Граматика | граматиката се чеше, но не се проверяваше |

Всичките пет режима са проверени на емулатор, а оценяването на
подреждането и на писането е изнесено в чисти функции
(`WordOrderScoring.kt`, `StrokeMatching.kt`), за които има unit тестове.
Писането проверява реда на щриховете, а не само формата им — първата
версия сравняваше по форма и ученикът можеше да проследи знака в
произволен ред.

---

## Източници и лицензи

| Източник | Лиценз |
|---|---|
| [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cedict) | CC BY-SA 4.0 |
| [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) | Arphic Public License |
| [HSK 3.0 word lists](https://literatelanguages.com/chinese/) | виж източника |
| [Chinese Grammar Wiki](https://resources.allsetlearning.com/chinese/grammar/Main_Page) | Creative Commons |
| [Tatoeba](https://tatoeba.org/en/downloads) | CC BY 2.0 FR |
| [pinyin-data](https://github.com/mozillazg/pinyin-data) | MIT |
| [NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M) | **CC-BY-NC** |

> **NLLB-200 е CC-BY-NC.** Допустимо за този некомерсиален проект.
> **Блокира платено разпространение** — преди Play Store машинните
> преводи трябва да се заменят с човешки или с модел под свободен
> лиценз. Вж. `PLAN.md`, раздел 9.

Атрибуцията трябва да се запази при разпространение.
