package com.feex.nutrition.ui.screens.foodproduct

import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.material3.Text
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun FoodProductScreen(
    foodProductViewModel: FoodProductViewModel = hiltViewModel(),
) {
    when (foodProductViewModel.foodProductState) {
        is FoodProductState.Fetching -> FetchingScreen(foodProductViewModel)
        is FoodProductState.Fetched -> FetchedScreen(foodProductViewModel)
        is FoodProductState.NotFound -> NotFoundScreen()
        is FoodProductState.Creating -> CreatingScreen()
        is FoodProductState.Created -> CreatedScreen()
        is FoodProductState.Error -> ErrorScreen()
    }
}

@Composable
fun FetchingScreen(foodProductViewModel: FoodProductViewModel) {
    Text("Fetching...")
    val barcode: String = foodProductViewModel.barcodeRepository.getBarcode()
    Text(barcode)
    foodProductViewModel.getOrCreateFoodProduct(barcode)
}

@Composable
fun FetchedScreen(foodProductViewModel: FoodProductViewModel) {
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
