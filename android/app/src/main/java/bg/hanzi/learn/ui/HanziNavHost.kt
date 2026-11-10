package bg.hanzi.learn.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
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
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import bg.hanzi.learn.R
import bg.hanzi.learn.ui.screens.dictionary.DictionaryScreen
import bg.hanzi.learn.ui.screens.grammar.GrammarScreen
import bg.hanzi.learn.ui.screens.home.HomeScreen
import bg.hanzi.learn.ui.screens.review.ReviewScreen

private sealed class Destination(
    val route: String,
    val icon: ImageVector,
    val labelRes: Int,
) {
    data object Home : Destination("home", Icons.Filled.Home, R.string.nav_learn)
    data object Review : Destination("review", Icons.Filled.Refresh, R.string.nav_review)
    data object Dictionary : Destination("dictionary", Icons.Filled.Search, R.string.nav_dict)
    data object Grammar : Destination("grammar", Icons.Filled.List, R.string.nav_grammar)
}

private val bottomDestinations = listOf(
    Destination.Home,
    Destination.Review,
    Destination.Dictionary,
    Destination.Grammar,
)

@Composable
fun HanziNavHost() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination

    Scaffold(
        bottomBar = {
            NavigationBar {
                bottomDestinations.forEach { destination ->
                    val selected = currentDestination?.hierarchy?.any {
                        it.route == destination.route
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
            composable(Destination.Review.route) { ReviewScreen() }
            composable(Destination.Dictionary.route) { DictionaryScreen() }
            composable(Destination.Grammar.route) { GrammarScreen() }
        }
    }
}
