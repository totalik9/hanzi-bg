package bg.hanzi.learn.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.List
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
import bg.hanzi.learn.ui.screens.dictionary.DictionaryScreen
import bg.hanzi.learn.ui.screens.grammar.GrammarScreen
import bg.hanzi.learn.ui.screens.home.HomeScreen
import bg.hanzi.learn.ui.screens.practice.PracticeScreen
import bg.hanzi.learn.ui.screens.review.ReviewScreen

private sealed class Destination(
    val route: String,
    val icon: ImageVector,
    val labelRes: Int,
) {
    data object Home : Destination("home", Icons.Filled.Home, R.string.nav_learn)
    data object Review : Destination("review", Icons.Filled.Refresh, R.string.nav_review)
    data object Practice : Destination("practice", Icons.Filled.Edit, R.string.nav_practice)
    data object Dictionary : Destination("dictionary", Icons.Filled.Search, R.string.nav_dict)
    data object Grammar : Destination("grammar", Icons.Filled.List, R.string.nav_grammar)
}

private val bottomDestinations = listOf(
    Destination.Home,
    Destination.Review,
    Destination.Practice,
    Destination.Dictionary,
    Destination.Grammar,
)

/**
 * The routes that take a level argument.
 *
 * The level travels through the navigation as an argument, so a screen
 * knows which HSK levels it is working with. Without it the practice
 * pool was fixed to levels 1-2 and the other 10 399 words in the
 * database could not be reached from anywhere in the app.
 *
 * The argument is declared optional with a default, so the bottom
 * navigation bar can still navigate to "practice" and "review" without
 * naming a level.
 */
private const val LEVEL_ARG = LevelSelection.ARGUMENT

private fun levelArgument() = navArgument(LEVEL_ARG) {
    type = NavType.StringType
    defaultValue = LevelSelection.DEFAULT
}

@Composable
fun HanziNavHost() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination

    Scaffold(
        bottomBar = {
            NavigationBar {
                bottomDestinations.forEach { destination ->
                    // The route of a destination with arguments carries
                    // them ("practice?level={level}"), so the comparison
                    // is made on the part before the question mark.
                    val selected = currentDestination?.hierarchy?.any {
                        it.route?.substringBefore("?") == destination.route
                    } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            navController.navigate(destination.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(destination.icon, contentDescription = null) },
                        label = { Text(stringResource(destination.labelRes)) },
                        // The tag lets the instrumented tests pick this
                        // item out of the screen: the word "Упражнения"
                        // also appears on the Home screen, on the button
                        // of every level card.
                        modifier = Modifier.testTag("nav_${destination.route}"),
                    )
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Destination.Home.route,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(Destination.Home.route) { HomeScreen(navController) }

            composable(
                route = "${Destination.Review.route}?$LEVEL_ARG={$LEVEL_ARG}",
                arguments = listOf(levelArgument()),
            ) { entry ->
                ReviewScreen(level = entry.arguments?.getString(LEVEL_ARG))
            }

            composable(
                route = "${Destination.Practice.route}?$LEVEL_ARG={$LEVEL_ARG}",
                arguments = listOf(levelArgument()),
            ) { entry ->
                PracticeScreen(level = entry.arguments?.getString(LEVEL_ARG))
            }

            composable(Destination.Dictionary.route) { DictionaryScreen() }
            composable(Destination.Grammar.route) { GrammarScreen() }
        }
    }
}
