# Installatie

## Eerst de demo

Download het bronpakket en pak het uit in een nieuwe map. Voer vanuit die map uit:

```console
python -m pip install -r requirements-dev.txt
python tools/run_tests.py
python tools/demo.py --output demo-output/demo.json
```

Gebruik Python 3.11 of hoger. De demo en tests werken met tijdelijke opslag.
Zij loggen niet in bij Home Assistant en sturen geen apparaten aan.

## Vereisten voor de HA-voorspeller

- Home Assistant met een afzonderlijk geïnstalleerde
  [Pyscript-integratie](https://hacs-pyscript.readthedocs.io/en/latest/reference.html).
- Pyscript moet normale Python-modules uit `/config/pyscript_modules` kunnen
  importeren. Deze opzet gebruikt `allow_all_imports: true`. Stel dat in via
  dezelfde configuratiemethode waarmee Pyscript al is geïnstalleerd; meng de
  UI- en YAML-basisconfiguratie niet.
- Werkende marktprijsbronnen via de officiële
  [Nord Pool-integratie](https://www.home-assistant.io/integrations/nordpool/)
  en/of een compatibele ENTSO-E-integratie.
- Een echte kwartierprijsbron voor het consumententarief. Deze preview gebruikt
  het bestaande Zonneplan-gerichte broncontract. Een andere leverancier vraagt
  een adapter of equivalente sensoren; de retailrol hernoemen alleen is niet
  voldoende wanneer de gegevens een andere betekenis hebben.
- Optioneel: eigen weer-, PV- en P1-entiteiten voor context en latere evaluatie.

De scalar prijsentiteiten die de collector leest moeten **EUR/kWh** voorstellen.
Maak zo nodig eerst eigen HA-templates die ct/kWh door 100 of EUR/MWh door 1000
delen. De Nord Pool-actie met een dagreeks heeft haar eigen normalisatie in
de adapter. Vergelijk geen kale marktprijs met een all-in consumententarief.
Andere valuta worden in deze preview afgewezen.

Dit pakket bevat geen API-sleutels en vraagt ze ook niet in de repository op.
Configureer een eventuele sleutel in de betreffende externe HA-integratie.

## Bronentiteiten invullen

Kopieer `examples/settings.example.json` naar een eigen bestand **buiten**
de repository. De sectie `entities` beschrijft de rollen. Laat ongebruikte,
optionele rollen leeg en vervang gebruikte `sensor.example_*`-waarden door
werkelijke eigen entiteiten. Geef weerentiteiten apart op in `weather_entities`.

`nordpool.config_entry` is de lokale configuratie-entry van de Nord Pool-integratie,
niet een API-sleutel. Laat hem leeg als je geen Nord Pool-dagactie gebruikt;
de code weigert dan een Nord Pool-verzoek. Voor inschakelen is een gekoppelde
retailbron en minstens één geconfigureerde marktbron verplicht.

Een syntactisch correcte mapping bewijst niet dat de entiteit beschikbaar is of
de juiste eenheid heeft. Controleer dat eerst in de HA-ontwikkelaarshulpmiddelen.
Laat `enabled` voorlopig `false`.

## Installatiemap voorbereiden

```console
python tools/prepare_install.py --destination install-stage --settings examples/settings.example.json
```

De bestemming moet nieuw zijn. Het hulpmiddel kopieert alleen de afzonderlijk
gereviewde forecastingbestanden uit `RELEASE_FILES.txt` en schrijft een lokale
configuratie met `enabled: false`. Het weigert bestaande mappen/bestanden en
symlink-/junctionpaden. Het installeert geen laadbesturing.

De structuur wordt:

```text
install-stage/
  ai_energy_v11/settings.json
  pyscript_modules/ai_energy_v11/*.py
  pyscript/ai_energy_v11*_bridge.py
  pyscript/ai_energy/__init__.py
```

Maak een backup van een bestaande installatie voordat je lokaal iets vervangt.
Gebruik voor de eerste beoordeling een afzonderlijke testinstallatie. Kopieer
de genoemde submappen vervolgens naar de gelijknamige locaties onder `/config`.
Laat bestaande, anders ingerichte AI Energy-versies niet tegelijkertijd dezelfde
sensoren publiceren. Het voorbereidingshulpmiddel voert deze migratie niet uit.

De betekenis van `AI_ENERGY_ROOT` is uitsluitend een alternatieve lokale
opslag- en instellingenmap. De standaard binnen HA is `/config/ai_energy_v11`.
De instellingen heten altijd `settings.json` binnen die map.

## Verzamelen en berekenen

1. Controleer `/config/ai_energy_v11/settings.json` lokaal.
2. Zet `enabled` op `true` wanneer de benodigde bronrollen en eenheden kloppen.
3. Herstart Pyscript zodat ook de gewone Python-configuratiemodule opnieuw wordt
   geïmporteerd. Alleen een editorbestand verversen hoeft daarvoor niet voldoende te zijn.
4. Controleer `sensor.ai_energy_v11_setup`, `sensor.ai_energy_v11_collector` en
   `sensor.ai_energy_v11_dashboard_data`.
5. Gebruik eventueel de bestaande Pyscript-acties zoals
   `pyscript.ai_energy_v11_collect_now`,
   `pyscript.ai_energy_v11_refresh_market_now` en
   `pyscript.ai_energy_v11_forecast_cycle` voor een gerichte controle.

Een nieuwe installatie begint zonder training. Het marktmodel vraagt minimaal
28 dagen historie; de retaillearner gebruikt onder andere een minimum van
500 rijen. De uitgebreidere forwardvalidatie vraagt meer gegevens. Dit zijn
minimumvoorwaarden in de huidige code, geen garantie op een goed model.
`core_ready: false` of onvoldoende historie is bij een koude start te verwachten.

Beoordeel later voorspellingen die vóór het doelkwartier zijn vastgelegd.
Publiceer geen testpercentages of besparingen voordat die met eigen, passende
gegevens zijn aangetoond.

## Planner en dashboard

De algemene adviesplanner leest een expliciet JSON-scenario. Er is nog geen
algemene HA-service die iedere consument of verwarmingsinstallatie automatisch
kan bedienen. Het afzonderlijke EV-recept heeft een eigen inrichtingstraject:
[EV-PLANNER.md](EV-PLANNER.md).

Je kunt de belangrijkste forecastsensorgegevens zonder custom kaart bekijken:

```yaml
type: entities
title: AI Energy
entities:
  - sensor.ai_energy_v11_setup
  - sensor.ai_energy_v11_collector
  - sensor.ai_energy_v11_dashboard_data
  - sensor.ai_energy_v11_forecast_accuracy
```

Deze kaart toont de bestaande entiteiten. Open de meer-informatie/attributen
voor de prijsreeks en modelstatus.
