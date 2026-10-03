from simcore22.engine.engine_loop import main as run_engine


def show_menu():
    print("\n=== SimCore22 Console Menu ===")
    print("1. Start engine (Foresight + OCR -> leaderboard)")
    print("2. Exit")

    choice = input("Select an option: ")

    if choice == "1":
        run_engine()
    else:
        print("Goodbye.")


if __name__ == "__main__":
    show_menu()
