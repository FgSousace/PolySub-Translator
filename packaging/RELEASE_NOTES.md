## PolySub Translator 0.6.0

- polski lektor Chatterbox pokazuje teraz jawnie, czy synteza działa na GPU Radeon ROCm, czy na CPU;
- aplikacja odczytuje z workera aktywne i żądane urządzenie, backend oraz dokładny powód fallbacku,
  zamiast ignorować te informacje;
- gdy poprawnie wybrany runtime ROCm spadnie na CPU podczas ładowania modelu albo przy dowolnej
  kwestii, PolySub natychmiast przerywa render i pokazuje powód błędu GPU — nie kontynuuje już
  po cichu wielogodzinnej syntezy na procesorze;
- status każdej kwestii pokazuje teraz `GPU` albo `CPU`, a komunikat startowy na Radeonie zawiera
  nazwę aktywnego urządzenia i wersję ROCm;
- usunięto mylący komunikat o „wątkach CPU” podczas uruchamiania Chatterbox na Radeonie;
- komputery bez zgodnego Radeona nadal mogą korzystać z normalnego trybu CPU; rygorystyczne
  zatrzymanie po fallbacku dotyczy tylko sesji, które zostały uruchomione jako ROCm.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.6.0.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.6.0.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia, napisy, środowisko AMD ROCm i punkty wznowienia z wersji 0.5.9
pozostają zachowane. Ta wersja przede wszystkim ujawnia realny backend Chatterboxa i zatrzymuje
pracę od razu, jeśli Radeon przestanie wykonywać syntezę, dzięki czemu błąd GPU można naprawić na
podstawie konkretnego komunikatu zamiast czekać godzinami na ukryty fallback CPU.
