package com.feex.nutrition.ui.screens.barcodescanner

import android.Manifest
import android.util.Log
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.PermissionRequired
import com.google.accompanist.permissions.rememberPermissionState

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun BarcodeScannerScreen(
    barcodeScannerViewModel: BarcodeScannerViewModel,
    onBarcodeFound: () -> Unit,
) {
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
            Log.d("NUT BarcodeScannerScreen", "content")
            BarcodeScannerLayout(barcodeScannerViewModel, onBarcodeFound)
        },
    )
}

@Composable
fun BarcodeScannerLayout(
    barcodeScannerViewModel: BarcodeScannerViewModel,
    onBarcodeFound: () -> Unit,
) {
    when (barcodeScannerViewModel.barcodeScannerState) {
        is BarcodeScannerState.Scanning -> CameraPreviewView(barcodeScannerViewModel)
        is BarcodeScannerState.Found -> {
            Log.d("NUT BarcodeScannerLayout", "onBarcodeFound")
            onBarcodeFound()
        }
    }
}
