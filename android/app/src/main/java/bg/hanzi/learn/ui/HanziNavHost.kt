package bg.hanzi.learn.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import bg.hanzi.learn.R
import bg.hanzi.learn.data.content.LevelSelection
import bg.hanzi.learn.ui.lesson.LessonScreen
import bg.hanzi.learn.ui.path.PathScreen
import bg.hanzi.learn.ui.screens.dictionary.DictionaryScreen
import bg.hanzi.learn.ui.screens.grammar.GrammarScreen
import bg.hanzi.learn.ui.screens.practice.PracticeScreen
import bg.hanzi.learn.ui.screens.review.ReviewScreen

/**
 * The tabs of the app.
 *
 * The path is the course and the dictionary is the tool. Everything
 * else -- the review session, the five practice modes, the grammar
 * reference -- is reachable from the "More" menu, because a learner
 * who is on the path does not need five icons at the bottom of the
 * screen to find the next word.
 */
private sealed class Tab(
    val route: String,
    val icon: ImageVector,
    val labelRes: Int,
) {
    data object Path : Tab("path", Icons.Filled.Home, R.string.nav_learn)
    data object Dictionary : Tab("dictionary", Icons.Filled.Search, R.string.nav_dict)
}

private val tabs = listOf(
    Tab.Path,
    Tab.Dictionary,
)

/**
 * The routes that take a level argument.
 *
 * The level travels through the navigation as an argument, so a screen
 * knows which HSK levels it is working with. It matters for the review
 * and the practice modes; the learning path carries its own order.
 */
private const val LEVEL_ARG = LevelSelection.ARGUMENT

private fun levelArgument() = navArgument(LEVEL_ARG) {
    type = NavType.StringType
    defaultValue = LevelSelection.DEFAULT
}

private data class MoreItem(
    val labelRes: Int,
    val icon: ImageVector,
    val tag: String,
    val onClick: () -> Unit,
)

private const val LESSON_ROUTE = "lesson"
private const val LESSON_KEY = "lessonKey"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HanziNavHost() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    var moreOpen by remember { mutableStateOf(false) }

    val route = currentDestination?.route?.substringBefore("?")
    val onPath = route == Tab.Path.route
    // The route of the lesson is "lesson/{lessonKey}", so it is
    // matched by its prefix. The bottom bar is hidden inside a
    // lesson: the learner is doing one thing and the tabs would only
    // offer a way out of it.
    val inLesson = route?.startsWith(LESSON_ROUTE) == true

    val moreItems = listOf(
        MoreItem(
            R.string.more_review,
            Icons.Filled.Refresh,
            "more_review",
        ) {
            navController.navigate("review?level=${LevelSelection.DEFAULT}")
        },
        MoreItem(
            R.string.more_practice,
            Icons.Filled.Edit,
            "more_practice",
        ) {
            navController.navigate("practice?level=${LevelSelection.DEFAULT}")
        },
        MoreItem(
            R.string.more_grammar,
            Icons.Filled.List,
            "more_grammar",
        ) {
            navController.navigate("grammar")
        },
    )

    Scaffold(
        topBar = {
            if (onPath) {
                TopAppBar(
                    title = { Text(stringResource(R.string.app_name)) },
                    actions = {
                        IconButton(
                            onClick = { moreOpen = true },
                            modifier = Modifier.testTag("more_menu"),
                        ) {
                            Icon(
                                Icons.Filled.MoreVert,
                                contentDescription = stringResource(R.string.more_menu),
                            )
                        }
                        DropdownMenu(
                            expanded = moreOpen,
                            onDismissRequest = { moreOpen = false },
                        ) {
                            moreItems.forEach { item ->
                                DropdownMenuItem(
                                    text = { Text(stringResource(item.labelRes)) },
                                    onClick = {
                                        moreOpen = false
                                        item.onClick()
                                    },
                                    leadingIcon = {
                                        Icon(item.icon, contentDescription = null)
                                    },
                                    modifier = Modifier.testTag(item.tag),
                                )
                            }
                        }
                    },
                )
            }
        },
        bottomBar = {
            if (!inLesson) {
                NavigationBar {
                    tabs.forEach { tab ->
                        val selected = currentDestination?.hierarchy?.any {
                            it.route?.substringBefore("?") == tab.route
                        } == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = null) },
                            label = { Text(stringResource(tab.labelRes)) },
                            modifier = Modifier.testTag("nav_${tab.route}"),
                        )
                    }
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Tab.Path.route,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(Tab.Path.route) {
                PathScreen(
                    onOpenLesson = { key -> navController.navigate("lesson/$key") },
                    onOpenReview = {
                        navController.navigate("review?level=${LevelSelection.DEFAULT}")
                    },
                )
            }

            composable(
                route = "$LESSON_ROUTE/{$LESSON_KEY}",
                arguments = listOf(navArgument(LESSON_KEY) { type = NavType.StringType }),
            ) { entry ->
                val key = entry.arguments?.getString(LESSON_KEY).orEmpty()
                LessonScreen(
                    lessonKey = key,
                    onFinished = { navController.popBackStack() },
                )
            }

            composable(Tab.Dictionary.route) { DictionaryScreen() }

            composable(
                route = "review?$LEVEL_ARG={$LEVEL_ARG}",
                arguments = listOf(levelArgument()),
            ) { entry ->
                ReviewScreen(level = entry.arguments?.getString(LEVEL_ARG))
            }

            composable(
                route = "practice?$LEVEL_ARG={$LEVEL_ARG}",
                arguments = listOf(levelArgument()),
            ) { entry ->
                PracticeScreen(level = entry.arguments?.getString(LEVEL_ARG))
            }

            composable("grammar") { GrammarScreen() }
        }
    }
}
