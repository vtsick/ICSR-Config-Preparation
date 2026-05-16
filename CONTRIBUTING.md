# Contributing to ICSR Config Modifier

Thank you for considering contributing to this project!

## About This Tool

This program (`modify_config.py`) currently addresses configurations of **GGSN/PGW Cisco Virtual Packet Core instances** specific to a particular customer. However, the underlying procedure should also work with:

- **MME instances**
- **Nodes containing EPDG services**

## Work in Progress

Please note that this is a **work in progress**. The tool has been developed to solve a specific use case, but contributions to improve its generality, robustness, and usability are extremely welcome.

## How to Contribute

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Commit your changes** (`git commit -m 'Add amazing feature'`)
5. **Push to the branch** (`git push origin feature/amazing-feature`)
6. **Open a Pull Request**

## Development Guidelines

- Follow the existing code style (4-space indentation, snake_case for variables/functions, UPPER_CASE for constants)
- Add clear docstrings to new functions
- Update documentation (README.md) if your changes affect usage
- Consider adding test cases if applicable
- Ensure your changes don't break existing functionality
- Run `python3 -m py_compile modify_config.py` to check for syntax errors
- Test with both dry-run and actual execution modes

## Reporting Issues

If you encounter bugs or have suggestions for improvement, please open an issue describing:
- The problem you encountered
- Steps to reproduce (if applicable)
- Expected behavior
- Actual behavior
- Any relevant configuration snippets (with sensitive information removed)

## License

By contributing, you agree that your contributions will be licensed under the same license as the repository.

Thank you for helping improve this tool!