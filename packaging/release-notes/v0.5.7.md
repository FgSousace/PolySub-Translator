## PolySub Translator 0.5.7

- polski lektor Chatterbox V3 na zgodnych Radeonach korzysta teraz z natywnego AMD ROCm zamiast
  wymuszonego CPU; RX 9070 XT jest automatycznie uruchamiany przez środowisko `gfx1201`;
- Chatterbox ponownie wykorzystuje zarządzane środowisko ROCm PolySub, doinstalowuje oficjalne
  `torchaudio` AMD i uruchamia model jako `cuda:0` po odizolowaniu właściwego indeksu HIP;
- worker lektora wykonuje automatyczny fallback do CPU, jeżeli model nie załaduje się na GPU albo
  konkretna operacja syntezy okaże się niezgodna z ROCm;
- środowisko lektora zapisuje użyty backend i indeks GPU, a test startowy wykonuje rzeczywiste
  obliczenie macierzowe na karcie przed rozpoczęciem syntezy;
- dodano brakujący pakiet `tiktoken` do lokalnego AI i paczki PyInstaller, naprawiając błąd
  ładowania mBART-50 „`tiktoken` is required to read a `tiktoken` file”;
- zachowano dotychczasowy tryb CPU dla komputerów bez zgodnego Radeona oraz bezpieczny powrót na
  CPU w razie problemu z akceleracją.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.7.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.7.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia, napisy i punkty wznowienia z wersji 0.5.6 pozostają zachowane.
Przy pierwszym uruchomieniu lektora na Radeonie PolySub może jednorazowo uzupełnić prywatne
środowisko ROCm o biblioteki audio Chatterbox.
