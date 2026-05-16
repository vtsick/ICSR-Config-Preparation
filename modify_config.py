#!/usr/bin/env python3

import argparse
import logging
import re
from pathlib import Path


LOOPBACK_HEADER_RE = re.compile(r"^\s*interface\s+(\S+)\s+loopback\s*$")
IP_ADDRESS_RE = re.compile(r"^\s*ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*$")
DIAMETER_ENDPOINT_HEADER_RE = re.compile(r"^(\s*diameter endpoint\s+(\S+)\s*)$")
SYSTEM_HOSTNAME_RE = re.compile(r"^(\s*system hostname\s+)(\S+)(\s*)$", re.MULTILINE)
RADIUS_NAS_IDENTIFIER_RE = re.compile(r"^(\s*radius attribute nas-identifier\s+)(\S+)(\s*)$", re.MULTILINE)
TOP_LEVEL_CONTEXT_RE = re.compile(r"^  context\s+(\S+)\s*$", re.MULTILINE)
AAA_GROUP_BLOCK_RE = re.compile(r"(^    aaa group\s+(\S+)\s*$.*?^    (?:#?exit)\s*$\n?)", re.MULTILINE | re.DOTALL)
APN_BLOCK_RE = re.compile(r"(^    apn\s+(\S+)\s*$.*?^    (?:#?exit)\s*$\n?)", re.MULTILINE | re.DOTALL)
IMS_AUTH_SERVICE_BLOCK_RE = re.compile(
    r"(^    ims-auth-service\s+(\S+)\s*$.*?^    #exit\s*$\n?)",
    re.MULTILINE | re.DOTALL,
)
IP_POOL_LINE_RE = re.compile(r"(^    ip pool\s+(\S+)\s+.*$\n?)", re.MULTILINE)
SERVICE_REDUNDANCY_PROTOCOL_BLOCK_RE = re.compile(
    r"^    service-redundancy-protocol.*$\n.*?^    #exit\s*$",
    re.MULTILINE | re.DOTALL,
)


def extract_loopback_ips_from_text(config_text):
    """Return {interface_name: ip_address} for loopback interfaces in config text."""
    loopbacks = {}
    current_interface = None

    for line in config_text.splitlines():
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


def extract_loopback_ips(config_path):
    """Return {interface_name: ip_address} for loopback interfaces in a config."""
    with open(config_path, "r", encoding="utf-8") as infile:
        return extract_loopback_ips_from_text(infile.read())


def collect_loopback_discrepancies(source_loopbacks, target_loopbacks):
    """Return loopback interfaces present only in source or only in target."""
    source_names = set(source_loopbacks)
    target_names = set(target_loopbacks)
    return {
        "missing_in_target": sorted(source_names - target_names),
        "missing_in_source": sorted(target_names - source_names),
    }


def extract_diameter_endpoint_blocks_from_text(config_text):
    """Return {endpoint_name: block_text} for Diameter endpoint blocks in config text."""
    endpoints = {}
    current_name = None
    current_block = []

    for line in config_text.splitlines(keepends=True):
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


def extract_diameter_endpoint_blocks(config_path):
    """Return {endpoint_name: block_text} for Diameter endpoint blocks in a config."""
    with open(config_path, "r", encoding="utf-8") as infile:
        return extract_diameter_endpoint_blocks_from_text(infile.read())


def extract_named_objects(config_text, pattern):
    """Return {object_name: matched_text} for a block or line regex with group 2 as the name."""
    return {match.group(2): match.group(1) for match in pattern.finditer(config_text)}


def extract_top_level_contexts(config_text):
    """Return top-level contexts as ordered dict-like items."""
    matches = list(TOP_LEVEL_CONTEXT_RE.finditer(config_text))
    contexts = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(config_text)
        contexts.append(
            {
                "name": match.group(1),
                "text": config_text[start:end],
                "start": start,
                "end": end,
            }
        )

    return contexts


def find_service_redundancy_context_names(config_text):
    """Return top-level context names containing a full service-redundancy-protocol block."""
    return {
        context["name"]
        for context in extract_top_level_contexts(config_text)
        if SERVICE_REDUNDANCY_PROTOCOL_BLOCK_RE.search(context["text"])
    }


def remove_contexts_by_name(config_text, context_names):
    """Return config_text with the specified top-level contexts removed."""
    parts = []
    last_end = 0

    for context in extract_top_level_contexts(config_text):
        if context["name"] in context_names:
            parts.append(config_text[last_end:context["start"]])
            last_end = context["end"]

    parts.append(config_text[last_end:])
    return "".join(parts)


def restore_contexts_by_name(original_text, modified_text, context_names):
    """Restore the specified top-level contexts in modified_text from original_text."""
    original_contexts = {context["name"]: context for context in extract_top_level_contexts(original_text)}

    for context_name in context_names:
        modified_contexts = {context["name"]: context for context in extract_top_level_contexts(modified_text)}
        original_context = original_contexts.get(context_name)
        modified_context = modified_contexts.get(context_name)

        if original_context is None or modified_context is None:
            continue

        modified_text = (
            f"{modified_text[:modified_context['start']]}"
            f"{original_context['text']}"
            f"{modified_text[modified_context['end']:]}"
        )

    return modified_text


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


def sync_block_region(source_text, target_text, block_pattern, label):
    """Replace a contiguous block region in target_text with the source version."""
    source_matches = list(block_pattern.finditer(source_text))
    target_matches = list(block_pattern.finditer(target_text))

    if not source_matches and not target_matches:
        return target_text, 0

    source_region = "".join(match.group(1) for match in source_matches)

    if target_matches:
        start = target_matches[0].start(1)
        end = target_matches[-1].end(1)
        target_text = f"{target_text[:start]}{source_region}{target_text[end:]}"
    elif source_matches:
        raise ValueError(f"Could not locate insertion point for {label} in target context")

    return target_text, len(source_matches)


def find_context_names_with_pattern(config_text, pattern):
    """Return top-level context names whose text contains at least one match for pattern."""
    return [
        context["name"]
        for context in extract_top_level_contexts(config_text)
        if pattern.search(context["text"])
    ]


def sync_context_objects(source_text, target_text, context_names, sync_specs):
    """Sync selected object regions for the given top-level contexts."""
    source_contexts = {context["name"]: context for context in extract_top_level_contexts(source_text)}
    synced_counts = {label: 0 for label, _ in sync_specs}

    for context_name in context_names:
        target_contexts = {context["name"]: context for context in extract_top_level_contexts(target_text)}
        source_context = source_contexts.get(context_name)
        target_context = target_contexts.get(context_name)

        if source_context is None or target_context is None:
            raise ValueError(f"Context {context_name!r} not found in both source and target configs")

        updated_context_text = target_context["text"]
        for label, pattern in sync_specs:
            updated_context_text, synced_count = sync_block_region(
                source_context["text"],
                updated_context_text,
                pattern,
                label,
            )
            synced_counts[label] += synced_count

        target_text = (
            f"{target_text[:target_context['start']]}"
            f"{updated_context_text}"
            f"{target_text[target_context['end']:]}"
        )

    return target_text, synced_counts


def collect_discrepancies(source_text, target_text, object_specs):
    """Return discrepancy details for named config objects."""
    discrepancies = {}

    for label, pattern in object_specs:
        source_objects = extract_named_objects(source_text, pattern)
        target_objects = extract_named_objects(target_text, pattern)
        source_names = set(source_objects)
        target_names = set(target_objects)
        discrepancies[label] = {
            "missing_in_target": sorted(source_names - target_names),
            "missing_in_source": sorted(target_names - source_names),
        }

    return discrepancies


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
    with open(file4_path, "r", encoding="utf-8") as infile:
        original_target_content = infile.read()

    with open(file3_path, "r", encoding="utf-8") as infile:
        source_content = infile.read()

    skipped_context_names = (
        find_service_redundancy_context_names(source_content)
        | find_service_redundancy_context_names(original_target_content)
    )
    filtered_source_content = remove_contexts_by_name(source_content, skipped_context_names)
    filtered_target_content = remove_contexts_by_name(original_target_content, skipped_context_names)

    source_loopbacks = extract_loopback_ips_from_text(filtered_source_content)
    target_loopbacks = extract_loopback_ips_from_text(filtered_target_content)
    source_endpoints = extract_diameter_endpoint_blocks_from_text(filtered_source_content)
    target_endpoints = extract_diameter_endpoint_blocks_from_text(filtered_target_content)
    loopback_discrepancies = collect_loopback_discrepancies(source_loopbacks, target_loopbacks)

    replacements = {}
    for interface_name, source_ip in source_loopbacks.items():
        target_ip = target_loopbacks.get(interface_name)
        if target_ip and target_ip != source_ip:
            replacements[target_ip] = source_ip

    modified_content = original_target_content

    discrepancies = collect_discrepancies(
        filtered_source_content,
        filtered_target_content,
        [
            ("diameter endpoint", DIAMETER_ENDPOINT_HEADER_RE),
            ("apn", APN_BLOCK_RE),
            ("aaa group", AAA_GROUP_BLOCK_RE),
            ("ims-auth-service", IMS_AUTH_SERVICE_BLOCK_RE),
            ("ip pool", IP_POOL_LINE_RE),
        ],
    )

    modified_content, replaced_endpoints = replace_diameter_endpoint_blocks(
        modified_content,
        source_endpoints,
        target_endpoints,
        source_loopbacks,
        target_loopbacks,
    )

    for old_ip, new_ip in replacements.items():
        modified_content = replace_exact_ip(modified_content, old_ip, new_ip)

    service_context_names = [
        name
        for name in find_context_names_with_pattern(filtered_source_content, APN_BLOCK_RE)
        if name not in skipped_context_names
    ]
    ip_pool_context_names = [
        name
        for name in find_context_names_with_pattern(filtered_source_content, IP_POOL_LINE_RE)
        if name not in skipped_context_names
    ]

    modified_content, service_context_counts = sync_context_objects(
        source_content,
        modified_content,
        service_context_names,
        [
            ("apn", APN_BLOCK_RE),
            ("aaa group", AAA_GROUP_BLOCK_RE),
            ("ims-auth-service", IMS_AUTH_SERVICE_BLOCK_RE),
        ],
    )
    modified_content, ip_pool_context_counts = sync_context_objects(
        source_content,
        modified_content,
        ip_pool_context_names,
        [
            ("ip pool", IP_POOL_LINE_RE),
        ],
    )
    synced_context_counts = {
        "apn": service_context_counts["apn"],
        "aaa group": service_context_counts["aaa group"],
        "ims-auth-service": service_context_counts["ims-auth-service"],
        "ip pool": ip_pool_context_counts["ip pool"],
    }

    modified_content, replaced_line_counts = copy_matched_line_values(
        source_content,
        modified_content,
        [
            ("system hostname", SYSTEM_HOSTNAME_RE),
            ("radius attribute nas-identifier", RADIUS_NAS_IDENTIFIER_RE),
        ],
    )

    modified_content = restore_contexts_by_name(
        original_target_content,
        modified_content,
        skipped_context_names,
    )

    return (
        modified_content,
        replacements,
        replaced_endpoints,
        replaced_line_counts,
        synced_context_counts,
        loopback_discrepancies,
        discrepancies,
        sorted(skipped_context_names),
    )


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

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
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be changed without writing the output file",
    )
    parser.add_argument(
        "output_config",
        type=Path,
        help="output filename for the resulting configuration",
    )
    args = parser.parse_args()

    # Validate input files exist
    if not args.source_config.is_file():
        logger.error("Source config file does not exist: %s", args.source_config)
        return 1
        
    if not args.target_config.is_file():
        logger.error("Target config file does not exist: %s", args.target_config)
        return 1

    # Validate we can write to output file (or its directory)
    try:
        if not args.dry_run:
            # Try to open for writing to check permissions early
            with open(args.output_config, "a", encoding="utf-8"):
                pass
    except OSError as e:
        logger.error("Cannot write to output file %s: %s", args.output_config, e)
        return 1

    try:
        (
            modified_content,
            replacements,
            replaced_endpoints,
            replaced_line_counts,
            synced_context_counts,
            loopback_discrepancies,
            discrepancies,
            skipped_context_names,
        ) = modify_config(
            args.source_config,
            args.target_config,
        )
    except Exception as e:
        logger.error("Error processing configuration: %s", e)
        return 1

    if args.dry_run:
        logger.info("Dry run complete; no file written.")
    else:
        try:
            with open(args.output_config, "w", encoding="utf-8") as outfile:
                outfile.write(modified_content)
            logger.info("Modified configuration saved to %s", args.output_config)
        except OSError as e:
            logger.error("Failed to write output file: %s", e)
            return 1

    logger.info("Updated %d loopback IP mappings.", len(replacements))
    # Sort by IP length descending to prevent replacement conflicts
    # e.g., replace 10.0.0.1 before 10.0.0.10 to avoid partial matches
    sorted_replacements = sorted(replacements.items(), key=lambda x: (-len(x[0]), x[0]))
    for old_ip, new_ip in sorted_replacements:
        logger.info("%s -> %s", old_ip, new_ip)
    logger.info("Replaced %d diameter endpoint blocks.", len(replaced_endpoints))
    for endpoint_name in sorted(replaced_endpoints):
        logger.info("diameter endpoint %s", endpoint_name)
    for label, count in synced_context_counts.items():
        logger.info("Synced %d %s definition(s).", count, label)
    for context_name in skipped_context_names:
        logger.info("Skipped context with service-redundancy-protocol: %s", context_name)
    for label, count in replaced_line_counts.items():
        logger.info("Copied %d line(s) for %s.", count, label)
    if loopback_discrepancies["missing_in_target"] or loopback_discrepancies["missing_in_source"]:
        logger.warning(
            "Discrepancies for loopback interface: "
            "%d only in source, %d only in target.",
            len(loopback_discrepancies["missing_in_target"]),
            len(loopback_discrepancies["missing_in_source"]),
        )
        for name in loopback_discrepancies["missing_in_target"]:
            logger.warning("  source-only loopback interface: %s", name)
        for name in loopback_discrepancies["missing_in_source"]:
            logger.warning("  target-only loopback interface: %s", name)
    for label, diff in discrepancies.items():
        missing_in_target = diff["missing_in_target"]
        missing_in_source = diff["missing_in_source"]
        if not missing_in_target and not missing_in_source:
            continue
        logger.warning(
            "Discrepancies for %s: %d only in source, %d only in target.",
            label,
            len(missing_in_target),
            len(missing_in_source),
        )
        for name in missing_in_target:
            logger.warning("  source-only %s: %s", label, name)
        for name in missing_in_source:
            logger.warning("  target-only %s: %s", label, name)

    return 0


if __name__ == "__main__":
    main()
