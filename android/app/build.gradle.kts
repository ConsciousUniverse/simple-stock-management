plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.cortoba.warehouse"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.cortoba.warehouse"
        minSdk = 24
        targetSdk = 34
        versionCode = 6
        versionName = "1.4.1"
        // The deployment the app talks to. There is no field on the phone to
        // change it: one build serves the site it was made for, and a wrong
        // address cannot be typed in by mistake.
        buildConfigField("String", "DEFAULT_BASE_URL", "\"https://ssm-warehouse.onrender.com/\"")
    }

    buildFeatures {
        buildConfig = true
        viewBinding = true
    }

    /**
     * One key, committed, for the app's whole life.
     *
     * Android refuses to install an update signed by a different key, so a
     * per-machine debug key would force every phone to uninstall before each
     * update — losing the session and teaching users to ignore the prompt. The
     * key is in the repository on purpose: it protects the update channel, not
     * a Play listing. The password can be overridden by an environment
     * variable for a build outside this repository.
     */
    signingConfigs {
        create("release") {
            storeFile = file("keystore/warehouse-release.jks")
            storePassword = System.getenv("KEYSTORE_PASSWORD") ?: "warehouse-release"
            keyAlias = "warehouse"
            keyPassword = System.getenv("KEY_PASSWORD") ?: "warehouse-release"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    // Scanning the item label. The embedded ZXing activity is a whole scanner
    // (preview, torch, permission) with one line of glue here — writing a
    // CameraX + ML Kit scanner by hand is a lot of code to keep working on
    // phones we cannot test.
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
