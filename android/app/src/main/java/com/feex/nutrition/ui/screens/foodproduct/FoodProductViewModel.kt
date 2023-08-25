package com.feex.nutrition.ui.screens.foodproduct

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apollographql.apollo3.exception.ApolloException
import com.feex.nutrition.GetFoodProductByBarcodeQuery
import com.feex.nutrition.data.FoodProductRepository
import com.google.mlkit.vision.barcode.common.Barcode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface FoodProductState {
    object Scanning : FoodProductState
    object BarcodeDetected : FoodProductState
    object Fetching : FoodProductState
    object Fetched : FoodProductState
    object NotFound : FoodProductState
    object AddProductManually : FoodProductState
    object Created : FoodProductState
    object AddedToPantry : FoodProductState
    data class Error(val errors: List<com.apollographql.apollo3.api.Error>?) : FoodProductState
    data class Exception(val exception: ApolloException) : FoodProductState
}

@HiltViewModel
class FoodProductViewModel @Inject constructor(
    private val foodProductRepository: FoodProductRepository,
) : ViewModel() {
    var foodProductState: FoodProductState by mutableStateOf(FoodProductState.Scanning)
        private set
    var foodProduct: GetFoodProductByBarcodeQuery.GetFoodProductByBarcode? = null

    fun reset() {
        viewModelScope.launch {
            foodProductRepository.reset()
            foodProductState = FoodProductState.Scanning
        }
    }

    fun barcodeDetected(barcodes: MutableList<Barcode>) {
        Log.d(TAG, "found")
        foodProductRepository.addDetectedBarcodes(barcodes)
        viewModelScope.launch {
            foodProductState = FoodProductState.BarcodeDetected
        }
    }

    fun getBarcode() : String {
        return foodProductRepository.getBarcode()
    }

    fun getFoodProduct(barcode: String) {
        viewModelScope.launch {
            Log.d(TAG, "getOrCreateFoodProduct:  ${foodProductState.javaClass.simpleName}")
            foodProductState = FoodProductState.Fetching

            try {
                val response = foodProductRepository.getFoodProductByBarcode(barcode)
                if (response.hasErrors()) {
                    Log.d(TAG, response.errors.toString())
                    foodProductState = FoodProductState.Error(response.errors)
                }
                else if (response.data?.getFoodProductByBarcode == null) {
                    foodProductState = FoodProductState.NotFound
                }
                else {
                    foodProduct = response.data?.getFoodProductByBarcode
                    foodProductState = FoodProductState.Fetched
                }
            } catch (e: ApolloException) {
                Log.d(TAG, e.toString())
                foodProductState = FoodProductState.Exception(e)
            }
        }
    }

    fun addFoodProductManually() {
        viewModelScope.launch {
            foodProductState = FoodProductState.AddProductManually
        }
    }

    fun createFoodProduct(
        barcode: String,
        brand: String,
        name: String,
        weight: String,
        numServings: String,
        energy: String,
        carbs: String,
        fat: String,
        protein: String,
    ) {
        viewModelScope.launch {
            try {
                val response = foodProductRepository.createFoodProduct(
                    barcode, brand, name, weight, numServings, energy, carbs, fat, protein
                )
                if (response.hasErrors()) {
                    Log.d(TAG, response.errors.toString())
                    foodProductState = FoodProductState.Error(response.errors)
                }
                else {
                    foodProductState = FoodProductState.Created
                }
            } catch (e: ApolloException) {
                Log.d(TAG, e.toString())
                foodProductState = FoodProductState.Exception(e)
            }
        }
    }

    fun addFoodProductToPantry() {
        viewModelScope.launch {
            foodProductState = FoodProductState.AddedToPantry
        }
    }

    companion object {
        private const val TAG: String = "NUT FoodProductViewModel"
    }
}
