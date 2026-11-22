package com.cortoba.warehouse

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The scanning screen is the one place the app contradicts how a phone is held.
 *
 * Three things went wrong at once and only one of them is visible in a build:
 * the library's own activity is `sensorLandscape` (so the phone turned
 * sideways), the capture theme descends from a framework theme (so an AppCompat
 * activity under it CRASHES when it starts), and the custom activity has to be
 * named in the scan options or none of it is used.
 */
class ScannerScreenTest {

    private fun read(path: String) = File(path).readText()

    @Test
    fun `the scanner is portrait`() {
        val manifest = read("src/main/AndroidManifest.xml")
        val entry = manifest.substringAfter("android:name=\".ScannerActivity\"")
            .substringBefore("/>")
        assertTrue(
            "the scanner must be portrait: $entry",
            entry.contains("android:screenOrientation=\"portrait\""),
        )
    }

    @Test
    fun `the capture theme is used, so the screen is not a stray light window`() {
        val entry = read("src/main/AndroidManifest.xml")
            .substringAfter("android:name=\".ScannerActivity\"")
            .substringBefore("/>")
        assertTrue(entry.contains("zxing_CaptureTheme"))
    }

    @Test
    fun `a framework theme cannot host an AppCompat activity`() {
        // zxing_CaptureTheme's parent is android:Theme.Holo…; an AppCompatActivity
        // under it throws "You need to use a Theme.AppCompat theme" at startup.
        val source = read("src/main/java/com/cortoba/warehouse/ScannerActivity.kt")
        assertTrue(source.contains("class ScannerActivity : Activity()"))
        // The declaration only: the comment above it names the class it is not.
        assertFalse(source.contains(": AppCompatActivity()"))
    }

    @Test
    fun `the scan asks for our activity`() {
        val source = read("src/main/java/com/cortoba/warehouse/NewDocumentActivity.kt")
        assertTrue(source.contains("setCaptureActivity(ScannerActivity::class.java)"))
        // Locking the orientation would ask the library for landscape.
        assertTrue(source.contains("setOrientationLocked(false)"))
    }

    @Test
    fun `focus keeps hunting instead of stopping at the first miss`() {
        val source = read("src/main/java/com/cortoba/warehouse/ScannerActivity.kt")
        assertTrue(source.contains("isContinuousFocusEnabled = true"))
        assertTrue(source.contains("FocusMode.CONTINUOUS"))
        assertTrue(source.contains("isBarcodeSceneModeEnabled = true"))
    }
}
