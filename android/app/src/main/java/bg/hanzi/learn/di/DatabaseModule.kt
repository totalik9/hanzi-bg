package bg.hanzi.learn.di

import android.content.Context
import androidx.room.Room
import bg.hanzi.learn.data.db.HanziUserDatabase
import bg.hanzi.learn.data.db.SrsCardDao
import bg.hanzi.learn.data.db.DailyStatsDao
import bg.hanzi.learn.data.db.BadgeDao
import bg.hanzi.learn.data.db.LearnerSettingDao
import bg.hanzi.learn.data.db.LessonProgressDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    /**
     * The migration from version 1 to version 2.
     *
     * Version 2 adds the learner's progress through the learning path.
     * The migration is written out instead of relying on the destructive
     * fallback: the SRS cards and the daily statistics are the only
     * record of what the learner has done, and a database wipe would
     * throw that away because three tables were added.
     */
    private val MIGRATION_1_2 = object : androidx.room.migration.Migration(1, 2) {
        override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS lesson_progress (
                    lessonKey TEXT NOT NULL,
                    bestScore INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    completedAt INTEGER,
                    PRIMARY KEY(lessonKey)
                )
                """.trimIndent(),
            )
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS badge (
                    id TEXT NOT NULL,
                    unlockedAt INTEGER NOT NULL,
                    PRIMARY KEY(id)
                )
                """.trimIndent(),
            )
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS learner_setting (
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(key)
                )
                """.trimIndent(),
            )
        }
    }

    @Provides
    @Singleton
    fun provideUserDatabase(@ApplicationContext context: Context): HanziUserDatabase =
        Room.databaseBuilder(context, HanziUserDatabase::class.java, "hanzi_user.db")
            .addMigrations(MIGRATION_1_2)
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideSrsCardDao(db: HanziUserDatabase): SrsCardDao = db.srsCardDao()

    @Provides
    fun provideDailyStatsDao(db: HanziUserDatabase): DailyStatsDao = db.dailyStatsDao()

    @Provides
    fun provideLessonProgressDao(db: HanziUserDatabase): LessonProgressDao =
        db.lessonProgressDao()

    @Provides
    fun provideBadgeDao(db: HanziUserDatabase): BadgeDao = db.badgeDao()

    @Provides
    fun provideLearnerSettingDao(db: HanziUserDatabase): LearnerSettingDao =
        db.learnerSettingDao()
}
