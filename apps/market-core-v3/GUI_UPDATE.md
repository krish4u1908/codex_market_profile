# GUI 3.0.8 prerequisite

This release requires **core 3.0.2** and `OPTION_REPORT_INPUTS_V1` for the basic
OI / VIX bubbles. For an existing core 3.0.1 installation, use the **full bundle**
with `core/deploy/update_data.py check` and `apply`; follow `DATA_UPDATE.md`.

Do not deploy this as a GUI-only change over core 3.0.1. The GUI-only updater
checks both cores before changing services. After core 3.0.2 is installed, the
separate GUI-only package may be used for reinstallation of the GUI, with
`sudo python3 -B update_gui.py check` then `apply` in a freshly extracted bundle.

BANKNIFTY GUI remains on 8920; NIFTY GUI remains on 8921. PE bubbles are above
the price/basis ribbon and CE bubbles below. For each side, red is a VIX rise
of at least 0.4% and green is a fall of at least 0.4%. See `OI_ENTRY_REPLAY.md`
for the complete basic rule and recorded-session verification.
