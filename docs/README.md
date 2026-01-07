# Documentation Directory

This directory contains documentation for the instrument control system.

## Structure:
```
docs/
├── api/               # API documentation
├── user_guide/        # User guides and tutorials
├── developer_guide/   # Developer documentation
├── hardware/          # Hardware setup and configuration
└── examples/          # Code examples and tutorials
```

## Documentation Types:

### User Documentation:
- Getting started guides
- Experiment setup tutorials
- Troubleshooting guides
- Hardware configuration

### Developer Documentation:
- API reference
- Architecture overview
- Contributing guidelines
- Code style guidelines

### Hardware Documentation:
- Device specifications
- Wiring diagrams
- Configuration procedures
- Safety procedures

## Building Documentation:
Future plans include:
- Sphinx-based documentation
- Automatic API generation
- Interactive tutorials

## Viewing Documentation:
```bash
# Future: Serve documentation locally
python -m http.server 8000 --directory docs/_build/
```

## Notes:
- Documentation is written in Markdown format
- Code examples should be tested and current
- Include safety warnings for hardware operations