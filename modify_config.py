#!/usr/bin/env python3

import argparse
import re
from pathlib import Path


LOOPBACK_HEADER_RE = re.compile(r"^\s*interface\s+(\S+)\s+loopback\s*$")
IP_ADDRESS_RE = re.compile(r"^\s*ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*$")
DIAMETER_ENDPOINT_HEADER_RE = re.compile(r"^(\s*diameter endpoint\s+(\S+)\s*)$")
SYSTEM_HOSTNAME_RE = re.compile(r"^(\s*system hostname\s+)(\S+)(\s*)$", re.MULTILINE)
RADIUS_NAS_IDENTIFIER_RE = re.compile(r"^(\s*radius attribute nas-identifier\s+)(\S+)(\s*)$", re.MULTILINE)


def extract_loopback_ips(config_path):
    """Return {interface_name: ip_address} for loopback interfaces in a config."""
    loopbacks = {}
    current_interface = None

    with open(config_path, "r", encoding="utf-8") as infile:
        for line in infile:
            header_match = LOOPBACK_HEADER_RE.match(line)
            if header_match:
                current_interface = header_match.group(1)
                continue

            if current_interface is None:
                continue

            ip_match = IP_ADDRESS_RE.match(line)
            if ip_match:
                loopbacks[current_interface] = ip_match.group(1)
                continue

            if line.strip() == "#exit":
                current_interface = None

    return loopbacks


def extract_diameter_endpoint_blocks(config_path):
    """Return {endpoint_name: block_text} for Diameter endpoint blocks in a config."""
    endpoints = {}
    current_name = None
    current_block = []

    with open(config_path, "r", encoding="utf-8") as infile:
        for line in infile:
            header_match = DIAMETER_ENDPOINT_HEADER_RE.match(line.rstrip("\n"))
            if header_match:
                current_name = header_match.group(2)
                current_block = [line]
                continue

            if current_name is None:
                continue

            current_block.append(line)
            if line.strip() == "#exit":
                endpoints[current_name] = "".join(current_block)
                current_name = None
                current_block = []

    return endpoints


def replace_exact_ip(text, old_ip, new_ip):
    """Replace an IP only when it appears as a standalone IPv4 token."""
    pattern = re.compile(rf"(?<![\d.]){re.escape(old_ip)}(?![\d.])")
    return pattern.sub(new_ip, text)


def copy_matched_line_values(source_text, target_text, patterns):
    """Copy full-line values from source_text into matching lines in target_text."""
    replaced_counts = {}

    for label, pattern in patterns:
        source_matches = list(pattern.finditer(source_text))
        target_matches = list(pattern.finditer(target_text))
        count = min(len(source_matches), len(target_matches))

        if count == 0:
            replaced_counts[label] = 0
            continue

        parts = []
        last_end = 0

        for index in range(count):
            target_match = target_matches[index]
            source_match = source_matches[index]
            replacement = f"{target_match.group(1)}{source_match.group(2)}{target_match.group(3)}"
            parts.append(target_text[last_end:target_match.start()])
            parts.append(replacement)
            last_end = target_match.end()

        parts.append(target_text[last_end:])
        target_text = "".join(parts)
        replaced_counts[label] = count

    return target_text, replaced_counts


def replace_diameter_endpoint_blocks(text, source_blocks, target_blocks, source_loopbacks, target_loopbacks):
    """
    Replace matching Diameter endpoint blocks in text with the source version
    when those blocks reference loopback IPs.
    """
    loopback_ips = set(source_loopbacks.values()) | set(target_loopbacks.values())
    replaced_endpoints = []

    for endpoint_name, source_block in source_blocks.items():
        target_block = target_blocks.get(endpoint_name)
        if not target_block:
            continue

        if target_block == source_block:
            continue

        if not any(ip in source_block or ip in target_block for ip in loopback_ips):
            continue

        text = text.replace(target_block, source_block, 1)
        replaced_endpoints.append(endpoint_name)

    return text, replaced_endpoints


def modify_config(file3_path, file4_path):
    """
    Copy loopback IP addresses from file3 into the matching loopback interfaces in file4.

    All exact references to the old file4 loopback IPs are also updated in the resulting
    configuration, including interface blocks, BGP network statements, prefix-lists,
    and any other direct IP references.
    """
    source_loopbacks = extract_loopback_ips(file3_path)
    target_loopbacks = extract_loopback_ips(file4_path)
    source_endpoints = extract_diameter_endpoint_blocks(file3_path)
    target_endpoints = extract_diameter_endpoint_blocks(file4_path)

    replacements = {}
    for interface_name, source_ip in source_loopbacks.items():
        target_ip = target_loopbacks.get(interface_name)
        if target_ip and target_ip != source_ip:
            replacements[target_ip] = source_ip

    with open(file4_path, "r", encoding="utf-8") as infile:
        modified_content = infile.read()

    with open(file3_path, "r", encoding="utf-8") as infile:
        source_content = infile.read()

    modified_content, replaced_endpoints = replace_diameter_endpoint_blocks(
        modified_content,
        source_endpoints,
        target_endpoints,
        source_loopbacks,
        target_loopbacks,
    )

    for old_ip, new_ip in replacements.items():
        modified_content = replace_exact_ip(modified_content, old_ip, new_ip)

    modified_content, replaced_line_counts = copy_matched_line_values(
        source_content,
        modified_content,
        [
            ("system hostname", SYSTEM_HOSTNAME_RE),
            ("radius attribute nas-identifier", RADIUS_NAS_IDENTIFIER_RE),
        ],
    )

    return modified_content, replacements, replaced_endpoints, replaced_line_counts


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Copy matching loopback-related settings from a source StarOS "
            "configuration into a target configuration."
        )
    )
    parser.add_argument(
        "source_config",
        type=Path,
        help="input config used as the source of loopback-related values",
    )
    parser.add_argument(
        "target_config",
        type=Path,
        help="config to modify based on the source config",
    )
    parser.add_argument(
        "output_config",
        type=Path,
        help="output filename for the resulting configuration",
    )
    args = parser.parse_args()

    modified_content, replacements, replaced_endpoints, replaced_line_counts = modify_config(
        args.source_config,
        args.target_config,
    )

    with open(args.output_config, "w", encoding="utf-8") as outfile:
        outfile.write(modified_content)

    print(f"Updated {len(replacements)} loopback IP mappings.")
    for old_ip, new_ip in sorted(replacements.items()):
        print(f"{old_ip} -> {new_ip}")
    print(f"Replaced {len(replaced_endpoints)} diameter endpoint blocks.")
    for endpoint_name in sorted(replaced_endpoints):
        print(f"diameter endpoint {endpoint_name}")
    for label, count in replaced_line_counts.items():
        print(f"Copied {count} line(s) for {label}.")
    print(f"Modified configuration saved to {args.output_config}")


if __name__ == "__main__":
    main()
