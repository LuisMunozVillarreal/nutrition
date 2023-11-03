package com.feex.nutrition.foodproductfinder

import android.Manifest
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.camera.core.Preview
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.apollographql.apollo3.ApolloClient
import com.feex.nutrition.FoodProductSearchQuery
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.PermissionRequired
import com.google.accompanist.permissions.rememberPermissionState
import com.google.mlkit.vision.barcode.common.Barcode
import java.util.concurrent.Executors
import com.feex.nutrition.foodproductfinder.*

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun BarcodeScanScreen() {
    val cameraPermissionState = rememberPermissionState(permission = Manifest.permission.CAMERA)

    PermissionRequired(
        permissionState = cameraPermissionState,
        permissionNotGrantedContent = {
            LaunchedEffect(Unit) {
                cameraPermissionState.launchPermissionRequest()
            }
        },
        permissionNotAvailableContent = {
            Text("Permission denied. Barcode scanner can't " +
                    "function without access to the camera")
        },
        content = {
            BarcodeScanner()
        },
    )
}

@Composable
fun BarcodeScanner() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val detectedBarcode = remember { mutableStateListOf<Barcode>() }
    val imageWidth = remember { mutableStateOf(0) }
    val imageHeight = remember { mutableStateOf(0) }
    val analyzer = BarcodeAnalyser { barcodes, width, height ->
        detectedBarcode.clear()
        detectedBarcode.addAll(barcodes)
        imageWidth.value = width
        imageHeight.value = height
    }
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }
    var preview by remember { mutableStateOf<Preview?>(null) }
    val executor = ContextCompat.getMainExecutor(context)
    val cameraProvider = cameraProviderFuture.get()
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }

    if (detectedBarcode.size == 0) {
        AndroidView(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(),
            factory = { ctx ->
                val previewView = PreviewView(ctx)
                cameraProviderFuture.addListener({
                    val imageAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .apply {
                            setAnalyzer(cameraExecutor, analyzer)
                        }
                    val cameraSelector = CameraSelector.Builder()
                        .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                        .build()
                    cameraProvider.unbindAll()
                    cameraProvider.bindToLifecycle(
                        lifecycleOwner,
                        cameraSelector,
                        imageAnalysis,
                        preview
                    )
                }, executor)
                preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }
                previewView
            }
        )
    }
    else {
        val barcode = detectedBarcode.joinToString(separator = "\n") { it.displayValue.toString() }
        Text(text = barcode)
        var foodProduct by remember { mutableStateOf<String?>("") }
        val apolloClient = ApolloClient.Builder().serverUrl("http://192.168.0.2:8000/graphql").build()
        LaunchedEffect(Unit) {
            val response = apolloClient.query(FoodProductSearchQuery(barcode = barcode)).execute()
            foodProduct = response.data?.foodProductSearch?.firstOrNull()?.name
        }
        if (foodProduct.isNullOrBlank()) {
            Text(text = "No product in local DB")
        }
        else {
            Text(text = foodProduct.toString())
        }
    }
}

//@Preview
@Composable
fun BarcodeScanScreenPreview() {
    BarcodeScanner()
}
