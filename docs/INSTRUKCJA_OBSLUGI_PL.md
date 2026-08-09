# PolySub Translator™ — instrukcja obsługi

**Wersja 0.4.9 • autor: fgSousace • użytek niekomercyjny**

Ta instrukcja prowadzi od wyboru pliku do gotowego filmu. Program nigdy nie
nadpisuje oryginału.

## 1. Instalacja

1. Pobierz `PolySub-Translator-Setup.exe` z oficjalnej strony GitHub Releases.
2. Uruchom instalator, wybierz folder i kliknij **Instaluj**.
3. Przy pierwszym uruchomieniu otwórz **Pobierz / usuń…** i pobierz co najmniej
   jeden model lokalny albo wybierz silnik DeepL i wpisz swój klucz API.

Instalator zawiera aplikację, FFmpeg i biblioteki NVIDIA. Nie zawiera wag 20
modeli tłumaczeniowych — każdy z nich jest opcjonalnym dodatkiem.

## 2. Obsługiwane pliki wejściowe

| Rodzaj | Rozszerzenia | Co robi program |
|---|---|---|
| Napisy | `.srt` | Wczytuje tekst, numery i timestampy. |
| Film | `.mp4`, `.m4v`, `.mkv`, `.mov`, `.avi`, `.webm` | Najpierw szuka tekstowej ścieżki napisów; gdy jej nie ma, uruchamia Whisper. |
| Dowolny plik | filtr `Wszystkie pliki (*.*)` | Plik jest widoczny w oknie wyboru; przed otwarciem program sprawdza, czy jego format jest obsługiwany. |

Pierwszy filtr okna wyboru pokazuje razem wszystkie obsługiwane napisy i filmy.
Po wyborze aplikacja opisuje typ, rozmiar, liczbę kwestii i liczbę słów.

## 3. Najprostsze tłumaczenie

1. Kliknij **Wyszukaj napisy w filmie lub wybierz plik**.
2. Wskaż SRT albo film. Po przygotowaniu pliku główny przycisk zmieni nazwę
   na **Rozpocznij tłumaczenie**.
3. Sprawdź wykryty język i wybierz język docelowy.
4. Wybierz silnik:
   - **Lokalny AI** — lista pokazuje tylko modele już pobrane i gotowe;
   - **DeepL API** — wpisz klucz, który nie jest zapisywany.
5. Zaznacz dokładnie jeden wymagany checkbox:
   - **Tłumacz automatycznie** — zapisuje gotowy SRT;
   - **Tłumacz z weryfikacją** — otwiera edytor problematycznych kwestii.
6. Zostaw urządzenie **Automatycznie** albo wybierz faktycznie gotowy CPU/GPU.
7. Wybierz profil czasu napisów i kliknij **Rozpocznij tłumaczenie**.

## 4. Anulowanie i wznowienie

Podczas tłumaczenia aktywuje się przycisk **Anuluj tłumaczenie**. Po kliknięciu
program kończy lub przerywa aktualną partię i nie rozpoczyna następnej. Gotowe
partie są zachowane w punkcie wznowienia. Ponowne uruchomienie tego samego zadania
kontynuuje od zapisanej kwestii.

## 5. Czytelność napisów

| Profil | Zachowanie |
|---|---|
| **Zalecane** | Minimum 1,5 s i do 17 znaków/s, gdy dialog daje wolne miejsce. |
| **Krótsze** | Minimum 1,0 s; dobre do szybkich scen. |
| **Dłuższe** | Minimum 2,0 s; wygodniejsze czytanie. |
| **Oryginalne** | Pozostawia czasy źródłowe 1:1. |
| **Własne** | Pozwala ustawić minimum 0,5–5 s i 8–30 znaków/s. |

Program nie przesuwa początku nowej wypowiedzi. Wydłuża stary napis wyłącznie
do bezpiecznej granicy przed następnym dialogiem, dlatego dwie postacie nie
zostają połączone, a napisy nie powstają jeden na drugim.

## 6. Modele AI

Główne pole **Model lokalnego AI** zawiera tylko modele, których pobieranie jest
ukończone. Pełny katalog 20 modeli znajduje się w **Pobierz / usuń…**. Menedżer
pokazuje rozmiar, wymagania, zakres języków, licencję i stan plików. Nieukończony
model nie może zostać przypadkowo uruchomiony.

## 7. NVIDIA, AMD i CPU

- **NVIDIA:** instalator zawiera PyTorch 2.11 z CUDA 12.8 i cuDNN 9. Jest to
  wariant dla kart GTX 10 oraz RTX 20/30/40/50 z aktualnym sterownikiem.
- **AMD Radeon:** Windows wymaga osobnego, niezgodnego z CUDA wariantu PyTorch.
  Kliknij **Skonfiguruj / sprawdź AMD**. Program utworzy odizolowane środowisko
  Python 3.12, pobierze oficjalne AMD ROCm 7.2.1 i wykona prawdziwy test GPU.
- **CPU Intel/AMD:** zawsze dostępna droga awaryjna. Ustawienie 100% przekazuje
  modelowi wszystkie logiczne wątki, ale nie obniża jakości.

Oficjalna obsługa AMD ROCm 7.2.1 na Windows obejmuje obecnie: RX 9070, RX 9070
XT, AI PRO R9700, RX 9060 XT, RX 7900 XTX, PRO W7900, PRO W7900 Dual Slot oraz
RX 7700. Wymagane są Windows 11, Python 3.12 i sterownik Adrenalin 26.2.2.
Starszy lub niewymieniony Radeon nadal działa przez CPU; sama nazwa karty nie
jest traktowana jako dowód gotowej akceleracji.

## 8. Gotowy film

Po przetłumaczeniu napisów filmu możesz wybrać:

- **Dodaj przełączaną ścieżkę — szybko** — bez ponownego kodowania; ścieżkę
  czasem trzeba włączyć w VLC lub telewizorze;
- **Wypal napisy na obrazie — TV** — napisy są częścią każdej klatki i zawsze
  widoczne, ale film musi zostać ponownie zakodowany.

## 9. Najczęstsze problemy

- **Nie widzę modelu w głównym oknie:** pobieranie nie jest ukończone; otwórz
  menedżer i wybierz **Wznów/Pobierz**.
- **GPU jest na liście, ale program wybiera CPU:** karta została wykryta fizycznie,
  lecz backend albo sterownik nie przeszedł testu. Opis pod listą podaje powód.
- **RX 9070 XT używa CPU:** uruchom konfigurator AMD i upewnij się, że masz
  Windows 11, Python 3.12 oraz wskazany sterownik AMD.
- **Napisy zniknęły w VLC:** włącz ścieżkę w menu **Napisy** albo użyj
  opcji trwałego wypalenia.
- **Przycisk tłumaczenia nie startuje:** wybierz plik, gotowy model/język i zaznacz
  jeden checkbox trybu.

## 10. Autor i licencja

PolySub Translator™ został stworzony przez **fgSousace**.

Required Notice: PolySub Translator™ — Copyright © 2026 fgSousace. Licensed for noncommercial use only.

Od wersji 0.4.9 oryginalny kod aplikacji jest dostępny na warunkach PolyForm
Noncommercial License 1.0.0. Dozwolony jest użytek osobisty i inny niekomercyjny.
Użytek zarobkowy/komercyjny wymaga osobnej pisemnej zgody fgSousace. Biblioteki
zewnętrzne i pobierane modele zachowują swoje osobne licencje.
