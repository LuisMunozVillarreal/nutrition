package com.feex.nutrition.ui.screens.foodproduct

import android.util.Log
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
import androidx.hilt.navigation.compose.hiltViewModel
import com.feex.nutrition.GetFoodProductByBarcodeQuery
import com.feex.nutrition.ui.screens.barcodescanner.BarcodeScannerScreen

@Composable
fun FoodProductScreen(
    foodProductViewModel: FoodProductViewModel
) {
    val foodProductState = foodProductViewModel.foodProductState
    val getBarcode = { foodProductViewModel.getBarcode() }
    val scanAnotherProduct = {
        foodProductViewModel.reset()
    }

    Log.d("NUT FoodProductScreen", foodProductState.javaClass.simpleName)

    when (foodProductState) {
        is FoodProductState.Scanning -> BarcodeScannerScreen(
            onBarcodeFound = { barcodes ->
                foodProductViewModel.barcodeDetected(barcodes)
            }
        )
        is FoodProductState.BarcodeDetected -> BarcodeDetected(
            foodProductState, getBarcode, onBarcodeDetected = {
                val barcode = foodProductViewModel.getBarcode()
                foodProductViewModel.getFoodProduct(barcode)
            }
        )
        is FoodProductState.Fetching -> FetchingScreen(foodProductState, getBarcode)
        is FoodProductState.Fetched -> FoodProductFetchedScreen(
            foodProductState,
            foodProductViewModel.foodProduct,
            addToPantry = {
                foodProductViewModel.addFoodProductToPantry()
            },
            scanAnotherProduct,
        )
        is FoodProductState.NotFound -> CreateFoodProductScreen(getBarcode())
        is FoodProductState.AddProductManually -> CreateFoodProductScreen()
        is FoodProductState.Created -> CreatedScreen()
        is FoodProductState.AddedToPantry -> AddedToPantry(scanAnotherProduct)
        is FoodProductState.Error -> ErrorScreen(
            foodProductState,
            getBarcode,
            scanAnotherProduct,
        )
        is FoodProductState.Exception -> ExceptionScreen(
            foodProductState,
            getBarcode,
            scanAnotherProduct,
        )
    }
}

@Composable
fun BarcodeDetected(
    foodProductState: FoodProductState,
    getBarcode: () -> String,
    onBarcodeDetected: () -> Unit,
) {
    Log.d("NUT BarcodeDetected", foodProductState.javaClass.simpleName)
    Column {
        Text("Barcode detected")
        Text(getBarcode())
    }
    onBarcodeDetected()
}
@Composable
fun FetchingScreen(
    foodProductState: FoodProductState,
    getBarcode: () -> String,
) {
    Log.d("NUT FetchingScreen", foodProductState.javaClass.simpleName)
    Column {
        Text("Fetching...")
        Text(getBarcode())
    }
}

@Composable
fun AddedToPantry(
    scanAnotherProduct: () -> Unit,
) {
    Column {
        Text("Added to pantry!")
        Text("You have 3 'Ocado Chicken Breask' in your pantry")
        Button(onClick={ scanAnotherProduct() }) {
            Text("Scan another product")
        }
    }
}

@Composable
fun CreatedScreen() {
    Text("Created")
}

@Composable
fun ErrorScreen(
    foodProductState: FoodProductState,
    getBarcode: () -> kotlin.String,
    scanAnotherProduct: () -> Unit,
) {
    Column {
        Text("Error")
        Text(getBarcode())
        Text(foodProductState.toString())
        Button(onClick={ scanAnotherProduct() }) {
            Text("Scan another product")
        }
    }
}

@Composable
fun ExceptionScreen(
    foodProductState: FoodProductState,
    getBarcode: () -> kotlin.String,
    scanAnotherProduct: () -> Unit,
) {
    Column {
        Text("Exception")
        Text(getBarcode())
        Text(foodProductState.toString())
        Button(onClick={ scanAnotherProduct() }) {
            Text("Scan another product")
        }
    }
}
