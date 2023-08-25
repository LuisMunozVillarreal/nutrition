package com.feex.nutrition.ui.screens.foodproduct

import android.util.Log
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import com.feex.nutrition.GetFoodProductByBarcodeQuery

@Composable
fun FoodProductFetchedScreen(
    foodProductState: FoodProductState,
    foodProduct: GetFoodProductByBarcodeQuery.GetFoodProductByBarcode?,
    addToPantry: () -> Unit,
    scanAnotherProduct: () -> Unit,
) {
    Log.d("NUT FetchedScreen", foodProductState.javaClass.simpleName)
    Column {
        Text("Fetched")
        Text("Barcode: " + foodProduct?.barcode)
        Text("Brand: " + foodProduct?.brand)
        Text("Name: " + foodProduct?.name)
        Text("Energy: " + foodProduct?.energy)
        Text("Carbs: " + foodProduct?.carbsG)
        Text("Fat: " + foodProduct?.fatG)
        Text("Protein: " + foodProduct?.proteinG)
        Text("Weight: " + foodProduct?.weight)
        Text("Num Servings: " + foodProduct?.numServings)
        Row {
            Button(onClick={ addToPantry() }) {
                Text("Add to your pantry")
            }
            Button(onClick={ scanAnotherProduct() }) {
                Text("Scan another product")
            }
        }
    }
}
