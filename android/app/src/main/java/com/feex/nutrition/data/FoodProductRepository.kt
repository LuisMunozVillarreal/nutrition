package com.feex.nutrition.data

import com.apollographql.apollo3.ApolloClient
import com.apollographql.apollo3.api.ApolloResponse
import com.feex.nutrition.CreateFoodProductMutation
import com.feex.nutrition.GetFoodProductByBarcodeQuery
import com.feex.nutrition.adapter.GetFoodProductByBarcodeQuery_ResponseAdapter
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FoodProductRepository @Inject constructor(){
    private val apolloClient = ApolloClient.Builder().serverUrl("http://192.168.0.2:8000/graphql").build()

    suspend fun getFoodProductByBarcode(barcode: String): ApolloResponse<GetFoodProductByBarcodeQuery.Data> {
        return apolloClient.query(GetFoodProductByBarcodeQuery(barcode = barcode)).execute()
    }

    suspend fun createFoodProduct(barcode: String): ApolloResponse<CreateFoodProductMutation.Data> {
        return apolloClient.mutation(CreateFoodProductMutation(barcode = barcode)).execute()
    }
}