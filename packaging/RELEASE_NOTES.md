## PolySub Translator 0.6.1

- Whisper może teraz używać kart Radeon i Intel w Windows przez DirectML/DirectX 12; NVIDIA
  zachowuje dotychczasowy, szybszy backend CUDA, a przy błędzie DirectML dostępny jest bezpieczny
  powrót na CPU;
- DirectML działa w prywatnym Pythonie i nie nadpisuje bibliotek CUDA ani AMD ROCm aplikacji;
- worker Whispera używa zgodnego trybu FP32 i najpierw próbuje zachować dokładne znaczniki słów;
- Chatterbox otrzymał oficjalną szybką ścieżkę V3, która nie kopiuje uwagi z GPU do CPU po każdym
  tokenie;
- narrator odczytuje całkowity i wolny VRAM; na RX 9070 XT 16 GB uruchamia dwa trwałe workery,
  jeśli pamięć faktycznie na to pozwala, a na mniejszych kartach pozostaje przy jednym;
- dodano cztery profile tempa lektora: Bardzo spokojny, Spokojny (domyślny), Naturalny oraz
  Ścisłe dopasowanie; domyślny profil nie przekracza 1,08× i wykorzystuje przerwy między napisami;
- nowoczesny interfejs został przebudowany na pięć prostych ekranów: plik, tłumaczenie,
  czytelność, lektor i eksport; sprzęt oraz pozostałe opcje są w ustawieniach zaawansowanych;
- dotychczasowy przewijany interfejs pozostaje dostępny jako wariant Klasyczny.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.6.1.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.6.1.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia, napisy, środowiska AMD ROCm i punkty wznowienia pozostają zachowane.
Przy pierwszym użyciu nowego lektora PolySub jednorazowo zaktualizuje wyłącznie kod prywatnego
środowiska Chatterbox; wielogigabajtowe wagi V3 nie będą pobierane ponownie. DirectML używa
osobnego formatu modelu Whisper, więc jego wagę pobiera jednorazowo do prywatnego cache Windows.
