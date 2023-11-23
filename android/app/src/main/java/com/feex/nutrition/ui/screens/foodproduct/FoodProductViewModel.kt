package com.feex.nutrition.ui.screens.foodproduct

import android.util.Log
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.apollographql.apollo3.exception.ApolloException
import com.feex.nutrition.GetFoodProductByBarcodeQuery
import com.feex.nutrition.data.FoodProductRepository
import com.feex.nutrition.data.BarcodeRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface FoodProductState {
    object Idle : FoodProductState
    object Fetching : FoodProductState
    object Fetched : FoodProductState
    object NotFound : FoodProductState
    object Error : FoodProductState
    object Creating : FoodProductState
    object Created : FoodProductState
}

@HiltViewModel
class FoodProductViewModel @Inject constructor(
    val barcodeRepository: BarcodeRepository,
    private val foodProductRepository: FoodProductRepository,
) : ViewModel() {
    var foodProductState: FoodProductState by mutableStateOf(FoodProductState.Idle)
        private set
    var foodProduct: GetFoodProductByBarcodeQuery.GetFoodProductByBarcode? = null

    fun getOrCreateFoodProduct(barcode : String) {
        viewModelScope.launch {
            Log.d(TAG, "getOrCreateFoodProduct:  ${foodProductState.javaClass.simpleName}")
            foodProductState = FoodProductState.Fetching

            try {
                val response = foodProductRepository.getFoodProductByBarcode(barcode)
                if (response.hasErrors()) {
                    foodProductState = FoodProductState.Error
                }
                else if (response.data?.getFoodProductByBarcode!!.isEmpty()) {
                    foodProductState = FoodProductState.NotFound
                }
                else {
                    foodProduct = response.data?.getFoodProductByBarcode?.first()
                    foodProductState = FoodProductState.Fetched
                }
            } catch (e: ApolloException) {
                foodProductState = FoodProductState.Error
            }
        }
    }

    companion object {
        private const val TAG: String = "NUT FoodProductViewModel"
    }
}
