# Self-correction: before/after examples

## error

**e_commerce, question 65:** What are the statuses, dates, and shipment dates for all invoices?

- First attempt: `SELECT invoice_status_code , invoice_date , shipment_date FROM INVOICES`
- Result: no such column: shipment_date
- Feedback given: 'That query failed with this error: no such column: T1.shipment_date\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 3: `SELECT invoice_status_code , invoice_date , T2.shipment_date FROM INVOICES AS T1 JOIN SHIPMENTS AS T2 ON T1.invoice_number = T2.invoice_number`
- Gold: `SELECT T1.invoice_status_code ,  T1.invoice_date ,  T2.shipment_date FROM Invoices AS T1 JOIN Shipments AS T2 ON T1.invoice_number  =  T2.invoice_number`

**customers_and_orders, question 273:** What is the customer address, customer phone, and customer email for Jeromy?

- First attempt: `SELECT t1.customer_address , t1.customer_phone , t1.customer_email FROM customers AS t1 JOIN customers_orders AS t2 ON t1.customer_id = t2.customer_id WHERE t1.customer_name = 'Jeromy'`
- Result: no such table: customers_orders
- Feedback given: 'That query failed with this error: no such table: customers_orders\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT t1.customer_address , t1.customer_phone , t1.customer_email FROM customers AS t1 JOIN customer_orders AS t2 ON t1.customer_id = t2.customer_id WHERE t1.customer_name = 'Jeromy'`
- Gold: `SELECT customer_address ,  customer_phone ,  customer_email FROM Customers WHERE customer_name  =  "Jeromy"`

**cre_Students_Information_Systems, question 467:** How many students have joined in the most common type of event? List the number, the event type and description.

- First attempt: `SELECT count(*) , T1.event_type_code , T1.event_type_description FROM student_events AS T1 JOIN ref_event_types AS T2 ON T1.event_type_code = T2.event_type_code GROUP BY T1.event_type_code ORDER BY count(*) DESC LIMIT 1`
- Result: no such column: T1.event_type_description
- Feedback given: 'That query failed with this error: no such column: T1.event_type_description\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT count(*) , T1.event_type_code , T2.event_type_description FROM student_events AS T1 JOIN ref_event_types AS T2 ON T1.event_type_code = T2.event_type_code GROUP BY T1.event_type_code ORDER BY count(*) DESC LIMIT 1`
- Gold: `SELECT count(*) ,  T2.event_type_code ,  T3.event_type_description FROM Students AS T1 JOIN Student_Events AS T2 ON T1.student_id  =  T2.student_id JOIN Ref_Event_Types AS T3 ON T2.event_type_code  =  T3.event_type_code GROUP BY T2.event_type_code ORDER BY count(*) DESC LIMIT 1`
