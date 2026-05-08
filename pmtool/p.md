# Projektbericht

## Allgemeine Angaben
- **Projekttitel:** Raspberry Pi Pico 2 Mainboard
- **Projektteam:** Maximilian Ströhle, Florian Burtscher
- **Datum:** 2026-04-15

## Projektrisiko
| Risiko | Wahrscheinlichkeit | Ausmaß | Gegenmaßnahme |
| --- | --- | --- | --- |
| GPIO-Pin-Konflikte bei Features
PCB-Fehler (Routing/Footprint)
Zeitknappheit | 3/5 (mittel) | 5/5 (sehr hoch) | Frühzeitige Pin-Planung, Pin-Matrix erstellen, Funktionen priorisieren
DRC/ERC, Referenzdesigns nutzen
Klare Feature-Abgrenzung, kein Scope-Creep |
| PCB-Fehler (Routing/Footprint) | 3/5 (mittel) | 3/5 (mittel) | DRC/ERC, Referenzdesigns nutzen |
| Zeitknappheit | 2/5 (gering) | 3/5 (mittel) | Klare Feature-Abgrenzung, kein Scope-Creep |

## Aufgabenrisiko
| Risiko | Wahrscheinlichkeit | Ausmaß | Gegenmaßnahme |
| --- | --- | --- | --- |
| PCB-Layout auf Fertigungsreife bringen: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| PCB-Bestellung vorbereiten: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| PCB-Design fortsetzen: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| Pico 2 W Test Board Programmieren und Testen: Fehlende Testabdeckung auf Hardware-Schnittstellen | 2/5 (gering) | 3/5 (mittel) | Frühe Bring-up-Tests und definierte Testprotokolle durchführen |
| MicroPython Bring-up dokumentieren: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Projekt Auftrag analysiert und festgelegt was wir wollen: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Bisherig festgelegte Teile angeschaut und uns darüber informiert: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Besprechung mit Betreuungslehrer: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Wir haben geplant den Auftrag genau zu inspizieren und festzulegen, was genau wir im Projekt wollen und was nicht: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Wir haben geplant uns die Bauteile, die wir entscheiden zu verwenden anzuschauen und uns zu überlegen welche genau wir verwenden: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Mit Betreuungslehrer Projektspezifikationen besprechen: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Schaltplan fast fertig (nur noch GPIO break Out): GPIO-Pin-Konflikte bei Feature-Erweiterungen | 3/5 (mittel) | 3/5 (mittel) | Frühzeitige Pin-Matrix pflegen, Funktionen priorisieren und vor Routing fixieren |
| Angefangen zu Planen was für GPIO-Pins wir für was für Features verwendet werden: GPIO-Pin-Konflikte bei Feature-Erweiterungen | 3/5 (mittel) | 3/5 (mittel) | Frühzeitige Pin-Matrix pflegen, Funktionen priorisieren und vor Routing fixieren |
| Geeignete Bauteile ausgewählt die wir vorab wissen müssen: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Schaltplan weiterzeichnen: Fehler im Schaltplan | 2/5 (gering) | 4/5 (hoch) | Schaltplan-Review und Datenblatt-Checks gegen kritische Signale |
| Bauteile auswählen: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| Alle Bauteile aus dem Magazin und DigiKey gewählt und Footprints gesetzt: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| PCB design zu 10% fertig: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| Schaltplan 100% fertig: Fehler im Schaltplan | 2/5 (gering) | 4/5 (hoch) | Schaltplan-Review und Datenblatt-Checks gegen kritische Signale |
| Beginn PCB design: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| Fertig festlegen der Footprints: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| PCB-Design zu 80% Fertig: Routing-/Footprint-Fehler im PCB | 3/5 (mittel) | 4/5 (hoch) | ERC/DRC prüfen, Peer-Review vor Bestellung, Referenzdesign vergleichen |
| Test Board in Betrieb genommen und I2C Bus getestet: Fehlende Testabdeckung auf Hardware-Schnittstellen | 2/5 (gering) | 3/5 (mittel) | Frühe Bring-up-Tests und definierte Testprotokolle durchführen |
| GPIO-Pin-Matrix konsolidieren: GPIO-Pin-Konflikte bei Feature-Erweiterungen | 3/5 (mittel) | 3/5 (mittel) | Frühzeitige Pin-Matrix pflegen, Funktionen priorisieren und vor Routing fixieren |
| Reset- und Entprellschaltung finalisieren: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| I2C Bus mit Oszilloskop validieren: Fehlende Testabdeckung auf Hardware-Schnittstellen | 2/5 (gering) | 3/5 (mittel) | Frühe Bring-up-Tests und definierte Testprotokolle durchführen |
| Power-Design TPS62162 verifizieren: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |
| USB-C Schnittstelle robust implementieren: Terminabweichungen durch Hardware-Iteration | 2/5 (gering) | 3/5 (mittel) | Puffer einplanen und Prioritäten pro Woche fokussieren |

## Nächster Meilenstein
- **Bezeichnung:** GPIO-Planung abgestimmt
- **Geplantes Datum:** 2026-04-18