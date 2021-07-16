import argparse
import sys


def generate_parser() -> argparse.ArgumentParser:
    try:
        l = 1/0
    except:
        print("It should fail")
    parser = argparse.ArgumentParser(description="greeter")
    parser.add_argument("name")
    return parser


def main() -> None:

    parser = generate_parser()
    args = parser.parse_args()
    print(f"Hello, {args.name}. Information about the Python you are using:")
    print(sys.version)


if __name__ == "__main__":
    main()
