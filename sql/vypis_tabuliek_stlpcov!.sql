SELECT
    TABLE_NAME,      -- Názov tabuľky
    COLUMN_NAME,     -- Názov stĺpca
    ORDINAL_POSITION, -- Poradie stĺpca v tabuľke
    COLUMN_TYPE      -- Typ stĺpca (napr. VARCHAR(255), DECIMAL(10,2))
FROM
    INFORMATION_SCHEMA.COLUMNS
WHERE
    TABLE_SCHEMA = 'erp_new' -- Názov vašej databázy
ORDER BY
    TABLE_NAME,
    ORDINAL_POSITION;