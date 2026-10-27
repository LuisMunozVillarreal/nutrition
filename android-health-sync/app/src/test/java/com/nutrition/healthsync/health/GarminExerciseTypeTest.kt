package com.nutrition.healthsync.health

import androidx.health.connect.client.records.ExerciseSessionRecord
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GarminExerciseTypeTest {
    @Test
    fun `mapea caminar correr y bicicleta`() {
        assertEquals("walk", GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_WALKING))
        assertEquals("walk", GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_HIKING))
        assertEquals("run", GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_RUNNING))
        assertEquals(
            "run",
            GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL),
        )
        assertEquals("cycle", GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_BIKING))
        assertEquals(
            "cycle",
            GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY),
        )
    }

    @Test
    fun `mapea ejercicios de gimnasio sin inventar otros tipos`() {
        assertEquals(
            "gym",
            GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING),
        )
        assertEquals(
            "gym",
            GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING),
        )
        assertEquals(
            "gym",
            GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING),
        )
        assertNull(GarminExerciseType.toNutritionType(ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER))
    }
}
