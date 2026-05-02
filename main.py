"""App Factory - Automated Mobile App Production Pipeline.

Phase 1: Bedrock connection test and basic pipeline skeleton.
"""

from factory.client import test_connection


def main():
    print("=== App Factory ===")
    print("Testing Bedrock connection...\n")

    if test_connection():
        print("\nReady to build apps!")
    else:
        print("\nSetup incomplete. Check your .env file.")


if __name__ == "__main__":
    main()
