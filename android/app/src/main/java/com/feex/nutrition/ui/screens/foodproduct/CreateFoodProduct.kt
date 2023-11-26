package com.feex.nutrition.ui.screens.foodproduct

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
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
fun CreateFoodProductScreen(
    barcode: String = "",
    createFoodProduct: (String, String, String, String, String, String, String, String, String) -> Unit,
) {
    val isBarcodeChangeable = barcode.isEmpty()
    var barcode by rememberSaveable { mutableStateOf(barcode) }
    var brand by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var weight by rememberSaveable { mutableStateOf("") }
    var numServings by rememberSaveable { mutableStateOf("") }
    var energy by rememberSaveable { mutableStateOf("") }
    var carbs by rememberSaveable { mutableStateOf("") }
    var fat by rememberSaveable { mutableStateOf("") }
    var protein by rememberSaveable { mutableStateOf("") }

    // TODO: Validate form input for numbers
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
        numServings = numServings,
        onNumServingsChange = { numServings = it },
        energy = energy,
        onEnergyChange = { energy = it },
        carbs = carbs,
        onCarbsChange = { carbs = it },
        fat = fat,
        onFatChange = { fat = it },
        protein = protein,
        onProteinChange = { protein = it },
        onCreateFoodProductButtonClicked = {
            createFoodProduct(barcode, brand, name, weight, numServings, energy, carbs, fat, protein)
        }
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
    numServings: String = "",
    onNumServingsChange: (String) -> Unit = {},
    energy: String = "",
    onEnergyChange: (String) -> Unit = {},
    carbs: String = "",
    onCarbsChange: (String) -> Unit = {},
    fat: String = "",
    onFatChange: (String) -> Unit = {},
    protein: String = "",
    onProteinChange: (String) -> Unit = {},
    onCreateFoodProductButtonClicked: () -> Unit = {},
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
        OutlinedTextField(
            value = numServings,
            onValueChange = onNumServingsChange,
            label = { Text("Number of servings" ) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        OutlinedTextField(
            value = energy,
            onValueChange = onEnergyChange,
            label = { Text("Energy" ) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        OutlinedTextField(
            value = carbs,
            onValueChange = onCarbsChange,
            label = { Text("Carbohydrates" ) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        OutlinedTextField(
            value = fat,
            onValueChange = onFatChange,
            label = { Text("Fat" )},
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        OutlinedTextField(
            value = protein,
            onValueChange = onProteinChange,
            label = { Text("Protein" )},
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
        )
        Button(onClick={ onCreateFoodProductButtonClicked() }) {
            Text("Create Food Product")
        }
    }
}

@Preview(showBackground = true)
@Composable
fun CreateFoodProductContentPreview() {
    NutritionTheme {
        CreateFoodProductContent("1234567890")
    }
}
