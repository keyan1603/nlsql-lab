-- The extension: eleven more tables (fulfilment, payments, inventory, promotions, web events, segment history, suppliers).
-- Added on purpose to make the schema wider and the names more confusable: ship_status next to ord_status and pay_status,
-- three different quantities (ord_line.qty, inv_move.qty, inventory.on_hand_qty), four different dates per order (ord_dt, paid_ts,
-- ship_dt, deliv_dt). Loaded after schema.sql; nothing in the core tables changes, so the 55 core questions keep their answers.

DROP TABLE IF EXISTS prod_supplier;
DROP TABLE IF EXISTS supplier;
DROP TABLE IF EXISTS cust_segment_hist;
DROP TABLE IF EXISTS web_event;
DROP TABLE IF EXISTS ord_promo;
DROP TABLE IF EXISTS promo;
DROP TABLE IF EXISTS payment;
DROP TABLE IF EXISTS shipment;
DROP TABLE IF EXISTS inv_move;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS warehouse;

CREATE TABLE warehouse (
  wh_id      VARCHAR(4)  NOT NULL COMMENT 'warehouse id, like W1',
  wh_nm      VARCHAR(40) NOT NULL COMMENT 'warehouse name',
  region_cd  VARCHAR(3)  NOT NULL COMMENT 'region the warehouse serves: NA, EU, AP, LA',
  PRIMARY KEY (wh_id)
) COMMENT = 'Warehouses';

CREATE TABLE inventory (
  sku            VARCHAR(10) NOT NULL COMMENT 'product',
  wh_id          VARCHAR(4)  NOT NULL COMMENT 'warehouse holding it',
  on_hand_qty    INT         NOT NULL COMMENT 'units on hand today (the data date): opening stock plus all movements',
  reorder_pt     INT         NOT NULL COMMENT 'restock when on_hand_qty falls to or below this',
  PRIMARY KEY (sku, wh_id),
  CONSTRAINT fk_inv_sku FOREIGN KEY (sku) REFERENCES prod_catalog (sku),
  CONSTRAINT fk_inv_wh FOREIGN KEY (wh_id) REFERENCES warehouse (wh_id)
) COMMENT = 'Current stock per product per warehouse';

CREATE TABLE inv_move (
  mv_id     INT         NOT NULL AUTO_INCREMENT COMMENT 'movement id',
  sku       VARCHAR(10) NOT NULL COMMENT 'product moved',
  wh_id     VARCHAR(4)  NOT NULL COMMENT 'warehouse it moved in or out of',
  mv_ts     DATETIME    NOT NULL COMMENT 'when it moved',
  mv_type   VARCHAR(3)  NOT NULL COMMENT 'IN restock, OUT customer shipment, ADJ stock count correction',
  qty       INT         NOT NULL COMMENT 'units moved: positive for IN, negative for OUT, either sign for ADJ',
  ord_id    VARCHAR(8)  NULL     COMMENT 'order that caused an OUT movement; NULL for IN and ADJ',
  PRIMARY KEY (mv_id),
  KEY ix_mv_sku (sku, wh_id),
  KEY ix_mv_ts (mv_ts)
) COMMENT = 'Stock movements';

CREATE TABLE shipment (
  ship_id      VARCHAR(8) NOT NULL COMMENT 'shipment id, like S-8001',
  ord_id       VARCHAR(8) NOT NULL COMMENT 'order shipped',
  wh_id        VARCHAR(4) NOT NULL COMMENT 'warehouse it left from',
  carrier_cd   VARCHAR(3) NOT NULL COMMENT 'carrier: UPS, DHL, FDX, USP',
  ship_dt      DATE       NOT NULL COMMENT 'date handed to the carrier',
  deliv_dt     DATE       NULL     COMMENT 'date delivered; NULL until delivered',
  ship_status  CHAR(1)    NOT NULL COMMENT 'shipment state: I in transit, D delivered',
  PRIMARY KEY (ship_id),
  KEY ix_ship_ord (ord_id),
  CONSTRAINT fk_ship_ord FOREIGN KEY (ord_id) REFERENCES ord_hdr (ord_id)
) COMMENT = 'Shipments, one per shipped order';

CREATE TABLE payment (
  pay_id       VARCHAR(8)    NOT NULL COMMENT 'payment attempt id, like P-3001',
  ord_id       VARCHAR(8)    NOT NULL COMMENT 'order paid',
  method_cd    VARCHAR(2)    NOT NULL COMMENT 'method: CC card, PP PayPal, BT bank transfer, GC gift card',
  pay_amt      DECIMAL(12,2) NOT NULL COMMENT 'amount of this attempt, in the order currency',
  currency_cd  CHAR(3)       NOT NULL COMMENT 'currency of pay_amt',
  paid_ts      DATETIME      NOT NULL COMMENT 'when the attempt was made',
  pay_status   CHAR(1)       NOT NULL COMMENT 'attempt outcome: S settled, F failed, R refunded after settling',
  PRIMARY KEY (pay_id),
  KEY ix_pay_ord (ord_id),
  CONSTRAINT fk_pay_ord FOREIGN KEY (ord_id) REFERENCES ord_hdr (ord_id)
) COMMENT = 'Payment attempts; an order can have several';

CREATE TABLE promo (
  promo_id   INT         NOT NULL COMMENT 'promotion id',
  promo_cd   VARCHAR(12) NOT NULL COMMENT 'code customers type in',
  promo_nm   VARCHAR(40) NOT NULL COMMENT 'promotion name',
  disc_pct   DECIMAL(5,2) NOT NULL COMMENT 'percent off the order, 0 to 100',
  starts_dt  DATE        NOT NULL COMMENT 'first day it can be used',
  ends_dt    DATE        NOT NULL COMMENT 'last day it can be used',
  PRIMARY KEY (promo_id)
) COMMENT = 'Promotions';

CREATE TABLE ord_promo (
  ord_id    VARCHAR(8) NOT NULL COMMENT 'order the promotion was applied to',
  promo_id  INT        NOT NULL COMMENT 'promotion applied',
  PRIMARY KEY (ord_id, promo_id),
  CONSTRAINT fk_op_ord FOREIGN KEY (ord_id) REFERENCES ord_hdr (ord_id),
  CONSTRAINT fk_op_promo FOREIGN KEY (promo_id) REFERENCES promo (promo_id)
) COMMENT = 'Which promotions were used on which orders';

CREATE TABLE web_event (
  evt_id      INT         NOT NULL AUTO_INCREMENT COMMENT 'event id',
  session_id  VARCHAR(12) NOT NULL COMMENT 'browsing session the event belongs to',
  cust_id     VARCHAR(8)  NULL     COMMENT 'customer, if logged in; NULL for anonymous sessions',
  evt_ts      DATETIME    NOT NULL COMMENT 'when it happened',
  evt_type    VARCHAR(8)  NOT NULL COMMENT 'VIEW product viewed, CART added to cart, CHECKOUT started checkout, PURCHASE order placed',
  sku         VARCHAR(10) NULL     COMMENT 'product involved; NULL for CHECKOUT and PURCHASE',
  ord_id      VARCHAR(8)  NULL     COMMENT 'order created by a PURCHASE event; NULL otherwise',
  channel_cd  VARCHAR(4)  NOT NULL COMMENT 'WEB or APP',
  PRIMARY KEY (evt_id),
  KEY ix_we_session (session_id),
  KEY ix_we_cust (cust_id),
  KEY ix_we_ts (evt_ts)
) COMMENT = 'Website and app clickstream, many rows';

CREATE TABLE cust_segment_hist (
  cust_id      VARCHAR(8) NOT NULL COMMENT 'customer',
  month_dt     DATE       NOT NULL COMMENT 'first day of the month the segment applied',
  segment_cd   VARCHAR(8) NOT NULL COMMENT 'segment that month: NEW, REG regular, VIP, RISK at risk of leaving',
  PRIMARY KEY (cust_id, month_dt),
  CONSTRAINT fk_seg_cust FOREIGN KEY (cust_id) REFERENCES cust_master (cust_id)
) COMMENT = 'Monthly history of each customer segment';

CREATE TABLE supplier (
  sup_id   INT         NOT NULL COMMENT 'supplier id',
  sup_nm   VARCHAR(40) NOT NULL COMMENT 'supplier name',
  country  VARCHAR(2)  NOT NULL COMMENT 'two letter country code',
  PRIMARY KEY (sup_id)
) COMMENT = 'Suppliers';

CREATE TABLE prod_supplier (
  sku         VARCHAR(10) NOT NULL COMMENT 'product',
  sup_id      INT         NOT NULL COMMENT 'supplier that can provide it',
  lead_days   INT         NOT NULL COMMENT 'days from ordering to receiving',
  is_primary  TINYINT(1)  NOT NULL COMMENT '1 = the main supplier for this product',
  PRIMARY KEY (sku, sup_id),
  CONSTRAINT fk_ps_sku FOREIGN KEY (sku) REFERENCES prod_catalog (sku),
  CONSTRAINT fk_ps_sup FOREIGN KEY (sup_id) REFERENCES supplier (sup_id)
) COMMENT = 'Which suppliers provide which products';
