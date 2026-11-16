package bg.hanzi.learn.ui.path

import bg.hanzi.learn.data.content.CurriculumLesson
import bg.hanzi.learn.data.content.CurriculumUnit

/**
 * The rules of the learning path, without any Compose dependency.
 *
 * These rules decide what the learner is allowed to open, when the next
 * lesson unlocks, and whether a lesson was passed. They are plain
 * functions on purpose: a rule that decides whether a beginner can move
 * forward is worth a unit test, and a ViewModel test would need a
 * device.
 */
object PathRules {

    /**
     * The score a lesson needs to be passed.
     *
     * 80 % and not 100 %: a beginner who misses one of eight answers is
     * not a beginner who failed, and a wall here is where people stop.
     */
    const val PASS_SCORE = 80

    /**
     * The number of correct answers in a row that opens the production
     * exercise.
     *
     * The simulation found that 14 of 20 learners could produce Chinese
     * once the app asked them to, but only 2 of 20 reached the
     * vocabulary without it. So production is not an optional extra --
     * but it is also not something to throw at somebody on day one,
     * before they know what pinyin is. Twenty in a row is a promise
     * that they have the basics.
     */
    const val PRODUCTION_STREAK = 20

    /**
     * How many words the learner has to know before the writing step
     * joins the lesson.
     *
     * Writing is the slowest step and the one learners give up on. It
     * is also the one that has to happen for a character to stick, so it
     * comes in once the learner has a reason to care: after they have
     * met a couple of dozen characters.
     */
    const val WRITING_AFTER_WORDS = 20

    /** How a lesson stands relative to the learner's progress. */
    enum class LessonState {
        /** Done: it was passed. */
        DONE,

        /** The next lesson: it can be opened now. */
        CURRENT,

        /** Locked: the lesson before it was not passed. */
        LOCKED,
    }

    /**
     * The state of every lesson of the path.
     *
     * The path is linear: a lesson opens when the one before it was
     * passed with [PASS_SCORE] or better. A lesson that was attempted
     * but not passed stays [CURRENT] -- the learner retries it, and the
     * next one stays locked.
     *
     * A "teach" lesson is a reading lesson and has no score of its own;
     * the app records 100 for it when the learner has read it to the
     * end, so it opens the next lesson the same way a vocabulary lesson
     * does.
     *
     * @param lessons the path, in order
     * @param scores the best score of each lesson, by lesson key
     */
    fun states(
        lessons: List<CurriculumLesson>,
        scores: Map<String, Int>,
    ): Map<String, LessonState> {
        val states = mutableMapOf<String, LessonState>()
        var open = true
        for (lesson in lessons) {
            val score = scores[lesson.key] ?: 0
            val passed = score >= PASS_SCORE
            states[lesson.key] = when {
                passed -> LessonState.DONE
                open -> LessonState.CURRENT
                else -> LessonState.LOCKED
            }
            // The chain continues only through a lesson that was passed.
            if (passed) open = true else open = false
        }
        return states
    }

    /**
     * The lesson the learner should open next.
     *
     * It is the first lesson that is not done, or null when the whole
     * path is finished.
     */
    fun nextLesson(
        lessons: List<CurriculumLesson>,
        scores: Map<String, Int>,
    ): CurriculumLesson? {
        val states = states(lessons, scores)
        return lessons.firstOrNull { states[it.key] == LessonState.CURRENT }
    }

    /**
     * How much of the path is done, as a percentage.
     *
     * It counts the lessons that were passed, not the words: the unit
     * is the lesson, because that is what the learner completes.
     */
    fun percentComplete(
        lessons: List<CurriculumLesson>,
        scores: Map<String, Int>,
    ): Int {
        if (lessons.isEmpty()) return 0
        val done = lessons.count { (scores[it.key] ?: 0) >= PASS_SCORE }
        return (done * 100) / lessons.size
    }

    /**
     * Whether the production exercise is open.
     *
     * @param correctStreak how many answers in a row were right
     * @param alreadyUnlocked whether it was opened before
     */
    fun productionUnlocked(correctStreak: Int, alreadyUnlocked: Boolean): Boolean =
        alreadyUnlocked || correctStreak >= PRODUCTION_STREAK

    /**
     * Whether the writing step belongs in the lesson right now.
     *
     * @param wordsLearned how many words the learner has met in total
     */
    fun writingEnabled(wordsLearned: Int): Boolean = wordsLearned >= WRITING_AFTER_WORDS

    /**
     * The badges the learner has earned.
     *
     * The list is derived from the facts, not stored as a checklist, so
     * a badge cannot be "forgotten": if the learner has 100 words, the
     * badge for 100 words is earned, whatever happened to the database.
     *
     * @param wordsLearned how many words the learner has met
     * @param lessonsDone how many lessons were passed
     * @param streakDays how many days in a row the learner has studied
     * @param productionUnlocked whether the production exercise is open
     */
    fun badges(
        wordsLearned: Int,
        lessonsDone: Int,
        streakDays: Int,
        productionUnlocked: Boolean,
    ): List<Badge> {
        val badges = mutableListOf<Badge>()
        if (wordsLearned >= 1) badges += Badge.FIRST_WORD
        if (wordsLearned >= 20) badges += Badge.TWENTY_WORDS
        if (wordsLearned >= 50) badges += Badge.FIFTY_WORDS
        if (wordsLearned >= 100) badges += Badge.HUNDRED_WORDS
        if (lessonsDone >= 1) badges += Badge.FIRST_LESSON
        if (lessonsDone >= 10) badges += Badge.TEN_LESSONS
        if (streakDays >= 3) badges += Badge.STREAK_THREE
        if (streakDays >= 7) badges += Badge.STREAK_SEVEN
        if (streakDays >= 30) badges += Badge.STREAK_THIRTY
        if (productionUnlocked) badges += Badge.PRODUCTION
        return badges
    }
}

/**
 * A badge the learner can earn.
 *
 * The titles are in Bulgarian because they are shown to the learner.
 */
enum class Badge(val id: String, val title: String, val description: String) {
    FIRST_WORD("first_word", "Първата дума", "Първата дума, която научи"),
    TWENTY_WORDS("twenty_words", "20 думи", "Научи 20 думи"),
    FIFTY_WORDS("fifty_words", "50 думи", "Научи 50 думи"),
    HUNDRED_WORDS("hundred_words", "100 думи", "Научи 100 думи"),
    FIRST_LESSON("first_lesson", "Първи урок", "Завърши първия урок"),
    TEN_LESSONS("ten_lessons", "10 урока", "Завърши 10 урока"),
    STREAK_THREE("streak_three", "3 дни", "Учи се 3 дни поред"),
    STREAK_SEVEN("streak_seven", "7 дни", "Учи се 7 дни поред"),
    STREAK_THIRTY("streak_thirty", "30 дни", "Учи се 30 дни поред"),
    PRODUCTION("production", "Производство", "Отключи произвеждането на думи"),
}

/**
 * A unit of the path with its lessons and their states.
 *
 * It is what the Path screen renders, so it carries the state of every
 * lesson instead of leaving the screen to work it out.
 */
data class UnitView(
    val unit: CurriculumUnit,
    val lessons: List<LessonView>,
) {
    val doneCount: Int get() = lessons.count { it.state == PathRules.LessonState.DONE }
    val isDone: Boolean get() = lessons.isNotEmpty() && doneCount == lessons.size
    val isUnlocked: Boolean
        get() = lessons.any { it.state != PathRules.LessonState.LOCKED }
}

data class LessonView(
    val lesson: CurriculumLesson,
    val state: PathRules.LessonState,
    val bestScore: Int,
    val wordCount: Int,
)
