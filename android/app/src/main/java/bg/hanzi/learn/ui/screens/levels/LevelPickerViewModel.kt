package bg.hanzi.learn.ui.screens.levels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.LevelSelection
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

/** One HSK level and what the app can do with it. */
data class LevelInfo(
    /** The level id as the database stores it ("1", "7-9"). */
    val id: String,
    /** The level as the learner reads it ("HSK 1", "HSK 7-9"). */
    val label: String,
    /** How many words the level holds. */
    val wordCount: Int,
    /**
     * Whether the level has pronunciation clips.
     *
     * Every level has clips now: the audio for HSK 7 to 9 was built in
     * November 2026, so the 5 562 words of that level can be heard
     * too. The flag is still read from the database rather than assumed,
     * because a level can lose its clips -- the app then says so
     * instead of offering a button that plays nothing.
     */
    val hasAudio: Boolean,
)

data class LevelPickerUiState(
    val loading: Boolean = true,
    val levels: List<LevelInfo> = emptyList(),
)

/**
 * Reads the levels the vocabulary is graded into.
 *
 * The counts and the audio are read from the content database, so the
 * picker cannot promise a level the app does not have.
 */
@HiltViewModel
class LevelPickerViewModel @Inject constructor(
    private val content: ContentRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LevelPickerUiState())
    val uiState: StateFlow<LevelPickerUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    private fun load() {
        viewModelScope.launch {
            val levels = withContext(Dispatchers.IO) {
                content.levels().map { id ->
                    LevelInfo(
                        id = id,
                        label = "HSK ${LevelSelection.labelOf(id).removePrefix("HSK ")}",
                        wordCount = content.wordCount(id),
                        hasAudio = content.levelHasAudio(id),
                    )
                }
            }
            _uiState.value = LevelPickerUiState(loading = false, levels = levels)
        }
    }
}
