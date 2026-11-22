package com.cortoba.warehouse

import android.app.Activity
import android.os.Bundle
import android.view.KeyEvent
import com.journeyapps.barcodescanner.CaptureManager
import com.journeyapps.barcodescanner.DecoratedBarcodeView
import com.journeyapps.barcodescanner.camera.CameraSettings

/**
 * The scanning screen, the way a phone is held: upright.
 *
 * The library's own activity is declared `sensorLandscape`, so tapping "scan"
 * turned the phone sideways. The operator then had to rotate a phone they were
 * already holding upright, the camera restarted on the rotation, and the shelf
 * label had to be re-aimed at a sideways preview — which is most of what "the
 * scanner is slow" was.
 *
 * Focus is the other half of the wait. The library's default is a single
 * autofocus attempt (`AUTO`); on a cheap phone it misses once and then waits for
 * a frame that never gets sharp, so the operator moves the phone back and forth.
 * Continuous focus with the barcode scene mode keeps hunting, and the torch
 * comes on in a dark aisle.
 *
 * `CaptureManager` is reused unchanged, so permissions, the result extra and
 * `ScanContract` behave exactly as before — only the camera settings and the
 * orientation are ours.
 *
 * A plain `Activity`, not an `AppCompatActivity`: the library's capture theme
 * descends from a framework theme, and an AppCompat activity under it throws
 * when it starts — a crash the build cannot see.
 */
class ScannerActivity : Activity() {

    private lateinit var barcodeView: DecoratedBarcodeView
    private lateinit var capture: CaptureManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        barcodeView = DecoratedBarcodeView(this)
        setContentView(barcodeView)

        capture = CaptureManager(this, barcodeView)
        capture.initializeFromIntent(intent, savedInstanceState)
        // AFTER the intent: the library installs its own defaults there, and
        // setting them earlier would be overwritten.
        barcodeView.cameraSettings = CameraSettings().apply {
            isAutoFocusEnabled = true
            isContinuousFocusEnabled = true
            focusMode = CameraSettings.FocusMode.CONTINUOUS
            isBarcodeSceneModeEnabled = true
            isAutoTorchEnabled = true
        }
        capture.decode()
    }

    override fun onResume() {
        super.onResume()
        capture.onResume()
    }

    override fun onPause() {
        super.onPause()
        capture.onPause()
    }

    override fun onDestroy() {
        super.onDestroy()
        capture.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        capture.onSaveInstanceState(outState)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        capture.onRequestPermissionsResult(requestCode, permissions, grantResults)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean =
        barcodeView.onKeyDown(keyCode, event) || super.onKeyDown(keyCode, event)
}
