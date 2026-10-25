# Android emulator or device: screenrecord

`screenrecord` on the device writes H.264 MP4, so no conversion is needed. It stops on
its own after 180 seconds.

```sh
adb shell settings put global sysui_demo_allowed 1
adb shell am broadcast -a com.android.systemui.demo -e command enter
adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941
adb shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false
adb shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false
adb shell screenrecord /sdcard/demo.mp4 &
rec=$!
# ... drive the app: an Espresso test, Maestro flow or other scripted run ...
adb shell pkill -INT screenrecord; wait "$rec"
adb pull /sdcard/demo.mp4 "$tmp/demo.mp4" && adb shell rm /sdcard/demo.mp4
adb shell am broadcast -a com.android.systemui.demo -e command exit
```

- Stop with `SIGINT` on the device and wait for it before pulling: killing only the
  local `adb` leaves an unfinished file.
- Set the clock, battery and notifications explicitly: `enter` alone leaves them live, and
  on a real device the notifications can show personal messages.
- Record at the native size: a forced landscape `--size` letterboxes a portrait app.
- A run longer than 180 seconds needs several recordings joined with `ffmpeg -f concat`.
