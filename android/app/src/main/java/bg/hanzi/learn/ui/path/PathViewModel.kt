package bg.hanzi.learn.ui.path

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.CurriculumRepository
import bg.hanzi.learn.data.content.CurriculumUnit
import bg.hanzi.learn.data.content.WordEntry
import bg.hanzi.learn.data.db.DailyStats
import bg.hanzi.learn.data.db.DailyStatsDao
import bg.hanzi.learn.data.db.LearnerSettingDao
import bg.hanzi.learn.data.db.LessonProgressDao
import bg.hanzi.learn.data.db.SettingKey
import bg.hanzi.learn.data.db.SrsCardDao
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Calendar
import javax.inject.Inject

data class PathUiState(
    val loading: Boolean = true,
    val contentAvailable: Boolean = false,
    /** The units of the path, with the state of every lesson. */
    val units: List<UnitView> = emptyList(),
    /** The lesson to open next, or null when the path is finished. */
    val next: LessonView? = null,
    /** How much of the path is done, 0..100. */
    val percent: Int = 0,
    /** How many words the learner has met in total. */
    val wordsLearned: Int = 0,
    /** The cards that are due today. */
    val dueCount: Int = 0,
    /** How many reviews the learner has done today. */
    val todayReviewed: Int = 0,
    /** The daily goal in reviews. */
    val dailyGoal: Int = 20,
    /** How many days in a row the learner has studied. */
    val streakDays: Int = 0,
    /** The badges the learner has earned. */
    val badges: List<Badge> = emptyList(),
    /** Whether the learner has answered the first-run questions. */
    val onboarded: Boolean = false,
)

/**
 * The Path screen: the learning path, and the learner's place on it.
 *
 * The screen shows one thing above everything else: the next lesson. A
 * beginner who is met with a list of 10 896 words and a choice of seven
 * levels is not asked to learn; they are asked to decide, and the
 * decision is the wall. The path removes the decision.
 */
@HiltViewModel
class PathViewModel @Inject constructor(
    private val curriculum: CurriculumRepository,
    private val content: ContentRepository,
    private val progressDao: LessonProgressDao,
    private val srsDao: SrsCardDao,
    private val dailyStatsDao: DailyStatsDao,
    private val settingsDao: LearnerSettingDao,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PathUiState())
    val uiState: StateFlow<PathUiState> = _uiState.asStateFlow()

    private var cachedUnits: List<CurriculumUnit> = emptyList()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val available = content.isAvailable
            val units = curriculum.units()
            cachedUnits = units

            val lessons = units.flatMap { it.lessons }
            val progress = progressDao.all().first()
            val scores = progress.associate { it.lessonKey to it.bestScore }
            val states = PathRules.states(lessons, scores)

            // The words the learner has met: the ones with an SRS card.
            // The cards are created by the lessons, so this is the count
            // of the vocabulary the learner has actually seen.
            val wordsLearned = srsDao.totalCards().first()

            val due = srsDao.dueCount(startOfToday()).first()
            val today = DailyStats.todayKey()
            val todayStats = dailyStatsDao.forDay(today).first()
            val activeDays = dailyStatsDao.activeDays().first()
            val streak = DailyStats.streak(activeDays, today)

            val onboardingDone = settingsDao.get(SettingKey.ONBOARDED) == "true"
            val correctStreak = settingsDao.get(SettingKey.CORRECT_STREAK)?.toIntOrNull() ?: 0
            val productionOpen = settingsDao.get(SettingKey.PRODUCTION_UNLOCKED) == "true"

            val unitViews = units.map { unit ->
                UnitView(
                    unit = unit,
                    lessons = unit.lessons.map { lesson ->
                        LessonView(
                            lesson = lesson,
                            state = states[lesson.key] ?: PathRules.LessonState.LOCKED,
                            bestScore = scores[lesson.key] ?: 0,
                            wordCount = lesson.words.size,
                        )
                    },
                )
            }

            val nextLesson = PathRules.nextLesson(lessons, scores)
            val next = nextLesson?.let { lesson ->
                LessonView(
                    lesson = lesson,
                    state = PathRules.LessonState.CURRENT,
                    bestScore = scores[lesson.key] ?: 0,
                    wordCount = lesson.words.size,
                )
            }

            _uiState.value = PathUiState(
                loading = false,
                contentAvailable = available,
                units = unitViews,
                next = next,
                percent = PathRules.percentComplete(lessons, scores),
                wordsLearned = wordsLearned,
                dueCount = due,
                todayReviewed = todayStats?.reviews ?: 0,
                dailyGoal = settingsDao.get(SettingKey.DAILY_GOAL)?.toIntOrNull() ?: 20,
                streakDays = streak,
                badges = PathRules.badges(
                    wordsLearned = wordsLearned,
                    lessonsDone = lessons.count { (scores[it.key] ?: 0) >= PathRules.PASS_SCORE },
                    streakDays = streak,
                    productionUnlocked = productionOpen ||
                        PathRules.productionUnlocked(correctStreak, productionOpen),
                ),
                onboarded = onboardingDone,
            )
        }
    }

    /** Marks the first-run questions as answered. */
    fun completeOnboarding(goal: String, dailyMinutes: Int) {
        viewModelScope.launch {
            settingsDao.put(
                bg.hanzi.learn.data.db.LearnerSettingEntity(SettingKey.ONBOARDED, "true"),
            )
            settingsDao.put(
                bg.hanzi.learn.data.db.LearnerSettingEntity(SettingKey.GOAL, goal),
            )
            settingsDao.put(
                bg.hanzi.learn.data.db.LearnerSettingEntity(
                    SettingKey.DAILY_MINUTES,
                    dailyMinutes.toString(),
                ),
            )
            // The daily goal follows the time the learner has. Ten
            // minutes a day is twenty reviews; half an hour is sixty.
            val goal = when {
                dailyMinutes <= 5 -> 10
                dailyMinutes <= 15 -> 20
                dailyMinutes <= 30 -> 40
                else -> 60
            }
            settingsDao.put(
                bg.hanzi.learn.data.db.LearnerSettingEntity(
                    SettingKey.DAILY_GOAL,
                    goal.toString(),
                ),
            )
            refresh()
        }
    }

    private fun startOfToday(): Long = Calendar.getInstance().apply {
        set(Calendar.HOUR_OF_DAY, 0)
        set(Calendar.MINUTE, 0)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
    }.timeInMillis
}
