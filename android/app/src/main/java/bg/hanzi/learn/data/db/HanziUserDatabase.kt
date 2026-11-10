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

    @Query("SELECT COUNT(*) FROM srs_card")
    suspend fun totalCards(): Int

    @Query("DELETE FROM srs_card")
    suspend fun clear()
}

@Dao
interface DailyStatsDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(stats: DailyStatsEntity)

    @Query("SELECT * FROM daily_stats WHERE day = :day")
    fun forDay(day: String): Flow<DailyStatsEntity?>

    @Query("SELECT COALESCE(SUM(reviews), 0) FROM daily_stats WHERE day >= :since")
    fun reviewsSince(since: String): Flow<Int>
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
