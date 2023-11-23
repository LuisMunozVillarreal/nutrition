package com.feex.nutrition.data

import android.util.Log
import com.google.mlkit.vision.barcode.common.Barcode
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BarcodeRepository @Inject constructor() {
    private val barcodes = mutableListOf<Barcode>()

    fun getBarcode(): String {
        Log.d(TAG, "getBarcode")
        return barcodes.first().rawValue ?: ""
    }

    fun addDetectedBarcodes(detectedBarcodes: MutableList<Barcode>) {
        Log.d(TAG, "addDetectedBarcodes")
        barcodes.clear()
        barcodes.addAll(detectedBarcodes)
    }

    companion object {
        private const val TAG: String = "NUT BarcodeRepository"
    }
}
