# Tests Directory

This directory contains test files for the instrument control system.

## Structure:
```
tests/
├── test_core/           # Tests for core functionality
├── test_devices/        # Tests for device communication
├── test_experiments/    # Tests for experiment protocols
├── test_operations/     # Tests for instrument operations
├── test_utils/          # Tests for utility functions
└── integration/         # Integration tests
```

## Test Categories:

### Unit Tests:
- Individual module testing
- Function-level validation
- Error handling verification

### Integration Tests:
- End-to-end experiment workflows
- Device communication validation
- System-level functionality

## Testing Framework:
Currently using manual testing with `test.py`. Future plans include:
- pytest framework
- Automated test execution
- Continuous integration

## Running Tests:
```bash
# Manual testing (current)
python test.py

# Future pytest implementation
pytest tests/
```

## Notes:
- Tests should not require physical hardware when possible
- Use mocking for device communication
- Include safety-critical test scenarios