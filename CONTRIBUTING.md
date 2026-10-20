# Bijdragen

Beschrijf bij een wijziging het concrete probleem, het nieuwe gedrag en de
gebruikte test. Gebruik fictieve voorbeelden in issues en pull requests.

Voer voor een voorstel uit:

```console
python -m pip install -r requirements-dev.txt
python tools/run_tests.py
python tools/audit_release.py
```

Houd gepubliceerde marktprijzen, marktprognoses en consumententarieven uit
elkaar. Vermeld eenheden, tijdzone en ontbrekende waarden expliciet. Een
ontbrekende prijs mag nooit als nul worden ingevuld.

Behoud deadline-, handmatige-override- en noodregels bij wijzigingen aan het
EV-recept. Voeg een scenario toe dat aantoont dat een gewijzigde opdracht
na een wachttijd geen oude startopdracht kan laten doorgaan.

Publiceer geen HA-back-up, persoonlijk logbestand of opgeslagen model bij
een foutmelding. Een synthetisch scenario en een foutmelding zonder waarden
zijn meestal voldoende.

Een nieuw bronbestand wordt alleen meegepakt nadat het afzonderlijk is
gereviewd en toegevoegd aan `RELEASE_FILES.txt`. Neem daar nooit lokaal
gerenderde configuratie of een instellingenbackup in op.
