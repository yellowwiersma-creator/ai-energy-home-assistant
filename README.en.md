# AI Energy for Home Assistant

Price forecasting and bounded energy scheduling, prepared as an open-source
preview. The full [Dutch README](README.md) contains installation instructions.

The repository includes the actual V11 forecasting modules, opt-in Pyscript
bridges, a new pure advisory load scheduler, an inactive advanced EV recipe,
tests, and an entirely synthetic end-to-end demonstration.

```console
python -m pip install -r requirements-dev.txt
python tools/run_tests.py
python tools/demo.py --output demo-output/demo.json
```

Keep published market prices, predicted market prices and final retail tariffs
distinct. A new installation starts without learned household history.
No private measurements, calendar entries, trained models, credentials or
deployment-specific identifiers are included. Demo results are not performance
or savings evidence.

The generic scheduler never controls equipment. The optional EV recipe retains
its session/deadline/manual-override logic but requires local integration review;
all automations and its master initialize OFF. This is a manual-install preview,
not a one-click HACS integration or a universal charger driver.

Code is MIT licensed. External Home Assistant integrations and data providers
retain their own licenses and terms; see [NOTICE.md](NOTICE.md).
