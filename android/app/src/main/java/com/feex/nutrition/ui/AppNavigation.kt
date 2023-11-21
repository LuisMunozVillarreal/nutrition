package com.feex.nutrition.ui

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.feex.nutrition.ui.screens.HomeScreen
import com.feex.nutrition.ui.screens.barcodescanner.BarcodeScannerScreen
import com.feex.nutrition.ui.screens.foodproduct.FoodProductScreen

enum class NutritionScreen {
    Home,
    BarcodeScan,
    FoodProduct,
}

@Composable
fun AppNavigation(
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
            BarcodeScannerScreen(
                onBarcodeFound = {
                    navController.navigate(NutritionScreen.FoodProduct.name)
                }
            )
        }
        composable(route = NutritionScreen.FoodProduct.name) {
            FoodProductScreen()
        }
    }
}