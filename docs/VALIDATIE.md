# Validatie en grenzen

De tests gebruiken synthetische waarden en tijdelijke opslag. Zij wijzigen
geen Home Assistant-installatie en bellen geen echte prijs- of voertuigservices.

Lokale controle op 19 oktober 2026: **65 unittests geslaagd**, waaronder een
test die 15 bestaande modelzelftests uitvoert. De publicatiecontrole van
69 afzonderlijk gekozen bronbestanden gaf geen patroonmeldingen.

## Gecontroleerd

- De echte ingebouwde modelzelftests: markt-/ENTSO-E-normalisatie, learner,
  ledger, evaluatie, marktvoorspelling, confidence en modelbeheer.
- Lokale configuratie: verse installatie uit, ongeldige waarden afgewezen,
  lege Nord Pool-configuratie veroorzaakt geen verzoek, opslag geïsoleerd.
- Algemene planner: ontbrekende/negatieve prijzen, gewogen deelslots, gaten,
  deadlines, gedeeld vermogen, prioriteit, beide DST-overgangen en onzekerheid.
- EV-recept: de 33 flows en sessie-/handmatige-/noodregels, expliciete eenheden,
  uitgeschakelde automatiseringen en guards rond serviceaanroepen.
- Echte demo-CLI: JSON-serialisatie van 384 kunstmatige forecastkwartieren en
  een plan voor drie voorbeeldverbruikers, zonder de aanroepende omgeving te wijzigen.
- Installatievoorbereiding: nieuwe map, exclusieve bestanden, geen stilzwijgende
  vervanging van bestaande configuratie.
- Release: individuele bestandenlijst, uitsluiting van lokale instellingen,
  patrooncontrole op identificatie en aanvullende handmatige broncontrole.

## Nog lokaal te testen

- De volledige eerste installatie in een afzonderlijke HA-omgeving, inclusief
  jouw versie van Pyscript en de gekozen prijsintegraties.
- Koude start, voldoende eigen geschiedenis en chronologische modelkwaliteit
  met echte toekomstige kwartieren.
- Tariefadapter, voertuig-/laadpaalacties en fysieke deadlines met echte apparatuur.
- Een bruikbaar warmte-/comfortmodel voordat verwarmingsadvies automatisch
  voor apparaatsturing wordt gebruikt.

De oorspronkelijke woninginstallatie is bij de voorbereiding niet gewijzigd.
De openbare variant is een afzonderlijke preview en is niet teruggeplaatst in
die installatie. Syntactische tests en geslaagde rekenvoorbeelden vervangen
deze praktijkcontrole niet.

## Opnieuw uitvoeren

```console
python tools/run_tests.py
python tools/audit_release.py
```

De GitHub Actions-workflow is voorbereid voor Linux en Windows. De workflow
is pas op GitHub uitgevoerd nadat de repository daar is aangemaakt en de
workflow is gestart; lokale tests zijn geen bewijs van een al geslaagde CI-run.
