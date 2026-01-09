"""PaperSqueeze CLI - Command-line interface."""

import argparse
import json
import logging
import sys
from pathlib import Path

from papersqueeze.config.loader import load_config
from papersqueeze.config.schema import AppConfig
from papersqueeze.api.paperless import PaperlessClient, DocumentSnapshot
from papersqueeze.exceptions import PaperSqueezeError, ConfigurationError


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config_or_exit(config_path: str | None = None) -> AppConfig:
    """Load configuration or exit with error message."""
    try:
        return load_config(config_path)
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)


def snapshot_to_dict(snapshot: DocumentSnapshot) -> dict:
    """Convert snapshot to a dict for display."""
    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "original_file_name": snapshot.original_file_name,
        "correspondent": {
            "id": snapshot.correspondent_id,
            "name": snapshot.correspondent_name,
        },
        "document_type": {
            "id": snapshot.document_type_id,
            "name": snapshot.document_type_name,
        },
        "tags": snapshot.tag_names,
        "custom_fields": snapshot.custom_fields,
        "content_length": snapshot.content_length,
        "content_hash": snapshot.content_hash,
        "created": snapshot.created,
        "added": snapshot.added,
        "modified": snapshot.modified,
    }


# =============================================================================
# Commands
# =============================================================================

def cmd_info(args: argparse.Namespace, config: AppConfig) -> int:
    """Show current configuration and status."""
    print("PaperSqueeze Configuration")
    print("=" * 40)
    print(f"Paperless URL: {config.paperless.url}")
    print(f"LLM Provider: {config.llm.provider}")
    print(f"Gatekeeper Model: {config.llm.gatekeeper_model}")
    print(f"Specialist Model: {config.llm.specialist_model}")
    print(f"Log Level: {config.log_level.value}")
    print(f"Dry Run: {config.processing.dry_run}")
    print()

    # Test Paperless connection
    print("Testing Paperless connection...")
    try:
        with PaperlessClient(config.paperless) as client:
            client.preload_cache()
            print("✓ Connection successful")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return 1

    return 0


def cmd_snapshot(args: argparse.Namespace, config: AppConfig) -> int:
    """Fetch and display document snapshot."""
    doc_id = args.doc_id

    try:
        with PaperlessClient(config.paperless) as client:
            snapshot = client.get_document_snapshot(doc_id)

            if args.json:
                print(json.dumps(snapshot_to_dict(snapshot), indent=2, default=str))
            else:
                print(f"Document {doc_id} Snapshot")
                print("=" * 40)
                print(f"Title: {snapshot.title}")
                print(f"Original Filename: {snapshot.original_file_name}")
                print(f"Correspondent: {snapshot.correspondent_name} (ID: {snapshot.correspondent_id})")
                print(f"Document Type: {snapshot.document_type_name} (ID: {snapshot.document_type_id})")
                print(f"Tags: {', '.join(snapshot.tag_names) or '(none)'}")
                print(f"Content Length: {snapshot.content_length} chars")
                print(f"Content Hash: {snapshot.content_hash}")
                print(f"Created: {snapshot.created}")
                print()
                print("Custom Fields:")
                if snapshot.custom_fields:
                    for name, value in snapshot.custom_fields.items():
                        print(f"  {name}: {value}")
                else:
                    print("  (none)")

                if args.content:
                    print()
                    print("Content (first 2000 chars):")
                    print("-" * 40)
                    print(snapshot.content[:2000])

    except PaperSqueezeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_process(args: argparse.Namespace, config: AppConfig) -> int:
    """Process a document (MVP: just snapshot for now)."""
    doc_id = args.doc_id
    logger = logging.getLogger("papersqueeze")

    logger.info(f"Processing document {doc_id}")
    logger.info(f"API URL from config: {config.paperless.url}")

    try:
        with PaperlessClient(config.paperless) as client:
            # Step 1: Take snapshot (pre-state)
            logger.info("Taking pre-state snapshot...")
            pre_snapshot = client.get_document_snapshot(doc_id)

            logger.info(f"Document: {pre_snapshot.title}")
            logger.info(f"Correspondent: {pre_snapshot.correspondent_name}")
            logger.info(f"Document Type: {pre_snapshot.document_type_name}")
            logger.info(f"Tags: {pre_snapshot.tag_names}")
            logger.info(f"Content length: {pre_snapshot.content_length}")
            logger.info(f"Content hash: {pre_snapshot.content_hash}")

            # Step 2: Template selection (placeholder)
            logger.info("Template selection: (not implemented yet)")

            # Step 3: Deterministic extraction (placeholder)
            logger.info("Deterministic extraction: (not implemented yet)")

            # Step 4: LLM extraction (placeholder)
            logger.info("LLM extraction: (not implemented yet - MVP skips AI)")

            # Step 5: Validation (placeholder)
            logger.info("Validation: (not implemented yet)")

            # Step 6: Commit (placeholder)
            if config.processing.dry_run:
                logger.info("DRY RUN: No changes applied")
            else:
                logger.info("Commit: (not implemented yet)")

            # Step 7: Post-verification (placeholder)
            logger.info("Post-verification: (not implemented yet)")

            print(f"Document {doc_id} processed successfully (MVP: snapshot only)")
            return 0

    except PaperSqueezeError as e:
        logger.error(f"Processing failed: {e}")
        return 1


def cmd_test_api(args: argparse.Namespace, config: AppConfig) -> int:
    """Test API connectivity and list metadata."""
    print("Testing Paperless-ngx API...")
    print()

    try:
        with PaperlessClient(config.paperless) as client:
            client.preload_cache()

            print("Tags:")
            for name in sorted(client._tag_cache.keys()):
                tag = client._tag_cache[name]
                print(f"  - {tag.name} (ID: {tag.id})")

            print()
            print("Correspondents:")
            for name in sorted(client._correspondent_cache.keys()):
                corr = client._correspondent_cache[name]
                print(f"  - {corr.name} (ID: {corr.id})")

            print()
            print("Document Types:")
            for name in sorted(client._document_type_cache.keys()):
                dt = client._document_type_cache[name]
                print(f"  - {dt.name} (ID: {dt.id})")

            print()
            print("Custom Fields:")
            for name in sorted(client._custom_field_cache.keys()):
                cf = client._custom_field_cache[name]
                print(f"  - {cf.name} (ID: {cf.id}, type: {cf.data_type})")

    except PaperSqueezeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="papersqueeze",
        description="PaperSqueeze - Intelligent document processing for Paperless-ngx",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to config.yaml",
        default=None,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # info command
    subparsers.add_parser("info", help="Show configuration and test connection")

    # test-api command
    subparsers.add_parser("test-api", help="Test API and list all metadata")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Get document snapshot")
    snapshot_parser.add_argument("doc_id", type=int, help="Document ID")
    snapshot_parser.add_argument("--json", action="store_true", help="Output as JSON")
    snapshot_parser.add_argument("--content", action="store_true", help="Include content preview")

    # process command
    process_parser = subparsers.add_parser("process", help="Process a document")
    process_parser.add_argument("doc_id", type=int, help="Document ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # Load config
    config = load_config_or_exit(args.config)

    # Override log level from config if not verbose
    if not args.verbose:
        setup_logging(config.log_level.value)

    # Dispatch command
    commands = {
        "info": cmd_info,
        "test-api": cmd_test_api,
        "snapshot": cmd_snapshot,
        "process": cmd_process,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args, config)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
