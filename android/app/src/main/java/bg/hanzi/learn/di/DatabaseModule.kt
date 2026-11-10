package bg.hanzi.learn.di

import android.content.Context
import androidx.room.Room
import bg.hanzi.learn.data.db.HanziUserDatabase
import bg.hanzi.learn.data.db.SrsCardDao
import bg.hanzi.learn.data.db.DailyStatsDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideUserDatabase(@ApplicationContext context: Context): HanziUserDatabase =
        Room.databaseBuilder(context, HanziUserDatabase::class.java, "hanzi_user.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideSrsCardDao(db: HanziUserDatabase): SrsCardDao = db.srsCardDao()

    @Provides
    fun provideDailyStatsDao(db: HanziUserDatabase): DailyStatsDao = db.dailyStatsDao()
}
