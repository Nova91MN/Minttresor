# MintTresor

**Eine einfache, lokale Dateiablage mit persönlichen VeraCrypt-Tresoren für Linux Mint.**

Deutsche Desktopoberfläche · lokale Benutzerkonten · frei wählbarer Speicherort · Ordnerzugriff für LibreOffice und andere Programme.

> Version 0.2.0 ergänzt einen einmalig durch den Administrator einzurichtenden Gastzugang ohne Adminpasswort im Alltag. Die Containererstellung wurde mit echtem VeraCrypt 1.26.31 getestet. Ein vollständiger Praxistest mit LibreOffice auf einem Linux-Mint-Desktop steht noch aus.

![MintTresor Startseite](docs/startseite.png)

## Für Einsteiger: installieren

1. **VeraCrypt installieren:** Auf der [offiziellen Downloadseite](https://veracrypt.io/en/Downloads.html) das passende Linux-Paket herunterladen. Für Linux Mint 22.x passt üblicherweise das Ubuntu-24.04-Paket, für Mint 21.x Ubuntu 22.04. LMDE benötigt das passende Debian-Paket. Das Paket durch Doppelklick mit der Paketverwaltung installieren. Die grafische VeraCrypt-Version erleichtert auch die spätere Wiederherstellung.
2. **MintTresor herunterladen:** Bei GitHub unter **Releases** das ZIP der aktuellen Vorabversion laden und entpacken.
3. Im entpackten Ordner mit der rechten Maustaste **„Im Terminal öffnen“** wählen und ausführen:

   ```bash
   bash install.sh
   ```

4. **Gastzugang einmalig als Administrator einrichten** (siehe unten), dann **MintTresor** im Linux-Anwendungsmenü starten. Fehlendes `python3-tk` installiert das Skript über die Paketverwaltung; dafür wird das Linux-Systempasswort benötigt. MintTresor selbst läuft als normaler Benutzer.

Voraussetzungen: Python 3.10 oder neuer, Tkinter, VeraCrypt unter `/usr/bin/veracrypt` mit `--stdin`-Unterstützung (geprüft mit 1.26.31), `xdg-open` und `sudo`.

## Einmalige Freigabe durch den Administrator

Gäste brauchen **nur ihr Tresorpasswort**. Ein Administrator führt im entpackten Projektordner einmalig aus:

```bash
sudo bash setup-guests.sh LINUX-BENUTZER
```

`LINUX-BENUTZER` ist das Linux-Konto, in dem Gäste die Anwendung starten, **nicht** ein in MintTresor registrierter Name. Im Terminal dieser Sitzung zeigt `whoami` den richtigen Namen. Bei einem gemeinsam genutzten Linux-Konto reicht eine Freigabe für dieses Konto. Beispielsweise: `sudo bash setup-guests.sh rotemagda`.

Dabei wird das Heimatverzeichnis dieses Linux-Kontos als Speicherbereich freigegeben. Für externe Laufwerke zusätzliche bestehende Ordner ausdrücklich angeben:

```bash
sudo bash setup-guests.sh gast /media/gast/Datentraeger/Tresore
```

Bei erneutem Aufruf werden die Zusatzordner durch die dann angegebenen ersetzt. Bereits eingerichtete weitere Linux-Konten bleiben erhalten. Danach `bash install.sh` im **Gastkonto** ausführen und MintTresor dort starten. Auch beim direkten Start von `app.py` gilt die Freigabe.

Die Einrichtung braucht einmal das Adminpasswort. **Beim Öffnen und Schließen erscheint kein Admin-Dialog mehr.** Fehlt die Freigabe oder wurde der Speicherort noch nicht zugelassen, gibt es eine Fehlermeldung ohne Passwortabfrage. MintTresor verwendet dafür ausschließlich `sudo -n`; keine automatische Rückkehr zur bisherigen Polkit-Abfrage.

**Update von 0.1.x:** Zuerst alle geöffneten Tresore mit der alten Version schließen, dann die Gastfreigabe einrichten und `bash install.sh` erneut ausführen. Bestehende Konten, Tresorpasswörter und Container bleiben erhalten. Nur die temporären Öffnungsordner wechseln nach `/run/minttresor`.

## In drei Schritten einrichten

1. **Einrichtung & Speicherort:** Einen Standardordner wählen, zum Beispiel `Dokumente/Tresore` oder einen Ordner auf einer externen Festplatte. Ohne Änderung gilt `~/Tresore`.
2. **Neuen Benutzer anlegen:** Benutzername, Passwort und Wiederholung eingeben. Die Größe ist auf 2 GB voreingestellt, wählbar sind 1–32 GiB. Der gesamte Container wird angelegt und verschlüsselt; dies dauert je nach Laufwerk einige Minuten. Das Passwort benötigt mindestens 12 Zeichen. Es gibt keine E-Mail, Cloud und Passwortzurücksetzung.
3. **Anmelden und Tresor öffnen:** Nach der einmaligen Gastfreigabe genügt das persönliche Tresorpasswort. Gäste erhalten keine allgemeinen Administratorrechte.

Der Standardordner gilt für **neu angelegte** Tresore. Bestehende Tresore werden beim Ändern dieser Einstellung nicht verschoben.

## Mit LibreOffice arbeiten

**Meinen Ordner öffnen** anklicken. Dateien hineinlegen oder in LibreOffice unter **Speichern unter** diesen geöffneten Ordner wählen. Auch Bilder, PDFs und andere Dateien funktionieren über den normalen Dateimanager.

Vor **Tresor schließen und abmelden** alle Dokumente speichern, Programme mit Dateien im Tresor und die zugehörigen Dateimanagerfenster schließen. Bei belegtem Tresor bricht MintTresor ab; es erzwingt kein Aushängen. Auch das Schließen des App-Fensters hängt den aktuell verwendeten Tresor zuerst aus. Nach einem Absturz können Tresore geöffnet bleiben: erneut anmelden und schließen. Die Startseite zeigt bekannte noch eingehängte Tresore an.

### Grenzen dieser ersten Version

- FAT als internes Dateisystem: **eine einzelne Datei muss kleiner als 4 GiB sein**. Geeignet für gewöhnliche Office-Dateien, weniger für große Videos oder virtuelle Maschinen. Containergröße 1–32 GiB, keine automatische Erweiterung.
- Lokale App-Konten innerhalb **eines Linux-Benutzerkontos**. Sie bieten individuelle verschlüsselte Ablagen, aber keine Trennung bereits geöffneter Tresore gegenüber anderen Programmen desselben Linux-Benutzers. Für unabhängige Personen mit unterschiedlichen Zugriffsrechten eigene Linux-Konten verwenden.
- Ein geöffneter Tresor ist für den berechtigten Linux-Benutzer lesbar. Administratoren, Schadsoftware und bereits entsperrte Sitzungen werden dadurch nicht abgewehrt.
- LibreOffice kann Sicherungen, Wiederherstellungsdaten und temporäre Dateien außerhalb des Tresors anlegen. Für vertrauliche Arbeit die Office-Einstellungen für Backups, AutoWiederherstellung und temporäre Pfade prüfen. MintTresor verwaltet diese Programmeinstellungen nicht.
- Keine gemeinsamen Tresore, Passwortänderung, Benutzerlöschung, automatische Sperre, Wiederherstellungsfunktion oder Verwaltung vorhandener fremder VeraCrypt-Container in der Oberfläche. VeraCrypt selbst kann die erzeugten Container öffnen.
- Bei Stromausfall und erzwungenem Beenden ist ein geöffneter Tresor nicht automatisch sicher geschlossen.

## Wo liegen die Daten?

| Inhalt | Ort |
| --- | --- |
| Verschlüsselte Container | Standardordner, jeweils `<zufällige Kennung>.hc` |
| Lokale Kontodaten und gespeicherte Pfade | `~/.local/share/minttresor/accounts.sqlite3` |
| Geöffnete Ordner | `/run/minttresor/<Linux-UID>/<Kennung>` |
| Anwendung | `~/.local/lib/minttresor` |

Die Kontodaten enthalten Benutzernamen und Pfade im Klartext sowie zufällig gesalzene scrypt-Prüfwerte, **keine Klartextpasswörter**. Verwendet werden scrypt N=131072, r=8, p=1 und 16-Byte-Salts. Das Tresorpasswort wird über eine Pipe an VeraCrypt übergeben, nicht als Kommandozeilenargument, Umgebungsvariable oder Datei. Python garantiert kein vollständiges Löschen von Passwörtern aus dem Arbeitsspeicher.

Die Verschlüsselung übernimmt VeraCrypt mit AES, SHA-512 und PIM 0. Zufallsquelle ist `/dev/urandom`. Zum Ein- und Aushängen wird ein fest installierter, eingeschränkter Systemhelfer verwendet. Die Oberfläche läuft als normaler Benutzer. Kein Server, keine Telemetrie und kein Hintergrunddienst. Nur die ausdrücklich angeklickte Downloadseite öffnet einen Browser.

### Umfang der Gastfreigabe

`setup-guests.sh` installiert den root-eigenen Helfer `/usr/local/libexec/minttresor-helper`, die Kontokonfiguration `/etc/minttresor/<UID>.json` und eine mit `visudo` geprüfte Regel `/etc/sudoers.d/minttresor-<UID>`. Freigegeben ist ausschließlich dieser Helfer ohne Kommandozeilenargumente. Es gibt keine pauschale Freigabe für VeraCrypt, Python oder eine Shell.

Der Helfer läuft mit isoliertem System-Python (`-I`) und importiert keinen Code aus dem beschreibbaren App-Ordner. Er prüft Linux-UID, freigegebene Speicherbereiche, Containerkennung und Dateibesitz. Symlinks, Hardlinks, Gerätedateien und frei vorgegebene Befehle sind ausgeschlossen. Er hält den geprüften Container über einen Dateideskriptor fest und verwendet feste Öffnungsordner unter einem root-eigenen Laufzeitverzeichnis. FAT wird mit `nodev,nosuid,noexec` und den Rechten des aufrufenden Kontos eingehängt. Es gibt kein erzwungenes Aushängen. Die Freigabe erlaubt die Verwendung des Helfers auch außerhalb der Oberfläche; zum Entschlüsseln wird weiterhin das Tresorpasswort benötigt.

## Backup und Wiederherstellung

1. Alle Tresore schließen.
2. Die `.hc`-Dateien und den gesamten Ordner `~/.local/share/minttresor` auf ein anderes Laufwerk sichern. Kontodaten ebenfalls vertraulich behandeln.
3. Passwörter getrennt und sicher aufbewahren. Ohne Passwort gibt es keinen Zugang.

Mit einer Containerdatei und dem zugehörigen Passwort kann der Tresor unabhängig von MintTresor in VeraCrypt geöffnet werden. Nach Verlust der Kontodaten gibt es in dieser Version keinen Importassistenten. Beim Wiederherstellen der Kontodaten müssen die gespeicherten absoluten Pfade stimmen; bei Umzug auf einen anderen Rechner ist die direkte Verwendung von VeraCrypt der einfachere Wiederherstellungsweg.

Ein fehlgeschlagener Erstellungsvorgang kann eine unvollständige `.hc`-Datei hinterlassen. Sie wird bewusst nicht automatisch gelöscht. Erst nach Prüfung manuell entfernen; bei fehlgeschlagener Kontoanlage wird kein Benutzer gespeichert.

## Entwicklung und Prüfungen

Ohne Installation im entpackten Projektordner starten:

```bash
python3 -m minttresor
```

Alternativ lässt sich die Datei direkt starten, auch mit einem absoluten Pfad:

```bash
python3 minttresor/app.py
```

`python3 -m minttresor.app` funktioniert ebenfalls. Die Befehle in einem Terminal der grafischen Linux-Sitzung ausführen. Falls die Oberfläche fehlt, `sudo apt install python3-tk` ausführen. Nach einem Update bei bereits installierter Anwendung `bash install.sh` erneut ausführen; die vorhandenen Konten und Tresore bleiben dabei erhalten.

In Version 0.1.0 fehlte in `app.py` der Aufruf des Startprogramms. Der Modulstart endete deshalb ohne Fenster. Beim direkten Dateistart scheiterte außerdem der relative Import. Beide Startwege sind ab 0.1.1 korrigiert.

Automatisierte Tests ohne VeraCrypt oder Root-Rechte:

```bash
python3 -m unittest discover -s tests -v
```

Abgedeckt sind Anmeldung, falsche Passwörter, doppelte Namen, Passwortvalidierung, Speicherpfade, Dateirechte, fehlgeschlagene Erstellung, Platzmangel und sicherheitsrelevante VeraCrypt-Aufrufe. Die Adaptertests simulieren Systemaufrufe. Zusätzlich wurde lokal ein echter 1-GiB-Container mit VeraCrypt 1.26.31 erstellt und die Oberfläche unter Xvfb durchlaufen.

Die Starttests prüfen alle drei Startwege auf ein tatsächlich sichtbares Fenster und laufende Ereignisverarbeitung. Dafür ist ein Desktop oder Xvfb nötig; ohne `DISPLAY` wird dieser Test übersprungen. In GitHub Actions läuft die vollständige Suite mit `xvfb-run -a python -m unittest discover -s tests -v`. Außerdem wird geprüft, dass beim Start ohne grafische Sitzung eine verständliche Fehlermeldung und ein Fehlerstatus zurückgegeben werden.

Vor Freigabe für wichtige Daten auf Linux Mint prüfen:

- Zwei Benutzer anlegen, falsches Passwort und getrennte Container prüfen.
- Nach einmaliger Einrichtung als Gast ohne sudo-Rechte anmelden: Öffnen und Schließen dürfen keine Adminabfrage zeigen. Ohne Freigabe muss eine verständliche Fehlermeldung erscheinen.
- Eine LibreOffice-Datei speichern, Tresor schließen, wieder öffnen und Inhalt prüfen.
- Bei noch geöffneten Dateien das Aushängen versuchen: bei Fehler muss der Tresor geöffnet bleiben.
- App bei geöffnetem Tresor schließen; danach mit VeraCrypt bzw. `findmnt` kontrollieren, dass er ausgehängt ist.
- Backup eines geschlossenen Containers in VeraCrypt öffnen.

Der zusätzliche CI-Job `guest-integration` installiert VeraCrypt mit fest geprüftem SHA-256, richtet ein Linux-Testkonto ohne allgemeine sudo-Rechte ein und führt einen echten Container-Roundtrip aus: falsches Passwort ablehnen, öffnen, Datei schreiben, schließen und erneut lesen. Die normalen Helfertests prüfen Pfadgrenzen, Symlinks, Hardlinks, Besitzerprüfung, feste Befehle und passwortlose Aufrufe ohne interaktiven Fallback.

## Deinstallation

Zuerst alle Tresore schließen. Anschließend `~/.local/lib/minttresor`, `~/.local/bin/minttresor` und `~/.local/share/applications/minttresor.desktop` entfernen. Container und Kontodaten bleiben absichtlich erhalten. Ein Administrator kann zusätzlich `/etc/sudoers.d/minttresor-<UID>` und `/etc/minttresor/<UID>.json` für das betroffene Linux-Konto entfernen. Wenn kein Konto den Helfer mehr verwendet, auch `/usr/local/libexec/minttresor-helper` entfernen. Nach Änderungen am Helfer die Gastfreigabe mit dem aktuellen Skript erneut installieren.

## Lizenz

GNU GPL Version 3, siehe [LICENSE](LICENSE). Eigenständiges Projekt; nicht mit VeraCrypt oder Linux Mint verbunden. VeraCrypt ist eine separat zu installierende Anwendung mit eigener Lizenz.
