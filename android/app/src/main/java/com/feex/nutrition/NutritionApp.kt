package com.feex.nutrition

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.feex.nutrition.foodproductfinder.BarcodeScanScreen
import com.feex.nutrition.ui.HomeScreen

enum class NutritionScreen() {
    Home,
    BarcodeScan,
}

@Composable
fun NutritionApp(
    navController: NavHostController = rememberNavController(),
) {
    NavHost(
        navController = navController,
        startDestination = NutritionScreen.Home.name,
    ) {
        composable(route = NutritionScreen.Home.name) {
            HomeScreen(
                onScanBarcodeButtonClicked = {
                    navController.navigate(NutritionScreen.BarcodeScan.name)
                }
            )
        }
        composable(route = NutritionScreen.BarcodeScan.name) {
            BarcodeScanScreen()
        }
    }
}
