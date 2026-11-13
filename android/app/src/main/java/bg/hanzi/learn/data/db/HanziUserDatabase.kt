package bg.hanzi.learn.data.db

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/**
 * User-owned state. The read-only content (dictionary, vocabulary, grammar)
 * lives in a separate content.db that is shipped as an asset and copied on
 * first launch — it never needs migration.
 */
@Entity(tableName = "srs_card")
data class SrsCardEntity(
    @PrimaryKey val itemId: String,
    val level: String,
    val dueAt: Long,
    val stability: Double,
    val difficulty: Double,
    val reps: Int,
    val lapses: Int,
    val state: Int,
    val lastReviewAt: Long?,
)

@Entity(tableName = "daily_stats")
data class DailyStatsEntity(
    @PrimaryKey val day: String,
    val reviews: Int,
    val correct: Int,
    val newWords: Int,
)

@Dao
interface SrsCardDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(card: SrsCardEntity)

    @Query("SELECT * FROM srs_card WHERE dueAt <= :now ORDER BY dueAt ASC LIMIT :limit")
    suspend fun dueCards(now: Long, limit: Int): List<SrsCardEntity>

    @Query("SELECT COUNT(*) FROM srs_card WHERE dueAt <= :now")
    fun dueCount(now: Long): Flow<Int>

    @Query("SELECT * FROM srs_card WHERE itemId = :itemId LIMIT 1")
    suspend fun findById(itemId: String): SrsCardEntity?

    @Query("SELECT COUNT(*) FROM srs_card WHERE level = :level")
    suspend fun learnedCount(level: String): Int
}

@Dao
interface DailyStatsDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(stats: DailyStatsEntity)

    @Query("SELECT * FROM daily_stats WHERE day = :day")
    fun forDay(day: String): Flow<DailyStatsEntity?>

    @Query("SELECT COALESCE(SUM(reviews), 0) FROM daily_stats WHERE day >= :since")
    fun reviewsSince(since: String): Flow<Int>

    /**
     * The days that have at least one review, newest first.
     *
     * The streak is computed from this list rather than in SQL: a streak
     * is a run of consecutive days, and expressing that in SQLite needs
     * a recursive query that is much harder to read than the loop that
     * consumes this list.
     */
    @Query("SELECT day FROM daily_stats WHERE reviews > 0 ORDER BY day DESC")
    fun activeDays(): Flow<List<String>>

    /**
     * Record one graded review.
     *
     * The counters are incremented in the database rather than read,
     * written and written back, so two reviews in the same second
     * cannot lose one another.
     */
    @Query(
        """
        INSERT INTO daily_stats (day, reviews, correct, newWords)
        VALUES (:day, :reviews, :correct, :newWords)
        ON CONFLICT(day) DO UPDATE SET
            reviews = reviews + :reviews,
            correct = correct + :correct,
            newWords = newWords + :newWords
        """
    )
    suspend fun recordReview(day: String, reviews: Int, correct: Int, newWords: Int)
}

@Database(
    entities = [SrsCardEntity::class, DailyStatsEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class HanziUserDatabase : RoomDatabase() {
    abstract fun srsCardDao(): SrsCardDao
    abstract fun dailyStatsDao(): DailyStatsDao
}
