# PolySub Translator

**Context-aware multilingual subtitle translator with automatic language detection and
interactive review.**

PolySub tłumaczy kompletne pliki `.srt`, zachowując numery kwestii, timestampy i podstawowe
formatowanie. Użytkownik wybiera silnik lokalny albo DeepL API oraz jeden z dwóch trybów:
szybkie tłumaczenie automatyczne lub tłumaczenie z ręczną weryfikacją niejasnych fragmentów.

> Status: `v0.2.0-alpha` — aplikacja SRT z automatycznym instalatorem Windows.

## Najważniejsze funkcje

- automatyczne wykrywanie języka całego pliku;
- wybór dowolnego języka docelowego obsługiwanego przez wybrany silnik;
- lokalny model M2M100 lub DeepL API;
- licznik `Przetłumaczono 1 428 z 9 732 słów` zamiast samego procentu;
- nienaruszalne identyfikatory i timestampy;
- zapis awaryjny i automatyczne wznowienie przerwanego zadania;
- informacje o postaciach, płci, relacjach i stylu jako dodatkowy kontekst;
- edytor pokazujący oryginał i tłumaczenie obok siebie;
- oznaczanie kwestii z możliwie niejednoznaczną płcią lub odmianą;
- interfejs graficzny oraz wersja terminalowa;
- oryginalny plik nigdy nie jest nadpisywany.

## Tryby tłumaczenia

| Tryb | Działanie | Najlepsze zastosowanie |
|---|---|---|
| **Tłumacz automatycznie** | Tłumaczy cały plik bez zatrzymywania i od razu zapisuje wynik. | Szybki rezultat i napisy do późniejszej korekty. |
| **Tłumacz z weryfikacją** | Używa dodatkowego kontekstu i otwiera edytor z oznaczonymi kwestiami. | Dialogi wymagające poprawnej płci, odmiany i spójności postaci. |

## Silniki

| Silnik | Internet | Klucz | Obsługa języków | Uwagi |
|---|---:|---:|---|---|
| **M2M100 418M** | tylko przy pierwszym pobraniu | nie | około 100 | Darmowy, lokalny model; pobiera około 2 GB. |
| **DeepL API** | tak | tak | zgodnie z aktualną ofertą API | Lepszy kontekst i jakość dla obsługiwanych par językowych. |

Kod projektu ma licencję MIT. Model `facebook/m2m100_418M` jest pobierany osobno z Hugging Face
i również jest udostępniany na licencji MIT. PolySub nie dołącza modelu ani kluczy API do repozytorium.

## Najprostsza instalacja na Windows

Nie musisz instalować Pythona ani wpisywać komend. Gotowy pakiet Windows powstaje automatycznie
w zakładce **Actions → Build Windows Installer**:

1. Otwórz ostatni udany build oznaczony zielonym znakiem.
2. Pobierz na dole artefakt `PolySub-Translator-Windows`.
3. Rozpakuj pobrany ZIP i uruchom `PolySub-Translator-Setup.exe`.
4. Zostaw zaznaczoną opcję utworzenia ikony na pulpicie i zakończ instalację.

Przy kolejnych uruchomieniach klikaj skrót **PolySub Translator** na pulpicie albo w menu Start.
Instalator działa dla bieżącego użytkownika i nie wymaga uprawnień administratora.

> Windows może przy pierwszym uruchomieniu pokazać ostrzeżenie SmartScreen, ponieważ projekt nie ma
> jeszcze płatnego certyfikatu podpisu kodu. Kod instalatora i cały proces budowania są publiczne.

### Pierwsze tłumaczenie lokalne

Plik programu `.exe` zawiera silnik potrzebny do uruchomienia aplikacji, ale nie zawiera dużego
modelu językowego. Przy pierwszym użyciu opcji **Lokalny AI (M2M100)** aplikacja pobierze około 2 GB.
Może to potrwać kilka lub kilkanaście minut. Model zostaje w pamięci podręcznej Windows, więc przy
następnych uruchomieniach i tłumaczeniach nie jest pobierany ponownie.

### Wersja przenośna

Ten sam artefakt zawiera `PolySub-Translator-Portable.zip`. Po rozpakowaniu można uruchomić
`PolySubTranslator\PolySubTranslator.exe` bez instalacji, ale wersja przenośna nie tworzy skrótu.

## Instalacja z kodu źródłowego na Windows

Wymagany jest Python 3.10 lub nowszy.

```powershell
git clone https://github.com/FgSousace/PolySub-Translator.git
cd PolySub-Translator
py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Wariant lokalny

```powershell
pip install -e ".[local,fasttext]"
polysub-gui
```

Podczas pierwszego tłumaczenia zostanie pobrany model M2M100. Opcjonalny fastText zwiększa zakres
automatycznego rozpoznawania do 176 języków; bez niego działa lekki mechanizm zapasowy.

### Wariant DeepL API

```powershell
pip install -e .
polysub-gui
```

Klucz można wpisać bezpośrednio w aplikacji — jest używany tylko w bieżącej sesji i nie jest
zapisywany. Alternatywnie ustaw `DEEPL_API_KEY` jako zmienną środowiskową.

## Użycie

### Interfejs graficzny

```powershell
polysub-gui
```

1. Wybierz plik SRT.
2. Sprawdź automatycznie wykryty język i wybierz język docelowy.
3. Wybierz lokalny model albo DeepL API.
4. Wybierz **Tłumacz automatycznie** albo **Tłumacz z weryfikacją**.
5. Opcjonalnie wpisz informacje, np. `Anna — kobieta; Marek — mężczyzna`.
6. Rozpocznij tłumaczenie.

Wynik otrzyma nazwę w rodzaju `film.pl.srt`. W trybie weryfikacji zostanie najpierw otwarty edytor.

### Terminal

```powershell
# Lokalnie: automatyczne wykrycie angielskiego i tłumaczenie na polski
polysub film.srt --target pl --engine local --mode automatic

# DeepL i ręczna kontrola oznaczonych kwestii
$env:DEEPL_API_KEY = "TWÓJ_KLUCZ"
polysub film.srt --target pl --engine deepl --mode review

# Informacje o postaciach z pliku tekstowego
polysub film.srt --target pl --engine deepl --mode review --context-file postacie.txt
```

Uruchomienie `polysub` bez parametrów otwiera GUI.

## Dokładność płci i odmiany

Samo zdanie `I'm ready` nie zawiera informacji, czy mówi kobieta, czy mężczyzna. Żaden translator
nie może zawsze odtworzyć tej informacji, jeżeli nie występuje ona w napisach albo kontekście.
Dlatego PolySub:

1. analizuje sąsiednie kwestie;
2. pozwala podać profile postaci;
3. oznacza potencjalnie niejednoznaczne fragmenty;
4. umożliwia poprawienie każdej kwestii przed zapisaniem.

Tryb weryfikacji zwiększa kontrolę nad jakością, ale nie udaje stuprocentowej pewności tam, gdzie
tekst źródłowy nie zawiera wymaganej informacji.

## Bezpieczeństwo pliku

- oryginalny plik nie jest modyfikowany;
- struktura jest sprawdzana przed zapisem;
- niedokończone zadanie trafia do pliku `*.srt.polysub.json`;
- plik awaryjny nie zawiera klucza API i jest usuwany po ukończeniu tłumaczenia;
- `.env` oraz pliki awaryjne są ignorowane przez Git.

## Testy i jakość kodu

```powershell
pip install -e ".[dev]"
ruff check .
pytest
```

GitHub Actions uruchamia lint i testy na Pythonie 3.10 oraz 3.12. Osobny workflow Windows tworzy
gotowy instalator `.exe` oraz wersję przenośną `.zip` przy zmianach w aplikacji.

## Struktura projektu

```text
src/polysub/
├── engines/       # DeepL i lokalny M2M100
├── cli.py         # interfejs terminalowy
├── gui.py         # aplikacja desktopowa
├── service.py     # tłumaczenie, kontekst, postęp i wznowienie
├── subtitles.py   # parser oraz walidacja SRT
├── detector.py    # automatyczne wykrywanie języka
└── review.py      # wyszukiwanie fragmentów wymagających kontroli
```

## Plan rozwoju

- obsługa VTT i ASS/SSA;
- tłumaczenie całych folderów;
- słownik nazw i terminów zapisywany per projekt;
- profile postaci przypisywane do konkretnych rozmówców;
- pamięć zaakceptowanych tłumaczeń;
- dołączanie napisów do MKV/MP4 przez FFmpeg;
- podpis cyfrowy instalatora Windows certyfikatem code-signing.

## Licencja

[MIT](LICENSE)
