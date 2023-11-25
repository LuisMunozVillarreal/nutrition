package com.feex.nutrition.ui.screens.foodproduct

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import com.feex.nutrition.ui.theme.NutritionTheme

@Composable
fun CreateFoodProductScreen(barcode: String = "") {
    val isBarcodeChangeable = barcode.isEmpty()
    var barcode by rememberSaveable { mutableStateOf(barcode) }
    var brand by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var weight by rememberSaveable { mutableStateOf("") }

    CreateFoodProductContent(
        barcode = barcode,
        isBarcodeChangeable = isBarcodeChangeable,
        onBarcodeChange = { barcode = it },
        brand = brand,
        onBrandChange = { brand = it },
        name = name,
        onNameChange = { name = it },
        weight = weight,
        onWeightChange = { weight = it },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateFoodProductContent(
    barcode: String = "",
    onBarcodeChange: (String) -> Unit = {},
    isBarcodeChangeable: Boolean = false,
    brand: String = "",
    onBrandChange: (String) -> Unit = {},
    name: String = "",
    onNameChange: (String) -> Unit = {},
    weight: String = "",
    onWeightChange: (String) -> Unit = {},
//    numServings: Float,
//    onNumServingsChange: (Float) -> Unit,
//    energy: Float,
//    onEnergyChange: (Float) -> Unit,
//    : Float,
//    : (Float) -> Unit,
//    : Float,
//    : (Float) -> Unit,
//    : Float,
//    : (Float) -> Unit,
//    : Float,
//    : (Float) -> Unit,
//    : Float,
//    : (Float) -> Unit,
    ) {
    Column {
        if (isBarcodeChangeable) {
            OutlinedTextField(
                value = barcode,
                onValueChange = onBarcodeChange,
                label = { Text("Barcode") }
                )
        }
        else {
            Text("Barcode: $barcode")
        }
        OutlinedTextField(
            value = brand,
            onValueChange = onBrandChange,
            label = { Text("Brand" ) }
        )
        OutlinedTextField(
            value = name,
            onValueChange = onNameChange,
            label = { Text("Name" ) }
        )
        OutlinedTextField(
            value = weight,
            onValueChange = onWeightChange,
            label = { Text("Weight" ) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
//        OutlinedTextField(
//            value = numServings,
//            onValueChange = onNumSercingsChange,
//            label = { Text("Number of servings" ) }
//        )
//        OutlinedTextField(
//            value = energy,
//            onValueChange = onEnergyChange,
//            label = { Text("Energy" ) }
//        )
//        OutlinedTextField(
//            value = carbs,
//            onValueChange = onCarbsChange,
//            label = { Text("Carbohydrates" ) }
//        )
//        OutlinedTextField(
//            value = fat,
//            onValueChange = onFatChange,
//            label = { Text("Fat" )}
//        )
//        OutlinedTextField(
//            value = protein,
//            onValueChange = onProteinChange,
//            label = { Text("Protein" )}
//        )
    }
}

@Preview(showBackground = true)
@Composable
fun CreateFoodProductScreenPreview() {
    NutritionTheme {
        CreateFoodProductScreen("1234567890")
    }
}
