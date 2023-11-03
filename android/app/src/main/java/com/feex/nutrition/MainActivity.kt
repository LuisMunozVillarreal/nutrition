package com.feex.nutrition

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.feex.nutrition.ui.theme.NutritionTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            NutritionTheme {
                NutritionApp()
            }
        }
    }
}
