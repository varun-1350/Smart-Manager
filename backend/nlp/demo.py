import json
import sys

from .intent_classifier import IntentClassifier
from .pipeline import analyze


def main() -> None:
    text = " ".join(sys.argv[1:]) or input("> ")
    result = analyze(text, IntentClassifier.load())
    print(json.dumps(result.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()