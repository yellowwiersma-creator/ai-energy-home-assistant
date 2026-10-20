# Het optionele EV-recept

Dit is de opgeschoonde volledige HA-planner, met 33 samenwerkende automatiseringen
en een kostenscript. Het behoudt de oorspronkelijke afhandeling van agenda,
handmatig doel, vaste start, direct laden, sessiewissels, noodplanning en deadlines.

De openbare voorbeeldversie bevat geen persoonlijke agenda of apparaat-ID.
Alle automatiseringen hebben `initial_state: false`. De aparte
`input_boolean.ai_energy_actuation_enabled` start uit. Ook afzonderlijke
serviceaanroepen controleren die master, zodat een wachttijd geen algemene
toestemming voor latere opdrachten vormt.

## Mappings

`home_assistant/optional/ev_roles.json` beschrijft 22 rollen, waaronder:

- cloud-SOC en het door het voertuig opgegeven update-moment;
- lokale OBD-SOC, ECU-status, oplopende uptime en 12V-spanning;
- laadpaalstatus, laadstroom, modus, sessie-energie en gemeten vermogen;
- voertuiglimiet, voertuigverversing en vertrekkalender;
- import-/exportvermogen, tariefreeks en notificatieontvanger.

`examples/ev-settings.example.json` toont de configuratie. De twee agenda-woorden
worden als AND-filter toegepast; het tweede mag leeg zijn. De hulpmiddelen
controleren entiteitsdomeinen en houden agenda-woorden als gegevens, ook als
daar aanhalingstekens in staan. Laadvermogen en elektrische energie per SOC-procent
zijn expliciete instellingen.

## Lokaal renderen

Bewaar een kopie van de instellingen buiten de repository en gebruik bijvoorbeeld:

```console
python tools/render_ev_planner.py --settings examples/ev-settings.example.json --output local/ev-planner.yaml
```

Het doelbestand moet nieuw zijn. De uitvoer blijft uitgeschakeld. Er is geen
rendereroptie voor het aanzetten van laden of automatiseringen. Het resultaat
bevat jouw lokale mappings zodra je echte instellingen gebruikt; publiceer dat
bestand niet. Alleen het gereviewde generieke recept staat in `RELEASE_FILES.txt`.

## Eerst beoordelen

De bestaande `kia_uvo`-acties, native laadpaalmodi/statuswaarden en de controle
van een bevestigde laadlimiet zijn onderdeel van het recept. Een willekeurige
andere integratie ondersteunt die niet automatisch. Een rolsensor hernoemen
maakt een merkgebonden service niet universeel. Ook de `ai_kia_*`-namespace
blijft bestaan; gebruik het niet naast een bestaande planner met dezelfde IDs.

Laat een lokale adapter eerst aantonen dat aangesloten-status, stroomlimiet,
laadlimiet, energie-eenheid en start/stop-semantiek kloppen. Test vervolgens
handmatig ingrijpen tijdens een wachttijd, korte deadlines en wegvallende bronnen
in een testomgeving. Activeer pas daarna bewust de benodigde automatiseringen.

Het master uitzetten blokkeert volgende opdrachten maar stopt niet gegarandeerd
een al lopende fysieke laadbeurt. Gebruik voor direct stoppen de normale
laadpaal-/voertuigbediening. Fabrieksbeveiligingen en de lokale 12V-slaapinstellingen
van een OBD-adapter blijven zelfstandig ingesteld; dit openbare recept verandert
geen adapterfirmware of slaapgrens.

## Behouden controles

- Handmatige opdrachten en sessiewissels winnen van een eerder berekende opdracht.
- Startvoorwaarden worden na wachten opnieuw beoordeeld.
- De planning gebruikt aaneengesloten kwartieren en rekent het laatste deelslot gewogen.
- Deadline, startbuffer, noodplanning en afkoeltijden blijven in de logica aanwezig.
- De forecastadapter verlangt expliciete kwartier-/ct/kWh-metadata.
- Ontbrekende of niet-eindige prijzen worden overgeslagen; echte nul en negatieve prijzen blijven geldig.

De tests behandelen deze rekenscenario's en controleren de uitgeschakelde
toestand plus guards. Zij bewijzen geen fysieke compatibiliteit met alle
laadpalen, auto's of Home Assistant-versies.
