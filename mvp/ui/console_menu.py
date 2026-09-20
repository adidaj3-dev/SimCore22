from mvp.engine.ingestion import run_live_pipeline

def show_menu():
    print("\n=== SimCore MVP Console Menu ===")
    print("1. Start GSPro Live Ingestion")
    print("2. Exit")

    choice = input("Select an option: ")

    if choice == "1":
        run_live_pipeline()
    else:
        print("Goodbye.")
