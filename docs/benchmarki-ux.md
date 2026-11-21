# Benchmarki UX i funkcjonalne (sektor C — GUI)

Cel: oprzeć GUI na oficjalnych, publicznie zaakceptowanych wzorcach, żeby jury nie miało uwag co do użyteczności, dostępności i spójności z administracją publiczną.
Stan na 2026-11-21. Każde źródło oznaczono: **[odczytane]** = treść strony faktycznie przeczytana; **[niezweryfikowane]** = tylko wynik wyszukiwarki lub strona się nie wczytała.

## 1. Źródła

| Źródło | Status | Do czego służy w projekcie |
|---|---|---|
| Design System Gov.pl (KPRM), https://aplikacje.gov.pl/app/govpl-front-styleguide/ (v1.0 beta) | [odczytane: Uploader, Stepper, Komunikat, Input, Przycisk, Loader, Kolory, Typografia, Dostępność, Język] | **Główny wzorzec wizualny i komponentowy** |
| GOV.UK Design System: File upload, Error summary, Check answers, Confirmation pages | [odczytane] | Zachowanie błędów, podsumowanie, potwierdzenie |
| MoJ Multi file upload, https://design-patterns.service.justice.gov.uk/components/multi-file-upload | [odczytane] | Wiele plików naraz, błędy per plik |
| USWDS: File input, Alert, Table, Step indicator | [odczytane; Table częściowo] | Dostępność czytników ekranu, role ARIA |
| Informacja Prezesa KIO z 13.03.2026 + „Podstawowe informacje” UZP (gov.pl/web/uzp) | [odczytane] | Reguły domenowe: formaty, nazwy plików, załączniki, wpis |
| ezamowienia.gov.pl (strona główna) | [odczytane tylko strona główna] | Pasek dostępności, okno wygaśnięcia sesji, stopka |
| orzeczenia.uzp.gov.pl (strona główna) | [odczytane tylko strona główna] | Wyszukiwarka z historią, zwijane zaawansowane filtry |
| prs.ms.gov.pl, wyszukiwarka-krs.ms.gov.pl | [niezweryfikowane] przerwa techniczna / pusta strona (JS) | Nie użyte jako wzorzec |
| Azure Document Intelligence, Google Document AI HITL | [odczytane, ale bez wzorców UX weryfikacji; HITL Google wycofane 16.01.2024] | Brak. Wzorzec „PDF obok pól” to nasza propozycja, nie benchmark |

## 2. Design System Gov.pl — wartości do przejęcia (odczytane)

**Kolory:** Dark blue `#0052a5` (akcja główna), Light blue `#006cd7`, Black `#1b1b1b`, Gray 1 `#656565`, Gray 2 `#767676`, Gray 3 `#b7b7b7`, Gray 3a `#dadada`, Gray 4 `#f1f1f1`, White `#ffffff`. Dodatkowe: Navy `#00468d`, Dark red `#a7162d`, Light red `#d5233f`, Yellow `#eba828`, Yellow bright `#ffc605`, Green `#598527`.
**Typografia:** Open Sans (400/600/700 + kursywy; licencja Apache 2.0). Skala 40/32/28/24/20/16/14/12 px, bazowo 16 px = 1 em. Interlinia 1,5 dla akapitów i 1,25 dla nagłówków. Odstęp między akapitami = 2× rozmiar fontu. Tekst wyrównany do lewej, **bez justowania**. Skalowanie fluidalne od 360 px.
**Język:** prosty polski (poziom 8–9 lat nauki), zwrot do użytkownika w 2. os. („Wpisz”, „Sprawdź”), bez strony biernej, bez form rodzajowych, linki opisowe (nigdy „tutaj”), przy plikach do pobrania podaj format i rozmiar.

### Uploader (kluczowy dla nas)
- Etykieta pola, ramka, instrukcja **„Przeciągnij i upuść pliki na to pole albo załaduj z dysku”**, przycisk **„Dodaj plik”** (nie zmieniać tych tekstów), informacja o formatach i maksymalnym rozmiarze, opcjonalnie liczba plików.
- Lista podglądu: nazwa pliku, ikona typu, rozmiar, krzyżyk do usunięcia, separator. Z progress barem i procentami, gdy plik idzie od razu na serwer. Bez progress bara, gdy plik trafia tylko do pamięci przeglądarki do czasu „Wyślij”.
- Stany: Enabled, Disabled, Error (z komunikatem walidacyjnym).
- Przy osiągnięciu limitu liczby plików pole uploadera znika, zostaje sama lista.
- W jednym uploaderze nie mieszać ikon ze miniaturami.

### Komunikat (alert)
Typy: Sukces, Ostrzeżenie, Błąd, Informacja. Zawsze z piktogramem. **Inline w treści strony, nigdy pływający.** W formularzach równolegle z walidacją przy polu. Błąd ma mówić: gdzie, co jest nie tak, co zrobić („Błąd w polu PESEL. Sprawdź poprawność wprowadzonych danych”). Opcjonalny odnośnik „Przejdź do pola”.

### Stepper
3–5 kroków (max 6–7), pod nagłówkiem strony, każdy krok to osobna podstrona. Stany: Active, Next enabled, Next disabled, Finished, Error. W wariancie liniowym cofać się można tylko do ukończonych kroków.

### Przyciski
Jeden Primary na stronę. Secondary = akcje poboczne, Tertiary = Anuluj/Odrzuć, **Red** tylko dla nieodwracalnych (np. Usuń). Przyciski nie służą do nawigacji (do tego linki). Stany: Enabled, Hover, Focus, Disabled.

### Loader
Spinner dla operacji 1–5 s (treść pod nim rozjaśniona „mgiełką”). **Progress bar dla operacji >5 s**, z krótkim opisem; czas podawać tylko, gdy da się go realnie określić.

### Input
Etykieta nad polem, placeholder z formatem („Wpisz numer telefonu w formacie +48 XXX XXX XXX”), dodatkowe wyjaśnienia w tooltipie. Stany: Enabled, Disabled, Active, Filled, Error, Focus.

## 3. Wzorce z GOV.UK / MoJ / USWDS (odczytane)

1. **Error summary** na górze strony przy każdym błędzie, nawet jednym: nagłówek „There is a problem”, każdy błąd linkuje do pola, treść **identyczna** z komunikatem przy polu, fokus klawiatury przenoszony na podsumowanie, `role="alert"`, prefiks „Error:” w `<title>`.
2. **Komunikaty błędów uploadu per przypadek:** brak pliku, zły typ („must be a …”), za duży („must be smaller than …”), pusty, zabezpieczony hasłem, wirus, błąd wysyłki z „spróbuj ponownie”, przekroczony limit liczby plików. Dla nas po polsku, np. „Wybrany plik jest pusty”, „Wybrany plik jest chroniony hasłem”.
3. **Wiele plików (MoJ):** każdy plik wysyła się od razu, wiersz ze statusem (zielony + ptaszek / czerwony + ostrzeżenie), postęp w %, błędy **per plik z nazwą pliku** w error summary. Zastrzeżenie MoJ: wiele plików naraz jest bardziej podatne na błędy, a komponent jest oznaczony „to be reviewed”. U nas uzasadnione, bo sprawa to 3 dokumenty naraz.
4. **Check answers:** strona kontrolna przed zatwierdzeniem, tytuł mówi, co zrobić, link „Zmień” z ukrytym tekstem opisującym pole, niewypełnione opcjonalne pole = „Nie podano”, po zmianie powrót do podsumowania, przycisk opisuje akcję („Zatwierdź i pobierz JSON”).
5. **Strona potwierdzenia:** numer referencyjny, co dalej, możliwość zapisu rekordu (PDF/JSON), kontrast elementów interaktywnych ≥ 3:1.
6. **Dostępność plików (USWDS):** czytnik ogłasza liczbę i nazwy wybranych plików oraz błąd typu pliku; `accept` + hint z `aria-describedby`; działa bez JS (progressive enhancement). Znany słaby punkt: jeden przycisk opisujący jednocześnie „przeciągnij” i „wybierz z dysku” myli czytniki. Rozdzielić.
7. **Alert ARIA (USWDS):** `role="alert"` dla błędów, `role="status"` dla sukcesu. Nie polegać wyłącznie na kolorze.
8. **Tabele (USWDS, część niezweryfikowana):** `<caption>`, `scope` na nagłówkach, `aria-sort`, przewijany kontener z `tabindex="0"`.

## 4. Wzorce z polskich serwisów (tylko strony główne)

- **ezamowienia.gov.pl:** pasek w nagłówku z przełącznikiem kontrastu i trzema rozmiarami czcionki „A A A”, logo w wersji kontrastowej, breadcrumb „Jesteś tutaj:”, okno **„Twoja sesja wygaśnie za… Czy chcesz kontynuować?”**, stopka z Regulaminem, Polityką prywatności i Deklaracją dostępności.
- **orzeczenia.uzp.gov.pl:** podpowiedzi „Ostatnie / Popularne wyszukiwania”, zwinięte „Zaawansowane wyszukiwanie”. Antywzorzec: Deklaracja dostępności jako plik .docx. U nas ma być stroną HTML.
- Nie sprawdzono: strony wyników, paginacji, eksportu, walidacji NIP/KRS w tych serwisach.

## 5. Reguły domenowe KIO, które GUI i walidacja muszą respektować (odczytane)

- Od 13.03.2026 odwołania składa się elektronicznie **tylko przez e-Doręczenia** (adres `AE:PL-38390-18806-HVTGC-26`); ePUAP nie służy już do odwołań. Ważne dla starszych dokumentów w danych treningowych, mogą wspominać ePUAP.
- Formaty: PDF z warstwą tekstową, formaty biurowe, PAdES dla dokumentów podpisywanych. Mail do 35 MB. Nazwy plików zalecane jako `RRRR-MM-DD_krotki_opis.pdf`; sufiksy `_tajemnica_przedsiebiorstwa`, `_dane_RODO`.
- Załączniki odwołania: dowód wpisu, dowód przesłania zamawiającemu, **pełnomocnictwo** (+ ciąg umocowań, opłata skarbowa 17 zł), dowody. To odpowiada naszym trzem typom dokumentów: odwołanie, pełnomocnictwo, potwierdzenie przelewu.
- Wpis: 7 500 / 15 000 zł (dostawy, usługi), 10 000 / 20 000 zł (roboty), zależnie od progów UE. Walidacja kwoty w `przelew` może sprawdzać, czy mieści się w tym zbiorze (jako **ostrzeżenie**, nie błąd).
- Numer rachunku wpisu NBP: `60 1010 1010 0081 3622 3100 0000`. Tytuł przelewu zawiera odwołującego, zamawiającego, przedmiot i datę odwołania.

## 6. Rekomendacje dla naszego GUI (decyzje do przyjęcia)

**Zgodne z benchmarkami:**
1. Styl Gov.pl: kolory i Open Sans jak wyżej, jeden Primary na ekran, komunikaty inline z piktogramem, polskie teksty w 2. osobie.
2. Uploader dokładnie wg Gov.pl (teksty instrukcji i przycisku bez zmian), lista z rozmiarem i krzyżykiem, progress bar, bo plik idzie na serwer. Błędy per plik z nazwą, error summary na górze z fokusem.
3. Stepper (4 kroki): Dodaj pliki → Wyniki klasyfikacji → Sprawdź dane → Pobierz JSON. W wariancie liniowym.
4. Ekran „Sprawdź dane” wg Check answers: grupy pól, „Zmień”, „Nie podano” dla `null`, przycisk „Zatwierdź i pobierz JSON”.
5. Loader: spinner do 5 s, progress bar z licznikiem plików „2 z 3” dla przetwarzania wsadowego (czas podawać tylko, jeśli realny).
6. Dostępność: pasek kontrast / A A A, stopka z linkiem do **HTML-owej** Deklaracji dostępności, pełna obsługa klawiaturą, `role="alert"/"status"`, `<caption>` i `scope` w tabelach, status nie tylko kolorem.
7. Okno wygaśnięcia sesji nie jest potrzebne (brak logowania). Pominąć.

**MUST HAVE (decyzja zespołu): podgląd PDF obok pól z podświetleniem źródła.**
Żaden z odczytanych serwisów publicznych tego nie opisuje, więc to nasza funkcja wyróżniająca. Nie powołujemy się na „standard”, tylko pokazujemy ją jako kontrolę wiarygodności wyniku. Wymagania, żeby działała bez uwag:
1. Układ dwukolumnowy: lewa kolumna pola (pogrupowane jak w JSON), prawa PDF (react-pdf). Na wąskim ekranie kolumny w pionie, z przełącznikiem „Pola / Dokument”.
2. Klik lub fokus na polu przewija PDF do właściwej strony (`page` z trace) i podświetla fragment (`source_snippet`). Klik w podświetlony fragment wybiera pole. Obie strony działają z klawiatury.
3. Podświetlenie nie tylko kolorem: obramowanie + etykieta pola; kontrast ≥ 3:1 (paleta Gov.pl, np. `#eba828` tło z `#1b1b1b` tekstem).
4. Gdy źródła nie da się zlokalizować (pole z LLM bez snippetu, PDF skanowany): jawny komunikat „Nie znaleziono tego fragmentu w dokumencie” (komunikat Ostrzeżenie), bez udawania podświetlenia.
5. Pola `null` pokazują „Nie podano”, bez podświetlenia.
6. Wartość edytowalna, z zachowaniem oryginału („Przywróć wartość z dokumentu”); każda zmiana ręczna oznaczona, a pobrany JSON zawiera wartość po edycji.
7. Odpowiednik dla czytnika ekranu: przy polu tekst „Źródło: strona 2, „…fragment…””, bo samo podświetlenie w PDF jest niedostępne wzrokowo.
8. Zależność z backendu: `trace` musi zwracać `page` i `source_snippet` (a najlepiej współrzędne/offset) dla każdego pola. Do uzgodnienia z sektorem B. Pozycję fragmentu w PDF wyznaczamy wyszukiwaniem tekstu w warstwie tekstowej (react-pdf text layer).
Znacznik niskiej pewności (próg + ikona + tekst) to osobna, opcjonalna propozycja.

## 7. Czego nie zweryfikowano (do zrobienia przed demo)

- Strony wyników orzeczenia.uzp.gov.pl i e-Zamówień, KRS (niedostępny).
- Zakładki „Dostępność” i „Przypadki użycia” komponentów Gov.pl (czytano tylko „Opis”).
- Dokładne tokeny odstępów, siatki i focus ring Gov.pl (`/wytyczne/odstepy`, `/grid`).
- Obwieszczenie o progach UE na 2026–2027 (liczbowe progi nie były w źródle).
- Realne działanie uploadera w przeglądarce (czytano specyfikację, nie uruchamiano).
