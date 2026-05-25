# Domain Pack Schema — Marketplace Agent/Broker Enrollment Integrity (v0.1)
DomainPackId: marketplaceagentbrokerenrollment
Version: 0.1.0

Purpose
- Support unauthorized enrollment / unauthorized plan switch detection and broker oversight workflows using enrollment transaction history and complaint/casework signals.

## 1) Entities

### Consumer
- consumer_id (surrogate)
- demographics_segment (optional; safe)
- geography (state/county; optional)

### Enrollment
- enrollment_id (surrogate)
- consumer_id (fk)
- issuer_id (fk)
- plan_id (fk)
- start_dt, end_dt
- status

### EnrollmentChangeEvent
- change_event_id (surrogate)
- enrollment_id (fk)
- consumer_id (fk)
- broker_npn (fk; nullable)
- change_type (enum: new_enroll, switch, terminate, update, other)
- change_dt (datetime)
- channel (enum/string; optional)
- source_system (string; optional)
- metadata (object; optional)

### AgentBroker
- broker_npn (string; stable)
- broker_org (optional)
- broker_status (optional)
- geography/service_area (optional)

### BrokerConsumerAssociation (important for “associated broker” controls)
- association_id (surrogate)
- consumer_id (fk)
- enrollment_id (fk; optional)
- broker_npn (fk)
- association_status (enum: associated, not_associated, pending, removed)
- association_start_dt, association_end_dt
- association_source (string; optional)

### ComplaintCase
- complaint_id (surrogate)
- consumer_id (fk)
- enrollment_id (fk; optional)
- broker_npn (fk; nullable if inferred)
- complaint_type (enum/string)
- complaint_dt (datetime)
- severity (optional)
- status/resolution (optional)
- linked_change_event_ids (array; optional)

### ConsentVerificationEvent (optional)
- consent_event_id (surrogate)
- consumer_id
- broker_npn (optional)
- consent_type (enum: three_way_call, attestation, other)
- consent_dt
- outcome (optional)

### ContactPoint / Device (optional, sensitive)
- contact_id / device_id (surrogate)
- consumer_id
- type (enum: phone, email, address, ip, device_fingerprint)
- value_hash (string; hashed)
- first_seen_dt, last_seen_dt

## 2) Edges (for graph features)
- consumer_has_enrollment (consumer → enrollment)
- enrollment_has_change_event (enrollment → change_event)
- change_event_attributed_to_broker (change_event → broker)
- complaint_against_broker (complaint → broker)
- broker_associated_with_consumer (broker ↔ consumer/enrollment)
- shared_contact_point (consumer ↔ consumer via contact/device)
- broker_shared_contact_cluster (broker ↔ contact cluster)

## 3) Minimum required fields
- change_event_id, change_dt, change_type, broker_npn (when present)
- complaint_id, complaint_dt, complaint_type, broker_npn (when present)
- association history (broker_npn + consumer/enrollment + effective dates)
