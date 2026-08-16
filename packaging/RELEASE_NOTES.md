## PolySub Translator 0.5.8

- naprawiono instalację Chatterbox na Radeonach z ROCm 7.14: oficjalny stos AMD dla Windows
  używa PyTorch `2.12.0+rocm7.14.0` razem z `torchaudio 2.11.0+rocm7.14.0`;
- usunięto błędną próbę instalacji nieistniejącego pakietu `torchaudio 2.12.0+rocm7.14.0`, która
  powodowała komunikat `No matching distribution found` i przełączenie lektora na CPU;
- podniesiono schemat środowiska lektora, aby wcześniejsza nieudana konfiguracja została
  automatycznie ponowiona z poprawnym pakietem audio;
- manifest ROCm sprawdza teraz także wersję `torchaudio`, a test startowy weryfikuje jej obecność
  przed uruchomieniem syntezy na GPU;
- zachowano PyTorch ROCm 2.12.0, obsługę RX 9070 XT (`gfx1201`) oraz automatyczny fallback do CPU.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.8.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.8.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia, napisy i punkty wznowienia z wersji 0.5.7 pozostają zachowane.
Po aktualizacji wystarczy ponownie uruchomić przygotowanie lektora — PolySub doinstaluje poprawne
`torchaudio 2.11.0+rocm7.14.0` do zarządzanego środowiska AMD i ponowi test GPU.
