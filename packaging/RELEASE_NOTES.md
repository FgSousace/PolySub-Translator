## Nowości w wersji 0.4.5

- dynamiczna lista pokazuje prawdziwy model procesora i wszystkie wykryte karty graficzne;
- tryb **Automatycznie** osobno wybiera najlepsze urządzenie do tłumaczenia i rozpoznawania mowy;
- można ręcznie wskazać konkretny CPU albo GPU, również w komputerze z kilkoma kartami;
- program wykrywa dostępne backendy CUDA, ROCm oraz Intel XPU zamiast zgadywać po nazwie sprzętu;
- przy braku zgodnego backendu wyświetla jasną informację i bezpiecznie przechodzi na CPU;
- błąd GPU podczas ładowania lub obliczeń powoduje automatyczne ponowienie zadania na procesorze;
- przycisk **Odśwież listę sprzętu** ponownie sprawdza urządzenia bez restartowania programu.

Wydanie 0.4.4 pozostaje dostępne osobno w historii GitHub Releases.

## Wcześniej dodane w wersji 0.4.4

- program automatycznie sprawdza w tle najnowsze wydanie po uruchomieniu;
- przycisk **Sprawdź aktualizacje** pozwala powtórzyć sprawdzenie w dowolnym momencie;
- gdy pojawi się nowsza wersja, program pokazuje numer zainstalowanej i najnowszej wersji;
- przycisk pobierania prowadzi bezpośrednio do oficjalnego instalatora z GitHub Releases;
- aktualizacje nie instalują się ani nie uruchamiają bez zgody użytkownika.

## Wcześniej dodane w wersji 0.4.3

- dwa poziome paski: liczba ukończonych etapów i postęp bieżącej czynności;
- dziennik pokazujący ładowanie modeli, wykrywanie języka, tłumaczenie, kontrolę i zapis;
- licznik czasu z komunikatem potwierdzającym, że program nadal działa;
- przewijane ustawienia oraz przyciski przypięte na dole, aby nie znikały na mniejszych ekranach;
- lepsze skalowanie DPI w Windows.

## Dwa wygodne sposoby instalacji na Windows

### Najszybciej

1. Pobierz `PolySub-Translator-Setup.exe`.
2. Uruchom plik, wybierz katalog i kliknij **Instaluj**.

### Instalator w ZIP-ie

1. Pobierz `PolySub-Translator-Installer.zip`.
2. Rozpakuj go — w środku są `PolySub-Translator-Setup.exe` i `README.txt`.
3. Uruchom instalator.

Po instalacji kreator pokazuje krótką instrukcję i pozwala od razu uruchomić program. Skrót
**PolySub Translator** jest dostępny na pulpicie oraz w menu Start.

Nie pobieraj plików `Source code`, jeżeli chcesz po prostu uruchomić program.

Windows SmartScreen może wyświetlić ostrzeżenie, ponieważ instalator nie ma jeszcze płatnego
certyfikatu podpisu cyfrowego. W takim przypadku wybierz **Więcej informacji → Uruchom mimo to**.

Instalator nie wymaga Pythona, Gita ani uprawnień administratora. Wersja przenośna jest dostępna
w pliku `PolySub-Translator-Portable.zip`.
