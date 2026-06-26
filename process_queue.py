"""
LLM Queue Processor
====================
Processes pending LLM requests from the llm_queue table.

Usage:
  python process_queue.py                  # Process all pending, then exit
  python process_queue.py --watch          # Continuously poll for new requests
  python process_queue.py --watch --interval 5   # Poll every 5 seconds
"""
import argparse
import os
import sys
import time

# Ensure ANTHROPIC_API_KEY is set
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
    print("Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

import anthropic

from core.config import DB_PATH, MODELS
from core.db import Database
from core.api_client import record_usage


def process_pending(db: Database, client: anthropic.Anthropic) -> int:
    """Process all pending LLM requests. Returns number processed."""
    rows = db.fetchall(
        "SELECT * FROM llm_queue WHERE status = 'pending' ORDER BY id ASC"
    )
    if not rows:
        return 0

    processed = 0
    for row in rows:
        row = dict(row)
        req_id = row["id"]
        agent_id = row["agent_id"]
        model = row["model"]
        task_type = row["task_type"]

        print(f"  Processing #{req_id} [{agent_id}] ({task_type}) model={model}...")

        # Mark as in-progress
        db.execute(
            "UPDATE llm_queue SET status = 'processing' WHERE id = ?", (req_id,)
        )

        try:
            messages = [{"role": "user", "content": row["prompt"]}]
            kwargs = {
                "model": model,
                "max_tokens": row["max_tokens"] or 4096,
                "messages": messages,
                "temperature": row["temperature"] or 0.7,
            }
            if row["system_prompt"]:
                kwargs["system"] = row["system_prompt"]

            response = client.messages.create(**kwargs)
            text = response.content[0].text

            usage = response.usage
            tokens_in = usage.input_tokens
            tokens_out = usage.output_tokens
            cached = getattr(usage, "cache_read_input_tokens", 0) or 0

            # Record token usage
            record_usage(
                db=db, agent_id=agent_id, model=model,
                tokens_in=tokens_in, tokens_out=tokens_out,
                task_type=task_type, cached_tokens=cached,
            )

            # Write response back
            db.execute(
                "UPDATE llm_queue SET status = 'completed', response = ?, "
                "completed_at = datetime('now') WHERE id = ?",
                (text, req_id),
            )
            print(f"    Done: {tokens_in} in / {tokens_out} out tokens")
            processed += 1

        except Exception as e:
            print(f"    ERROR: {e}")
            db.execute(
                "UPDATE llm_queue SET status = 'failed', response = ? WHERE id = ?",
                (str(e), req_id),
            )

    return processed


def main():
    parser = argparse.ArgumentParser(description="Process LLM queue requests")
    parser.add_argument("--watch", action="store_true", help="Continuously poll for new requests")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds (default: 5)")
    args = parser.parse_args()

    db = Database(DB_PATH)
    client = anthropic.Anthropic()

    # Show queue status
    pending = db.fetchone("SELECT COUNT(*) AS c FROM llm_queue WHERE status = 'pending'")
    total = db.fetchone("SELECT COUNT(*) AS c FROM llm_queue")
    print(f"LLM Queue: {pending['c']} pending / {total['c']} total")

    if args.watch:
        print(f"Watching for new requests every {args.interval}s... (Ctrl+C to stop)")
        try:
            while True:
                n = process_pending(db, client)
                if n:
                    print(f"Processed {n} request(s)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        n = process_pending(db, client)
        print(f"\nProcessed {n} request(s)")

    db.close()


if __name__ == "__main__":
    main()
