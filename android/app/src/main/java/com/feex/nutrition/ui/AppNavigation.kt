package com.feex.nutrition.ui

import android.util.Log
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.feex.nutrition.ui.screens.HomeScreen
import com.feex.nutrition.ui.screens.foodproduct.FoodProductScreen
import androidx.hilt.navigation.compose.hiltViewModel
import com.feex.nutrition.ui.screens.foodproduct.FoodProductViewModel


enum class NutritionScreen {
    Home,
    FoodProduct,
}

@Composable
fun AppNavigation() {
    val navController: NavHostController = rememberNavController()
    val foodProductViewModel: FoodProductViewModel = hiltViewModel()

    NavHost(
        navController = navController,
        startDestination = NutritionScreen.Home.name,
    ) {
        composable(route = NutritionScreen.Home.name) {
            Log.d("NUT AppNavigation", "HomeScreen")
            HomeScreen(
                onScanBarcodeButtonClicked = {
                    navController.navigate(NutritionScreen.FoodProduct.name)
                },
                onCreateProductButtonClicked =  {
                    foodProductViewModel.addFoodProductManually()
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