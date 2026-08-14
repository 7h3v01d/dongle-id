DONGLE-ID -- USB Dongle Registration & Identification Console
================================================================

SETUP
    pip install -r requirements.txt
    python dongle_id.py

HOW IT WORKS
    The app reads each USB HID device's real descriptor fields --
    Vendor ID, Product ID, Serial Number, Manufacturer string, and
    Product string -- which are burned into the dongle's firmware.
    It combines VID+PID+Serial into a fingerprint that uniquely
    identifies that physical dongle (falls back to VID+PID if a
    dongle reports no serial, which some cheap ones don't).

WORKFLOW
    1. Open the app, go to the MONITOR tab.
    2. Plug in one dongle at a time.
    3. Every row in the live table has a REGISTER (unknown) or EDIT
       (known) button -- works for anything currently connected,
       whether it just got plugged in or was already there.
    4. Next time that exact dongle goes in, it's instantly
       identified: "DEVICE IDENTIFIED -> Logitech mouse receiver".
    5. The CATALOGUE tab lists everything registered, with
       search/filter, + ADD NEW ENTRY (pick a connected device or
       type VID/PID manually), edit, and delete.

SHARING / PORTING YOUR CATALOGUE
    Catalogue tab -> EXPORT CATALOGUE saves a self-describing JSON
    file (app name, format version, export date, entry count) that
    you can hand to someone else or move to another PC.

    Catalogue tab -> IMPORT CATALOGUE reads that file back in. It
    merges rather than blindly overwrites:
        - new entries are added straight away
        - entries that already exist locally (same VID/PID/serial)
          trigger a prompt: Keep Mine / Overwrite With Imported /
          Cancel Import
    Old bare-JSON exports (from before this feature) still import
    fine -- the importer recognizes both formats.

NOTES
    - Plug dongles in ONE AT A TIME during registration/detection --
      if several appear in the same ~1.2s poll cycle the app can't
      tell which is which and will just tell you to do them
      individually.
    - Linux: if a dongle shows blank serial/manufacturer strings, you
      may need udev permissions for hidraw access (add your user to
      the 'plugdev' group, or add a udev rule for the device).
    - Windows/macOS: should work with no extra setup via hidapi.
    - Catalogue is stored at ~/.dongle_id/catalogue.json
