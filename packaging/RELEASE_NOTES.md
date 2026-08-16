## PolySub Translator 0.5.9

- lokalne tłumaczenie na GPU korzysta teraz z agresywnego, dynamicznego batchowania zamiast
  historycznego limitu 8 kwestii; po załadowaniu modelu PolySub sprawdza wolny VRAM i dobiera
  partię do 64 kwestii, z osobnym bezpiecznym limitem dla cięższych modeli;
- na urządzeniach CUDA/HIP modele próbują używać FP16, co ogranicza zużycie VRAM i zwiększa
  przepustowość; jeżeli konkretny model/operacja nie obsłuży FP16, program ponawia ją na GPU w FP32;
- po rzeczywistym błędzie braku VRAM program nie porzuca od razu karty i nie przełącza całej pracy
  na CPU — automatycznie zmniejsza partię o połowę, czyści cache akceleratora i ponawia tłumaczenie
  na tym samym GPU;
- szybki tryb automatyczny używa teraz greedy decoding (`num_beams=1`) i cache generacji zamiast
  beam search `2`, aby maksymalizować szybkość; tryb dokładny/weryfikacji zachowuje `num_beams=5`;
- log pokazuje aktywną precyzję GPU oraz dobrany rozmiar partii, dzięki czemu od razu widać,
  czy tłumaczenie faktycznie wykorzystuje akcelerator;
- zachowano obsługę Radeon ROCm, NVIDIA CUDA, CPU fallback i punkty wznowienia tłumaczenia.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.9.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.9.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia, napisy, środowisko AMD ROCm i punkty wznowienia z wersji 0.5.8
pozostają zachowane. Po aktualizacji wystarczy rozpocząć tłumaczenie ponownie; nowe ustawienia
wydajności są dobierane automatycznie.
