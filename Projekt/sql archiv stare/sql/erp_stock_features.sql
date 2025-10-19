USE erp;

CREATE TABLE IF NOT EXISTS writeoff_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ts DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  sklad_id BIGINT NOT NULL,
  produkt_id BIGINT NOT NULL,
  qty DECIMAL(18,3) NOT NULL,
  reason_code TINYINT NOT NULL,
  reason_text VARCHAR(255) NULL,
  actor_user_id BIGINT NULL,
  signature_text VARCHAR(255) NULL,
  CONSTRAINT fk_wo_sklad FOREIGN KEY (sklad_id) REFERENCES warehouses(id),
  CONSTRAINT fk_wo_prod FOREIGN KEY (produkt_id) REFERENCES products(id)
) ENGINE=InnoDB;

DROP PROCEDURE IF EXISTS sp_manual_writeoff;
DELIMITER //
CREATE PROCEDURE sp_manual_writeoff(
    IN p_actor_user_id BIGINT,
    IN p_sklad_id BIGINT,
    IN p_produkt_id BIGINT,
    IN p_qty DECIMAL(18,3),
    IN p_reason_code TINYINT,
    IN p_reason_text VARCHAR(255),
    IN p_signature_text VARCHAR(255)
)
BEGIN
    IF p_qty <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Qty must be > 0';
    END IF;

    CALL sp_inventory_consume(p_actor_user_id, p_sklad_id, p_produkt_id, p_qty, p_reason_code, p_reason_text);

    INSERT INTO writeoff_logs(sklad_id, produkt_id, qty, reason_code, reason_text, actor_user_id, signature_text)
    VALUES (p_sklad_id, p_produkt_id, p_qty, p_reason_code, p_reason_text, p_actor_user_id, p_signature_text);
END//
DELIMITER ;
