-- The lab database: a support and orders platform, named the way real legacy schemas are named
-- (abbreviations, codes instead of words, a lookup table for what the codes mean, soft deletes).
-- Column comments document the codes. The prompt builder can include or strip them, which is one of the
-- experiments: how much of a model's accuracy comes from the schema documentation?

DROP TABLE IF EXISTS tkt_event;
DROP TABLE IF EXISTS support_tkt;
DROP TABLE IF EXISTS refund_req;
DROP TABLE IF EXISTS ord_line;
DROP TABLE IF EXISTS ord_hdr;
DROP TABLE IF EXISTS fx_rate;
DROP TABLE IF EXISTS prod_catalog;
DROP TABLE IF EXISTS cust_master;
DROP TABLE IF EXISTS policy_rule;
DROP TABLE IF EXISTS code_lookup;
DROP TABLE IF EXISTS emp;

CREATE TABLE code_lookup (
  code_type VARCHAR(20) NOT NULL COMMENT 'which code list: ORD_STATUS, TIER, REFUND_STATUS, REFUND_REASON, TKT_CATEG, REGION, CHANNEL, DEPT',
  code_val  VARCHAR(10) NOT NULL COMMENT 'the stored code',
  code_desc VARCHAR(60) NOT NULL COMMENT 'what the code means in words',
  PRIMARY KEY (code_type, code_val)
) COMMENT = 'Meaning of every coded column in the other tables';

CREATE TABLE emp (
  emp_id       VARCHAR(8)    NOT NULL COMMENT 'employee id, like E-007',
  emp_nm       VARCHAR(60)   NOT NULL COMMENT 'full name',
  dept_cd      VARCHAR(6)    NOT NULL COMMENT 'department code, see code_lookup DEPT',
  mgr_emp_id   VARCHAR(8)    NULL     COMMENT 'emp_id of the direct manager; NULL for the top of the tree',
  hire_dt      DATE          NOT NULL COMMENT 'date hired',
  salary_amt   DECIMAL(10,2) NOT NULL COMMENT 'annual salary in USD; sensitive',
  natl_id      VARCHAR(16)   NOT NULL COMMENT 'national identifier; sensitive personal data',
  email_addr   VARCHAR(80)   NOT NULL COMMENT 'work email address',
  PRIMARY KEY (emp_id),
  KEY ix_emp_mgr (mgr_emp_id)
) COMMENT = 'Employees';

CREATE TABLE cust_master (
  cust_id     VARCHAR(8)  NOT NULL COMMENT 'customer id, like C-1002',
  cust_nm     VARCHAR(60) NOT NULL COMMENT 'customer name',
  tier_cd     CHAR(1)     NOT NULL COMMENT 'loyalty tier: P platinum, G gold, S standard',
  region_cd   VARCHAR(3)  NOT NULL COMMENT 'sales region: NA, EU, AP, LA',
  signup_dt   DATE        NOT NULL COMMENT 'date the customer signed up',
  is_actv     TINYINT(1)  NOT NULL COMMENT '1 = active, 0 = closed or inactive (soft delete)',
  email_addr  VARCHAR(80) NOT NULL COMMENT 'contact email address',
  phone_no    VARCHAR(20) NULL     COMMENT 'contact phone number',
  PRIMARY KEY (cust_id)
) COMMENT = 'Customer master record';

CREATE TABLE prod_catalog (
  sku         VARCHAR(10)   NOT NULL COMMENT 'stock keeping unit',
  prod_nm     VARCHAR(60)   NOT NULL COMMENT 'product name',
  categ_cd    VARCHAR(4)    NOT NULL COMMENT 'product category code: KIT kitchen, HOM home, OFC office, ELC electronics',
  list_prc    DECIMAL(10,2) NOT NULL COMMENT 'list price in USD',
  disc_flag   TINYINT(1)    NOT NULL COMMENT '1 = product is DISCONTINUED (not a price discount), 0 = still sold',
  PRIMARY KEY (sku)
) COMMENT = 'Product catalog';

CREATE TABLE fx_rate (
  currency_cd CHAR(3)       NOT NULL COMMENT 'ISO currency code',
  eff_dt      DATE          NOT NULL COMMENT 'first date the rate applies',
  rate_to_usd DECIMAL(10,6) NOT NULL COMMENT 'multiply an amount in this currency by this to get USD',
  PRIMARY KEY (currency_cd, eff_dt)
) COMMENT = 'Exchange rates, one row per currency per effective date';

CREATE TABLE ord_hdr (
  ord_id         VARCHAR(8)    NOT NULL COMMENT 'order id, like O-5002',
  cust_id        VARCHAR(8)    NOT NULL COMMENT 'customer who placed the order',
  ord_dt         DATE          NOT NULL COMMENT 'order date',
  ord_status     CHAR(1)       NOT NULL COMMENT 'N new, S shipped, D delivered, C cancelled, R returned',
  ord_total_amt  DECIMAL(12,2) NOT NULL COMMENT 'order total in the ORDER currency (currency_cd), already net of line discounts',
  currency_cd    CHAR(3)       NOT NULL COMMENT 'currency of ord_total_amt',
  channel_cd     VARCHAR(4)    NOT NULL COMMENT 'sales channel: WEB, APP, PHN, STR',
  PRIMARY KEY (ord_id),
  KEY ix_ord_cust (cust_id),
  KEY ix_ord_dt (ord_dt),
  CONSTRAINT fk_ord_cust FOREIGN KEY (cust_id) REFERENCES cust_master (cust_id)
) COMMENT = 'Order header, one row per order';

CREATE TABLE ord_line (
  ord_id    VARCHAR(8)    NOT NULL COMMENT 'order the line belongs to',
  line_no   INT           NOT NULL COMMENT 'line number within the order',
  sku       VARCHAR(10)   NOT NULL COMMENT 'product ordered',
  qty       INT           NOT NULL COMMENT 'units ordered',
  unit_prc  DECIMAL(10,2) NOT NULL COMMENT 'price per unit in the order currency',
  disc_pct  DECIMAL(5,2)  NOT NULL COMMENT 'percent discount on this line, 0 to 100',
  PRIMARY KEY (ord_id, line_no),
  CONSTRAINT fk_line_ord FOREIGN KEY (ord_id) REFERENCES ord_hdr (ord_id),
  CONSTRAINT fk_line_sku FOREIGN KEY (sku) REFERENCES prod_catalog (sku)
) COMMENT = 'Order lines, one row per product on an order';

CREATE TABLE refund_req (
  rfd_id           VARCHAR(8)    NOT NULL COMMENT 'refund request id, like R-9001',
  ord_id           VARCHAR(8)    NOT NULL COMMENT 'order the refund is for',
  req_dt           DATE          NOT NULL COMMENT 'date the refund was requested',
  rfd_amt          DECIMAL(10,2) NOT NULL COMMENT 'amount requested, in the order currency',
  reason_cd        VARCHAR(4)    NOT NULL COMMENT 'reason: DMG damaged, DUP duplicate charge, LAT late delivery, OTH other',
  status_cd        CHAR(1)       NOT NULL COMMENT 'P pending, A approved, D denied',
  approver_emp_id  VARCHAR(8)    NULL     COMMENT 'employee who decided; NULL while pending',
  decided_dt       DATE          NULL     COMMENT 'date decided; NULL while pending',
  PRIMARY KEY (rfd_id),
  KEY ix_rfd_ord (ord_id),
  CONSTRAINT fk_rfd_ord FOREIGN KEY (ord_id) REFERENCES ord_hdr (ord_id)
) COMMENT = 'Refund requests';

CREATE TABLE support_tkt (
  tkt_id            VARCHAR(8)  NOT NULL COMMENT 'ticket id, like T-70010',
  cust_id           VARCHAR(8)  NOT NULL COMMENT 'customer who raised the ticket',
  opened_ts         DATETIME    NOT NULL COMMENT 'when the ticket was opened',
  closed_ts         DATETIME    NULL     COMMENT 'when it was closed; NULL means the ticket is still open',
  sev_lvl           TINYINT     NOT NULL COMMENT 'severity: 1 critical, 2 high, 3 medium, 4 low',
  categ_cd          VARCHAR(6)  NOT NULL COMMENT 'category: BILL billing, SHIP shipping, TECH technical, ACCT account, REFD refunds',
  assigned_emp_id   VARCHAR(8)  NULL     COMMENT 'employee working it; NULL if not yet assigned',
  channel_cd        VARCHAR(4)  NOT NULL COMMENT 'how it arrived: WEB, APP, PHN, STR',
  PRIMARY KEY (tkt_id),
  KEY ix_tkt_cust (cust_id),
  KEY ix_tkt_open (opened_ts),
  CONSTRAINT fk_tkt_cust FOREIGN KEY (cust_id) REFERENCES cust_master (cust_id)
) COMMENT = 'Support tickets';

CREATE TABLE tkt_event (
  evt_id        INT         NOT NULL AUTO_INCREMENT COMMENT 'event id',
  tkt_id        VARCHAR(8)  NOT NULL COMMENT 'ticket the event belongs to',
  evt_ts        DATETIME    NOT NULL COMMENT 'when it happened',
  evt_type      VARCHAR(10) NOT NULL COMMENT 'OPEN, ASSIGN, REPLY, ESCAL (escalated), CLOSE',
  actor_emp_id  VARCHAR(8)  NULL     COMMENT 'employee who did it; NULL for customer actions',
  PRIMARY KEY (evt_id),
  KEY ix_evt_tkt (tkt_id),
  CONSTRAINT fk_evt_tkt FOREIGN KEY (tkt_id) REFERENCES support_tkt (tkt_id)
) COMMENT = 'Ticket history';

CREATE TABLE policy_rule (
  rule_id    INT         NOT NULL COMMENT 'rule row id',
  rule_key   VARCHAR(40) NOT NULL COMMENT 'which policy: refund_approval_threshold (USD amount above which a refund needs manager approval), sla_hours_sev1 (hours to resolve a critical ticket)',
  rule_val   VARCHAR(40) NOT NULL COMMENT 'the value, stored as text',
  eff_from   DATE        NOT NULL COMMENT 'first date the value applies',
  eff_to     DATE        NULL     COMMENT 'last date the value applies; NULL = still in force',
  PRIMARY KEY (rule_id)
) COMMENT = 'Policy values that change over time; pick the row in force on the date you care about';
