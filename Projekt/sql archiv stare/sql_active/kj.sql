-- Tento príkaz pridá stĺpec pre DPH do tabuľky produktov.
-- Ak ti vráti chybu "Duplicate column name 'dph'", je to v poriadku.
ALTER TABLE produkty ADD COLUMN dph DECIMAL(5, 2) NOT NULL DEFAULT 19.00;

-- Tento príkaz vytvorí novú tabuľku na ukladanie oznamov pre B2B portál.
CREATE TABLE IF NOT EXISTS b2b_nastavenia (
kluc VARCHAR(50) PRIMARY KEY,
hodnota TEXT,
posledna_uprava TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Tento príkaz pridá stĺpec na zaznamenanie súhlasu s GDPR.
ALTER TABLE b2b_zakaznici ADD COLUMN gdpr_suhlas BOOLEAN NOT NULL DEFAULT FALSE;

-- Tieto príkazy rozšíria tabuľku objednávok o ceny s DPH a bez DPH.
ALTER TABLE b2b_objednavky ADD COLUMN celkova_suma_bez_dph DECIMAL(10, 2);
ALTER TABLE b2b_objednavky ADD COLUMN celkova_suma_s_dph DECIMAL(10, 2);

-- --- NOVÉ PRÍKAZY NA OPRAVU A ROZŠÍRENIE ---

-- 1. Odstránenie starého, konfliktného stĺpca z objednávok.
-- Ak tento príkaz vráti chybu, že stĺpec neexistuje, je to v poriadku.
ALTER TABLE b2b_objednavky DROP COLUMN celkova_suma;

-- 2. Rozšírenie tabuľky položiek objednávky o nové stĺpce pre objednávanie na kusy.
ALTER TABLE b2b_objednavky_polozky ADD COLUMN objednana_jednotka VARCHAR(10) NOT NULL DEFAULT 'kg';
ALTER TABLE b2b_objednavky_polozky ADD COLUMN poznamka_k_polozke TEXT;