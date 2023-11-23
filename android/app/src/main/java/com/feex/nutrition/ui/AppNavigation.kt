package com.feex.nutrition.ui

import android.util.Log
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.feex.nutrition.ui.screens.HomeScreen
import com.feex.nutrition.ui.screens.barcodescanner.BarcodeScannerScreen
import com.feex.nutrition.ui.screens.foodproduct.FoodProductScreen
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import com.feex.nutrition.ui.screens.barcodescanner.BarcodeScannerViewModel
import com.feex.nutrition.ui.screens.foodproduct.FoodProductViewModel


enum class NutritionScreen {
    Home,
    BarcodeScan,
    FoodProduct,
}

@Composable
fun AppNavigation() {
    val navController: NavHostController = rememberNavController()
    val foodProductViewModel: FoodProductViewModel = hiltViewModel()
    val barcodeScannerViewModel: BarcodeScannerViewModel = hiltViewModel()

    NavHost(
        navController = navController,
        startDestination = NutritionScreen.Home.name,
    ) {
        composable(route = NutritionScreen.Home.name) {
            Log.d("NUT AppNavigation", "HomeScreen")
            HomeScreen(
                onScanBarcodeButtonClicked = {
                    navController.navigate(NutritionScreen.BarcodeScan.name)
                }
            )
        }
        composable(route = NutritionScreen.BarcodeScan.name) {
            Log.d("NUT AppNavigation", "BarcodeScannerScreen")
            BarcodeScannerScreen(
                barcodeScannerViewModel,
                onBarcodeFound = {
                    navController.navigate(NutritionScreen.FoodProduct.name)
                }
            )
        }
        composable(route = NutritionScreen.FoodProduct.name) {
            Log.d("NUT AppNavigation", "FoodProductScreen")
            FoodProductScreen(foodProductViewModel)
        }
    }
}