# ICSR Config Modifier v1.0.1

This repository contains `modify_config.py`, a small utility for generating a new configuration file based on two StarOS configuration snapshots.

## Purpose

The script is intended to help prepare two StarOS nodes for Inter Chassis Session Redundancy (ICSR).

For ICSR, both nodes must have the same service-facing configuration so sessions can be handled consistently on either chassis. At the same time, the node-specific L3 interconnections must remain individual for each node and should not be blindly cloned.

This tool automates the parts of the service configuration that need to be aligned between the nodes while leaving the target node's non-shared L3 connectivity in place.

**Note**: This program currently addresses configurations of GGSN/PGW Cisco Virtual Packet Core instances specific to a particular customer while the procedure also should work with MME instances as well as with nodes which contain EPDG services. See CONTRIBUTING.md for details.

## What It Does

Given:

- `node-1-1.cfg` as the reference configuration
- `node-2-1.cfg` as the base configuration

Run:

```bash
python3 modify_config.py node-1-1.cfg node-2-1.cfg node-2-1-new.cfg
```

the script produces:

- `node-2-1-new.cfg`

The generated configuration keeps the base node's config as a starting point and selectively copies service-related values from the reference node.

The script currently:

- copies loopback interface IP addresses from the reference config into matching loopback interfaces in the base config
- updates exact references to the replaced loopback IPs across the base config
- replaces matching Diameter endpoint blocks in the base config with the reference versions when those endpoints use loopback IPs
- copies `system hostname` from the reference config into the generated output
- copies `radius attribute nas-identifier` values from the reference config into the generated output

## Usage

Place these files in the same directory:

- `modify_config.py`
- your reference config (source of values to copy)
- your base config (to be modified)

Run:

```bash
python3 modify_config.py <reference.cfg> <base.cfg> <output.cfg>
```

Optional arguments:

- `-n, --dry-run`: Show what would be changed without writing the output file

The script creates a new output file and does not modify the input configuration files.

## Notes

- Requires Python 3.8+
- Configuration files are intentionally excluded from git tracking.
- The script requires three positional arguments: reference config, base config, and output config.
- Review the resulting config before deployment, especially around node-specific transport and routing sections.
