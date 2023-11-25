package com.feex.nutrition.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.tooling.preview.Preview


@Composable
fun HomeScreen(
    onScanBarcodeButtonClicked: () -> Unit,
    onCreateProductButtonClicked: () -> Unit,
) {
    Row {
        Button(onClick = onScanBarcodeButtonClicked) {
            Text("Scan Barcode")
        }
        Button(onClick = onCreateProductButtonClicked) {
            Text("Add product manually")
        }
    }
}
