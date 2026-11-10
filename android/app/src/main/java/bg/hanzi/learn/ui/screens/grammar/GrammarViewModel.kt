package bg.hanzi.learn.ui.screens.grammar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import bg.hanzi.learn.data.content.ContentRepository
import bg.hanzi.learn.data.content.GrammarEntry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

data class GrammarUiState(
    val loading: Boolean = true,
    val entries: List<GrammarEntry> = emptyList(),
)

@HiltViewModel
class GrammarViewModel @Inject constructor(
    private val content: ContentRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(GrammarUiState())
    val uiState: StateFlow<GrammarUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            val entries = withContext(Dispatchers.IO) { content.grammar() }
            _uiState.value = GrammarUiState(loading = false, entries = entries)
        }
    }
}
