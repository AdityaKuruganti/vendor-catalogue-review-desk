-- MOCK data for demos. SKUs match data/sample_vendor_rows.csv: process that CSV in the
-- review desk and APPROVE the rows first, otherwise the copilot correctly reports
-- "catalogue not available" and routes fit questions to a human.
insert into public.cx_customers (phone, name) values
  ('9876543210', 'Priya Sharma'),
  ('9123456780', 'Anita Iyer'),
  ('9988776655', 'Rohan Mehta')            -- no orders
on conflict (phone) do nothing;

insert into public.cx_orders (order_id, customer_id, sku_code, size_ordered, status, carrier, awb, ordered_at, expected_delivery)
select v.order_id, c.customer_id, v.sku, v.size, v.status, v.carrier, v.awb, v.ordered_at::timestamptz, v.eta::date
from (values
  ('ORD-10001','9876543210','W-KRT-GRN-M','M','IN_TRANSIT','Delhivery','DL4455667788','2026-09-28','2026-10-05'),
  ('ORD-10002','9876543210','W-DRS-RED-L','L','DELIVERED','Ecom Express','EE1122334455','2026-09-12','2026-09-20'),
  ('ORD-10005','9876543210','W-SAR-MRN-FS','Free Size','PLACED',null,null,'2026-10-01','2026-10-08'),
  ('ORD-10003','9123456780','K-FRK-PNK-67','6-7Y','SHIPPED','Xpressbees','XB9988776655','2026-09-29','2026-10-06'),
  ('ORD-10004','9123456780','K-TEE-YEL-45','4-5Y','OUT_FOR_DELIVERY','Delhivery','DL1239874560','2026-09-27','2026-10-02'),
  ('ORD-10006','9123456780','X-NOT-IN-CATALOGUE','M','IN_TRANSIT','Delhivery','DL7770001112','2026-09-30','2026-10-07')
) as v(order_id, phone, sku, size, status, carrier, awb, ordered_at, eta)
join public.cx_customers c on c.phone = v.phone
on conflict (order_id) do nothing;
