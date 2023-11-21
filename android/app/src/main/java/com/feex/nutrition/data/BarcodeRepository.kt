package com.feex.nutrition.data

import com.google.mlkit.vision.barcode.common.Barcode
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BarcodeRepository @Inject constructor() {
    private val barcodes = mutableListOf<Barcode>()

    fun getBarcode(): String {
        return barcodes.first().rawValue ?: ""
    }

    fun addDetectedBarcodes(detectedBarcodes: MutableList<Barcode>) {
        barcodes.clear()
        barcodes.addAll(detectedBarcodes)
    }
}
