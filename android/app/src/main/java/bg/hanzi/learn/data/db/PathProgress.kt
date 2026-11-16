package bg.hanzi.learn.data.db

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/**
 * The learner's progress through the learning path.
 *
 * The path itself is in the read-only content database. What the learner
 * has DONE with it is user state, so it lives here, in the database that
 * is allowed to change.
 *
 * The old "lessons" table held one row per HSK level and was never read
 * by a screen; this table is the one that decides what the learner is
 * allowed to open next.
 */
@Entity(tableName = "lesson_progress")
data class LessonProgressEntity(
    @PrimaryKey val lessonKey: String,
    /** 0..100 -- the best score the learner reached in this lesson. */
    val bestScore: Int,
    /** How many times the lesson was finished. */
    val attempts: Int,
    /** When the lesson was last completed, or null if it never was. */
    val completedAt: Long?,
)

/**
 * The badges the learner has earned.
 *
 * A badge is earned by a fact about the learner (a streak, a number of
 * words), and it is recorded so that it can be shown once, when it is
 * earned, and afterwards in the list.
 */
@Entity(tableName = "badge")
data class BadgeEntity(
    @PrimaryKey val id: String,
    val unlockedAt: Long,
)

/**
 * A single key/value setting of the learner's account.
 *
 * It holds the answers of the first-run questions (why the learner is
 * studying Chinese, how much time they have) and the counters the
 * lessons depend on.
 */
@Entity(tableName = "learner_setting")
data class LearnerSettingEntity(
    @PrimaryKey val key: String,
    val value: String,
)

@Dao
interface LessonProgressDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(progress: LessonProgressEntity)

    @Query("SELECT * FROM lesson_progress")
    fun all(): Flow<List<LessonProgressEntity>>

    @Query("SELECT * FROM lesson_progress WHERE lessonKey = :key LIMIT 1")
    suspend fun find(key: String): LessonProgressEntity?

    @Query("SELECT COUNT(*) FROM lesson_progress WHERE completedAt IS NOT NULL")
    fun completedCount(): Flow<Int>
}

@Dao
interface BadgeDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun unlock(badge: BadgeEntity)

    @Query("SELECT * FROM badge ORDER BY unlockedAt DESC")
    fun all(): Flow<List<BadgeEntity>>

    @Query("SELECT id FROM badge")
    suspend fun unlockedIds(): List<String>
}

@Dao
interface LearnerSettingDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(setting: LearnerSettingEntity)

    @Query("SELECT value FROM learner_setting WHERE key = :key LIMIT 1")
    suspend fun get(key: String): String?

    @Query("SELECT * FROM learner_setting")
    fun all(): Flow<List<LearnerSettingEntity>>
}

/**
 * The keys of the settings, in one place so a typo cannot silently
 * create a second, unread setting.
 */
object SettingKey {
    /** "true" once the learner has answered the first-run questions. */
    const val ONBOARDED = "onboarded"

    /** Why the learner is studying Chinese. */
    const val GOAL = "goal"

    /** How many minutes the learner has a day. */
    const val DAILY_MINUTES = "daily_minutes"

    /** The daily goal in reviews. */
    const val DAILY_GOAL = "daily_goal"

    /** The day the learner last opened the app, for the streak. */
    const val LAST_OPEN_DAY = "last_open_day"

    /** The number of consecutive days the learner has studied. */
    const val STREAK_DAYS = "streak_days"

    /**
     * How many answers in a row the learner has got right.
     *
     * The production exercise (pinyin -> character) opens after 20 in a
     * row: it is the step the simulation says 14 of 20 learners can do,
     * and it is the step that turns a passive dictionary into a spoken
     * language. Unlocking it on a streak keeps it from being a wall.
     */
    const val CORRECT_STREAK = "correct_streak"

    /** "true" once the production exercise has been unlocked. */
    const val PRODUCTION_UNLOCKED = "production_unlocked"
}
