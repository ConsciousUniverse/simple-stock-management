package com.cortoba.warehouse

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * The check that runs while the app is closed.
 *
 * The dialog on launch only helps someone who opens the app; a phone in a
 * drawer would sit on an old build for weeks. This worker asks every few hours
 * and posts a notification, so the update is announced rather than discovered.
 */
class UpdateWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val session = Session(applicationContext)
        val api = session.api()
        val info = runCatching { api.versionAnonymous() }
            .onFailure { Log.w(TAG, "update check failed: ${it.message}") }
            .getOrNull()
        if (info == null || !info.isNewerThan(BuildConfig.VERSION_CODE)) {
            return@withContext Result.success()
        }
        UpdateNotifier.notify(applicationContext, info)
        Result.success()
    }

    companion object {
        private const val TAG = "UpdateWorker"
        private const val WORK_NAME = "warehouse-update-check"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<UpdateWorker>(6, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                // KEEP: re-scheduling on every launch must not reset the timer,
                // or a phone opened daily would never reach the six-hour mark.
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
