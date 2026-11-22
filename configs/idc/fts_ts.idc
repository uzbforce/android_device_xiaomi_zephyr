#
# Focaltech FT3683G touchscreen (fts_ts)
#
# Keep the touch device enabled while the display viewport is inactive and let
# its wakeup gestures wake the AP. Without these two switches InputReader
# disables fts_ts as soon as the panel leaves DOZE, which also stops DT2W and
# the raw FOD touch stream.
#

device.internal = 1

touch.deviceType = touchScreen
touch.orientationAware = 1
touch.wake = 1
touch.enableForInactiveViewport = 1

# InputDevice.mIsWaking comes from device.wake, not touch.wake. Without this
# the touch mapper can see the gesture but InputReader will not request a wake.
device.wake = 1
