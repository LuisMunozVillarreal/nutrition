package com.feex.nutrition.data

import android.util.Log
import com.apollographql.apollo3.ApolloClient
import com.apollographql.apollo3.api.ApolloResponse
import com.feex.nutrition.CreateFoodProductMutation
import com.feex.nutrition.GetFoodProductByBarcodeQuery
import com.google.mlkit.vision.barcode.common.Barcode
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FoodProductRepository @Inject constructor(){
    private val apolloClient = ApolloClient.Builder().serverUrl("http://192.168.0.2:8000/graphql").build()
    private val barcodes = mutableListOf<Barcode>()

    fun reset() {
        barcodes.clear()
    }

    fun getBarcode(): String {
        Log.d(TAG, "getBarcode")
        return barcodes.firstOrNull()?.rawValue ?: ""
    }

    fun addDetectedBarcodes(detectedBarcodes: MutableList<Barcode>) {
        Log.d(TAG, "addDetectedBarcodes")
        barcodes.clear()
        barcodes.addAll(detectedBarcodes)
    }

    suspend fun getFoodProductByBarcode(barcode: String): ApolloResponse<GetFoodProductByBarcodeQuery.Data> {
        return apolloClient.query(GetFoodProductByBarcodeQuery(barcode = barcode)).execute()
    }

    suspend fun createFoodProduct(
        barcode: String,
        brand: String,
        name: String,
        weight: String,
        numServings: String,
        energy: String,
        carbs: String,
        fat: String,
        protein: String,
    ): ApolloResponse<CreateFoodProductMutation.Data> {
        return apolloClient.mutation(CreateFoodProductMutation(
            barcode = barcode,
            brand = brand,
            name = name,
            weight = weight,
            numServings = numServings,
            energy = energy,
            carbs = carbs,
            fat = fat,
            protein = protein,
        )).execute()
    }

    companion object {
        private const val TAG: String = "NUT FoodProductRepository"
    }
}