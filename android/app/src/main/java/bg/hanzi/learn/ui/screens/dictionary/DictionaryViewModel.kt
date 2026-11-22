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
    /**
     * True when the learner has typed nothing and the list is the
     * browse list rather than the result of a search.
     */
    val browsing: Boolean = true,
    /**
     * True when there are more words to show. The dictionary holds ten
     * thousand entries, so a search that matches three thousand of them
     * has to say so instead of quietly showing the first fifty.
     */
    val hasMore: Boolean = false,
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

    /**
     * How many words are shown.
     *
     * The dictionary holds ten thousand entries, so the list is paged:
     * the learner asks for more and the page grows. The first page is
     * small enough to be readable and large enough to be useful.
     */
    private var pageSize = PAGE_SIZE

    init {
        queries
            .debounce(250)
            .distinctUntilChanged()
            .onEach { q -> runSearch(q) }
            .launchIn(viewModelScope)
        // The browse list: the commonest words, so the dictionary shows
        // something before the learner has typed anything.
        viewModelScope.launch { runSearch("") }
    }

    fun search(query: String) {
        pageSize = PAGE_SIZE
        queries.value = query
    }

    /**
     * Shows or hides the words whose Bulgarian gloss came from a machine.
     */
    fun setHumanGlossesOnly(enabled: Boolean) {
        humanGlossesOnly = enabled
        val q = queries.value
        viewModelScope.launch { runSearch(q) }
    }

    /**
     * Shows the next page of the list.
     *
     * The page grows instead of being replaced, so the learner keeps
     * what they have already read.
     */
    fun loadMore() {
        pageSize += PAGE_SIZE
        val q = queries.value
        viewModelScope.launch { runSearch(q) }
    }

    private suspend fun runSearch(query: String) {
        if (query.isBlank()) {
            // Nothing was typed: the dictionary shows what it has.
            val words = withContext(Dispatchers.IO) {
                content.browseWords(limit = pageSize + 1)
            }
            val more = words.size > pageSize
            _uiState.value = DictionaryUiState(
                loading = false,
                results = words.take(pageSize),
                humanGlossesOnly = humanGlossesOnly,
                browsing = true,
                hasMore = more,
            )
            return
        }
        _uiState.value = _uiState.value.copy(loading = true)
        // One more than the page size, so the state knows whether there
        // is a next page without a second query.
        val results = withContext(Dispatchers.IO) {
            content.search(
                query = query,
                limit = pageSize + 1,
                humanGlossesOnly = humanGlossesOnly,
            )
        }
        val more = results.size > pageSize
        _uiState.value = DictionaryUiState(
            loading = false,
            results = results.take(pageSize),
            humanGlossesOnly = humanGlossesOnly,
            browsing = false,
            hasMore = more,
        )
    }

    private companion object {
        /** How many words one page of the dictionary holds. */
        const val PAGE_SIZE = 50
    }
}
