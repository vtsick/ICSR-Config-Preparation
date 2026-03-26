# ICSR Config Modifier

This repository contains `modify_config.py`, a small utility for generating a new configuration file based on two StarOS configuration snapshots.

## What It Does

Given:

- `nn-b2b-sae-3-1.cfg` as the source configuration
- `nn-b2b-sae-4-1.cfg` as the target configuration

the script produces:

- `nn-b2b-sae-4-1-new.cfg`

The script currently:

- copies loopback interface IP addresses from the source config into matching loopback interfaces in the target config
- updates exact references to the replaced loopback IPs across the target config
- replaces matching Diameter endpoint blocks in the target config with the source versions when those endpoints use loopback IPs
- copies `system hostname` from the source config into the generated output
- copies `radius attribute nas-identifier` values from the source config into the generated output

## Usage

Place these files in the same directory:

- `modify_config.py`
- your source config
- your target config

Run:

```bash
python3 modify_config.py <source.cfg> <target.cfg> <output.cfg>
```

Example:

```bash
python3 modify_config.py nn-b2b-sae-3-1.cfg nn-b2b-sae-4-1.cfg nn-b2b-sae-4-1-new.cfg
```

## Notes

- Configuration files are intentionally excluded from git tracking.
- The script requires three positional arguments: source config, target config, and output config.
