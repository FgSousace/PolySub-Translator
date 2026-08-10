## PolySub Translator 0.5.3

- naprawiono automatyczne przygotowanie AMD ROCm na Windows, które mogło kończyć się błędem
  `BackendUnavailable: Cannot import 'setuptools.build_meta'`;
- prywatne środowisko AMD instaluje teraz binarne pakiety `setuptools` i `wheel` przed
  rozwiązaniem zależności oficjalnego PyTorch ROCm 7.14;
- źródłowy metapakiet `rocm-7.14.0.tar.gz` korzysta z przygotowanego backendu zamiast wadliwego
  tymczasowego środowiska pip;
- przerwana instalacja AMD jest automatycznie kontynuowana przy następnym
  uruchomieniu albo po użyciu przycisku **Odśwież listę sprzętu**;
- RX 9070 XT nadal jest izolowany od zintegrowanego Radeona przez `HIP_VISIBLE_DEVICES`, a GPU
  zostaje oznaczone jako gotowe dopiero po rzeczywistym teście obliczeń;
- wyłączono kompresję UPX, a pobierany i uruchamiany `get-pip.py` zastąpiono oficjalnym kołem
  `pip` 25.2 sprawdzanym przez przypiętą sumę SHA-256;
- gotowy plik aplikacji oraz Setup przechodzą skan Microsoft Defender przed publikacją, jeżeli
  Defender jest dostępny na runnerze Windows;
- szablon GitHub Releases opisuje od teraz wyłącznie bieżącą wersję, bez kopiowania historii
  wszystkich poprzednich wydań;
- pliki mają jednoznaczne nazwy `PolySub-Translator-Setup-0.5.3.exe` oraz
  `PolySub-Translator-Installer-0.5.3.zip`.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.3.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.3.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Nie pobieraj automatycznie dodanych przez GitHub plików `Source code`, jeżeli chcesz tylko
zainstalować program. Nowa paczka portable nie jest publikowana.
