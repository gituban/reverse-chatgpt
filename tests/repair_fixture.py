def add_numbers(a, b):
    # Intentional v0.8f repair fixture bug.
    # The autonomous agent should discover this from CI failure logs.
    return a - b


def main():
    actual = add_numbers(20, 22)
    expected = 42

    assert actual == expected, (
        f"REPAIR_FIXTURE_FAILURE: "
        f"expected {expected}, got {actual}"
    )

    print("REPAIR_FIXTURE_PASS")


if __name__ == "__main__":
    main()
