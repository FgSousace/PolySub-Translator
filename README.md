# PolySub Translator

**Context-aware multilingual subtitle translator with automatic language detection and
interactive review.**

PolySub tłumaczy kompletne pliki `.srt` albo sam przygotowuje napisy z filmu, zachowując numery
kwestii, timestampy i podstawowe formatowanie. Użytkownik wybiera silnik lokalny albo DeepL API
oraz jeden z dwóch trybów: szybkie tłumaczenie automatyczne lub tłumaczenie z ręczną weryfikacją
niejasnych fragmentów.

> Status: `v0.4.6-alpha` — trwałe napisy do TV, pełne użycie CPU i obsługa CUDA dla RTX 2080.

## Najważniejsze funkcje

- automatyczne wykrywanie języka całego pliku;
- dodatkowy import MP4/MKV/MOV/M4V/AVI/WebM bez usuwania obsługi SRT;
- wyciąganie pierwszej tekstowej ścieżki napisów z filmu;
- lokalne rozpoznawanie mowy przez Whisper, gdy film nie zawiera napisów;
- szybkie dołączanie gotowych napisów do filmu bez ponownego kodowania obrazu i dźwięku;
- wypalanie napisów na stałe w obrazie filmu z automatyczną akceleracją NVIDIA, Intel lub AMD;
- wybór dowolnego języka docelowego obsługiwanego przez wybrany silnik;
- lokalny model M2M100 lub DeepL API;
- dynamiczna lista rzeczywiście wykrytych procesorów i kart NVIDIA, AMD oraz Intel;
- tryb Auto wybierający najlepszy zgodny backend z bezpiecznym powrotem na CPU;
- wybór limitu 25%, 50%, 75% albo 100% logicznych wątków procesora;
- dwa paski postępu: wszystkie etapy operacji oraz dokładny postęp bieżącego etapu;
- dziennik wykonywanych czynności, czas pracy, procenty, liczba słów i czas nagrania;
- przewijany interfejs z przyciskami stale widocznymi na dole również na mniejszych ekranach;
- automatyczne sprawdzanie najnowszej wersji oraz ręczny przycisk pobrania aktualizacji;
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

## Automatyczne wykrywanie sprzętu

Lista urządzeń nie zawiera wpisanych na stałe modeli. Przy każdym uruchomieniu PolySub odczytuje
prawdziwą nazwę procesora i wszystkich kart graficznych obecnych w komputerze. Można wybrać:

- **Automatycznie — najlepsze dostępne urządzenie**;
- konkretną wykrytą kartę graficzną;
- konkretny procesor.

Program osobno sprawdza możliwość użycia urządzenia do M2M100 i do rozpoznawania mowy. Obsługuje
backendy udostępnione przez zainstalowane środowisko, między innymi CUDA, ROCm i Intel XPU. Jeśli
wybrane GPU albo sterownik nie obsługuje danej operacji, PolySub informuje o tym i proponuje lub
automatycznie wykonuje zadanie na CPU. Awaria GPU podczas ładowania albo obliczeń również nie
powoduje utraty całego zadania — program ponawia operację na procesorze.

W instalatorze Windows 0.4.6 znajduje się środowisko PyTorch CUDA 12.6 i cuDNN 9. Pakiet jest
przygotowany również dla kart NVIDIA z serii RTX 20, w tym RTX 2080; potrzebny jest aktualny
sterownik NVIDIA. Sprzęt AMD i Intel nadal jest wykrywany dynamicznie, a przy wypalaniu filmu
program potrafi użyć odpowiednio AMD AMF lub Intel Quick Sync, jeśli udostępnia je FFmpeg.

Sekcja **Wykorzystanie procesora** mapuje wybrany procent na prawdziwą liczbę logicznych wątków.
Ustawienie 100% przekazuje wszystkie dostępne wątki do PyTorch, Whispera i kodera CPU oraz zwiększa
bezpieczny rozmiar partii tłumaczenia. Nie zmienia parametrów jakości modelu. Wskaźnik Menedżera
zadań może chwilowo spaść podczas pobierania, odczytu plików albo etapów, których nie da się
równolegle rozłożyć, ale program nie wykonuje sztucznego obciążenia bez użytecznej pracy.

Kod projektu ma licencję MIT. Model `facebook/m2m100_418M` jest pobierany osobno z Hugging Face
i również jest udostępniany na licencji MIT. PolySub nie dołącza modelu ani kluczy API do repozytorium.

## Dodatkowa funkcja: film zamiast gotowego SRT

Dotychczasowy wybór `.srt` działa tak samo jak wcześniej. Dodatkowo można wskazać cały film:

1. PolySub próbuje wyciągnąć pierwszą tekstową ścieżkę napisów do `film.extracted.srt`.
2. Jeżeli film nie ma tekstowych napisów, Whisper słucha audio i tworzy `film.transcribed.srt`.
3. Program wykrywa język utworzonego tekstu.
4. Użytkownik wybiera język docelowy i zwykły tryb tłumaczenia.
5. Wynik zostaje zapisany obok filmu, np. jako `film.pl.srt`.
6. Na końcu można wybrać szybkie dodanie przełączanej ścieżki albo wypalenie napisów na stałe
   w obrazie filmu.

Do ekstrakcji używany jest FFmpeg dołączony do aplikacji, więc nie trzeba instalować go ręcznie.
Rozpoznawanie mowy działa lokalnie i oferuje wariant **small** (szybszy) oraz **medium**
(dokładniejszy, ustawiony domyślnie). Model Whisper pobiera się tylko przy pierwszym użyciu danego
wariantu i pozostaje w pamięci podręcznej Windows.

> Whisper rozpoznaje wypowiedziane słowa i ich czas, ale nie zna automatycznie imion ani płci
> rozmówców. Do takich przypadków nadal służą informacje o postaciach i tryb weryfikacji.

### Szybkie dołączanie napisów do filmu

PolySub nie przelicza ponownie obrazu ani dźwięku. FFmpeg kopiuje istniejące strumienie 1:1 i
dodaje przełączaną ścieżkę napisów. Dlatego karta graficzna nie jest potrzebna, jakość filmu się
nie zmienia, a operacja jest ograniczona głównie szybkością odczytu i zapisu dysku. Zależnie od
kontenera powstaje np. `film.pl.subtitled.mp4` albo `film.pl.subtitled.mkv`.

Napisy można włączać i wyłączać w odtwarzaczu. Nie są one wypalane na stałe w każdej klatce — takie
wypalanie jest dostępne jako drugi, osobny przycisk.

### Trwałe napisy na obrazie do telewizora

Przycisk **Wypal napisy na obrazie — TV** tworzy osobny plik, domyślnie
`film.pl.burned.mp4`. Tekst staje się częścią każdej klatki, więc będzie widoczny również w
odtwarzaczu lub telewizorze, który nie włącza dodatkowej ścieżki SRT.

Ta operacja musi ponownie zakodować obraz. PolySub najpierw sprawdza dostępne kodery i próbuje
NVIDIA NVENC, Intel Quick Sync albo AMD AMF zgodnie z wybranym sprzętem. Jeśli koder sprzętowy jest
niedostępny lub zgłosi błąd, program automatycznie przechodzi na wielowątkowy x264 na CPU. Obraz
jest zapisywany jako H.264 z formatem pikseli `yuv420p`, a dźwięk jako AAC dla szerokiej zgodności
z telewizorami. Pasek pokazuje przetworzony czas filmu, a oryginał nigdy nie jest nadpisywany.

PolySub pracuje na zwykłym lokalnym pliku wideo. Nie przechwytuje filmu bezpośrednio z aplikacji
HBO ani nie obchodzi zabezpieczeń DRM — najpierw trzeba mieć legalnie dostępny, niechroniony plik,
który można otworzyć w programie.

## Najprostsza instalacja na Windows

Nie musisz instalować Pythona, Gita ani wpisywać komend. Instalator pobiera się bezpośrednio z
zakładki **Releases** — bez szukania workflow i rozpakowywania dodatkowego artefaktu:

1. Otwórz [najnowszą wersję PolySub Translator](https://github.com/FgSousace/PolySub-Translator/releases/latest).
2. W sekcji **Assets** wybierz jeden z dwóch wariantów:
   - `PolySub-Translator-Setup.exe` — uruchamiasz bezpośrednio, bez rozpakowywania;
   - `PolySub-Translator-Installer.zip` — po rozpakowaniu zawiera instalator i `README.txt`.
3. Uruchom `PolySub-Translator-Setup.exe` i wybierz katalog instalacji.
4. Zostaw zaznaczoną opcję utworzenia ikony na pulpicie i kliknij **Instaluj**.
5. Po instalacji kreator pokaże krótką instrukcję oraz opcję uruchomienia programu.

Przy kolejnych uruchomieniach klikaj skrót **PolySub Translator** na pulpicie albo w menu Start.
Instalator działa dla bieżącego użytkownika i nie wymaga uprawnień administratora.

Wersja 0.4.6 jest większa od 0.4.5, ponieważ zawiera biblioteki CUDA i cuDNN potrzebne do działania
na zgodnych kartach NVIDIA bez ręcznego instalowania środowiska programistycznego CUDA. Starsze
wydania 0.4.5 oraz 0.4.4 pozostają dostępne na stronie Releases.

Po uruchomieniu program dyskretnie sprawdza najnowsze wydanie na GitHubie. Jeśli jest dostępna
nowsza wersja, pokaże jej numer i przycisk **Pobierz wersję…**. Instalator nigdy nie uruchamia się
sam — pobieranie rozpoczyna się dopiero po kliknięciu przycisku przez użytkownika.

> Windows może pokazać ostrzeżenie SmartScreen, ponieważ projekt nie ma jeszcze płatnego
> certyfikatu podpisu kodu. Wybierz **Więcej informacji → Uruchom mimo to**. Kod instalatora,
> automatyczny test instalacji i cały proces budowania są publiczne.

### Pierwsze tłumaczenie lokalne

Plik programu `.exe` zawiera silnik potrzebny do uruchomienia aplikacji, ale nie zawiera dużego
modelu językowego. Przy pierwszym użyciu opcji **Lokalny AI (M2M100)** aplikacja pobierze około 2 GB.
Może to potrwać kilka lub kilkanaście minut. Model zostaje w pamięci podręcznej Windows, więc przy
następnych uruchomieniach i tłumaczeniach nie jest pobierany ponownie.

### Wersja przenośna

Ta sama strona Releases zawiera `PolySub-Translator-Portable.zip`. Po rozpakowaniu można uruchomić
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
pip install "torch==2.12.1" --index-url https://download.pytorch.org/whl/cu126
pip install -e ".[local,fasttext,video]"
polysub-gui
```

Podczas pierwszego tłumaczenia zostanie pobrany model M2M100. Opcjonalny fastText zwiększa zakres
automatycznego rozpoznawania do 176 języków; bez niego działa lekki mechanizm zapasowy. Dodatek
`video` zawiera obsługę FFmpeg i lokalnej transkrypcji Whisper.

### Wariant DeepL API

```powershell
pip install -e ".[video,fasttext]"
polysub-gui
```

Klucz można wpisać bezpośrednio w aplikacji — jest używany tylko w bieżącej sesji i nie jest
zapisywany. Alternatywnie ustaw `DEEPL_API_KEY` jako zmienną środowiskową. Jeśli nie potrzebujesz
funkcji filmu, wystarczy podstawowe `pip install -e .`.

## Użycie

### Interfejs graficzny

```powershell
polysub-gui
```

1. Wybierz plik SRT albo film. Obsługa filmu jest funkcją dodatkową.
2. Dla filmu bez napisów wybierz szybszy lub dokładniejszy wariant Whisper.
3. Sprawdź automatycznie wykryty język i wybierz język docelowy.
4. Wybierz lokalny model albo DeepL API.
5. Wybierz **Tłumacz automatycznie** albo **Tłumacz z weryfikacją**.
6. Zostaw **Automatycznie** albo wybierz wykryty procesor lub kartę graficzną.
7. Wybierz limit wykorzystania procesora; domyślne 100% daje maksymalną wydajność.
8. Opcjonalnie wpisz informacje, np. `Anna — kobieta; Marek — mężczyzna`.
9. Rozpocznij tłumaczenie.
10. Dla filmu wybierz **Dodaj przełączaną ścieżkę — szybko** albo
    **Wypal napisy na obrazie — TV**.

Wynik tłumaczenia otrzyma nazwę w rodzaju `film.pl.srt`. W trybie weryfikacji zostanie najpierw
otwarty edytor. Przycisk dołączania uaktywnia się dopiero po zapisaniu gotowych napisów.

### Terminal

```powershell
# Lokalnie: automatyczne wykrycie angielskiego i tłumaczenie na polski
polysub film.srt --target pl --engine local --mode automatic

# DeepL i ręczna kontrola oznaczonych kwestii
$env:DEEPL_API_KEY = "TWÓJ_KLUCZ"
polysub film.srt --target pl --engine deepl --mode review

# Informacje o postaciach z pliku tekstowego
polysub film.srt --target pl --engine deepl --mode review --context-file postacie.txt

# Cały film: wyciągnięcie napisów lub transkrypcja audio, a następnie tłumaczenie
polysub film.mp4 --target pl --engine local --speech-model medium

# To samo oraz szybkie utworzenie filmu z przełączaną polską ścieżką napisów
polysub film.mp4 --target pl --engine local --attach-to-video

# Film z polskimi napisami wypalonymi na stałe i pełnym limitem CPU
polysub film.mp4 --target pl --engine local --burn-into-video --cpu-limit 100
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
- oryginalny film nigdy nie jest modyfikowany ani nadpisywany;
- napisy wyciągnięte lub rozpoznane z filmu są zapisywane w osobnym pliku roboczym `.srt`;
- film z dołączonymi napisami zawsze jest zapisywany jako osobny plik `.mp4` albo `.mkv`;
- film z napisami wypalonymi na obrazie również powstaje jako osobny plik;
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

GitHub Actions uruchamia lint i testy na Pythonie 3.10 oraz 3.12. Workflow Windows buduje
`Setup.exe`, instaluje go w czystym katalogu, sprawdza dołączony README, oba sposoby dodawania
napisów, ustawienia CPU, biblioteki CUDA/cuDNN, GUI, deinstalator i zawartość instalacyjnego ZIP-a,
a dopiero potem publikuje pliki w Releases.

## Struktura projektu

```text
src/polysub/
├── engines/       # DeepL i lokalny M2M100
├── cli.py         # interfejs terminalowy
├── gui.py         # aplikacja desktopowa
├── service.py     # tłumaczenie, kontekst, postęp i wznowienie
├── performance.py # limity CPU i konfiguracja bibliotek wielowątkowych
├── subtitles.py   # parser oraz walidacja SRT
├── video.py       # FFmpeg, wbudowane napisy i lokalna transkrypcja Whisper
├── detector.py    # automatyczne wykrywanie języka
└── review.py      # wyszukiwanie fragmentów wymagających kontroli
```

## Plan rozwoju

- obsługa VTT i ASS/SSA;
- tłumaczenie całych folderów;
- słownik nazw i terminów zapisywany per projekt;
- profile postaci przypisywane do konkretnych rozmówców;
- pamięć zaakceptowanych tłumaczeń;
- podpis cyfrowy instalatora Windows certyfikatem code-signing.

## Licencja

[MIT](LICENSE). Informacje o bibliotekach i plikach wykonywalnych dołączanych do wersji Windows są
zebrane w [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
