package bg.hanzi.learn.ui.screens.dictionary

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.WordEntry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

data class DictionaryUiState(
    val loading: Boolean = false,
    val results: List<WordEntry> = emptyList(),
    /**
     * When true, only the words whose Bulgarian gloss was written by a
     * person are shown.
     *
     * The machine translation covers 95 % of the vocabulary, but a
     * machine gloss can be wrong, and the column `gloss_source` says
     * which is which. A learner who wants only the checked words can
     * ask for them.
     */
    val humanGlossesOnly: Boolean = false,
)

@OptIn(FlowPreview::class)
@HiltViewModel
class DictionaryViewModel @Inject constructor(
    private val content: ContentRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DictionaryUiState())
    val uiState: StateFlow<DictionaryUiState> = _uiState.asStateFlow()

    private val queries = MutableStateFlow("")
    private var humanGlossesOnly = false

    init {
        queries
            .debounce(250)
            .distinctUntilChanged()
            .onEach { q -> runSearch(q) }
            .launchIn(viewModelScope)
    }

    fun search(query: String) {
        queries.value = query
    }

    /** Shows or hides the words whose Bulgarian gloss came from a machine. */
    fun setHumanGlossesOnly(enabled: Boolean) {
        humanGlossesOnly = enabled
        val q = queries.value
        viewModelScope.launch { runSearch(q) }
    }

    private suspend fun runSearch(query: String) {
        if (query.isBlank()) {
            _uiState.value = DictionaryUiState(
                loading = false,
                results = emptyList(),
                humanGlossesOnly = humanGlossesOnly,
            )
            return
        }
        _uiState.value = _uiState.value.copy(loading = true)
        val results = withContext(Dispatchers.IO) { content.search(query, limit = 50) }
        val filtered = if (humanGlossesOnly) {
            // Only the glosses a person wrote, with no machine text in
            // them. A combined gloss has both, so it does not pass.
            results.filter { it.glossSource == "human" }
        } else {
            results
        }
        _uiState.value = DictionaryUiState(
            loading = false,
            results = filtered,
            humanGlossesOnly = humanGlossesOnly,
        )
    }
}
