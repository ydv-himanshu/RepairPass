CREATE DATABASE IF NOT EXISTS RepairPassDB;
USE RepairPassDB;
-- 1st module
CREATE TABLE MANUFACTURER (
    manufacturer_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(50),
    support_website VARCHAR(255)
);
 
CREATE TABLE CATEGORY (
    category_id VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL
);

CREATE TABLE PRODUCT_MODEL (
    model_id VARCHAR(10) PRIMARY KEY,
    manufacturer_id VARCHAR(10) NOT NULL,
    category_id VARCHAR(10) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    release_year INT CHECK (release_year >= 2000),
    FOREIGN KEY (manufacturer_id) REFERENCES MANUFACTURER(manufacturer_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES CATEGORY(category_id) ON DELETE CASCADE
);

CREATE TABLE PRODUCT (
    product_id VARCHAR(10) PRIMARY KEY,
    serial_number VARCHAR(50) UNIQUE NOT NULL,
    model_id VARCHAR(10) NOT NULL,
    purchase_date DATE NOT NULL,
    FOREIGN KEY (model_id) REFERENCES PRODUCT_MODEL(model_id) ON DELETE CASCADE
);

INSERT INTO MANUFACTURER VALUES ('MF01', 'Apple', 'USA', 'support.apple.com'), ('MF02', 'Dell', 'USA', 'dell.com/support');
INSERT INTO CATEGORY VALUES ('C01', 'Smartphone'), ('C02', 'Laptop');
INSERT INTO PRODUCT_MODEL VALUES ('M101', 'MF01', 'C01', 'iPhone 14 Pro', 2022), ('M102', 'MF02', 'C02', 'XPS 15', 2023);
INSERT INTO PRODUCT VALUES ('P1001', 'F2LX3091DN', 'M101', '2023-10-15'), ('P1002', 'DLX8820391', 'M102', '2024-01-10');

-- 2nd module
CREATE TABLE OWNER (
    owner_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    contact_info VARCHAR(150) NOT NULL
);

CREATE TABLE OWNERSHIP (
    ownership_id VARCHAR(10) PRIMARY KEY,
    product_id VARCHAR(10) NOT NULL,
    owner_id VARCHAR(10) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id) REFERENCES OWNER(owner_id) ON DELETE CASCADE,
    CONSTRAINT chk_ownership_dates CHECK (end_date IS NULL OR end_date >= start_date)
);

INSERT INTO OWNER VALUES ('O501', 'Rahul Sharma', 'rahul.s@example.com'), ('O502', 'Priya Verma', 'priya.v@example.com');

INSERT INTO OWNERSHIP VALUES ('H701', 'P1001', 'O501', '2023-10-15', '2025-08-01');
INSERT INTO OWNERSHIP VALUES ('H702', 'P1001', 'O502', '2025-08-01', NULL);

-- 3rd module
CREATE TABLE REPAIR_CENTER (
    center_id VARCHAR(10) PRIMARY KEY,
    center_name VARCHAR(100) NOT NULL,
    city VARCHAR(50) NOT NULL,
    contact_info VARCHAR(150),
    is_authorized VARCHAR(3) CHECK (is_authorized IN ('Yes', 'No'))
);

CREATE TABLE REPAIR (
    repair_id VARCHAR(10) PRIMARY KEY,
    product_id VARCHAR(10) NOT NULL,
    center_id VARCHAR(10) NOT NULL,
    repair_date DATE NOT NULL,
    issue_description TEXT NOT NULL,
    work_performed TEXT NOT NULL,
    labour_cost DECIMAL(10, 2) DEFAULT 0.00,
    FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id) ON DELETE CASCADE,
    FOREIGN KEY (center_id) REFERENCES REPAIR_CENTER(center_id) ON DELETE CASCADE
);

CREATE TABLE PART (
    part_id VARCHAR(10) PRIMARY KEY,
    part_name VARCHAR(100) NOT NULL,
    part_type VARCHAR(50) NOT NULL
);

CREATE TABLE REPAIR_PART (
    repair_id VARCHAR(10) NOT NULL,
    part_id VARCHAR(10) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    part_cost DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (repair_id, part_id),
    FOREIGN KEY (repair_id) REFERENCES REPAIR(repair_id) ON DELETE CASCADE,
    FOREIGN KEY (part_id) REFERENCES PART(part_id) ON DELETE CASCADE
);

INSERT INTO REPAIR_CENTER VALUES ('RC01', 'iCare Express', 'Delhi', 'care@icare.example.com', 'No');
INSERT INTO REPAIR VALUES ('R901', 'P1001', 'RC01', '2024-06-12', 'Broken screen & battery drain', 'Screen & battery swap', 50.00);
INSERT INTO PART VALUES ('PT01', 'OLED Display', 'Display'), ('PT02', 'Battery', 'Battery');
INSERT INTO REPAIR_PART VALUES ('R901', 'PT01', 1, 150.00), ('R901', 'PT02', 1, 50.00);

-- 4th module
CREATE TABLE WARRANTY_PROVIDER (
    provider_id VARCHAR(10) PRIMARY KEY,
    provider_name VARCHAR(100) NOT NULL,
    contact_info VARCHAR(150)
);

CREATE TABLE WARRANTY (
    warranty_id VARCHAR(10) PRIMARY KEY,
    product_id VARCHAR(10) NOT NULL,
    provider_id VARCHAR(10) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES WARRANTY_PROVIDER(provider_id) ON DELETE CASCADE,
    CONSTRAINT chk_warranty_dates CHECK (end_date >= start_date)
);

INSERT INTO WARRANTY_PROVIDER VALUES ('WP01', 'AppleCare+', 'support.apple.com/applecare');
INSERT INTO WARRANTY VALUES ('W301', 'P1001', 'WP01', '2023-10-15', '2025-10-14');

-- 5th module
CREATE VIEW vw_DevicePassport AS
SELECT 
    p.serial_number,
    m.name AS manufacturer_name,
    pm.model_name,
    cat.category_name,
    p.purchase_date,
    o.name AS current_owner_name,
    o.contact_info AS current_owner_contact,
    r.repair_date,
    rc.center_name AS repair_shop,
    rc.is_authorized,
    r.issue_description,
    r.work_performed,
    pt.part_name,
    rp.quantity,
    rp.part_cost,
    r.labour_cost,
    wp.provider_name AS warranty_provider,
    w.start_date AS warranty_start,
    w.end_date AS warranty_end,
    CASE 
        WHEN CURRENT_DATE BETWEEN w.start_date AND w.end_date THEN 'ACTIVE'
        ELSE 'EXPIRED'
    END AS computed_warranty_status
FROM PRODUCT p
JOIN PRODUCT_MODEL pm ON p.model_id = pm.model_id
JOIN MANUFACTURER m ON pm.manufacturer_id = m.manufacturer_id
JOIN CATEGORY cat ON pm.category_id = cat.category_id
LEFT JOIN OWNERSHIP os ON p.product_id = os.product_id AND os.end_date IS NULL
LEFT JOIN OWNER o ON os.owner_id = o.owner_id
LEFT JOIN REPAIR r ON p.product_id = r.product_id
LEFT JOIN REPAIR_CENTER rc ON r.center_id = rc.center_id
LEFT JOIN REPAIR_PART rp ON r.repair_id = rp.repair_id
LEFT JOIN PART pt ON rp.part_id = pt.part_id
LEFT JOIN WARRANTY w ON p.product_id = w.product_id
LEFT JOIN WARRANTY_PROVIDER wp ON w.provider_id = wp.provider_id;
