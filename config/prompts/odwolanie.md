---
# Pola, które LLM może uzupełnić, gdy reguły dały null (wariant hybrydowy, odw2json/llm_fill.py).
# opis     - instrukcja dla modelu (wg data/oczekiwane-json/odwolanie.json); zawsze w cudzysłowie (znak # w YAML),
# szukaj   - frazy jak w config/doctypes (re:<regex> na tekście bez polskich znaków, małe litery);
#            wycinek = okna wokół trafień; brak trafienia = pole bez zapytania; [] = tylko początek dokumentu,
# wartosci - zamknięta lista dozwolonych odpowiedzi (wtedy bez kontroli „jest w tekście”).
# Bez Zamawiajacy[].prowadzacy_postepowanie: reguły zostawiają null tylko przy jednym zamawiającym (GT też null).
pola:
  OdwolanieKIO.data:
    opis: 'Data sporządzenia odwołania z linii z miejscem i datą (np. „Warszawa, dnia 13.10.2025”), format RRRR-MM-DD. Brak takiej linii = null.'
    szukaj: ['re:\bdnia\b', 're:^[^\n]{2,40},\s*(?:dnia\s+)?\d{1,2}[ .]']
  OdwolanieKIO.miejscowosc:
    opis: 'Miejscowość z linii z miejscem i datą sporządzenia (np. „Warszawa, dnia …”), w mianowniku. Adres KIO (ul. Postępu 17A, Warszawa) ani adres strony to NIE jest miejscowość sporządzenia; brak takiej linii = null.'
    szukaj: ['re:\bdnia\b', 're:^[^\n]{2,40},\s*(?:dnia\s+)?\d{1,2}[ .]']
  OdwolanieKIO.czynnosc_dzien:
    opis: 'Data czynności zamawiającego zaskarżonej w PIERWSZYM zarzucie (dzień publikacji, przekazania lub powzięcia wiadomości), RRRR-MM-DD. Brak wiarygodnej daty = null.'
    szukaj: ['re:zarzut\w*', 're:powzi\w*', 're:zawiadomi\w*', 're:opublikowa\w*', 're:przekaza\w*']
  OdwolanieKIO.czynnosc_powod_id:
    opis: 'Powód odwołania z PIERWSZEGO zarzutu, liczba 1-12: 1=Decyzja o odrzuceniu oferty, 2=Ogłoszenie wyboru oferty, 3=Decyzja o wykluczeniu wykonawcy, 4=Publikacja specyfikacji warunków zamówienia (SWZ), 5=Modyfikacja treści SWZ, 6=Odpowiedzi/wyjaśnienia do SWZ, 7=Zaniechanie odrzucenia oferty, 8=Zaniechanie wykluczenia wykonawcy, 9=Decyzja o unieważnieniu postępowania, 10=Zaniechanie unieważnienia postępowania, 11=Opis przedmiotu zamówienia (OPZ), 12=Projektowane postanowienia umowy.'
    szukaj: ['re:zarzut\w*', 're:zaskarz\w*', 're:czynnosc\w*']
  Odwolujacy[].nazwa:
    opis: 'Pełna nazwa Odwołującego (wykonawcy wnoszącego odwołanie); przy konsorcjum nazwa Lidera.'
    szukaj: ['re:odwolujac\w*', 're:wnoszac\w*']
  Odwolujacy[].krs:
    opis: 'Numer KRS Odwołującego (lub Lidera konsorcjum), 10 cyfr, tylko jeśli podany przy Odwołującym.'
    szukaj: ['re:krs']
  Odwolujacy[].nip:
    opis: 'NIP Odwołującego (lub Lidera konsorcjum), tylko jeśli podany przy Odwołującym.'
    szukaj: ['re:nip']
  Odwolujacy[].regon:
    opis: 'REGON Odwołującego (lub Lidera konsorcjum), tylko jeśli podany przy Odwołującym.'
    szukaj: ['re:regon']
  Odwolujacy[].przez-pelnomocnika:
    opis: '1, jeśli Odwołującego reprezentuje pełnomocnik; 0, jeśli nie.'
    szukaj: ['re:pelnomocni\w*']
  Odwolujacy[].pelnomocnik.imie_nazwisko:
    opis: 'Imię i nazwisko pełnomocnika Odwołującego (mianownik, bez tytułu).'
    szukaj: ['re:pelnomocni\w*', 're:\badw\.', 're:\bradc\w*', 're:adwokat\w*', 're:\br\.\s?pr\.']
  Odwolujacy[].pelnomocnik.nazwa:
    opis: 'Nazwa podmiotu (kancelarii), w którym działa pełnomocnik Odwołującego.'
    szukaj: ['kancelaria', 're:pelnomocni\w*']
  Odwolujacy[].pelnomocnik.mail:
    opis: 'Adres e-mail pełnomocnika Odwołującego, przepisany dokładnie z tekstu.'
    szukaj: ['re:@', 're:e-?mail']
  Zamawiajacy[].nazwa:
    opis: 'Pełna nazwa Zamawiającego.'
    szukaj: ['re:zamawiajac\w*']
  Zamawiajacy[].krs:
    opis: 'Numer KRS Zamawiającego, tylko jeśli jawnie podany przy Zamawiającym.'
    szukaj: ['re:krs']
  Zamawiajacy[].nip:
    opis: 'NIP Zamawiającego, tylko jeśli jawnie podany przy Zamawiającym.'
    szukaj: ['re:nip']
  Zamawiajacy[].regon:
    opis: 'REGON Zamawiającego, tylko jeśli jawnie podany przy Zamawiającym.'
    szukaj: ['re:regon']
  ZamowieniePubliczne.numer_bzp:
    opis: 'Numer ogłoszenia w Biuletynie Zamówień Publicznych, format RRRR/BZP ######## (np. 2025/BZP 00123456). Nie wpisuj numeru TED.'
    szukaj: ['re:bzp', 're:biuletyn\w*']
  ZamowieniePubliczne.numer_ted:
    opis: 'Numer ogłoszenia w TED (Dziennik Urzędowy UE), zapis NNNNNN-RRRR (np. 641651-2025); zapis „2025/S 123-641651” zamień na 641651-2025.'
    szukaj: ['re:\bted\b', 're:dz\.?\s*urz', 'dzienniku urzedowym', 're:\d{4}\s*/\s*s\s*\d', 're:(?<![\d/-])\d{6}-20\d{2}(?!\d)']
  ZamowieniePubliczne.numer_postepowania:
    opis: 'Numer referencyjny / znak sprawy postępowania nadany przez zamawiającego (np. ZP.039.2025, DZP.260.11.2025).'
    szukaj: ['re:znak\w*', 're:nr\.?\s+postepowani\w*', 're:numer\s+(?:referencyjn|postepowani|sprawy)\w*', 're:sygn\w*', 're:nr\s+ref\w*']
  ZamowieniePubliczne.tytul:
    opis: 'Tytuł (nazwa) zamówienia lub postępowania, bez cudzysłowów.'
    szukaj: ['re:\bpn\.', 're:pod\s+nazw\w*', 're:dotyczy', 're:\bdot\.', 're:zamowieni\w*\s+publiczn\w*']
---
Dokument to odwołanie do Krajowej Izby Odwoławczej. Odwołujący to wykonawca, który wnosi odwołanie; Zamawiający to instytucja prowadząca postępowanie. Nie myl danych Odwołującego, Zamawiającego, pełnomocnika ani wykonawcy wybranego lub przystępującego: numer przypisuj do pola tylko wtedy, gdy w tekście stoi przy właściwym podmiocie. Adres Krajowej Izby Odwoławczej (Prezes KIO, ul. Postępu 17A, 02-676 Warszawa) to adresat pisma, nie dane stron.
