# Gegevens, eenheden en tijd

## Algemene adviesplanner

Een scenario bevat `price_unit: "EUR/kWh"`, `site_power_kw`, `slots` en `loads`.

```json
{
  "price_unit": "EUR/kWh",
  "site_power_kw": 4.6,
  "slots": [
    {"start": "2025-01-01T00:00:00Z", "retail_eur_kwh": 0.20, "source": "known"},
    {"start": "2025-01-01T00:15:00Z", "retail_eur_kwh": 0.16, "source": "forecast", "uncertainty_eur_kwh": 0.03}
  ],
  "loads": [
    {"name": "Demo", "energy_kwh": 0.5, "power_kw": 1.0,
     "earliest": "2025-01-01T00:00:00Z", "deadline": "2025-01-01T01:00:00Z"}
  ]
}
```

Een slot duurt precies 15 minuten. Tijdstempels bevatten een UTC-offset en
worden intern naar UTC omgezet; zo blijven de twee gelijke lokale klokuren
bij de overgang naar wintertijd afzonderlijke momenten. Dubbele slots worden
afgewezen. Gaten in een prijsreeks mogen geen aaneengesloten blok vormen.

`known` betekent een bekend **volledig consumententarief**. Gebruik `forecast`
wanneer alleen de marktprijs vaststaat maar de retailomzetting nog geschat is.
`uncertainty_eur_kwh` is een door de aanroeper gekozen opwaarts scenario,
geen statistische garantie. Bij `uncertainty_weight > 0` komen prognoses zonder
zo'n marge niet in aanmerking.

`energy_kwh` is de gevraagde **elektrische inputenergie**. Bereken een benodigde
accutoename dus eerst met het relevante laadverlies. Bereken warmtebehoefte
afzonderlijk; de referentieplanner schat geen COP, temperatuur of comfort.

## HA-forecastcontract

`sensor.ai_energy_v11_dashboard_data` publiceert onder andere:

- `core_ready`: of het kernadvies voldoende gegevens heeft;
- `predictions`: de compacte kwartierreeks met onder andere `timestamp` en
  `retail_cent` (volledig verwacht consumententarief in ct/kWh);
- `known_market_slots` en `ai_market_slots`: marktbronherkomst, geen garantie
  dat de totale retailprijs al bekend is;
- expliciete retail-eenheid en `interval_minutes: 15`;
- de modelnamen en eventueel beschikbare evaluatie-informatie.

Bekijk bij een eigen adapter de actuele attributen voordat je de reeks bindt.
De optionele EV-adapter controleert de eenheid en eindigheid van een prijs en
deelt centen door 100. Ongeldige prijsregels worden overgeslagen.

Er bestaat nog geen universele automatische omzetting van iedere leverancier-
of forecastsensor naar het algemene scenarioformaat. `tools/plan.py` verwacht
het hierboven beschreven expliciete contract.
