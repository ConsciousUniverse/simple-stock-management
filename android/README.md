# The warehouse Android app

The phone app for the warehouse: it signs in against this server, shows the
account, and **installs its own updates**.

## What it does

| Screen | What it shows |
| --- | --- |
| Sign in | Phone number **or user name**, and the password a manager gave. The server address is editable, so one build serves every deployment. |
| My account | Name, role, and the number the app signs in with — **read only**. A button asks a manager for a new number. |
| Update prompt | On launch, and every six hours in the background, the app asks `GET /api/mobile/version/?code=<installed>`; a higher build opens a dialog (or a notification when the app is closed) and downloads + installs the APK. |

## Why the phone cannot be changed in the app

The number is the account's identity in the app: it is what a manager sets on
`/users/`, and it is what the app displays. If the app could write it, anyone
holding a phone for a minute could point it at another person's account. So:

* `POST /api/mobile/phone-change-requests/` only **records a request**; the
  number does not move.
* The manager approves or refuses on `/users/` → «طلبات تغيير رقم الهاتف».
* A payload that tries to write `phone` is refused with `403 phone_locked`.

## Building

JDK 17 and the Android SDK (platform 34, build-tools 34) are required.

```bash
cd android
echo "sdk.dir=/path/to/android-sdk" > local.properties
gradle :app:testDebugUnitTest :app:assembleRelease
# app/build/outputs/apk/release/app-release.apk
```

`keystore/warehouse-release.jks` is committed **on purpose**: Android refuses to
install an update signed by a different key, so a per-machine key would force
every phone to uninstall before each update. It protects the update channel, not
a Play listing.

## Publishing a build

1. Bump **both** `versionCode` and `versionName` in `app/build.gradle.kts`. The
   phones compare `versionCode`; without a bump nothing is offered.
2. Build, then upload the APK somewhere durable — the server's disk is wiped on
   every deploy, so `/android/` stores the **address**, never the file. The
   releases repository `melsofany/warehouse-app-releases` is used for this.
3. Compute `sha256sum` and the size in bytes.
4. Publish on `/android/` (a manager): version, **build number** (must be higher
   than the current one), address, checksum, size, and whether the build is
   mandatory.

The app checks the checksum after downloading and refuses the file when it does
not match.
