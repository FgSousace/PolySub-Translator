## PolySub Translator 0.5.6

- naprawiono błąd „Brakuje pakietów lokalnego AI” pojawiający się przy rozpoczęciu
  tłumaczenia pobranym modelem;
- środowisko AMD ROCm sprawdza teraz nie tylko obliczenia GPU, lecz także kompletność
  `transformers`, `sentencepiece`, `tokenizers`, `safetensors` i pozostałych bibliotek modeli;
- przerwana albo niepełna instalacja bibliotek AMD jest wykrywana i automatycznie naprawiana
  przed udostępnieniem Radeona do tłumaczenia;
- instalator zawiera pełne zależności lokalnego AI, a test wydania uruchamia dokładnie te klasy
  Transformers, których program używa po kliknięciu „Rozpocznij tłumaczenie”;
- komunikat błędu pokazuje od teraz nazwę brakującego składnika i prawidłową metodę naprawy;
  aplikacja EXE nie zaleca już instalowania pakietów do przypadkowego Pythona systemowego;
- podpis autora został ujednolicony do **FgSousace** w aplikacji, instalatorze, licencji,
  dokumentacji oraz opisach wszystkich wydań.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.6.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.6.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Pobrane modele, ustawienia oraz punkty wznowienia z wersji 0.5.5 pozostają zachowane.
