USE erp;

DROP VIEW IF EXISTS produkty;
CREATE OR REPLACE VIEW produkty AS
SELECT
  p.id, p.ean, p.nazov, p.typ,
  COALESCE(pc.name, '') AS kategoria,
  p.jednotka, p.min_zasoba, p.dph, p.je_vyroba, p.parent_id,
  p.kategoria_id
FROM products p
LEFT JOIN product_categories pc ON pc.id = p.kategoria_id;

DROP VIEW IF EXISTS sklady;
CREATE OR REPLACE VIEW sklady AS
SELECT
  id,
  nazov,
  CASE
    WHEN typ IN ('vyrobny','centralny') THEN typ
    WHEN typ = 0 THEN 'vyrobny'
    WHEN typ = 1 THEN 'centralny'
    ELSE 'centralny'
  END AS typ
FROM warehouses;

DROP VIEW IF EXISTS sklad;
CREATE OR REPLACE VIEW sklad AS
SELECT * FROM sklady;
