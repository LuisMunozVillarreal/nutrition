package com.nutrition.healthsync

import java.time.ZoneId
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Test

class AboutVersionTest {
    @Test
    fun `about text identifies the installed build`() {
        assertEquals(
            "Versión 1.1 (2)",
            formatInstalledVersion("1.1", 2),
        )
    }

    @Test
    fun `last sync is shown as a local readable time`() {
        assertEquals(
            "2 sept, 15:05",
            formatLastSync(
                "2026-09-02T14:05:00Z",
                ZoneId.of("Europe/London"),
                Locale.forLanguageTag("es-ES"),
            ),
        )
    }
}
