# DONGLE-ID

**Stop guessing which USB dongle goes with which device.**

DONGLE-ID is a small desktop app that reads the real USB descriptors baked into every dongle's firmware — Vendor ID, Product ID, Serial Number, Manufacturer/Product strings — and uses them to build a personal catalogue of what each physical dongle actually does. Plug one in, and it tells you instantly. No more plugging in three identical black USB receivers to find out which one pairs with your mouse.

![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![UI](https://img.shields.io/badge/UI-PyQt6-orange)

---

## Why

If you've got a drawer of USB dongles for mice, keyboards, headsets, and other wireless peripherals, they often look **identical** but are only compatible with the one device they shipped with. DONGLE-ID fixes that by fingerprinting each dongle from its actual firmware descriptors and letting you label it once — permanently.

## Features

- **Instant identification** — plug in a registered dongle, see what it's for in the Monitor tab immediately.
- **One-click registration** — unknown dongle plugged in? Hit REGISTER, name it, done.
- **Live device table** — every currently connected HID device, known or unknown, with a REGISTER/EDIT action right on the row.
- **Searchable catalogue** — full list of everything you've registered: name, category, VID:PID, serial, times seen, last seen, notes.
- **Manual entry** — pre-catalogue a dongle by typing its VID/PID even if it isn't plugged in right now.
- **Export / Import (portable & shareable)** — export your catalogue as a self-describing JSON file and hand it to another machine or a teammate. Import merges intelligently — new entries are added automatically, and conflicts prompt you to keep yours or take the imported version, so you never silently lose data.
- **Dark industrial UI** — because a utility like this should look like a piece of test equipment, not a to-do app.

## How it works

Every USB HID device reports a small set of descriptor fields when it enumerates — this is standard USB spec, not something the app has to reverse-engineer:

| Field | Example |
|---|---|
| Vendor ID | `046d` |
| Product ID | `c52b` |
| Serial Number | `SN00123ABC` *(not all devices report one)* |
| Manufacturer String | `Logitech` |
| Product String | `USB Receiver` |

DONGLE-ID combines Vendor ID + Product ID + Serial Number into a fingerprint that uniquely identifies **that specific physical dongle** (falling back to just VID:PID if a device doesn't report a serial — the app will flag this lower-confidence case). Your fingerprint → label mappings are stored locally and checked against whatever's currently connected, on a ~1.2 second poll loop.

## Installation

```bash
git clone https://github.com/<your-username>/dongle-id.git
cd dongle-id
pip install -r requirements.txt
python dongle_id.py
```

### Requirements

- Python 3.9+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [hidapi](https://pypi.org/project/hidapi/)

### Platform notes

- **Windows / macOS** — should work out of the box, no extra driver setup.
- **Linux** — you may need `hidraw` permissions to read serial/manufacturer strings correctly. Add your user to the `plugdev` group, or add a udev rule scoped to the relevant device class, then re-plug the device.

## Usage

1. Launch the app and open the **MONITOR** tab.
2. Plug in a dongle — **one at a time**, so the app can tell which device just appeared.
3. Unknown device → click **REGISTER** on its row, give it a name and category, save.
4. Known device → identified instantly with a green confirmation and your saved notes.
5. Browse, search, edit, or delete anything from the **CATALOGUE** tab.

### Sharing your catalogue

- `CATALOGUE → ⇩ EXPORT CATALOGUE` — writes a portable JSON file (includes format version + export date) you can back up or hand to someone else.
- `CATALOGUE → ⇧ IMPORT CATALOGUE` — reads that file back in. New entries are added automatically; if an entry already exists locally, you'll be asked whether to keep yours or take the imported version.

## Data storage

Your catalogue lives locally at:

```
~/.dongle_id/catalogue.json
```

Nothing is sent anywhere — it's a local JSON file you fully own and can back up, version-control, or sync however you like.

## Roadmap / ideas

- [ ] System tray mode with background notifications on plug-in
- [ ] Bulk onboarding wizard for cataloguing many dongles in one session
- [ ] Activity log of plug-in events over time
- [ ] Photo attachment per catalogue entry
- [ ] Printable label sheet for physically tagging dongles
- [ ] Ambiguity warnings for dongles with no serial number

Contributions and issue reports welcome.

## License

Add a license of your choice (e.g. MIT) before publishing — none is included by default.
