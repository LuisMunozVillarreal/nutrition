package com.feex.nutrition.ui.screens.barcodescanner

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.feex.nutrition.data.BarcodeRepository
import com.google.mlkit.vision.barcode.common.Barcode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface BarcodeScannerState {
    object Scanning : BarcodeScannerState
    object Found : BarcodeScannerState
}

@HiltViewModel
class BarcodeScannerViewModel @Inject constructor(
    private val barcodeRepository: BarcodeRepository
) : ViewModel() {
    var barcodeScannerState: BarcodeScannerState by mutableStateOf(BarcodeScannerState.Scanning)
        private set

    fun found(barcodes: MutableList<Barcode>) {
        viewModelScope.launch {
            barcodeScannerState = BarcodeScannerState.Found
        }
        barcodeRepository.addDetectedBarcodes(barcodes)
    }
}
