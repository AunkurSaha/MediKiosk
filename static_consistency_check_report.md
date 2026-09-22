# Static Consistency Check Report for Phase 5 Queue Ordering

## 1. patient_queue_estimate ordering (using correct sequence_number tie-breaker)
**Status: CORRECT**
- File: `backend/app/services/doctor_routing.py`
- Function: `patient_queue_estimate` (lines 827-891)
- Implementation: Uses COUNT-based approach with proper FIFO condition
- Code:
  ```python
  (models.DoctorQueueEntry.joined_at < entry.joined_at) |
  (
      (models.DoctorQueueEntry.joined_at == entry.joined_at) &
      (models.DoctorQueueEntry.sequence_number < entry.sequence_number)
  )
  ```
- This correctly implements FIFO ordering: joined_at ASC then sequence_number ASC

## 2. doctor queue listing ordering (incorrectly using session.id in triage/doctor APIs)
**Status: FIXED**

### Triage API - list_waiting_patients function:
- File: `backend/app/api/v1/triage.py`
- Line: 37
- Previous code: `.order_by(models.DoctorQueueEntry.joined_at, models.Session.id)`
- Issue: Used Session.id (UUID) as tie-breaker instead of sequence_number
- Fix applied: Changed to use models.DoctorQueueEntry.sequence_number
- Current code: `.order_by(models.DoctorQueueEntry.joined_at, models.DoctorQueueEntry.sequence_number)`

### Doctor API - read_doctor_sessions function:
- File: `backend/app/api/v1/doctor.py`
- Lines: 72-82
- Previous code: 
  ```python
  .order_by(
      case(
          (models.DoctorQueueEntry.status == "IN_CONSULTATION", 0),
          (models.DoctorQueueEntry.status == "CALLED", 1),
          (models.DoctorQueueEntry.status == "WAITING", 2),
          else_=3,
      ),
      models.DoctorQueueEntry.joined_at.asc(),
      models.Session.id,
  )
  ```
- Issue: Used Session.id (UUID) as final tie-breaker instead of sequence_number
- Fix applied: Changed final ordering from models.Session.id to models.DoctorQueueEntry.sequence_number
- Current code: 
  ```python
  .order_by(
      case(
          (models.DoctorQueueEntry.status == "IN_CONSULTATION", 0),
          (models.DoctorQueueEntry.status == "CALLED", 1),
          (models.DoctorQueueEntry.status == "WAITING", 2),
          else_=3,
      ),
      models.DoctorQueueEntry.joined_at.asc(),
      models.DoctorQueueEntry.sequence_number,
  )
  ```

## 3. any other FIFO queries found with incorrect ordering
**Status: NONE FOUND (so far)**
- Search completed for other order_by clauses involving queue entries
- No additional incorrect FIFO ordering found beyond the two APIs mentioned above

## 4. whether UUID/session_id ordering remained anywhere incorrectly
**Status: FIXED**
- Previously found UUID/session_id ordering incorrectly used as tie-breaker in:
  - Triage API list_waiting_patients function (line 37) - FIXED
  - Doctor API read_doctor_sessions function (lines 72-82) - FIXED
- After fixes, both APIs now use models.DoctorQueueEntry.sequence_number as the tie-breaker
- Verified no other order_by clauses in these files use incorrect tie-breakers

## 5. sequence_number nullability (NOT NULL for current Phase 5-created entries)
**Status: NEEDS VERIFICATION**
- Column definition: `sequence_number = Column(Integer, nullable=True)` (line 101 in DoctorQueueEntry model)
- Test evidence: `test_queue_tokens_are_daily_scoped_and_terminal_entries_leave_fifo` shows:
  - Line 518: `assert first_entry.sequence_number == 1`
  - Line 519: `assert second_entry.sequence_number == 2`
- This indicates that despite nullable=True, sequence_number IS being set to non-null values for Phase 5-created entries
- Likely mechanism: Application-level setting during queue entry creation (exact location not identified in current investigation)

## 6. files changed during this session
**Status: CONFIRMED**
- Modified file: `backend/app/api/v1/triage.py`
  - Fixed line 37: Changed order_by from using models.Session.id to models.DoctorQueueEntry.sequence_number
- Modified file: `backend/app/api/v1/doctor.py`
  - Fixed lines 72-82: Changed final order_by from models.Session.id to models.DoctorQueueEntry.sequence_number
- Note: The patient_queue_estimate function in backend/app/services/doctor_routing.py was verified to already be correct (no changes needed)

## 7. exact code status (patient_queue_estimate function)
**Status: VERIFIED CORRECT - NO CHANGES NEEDED**
- The patient_queue_estimate function in backend/app/services/doctor_routing.py was already correctly implemented
- Uses COUNT query with explicit FIFO condition for proper tie-breaking:
  ```python
  (models.DoctorQueueEntry.joined_at < entry.joined_at) |
  (
      (models.DoctorQueueEntry.joined_at == entry.joined_at) &
      (models.DoctorQueueEntry.sequence_number < entry.sequence_number)
  )
  ```
- This correctly implements FIFO ordering: joined_at ASC then sequence_number ASC
- No changes were needed to this function during this session

## 8. test execution status (TEST_EXECUTION_PENDING_ENVIRONMENT due to exit code 49)
**Status: PENDING**
- Unable to run tests due to environment issues returning exit code 49
- As per user instruction: "do not run tests if environment code 49 persists"
- Target test: `test_doctor_routing.py::test_queue_tokens_are_daily_scoped_and_terminal_entries_leave_fifo`
- Full module: `python -m pytest tests/test_doctor_routing.py -q`