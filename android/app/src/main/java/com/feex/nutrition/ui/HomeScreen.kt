package com.feex.nutrition.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.tooling.preview.Preview


@Composable
fun HomeScreen(
    onScanBarcodeButtonClicked: () -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Button(onClick = onScanBarcodeButtonClicked) {
            Text("Scan Barcode")
        }
    }
}

@Preview
@Composable
fun HomeScreenPreview() {
    HomeScreen(
        onScanBarcodeButtonClicked = {},
    )
}
