# Self-correction: before/after examples

## plain

**cre_Doc_Template_Mgt, question 342:** What are the different template type codes, and how many documents use each type?

- First attempt: `SELECT Template_Type_Code , count(*) FROM Documents GROUP BY Template_Type_Code`
- Result: no such column: Template_Type_Code
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT T1.Template_Type_Code , count(*) FROM Ref_Template_Types AS T1 JOIN Templates AS T2 ON T1.Template_Type_Code = T2.Template_Type_Code JOIN Documents AS T3 ON T2.Template_ID = T3.Template_ID GROUP BY T1.Template_Type_Code`
- Gold: `SELECT T1.template_type_code ,  count(*) FROM Templates AS T1 JOIN Documents AS T2 ON T1.template_id  =  T2.template_id GROUP BY T1.template_type_code`

**student_transcripts_tracking, question 517:** How many departments offer any degree?

- First attempt: `SELECT count(*) FROM DEPARTMENT_PROGRAMS`
- Result: no such table: DEPARTMENT_PROGRAMS
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 3: `SELECT count(DISTINCT course_id) FROM STUDENT_ENROLMENT_COURSES`
- Gold: `SELECT count(DISTINCT department_id) FROM Degree_Programs`

**poker_player, question 669:** What is the average earnings of poker players with height higher than 200?

- First attempt: `SELECT avg(Earnings) FROM poker_player WHERE Height > 200`
- Result: no such column: Height
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT avg(T1.Earnings) FROM poker_player AS T1 JOIN people AS T2 ON T1.People_ID = T2.People_ID WHERE T2.Height > 200`
- Gold: `SELECT avg(T2.Earnings) FROM people AS T1 JOIN poker_player AS T2 ON T1.People_ID  =  T2.People_ID WHERE T1.Height  >  200`

## error

**pets_1, question 57:** Find the first name of students who have cat or dog pet.

- First attempt: `SELECT T1.Fname FROM STUDENT AS T1 JOIN HAS_PET AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.pet_type = 'cat' OR T3.pet_type = 'dog'`
- Result: no such column: T3.pet_type
- Feedback given: 'That query failed with this error: no such column: T3.pet_type\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT T1.Fname FROM STUDENT AS T1 JOIN HAS_PET AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'cat' OR T3.PetType = 'dog'`
- Gold: `SELECT DISTINCT T1.Fname FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat' OR T3.pettype  =  'dog'`

**cre_Doc_Template_Mgt, question 335:** What the smallest version number and its template type code?

- First attempt: `SELECT min(Template_Version) , Template_Type_Code FROM Templates`
- Result: no such column: Template_Version
- Feedback given: 'That query failed with this error: no such column: Template_Version\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT min(version_number) , Template_Type_Code FROM Templates`
- Gold: `SELECT min(Version_Number) ,  template_type_code FROM Templates`

**student_transcripts_tracking, question 517:** How many departments offer any degree?

- First attempt: `SELECT count(*) FROM DEPARTMENT_PROGRAMS`
- Result: no such table: DEPARTMENT_PROGRAMS
- Feedback given: 'That query failed with this error: no such table: DEPARTMENT_PROGRAMS\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT count(*) FROM Degree_Programs`
- Gold: `SELECT count(DISTINCT department_id) FROM Degree_Programs`

## plain_empty

**cre_Doc_Template_Mgt, question 342:** What are the different template type codes, and how many documents use each type?

- First attempt: `SELECT Template_Type_Code , count(*) FROM Documents GROUP BY Template_Type_Code`
- Result: no such column: Template_Type_Code
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT T1.Template_Type_Code , count(*) FROM Ref_Template_Types AS T1 JOIN Templates AS T2 ON T1.Template_Type_Code = T2.Template_Type_Code JOIN Documents AS T3 ON T2.Template_ID = T3.Template_ID GROUP BY T1.Template_Type_Code`
- Gold: `SELECT T1.template_type_code ,  count(*) FROM Templates AS T1 JOIN Documents AS T2 ON T1.template_id  =  T2.template_id GROUP BY T1.template_type_code`

**student_transcripts_tracking, question 517:** How many departments offer any degree?

- First attempt: `SELECT count(*) FROM DEPARTMENT_PROGRAMS`
- Result: no such table: DEPARTMENT_PROGRAMS
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 3: `SELECT count(DISTINCT course_id) FROM STUDENT_ENROLMENT_COURSES`
- Gold: `SELECT count(DISTINCT department_id) FROM Degree_Programs`

**poker_player, question 669:** What is the average earnings of poker players with height higher than 200?

- First attempt: `SELECT avg(Earnings) FROM poker_player WHERE Height > 200`
- Result: no such column: Height
- Feedback given: 'That query is not right. Write a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT avg(T1.Earnings) FROM poker_player AS T1 JOIN people AS T2 ON T1.People_ID = T2.People_ID WHERE T2.Height > 200`
- Gold: `SELECT avg(T2.Earnings) FROM people AS T1 JOIN poker_player AS T2 ON T1.People_ID  =  T2.People_ID WHERE T1.Height  >  200`

## error_empty

**pets_1, question 57:** Find the first name of students who have cat or dog pet.

- First attempt: `SELECT T1.Fname FROM STUDENT AS T1 JOIN HAS_PET AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.pet_type = 'cat' OR T3.pet_type = 'dog'`
- Result: no such column: T3.pet_type
- Feedback given: 'That query failed with this error: no such column: T3.pet_type\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT T1.Fname FROM STUDENT AS T1 JOIN HAS_PET AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'cat' OR T3.PetType = 'dog'`
- Gold: `SELECT DISTINCT T1.Fname FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat' OR T3.pettype  =  'dog'`

**cre_Doc_Template_Mgt, question 335:** What the smallest version number and its template type code?

- First attempt: `SELECT min(Template_Version) , Template_Type_Code FROM Templates`
- Result: no such column: Template_Version
- Feedback given: 'That query failed with this error: no such column: Template_Version\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT min(version_number) , Template_Type_Code FROM Templates`
- Gold: `SELECT min(Version_Number) ,  template_type_code FROM Templates`

**student_transcripts_tracking, question 517:** How many departments offer any degree?

- First attempt: `SELECT count(*) FROM DEPARTMENT_PROGRAMS`
- Result: no such table: DEPARTMENT_PROGRAMS
- Feedback given: 'That query failed with this error: no such table: DEPARTMENT_PROGRAMS\nWrite a corrected SQLite query. Reply with only the SQL query.'
- Attempt 2: `SELECT count(*) FROM Degree_Programs`
- Gold: `SELECT count(DISTINCT department_id) FROM Degree_Programs`
