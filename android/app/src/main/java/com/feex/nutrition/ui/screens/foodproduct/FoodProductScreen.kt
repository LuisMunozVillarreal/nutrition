package com.feex.nutrition.ui.screens.foodproduct

import android.util.Log
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun FoodProductScreen(
    foodProductViewModel: FoodProductViewModel,
) {
    Log.d("NUT FoodProductScreen", foodProductViewModel.foodProductState.javaClass.simpleName)
    when (foodProductViewModel.foodProductState) {
        is FoodProductState.Idle -> BarcodeDetected(foodProductViewModel)
        is FoodProductState.Fetching -> FetchingScreen(foodProductViewModel)
        is FoodProductState.Fetched -> FetchedScreen(foodProductViewModel)
        is FoodProductState.NotFound -> NotFoundScreen()
        is FoodProductState.Creating -> CreatingScreen()
        is FoodProductState.Created -> CreatedScreen()
        is FoodProductState.Error -> ErrorScreen()
    }
}

@Composable
fun BarcodeDetected(foodProductViewModel: FoodProductViewModel) {
    Log.d("NUT BarcodeDetected", foodProductViewModel.foodProductState.javaClass.simpleName)
    val barcode: String = foodProductViewModel.barcodeRepository.getBarcode()
    Column {
        Text("Barcode detected")
        Text(barcode)
    }
    foodProductViewModel.getOrCreateFoodProduct(barcode)
}
@Composable
fun FetchingScreen(foodProductViewModel: FoodProductViewModel) {
    Log.d("NUT FetchingScreen", foodProductViewModel.foodProductState.javaClass.simpleName)
    val barcode: String = foodProductViewModel.barcodeRepository.getBarcode()
    Column {
        Text("Fetching...")
        Text(barcode)
    }
}

@Composable
fun FetchedScreen(foodProductViewModel: FoodProductViewModel) {
    Log.d("NUT FetchedScreen", foodProductViewModel.foodProductState.javaClass.simpleName)
    Column {
        Text("Fetched")
        Text("Brand: " + foodProductViewModel.foodProduct?.brand)
        Text("Name: " + foodProductViewModel.foodProduct?.name)
        Text("Energy: " + foodProductViewModel.foodProduct?.energy)
        Text("Carbs: " + foodProductViewModel.foodProduct?.carbsG)
        Text("Fat: " + foodProductViewModel.foodProduct?.fatG)
    }
}

@Composable
fun NotFoundScreen() {
    Text("Not found")
}

@Composable
fun CreatingScreen() {
    Text("Creating...")
}

@Composable
fun CreatedScreen() {
    Text("Created")
}

@Composable
fun ErrorScreen() {
    Text("Error")
}
