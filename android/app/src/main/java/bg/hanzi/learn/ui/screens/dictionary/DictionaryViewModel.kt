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
import kotlinx.coroutines.withContext
import javax.inject.Inject

data class DictionaryUiState(
    val loading: Boolean = false,
    val results: List<WordEntry> = emptyList(),
)

@OptIn(FlowPreview::class)
@HiltViewModel
class DictionaryViewModel @Inject constructor(
    private val content: ContentRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DictionaryUiState())
    val uiState: StateFlow<DictionaryUiState> = _uiState.asStateFlow()

    private val queries = MutableStateFlow("")

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

    private suspend fun runSearch(query: String) {
        if (query.isBlank()) {
            _uiState.value = DictionaryUiState(loading = false, results = emptyList())
            return
        }
        _uiState.value = _uiState.value.copy(loading = true)
        val results = withContext(Dispatchers.IO) { content.search(query, limit = 50) }
        _uiState.value = DictionaryUiState(loading = false, results = results)
    }
}
