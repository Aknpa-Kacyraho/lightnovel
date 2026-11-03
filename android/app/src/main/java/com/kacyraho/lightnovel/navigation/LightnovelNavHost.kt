package com.kacyraho.lightnovel.navigation

import android.net.Uri
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.SaveableStateHolder
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.R
import com.kacyraho.lightnovel.feature.catalog.CatalogRoute
import com.kacyraho.lightnovel.feature.chapters.ChapterListRoute
import com.kacyraho.lightnovel.feature.discover.DiscoverRoute
import com.kacyraho.lightnovel.feature.library.LibraryRoute
import com.kacyraho.lightnovel.feature.memory.StoryMemoryRoute
import com.kacyraho.lightnovel.feature.worldline.WorldlineRoute
import com.kacyraho.lightnovel.feature.reader.ReaderRoute
import com.kacyraho.lightnovel.feature.settings.SettingsRoute
import com.kacyraho.lightnovel.feature.tasks.TaskCenterRoute

private data class TopLevelDestination(
    val route: String,
    val label: String,
    val icon: Int,
)

private val topLevelDestinations = listOf(
    TopLevelDestination("library", "书架", R.drawable.ic_nav_library),
    TopLevelDestination("discover", "发现", R.drawable.ic_nav_discover),
    TopLevelDestination("tasks", "任务", R.drawable.ic_nav_tasks),
    TopLevelDestination("settings", "设置", R.drawable.ic_nav_settings),
)

@Composable
fun LightnovelNavHost(container: AppContainer) {
    val libraryNav = rememberNavController()
    val discoverNav = rememberNavController()
    val tasksNav = rememberNavController()
    val settingsNav = rememberNavController()
    var selectedTab by rememberSaveable { mutableStateOf("library") }
    var pendingDiscoverRoute by rememberSaveable { mutableStateOf<String?>(null) }
    val stateHolder = rememberSaveableStateHolder()
    val activeNav = when (selectedTab) {
        "discover" -> discoverNav
        "tasks" -> tasksNav
        "settings" -> settingsNav
        else -> libraryNav
    }
    val activeEntry by activeNav.currentBackStackEntryAsState()
    val activeRoute = activeEntry?.destination?.route
    val showBottomBar = activeRoute?.startsWith("reader/") != true

    fun switchTab(tab: String) {
        if (selectedTab == tab) {
            val root = when (tab) {
                "discover" -> "discover"
                "tasks" -> "tasks"
                "settings" -> "settings"
                else -> "library"
            }
            activeNav.popBackStack(root, inclusive = false)
        } else {
            selectedTab = tab
        }
    }

    fun openDiscover(route: String) {
        if (selectedTab == "discover") {
            discoverNav.navigate(route) { launchSingleTop = true }
        } else {
            pendingDiscoverRoute = route
            selectedTab = "discover"
        }
    }

    LaunchedEffect(selectedTab, pendingDiscoverRoute) {
        val pending = pendingDiscoverRoute ?: return@LaunchedEffect
        if (selectedTab == "discover") {
            discoverNav.navigate(pending) { launchSingleTop = true }
            pendingDiscoverRoute = null
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.surfaceContainer,
                    tonalElevation = 0.dp,
                ) {
                    topLevelDestinations.forEach { destination ->
                        NavigationBarItem(
                            selected = selectedTab == destination.route,
                            onClick = { switchTab(destination.route) },
                            icon = {
                                Icon(
                                    painter = painterResource(destination.icon),
                                    contentDescription = destination.label,
                                )
                            },
                            label = { Text(destination.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = MaterialTheme.colorScheme.primary,
                                selectedTextColor = MaterialTheme.colorScheme.primary,
                                indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                                unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                                unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            ),
                        )
                    }
                }
            }
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabHost(selectedTab == "library", stateHolder, "tab-library") {
                NavHost(libraryNav, startDestination = "library") {
                    composable("library") {
                        LibraryRoute(
                            container = container,
                            onOpenBook = { bookId ->
                                libraryNav.navigate("chapters/$bookId?from=library")
                            },
                            onContinue = { bookId, idx ->
                                libraryNav.navigate("reader/$bookId/$idx")
                            },
                            onDiscover = { switchTab("discover") },
                            onOpenSettings = { switchTab("settings") },
                        )
                    }
                    bookRoutes(
                        nav = libraryNav,
                        container = container,
                        onDiscoverSearch = ::openDiscover,
                    )
                }
            }

            TabHost(selectedTab == "discover", stateHolder, "tab-discover") {
                NavHost(discoverNav, startDestination = "discover") {
                    composable("discover") {
                        DiscoverRoute(
                            container = container,
                            onOpenBook = { bookId ->
                                discoverNav.navigate("chapters/$bookId?from=discover")
                            },
                            onOpenCatalog = { discoverNav.navigate("catalog") },
                        )
                    }
                    composable("catalog") {
                        CatalogRoute(
                            container = container,
                            onBack = { discoverNav.popBackStack() },
                        )
                    }
                    composable(
                        route = "discover?q={q}&mode={mode}",
                        arguments = listOf(
                            navArgument("q") {
                                type = NavType.StringType
                                nullable = true
                                defaultValue = null
                            },
                            navArgument("mode") {
                                type = NavType.StringType
                                nullable = true
                                defaultValue = null
                            },
                        ),
                    ) { entry ->
                        DiscoverRoute(
                            container = container,
                            initialQuery = entry.arguments?.getString("q"),
                            initialMode = entry.arguments?.getString("mode"),
                            onBack = { discoverNav.popBackStack() },
                            onOpenBook = { bookId ->
                                discoverNav.navigate("chapters/$bookId?from=discover")
                            },
                            onOpenCatalog = { discoverNav.navigate("catalog") },
                        )
                    }
                    bookRoutes(
                        nav = discoverNav,
                        container = container,
                        onDiscoverSearch = ::openDiscover,
                    )
                }
            }

            TabHost(selectedTab == "tasks", stateHolder, "tab-tasks") {
                NavHost(tasksNav, startDestination = "tasks") {
                    composable("tasks") {
                        TaskCenterRoute(
                            container = container,
                            onOpenChapter = { bookId, idx ->
                                tasksNav.navigate("reader/$bookId/$idx")
                            },
                            onRetryChapter = { bookId, idx ->
                                tasksNav.navigate("reader/$bookId/$idx?retry=true")
                            },
                        )
                    }
                    bookRoutes(
                        nav = tasksNav,
                        container = container,
                        onDiscoverSearch = ::openDiscover,
                    )
                }
            }

            TabHost(selectedTab == "settings", stateHolder, "tab-settings") {
                NavHost(settingsNav, startDestination = "settings") {
                    composable("settings") {
                        SettingsRoute(container = container)
                    }
                }
            }
        }
    }
}

@Composable
private fun TabHost(
    visible: Boolean,
    stateHolder: SaveableStateHolder,
    key: String,
    content: @Composable () -> Unit,
) {
    if (visible) {
        stateHolder.SaveableStateProvider(key) { content() }
    }
}

private fun NavGraphBuilder.bookRoutes(
    nav: NavHostController,
    container: AppContainer,
    onDiscoverSearch: (String) -> Unit,
) {
    composable(
        route = "chapters/{bookId}?from={from}",
        arguments = listOf(
            navArgument("bookId") { type = NavType.StringType },
            navArgument("from") {
                type = NavType.StringType
                defaultValue = "library"
            },
        ),
    ) { entry ->
        val bookId = entry.arguments?.getString("bookId") ?: return@composable
        ChapterListRoute(
            container = container,
            bookId = bookId,
            onBack = { nav.popBackStack() },
            onOpenChapter = { idx ->
                nav.navigate("reader/$bookId/$idx")
            },
            onSearchAuthor = { author ->
                onDiscoverSearch("discover?q=${Uri.encode(author)}&mode=author")
            },
            onSearchTag = { tag ->
                onDiscoverSearch("discover?q=${Uri.encode(tag)}&mode=tag")
            },
            onOpenMemory = { nav.navigate("memory/$bookId") },
            onOpenWorldlines = { nav.navigate("worldlines/$bookId") },
        )
    }
    composable(
        route = "memory/{bookId}",
        arguments = listOf(navArgument("bookId") { type = NavType.StringType }),
    ) { entry ->
        val bookId = entry.arguments?.getString("bookId") ?: return@composable
        StoryMemoryRoute(
            container = container,
            bookId = bookId,
            onBack = { nav.popBackStack() },
        )
    }
    composable(
        route = "worldlines/{bookId}",
        arguments = listOf(navArgument("bookId") { type = NavType.StringType }),
    ) { entry ->
        val bookId = entry.arguments?.getString("bookId") ?: return@composable
        WorldlineRoute(
            container = container,
            bookId = bookId,
            onBack = { nav.popBackStack() },
        )
    }
    readerRoute(nav, container)
}

private fun NavGraphBuilder.readerRoute(
    nav: NavHostController,
    container: AppContainer,
) {
    composable(
        route = "reader/{bookId}/{idx}?retry={retry}",
        arguments = listOf(
            navArgument("bookId") { type = NavType.StringType },
            navArgument("idx") { type = NavType.IntType },
            navArgument("retry") {
                type = NavType.BoolType
                defaultValue = false
            },
        ),
    ) { entry ->
        val bookId = entry.arguments?.getString("bookId") ?: return@composable
        val idx = entry.arguments?.getInt("idx") ?: return@composable
        val retry = entry.arguments?.getBoolean("retry") ?: false
        ReaderRoute(
            container = container,
            bookId = bookId,
            chapterIndex = idx,
            autoRetry = retry,
            onBack = { nav.popBackStack() },
            onOpenCatalog = {
                val previous = nav.previousBackStackEntry?.destination?.route
                if (previous?.startsWith("chapters/") == true) {
                    nav.popBackStack()
                } else {
                    nav.navigate("chapters/$bookId?from=library") {
                        launchSingleTop = true
                    }
                }
            },
            onOpenMemory = { nav.navigate("memory/$bookId") },
            onOpenWorldlines = { nav.navigate("worldlines/$bookId") },
            onOpenChapter = { next ->
                nav.navigate("reader/$bookId/$next") {
                    popUpTo(entry.destination.id) { inclusive = true }
                    launchSingleTop = true
                }
            },
        )
    }
}
