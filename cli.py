"""Terminal interface: python cli.py "top 5 categories by revenue" [--chart]"""
import argparse
import logging

from analyst import run_question


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the AI data analyst a question.")
    parser.add_argument("question")
    parser.add_argument("--chart", action="store_true", help="open the chart in a browser")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    out = run_question(args.question)
    if out.get("sql"):
        print(f"SQL:\n{out['sql']}\n")
    if out.get("df") is not None:
        print(out["df"].head(20).to_string(index=False), "\n")
    print(out.get("answer", ""))
    if args.chart and out.get("figure") is not None:
        out["figure"].show()


if __name__ == "__main__":
    main()
