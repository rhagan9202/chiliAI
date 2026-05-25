# Test fixture

## Story foo.01: First

**ID:** foo.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** user, **I need** thing, **so that** outcome.

### Current State
- Nothing exists yet.

### Acceptance Criteria
- [ ] First criterion.
- [ ] Second criterion.

### Verification
- Run the test.

### Code touch points
- src/foo.py (new)

## Story foo.02: Second

**ID:** foo.02
**Status:** done
**Prerequisites:** [foo.01]
**Unblocks:** []
**Estimated size:** M
**Done:** 2026-05-24 · abc1234 · #42

**As a** user, **I need** more, **so that** outcome.

### Current State
- Exists at src/foo.py:1.

### Acceptance Criteria
- [x] Criterion one.
- [x] Criterion two.

### Verification
- pytest tests/foo/

### Code touch points
- src/foo.py (modify)
